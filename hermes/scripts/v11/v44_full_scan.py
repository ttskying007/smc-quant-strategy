#!/usr/bin/env python3
"""V44全量4800股回测"""
import sys, json, time, os
sys.path.insert(0, '/root/.hermes/scripts')
from pathlib import Path
from collections import Counter

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v44')
OUTPUT_DIR.mkdir(exist_ok=True)

from v44_engine import backtest_stock_v44, load_ohlcv

symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_daily_300.json')])
print(f"Full scan: {len(symbols)} stocks")

t_start = time.time()
all_trades, stock_results = [], []

for idx, sym in enumerate(symbols):
    ohlcv = load_ohlcv(sym)
    if not ohlcv or len(ohlcv) < 150:
        if (idx + 1) % 500 == 0:
            print(f"  [{idx+1}/{len(symbols)}] {sym:12s} SKIP")
        continue

    result = backtest_stock_v44(ohlcv, sym)
    if result:
        p = result['perf']
        for trade in result['trades']:
            trade['symbol'] = sym
        all_trades.extend(result['trades'])
        stock_results.append({'symbol': sym, **p})
        if (idx + 1) % 100 == 0 or p['n_trades'] > 0:
            print(f"  [{idx+1:4d}/{len(symbols)}] {sym:12s} n={p['n_trades']:2d} WR={p['win_rate']:.0f}% RR={p['avg_rr']:.2f}x")
    elif (idx + 1) % 500 == 0:
        print(f"  [{idx+1}/{len(symbols)}] {sym:12s} SKIP")

total_time = time.time() - t_start

if all_trades:
    n = len(all_trades)
    wins = sum(1 for t in all_trades if t['won'])
    wr = wins / n * 100
    wp = sum(t['pnl_pct'] for t in all_trades if t['won'])
    lp = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
    pf = wp / lp if lp > 0 else 999
    rr = sum(t['rr'] for t in all_trades) / n
    pnl = sum(t['pnl_pct'] for t in all_trades) / n
    holds = [t['hold_bars'] for t in all_trades]
    
    tp_hits = [t for t in all_trades if t.get('exit_method') == 'tp_hit']
    trailing_trades = [t for t in all_trades if t.get('exit_method') == 'trailing']
    bull_trades = [t for t in all_trades if t.get('direction') == 'bull']
    bear_trades = [t for t in all_trades if t.get('direction') == 'bear']

    print(f"\n  === V44 FULL (4800 stocks) ===")
    print(f"  Time: {total_time:.0f}s | Stocks: {len(stock_results)}/{len(symbols)}")
    print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
    print(f"  Avg hold: {sum(holds)/len(holds):.1f} bars")
    
    for label, trades in [('TP hit', tp_hits), ('Trailing', trailing_trades),
                           ('Bull', bull_trades), ('Bear', bear_trades)]:
        if trades:
            tn = len(trades)
            tw = sum(1 for t in trades if t['won']) / tn * 100
            tr = sum(t['rr'] for t in trades) / tn
            print(f"    {label:12s}: n={tn:5d} WR={tw:.1f}% RR={tr:.2f}x")

    # Save
    outpath = OUTPUT_DIR / 'v44_full.json'
    json.dump({
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'V44-FULL',
        'config': {'ob_v14': True, 'retest_entry': True, 'bear_enhanced': True},
        'summary': {
            'total_trades': n, 'tradable': len(stock_results),
            'win_rate': round(wr, 1), 'avg_rr': round(rr, 2),
            'profit_factor': round(pf, 2) if pf < 999 else 999,
            'avg_pnl': round(pnl, 2),
            'avg_hold': round(sum(holds)/len(holds), 1),
        },
        'stocks': stock_results,
        'all_trades': all_trades,
    }, open(outpath, 'w'), ensure_ascii=False, indent=2, default=str)
    print(f"\n  Saved: {outpath}")
else:
    print("\n  No trades!")
