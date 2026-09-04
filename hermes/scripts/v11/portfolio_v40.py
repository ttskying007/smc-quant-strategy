#!/usr/bin/env python3
"""
V40 — SMC Portfolio Backtest with Quality-Weighted Position Sizing
==================================================================
基于V38.3全量逐笔数据(67,002笔, 4,282股票), 叠加仓位管理:
- WR分档浮动杠杆 (精英3x → 惩罚0.2x)
- 组合级指标: 总回报、夏普比、最大回撤(模拟)
- 场景分析: 最优WR阈值、入口类型贡献

Usage:
  cd /root/.hermes/scripts/v11 && PYTHONUNBUFFERED=1 python3 portfolio_v40.py
"""
import json, math, sys, time, random
from pathlib import Path
from collections import defaultdict, Counter

V38_FULL = '/root/.hermes/smc_opt_v38/backtest_v38_full.json'
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v40')
OUTPUT_DIR.mkdir(exist_ok=True)

# ── V40 仓位参数 ──
BASE_POS_PCT = 1.0       # 每笔基础仓位(%)
INITIAL_CAPITAL = 100_000

# WR分档 → 仓位乘数 (V40 refined)
WR_CONFIG = [
    (0,  40,  0.10, 'penalty'),
    (40, 60,  0.35, 'low'),
    (60, 75,  0.75, 'medium'),
    (75, 85,  1.00, 'baseline'),
    (85, 92,  1.35, 'high'),
    (92, 101, 1.75, 'elite'),
]

# RR加分档
RR_BONUS = [
    ('elite', 5.0, 1.15),
    ('high',  4.0, 1.08),
    ('baseline', 3.0, 1.05),
]


def quality_score(wr, rr):
    """WR+RR → 仓位乘数"""
    mult = 0.5
    label = 'unknown'
    for lo, hi, m, lb in WR_CONFIG:
        if lo <= wr < hi:
            mult, label = m, lb
            break
    # RR加分
    for lb, rr_thresh, bonus in RR_BONUS:
        if label == lb and rr >= rr_thresh:
            mult = min(mult * bonus, 2.0)
            break
    if wr < 30:
        mult = 0.05
    return round(mult, 3), label


def simulate_portfolio_pnl(trades_with_stock):
    """
    组合P&L蒙特卡洛模拟 (加性模型, bootstrapping)
    """
    n_sims = 500
    
    # 每笔交易的绝对贡献 ($)
    trade_contributions = [
        INITIAL_CAPITAL * (t['position_pct'] / 100) * (t['pnl_pct'] / 100)
        for t in trades_with_stock
    ]
    total_contrib = sum(trade_contributions)
    total_return_pct = total_contrib / INITIAL_CAPITAL * 100
    
    # Bootstrapping: 有放回重采样
    random.seed(42)
    n_sample = len(trade_contributions)
    all_returns = []
    
    for sim in range(n_sims):
        sample = [random.choice(trade_contributions) for _ in range(n_sample)]
        sample_return = sum(sample) / INITIAL_CAPITAL * 100
        all_returns.append(sample_return)
    
    sorted_ret = sorted(all_returns)
    p05 = sorted_ret[int(len(sorted_ret) * 0.05)]
    p25 = sorted_ret[int(len(sorted_ret) * 0.25)]
    p50 = sorted_ret[int(len(sorted_ret) * 0.50)]
    p75 = sorted_ret[int(len(sorted_ret) * 0.75)]
    p95 = sorted_ret[int(len(sorted_ret) * 0.95)]
    
    worst_5pct = sum(sorted_ret[:int(len(sorted_ret)*0.05)]) / max(int(len(sorted_ret)*0.05), 1)
    var_95 = -p05
    
    avg_ret = sum(all_returns) / len(all_returns)
    std_ret = (sum((r - avg_ret)**2 for r in all_returns) / len(all_returns))**0.5
    
    return {
        'n_simulations': n_sims,
        'total_pnl_pct': round(total_return_pct, 2),
        'expected_return_pct': round(avg_ret, 2),
        'percentiles': {
            'p5': round(p05, 2), 'p25': round(p25, 2),
            'p50': round(p50, 2), 'p75': round(p75, 2), 'p95': round(p95, 2),
        },
        'std_return_pct': round(std_ret, 2),
        'var_95_pct': round(var_95, 2),
        'worst_5pct_avg_return_pct': round(worst_5pct, 2),
        'pct_positive_returns': round(sum(1 for r in all_returns if r > 0)/len(all_returns)*100, 1),
    }


def main():
    print("=" * 80)
    print("V40 — SMC PORTFOLIO BACKTEST with Quality-Weighted Position Sizing")
    print("=" * 80)
    
    # ── 1. 加载数据 ──
    t0 = time.time()
    data = json.loads(Path(V38_FULL).read_bytes())
    stock_results = data['stock_results']
    trades = data['trades']
    
    print(f"\n[1/5] Data loaded: {len(trades)} trades, {len(stock_results)} stocks ({time.time()-t0:.1f}s)")
    print(f"  Baseline: WR={data['summary']['win_rate']}% RR={data['summary']['avg_rr']}x")
    
    # ── 2. 分配符号到交易 ──
    t1 = time.time()
    trades_with_stock = []
    cum = 0
    for sr in stock_results:
        sym = sr['symbol']
        wr = sr['win_rate']
        rr = sr['avg_rr']
        q, label = quality_score(wr, rr)
        n = sr['n_trades']
        stock_trades = trades[cum:cum+n]
        for t in stock_trades:
            t['symbol'] = sym
            t['wr'] = wr
            t['rr'] = rr
            t['quality'] = q
            t['quality_label'] = label
            # Position size
            pos = min(BASE_POS_PCT * q, 3.0)
            t['position_pct'] = pos
            trades_with_stock.append(t)
        cum += n
    
    print(f"\n[2/5] Symbol mapping done ({time.time()-t1:.1f}s)")
    
    # ── 3. 质量分分布分析 ──
    t2 = time.time()
    q_dist = Counter()
    for s in stock_results:
        _, label = quality_score(s['win_rate'], s['avg_rr'])
        q_dist[label] += 1
    
    print(f"\n[3/5] Quality Distribution:", flush=True)
    for label, cnt in q_dist.most_common():
        label_stocks = [s for s in stock_results if quality_score(s['win_rate'], s['avg_rr'])[1] == label]
        avg_wr = sum(s['win_rate'] for s in label_stocks) / len(label_stocks) if label_stocks else 0
        avg_rr = sum(s['avg_rr'] for s in label_stocks) / len(label_stocks) if label_stocks else 0
        avg_pnl = sum(s['avg_pnl'] for s in label_stocks) / len(label_stocks) if label_stocks else 0
        total_n = sum(s['n_trades'] for s in label_stocks)
        print(f"  {label:12s}: {cnt:4d} stocks | {total_n:5d} trades | "
              f"avgWR={avg_wr:.1f}% avgRR={avg_rr:.2f}x avgP&L={avg_pnl:+.2f}%", flush=True)
    
    # ── 4. 汇总组合指标(等权 vs 质量加权) ──
    t3 = time.time()
    print(f"\n[4/5] Portfolio Metrics ({time.time()-t3:.1f}s)")
    print(f"{'='*80}")
    
    # 4a. 等权基线 (单笔1%)
    ew_pnl = sum(t['pnl_pct'] for t in trades_with_stock) / len(trades_with_stock)
    ew_pnl_total = sum(t['pnl_pct'] * (BASE_POS_PCT/100) for t in trades_with_stock)
    ew_wins = sum(1 for t in trades_with_stock if t['won'])
    ew_wr = ew_wins / len(trades_with_stock) * 100
    
    # 4b. 质量加权
    qw_pnl_wt = sum(t['pnl_pct'] * (t['position_pct']/100) for t in trades_with_stock)
    qw_total_pos = sum(t['position_pct'] for t in trades_with_stock) / len(trades_with_stock)
    qw_avg_pos = sum(t['position_pct'] for t in trades_with_stock) / len(trades_with_stock)
    
    # 4c. 分质量段贡献
    bucket_pnl = defaultdict(lambda: {'n': 0, 'pnl_sum': 0.0, 'pos_sum': 0.0, 'win_sum': 0})
    for t in trades_with_stock:
        lb = t['quality_label']
        bucket_pnl[lb]['n'] += 1
        bucket_pnl[lb]['pnl_sum'] += t['pnl_pct'] * (t['position_pct']/100)
        bucket_pnl[lb]['pos_sum'] += t['position_pct']
        bucket_pnl[lb]['win_sum'] += 1 if t['won'] else 0
    
    print(f"\n{'Bucket':<12s} {'N':<7s} {'WtPnl':<10s} {'AvgPos':<8s} {'WR':<7s}")
    print(f"{'-'*50}")
    for lb, stats in sorted(bucket_pnl.items(), key=lambda x: -x[1]['pnl_sum']):
        wr_pct = stats['win_sum']/stats['n']*100 if stats['n'] else 0
        print(f"{lb:<12s} {stats['n']:<7d} {stats['pnl_sum']:<+10.4f}% "
              f"{stats['pos_sum']/stats['n']:<8.2f}% {wr_pct:<7.1f}%")
    
    total_qw_pnl = sum(v['pnl_sum'] for v in bucket_pnl.values())
    avg_qw_pos = sum(v['pos_sum'] for v in bucket_pnl.values()) / sum(v['n'] for v in bucket_pnl.values()) if sum(v['n'] for v in bucket_pnl.values()) else 0
    
    print(f"\n{'TOTAL':<12s} {len(trades_with_stock):<7d} {total_qw_pnl:<+10.4f}% "
          f"{avg_qw_pos:<8.2f}% {ew_wr:.1f}%")
    
    # 4d. 入口类型贡献
    print(f"\nPortfolio Contribution by Entry Type:")
    et_bucket = defaultdict(lambda: {'n':0, 'pnl_sum':0.0, 'pos_sum':0.0})
    for t in trades_with_stock:
        et = t['entry_type']
        et_bucket[et]['n'] += 1
        et_bucket[et]['pnl_sum'] += t['pnl_pct'] * (t['position_pct']/100)
        et_bucket[et]['pos_sum'] += t['position_pct']
    
    print(f"{'EntryType':<15s} {'N':<7s} {'PortPnl':<10s} {'AvgPos':<8s}")
    print(f"{'-'*45}")
    for et, s in sorted(et_bucket.items(), key=lambda x: -x[1]['pnl_sum']):
        print(f"{et:<15s} {s['n']:<7d} {s['pnl_sum']:<+10.4f}% {s['pos_sum']/s['n']:<8.2f}%")
    
    # 4e. 方向贡献
    dir_bucket = defaultdict(lambda: {'n':0, 'pnl_sum':0.0, 'pos_sum':0.0})
    for t in trades_with_stock:
        d = t['direction']
        dir_bucket[d]['n'] += 1
        dir_bucket[d]['pnl_sum'] += t['pnl_pct'] * (t['position_pct']/100)
        dir_bucket[d]['pos_sum'] += t['position_pct']
    
    print(f"\nPortfolio Contribution by Direction:")
    for d, s in dir_bucket.items():
        pct = s['pnl_sum']/total_qw_pnl*100 if total_qw_pnl != 0 else 0
        print(f"  {d:8s}: {s['n']:5d} trades | PnL={s['pnl_sum']:<+10.4f}% ({pct:.1f}% of total)")
    
    print(f"\n{'='*80}")
    print(f"EQUAL-WEIGHT BASELINE:")
    print(f"  Total P&L (1% each): {sum(t['pnl_pct']*(BASE_POS_PCT/100) for t in trades_with_stock):+.4f}%")
    print(f"  Avg trade P&L: {ew_pnl:+.4f}%")
    print(f"  WR: {ew_wr:.1f}%")
    
    print(f"\nQUALITY-WEIGHTED PORTFOLIO:")
    print(f"  Total P&L: {total_qw_pnl:+.4f}%")
    print(f"  Avg position: {avg_qw_pos:.2f}%")
    print(f"  Quality premium: {total_qw_pnl - sum(t['pnl_pct']*(BASE_POS_PCT/100) for t in trades_with_stock):+.4f}%")
    
    # ── 5. 蒙特卡洛模拟 ──
    t4 = time.time()
    print(f"\n[5/5] Monte Carlo Portfolio Simulation (500 runs)...")
    mc = simulate_portfolio_pnl(trades_with_stock)
    print(f"  Done ({time.time()-t4:.1f}s)")
    print(f"\nMonte Carlo Results (500 simulations):")
    print(f"  Expected Return:    {mc['expected_return_pct']:+.2f}%")
    print(f"  Total P&L:          {mc['total_pnl_pct']:+.2f}%")
    print(f"  Std Dev:            {mc['std_return_pct']:.2f}%")
    print(f"  VaR (95%%):         {mc['var_95_pct']:.2f}%")
    print(f"  Worst 5%% Avg:      {mc['worst_5pct_avg_return_pct']:+.2f}%")
    print(f"  %% Positive:         {mc['pct_positive_returns']:.1f}%")
    print(f"  Percentiles:")
    print(f"    P5:  {mc['percentiles']['p5']:+.2f}%")
    print(f"    P25: {mc['percentiles']['p25']:+.2f}%")
    print(f"    P50: {mc['percentiles']['p50']:+.2f}%")
    print(f"    P75: {mc['percentiles']['p75']:+.2f}%")
    print(f"    P95: {mc['percentiles']['p95']:+.2f}%")
    
    # ── 场景分析: 最优WR阈值 ──
    print(f"\n{'='*80}")
    print("SCENARIO ANALYSIS: Optimal WR Threshold")
    print(f"{'='*80}")
    
    thresholds = [50, 60, 70, 75, 80, 85, 90, 92, 95]
    print(f"{'WR>=':<6s} {'Stocks':<8s} {'Trades':<8s} {'PortPnl':<12s} {'AvgPos':<10s}")
    print(f"{'-'*50}")
    
    scenario_results = []
    for thresh in thresholds:
        # Filter stocks with WR >= threshold
        filtered = [t for t in trades_with_stock if t['wr'] >= thresh]
        if not filtered:
            continue
        total_pnl = sum(t['pnl_pct'] * (t['position_pct']/100) for t in filtered)
        avg_pos = sum(t['position_pct'] for t in filtered) / len(filtered)
        n_stocks = len(set(t['symbol'] for t in filtered))
        
        scenario_results.append({
            'wr_threshold': thresh,
            'n_stocks': n_stocks,
            'n_trades': len(filtered),
            'portfolio_pnl': round(total_pnl, 4),
            'avg_position': round(avg_pos, 2),
        })
        
        print(f"WR>={thresh:<3d}% {n_stocks:<8d} {len(filtered):<8d} {total_pnl:<+12.4f}% {avg_pos:<10.2f}%")
    
    # Find optimal
    best = max(scenario_results, key=lambda x: x['portfolio_pnl'])
    print(f"\n  Optimal: WR>={best['wr_threshold']}% → PnL={best['portfolio_pnl']:+.4f}% "
          f"({best['n_stocks']} stocks, {best['n_trades']} trades)")
    
    # ── 保存 ──
    output = {
        'config': {
            'version': 'V40',
            'base_position_pct': BASE_POS_PCT,
            'max_position_pct': 3.0,
            'wr_buckets': [(l, h) for l, h, _, _ in WR_CONFIG],
            'multipliers': [m for _, _, m, _ in WR_CONFIG],
        },
        'portfolio_metrics': {
            'n_trades': len(trades_with_stock),
            'n_stocks': len(stock_results),
            'equal_weight_pnl_pct': round(sum(t['pnl_pct']*(BASE_POS_PCT/100) for t in trades_with_stock), 4),
            'quality_weighted_pnl_pct': round(total_qw_pnl, 4),
            'quality_premium_pct': round(total_qw_pnl - sum(t['pnl_pct']*(BASE_POS_PCT/100) for t in trades_with_stock), 4),
            'avg_position_pct': round(avg_qw_pos, 2),
            'avg_trade_pnl_pct': round(ew_pnl, 4),
            'monte_carlo': mc,
        },
        'quality_distribution': {lb: cnt for lb, cnt in q_dist.most_common()},
        'bucket_contributions': {
            lb: {
                'n': stats['n'], 
                'weighted_pnl_pct': round(stats['pnl_sum'], 4),
                'avg_position_pct': round(stats['pos_sum']/stats['n'], 2) if stats['n'] else 0,
                'wr_pct': round(stats['win_sum']/stats['n']*100, 1) if stats['n'] else 0,
            }
            for lb, stats in sorted(bucket_pnl.items(), key=lambda x: -x[1]['pnl_sum'])
        },
        'entry_type_contributions': {
            et: {'n': s['n'], 'weighted_pnl_pct': round(s['pnl_sum'], 4)}
            for et, s in sorted(et_bucket.items(), key=lambda x: -x[1]['pnl_sum'])
        },
        'direction_contributions': {
            d: {'n': s['n'], 'weighted_pnl_pct': round(s['pnl_sum'], 4)}
            for d, s in dir_bucket.items()
        },
        'scenario_analysis': scenario_results,
        'optimal_threshold': {'wr_threshold': best['wr_threshold'], 'portfolio_pnl': best['portfolio_pnl']},
    }
    
    outpath = OUTPUT_DIR / 'v40_portfolio.json'
    json.dump(output, open(outpath, 'w'), ensure_ascii=False, indent=2, default=str)
    print(f"\nSaved: {outpath}")
    print(f"\nTotal time: {time.time()-t0:.1f}s")


if __name__ == '__main__':
    main()
