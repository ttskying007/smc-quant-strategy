#!/usr/bin/env python3
"""
SMC V5.4 全自动迭代优化器 (≥120轮)
======================================
架构:
  - 分层优化: 高波动(ATR≥2%)和低波动分别优化
  - 每轮: 测试15只股票 → 评分 → 参数微调
  - 参数搜索: 模拟退火 + 随机扰动 + 收敛重置

3个阶段:
  Phase 1 (1-40): 全局搜索
  Phase 2 (41-80): 局部精调
  Phase 3 (81-120): 验证+微调
"""

import sys, json, time, math, random, os
from pathlib import Path

sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
from smc_engine_v54 import load_bars, get_vol_profile, backtest_v54, compute_score
from smc_engine_v54 import get_adaptive_params

LOG_DIR = Path.home() / '.hermes' / 'smc_opt_v54'
LOG_DIR.mkdir(parents=True, exist_ok=True)
PROGRESS_FILE = LOG_DIR / 'optimizer_progress.json'
BEST_FILE = LOG_DIR / 'best_params.json'
LATEST_SCAN = LOG_DIR / 'latest_scan.json'

# ════════ 测试股票池 ════════

TEST_STOCKS = [
    '300231.SZ', '000858.SZ', '600519.SH', '002415.SZ', '300750.SZ',
    '601318.SH', '000333.SZ', '002594.SZ', '688981.SH', '600036.SH',
    '300059.SZ', '600030.SH', '002230.SZ', '300124.SZ', '600276.SH',
]

# ════════ 核心优化参数 ════════

# V5.4的优化参数集
OPT_PARAMS = {
    # FVG
    'fvg_min_width_high':   {'min':0.20, 'max':0.40, 'default':0.32},
    'fvg_min_width_med':    {'min':0.18, 'max':0.35, 'default':0.25},
    'fvg_min_width_low':    {'min':0.10, 'max':0.25, 'default':0.15},
    # Sweep
    'sweep_lookback_high':  {'min':12, 'max':25, 'default':18},
    'sweep_lookback_low':   {'min':8, 'max':18, 'default':12},
    'sweep_wick_high':      {'min':1.5, 'max':3.0, 'default':2.2},
    'sweep_wick_low':       {'min':1.2, 'max':2.5, 'default':1.8},
    # 结构
    'confirm_range':        {'min':1, 'max':4, 'default':2},
    'min_consecutive':      {'min':1, 'max':3, 'default':2},
    'min_signal_sources':   {'min':1, 'max':3, 'default':1},
    'max_trades':           {'min':3, 'max':10, 'default':6},
    # 门槛
    'min_score':            {'min':0.5, 'max':2.0, 'default':1.0},
    'trail_activation':     {'min':0.2, 'max':0.6, 'default':0.35},
}

# ════════ 自适应参数转V5.4引擎参数 ════════

def flat_to_engine(flat_params, atr_pct):
    """将平面参数转换为引擎接受的参数dict"""
    ap = get_adaptive_params(atr_pct)
    
    # 根据波动率层选择对应的fvg_min_width
    if atr_pct >= 3.0:
        ap['fvg_min_width'] = flat_params.get('fvg_min_width_high', 0.32)
        ap['sweep_lookback'] = flat_params.get('sweep_lookback_high', 18)
        ap['sweep_wick_ratio'] = flat_params.get('sweep_wick_high', 2.2)
    elif atr_pct >= 1.5:
        ap['fvg_min_width'] = flat_params.get('fvg_min_width_med', 0.25)
        ap['sweep_lookback'] = flat_params.get('sweep_lookback_med', 15) if 'sweep_lookback_med' in flat_params else 15
        ap['sweep_wick_ratio'] = flat_params.get('sweep_wick_med', 2.0) if 'sweep_wick_med' in flat_params else 2.0
    else:
        ap['fvg_min_width'] = flat_params.get('fvg_min_width_low', 0.15)
        ap['sweep_lookback'] = flat_params.get('sweep_lookback_low', 12)
        ap['sweep_wick_ratio'] = flat_params.get('sweep_wick_low', 1.8)
    
    for k in ['confirm_range', 'min_consecutive', 'min_signal_sources', 'max_trades', 'min_score', 'trail_activation']:
        if k in flat_params:
            ap[k] = flat_params[k]
    
    return ap


def default_flat_params():
    return {k: v['default'] for k, v in OPT_PARAMS.items()}

def randomize_flat_params(current=None, temperature=0.3):
    """随机扰动参数"""
    p = {}
    for k, v in OPT_PARAMS.items():
        if current and random.random() > 0.15:
            delta = (v['max'] - v['min']) * temperature * random.gauss(0, 0.2)
            val = current.get(k, v['default']) + delta
        else:
            val = v['min'] + random.random() * (v['max'] - v['min'])
        val = max(v['min'], min(v['max'], val))
        p[k] = round(val, 2) if isinstance(val, float) else int(val)
    return p


# ════════ 评估 ════════

def evaluate_params_flat(flat_params, stock_list=None, max_stocks=15):
    """评估一组参数在所有股票上的加权表现"""
    if stock_list is None:
        stock_list = TEST_STOCKS[:max_stocks]
    
    all_trades = []
    stocks_ok = 0
    stocks_signal = 0
    stock_scores = []
    
    for symbol in stock_list:
        try:
            bars = load_bars(symbol, 'daily', 300)
            if not bars or len(bars) < 60:
                continue
            stocks_ok += 1
            vol = get_vol_profile(bars)
            atr = vol['atr_pct']
            
            # 转换参数
            engine_params = flat_to_engine(flat_params, atr)
            
            trades = backtest_v54(bars, engine_params)
            if trades:
                stocks_signal += 1
                s = compute_score(trades)
                all_trades.extend(trades)
                stock_scores.append(s['score'])
        except Exception as e:
            continue
    
    if not all_trades:
        return {'score': 0, 'wr': 0, 'pf': 0, 'n': 0, 'n_wins': 0, 'n_losses': 0,
                'ret': 0, 'stocks_ok': stocks_ok, 'stocks_signal': 0}
    
    s = compute_score(all_trades)
    s['stocks_ok'] = stocks_ok
    s['stocks_signal'] = stocks_signal
    s['stocks_score_avg'] = round(sum(stock_scores)/len(stock_scores), 1) if stock_scores else 0
    s['stocks_score_list'] = stock_scores
    return s


# ════════ 优化循环 ════════

def run_optimization(n_rounds=120, n_start=0, resume=False):
    """运行全自动优化"""
    
    best_score = 0
    best_params = default_flat_params()
    best_full_s = None
    all_log = []
    start_round = 0
    
    if resume and PROGRESS_FILE.exists():
        try:
            p = json.load(open(PROGRESS_FILE))
            best_score = p.get('best_score', 0)
            best_params = p.get('best_params', best_params)
            all_log = p.get('log', [])
            start_round = p.get('current_round', 0) + 1
            print(f"[恢复] 从第{start_round}轮继续, 当前Best Score={best_score:.1f}")
        except:
            pass
    
    current_params = best_params.copy()
    temperature = 0.5
    no_improve = 0
    last_best_r = start_round
    
    print(f"=== V5.4 Optimizer | {n_rounds} rounds | {len(OPT_PARAMS)} dims ===")
    
    if not resume:
        # Baseline test
        bs = evaluate_params_flat(best_params, max_stocks=8)
        best_score = bs['score']
        all_log.append({'r': 0, 'score': bs['score'], 'wr': bs.get('wr',0), 'pf': bs.get('pf',0), 'n': bs.get('n',0)})
        print(f"[R000] Baseline: Score={bs['score']:.1f} WR={bs.get('wr',0):.1f}% PF={bs.get('pf',0):.2f} N={bs.get('n',0)}")
    
    for rnd in range(start_round, n_rounds):
        r = rnd + 1
        t0 = time.time()
        
        # 降温
        temperature = max(0.05, 0.5 * math.exp(-r / 30))
        
        # Phase切换
        if r == 41:
            temperature = 0.15
            print(f"[Phase 2] 开始局部精调")
        elif r == 81:
            temperature = 0.08
            print(f"[Phase 3] 开始验证+微调")
        
        # 自动扩大搜索
        if no_improve > 8 and r % 10 == 0:
            temperature = min(0.6, temperature * 3)
            no_improve = 0
            print(f"  [Reset] Temp→{temperature:.2f}")
        
        # 尝试5组随机参数
        best_trial = {'score': 0}
        for trial in range(5):
            trial_params = randomize_flat_params(current_params, temperature)
            s = evaluate_params_flat(trial_params, max_stocks=10)
            if s['score'] > best_trial['score']:
                best_trial = {'score': s['score'], 'params': trial_params.copy(),
                              'wr': s.get('wr',0), 'pf': s.get('pf',0), 'n': s.get('n',0),
                              'sig_stocks': s.get('stocks_signal',0)}
        
        # Log
        log_entry = {'r': r, 'score': best_trial['score'], 'wr': best_trial.get('wr',0),
                     'pf': best_trial.get('pf',0), 'n': best_trial.get('n',0),
                     'sig': best_trial.get('sig_stocks',0)}
        all_log.append(log_entry)
        
        if best_trial['score'] > best_score:
            best_score = best_trial['score']
            best_params = best_trial['params'].copy()
            no_improve = 0
            last_best_r = r
            
            # Full validation
            full_s = evaluate_params_flat(best_params, max_stocks=15)
            best_full_s = full_s
            json.dump({'score': best_score, 'params': best_params, 'full_eval': full_s, 'round': r, 't': time.time()},
                      open(BEST_FILE, 'w'), indent=2)
            
            elapsed = time.time() - t0
            print(f"[R{r:03d}] ★ Score={best_score:.1f} WR={full_s.get('wr',0):.1f}% PF={full_s.get('pf',0):.2f} N={full_s.get('n',0)} Sig={full_s.get('stocks_signal',0)} (Δt={elapsed:.1f}s)")
        else:
            no_improve += 1
        
        # 每10轮状态
        if r % 15 == 0:
            now = time.strftime('%H:%M:%S')
            last10 = max(log['score'] for log in all_log[-10:]) if len(all_log) >= 10 else best_score
            print(f"[{now} R{r:03d}/{n_rounds}] Best={best_score:.1f} ±={no_improve} Temp={temperature:.2f} L10={last10:.1f}")
            
            # Save progress
            json.dump({
                'best_score': best_score, 'best_params': best_params,
                'current_round': r, 'temperature': temperature,
                'full_eval': best_full_s,
                'log': all_log[-100:],
                't': time.time(),
            }, open(PROGRESS_FILE, 'w'))
        
        # 参数更新 (混合策略)
        if r % 4 == 0:
            current_params = best_params.copy()
        else:
            current_params = best_trial.get('params', current_params)
    
    # Final
    print(f"\n{'='*60}")
    print(f"V5.4 OPTIMIZATION COMPLETE: {n_rounds} rounds")
    print(f"Final Best: Score={best_score:.1f}")
    print(f"Best Params:")
    for k, v in best_params.items():
        print(f"  {k}: {v}")
    
    if best_full_s:
        print(f"\nFinal Validation ({best_full_s.get('stocks_ok',0)} stocks):")
        for k in ['score','wr','pf','n','n_wins','n_losses','ret','sr','stocks_signal']:
            if k in best_full_s:
                print(f"  {k}: {best_full_s[k]}")
    
    json.dump({
        'best_score': best_score, 'best_params': best_params,
        'final_eval': best_full_s, 'total_rounds': n_rounds,
        't': time.time(),
    }, open(LOG_DIR / 'final_result.json', 'w'), indent=2)
    
    return best_params, best_full_s


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--rounds', '-n', type=int, default=120)
    p.add_argument('--stocks', '-s', type=int, default=10)
    p.add_argument('--resume', '-r', action='store_true')
    p.add_argument('--quick', '-q', action='store_true')
    args = p.parse_args()
    
    print(f"=== SMC V5.4 AdaptOptimizer ({args.rounds} rounds) ===")
    print(f"Params: {len(OPT_PARAMS)} dims | Stocks: {args.stocks}")
    
    if args.quick:
        print("Quick test (default params):")
        s = evaluate_params_flat(default_flat_params(), max_stocks=8)
        for k in ['score','wr','pf','n','stocks_signal','stocks_ok']:
            print(f"  {k}: {s.get(k,0)}")
        exit(0)
    
    t0 = time.time()
    bp, fs = run_optimization(n_rounds=args.rounds, resume=args.resume)
    elapsed = time.time() - t0
    print(f"\nTime: {elapsed:.0f}s ({elapsed/max(1,args.rounds):.1f}s/round)")
    print(f"Saved to: {LOG_DIR}")