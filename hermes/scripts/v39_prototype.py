#!/usr/bin/env python3
"""
SMC V39 — Position Sizing Prototype
====================================
基于V38.4全量回测**股票级聚合数据**, 应用浮动杠杆仓位管理:

Feature:
- Signal quality score (基于股票历史WR)
- Floating leverage: position% = base% × quality_score
- Base: hasTP=2%, noTP=1%
- Quality ranges: 0.5-1.5 based on WR

由于V38.4 JSON不包含逐笔交易明细, 
使用每只股票的聚合统计(entry_types分布, avg_pnl, WR, RR)进行估算。

Usage:
  PYTHONUNBUFFERED=1 python3 v39_prototype.py
"""
import json, sys, math
from pathlib import Path
from collections import defaultdict, Counter

V38_JSON = '/root/.hermes/smc_opt_v38/backtest_v384_full.json'
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v38')
OUTPUT_DIR.mkdir(exist_ok=True)

# Position sizing parameters
BASE_WITH_TP = 2.0   # % of portfolio per signal with TP
BASE_WITHOUT_TP = 1.0  # % of portfolio per signal without TP

WR_HIGH_THRESHOLD = 80.0
WR_MEDIUM_THRESHOLD = 70.0

# Entry types that typically have TP vs not
ENTRY_WITH_TP = {'FVG', 'OB', 'Sweep→FVG'}
ENTRY_WITHOUT_TP = {'CHOCH→retest', 'BreakerBlock'}


def load_v38_data():
    """Load V38.4 full backtest data (stock-level aggregates only)"""
    print(f"Loading V38.4 data from {V38_JSON}...", flush=True)
    data = json.loads(Path(V38_JSON).read_bytes())
    summary = data['summary']
    stock_results = data['stock_results']
    print(f"  Stocks: {summary['n_stocks']} | Trades: {summary['n_trades']}", flush=True)
    print(f"  WR: {summary['win_rate']}% | RR: {summary['avg_rr']}x | PF: {summary['profit_factor']}", flush=True)
    print(f"  Entry types: {summary['entry_type_breakdown']}", flush=True)
    print(f"  Exit methods: {summary['exit_method_breakdown']}", flush=True)
    return summary, stock_results


def compute_quality_score(stock):
    """
    Compute signal quality score based on stock-level WR/RR.
    Returns: quality_score (0.3-1.65), wr_bucket, wr, rr
    """
    wr = stock.get('win_rate', 0)
    avg_rr = stock.get('avg_rr', 0)
    
    if wr >= WR_HIGH_THRESHOLD:
        wr_bucket = 'high'
        quality_score = 1.5
    elif wr >= WR_MEDIUM_THRESHOLD:
        wr_bucket = 'medium'
        quality_score = 1.0
    else:
        wr_bucket = 'low'
        quality_score = 0.5
    
    # RR bonus for elite stocks
    if wr_bucket == 'high' and avg_rr >= 5.0:
        quality_score = min(quality_score * 1.1, 1.65)
    elif wr_bucket == 'medium' and avg_rr >= 3.0:
        quality_score = min(quality_score * 1.05, 1.1)
    
    # Heavy penalty for very low WR
    if wr < 50:
        quality_score = 0.3
    
    return round(quality_score, 3), wr_bucket, wr, avg_rr


def run_backtest(stock_results):
    """
    V39 position sizing backtest using stock-level aggregates.
    
    For each stock:
    - Get entry type distribution (n_trades per type)
    - Assign base position based on entry type (hasTP vs noTP)
    - Apply quality score multiplier
    - Calculate weighted P&L = sum(position% × avg_pnl_per_trade)
    """
    print("\n" + "=" * 80, flush=True)
    print("V39 POSITION SIZING BACKTEST (Stock-Aggregate Mode)", flush=True)
    print("=" * 80, flush=True)
    
    stock_allocations = []
    total_weighted_pnl = 0.0
    total_positions = 0
    
    # Track by entry type
    et_pnl = defaultdict(lambda: {'n': 0, 'pnl': 0.0, 'position_sum': 0.0})
    
    for stock in stock_results:
        symbol = stock['symbol']
        n_trades = stock.get('n_trades', 0)
        if n_trades < 1:
            continue
        
        avg_pnl = stock.get('avg_pnl', 0)
        entry_types = stock.get('entry_types', {})
        if not entry_types:
            continue
        
        # Quality score
        quality_score, wr_bucket, wr, avg_rr = compute_quality_score(stock)
        
        # Per-stock position sizing
        stock_pnl = 0.0
        total_entry_trades = sum(entry_types.values())
        positions = []
        
        for et, et_count in entry_types.items():
            # Determine if this entry type typically has TP
            has_tp = et in ENTRY_WITH_TP
            base_pct = BASE_WITH_TP if has_tp else BASE_WITHOUT_TP
            
            # Position size with floating leverage
            position_pct = base_pct * quality_score
            
            # Proportion of this stock's trades that use this entry type
            trade_share = et_count / total_entry_trades if total_entry_trades > 0 else 0
            
            # Weighted P&L contribution
            weighted_et_pnl = avg_pnl * (position_pct / 100) * trade_share * et_count
            
            stock_pnl += weighted_et_pnl
            total_weighted_pnl += weighted_et_pnl
            total_positions += 1
            
            et_pnl[et]['n'] += et_count
            et_pnl[et]['pnl'] += weighted_et_pnl
            et_pnl[et]['position_sum'] += position_pct * trade_share
            
            positions.append({
                'entry_type': et,
                'n_trades': et_count,
                'has_tp': has_tp,
                'base_pct': base_pct,
                'position_pct': round(position_pct, 2),
                'weighted_pnl': round(weighted_et_pnl, 4),
            })
        
        stock_allocations.append({
            'symbol': symbol,
            'n_trades': n_trades,
            'wr': wr,
            'avg_rr': avg_rr,
            'quality_bucket': wr_bucket,
            'quality_score': quality_score,
            'weighted_pnl_pct': round(stock_pnl, 4),
            'avg_position_pct': round(sum(p['position_pct'] for p in positions) / len(positions), 2) if positions else 0,
            'positions': positions,
        })
    
    # Sort by weighted P&L
    stock_allocations.sort(key=lambda x: -x['weighted_pnl_pct'])
    
    # Portfolio metrics
    n_stocks = len(stock_allocations)
    n_trades_total = sum(s['n_trades'] for s in stock_allocations)
    avg_pos = sum(s['avg_position_pct'] for s in stock_allocations) / n_stocks if n_stocks else 0
    
    # Summary
    print(f"\n{'='*80}", flush=True)
    print(f"PORTFOLIO-LEVEL METRICS", flush=True)
    print(f"{'='*80}", flush=True)
    print(f"  Total Stocks: {n_stocks}", flush=True)
    print(f"  Total Trades (processed): {n_trades_total}", flush=True)
    print(f"  Total Weighted P&L: {total_weighted_pnl:+.4f}%", flush=True)
    print(f"  Avg Position Size: {avg_pos:.2f}%", flush=True)
    print(f"  Base: hasTP={BASE_WITH_TP}%, noTP={BASE_WITHOUT_TP}%", flush=True)
    
    print(f"\n  P&L by Entry Type:", flush=True)
    for et, stats in sorted(et_pnl.items(), key=lambda x: -abs(x[1]['pnl'])):
        print(f"    {et:15s}: n={stats['n']:5d} PnL={stats['pnl']:+.4f}% avgPos={stats['position_sum']/max(stats['n'],1):.2f}%", flush=True)
    
    print(f"\n{'='*80}", flush=True)
    print(f"TOP 20 STOCKS (by weighted P&L)", flush=True)
    print(f"{'='*80}", flush=True)
    print(f"{'#':<4} {'Symbol':<12} {'N':<5} {'WR':<7} {'RR':<7} {'Q':<7} {'Pos%':<8} {'WtPnL%':<10}", flush=True)
    print("-" * 70, flush=True)
    for i, s in enumerate(stock_allocations[:20]):
        print(f"{i+1:<4} {s['symbol']:<12} {s['n_trades']:<5} {s['wr']:<7.1f} "
              f"{s['avg_rr']:<7.2f}x {s['quality_score']:<7.3f} {s['avg_position_pct']:<8.2f} "
              f"{s['weighted_pnl_pct']:<+10.4f}", flush=True)
    
    print(f"\nBOTTOM 10 STOCKS (by weighted P&L)", flush=True)
    for i, s in enumerate(stock_allocations[-10:]):
        print(f"  {i+1:<2}. {s['symbol']:<12} N={s['n_trades']:<3} WR={s['wr']:<5.1f}% "
              f"Q={s['quality_score']:<.3f} Pos={s['avg_position_pct']:<.2f}% "
              f"PnL={s['weighted_pnl_pct']:<+.4f}%", flush=True)
    
    # Quality bucket distribution
    print(f"\nQuality Distribution:", flush=True)
    q_dist = Counter(s['quality_bucket'] for s in stock_allocations)
    for q, cnt in q_dist.most_common():
        q_stocks = [s for s in stock_allocations if s['quality_bucket'] == q]
        avg_wpnl = sum(s['weighted_pnl_pct'] for s in q_stocks) / len(q_stocks) if q_stocks else 0
        print(f"  {q:8s}: {cnt:4d} stocks | avg WtPnL={avg_wpnl:+.4f}%", flush=True)
    
    # Save
    output = {
        'config': {
            'version': 'V39',
            'base_with_tp': BASE_WITH_TP,
            'base_without_tp': BASE_WITHOUT_TP,
            'wr_thresholds': {'high': WR_HIGH_THRESHOLD, 'medium': WR_MEDIUM_THRESHOLD},
            'quality_multipliers': {'high': 1.5, 'medium': 1.0, 'low': 0.5},
        },
        'portfolio_metrics': {
            'n_stocks': n_stocks,
            'n_trades': n_trades_total,
            'total_weighted_pnl_pct': round(total_weighted_pnl, 4),
            'avg_position_pct': round(avg_pos, 2),
            'pnl_by_entry_type': {et: {'n': v['n'], 'pnl_pct': round(v['pnl'], 4)}
                                  for et, v in sorted(et_pnl.items(), key=lambda x: -abs(x[1]['pnl']))},
        },
        'stock_allocations': [{
            'symbol': s['symbol'],
            'n_trades': s['n_trades'],
            'wr': s['wr'],
            'avg_rr': s['avg_rr'],
            'quality_score': s['quality_score'],
            'quality_bucket': s['quality_bucket'],
            'avg_position_pct': s['avg_position_pct'],
            'weighted_pnl_pct': s['weighted_pnl_pct'],
        } for s in stock_allocations],
    }
    
    outpath = OUTPUT_DIR / 'v39_position_sizing.json'
    json.dump(output, open(outpath, 'w'), ensure_ascii=False, indent=2, default=str)
    print(f"\nSaved: {outpath}", flush=True)
    
    return output


def main():
    summary, stock_results = load_v38_data()
    results = run_backtest(stock_results)
    
    pm = results['portfolio_metrics']
    print(f"\n{'='*80}", flush=True)
    print(f"V39 SUMMARY", flush=True)
    print(f"{'='*80}", flush=True)
    print(f"  Portfolio P&L: {pm['total_weighted_pnl_pct']:+.4f}%", flush=True)
    print(f"  Avg Position: {pm['avg_position_pct']:.2f}%", flush=True)
    print(f"  Stocks: {pm['n_stocks']} | Trades: {pm['n_trades']}", flush=True)
    print(f"  Quality: WR>=80%→1.5x, 70-80%→1.0x, <70%→0.5x", flush=True)
    print(f"  Base: hasTP=2%, noTP=1%", flush=True)


if __name__ == '__main__':
    main()
