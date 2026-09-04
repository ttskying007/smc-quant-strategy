#!/usr/bin/env python3
"""V466 Daily full 4800 stock scan"""
from pathlib import Path
import sys, json, time
sys.path.insert(0, '/root/.hermes/scripts')

# All stocks from daily cache
CACHE = Path('/root/.hermes/kline_cache')
symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                  for f in CACHE.glob('*_daily_300.json')])

print(f"V466-Daily full scan: {len(symbols)} stocks")
print(f"Start: {time.strftime('%Y-%m-%d %H:%M:%S')}")
t0 = time.time()

from v11.v466_daily import run_backtest
result = run_backtest(symbols, "V466-Daily-Full")

elapsed = time.time() - t0
print(f"\nTotal time: {elapsed:.0f}s ({elapsed/60:.1f}min)")

if result and result.get('all_trades'):
    OUTPUT_DIR = Path('/root/.hermes/smc_opt_v466')
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    out_trades = OUTPUT_DIR / 'v466_full.json'
    json.dump(result['all_trades'], open(str(out_trades), 'w'))
    print(f"Saved trades: {out_trades}")
    
    out_summary = OUTPUT_DIR / 'v466_full_summary.json'
    json.dump(result.get('summary', {}), open(str(out_summary), 'w'))
    print(f"Saved summary: {out_summary}")
    
    out_stocks = OUTPUT_DIR / 'v466_full_stocks.json'
    result['stock_results'].sort(key=lambda r: -r['n_trades'])
    json.dump(result['stock_results'], open(str(out_stocks), 'w'))
    print(f"Saved stocks: {out_stocks}")
else:
    print("No results!")
