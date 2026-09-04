#!/usr/bin/env python3
"""V467 full 60min scan for all 4552 stocks"""
import sys, json, time
sys.path.insert(0, '/root/.hermes/scripts')
from v11.v467_engine import run_backtest, OUTPUT_DIR, CACHE_DIR

symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_60min_200.json')])
print(f"Scanning {len(symbols)} stocks from 60min cache...")

result = run_backtest(symbols, "V467-60min")

if result and result.get('all_trades'):
    result['stock_results'].sort(key=lambda r: -r['n_trades'])
    
    # Save trades
    trades_path = OUTPUT_DIR / 'v467_full_trades.json'
    json.dump(result['all_trades'], open(str(trades_path), 'w'))
    
    # Save per-stock results (compact)
    stocks_path = OUTPUT_DIR / 'v467_full_stocks.json'
    json.dump(result['stock_results'], open(str(stocks_path), 'w'))
    
    # Save summary
    summary_path = OUTPUT_DIR / 'v467_full_summary.json'
    json.dump(result['summary'], open(str(summary_path), 'w'), indent=2)
    
    print(f"\n  Saved trades: {trades_path}")
    print(f"  Saved stocks: {stocks_path}")
    print(f"  Saved summary: {summary_path}")
