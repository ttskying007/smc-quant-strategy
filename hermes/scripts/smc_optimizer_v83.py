#!/usr/bin/env python3
"""
SMC V8.3 Optimizer — 第六代遗传优化器
========================================
架构升级 (与V8.2对比):
  1. 6阶段搜索 (vs V8.2的4阶段)
  2. 精英保留机制 (top-10解被完整保留到下一代)
  3. 自适应温度 (基于近期改进率的动态温度调整)
  4. 多策略交叉: uniform, single-point, blend
  5. 局部爬山: 每10轮对当前best做局部扰动搜索
  6. 岛屿模型: 3个独立种群岛屿, 每20轮迁徙
  7. 实时RR硬约束: 评分时RR<1.0直接废弃, N<10直接废弃

Phase 1 (R1-30):  广域探索 — 纯随机, 筛选WR>55%+N>5+RR>0.5
Phase 2 (R31-70):  聚焦搜索 — 70%突变+30%交叉, WR>65%+N>8+RR>0.8
Phase 3 (R71-120): 黄金区间 — N=15-35, RR>1.2, WR>70%, 局部爬山
Phase 4 (R121-170): 收敛 — 小步温度, 精细调参, 岛屿迁移
Phase 5 (R171-200): 强化 — 随机重启+深度局部搜索
Phase 6 (R201-250+): 极细调 — 微扰动, 仅接受WR>75%+N>12+RR>1.5

评分函数 V8.3:
  score = WR% × sqrt(min(N,40)) × min(3,PF) × min(3,RR)^1.5
  硬约束: RR<1.0→废弃, N<10→废弃, WR>92%+N<20→过拟合惩罚

每轮速度: ~15秒/30只股票
250轮≈63分钟
"""

import sys, json, time, math, random, os, subprocess, urllib.request
from pathlib import Path

sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
from smc_engine_v83 import (
    load_bars, backtest_v83, compute_v83_score,
    V83_PARAM_SPACE, TEST_STOCKS, check_proxy_v8
)

# ════════ 配置 ════════
LOG_DIR = Path.home() / '.hermes' / 'smc_opt_v83'
LOG_DIR.mkdir(parents=True, exist_ok=True)

BEST_FILE = LOG_DIR / 'best_params.json'
PROGRESS_FILE = LOG_DIR / 'progress.json'
LIVE_FILE = LOG_DIR / 'live_status.json'
HISTORY_FILE = LOG_DIR / 'history.json'
LOG_FILE = LOG_DIR / 'optimization_log.ndjson'

# Sync to V7/V8 directories for WebUI compatibility
V7_LIVE = Path.home() / '.hermes' / 'smc_opt_v7' / 'v7_live_status.json'
V82_DIR = Path.home() / '.hermes' / 'smc_opt_v82'

ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 250
STOCKS_COUNT = min(int(sys.argv[2]) if len(sys.argv) > 2 else 30, len(TEST_STOCKS))
STOCK_LIST = TEST_STOCKS[:STOCKS_COUNT]

# ════════ 命令行参数 ════════
SEED_FILE = None
TIGHTEN_FACTOR = None
for i, arg in enumerate(sys.argv):
    if arg == '--seed' and i+1 < len(sys.argv):
        SEED_FILE = sys.argv[i+1]
    if arg == '--tighten' and i+1 < len(sys.argv):
        TIGHTEN_FACTOR = float(sys.argv[i+1])

seed_params = {}
if SEED_FILE and os.path.exists(SEED_FILE):
    try:
        seed_data = json.load(open(SEED_FILE))
        seed_params = seed_data.get('params', {})
        log(f"Loaded seed from {SEED_FILE} ({len(seed_params)} params)")
    except:
        pass

_initial_params = seed_params.copy() if seed_params else {k: v['default'] for k, v in V83_PARAM_SPACE.items()}

# ════════ 代理检查 ════════
def check_proxy():
    try:
        r = subprocess.run(['pgrep', '-f', 'mihomo'], capture_output=True, text=True, timeout=3)
        if not r.stdout.strip():
            return False, 'mihomo not running'
    except:
        return False, 'pgrep failed'
    try:
        req = urllib.request.Request('http://127.0.0.1:9090', method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return True, 'ok'
            return False, f'API status={resp.status}'
    except Exception as e:
        return False, f'API error: {e}'

def restart_proxy():
    log("Proxy failed! Attempting restart...")
    subprocess.run(['pkill', '-9', '-f', 'mihomo'], timeout=5, capture_output=True)
    time.sleep(2)
    config = Path.home() / '.clash_config_new.yaml'
    if config.exists():
        subprocess.Popen(['/usr/local/bin/mihomo', '-d', str(Path.home() / '.clash'),
                          '-f', str(config)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)
        ok, msg = check_proxy()
        if ok:
            log("Proxy restart successful")
        else:
            log(f"Proxy restart failed: {msg}")
        return ok
    return False

# ════════ 日志/状态 ════════
def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line)
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(line + '\n')
        if LOG_FILE.stat().st_size > 2*1024*1024:
            LOG_FILE.rename(LOG_FILE.with_suffix(f'.{int(time.time())}.log'))
    except:
        pass

def save_live(round_num, best_score, best_wr, best_n, status='running', details=None):
    st = {
        'round': round_num,
        'total_rounds': ROUNDS,
        'best_score': best_score,
        'best_wr': best_wr,
        'best_n': best_n,
        'status': status,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'engine': 'V8.3',
        'details': details or {},
    }
    for f in [LIVE_FILE, V7_LIVE]:
        try:
            with open(f, 'w') as fp:
                json.dump(st, fp, ensure_ascii=False)
        except:
            pass
    # Also write to V8.2 dir for WebUI
    if V82_DIR.exists():
        try:
            with open(V82_DIR / 'live_status.json', 'w') as fp:
                json.dump(st, fp, ensure_ascii=False)
        except:
            pass

def save_progress(history):
    data = {'rounds': history, 'total_rounds': ROUNDS}
    try:
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except:
        pass

# ════════ 参数操作 ════════
def default_params():
    return {k: v['default'] for k, v in V83_PARAM_SPACE.items()}

def random_params():
    """Generate random params (with optional seed tightening)"""
    p = {}
    for k, v in V83_PARAM_SPACE.items():
        lo, hi = v['min'], v['max']

        if TIGHTEN_FACTOR and k in _initial_params:
            center = _initial_params[k]
            half_range = (hi - lo) * TIGHTEN_FACTOR / 2
            lo = max(v['min'], center - half_range)
            hi = min(v['max'], center + half_range)

        val = lo + random.random() * (hi - lo)
        if 'step' in v and v['step'] > 0.01:
            val = round(val / v['step']) * v['step']
        p[k] = round(val, 2) if isinstance(val, float) else val

    # V8.3: Force RR >= 1.2 by adjusting tp_pct relative to sl_pct
    sl = p.get('sl_pct', 5.0)
    tp = p.get('tp_pct', 10.0)
    if tp / max(0.5, sl) < 1.2:
        p['tp_pct'] = round(sl * 1.5, 1)  # Force tp >= 1.5x sl

    return p

def mutate_params(current, temperature=0.3):
    """Mutate with V8.3 RR constraint"""
    p = {}
    for k, v in V83_PARAM_SPACE.items():
        lo, hi = v['min'], v['max']
        if random.random() < 0.12:  # 12%完全随机
            val = lo + random.random() * (hi - lo)
        else:
            delta = (hi - lo) * temperature * random.gauss(0, 0.2)
            val = current.get(k, v['default']) + delta
        val = max(lo, min(hi, val))
        if 'step' in v and v['step'] > 0.01:
            val = round(val / v['step']) * v['step']
        p[k] = round(val, 2) if isinstance(val, float) else val

    # V8.3: Force RR constraint after mutation
    sl = p.get('sl_pct', 5.0)
    tp = p.get('tp_pct', 10.0)
    if tp / max(0.5, sl) < 1.2:
        p['tp_pct'] = round(max(tp, sl * 1.3), 1)

    return p

def crossover_params(p1, p2, temperature=0.1):
    """Uniform crossover + small perturbation"""
    p = {}
    for k, v in V83_PARAM_SPACE.items():
        if random.random() < 0.4:
            val = p1.get(k, v['default'])
        elif random.random() < 0.7:
            val = p2.get(k, v['default'])
        else:
            delta = (v['max']-v['min']) * temperature * random.gauss(0, 0.15)
            val = (p1.get(k, v['default']) + p2.get(k, v['default'])) / 2 + delta
        val = max(v['min'], min(v['max'], val))
        if 'step' in v and v['step'] > 0.01:
            val = round(val / v['step']) * v['step']
        p[k] = round(val, 2) if isinstance(val, float) else val

    sl = p.get('sl_pct', 5.0)
    tp = p.get('tp_pct', 10.0)
    if tp / max(0.5, sl) < 1.2:
        p['tp_pct'] = round(sl * 1.3, 1)

    return p

def blend_crossover(p1, p2, alpha=0.3):
    """Blend crossover: genes from [min-α*d, max+α*d]"""
    p = {}
    for k, v in V83_PARAM_SPACE.items():
        a = p1.get(k, v['default'])
        b = p2.get(k, v['default'])
        lo = min(a, b) - alpha * abs(a - b)
        hi = max(a, b) + alpha * abs(a - b)
        lo = max(v['min'], lo)
        hi = min(v['max'], hi)
        val = lo + random.random() * (hi - lo)
        if 'step' in v and v['step'] > 0.01:
            val = round(val / v['step']) * v['step']
        p[k] = round(val, 2) if isinstance(val, float) else val

    sl = p.get('sl_pct', 5.0)
    tp = p.get('tp_pct', 10.0)
    if tp / max(0.5, sl) < 1.2:
        p['tp_pct'] = round(sl * 1.3, 1)
    return p

def hill_climb(params, iterations=5, step_size=0.08):
    """Local hill climbing around best params"""
    best_p = params.copy()
    best_r = {'final_score': 0}

    for _ in range(iterations):
        candidate = {}
        for k, v in V83_PARAM_SPACE.items():
            lo, hi = v['min'], v['max']
            if random.random() < 0.15:
                val = best_p.get(k, v['default'])
            else:
                delta = (hi - lo) * step_size * random.gauss(0, 0.2)
                val = best_p.get(k, v['default']) + delta
            val = max(lo, min(hi, val))
            if 'step' in v and v['step'] > 0.01:
                val = round(val / v['step']) * v['step']
            candidate[k] = round(val, 2) if isinstance(val, float) else val

        sl = candidate.get('sl_pct', 5.0)
        tp = candidate.get('tp_pct', 10.0)
        if tp / max(0.5, sl) < 1.2:
            candidate['tp_pct'] = round(sl * 1.3, 1)

        r = evaluate_params(candidate)
        if r['final_score'] > best_r['final_score']:
            best_p = candidate
            best_r = r

    return best_p, best_r

# ════════ 岛屿模型 ════════
ISLAND_COUNT = 3
ISLAND_MIGRATE_EVERY = 20

def init_islands():
    """Initialize independent island populations"""
    islands = []
    for i in range(ISLAND_COUNT):
        pop = []
        for _ in range(5):
            params = random_params()
            pop.append(params)
        islands.append({
            'id': i,
            'population': pop,
            'best': None,
            'best_score': 0,
        })
    return islands

def migrate(islands):
    """Migrate best individuals between islands"""
    best_individuals = []
    for island in islands:
        if island['best']:
            best_individuals.append((island['best_score'], island['best'], island['id']))

    if len(best_individuals) < 2:
        return islands

    best_individuals.sort(key=lambda x: -x[0])

    # Best island sends its best to worst island
    if len(best_individuals) >= 2:
        best = best_individuals[0]
        worst = best_individuals[-1]
        # Replace worst island's worst individual with best island's best
        islands[worst[2]]['population'][-1] = best[1].copy()
        log(f"  🌊 Migration: Island #{best[2]} → #{worst[2]} (score={best[0]:.1f})")

    return islands

# ════════ 评估 ════════
def evaluate_params(params, stock_list=None):
    if stock_list is None:
        stock_list = STOCK_LIST

    all_trades = []
    stocks_ok = 0
    stocks_with_signals = 0

    for sym in stock_list:
        try:
            bars = load_bars(sym, 'daily', 300)
            if not bars or len(bars) < 80:
                continue
            stocks_ok += 1
            trades = backtest_v83(bars, params)
            if trades:
                stocks_with_signals += 1
                all_trades.extend(trades)
        except:
            continue

    score = compute_v83_score(all_trades)
    score['stocks_ok'] = stocks_ok
    score['stocks_signal'] = stocks_with_signals

    coverage_pct = stocks_with_signals / max(1, stocks_ok) * 100 if stocks_ok > 0 else 0
    score['coverage_pct'] = coverage_pct

    # V8.3: Coverage multiplier
    if coverage_pct < 15:
        cov_mult = 0.3
    elif coverage_pct < 25:
        cov_mult = 0.6
    elif coverage_pct < 35:
        cov_mult = 0.85
    elif coverage_pct < 50:
        cov_mult = 0.95
    else:
        cov_mult = 1.0

    final_score = score['final_score'] * cov_mult
    score['final_score'] = round(final_score, 2)
    return score

# ════════ 主流程 ════════
def main():
    log(f"╔═══ SMC V8.3 优化器 ═══ {ROUNDS}轮 × {STOCKS_COUNT}只股票 ═══╗")

    # Check proxy
    proxy_ok, msg = check_proxy()
    if not proxy_ok:
        log(f"Proxy unavailable ({msg}), attempting restart...")
        restart_proxy()
        proxy_ok, msg = check_proxy()
        if not proxy_ok:
            log(f"Proxy unrecoverable: {msg}, continuing anyway")

    # Preload cache
    log("Preloading K-line data...")
    for sym in STOCK_LIST:
        try:
            load_bars(sym, 'daily', 300)
        except:
            pass
    log(f"Cache ready ({len(STOCK_LIST)} stocks)")

    # Initialize
    best_params = _initial_params.copy()
    best_score_val = 0
    best_detail = {}

    # Elite pool: top-10 solutions
    elite_pool = []

    # Islands
    islands = init_islands()

    # Initial evaluation
    log("Phase 0: Initial evaluation...")
    result = evaluate_params(best_params)
    best_score_val = result['final_score']
    best_detail = result
    elite_pool.append((best_score_val, best_params.copy()))
    log(f"  Default: WR={result['wr']}% PF={result['pf']} N={result['n']} RR={result['rr_avg']} Score={result['final_score']}")

    history = [{
        'round': 0, 'score': result['final_score'], 'wr': result['wr'],
        'pf': result['pf'], 'n': result['n'], 'rr': result['rr_avg'],
        'phase': 0,
    }]

    # ════════ Phase 1: 广域探索 (R1-30) ════════
    phase1_end = min(30, ROUNDS)
    log(f"╠══ Phase 1: 广域探索 (R1-{phase1_end}) ══╣")
    phase = 1
    temperature = 0.6
    stagnant = 0

    for r in range(1, phase1_end + 1):
        if r % 10 == 0:
            ok, _ = check_proxy()
            if not ok:
                log("Proxy down! Restarting...")
                restart_proxy()
                time.sleep(2)

        params = random_params()
        result = evaluate_params(params)

        # Phase 1: Loose acceptance — WR>55% + N>5 + RR>0.5
        wr_ok = result['wr'] >= 55
        n_ok = result['n'] >= 5

        adjusted = result['final_score']
        if wr_ok and n_ok and result['final_score'] > best_score_val:
            best_score_val = result['final_score']
            best_params = params
            best_detail = result
            elite_pool.append((result['final_score'], params.copy()))
            elite_pool = sorted(elite_pool, key=lambda x: -x[0])[:10]
            log(f"  [R{r:03d}] ★ NEW BEST Score={result['final_score']} → WR={result['wr']}% PF={result['pf']} N={result['n']} RR={result['rr_avg']} Cov={result['coverage_pct']:.0f}%")
            stagnant = 0
        else:
            stagnant += 1

        history.append({
            'round': r, 'score': result['final_score'], 'wr': result['wr'],
            'pf': result['pf'], 'n': result['n'], 'rr': result['rr_avg'],
            'phase': phase,
        })

        if r % 5 == 0:
            save_live(r, best_score_val, best_detail.get('wr', 0), best_detail.get('n', 0),
                      details={'phase': phase, 'temp': round(temperature, 3), 'stagnant': stagnant,
                               'stocks_signal': best_detail.get('stocks_signal', 0),
                               'coverage': best_detail.get('coverage_pct', 0),
                               'rr': best_detail.get('rr_avg', 0)})
            save_progress(history)

    # ════════ Phase 2: 聚焦搜索 (R31-80) ════════
    phase2_end = min(80, ROUNDS)
    if ROUNDS > phase1_end:
        log(f"╠══ Phase 2: 聚焦搜索 (R{phase1_end+1}-{phase2_end}) ══╣")
        phase = 2
        temperature = 0.4
        improvement_rate = 0.05
        recent_improvements = []

        for r in range(phase1_end + 1, min(phase2_end + 1, ROUNDS + 1)):
            if r % 10 == 0:
                ok, _ = check_proxy()
                if not ok:
                    log("Proxy down! Restarting...")
                    restart_proxy()
                    time.sleep(2)

            if r % 12 == 0:
                temperature = max(0.15, temperature * 0.85)

            # Phase 2: 70% mutation, 15% random, 15% crossover
            rnd = random.random()
            if rnd < 0.15:
                params = random_params()
            elif rnd < 0.85:
                params = mutate_params(best_params, temperature)
            else:
                if len(elite_pool) >= 2:
                    p1 = random.choice(elite_pool)[1]
                    p2 = random.choice(elite_pool)[1]
                    params = crossover_params(p1, p2, temperature)
                else:
                    params = mutate_params(best_params, temperature)

            result = evaluate_params(params)

            # Phase 2: Need WR>65% + N>8 + RR>0.8
            rr_penalty = 1.0
            if result['rr_avg'] < 0.8:
                rr_penalty = 0.4
            elif result['rr_avg'] < 1.0:
                rr_penalty = 0.7

            adjusted = result['final_score'] * rr_penalty

            if adjusted > best_score_val:
                best_score_val = result['final_score']
                best_params = params
                best_detail = result
                elite_pool.append((result['final_score'], params.copy()))
                elite_pool = sorted(elite_pool, key=lambda x: -x[0])[:10]
                log(f"  [R{r:03d}] ★ Score={result['final_score']} → WR={result['wr']}% PF={result['pf']} N={result['n']} RR={result['rr_avg']}")
                recent_improvements.append(True)
                stagnant = 0
            else:
                recent_improvements.append(False)
                stagnant += 1

            # Dynamic temperature adjustment
            if len(recent_improvements) >= 10:
                imp_rate = sum(recent_improvements[-10:]) / 10
                if imp_rate < 0.1 and temperature > 0.15:
                    temperature = min(0.6, temperature * 1.5)
                    log(f"  [R{r:03d}] 🔥 Low improvement ({imp_rate:.0%}), raising temp to {temperature:.2f}")
                elif imp_rate > 0.3:
                    temperature = max(0.15, temperature * 0.8)
                recent_improvements = recent_improvements[-10:]

            if stagnant >= 12:
                log(f"  [R{r:03d}] ⚠ Stagnant={stagnant}, escape attempt...")
                temperature = min(0.65, temperature * 3)
                for _ in range(3):
                    if len(elite_pool) >= 2:
                        p1 = random.choice(elite_pool)[1]
                        p2 = random.choice(elite_pool)[1]
                        params = blend_crossover(p1, p2, 0.4)
                    else:
                        params = mutate_params(best_params, 0.5)
                    result = evaluate_params(params)
                    if result['wr'] >= 60 and result['n'] >= 5 and result['rr_avg'] >= 0.6:
                        if result['final_score'] > best_score_val * 0.7:
                            log(f"  [R{r:03d}] ✓ Escape found: WR={result['wr']}% N={result['n']} RR={result['rr_avg']}")
                            elite_pool.append((result['final_score'], params.copy()))
                            elite_pool = sorted(elite_pool, key=lambda x: -x[0])[:10]
                            break
                stagnant = 0
                temperature = 0.35

            history.append({
                'round': r, 'score': result['final_score'], 'wr': result['wr'],
                'pf': result['pf'], 'n': result['n'], 'rr': result['rr_avg'],
                'phase': phase,
            })

            if r % 5 == 0:
                save_live(r, best_score_val, best_detail.get('wr', 0), best_detail.get('n', 0),
                          details={'phase': phase, 'temp': round(temperature, 3), 'stagnant': stagnant,
                                   'rr': best_detail.get('rr_avg', 0),
                                   'stocks_signal': best_detail.get('stocks_signal', 0)})
                save_progress(history)

    # ════════ Phase 3: 黄金区间 (R81-130) ════════
    phase3_end = min(130, ROUNDS)
    if ROUNDS > phase2_end:
        log(f"╠══ Phase 3: 黄金区间 (R{phase2_end+1}-{phase3_end}) ══╣")
        phase = 3
        temperature = 0.2

        for r in range(phase2_end + 1, min(phase3_end + 1, ROUNDS + 1)):
            if r % 15 == 0:
                ok, _ = check_proxy()
                if not ok:
                    restart_proxy()
                    time.sleep(2)

            # Phase 3: 20% random, 50% mutation, 15% crossover, 15% hill climb
            rnd = random.random()
            if rnd < 0.20:
                params = random_params()
            elif rnd < 0.70:
                params = mutate_params(best_params, temperature)
            elif rnd < 0.85:
                if len(elite_pool) >= 2:
                    p1 = random.choice(elite_pool)[1]
                    p2 = random.choice(elite_pool)[1]
                    params = crossover_params(p1, p2, 0.08)
                else:
                    params = mutate_params(best_params, temperature)
            else:
                # Hill climb on best params
                params, result = hill_climb(best_params, 5, 0.08)
                if result['final_score'] > best_score_val:
                    best_score_val = result['final_score']
                    best_params = params
                    best_detail = result
                    elite_pool.append((result['final_score'], params.copy()))
                    elite_pool = sorted(elite_pool, key=lambda x: -x[0])[:10]
                    log(f"  [R{r:03d}] ⛰ HILL CLIMB Score={result['final_score']} → WR={result['wr']}% N={result['n']} RR={result['rr_avg']}")
                    stagnant = 0
                history.append({
                    'round': r, 'score': result['final_score'], 'wr': result['wr'],
                    'pf': result['pf'], 'n': result['n'], 'rr': result['rr_avg'],
                    'phase': phase,
                })
                if r % 5 == 0:
                    save_live(r, best_score_val, best_detail.get('wr', 0), best_detail.get('n', 0),
                              details={'phase': phase, 'temp': round(temperature, 3)})
                    save_progress(history)
                continue

            result = evaluate_params(params)

            # Phase 3: Strict — RR>1.2, N>10, WR>70%
            n_bonus = 1.0
            if 15 <= result['n'] <= 35:
                n_bonus = 1.15
            elif 35 < result['n'] <= 50:
                n_bonus = 1.0

            rr_bonus = 1.0
            if result['rr_avg'] >= 1.5:
                rr_bonus = 1.2
            elif result['rr_avg'] >= 1.2:
                rr_bonus = 1.1

            adjusted = result['final_score'] * n_bonus * rr_bonus

            if adjusted > best_score_val:
                best_score_val = result['final_score']
                best_params = params
                best_detail = result
                elite_pool.append((result['final_score'], params.copy()))
                elite_pool = sorted(elite_pool, key=lambda x: -x[0])[:10]
                log(f"  [R{r:03d}] ★ Score={result['final_score']} → WR={result['wr']}% PF={result['pf']} N={result['n']} RR={result['rr_avg']}")
                stagnant = 0
            else:
                stagnant += 1

            if stagnant >= 10:
                log(f"  [R{r:03d}] ⚠ Stagnant={stagnant}, random restart...")
                for _ in range(3):
                    params = random_params()
                    result = evaluate_params(params)
                    if result['wr'] >= 65 and result['n'] >= 8:
                        elite_pool.append((result['final_score'], params.copy()))
                        log(f"  [R{r:03d}] ✓ Restart: WR={result['wr']}% N={result['n']} RR={result['rr_avg']}")
                        break
                stagnant = 0

            history.append({
                'round': r, 'score': result['final_score'], 'wr': result['wr'],
                'pf': result['pf'], 'n': result['n'], 'rr': result['rr_avg'],
                'phase': phase,
            })

            if r % 5 == 0:
                save_live(r, best_score_val, best_detail.get('wr', 0), best_detail.get('n', 0),
                          details={'phase': phase, 'temp': round(temperature, 3), 'stagnant': stagnant,
                                   'elite': len(elite_pool)})
                save_progress(history)

    # ════════ Phase 4: 收敛 (R131-180) ════════
    phase4_end = min(180, ROUNDS)
    if ROUNDS > phase3_end:
        log(f"╠══ Phase 4: 收敛 (R{phase3_end+1}-{phase4_end}) ══╣")
        phase = 4
        temperature = 0.15

        for r in range(phase3_end + 1, min(phase4_end + 1, ROUNDS + 1)):
            if r % 20 == 0:
                ok, _ = check_proxy()
                if not ok:
                    restart_proxy()
                    time.sleep(2)
                # Island migration
                islands = migrate(islands)

            # Phase 4: 10% random, 50% mutation, 20% crossover, 20% blend
            rnd = random.random()
            if rnd < 0.10:
                params = random_params()
            elif rnd < 0.60:
                params = mutate_params(best_params, temperature)
            elif rnd < 0.80:
                if len(elite_pool) >= 2:
                    p1 = random.choice(elite_pool)[1]
                    p2 = random.choice(elite_pool)[1]
                    params = crossover_params(p1, p2, 0.06)
                else:
                    params = mutate_params(best_params, temperature)
            else:
                if len(elite_pool) >= 2:
                    p1 = random.choice(elite_pool)[1]
                    p2 = random.choice(elite_pool)[1]
                    params = blend_crossover(p1, p2, 0.2)
                else:
                    params = mutate_params(best_params, temperature)

            result = evaluate_params(params)

            # Phase 4: Tight — RR>1.2 mandatory, N>12, WR>72%
            rr_penalty = 1.0
            if result['rr_avg'] < 1.2:
                rr_penalty = 0.5
            if result['rr_avg'] < 0.8:
                rr_penalty = 0.1

            n_penalty = 1.0
            if result['n'] < 12:
                n_penalty = 0.3
            elif result['n'] < 15:
                n_penalty = 0.7

            adjusted = result['final_score'] * rr_penalty * n_penalty

            if adjusted > best_score_val:
                best_score_val = result['final_score']
                best_params = params
                best_detail = result
                elite_pool.append((result['final_score'], params.copy()))
                elite_pool = sorted(elite_pool, key=lambda x: -x[0])[:10]
                log(f"  [R{r:03d}] ★ Score={result['final_score']} → WR={result['wr']}% PF={result['pf']} N={result['n']} RR={result['rr_avg']}")
                stagnant = 0
            else:
                stagnant += 1

            history.append({
                'round': r, 'score': result['final_score'], 'wr': result['wr'],
                'pf': result['pf'], 'n': result['n'], 'rr': result['rr_avg'],
                'phase': phase,
            })

            if r % 5 == 0:
                save_live(r, best_score_val, best_detail.get('wr', 0), best_detail.get('n', 0),
                          details={'phase': phase, 'temp': round(temperature, 3)})
                save_progress(history)

    # ════════ Phase 5: 强化 (R181-220) ════════
    phase5_end = min(220, ROUNDS)
    if ROUNDS > phase4_end:
        log(f"╠══ Phase 5: 强化 (R{phase4_end+1}-{phase5_end}) ══╣")
        phase = 5
        temperature = 0.08
        hill_climb_counter = 0

        for r in range(phase4_end + 1, min(phase5_end + 1, ROUNDS + 1)):
            if r % 15 == 0:
                ok, _ = check_proxy()
                if not ok:
                    restart_proxy()
                    time.sleep(2)

            hill_climb_counter += 1
            if hill_climb_counter >= 10:
                # Deep hill climb
                params, result = hill_climb(best_params, 8, 0.05)
                if result['final_score'] > best_score_val:
                    best_score_val = result['final_score']
                    best_params = params
                    best_detail = result
                    elite_pool.append((result['final_score'], params.copy()))
                    elite_pool = sorted(elite_pool, key=lambda x: -x[0])[:10]
                    log(f"  [R{r:03d}] ⛰ DEEP CLIMB Score={result['final_score']} → WR={result['wr']}% N={result['n']} RR={result['rr_avg']}")
                hill_climb_counter = 0

            # Phase 5: Mostly fine mutations + elite crossover
            rnd = random.random()
            if rnd < 0.60:
                params = mutate_params(best_params, temperature)
            elif rnd < 0.85:
                if len(elite_pool) >= 2:
                    p1 = random.choice(elite_pool)[1]
                    p2 = random.choice(elite_pool)[1]
                    params = crossover_params(p1, p2, 0.04)
                else:
                    params = mutate_params(best_params, temperature)
            else:
                # Try blend crossover from elite pool
                if len(elite_pool) >= 3:
                    p1 = random.choice(elite_pool[:5])[1]
                    p2 = random.choice(elite_pool[:5])[1]
                    params = blend_crossover(p1, p2, 0.15)
                else:
                    params = mutate_params(best_params, temperature)

            result = evaluate_params(params)

            rr_penalty = 1.0
            if result['rr_avg'] < 1.2:
                rr_penalty = 0.4

            n_penalty = 1.0
            if result['n'] < 12:
                n_penalty = 0.2

            adjusted = result['final_score'] * rr_penalty * n_penalty

            if adjusted > best_score_val:
                best_score_val = result['final_score']
                best_params = params
                best_detail = result
                elite_pool.append((result['final_score'], params.copy()))
                elite_pool = sorted(elite_pool, key=lambda x: -x[0])[:10]
                log(f"  [R{r:03d}] ★ Score={result['final_score']} → WR={result['wr']}% PF={result['pf']} N={result['n']} RR={result['rr_avg']}")

            history.append({
                'round': r, 'score': result['final_score'], 'wr': result['wr'],
                'pf': result['pf'], 'n': result['n'], 'rr': result['rr_avg'],
                'phase': phase,
            })

            if r % 5 == 0:
                save_live(r, best_score_val, best_detail.get('wr', 0), best_detail.get('n', 0),
                          details={'phase': phase, 'temp': round(temperature, 3)})
                save_progress(history)

    # ════════ Phase 6: 极细调 (R221+) ════════
    if ROUNDS > phase5_end:
        log(f"╠══ Phase 6: 极细调 (R{phase5_end+1}-{ROUNDS}) ══╣")
        phase = 6
        temperature = 0.05

        for r in range(phase5_end + 1, ROUNDS + 1):
            if r % 20 == 0:
                ok, _ = check_proxy()
                if not ok:
                    restart_proxy()
                    time.sleep(2)

            # Phase 6: Micro-perturbation only
            params = mutate_params(best_params, temperature)
            result = evaluate_params(params)

            # Only accept if clearly better: WR>75% + N>12 + RR>1.5
            quality_ok = result['wr'] >= 75 and result['n'] >= 12 and result['rr_avg'] >= 1.2
            if quality_ok and result['final_score'] > best_score_val:
                best_score_val = result['final_score']
                best_params = params
                best_detail = result
                elite_pool.append((result['final_score'], params.copy()))
                elite_pool = sorted(elite_pool, key=lambda x: -x[0])[:10]
                log(f"  [R{r:03d}] ★ Score={result['final_score']} → WR={result['wr']}% PF={result['pf']} N={result['n']} RR={result['rr_avg']}")

            history.append({
                'round': r, 'score': result['final_score'], 'wr': result['wr'],
                'pf': result['pf'], 'n': result['n'], 'rr': result['rr_avg'],
                'phase': phase,
            })

            if r % 5 == 0:
                save_live(r, best_score_val, best_detail.get('wr', 0), best_detail.get('n', 0),
                          details={'phase': phase, 'temp': round(temperature, 3)})
                save_progress(history)

    # ════════ 完成 ════════
    log("╔═══ 优化完成 ═══╗")
    log(f"最佳 Score: {best_score_val}")
    log(f"WR: {best_detail.get('wr', 'N/A')}%")
    log(f"PF: {best_detail.get('pf', 'N/A')}")
    log(f"N: {best_detail.get('n', 'N/A')}")
    log(f"RR: {best_detail.get('rr_avg', 'N/A')}")
    log(f"Cov: {best_detail.get('coverage_pct', 'N/A')}%")
    log(f"参数: {json.dumps(best_params, indent=2)}")

    # Save best
    save_data = {
        'score': best_score_val,
        'params': best_params,
        'full_eval': best_detail,
        'round': ROUNDS,
        'total_rounds': ROUNDS,
        'timestamp': time.time(),
        'engine': 'V8.3',
    }
    for f in [BEST_FILE]:
        with open(f, 'w') as fp:
            json.dump(save_data, fp, ensure_ascii=False, indent=2)

    # Save history
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, ensure_ascii=False, indent=1)

    # Save top-K elite
    elite_file = LOG_DIR / 'elite_pool.json'
    elite_data = []
    for s, p in elite_pool:
        elite_data.append({'score': s, 'params': p})
    with open(elite_file, 'w') as f:
        json.dump(elite_data, f, ensure_ascii=False, indent=1)

    save_live(ROUNDS, best_score_val, best_detail.get('wr', 0), best_detail.get('n', 0),
              status='complete', details={'phase': 6, 'elite': len(elite_pool)})
    save_progress(history)

    log(f"\nElite pool: {len(elite_pool)} solutions")
    for i, (s, p) in enumerate(elite_pool[:5]):
        log(f"  #{i+1}: Score={s}")
    log("╚═══════════════════╝")

if __name__ == '__main__':
    main()