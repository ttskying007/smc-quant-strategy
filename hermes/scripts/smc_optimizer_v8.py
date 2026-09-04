#!/usr/bin/env python3
"""
SMC V8 Optimizer — 全自动迭代优化器 (200轮+)
================================================
架构:
  三阶段迭代 + 自适应参数扰动 + WR目标引导

Phase 1 (R1-50): 随机探索 + 网格覆盖
  - 每次完全随机12维参数
  - 15只股票快速测试
  - 保底: 找一组n>=5且WR>=50%的参数

Phase 2 (R51-150): 聚焦WR
  - 在最佳参数附近扰动 (温度逐渐降低)
  - WR目标80%+, 惩罚WR<60%
  - 如果连续10轮无进步→升温逃逸

Phase 3 (R151-200+): 精调
  - 小步扰动
  - 平衡WR+PF+RR

输出:
  - best_params.json (最佳参数)
  - progress.json (每轮记录供WebUI)
  - live_status.json (实时状态)

每轮速度: ~12秒/15只股票
200轮≈40分钟
"""

import sys, json, time, math, random, os
from pathlib import Path

sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
from smc_engine_v8 import (
    load_bars, get_vol_profile, backtest_v8, compute_v8_score,
    V8_PARAM_SPACE, TEST_STOCKS
)

# ════════ 配置 ════════
LOG_DIR = Path.home() / '.hermes' / 'smc_opt_v8'
LOG_DIR.mkdir(parents=True, exist_ok=True)

BEST_FILE = LOG_DIR / 'best_params.json'
PROGRESS_FILE = LOG_DIR / 'progress.json'
LIVE_FILE = LOG_DIR / 'live_status.json'
HISTORY_FILE = LOG_DIR / 'history.json'
LOG_FILE = LOG_DIR / 'optimization_log.ndjson'

# 也写入V7目录供旧WebUI读取
V7_STATUS = Path.home() / '.hermes' / 'smc_opt_v7' / 'v7_live_status.json'
V7_PROGRESS = Path.home() / '.hermes' / 'smc_opt_v7' / 'v7_progress.json'
V7P_STATUS = Path.home() / '.hermes' / 'smc_opt_v7plus' / 'v7p_live_status.json'

ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 200
STOCKS_COUNT = min(int(sys.argv[2]) if len(sys.argv) > 2 else 15, len(TEST_STOCKS))
STOCK_LIST = TEST_STOCKS[:STOCKS_COUNT]

# ════════ 代理检查 ════════
import subprocess, urllib.request

def check_proxy():
    """检查代理状态"""
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
    """重启代理"""
    log("代理失败! 尝试重启...")
    # kill existing
    subprocess.run(['pkill', '-9', '-f', 'mihomo'], timeout=5, capture_output=True)
    time.sleep(2)
    # start
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
    # rotate if > 2MB
    if LOG_FILE.stat().st_size > 2*1024*1024:
        LOG_FILE.rename(LOG_FILE.with_suffix(f'.{int(time.time())}.log'))

def save_live(round_num, best_score, best_wr, best_n, status='running', details=None):
    """写入实时状态"""
    st = {
        'round': round_num,
        'total_rounds': ROUNDS,
        'best_score': best_score,
        'best_wr': best_wr,
        'best_n': best_n,
        'status': status,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'engine': 'V8',
        'details': details or {},
    }
    for f in [LIVE_FILE, V7_STATUS, V7P_STATUS]:
        try:
            with open(f, 'w') as fp:
                json.dump(st, fp, ensure_ascii=False)
        except:
            pass

def save_progress(history):
    """写入迭代历史"""
    data = {'rounds': history, 'total_rounds': ROUNDS}
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    # also write to V7 dirs
    for pf in [V7_PROGRESS]:
        try:
            with open(pf, 'w') as fp:
                json.dump({'rounds': history[-50:], 'engine': 'V8', 'total_rounds': ROUNDS}, fp)
        except:
            pass

# ════════ 参数操作 ════════
def default_params():
    return {k: v['default'] for k, v in V8_PARAM_SPACE.items()}

def random_params():
    """完全随机参数"""
    p = {}
    for k, v in V8_PARAM_SPACE.items():
        if k == 'atr_min_pct':
            val = round(random.uniform(0.5, 2.5), 1)
        elif k == 'atr_max_pct':
            val = round(random.uniform(4.0, 8.0), 1)
        elif k == 'tp_pct':
            # tp_pct 倾向大一点(RR高)
            val = round(random.uniform(v['min'], v['max']), 1)
            if random.random() < 0.3:
                val = round(random.uniform(5.0, v['max']), 1)
        else:
            val = round(random.uniform(v['min'], v['max']), 2 if 'step' in v and v['step'] >= 0.1 else 3)
        if 'step' in v and v['step'] > 0.01:
            val = round(val / v['step']) * v['step']
        p[k] = round(val, 2) if isinstance(val, float) else val
    return p

def mutate_params(current, temperature=0.3):
    """在当前位置附近扰动参数"""
    p = {}
    for k, v in V8_PARAM_SPACE.items():
        lo, hi = v['min'], v['max']
        if random.random() < 0.2:  # 20%完全随机
            val = lo + random.random() * (hi - lo)
        else:
            delta = (hi - lo) * temperature * random.gauss(0, 0.2)
            val = current.get(k, v['default']) + delta
        val = max(lo, min(hi, val))
        if 'step' in v and v['step'] > 0.01:
            val = round(val / v['step']) * v['step']
        p[k] = round(val, 2) if isinstance(val, float) else val
    return p

# ════════ 评估 ════════
def evaluate_params(params, stock_list=None):
    """评估一组参数在股票池上的表现"""
    if stock_list is None:
        stock_list = STOCK_LIST
    
    all_trades = []
    stocks_ok = 0
    stocks_with_signals = 0
    total_signals = {'fvg': 0, 'sweep': 0, 'ob': 0, 'bpr': 0}
    
    for sym in stock_list:
        try:
            bars = load_bars(sym, 'daily', 300)
            if not bars or len(bars) < 80:
                continue
            stocks_ok += 1
            trades = backtest_v8(bars, params)
            if trades:
                stocks_with_signals += 1
                all_trades.extend(trades)
                
                # Count signal sources
                for t in trades:
                    src = t.get('sources', [])
                    for s in src:
                        if s in total_signals:
                            total_signals[s] += 1
        except Exception as e:
            continue
    
    score = compute_v8_score(all_trades)
    score['stocks_ok'] = stocks_ok
    score['stocks_signal'] = stocks_with_signals
    score['total_signals'] = total_signals
    
    # V8 specific: coverage penalty
    # If too few stocks have signals, penalize
    coverage_pct = stocks_with_signals / max(1, stocks_ok) * 100 if stocks_ok > 0 else 0
    score['coverage_pct'] = coverage_pct
    
    # Final adaptive score: WR guided + coverage
    wr = score['wr']
    n = score['n']
    pf = score['pf']
    
    # Adaptive scoring V8.2 — 直接使用平衡分数
    # Formula: balance_score = WR * sqrt(N) * min(3, PF) * cov_mult
    # This naturally rewards: more trades + high WR + good PF
    # A result with WR=80%, N=16, PF=3 scores: 80×4×3=960
    # A result with WR=100%, N=10, PF=999 scores: 100×3.16×3=948
    # A result with WR=70%, N=25, PF=2.5 scores: 70×5×2.5=875
    # All three are close — balanced exploration
    
    if wr < 50:
        score_mult = 0.1  # severe penalty for low WR
    elif wr < 60:
        score_mult = 0.5
    elif wr < 70:
        score_mult = 1.0
    else:
        score_mult = 1.0  # no extra WR multiplier (already in formula)
    
    # PF capping to prevent 999 domination
    pf_capped = min(3.0, pf)
    
    # Coverage penalty
    if coverage_pct < 15:
        cov_mult = 0.3
    elif coverage_pct < 25:
        cov_mult = 0.6
    else:
        cov_mult = 1.0
    
    # Balance score! The key insight: WR * sqrt(N) * min PF
    balance_score = wr * math.sqrt(max(1, n)) * pf_capped * cov_mult * score_mult
    
    final_score = round(balance_score, 1)
    
    score['final_score'] = round(final_score, 2)
    return score

# ════════ 主流程 ════════
def main():
    log(f"╔══ SMC V8 优化器 ══ {ROUNDS}轮 × {STOCKS_COUNT}只股票 ══╗")
    
    # 检查代理
    proxy_ok, msg = check_proxy()
    if not proxy_ok:
        log(f"代理不可用 ({msg}), 尝试重启...")
        restart_proxy()
        proxy_ok, msg = check_proxy()
        if not proxy_ok:
            log(f"代理无法恢复: {msg}, 继续但可能失败")
    
    # 预加载所有K线缓存
    log("预加载K线数据...")
    for sym in STOCK_LIST:
        try:
            load_bars(sym, 'daily', 300)
        except:
            pass
    log(f"缓存就绪 ({len(STOCK_LIST)}只股票)")
    
    # 初始参数
    best_params = default_params()
    best_score_val = 0
    best_detail = {}
    
    # 先跑第一轮
    log("Phase 0: 初始评估...")
    result = evaluate_params(best_params)
    best_score_val = result['final_score']
    best_detail = result
    log(f"  默认: WR={result['wr']}% PF={result['pf']} N={result['n']} Score={result['final_score']}")
    
    history = [{
        'round': 0, 'score': result['final_score'], 'wr': result['wr'],
        'pf': result['pf'], 'n': result['n'], 'phase': 0,
    }]
    
    # ════════ Phase 1: 随机探索 ════════
    log(f"╠══ Phase 1: 随机探索 (R1-{min(50, ROUNDS)}) ══╣")
    phase = 1
    temperature = 0.5
    stagnant = 0
    phase2_start = min(51, ROUNDS)
    
    for r in range(1, phase2_start):
        # 每轮检查代理
        if r % 10 == 0:
            ok, _ = check_proxy()
            if not ok:
                log("代理中断! 尝试重启...")
                restart_proxy()
                time.sleep(2)
        
        params = random_params()
        result = evaluate_params(params)
        
        if result['final_score'] > best_score_val:
            best_score_val = result['final_score']
            best_params = params
            best_detail = result
            log(f"  [R{r:03d}] ★ NEW BEST Score={best_score_val} → WR={result['wr']}% PF={result['pf']} N={result['n']} Cov={result['coverage_pct']:.0f}%")
            stagnant = 0
        else:
            stagnant += 1
        
        history.append({
            'round': r, 'score': result['final_score'], 'wr': result['wr'],
            'pf': result['pf'], 'n': result['n'], 'phase': phase,
        })
        
        if r % 5 == 0:
            current_wr = best_detail.get('wr', 0)
            save_live(r, best_score_val, current_wr, best_detail.get('n', 0),
                      details={'phase': phase, 'temp': temperature, 'stagnant': stagnant,
                               'stocks_signal': best_detail.get('stocks_signal', 0),
                               'coverage': best_detail.get('coverage_pct', 0)})
            save_progress(history)
    
    # ════════ Phase 2: 聚焦WR ════════
    phase3_start = min(151, ROUNDS + 1)
    if ROUNDS > phase2_start:
        log(f"╠══ Phase 2: 聚焦WR (R{phase2_start}-{min(150, ROUNDS)}) ══╣")
        phase = 2
        temperature = 0.35
        
        for r in range(phase2_start, phase3_start):
            if r % 10 == 0:
                ok, _ = check_proxy()
                if not ok:
                    log("代理中断! 重启...")
                    restart_proxy()
                    time.sleep(2)
            
            # 在best附近扰动, 但每10轮降温
            if r % 10 == 0:
                temperature = max(0.08, temperature * 0.85)
            
            params = mutate_params(best_params, temperature)
            result = evaluate_params(params)
            
            # 接受条件: WR>80%优先
            wr_improved = result['wr'] >= 80 and (result['wr'] > best_detail.get('wr', 0) or 
                            (abs(result['wr'] - best_detail.get('wr', 0)) < 5 and 
                             result['final_score'] > best_score_val))
            
            if result['final_score'] > best_score_val or wr_improved:
                best_score_val = result['final_score']
                best_params = params
                best_detail = result
                log(f"  [R{r:03d}] ★ NEW BEST Score={best_score_val} → WR={result['wr']}% PF={result['pf']} N={result['n']} Cov={result['coverage_pct']:.0f}%")
                stagnant = 0
            else:
                stagnant += 1
            
            # 停滞10轮 → 升温逃逸
            if stagnant >= 10:
                log(f"  [R{r:03d}] ⚠ Stagnant={stagnant}, 升温逃逸 temp={min(0.6, temperature*3)}")
                temperature = min(0.6, temperature * 3)
                # 在远离当前best的地方采样
                params = mutate_params(best_params, temperature)
                # 但强制WR>60
                for _ in range(3):
                    result = evaluate_params(params)
                    if result['wr'] >= 60 and result['n'] >= 5:
                        if result['final_score'] > best_score_val:
                            best_score_val = result['final_score']
                            best_params = params
                            best_detail = result
                            log(f"  [R{r:03d}] ★★ Escape success! Score={best_score_val}")
                        break
                    params = mutate_params(best_params, temperature)
                stagnant = 0
                temperature = 0.3  # 恢复
            
            history.append({
                'round': r, 'score': result['final_score'], 'wr': result['wr'],
                'pf': result['pf'], 'n': result['n'], 'phase': phase,
            })
            
            if r % 5 == 0:
                current_wr = best_detail.get('wr', 0)
                save_live(r, best_score_val, current_wr, best_detail.get('n', 0),
                          details={'phase': phase, 'temp': round(temperature, 3), 'stagnant': stagnant,
                                   'stocks_signal': best_detail.get('stocks_signal', 0),
                                   'coverage': best_detail.get('coverage_pct', 0)})
                save_progress(history)
    
    # ════════ Phase 3: 精调 (如果需要) ════════
    if ROUNDS >= phase3_start:
        log(f"╠══ Phase 3: 精调 (R{phase3_start}-{ROUNDS}) ══╣")
        phase = 3
        temperature = 0.12
        
        for r in range(phase3_start, ROUNDS + 1):
            if r % 10 == 0:
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
                log(f"  [R{r:03d}] ★ NEW BEST Score={best_score_val} → WR={result['wr']}% PF={result['pf']} N={result['n']}")
            
            history.append({
                'round': r, 'score': result['final_score'], 'wr': result['wr'],
                'pf': result['pf'], 'n': result['n'], 'phase': phase,
            })
            
            if r % 5 == 0:
                save_live(r, best_score_val, best_detail.get('wr', 0), best_detail.get('n', 0),
                          details={'phase': phase, 'temp': temperature})
                save_progress(history)
    
    # ════════ 最终结果 ════════
    # 保存最佳参数
    best_output = {
        'score': best_score_val,
        'params': best_params,
        'full_eval': best_detail,
        'round': ROUNDS,
        'total_rounds': ROUNDS,
        'timestamp': time.time(),
        'engine': 'V8',
    }
    with open(BEST_FILE, 'w') as f:
        json.dump(best_output, f, ensure_ascii=False, indent=2)
    
    # 保存历史
    with open(HISTORY_FILE, 'w') as f:
        json.dump({'rounds': history, 'engine': 'V8', 'total_rounds': ROUNDS}, f, ensure_ascii=False)
    
    save_live(ROUNDS, best_score_val, best_detail.get('wr', 0), best_detail.get('n', 0),
              status='complete', details={'phase': phase, 'best_params': best_params})
    save_progress(history)
    
    log(f"╚══ ═══════════════════════════════════ ══╝")
    log(f"")
    log(f"  ✅ 优化完成! {ROUNDS}轮")
    log(f"  📊 最佳Score: {best_score_val}")
    log(f"  🏆 WR: {best_detail.get('wr', 0)}% | PF: {best_detail.get('pf', 0)} | N: {best_detail.get('n', 0)}")
    log(f"  📈 Ret: {best_detail.get('ret', 0)}% | SR: {best_detail.get('sr', 0)}")
    log(f"  📡 Stocks: {best_detail.get('stocks_signal', 0)}/{best_detail.get('stocks_ok', 0)} 有信号")
    log(f"  📁 结果: {BEST_FILE}")
    log(f"  📁 历史: {HISTORY_FILE}")
    log(f"  📁 状态: {LIVE_FILE}")

if __name__ == '__main__':
    main()