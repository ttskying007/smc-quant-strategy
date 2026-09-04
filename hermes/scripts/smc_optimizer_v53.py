#!/usr/bin/env python3
"""
SMC V5.3 全自动迭代优化器 (≥100轮)
======================================
架构:
  - 100轮迭代, 每轮对所有参数进行随机/网格搜索
  - 每轮: 测试10只股票 → 评分 → 参数微调
  - 每轮参数更新: 最优参数 + 随机扰动(模拟退火)
  - 10轮检查一次 → 如果无进步, 重启大范围搜索

流程:
  1. 初始化参数
  2. 每轮: 随机扰动参数 → 测试 → 评分
  3. 保持最优参数
  4. 每10轮: 扩大搜索范围
  5. 输出结果
"""

import sys, json, time, math, random, os
from pathlib import Path

# Add to path for engine imports
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))

LOG_DIR = Path.home() / '.hermes' / 'smc_opt_v53'
LOG_DIR.mkdir(parents=True, exist_ok=True)
PROGRESS_FILE = LOG_DIR / 'optimizer_progress.json'
BEST_FILE = LOG_DIR / 'best_params.json'
LOG_FILE = LOG_DIR / 'optimization_log.ndjson'

# ════════ 测试股票池 (10只, 覆盖不同波动率) ════════

TEST_STOCKS = [
    '300231.SZ',  # 科技
    '000858.SZ',  # 白酒
    '600519.SH',  # 茅台
    '002415.SZ',  # 海康
    '300750.SZ',  # 宁德
    '601318.SH',  # 平安
    '000333.SZ',  # 美的
    '002594.SZ',  # 比亚迪
    '688981.SH',  # 中芯
    '600036.SH',  # 招行
    '300059.SZ',  # 东方财富
    '600030.SH',  # 中信
    '002230.SZ',  # 科大讯飞
    '300124.SZ',  # 汇川
    '600276.SH',  # 恒瑞
]

# ════════ 参数空间 ════════
from smc_engine_v53 import V53_PARAM_SPACE, load_bars, backtest_v53, compute_v53_score, get_vol_profile

def default_params():
    return {k: v['default'] for k, v in V53_PARAM_SPACE.items()}

def randomize_params(current=None, temperature=0.3):
    """随机生成参数, 如果提供了current则在其附近扰动"""
    p = {}
    for k, v in V53_PARAM_SPACE.items():
        if current and random.random() > 0.15:  # 85%保留附近, 15%完全随机
            # 扰动 ~15%
            delta = (v['max'] - v['min']) * temperature * random.gauss(0, 0.15)
            val = current.get(k, v['default']) + delta
        else:
            val = v['min'] + random.random() * (v['max'] - v['min'])
        val = max(v['min'], min(v['max'], val))
        if 'step' in v and v['step'] > 0.01:
            # 离散化
            val = round(val / v['step']) * v['step']
        p[k] = round(val, 2) if isinstance(val, float) else val
    return p

def evaluate_params(params, stock_list=None, max_stocks=15):
    """评估一组参数在多个股票上的表现"""
    if stock_list is None:
        stock_list = TEST_STOCKS[:max_stocks]
    
    all_trades = []
    stocks_ok = 0
    stocks_with_signals = 0
    
    for symbol in stock_list:
        try:
            bars = load_bars(symbol, 'daily', 300)
            if not bars or len(bars) < 50:
                continue
            stocks_ok += 1
            trades = backtest_v53(bars, params)
            if trades:
                stocks_with_signals += 1
                all_trades.extend(trades)
        except Exception as e:
            continue
    
    if not all_trades:
        return {'score': 0, 'wr': 0, 'pf': 0, 'n': 0, 'stocks_ok': stocks_ok, 'stocks_signal': 0}
    
    s = compute_v53_score(all_trades)
    s['stocks_ok'] = stocks_ok
    s['stocks_signal'] = stocks_with_signals
    s['total_stocks'] = len(stock_list)
    s['n_total_trades'] = len(all_trades)
    return s

def run_optimization(n_rounds=100, n_start=10, resume=False):
    """运行优化
    
    Args:
        n_rounds: 总轮数
        n_start: 起始轮数 (用于恢复)
        resume: 是否从之前的进度恢复
    """
    
    # 恢复进度
    best_score = 0
    best_params = default_params()
    all_results = []
    start_round = 0
    
    if resume and PROGRESS_FILE.exists():
        try:
            progress = json.load(open(PROGRESS_FILE))
            best_score = progress.get('best_score', 0)
            best_params = progress.get('best_params', best_params)
            all_results = progress.get('all_results', [])
            start_round = progress.get('current_round', 0) + 1
            print(f"[恢复] 从第{start_round}轮继续, 当前最佳Score={best_score}")
        except:
            pass
    
    if not resume:
        # 先做一次baseline
        baseline_s = evaluate_params(best_params)
        best_score = baseline_s['score']
        print(f"[Baseline] Score={best_score:.1f} WR={baseline_s.get('wr',0):.1f}% PF={baseline_s.get('pf',0):.2f}")
        all_results.append({
            'round': 0, 'params': best_params.copy(),
            'score': best_score, 'wr': baseline_s.get('wr',0),
            'pf': baseline_s.get('pf',0), 'n': baseline_s.get('n',0),
            'stocks_signal': baseline_s.get('stocks_signal',0),
        })
    
    current_params = best_params.copy()
    temperature = 0.5
    no_improve_count = 0
    last_best_round = start_round
    
    # Main loop
    for rnd in range(start_round, n_rounds):
        r = rnd + 1  # 1-index
        
        # 降温策略
        if temperature > 0.05:
            temperature = 0.5 * math.exp(-r / 30)
        
        # 每20轮扩大搜索
        if r % 20 == 0 and no_improve_count > 5:
            temperature = 0.6
            no_improve_count = 0
            print(f"  [Expanding] Temperature reset to {temperature}")
        
        # 尝试5组随机参数
        best_this_round = {'score': 0, 'params': current_params}
        
        for trial in range(5):
            trial_params = randomize_params(current_params if r > 3 else best_params, temperature)
            s = evaluate_params(trial_params, max_stocks=8)
            
            if s['score'] > best_this_round['score']:
                best_this_round = {'score': s['score'], 'params': trial_params.copy(), **s}
        
        all_results.append({
            'round': r,
            'params': best_this_round['params'],
            'score': best_this_round['score'],
            'wr': best_this_round.get('wr', 0),
            'pf': best_this_round.get('pf', 0),
            'n': best_this_round.get('n', 0),
            'stocks_signal': best_this_round.get('stocks_signal', 0),
        })
        
        # 更新最佳
        if best_this_round['score'] > best_score:
            best_score = best_this_round['score']
            best_params = best_this_round['params'].copy()
            no_improve_count = 0
            last_best_round = r
            
            # 用完整股票池验证
            full_s = evaluate_params(best_params, max_stocks=15)
            print(f"[R{r:03d}] ★ NEW BEST: Score={best_score:.1f} → Full: WR={full_s.get('wr',0):.1f}% PF={full_s.get('pf',0):.2f} N={full_s.get('n',0)} SigStocks={full_s.get('stocks_signal',0)}")
            
            # 保存best
            json.dump({'score': best_score, 'params': {k:round(v,4) for k,v in best_params.items()},
                       'full_eval': full_s, 'round': r, 'timestamp': time.time()},
                      open(BEST_FILE, 'w'), indent=2)
        else:
            no_improve_count += 1
        
        # 每5轮打印状态
        if r % 10 == 0:
            now = time.strftime('%H:%M:%S')
            print(f"[{now} R{r:03d}/{n_rounds}] BestScore={best_score:.1f} Temp={temperature:.2f} NoImpr={no_improve_count} ParamSample={best_params.get('fvg_min_width',0):.3f}")
        
        # 每5轮保存进度
        if r % 5 == 0:
            json.dump({
                'best_score': best_score,
                'best_params': best_params,
                'current_round': r,
                'all_results': all_results[-50:],
                'temperature': temperature,
                'timestamp': time.time(),
            }, open(PROGRESS_FILE, 'w'))
        
        # 更新当前参数 (50%最佳 + 50%最新)
        if r % 3 == 0:
            current_params = best_params.copy()
        else:
            current_params = best_this_round.get('params', current_params)
    
    # 结束后的全量验证
    print(f"\n{'='*60}")
    print(f"OPTIMIZATION COMPLETE: {n_rounds} rounds")
    print(f"Best Score: {best_score:.1f}")
    print(f"Best Params:")
    for k, v in best_params.items():
        print(f"  {k}: {v}")
    
    # Final full evaluation
    print(f"\nFinal evaluation (15 stocks):")
    final_s = evaluate_params(best_params, max_stocks=15)
    for k in ['score','wr','pf','n','n_wins','n_losses','ret','sr','stocks_signal','stocks_ok']:
        if k in final_s:
            print(f"  {k}: {final_s[k]}")
    
    # Save final
    json.dump({
        'best_score': best_score,
        'best_params': best_params,
        'final_eval': final_s,
        'total_rounds': n_rounds,
        'timestamp': time.time(),
    }, open(LOG_DIR / 'final_result.json', 'w'), indent=2)
    
    return best_params, final_s


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--rounds', '-n', type=int, default=100)
    parser.add_argument('--stocks', '-s', type=int, default=8, help='Stocks per eval')
    parser.add_argument('--resume', '-r', action='store_true')
    parser.add_argument('--quick', '-q', action='store_true', help='Quick: test only')
    args = parser.parse_args()
    
    print(f"=== SMC V5.3 Optimizer ({args.rounds} rounds) ===")
    print(f"Parameters: {len(V53_PARAM_SPACE)} dims")
    print(f"Test stocks: {args.stocks} at a time")
    
    if args.quick:
        print(f"\nQuick evaluation of default params...")
        s = evaluate_params(default_params(), max_stocks=15)
        print(f"Default: Score={s.get('score',0):.1f} WR={s.get('wr',0):.1f}% PF={s.get('pf',0):.2f} Trades={s.get('n',0)}")
        exit(0)
    
    start_t = time.time()
    best_params, final_s = run_optimization(n_rounds=args.rounds, resume=args.resume)
    elapsed = time.time() - start_t
    
    avg_per_round = elapsed / args.rounds if args.rounds else 0
    print(f"\nTime: {elapsed:.0f}s ({avg_per_round:.1f}s/round)")
    print(f"Results saved to {LOG_DIR}")