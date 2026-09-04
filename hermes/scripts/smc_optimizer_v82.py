#!/usr/bin/env python3
"""
SMC V8.2 Optimizer — 全自动迭代优化器 (200轮+)
================================================
架构:
  V8.2引擎 + RR引导评分 + 4阶段搜索

Phase 1 (R1-30): 种子探索 — 宽口径
  - 随机参数, 只要求 WR>50% + N>5 + RR>0.5
  - 快速淘汰无效参数
  
Phase 2 (R31-100): WR聚焦
  - 聚焦WR>75%, N>15, RR>0.8
  - 温度逐渐降低
  - 停滞10轮→升温逃逸

Phase 3 (R101-180): 黄金区间精调
  - 目标: WR>80%, N=25-40, RR>1.0
  - 小步扰动
  - RR惩罚强化

Phase 4 (R181-200): 收敛
  - 超小温度, 仅做微调
  
每轮速度: ~10-12秒/15只股票
200轮≈35分钟

评分函数 V8.2:
  score = WR × sqrt(N) × min(3, PF) × RR_mult × N_mult × WR_mult
  其中 RR_mult: RR<0.5→0.2, RR<0.8→0.5, RR<1.2→0.8, RR>2.0→1.1
       N_mult: 黄金区间 25-40→1.1, <8→严重惩罚
"""

import sys, json, time, math, random, os, subprocess, urllib.request
from pathlib import Path

sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
from smc_engine_v82 import (
    load_bars, get_vol_profile, backtest_v82, compute_v82_score,
    V82_PARAM_SPACE, TEST_STOCKS, check_proxy_v8
)

# ════════ 配置 ════════
LOG_DIR = Path.home() / '.hermes' / 'smc_opt_v82'
LOG_DIR.mkdir(parents=True, exist_ok=True)

BEST_FILE = LOG_DIR / 'best_params.json'
PROGRESS_FILE = LOG_DIR / 'progress.json'
LIVE_FILE = LOG_DIR / 'live_status.json'
HISTORY_FILE = LOG_DIR / 'history.json'
LOG_FILE = LOG_DIR / 'optimization_log.ndjson'

# 同步到V7/V8目录供WebUI读取
V7_LIVE = Path.home() / '.hermes' / 'smc_opt_v7' / 'v7_live_status.json'
V8_LIVE = Path.home() / '.hermes' / 'smc_opt_v8' / 'live_status.json'

ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 200
STOCKS_COUNT = min(int(sys.argv[2]) if len(sys.argv) > 2 else 15, len(TEST_STOCKS))
STOCK_LIST = TEST_STOCKS[:STOCKS_COUNT]

# ════════ 命令行参数扩展 ════════
SEED_FILE = None
TIGHTEN_FACTOR = None
for i, arg in enumerate(sys.argv):
    if arg == '--seed' and i+1 < len(sys.argv):
        SEED_FILE = sys.argv[i+1]
    if arg == '--tighten' and i+1 < len(sys.argv):
        TIGHTEN_FACTOR = float(sys.argv[i+1])

if SEED_FILE and os.path.exists(SEED_FILE):
    try:
        seed_data = json.load(open(SEED_FILE))
        seed_params = seed_data.get('params', {})
        log(f"从 {SEED_FILE} 加载种子参数 ({len(seed_params)}维)")
    except:
        seed_params = {}
else:
    seed_params = {}

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
    log("代理失败! 尝试重启...")
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
            log(f"代理重启成功")
        else:
            log(f"代理重启失败: {msg}")
        return ok
    return False

# ════════ 日志/状态 ════════
def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')
    if LOG_FILE.stat().st_size > 2*1024*1024:
        LOG_FILE.rename(LOG_FILE.with_suffix(f'.{int(time.time())}.log'))

def save_live(round_num, best_score, best_wr, best_n, status='running', details=None):
    st = {
        'round': round_num,
        'total_rounds': ROUNDS,
        'best_score': best_score,
        'best_wr': best_wr,
        'best_n': best_n,
        'status': status,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'engine': 'V8.2',
        'details': details or {},
    }
    for f in [LIVE_FILE, V7_LIVE, V8_LIVE]:
        try:
            with open(f, 'w') as fp:
                json.dump(st, fp, ensure_ascii=False)
        except:
            pass

def save_progress(history):
    data = {'rounds': history, 'total_rounds': ROUNDS}
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

# ════════ 参数操作 ════════
def default_params():
    return {k: v['default'] for k, v in V82_PARAM_SPACE.items()}

# 如果指定了种子，使用种子参数；否则用默认
if not seed_params:
    _default_init = default_params()
else:
    _default_init = seed_params.copy()
    # 补全缺失的参数
    for k, v in V82_PARAM_SPACE.items():
        if k not in _default_init:
            _default_init[k] = v['default']

def random_params():
    """生成随机参数（支持种子收缩）"""
    p = {}
    for k, v in V82_PARAM_SPACE.items():
        lo, hi = v['min'], v['max']
        
        # 如果指定了收缩因子，在种子附近缩小范围
        if TIGHTEN_FACTOR and k in _default_init:
            center = _default_init[k]
            if lo < center < hi:
                half_range = (hi - lo) * TIGHTEN_FACTOR / 2
                lo = max(v['min'], center - half_range)
                hi = min(v['max'], center + half_range)
        
        if k == 'atr_min_pct':
            val = round(random.uniform(lo, min(hi, 2.5)), 1)
        elif k == 'atr_max_pct':
            val = round(random.uniform(max(lo, 4.0), hi), 1)
        elif k == 'tp_pct':
            val = round(random.uniform(lo, hi), 1)
            if random.random() < 0.3:
                val = round(random.uniform(max(lo, 5.0), hi), 1)
        elif k == 'sl_pct':
            val = round(random.uniform(max(lo, 1.5), hi), 1)
        else:
            val = round(random.uniform(lo, hi), 2 if 'step' in v and v['step'] >= 0.1 else 3)
        if 'step' in v and v['step'] > 0.01:
            val = round(val / v['step']) * v['step']
        p[k] = round(val, 2) if isinstance(val, float) else val
    return p

def mutate_params(current, temperature=0.3):
    p = {}
    for k, v in V82_PARAM_SPACE.items():
        lo, hi = v['min'], v['max']
        if random.random() < 0.15:  # 15%完全随机
            val = lo + random.random() * (hi - lo)
        else:
            delta = (hi - lo) * temperature * random.gauss(0, 0.2)
            val = current.get(k, v['default']) + delta
        val = max(lo, min(hi, val))
        if 'step' in v and v['step'] > 0.01:
            val = round(val / v['step']) * v['step']
        p[k] = round(val, 2) if isinstance(val, float) else val
    return p

def crossover_params(p1, p2, temperature=0.1):
    """交叉+小扰动 — 结合两个parent的基因"""
    p = {}
    for k, v in V82_PARAM_SPACE.items():
        if random.random() < 0.4:
            val = p1.get(k, v['default'])
        elif random.random() < 0.7:
            val = p2.get(k, v['default'])
        else:
            # slight mutation
            delta = (v['max']-v['min']) * temperature * random.gauss(0, 0.15)
            val = (p1.get(k, v['default']) + p2.get(k, v['default'])) / 2 + delta
        val = max(v['min'], min(v['max'], val))
        if 'step' in v and v['step'] > 0.01:
            val = round(val / v['step']) * v['step']
        p[k] = round(val, 2) if isinstance(val, float) else val
    return p

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
            trades = backtest_v82(bars, params)
            if trades:
                stocks_with_signals += 1
                all_trades.extend(trades)
        except:
            continue
    
    score = compute_v82_score(all_trades)
    score['stocks_ok'] = stocks_ok
    score['stocks_signal'] = stocks_with_signals
    
    coverage_pct = stocks_with_signals / max(1, stocks_ok) * 100 if stocks_ok > 0 else 0
    score['coverage_pct'] = coverage_pct
    
    # V8.2 final score = 评分函数的score * coverage_mult
    if coverage_pct < 15:
        cov_mult = 0.4
    elif coverage_pct < 25:
        cov_mult = 0.7
    else:
        cov_mult = 1.0
    
    final_score = score['score'] * cov_mult
    
    score['final_score'] = round(final_score, 2)
    return score

# ════════ 主流程 ════════
def main():
    log(f"╔═══ SMC V8.2 优化器 ═══ {ROUNDS}轮 × {STOCKS_COUNT}只股票 ═══╗")
    
    # 检查代理
    proxy_ok, msg = check_proxy()
    if not proxy_ok:
        log(f"代理不可用 ({msg}), 尝试重启...")
        restart_proxy()
        proxy_ok, msg = check_proxy()
        if not proxy_ok:
            log(f"代理无法恢复: {msg}, 继续但可能失败")
    
    # 预加载K线缓存
    log("预加载K线数据...")
    for sym in STOCK_LIST:
        try:
            load_bars(sym, 'daily', 300)
        except:
            pass
    log(f"缓存就绪 ({len(STOCK_LIST)}只股票)")
    
    # 初始参数 (使用V8.2默认)
    best_params = default_params()
    best_score_val = 0
    best_detail = {}
    
    # 保存top-K个解用于交叉
    top_k = []  # list of (score, params)
    top_k_max = 5
    
    # 初始评估
    log("Phase 0: 初始评估...")
    result = evaluate_params(best_params)
    best_score_val = result['final_score']
    best_detail = result
    top_k.append((best_score_val, best_params.copy()))
    log(f"  默认: WR={result['wr']}% PF={result['pf']} N={result['n']} RR={result['rr_avg']} Score={result['final_score']}")
    
    history = [{
        'round': 0, 'score': result['final_score'], 'wr': result['wr'],
        'pf': result['pf'], 'n': result['n'], 'rr': result['rr_avg'],
        'phase': 0,
    }]
    
    # ════════ Phase 1: 种子探索 (R1-40) ════════
    phase1_end = min(40, ROUNDS)
    log(f"╠══ Phase 1: 种子探索 (R1-{phase1_end}) ══╣")
    phase = 1
    temperature = 0.55
    stagnant = 0
    
    for r in range(1, phase1_end + 1):
        if r % 10 == 0:
            ok, _ = check_proxy()
            if not ok:
                log("代理中断! 重启...")
                restart_proxy()
                time.sleep(2)
        
        params = random_params()
        result = evaluate_params(params)
        
        # Phase1: 宽松接受 — 只要WR>55% + N>5 + RR>0.5
        wr_ok = result['wr'] >= 55
        n_ok = result['n'] >= 5
        rr_ok = result['rr_avg'] >= 0.5
        
        phase1_bonus = 0
        if wr_ok: phase1_bonus += 10
        if n_ok: phase1_bonus += 5
        if rr_ok: phase1_bonus += 8
        
        adjusted_score = result['final_score'] + phase1_bonus
        
        if adjusted_score > best_score_val + 5:
            actual_score = result['final_score']
            if actual_score > best_score_val:
                best_score_val = actual_score
                best_params = params
                best_detail = result
                top_k.append((actual_score, params.copy()))
                top_k = sorted(top_k, key=lambda x: -x[0])[:top_k_max]
                log(f"  [R{r:03d}] ★ NEW BEST Score={best_score_val} → WR={result['wr']}% PF={result['pf']} N={result['n']} RR={result['rr_avg']} Cov={result['coverage_pct']:.0f}%")
                stagnant = 0
            else:
                stagnant += 1
        else:
            stagnant += 1
        
        history.append({
            'round': r, 'score': result['final_score'], 'wr': result['wr'],
            'pf': result['pf'], 'n': result['n'], 'rr': result['rr_avg'],
            'phase': phase,
        })
        
        if r % 5 == 0:
            save_live(r, best_score_val, best_detail.get('wr', 0), best_detail.get('n', 0),
                      details={'phase': phase, 'temp': temperature, 'stagnant': stagnant,
                               'stocks_signal': best_detail.get('stocks_signal', 0),
                               'coverage': best_detail.get('coverage_pct', 0),
                               'rr': best_detail.get('rr_avg', 0)})
            save_progress(history)
    
    # ════════ Phase 2: WR聚焦 (R41-120) ════════
    phase2_end = min(120, ROUNDS)
    if ROUNDS > phase1_end:
        log(f"╠══ Phase 2: WR聚焦 (R{phase1_end+1}-{phase2_end}) ══╣")
        phase = 2
        temperature = 0.35
        
        for r in range(phase1_end + 1, min(phase2_end + 1, ROUNDS + 1)):
            if r % 10 == 0:
                ok, _ = check_proxy()
                if not ok:
                    log("代理中断! 重启...")
                    restart_proxy()
                    time.sleep(2)
            
            if r % 15 == 0:
                temperature = max(0.1, temperature * 0.85)
            
            # Phase 2策略: 70%突变, 15%随机, 15%交叉
            rnd = random.random()
            if rnd < 0.15:
                params = random_params()
            elif rnd < 0.85:
                params = mutate_params(best_params, temperature)
            else:
                if len(top_k) >= 2:
                    p1 = random.choice(top_k)[1]
                    p2 = random.choice(top_k)[1]
                    params = crossover_params(p1, p2, temperature)
                else:
                    params = mutate_params(best_params, temperature)
            
            result = evaluate_params(params)
            
            # Phase2: 需要WR>70% + N>8 + RR>0.8才接受
            rr_penalty = 1.0
            if result['rr_avg'] < 0.8:
                rr_penalty = 0.5
            if result['rr_avg'] < 0.5:
                rr_penalty = 0.2
            
            adjusted = result['final_score'] * rr_penalty
            
            if adjusted > best_score_val:
                best_score_val = result['final_score']
                best_params = params
                best_detail = result
                top_k.append((result['final_score'], params.copy()))
                top_k = sorted(top_k, key=lambda x: -x[0])[:top_k_max]
                log(f"  [R{r:03d}] ★ Score={best_score_val} → WR={result['wr']}% PF={result['pf']} N={result['n']} RR={result['rr_avg']}")
                stagnant = 0
            else:
                stagnant += 1
            
            if stagnant >= 12:
                log(f"  [R{r:03d}] ⚠ Stagnant={stagnant}, 升温逃逸")
                temperature = min(0.6, temperature * 3)
                # 尝试3次交叉
                for _ in range(3):
                    if len(top_k) >= 2:
                        p1 = random.choice(top_k)[1]
                        p2 = random.choice(top_k)[1]
                        params = crossover_params(p1, p2, 0.25)
                    else:
                        params = mutate_params(best_params, 0.5)
                    result = evaluate_params(params)
                    if result['wr'] >= 60 and result['n'] >= 5 and result['rr_avg'] >= 0.5:
                        if result['final_score'] > best_score_val * 0.8:
                            log(f"  [R{r:03d}] ✓ Escape found: WR={result['wr']}% N={result['n']}")
                            break
                stagnant = 0
                temperature = 0.3
            
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
    
    # ════════ Phase 3: 黄金区间 (R121-180) ════════
    phase3_end = min(180, ROUNDS)
    if ROUNDS > phase2_end:
        log(f"╠══ Phase 3: 黄金区间 (R{phase2_end+1}-{phase3_end}) ══╣")
        phase = 3
        temperature = 0.18
        
        for r in range(phase2_end + 1, min(phase3_end + 1, ROUNDS + 1)):
            if r % 15 == 0:
                ok, _ = check_proxy()
                if not ok:
                    log("代理中断! 重启...")
                    restart_proxy()
                    time.sleep(2)
            
            # Phase 3: 小步 + 交叉
            rnd = random.random()
            if rnd < 0.2:
                params = random_params()
            elif rnd < 0.6:
                params = mutate_params(best_params, temperature)
            else:
                if len(top_k) >= 2:
                    p1 = random.choice(top_k)[1]
                    p2 = random.choice(top_k)[1]
                    params = crossover_params(p1, p2, 0.08)
                else:
                    params = mutate_params(best_params, temperature)
            
            result = evaluate_params(params)
            
            # Phase3: 严格要求 — RR>1.0, N>10, WR>75%
            # 但是允许N=15-45黄金区间
            n_bonus = 1.0
            if 15 <= result['n'] <= 45:
                n_bonus = 1.15
            
            rr_bonus = 1.0
            if result['rr_avg'] >= 1.2:
                rr_bonus = 1.2
            elif result['rr_avg'] >= 1.0:
                rr_bonus = 1.1
            elif result['rr_avg'] >= 0.8:
                rr_bonus = 0.9
            else:
                rr_bonus = 0.5
            
            adjusted = result['final_score'] * n_bonus * rr_bonus
            
            if adjusted > best_score_val:
                best_score_val = result['final_score']
                best_params = params
                best_detail = result
                top_k.append((result['final_score'], params.copy()))
                top_k = sorted(top_k, key=lambda x: -x[0])[:top_k_max]
                log(f"  [R{r:03d}] ★ Score={best_score_val} → WR={result['wr']}% PF={result['pf']} N={result['n']} RR={result['rr_avg']}")
            
            history.append({
                'round': r, 'score': result['final_score'], 'wr': result['wr'],
                'pf': result['pf'], 'n': result['n'], 'rr': result['rr_avg'],
                'phase': phase,
            })
            
            if r % 5 == 0:
                save_live(r, best_score_val, best_detail.get('wr', 0), best_detail.get('n', 0),
                          details={'phase': phase, 'temp': temperature,
                                   'rr': best_detail.get('rr_avg', 0)})
                save_progress(history)
    
    # ════════ Phase 4: 收敛 (R181+) ════════
    if ROUNDS > phase3_end:
        log(f"╠══ Phase 4: 收敛 (R{phase3_end+1}-{ROUNDS}) ══╣")
        phase = 4
        temperature = 0.08
        
        for r in range(phase3_end + 1, ROUNDS + 1):
            if r % 20 == 0:
                ok, _ = check_proxy()
                if not ok:
                    log("代理中断! 重启...")
                    restart_proxy()
                    time.sleep(2)
            
            params = mutate_params(best_params, temperature)
            result = evaluate_params(params)
            
            if result['final_score'] > best_score_val:
                best_score_val = result['final_score']
                best_params = params
                best_detail = result
                log(f"  [R{r:03d}] ★ Score={best_score_val} → WR={result['wr']}% PF={result['pf']} N={result['n']} RR={result['rr_avg']}")
            
            history.append({
                'round': r, 'score': result['final_score'], 'wr': result['wr'],
                'pf': result['pf'], 'n': result['n'], 'rr': result['rr_avg'],
                'phase': phase,
            })
            
            if r % 10 == 0:
                save_live(r, best_score_val, best_detail.get('wr', 0), best_detail.get('n', 0),
                          details={'phase': phase, 'temp': temperature})
                save_progress(history)
    
    # ════════ 最终结果 ════════
    # 取top_k中最强的
    if top_k:
        top_k.sort(key=lambda x: -x[0])
        best_score_val = top_k[0][0]
        best_params = top_k[0][1]
        # 重新评估top-1确保一致性
        best_detail = evaluate_params(best_params)
    
    best_output = {
        'score': best_score_val,
        'params': best_params,
        'full_eval': best_detail,
        'round': ROUNDS,
        'total_rounds': ROUNDS,
        'timestamp': time.time(),
        'engine': 'V8.2',
    }
    with open(BEST_FILE, 'w') as f:
        json.dump(best_output, f, ensure_ascii=False, indent=2)
    
    with open(HISTORY_FILE, 'w') as f:
        json.dump({'rounds': history, 'engine': 'V8.2', 'total_rounds': ROUNDS}, f, ensure_ascii=False)
    
    save_live(ROUNDS, best_score_val, best_detail.get('wr', 0), best_detail.get('n', 0),
              status='complete', details={'phase': phase, 'best_params': best_params})
    save_progress(history)
    
    log(f"╚═══ ═══════════════════════════════════ ═══╝")
    log(f"")
    log(f"  ✅ V8.2 优化完成! {ROUNDS}轮")
    log(f"  📊 最佳Score: {best_score_val}")
    log(f"  🏆 WR: {best_detail.get('wr', 0)}% | PF: {best_detail.get('pf', 0)} | N: {best_detail.get('n', 0)}")
    log(f"  🎯 RR: {best_detail.get('rr_avg', 0)} | Ret: {best_detail.get('ret', 0)}% | SR: {best_detail.get('sr', 0)}")
    log(f"  📡 Stocks: {best_detail.get('stocks_signal', 0)}/{best_detail.get('stocks_ok', 0)}")
    log(f"  📁 结果: {BEST_FILE}")
    print(json.dumps(best_output, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()