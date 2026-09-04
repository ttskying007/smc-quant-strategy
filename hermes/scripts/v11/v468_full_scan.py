#!/usr/bin/env python3
"""V468 全量4552扫描 — POI回调入场+真实入场+SCOUT-only过滤器"""
import sys, json, time
sys.path.insert(0, '/root/.hermes/scripts')
import v11.v468_engine as eng
from pathlib import Path

t0 = time.time()

symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                 for f in eng.CACHE_DIR.glob('*_60min_200.json')])

eng.MIN_PROJECTED_RR = 6.0
eng.SWING_SKIP = 3
eng.POI_RETRACE_WINDOW = 50
eng.SL_MIN = 0.30

result = eng.run_backtest(symbols, "V468-full-4552")

trades = result.get('all_trades', [])
n = len(trades)
wins = sum(1 for t in trades if t.get('won'))
rr = sum(t.get('rr', 0) for t in trades) / n if n else 0
pnl = sum(t.get('pnl_pct', 0) for t in trades) / n if n else 0
hold = sum(t.get('hold_bars', 0) for t in trades) / n if n else 0
stocks_traded = len(result.get('stock_results', []))

print(f"\n{'='*70}")
print(f"V468 FULL 4552-STOCK")
print(f"{'='*70}")
print(f"Time: {time.time()-t0:.0f}s | Stocks: {stocks_traded}/{len(symbols)} ({stocks_traded/len(symbols)*100:.1f}%)")
print(f"Trades: {n} | WR: {wins/n*100:.1f}% | RR: {rr:.2f}x | P&L: {pnl:+.2f}% | Hold: {hold:.1f}b")
print()

# RR distribution
rr_bins = {'<=1.5x': 0, '1.5-3x': 0, '3-5x': 0, '5-10x': 0, '>10x': 0}
for t in trades:
    r = t.get('rr', 0)
    if r <= 1.5: rr_bins['<=1.5x'] += 1
    elif r <= 3: rr_bins['1.5-3x'] += 1
    elif r <= 5: rr_bins['3-5x'] += 1
    elif r <= 10: rr_bins['5-10x'] += 1
    else: rr_bins['>10x'] += 1
print("RR Distribution:")
for k, v in rr_bins.items():
    print(f"  {k}: {v} ({v/n*100:.1f}%)")

# Save to V468 output dir
out_dir = Path('/root/.hermes/smc_opt_v468')
out_dir.mkdir(exist_ok=True)

# Save stocks summary
stocks_out = []
for sr in result.get('stock_results', []):
    stocks_out.append({
        'symbol': sr['symbol'],
        'n_trades': sr['n_trades'],
        'wr': sr.get('wr', 0),
        'rr': sr.get('avg_rr', 0),
        'pnl_pct': sr.get('avg_pnl', 0),
    })
with open(out_dir / 'v468_full_stocks.json', 'w') as f:
    json.dump(stocks_out, f)

# Save trades
with open(out_dir / 'v468_full_trades.json', 'w') as f:
    json.dump(trades, f)

# Build trade map
trade_map = {}
for sr in result.get('stock_results', []):
    trade_map[sr['symbol']] = sr.get('trades', [])
with open(out_dir / 'v468_full_trade_map.json', 'w') as f:
    json.dump(trade_map, f)

print(f"\nResults saved to {out_dir}/")
print(f"Elapsed: {time.time()-t0:.0f}s ({(time.time()-t0)/60:.1f}min)")
