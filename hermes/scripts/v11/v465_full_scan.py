#!/usr/bin/env python3
"""V465 60min full 4552-stock scanner (RR=8.0, multi-bar BE)"""
import sys, json
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts/v11')
from v465_engine import run_backtest, CACHE_DIR, OUTPUT_DIR

symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_60min_200.json')])
print(f"Scanning {len(symbols)} stocks from 60min cache...")
result = run_backtest(symbols, "V465-60min")

if result and result.get('all_trades'):
    stock_out = OUTPUT_DIR / 'v465_full_stocks.json'
    trades_out = OUTPUT_DIR / 'v465_full_trades.json'
    result['stock_results'].sort(key=lambda r: -r['n_trades'])
    json.dump(result['stock_results'], open(str(stock_out), 'w'), indent=2)
    json.dump(result['all_trades'], open(str(trades_out), 'w'))
    print(f"\nSaved: {stock_out} and {trades_out}")
