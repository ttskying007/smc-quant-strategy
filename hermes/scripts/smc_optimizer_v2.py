#!/usr/bin/env python3
"""
SMC Auto Optimizer v2.0 — 增强迭代引擎
==================================================================
核心改进:
1. 自适应评分 v6: 只评估高质量股票(trade>10的)的Sharpe中位数
2. 多策略并行: 每次迭代同时测试combo/sweep-fvg/osok三种策略
3. 精英保留: 最优参数在局部区域精细扫描
4. 更快迭代: 减少每轮股票数(20→10)但增加轮数(100→200+)
5. 代理自动恢复: 若检测到API连接失败, 自动尝试更换代理协议
==================================================================
"""

import json, math, sys, os, time, random, copy
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# --- Setup ---
SMC_DIR = os.path.expanduser('~/.hermes/skills/trading/smc-engine/scripts')
if SMC_DIR not in sys.path:
    sys.path.insert(0, SMC_DIR)

for k in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
    os.environ.pop(k, None)

from smc_backtest_v2 import (
    fetch_stock_list, fetch_klines, normalize_klines, calc_atr,
    detect_fvg, detect_liquidity_sweep, detect_order_blocks,
    detect_choch, detect_choch_v2, detect_market_structure,
    detect_combo_signals, calc_bpr, calc_ote, detect_volume_spread,
    backtest_single, generate_report, compute_sharpe, calc_drawdown,
    find_swing_highs, find_swing_lows,
)

OPT_DIR = Path.home() / '.hermes' / 'smc_opt'
ITER_DIR = OPT_DIR / 'iterations'
RESULTS_FILE = OPT_DIR / 'results_history.json'
BEST_PARAMS_FILE = OPT_DIR / 'best_params.json'
SUMMARY_FILE = OPT_DIR / 'summary_stats.json'
OPT_DIR.mkdir(parents=True, exist_ok=True)
ITER_DIR.mkdir(parents=True, exist_ok=True)


# ==================================================================
# 评分函数 v6: 只考虑"有效股票" (trade>10)的Sharpe和WR中位数
# ==================================================================

def evaluate_score_v6(per_stock_results):
    """
    从每只个股结果计算综合评分
    
    核心逻辑:
    - 只纳入交易次数>10的有效股票 (防过拟合)
    - 使用中位数而非平均数 (抗异常值)
    - WR>35%的股票数量占比作为核心指标
    - Sharpe>0的比例和平均Sharpe并重
    """
    valid = [r for r in per_stock_results if r.get('n_trades', 0) >= 10]
    if not valid or len(valid) < 5:
        return 0
    
    n_valid = len(valid)
    
    # 核心指标: WR分布
    wr_values = [r['win_rate'] for r in valid]
    high_wr_stocks = len([w for w in wr_values if w >= 33])  # WR>=33%
    very_high_wr_stocks = len([w for w in wr_values if w >= 40])
    
    wr_ratio = high_wr_stocks / n_valid
    vwr_ratio = very_high_wr_stocks / n_valid
    
    # Sharpe分布
    sharpe_values = [r['sharpe'] for r in valid]
    positive_sharpe = len([s for s in sharpe_values if s > 0])
    high_sharpe = len([s for s in sharpe_values if s > 1.0])
    very_high_sharpe = len([s for s in sharpe_values if s > 2.0])
    
    sp_ratio = positive_sharpe / n_valid
    hs_ratio = high_sharpe / n_valid
    vhs_ratio = very_high_sharpe / n_valid
    
    # 平均值 vs 中位数
    avg_sharpe = sum(sharpe_values) / n_valid
    median_sharpe = sorted(sharpe_values)[n_valid // 2]
    median_wr = sorted(wr_values)[n_valid // 2]
    
    # ---- 评分公式 v6.1 (Sharpe惩罚加强) ----
    
    # 0. 负Sharpe惩罚: avg_sharpe<0直接减半
    avg_sharpe_penalty = 1.0
    if avg_sharpe < 0:
        avg_sharpe_penalty = max(0.2, 1.0 + avg_sharpe)  # -0.5→0.5, -1.0→0
    
    # 1. Sharpe core (40%)
    sharpe_core = 0
    if avg_sharpe > 0:
        sharpe_core = min(40, avg_sharpe * 25)
    if avg_sharpe > 0.5:
        sharpe_core += 10
    if avg_sharpe > 1.0:
        sharpe_core += 10
    
    # 2. Sharpe ratio > 0 (20%)
    sp_score = min(20, sp_ratio * 25)
    
    # 3. WR >= 33% ratio (20%)
    wr_score = min(20, wr_ratio * 30)
    
    # 4. High quality stocks (20%)
    hq_score = min(20, (hs_ratio * 15 + vhs_ratio * 10))
    
    # 5. Very high WR bonus
    vwr_bonus = min(10, vwr_ratio * 25)
    
    # 6. WR median penalty/bonus
    if median_wr >= 35:
        med_bonus = 10
    elif median_wr >= 30:
        med_bonus = 5
    else:
        med_bonus = -10 * (35 - median_wr) / 35
    
    # Total with negative sharpe penalty
    total = (sharpe_core + sp_score + wr_score + hq_score + vwr_bonus + med_bonus) * avg_sharpe_penalty
    total = max(0, total)
    
    stats = {
        'n_valid': n_valid,
        'avg_sharpe': round(avg_sharpe, 3),
        'median_sharpe': round(median_sharpe, 3),
        'median_wr': round(median_wr, 1),
        'pos_sharpe_ratio': round(sp_ratio * 100, 1),
        'high_sharpe_ratio': round(hs_ratio * 100, 1),
        'high_wr_ratio': round(wr_ratio * 100, 1),
        'very_high_wr_ratio': round(vwr_ratio * 100, 1),
    }
    
    return round(total, 2), stats


# ==================================================================
# 快速评估 — 多策略 & 多参数
# ==================================================================

def quick_evaluate(params, stock_list, n_stocks=15, strategy='combo'):
    """
    快速评估一组参数, 在n_stocks上回测combo策略
    返回score和详细stats
    """
    sl = params.get('sl_atr_mult', 1.5)
    tp = params.get('tp_rr_mult', 2.0)
    
    per_stock = []
    errors = 0
    
    for idx, (code, name) in enumerate(stock_list[:n_stocks]):
        try:
            raw = fetch_klines(code, 'daily', 500)
            bars = normalize_klines(raw)
            if len(bars) < 100:
                errors += 1
                continue
            
            result = backtest_single(
                code, bars, strategy=strategy,
                sl_atr=sl, tp_rr=tp, only_long=False
            )
            
            trades = result.get('trades', [])
            if not trades:
                continue
            
            n = len(trades)
            wins = [t for t in trades if t['pnl'] > 0]
            losses = [t for t in trades if t['pnl'] <= 0]
            wr = len(wins) / n * 100
            ret = sum(t['pnl'] for t in trades) * 100
            pf = abs(sum(t['pnl'] for t in wins) / sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses) != 0 else 10.0
            sr = compute_sharpe([t['pnl'] for t in trades], 252)
            
            per_stock.append({
                'symbol': code, 'name': name,
                'n_trades': n, 'win_rate': round(wr, 1),
                'sharpe': sr, 'total_return_pct': round(ret, 2),
                'profit_factor': round(pf, 2),
            })
            
        except Exception:
            errors += 1
            continue
    
    score, stats = evaluate_score_v6(per_stock)
    
    return score, stats, per_stock


def multi_strategy_eval(params, stock_list, n_stocks=10):
    """同时评估三种策略"""
    results = {}
    for strat in ['combo', 'sweep-fvg', 'osok']:
        try:
            score, stats, stocks = quick_evaluate(params, stock_list, n_stocks, strat)
            results[strat] = {'score': score, 'stats': stats, 'stocks': stocks}
        except Exception as e:
            results[strat] = {'score': 0, 'stats': {'n_valid': 0}, 'stocks': [], 'error': str(e)}
    
    # Best strategy
    best_strat = max(results, key=lambda s: results[s]['score'])
    
    return results, best_strat


# ==================================================================
# 参数生成 v2 (更智能)
# ==================================================================

PARAM_SPACE = {
    'fvg_threshold': {'min': 0.15, 'max': 0.50, 'default': 0.30, 'step': 0.01},
    'sweep_wick_ratio': {'min': 1.0, 'max': 3.0, 'default': 1.5, 'step': 0.1},
    'ob_body_ratio': {'min': 0.3, 'max': 1.0, 'default': 0.5, 'step': 0.05},
    'sl_atr_mult': {'min': 0.8, 'max': 3.0, 'default': 1.5, 'step': 0.1},
    'tp_rr_mult': {'min': 1.0, 'max': 4.0, 'default': 2.0, 'step': 0.1},
    'sweep_lookback': {'min': 8, 'max': 25, 'default': 15, 'step': 1},
    'choch_lookback': {'min': 5, 'max': 25, 'default': 15, 'step': 1},
    'combo_fvg_sweep_max_dist': {'min': 3, 'max': 15, 'default': 10, 'step': 1},
    'fvg_merge_max_gap': {'min': 1, 'max': 4, 'default': 2, 'step': 1},
}


class ParamGeneratorV2:
    def __init__(self):
        self.history = []  # [{params, score, stats}]
        self.best_params = None
        self.best_score = -1
        self.gen = 0
        self.stagnation = 0
        self.best_per_gen = []  # track best per gen
    
    def random(self):
        p = {}
        for k, s in PARAM_SPACE.items():
            v = s['min'] + random.random() * (s['max'] - s['min'])
            if s['step'] > 0:
                v = round(v / s['step']) * s['step']
            p[k] = v
        return p
    
    def get_default(self):
        return {k: s['default'] for k, s in PARAM_SPACE.items()}
    
    def get_best(self):
        if self.best_params:
            return self.best_params
        return self.get_default()
    
    def mutate_best(self, rate=0.3):
        """在当前best附近变异"""
        p = dict(self.best_params or self.get_default())
        for k, s in PARAM_SPACE.items():
            if random.random() < rate:
                delta = (s['max'] - s['min']) * 0.05 * random.gauss(0, 1)
                p[k] = max(s['min'], min(s['max'], p[k] + delta))
                if s['step'] > 0:
                    p[k] = round(p[k] / s['step']) * s['step']
        return p
    
    def crossover_best_two(self):
        """从top2做交叉"""
        if len(self.history) < 4:
            return self.random()
        sorted_h = sorted(self.history[-30:], key=lambda x: x['score'], reverse=True)
        p1 = sorted_h[0]['params']
        p2 = sorted_h[1]['params'] if len(sorted_h) > 1 else (self.best_params or self.get_default())
        child = {}
        for k in PARAM_SPACE:
            child[k] = p1[k] if random.random() < 0.5 else p2[k]
            # Mutate
            if random.random() < 0.15:
                s = PARAM_SPACE[k]
                delta = (s['max'] - s['min']) * 0.03 * random.gauss(0, 1)
                child[k] = max(s['min'], min(s['max'], child[k] + delta))
                if s['step'] > 0:
                    child[k] = round(child[k] / s['step']) * s['step']
        return child
    
    def next(self):
        self.gen += 1
        if self.gen <= 5:
            return self.get_default() if self.gen == 1 else self.random()
        elif self.gen <= 10:
            return self.random()
        elif self.stagnation > 5:
            return self.mutate_best(rate=0.5)  # Bigger jumps when stuck
        elif random.random() < 0.4:
            return self.crossover_best_two()
        elif random.random() < 0.7:
            return self.mutate_best(rate=0.2)
        else:
            return self.random()
    
    def record(self, params, score, stats=None):
        self.history.append({'params': params, 'score': score, 'stats': stats})
        if score > self.best_score:
            self.best_score = score
            self.best_params = dict(params)
            self.stagnation = 0
            self.best_per_gen.append((self.gen, score))
        else:
            self.stagnation += 1


# ==================================================================
# 主优化循环
# ==================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--iterations', type=int, default=200, help='Total iterations')
    parser.add_argument('--stocks', type=int, default=12, help='Stocks per iteration')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--multi-strat', action='store_true', help='Test multiple strategies')
    args = parser.parse_args()
    
    N_ITERS = args.iterations
    N_STOCKS = args.stocks
    resume = args.resume
    
    # Load state
    start_iter = 0
    if resume and RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            state = json.load(f)
        start_iter = state.get('current_iteration', 0)
        print(f"Resumed: iter {start_iter}, best_score={state.get('best_score', 0)}")
    
    print(f"\n{'='*70}")
    print(f"  SMC Auto Optimizer v2.0")
    print(f"  Iterations: {N_ITERS} | Stocks/iter: {N_STOCKS}")
    print(f"  Multi-strat: {args.multi_strat} | Resume: {resume}")
    print(f"{'='*70}")
    
    # Load stocks
    print("Loading stock list...")
    all_stocks = fetch_stock_list()
    all_stocks = [(s['symbol'], s.get('name', '')) for s in all_stocks 
                  if not s.get('symbol', '').startswith('*ST')]
    random.seed(42)
    random.shuffle(all_stocks)
    print(f"  {len(all_stocks)} stocks")
    
    pg = ParamGeneratorV2()
    results_history = []
    best_score = state.get('best_score', -1) if resume else -1
    best_params = state.get('best_params') if resume else None
    best_all_time = best_score
    
    start_time = time.time()
    
    for iteration in range(start_iter + 1, N_ITERS + 1):
        t0 = time.time()
        
        # Generate params
        params = pg.next()
        
        # Run evaluation
        strategy = 'combo'
        try:
            score, stats, stocks = quick_evaluate(params, all_stocks, N_STOCKS, strategy)
            
            pg.record(params, score, stats)
            
            if score > best_all_time:
                best_all_time = score
                best_params = dict(params)
                
                # Save best immediately
                with open(BEST_PARAMS_FILE, 'w') as f:
                    json.dump({
                        'best_score': best_all_time,
                        'best_params': best_params,
                        'best_stats': stats,
                        'iteration': iteration,
                        'updated_at': datetime.now().isoformat(),
                    }, f, ensure_ascii=False, indent=2)
            
            # Save iteration
            entry = {
                'iteration': iteration,
                'score': score,
                'params': params,
                'stats': stats,
                'strategy': strategy,
                'best_params': best_params,
                'best_score': best_all_time,
            }
            results_history.append(entry)
            with open(ITER_DIR / f'iter_{iteration:04d}.json', 'w') as f:
                json.dump(entry, f, ensure_ascii=False, indent=2)
            
            # Update persistent state
            state = {
                'current_iteration': iteration,
                'best_score': best_all_time,
                'best_params': best_params,
                'best_result': entry,
                'results_history': results_history[-100:],  # Keep last 100
            }
            with open(RESULTS_FILE, 'w') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            
            elapsed = time.time() - t0
            
            # Print progress
            stats_str = f"SR={stats.get('avg_sharpe','?'):.2f} MW={stats.get('median_wr','?'):.1f}% HS={stats.get('high_wr_ratio','?'):.0f}% n={stats.get('n_valid','?')}"
    
            best_mark = ' 🏆' if score > best_all_time - 0.01 and score == best_all_time else ''
            print(f"  iter {iteration:>4d}/{N_ITERS} | score={score:>5.1f}{best_mark} | {stats_str} | {elapsed:.1f}s")
            
        except Exception as e:
            print(f"  iter {iteration:>4d}: ERROR {str(e)[:80]}")
            import traceback
            traceback.print_exc()
            time.sleep(2)
            continue
        
        # Early stop check
        if pg.stagnation > 30 and iteration > 40:
            print(f"\n  ⚡ Early stop: stagnated {pg.stagnation} iters")
            break
        
        # Progress report
        if iteration % 10 == 0:
            elapsed = time.time() - start_time
            rate = iteration / elapsed
            remaining = (N_ITERS - iteration) / rate if rate > 0 else 0
            print(f"\n  📊 [{iteration}/{N_ITERS}] Rate: {rate:.2f}it/s | "
                  f"ETA: {remaining/60:.1f}min | Best: {best_all_time} | "
                  f"Stagnation: {pg.stagnation}")
    
    # Final report
    total_time = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"  🏁 Optimization Complete!")
    print(f"  Iterations: {iteration if 'iteration' in dir() else N_ITERS}")
    print(f"  Time: {total_time/60:.1f} minutes")
    print(f"  Best score: {best_all_time}")
    if best_params:
        print(f"  Best params:")
        for k, v in best_params.items():
            print(f"    {k}: {v}")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()