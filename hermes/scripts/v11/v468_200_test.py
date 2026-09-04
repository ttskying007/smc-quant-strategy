#!/usr/bin/env python3
"""V468 200-stock test"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
from v11.v468_engine import run_backtest, load_ohlcv, backtest_stock_v45, CACHE_DIR

# Use the top 200 alphabetically
symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_60min_200.json')])[:200]

result = run_backtest(symbols, "V468-60min")

if not result or not result.get('all_trades'):
    print("NO TRADES")
    sys.exit(1)

trades = result['all_trades']
stocks = result['stock_results']
summary = result['summary']

# Save results
import json
with open('/root/.hermes/smc_opt_v468/v468_200_results.json', 'w') as f:
    json.dump({'stock_results': stocks, 'all_trades': trades, 'summary': summary}, f)

n = len(trades)
wins = sum(1 for t in trades if t['won'])
print(f"\n=== V468 200-STOCK FINAL ===")
print(f"Stocks: {len(stocks)}/{len(symbols)}")
print(f"Trades: {n} | WR: {wins/n*100:.1f}% | RR: {sum(t['rr'] for t in trades)/n:.2f}x")
print(f"P&L: {sum(t['pnl_pct'] for t in trades)/n:+.2f}%")
print(f"Avg hold: {sum(t['hold_bars'] for t in trades)/n:.1f}b | Max: {max(t['hold_bars'] for t in trades)}b")
print(f"POI activated: {sum(1 for t in trades if t.get('poi_activated',False))}/{(n)}")
print(f"Avg POI wait: {sum(t.get('poiretrace_bars',0) for t in trades)/n:.1f}b")
print(f"W/L ratio: {sum(t['pnl_pct'] for t in trades if t['won'])/wins:.2f}% / {abs(sum(t['pnl_pct'] for t in trades if not t['won']))/(n-wins):.2f}%")
print(f"\nHold dist:")
for h in sorted(set(t['hold_bars'] for t in trades)):
    sub = [t for t in trades if t['hold_bars'] == h]
    w = sum(1 for t in sub if t['won'])/len(sub)*100
    r = sum(t['rr'] for t in sub)/len(sub)
    p = sum(t['pnl_pct'] for t in sub)/len(sub)
    print(f"  hold={h:2d}b: {len(sub):3d} WR={w:.1f}% RR={r:.2f}x P&L={p:+.2f}%")
