#!/usr/bin/env python3
"""V472 200-stock test — V12 signals + V467 exit logic"""
import sys, json, time
sys.path.insert(0, '/root/.hermes/scripts')
from v11.v472_engine import run_backtest, OUTPUT_DIR, CACHE_DIR

symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_60min_200.json')])[:200]
print(f"Testing V472 (V12 signals) on {len(symbols)} stocks...")

# Use v472 output dir
OUTPUT_DIR.mkdir(exist_ok=True)

result = run_backtest(symbols, "V472-60min")

if result and result.get('all_trades'):
    with open(f'{OUTPUT_DIR}/v472_200_trades.json', 'w') as f:
        json.dump(result['all_trades'][:500], f)  # sample
    with open(f'{OUTPUT_DIR}/v472_200_stocks.json', 'w') as f:
        json.dump(result['stock_results'], f)
    if 'summary' in result:
        with open(f'{OUTPUT_DIR}/v472_200_summary.json', 'w') as f:
            json.dump(result['summary'], f, indent=2)

print("V472 200 test done.")
