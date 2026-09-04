#!/usr/bin/env python3
"""V33 Full Market Scan — Signal Time-Sequence Scoring"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts')
from v11.rolling_backtest_v33 import *

# Increase stocks to full market (not limited to 200)
# Monkey-patch: override backtest to run on ALL stocks
import v11.rolling_backtest_v33 as bt

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v33')
OUTPUT_DIR.mkdir(exist_ok=True)

symbols = sorted([f.stem.replace('_daily_300','').replace('_','.') for f in CACHE_DIR.glob('*_daily_300.json')])
print(f"V33 Full Market — {len(symbols)} stocks")

all_trades = []
stock_results = []
t_start = time.time()

for idx, sym in enumerate(symbols):
    result = bt.run_stock_v33(sym)
    if result:
        p = result['perf']
        all_trades.extend(result['trades'])
        stock_results.append(p)
    if (idx+1) % 500 == 0:
        elapsed = time.time() - t_start
        print(f"  [{idx+1}/{len(symbols)}] {len(stock_results)} tradable | {elapsed:.0f}s", flush=True)

total_time = time.time() - t_start

n = len(all_trades)
wins = sum(1 for t in all_trades if t['won'])
wr = wins / n * 100 if n else 0
win_pnl = sum(t['pnl_pct'] for t in all_trades if t['won'])
loss_pnl = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
pf = win_pnl / loss_pnl if loss_pnl > 0 else 999
rr = sum(t['rr'] for t in all_trades) / n if n else 0
pnl = sum(t['pnl_pct'] for t in all_trades) / n if n else 0
n80 = sum(1 for s in stock_results if s['win_rate'] >= 80)

print(f"\n{'='*70}")
print(f"V33 FULL MARKET — {len(stock_results)}/{len(symbols)} | {total_time:.0f}s")
print(f"{'='*70}")
print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
print(f"  WR>=80%: {n80}")
print(f"  Avg seq score: {sum(t['seq_score'] for t in all_trades)/n:.2f}")

outpath = OUTPUT_DIR / 'v33_full_merged.json'
json.dump({'timestamp': time.time(), 'config': {'version': 'V33', 'seq_scoring': True},
           'summary': {'total_symbols': len(symbols), 'tradable': len(stock_results),
                       'total_trades': n, 'win_rate': round(wr, 1), 'avg_rr': round(rr, 2),
                       'profit_factor': round(pf, 2), 'avg_pnl': round(pnl, 2)},
           'stocks': stock_results, 'all_trades': all_trades[:5000]},  # Cap trade data
          open(outpath, 'w'), ensure_ascii=False, indent=2, default=str)
print(f"\nSaved: {outpath}")
