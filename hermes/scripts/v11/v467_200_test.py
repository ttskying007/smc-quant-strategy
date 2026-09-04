#!/usr/bin/env python3
"""V467 200-stock test on 60min data"""
import sys, json, time
sys.path.insert(0, '/root/.hermes/scripts')
from v11.v467_engine import run_backtest, OUTPUT_DIR, CACHE_DIR

symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_60min_200.json')])[:200]

result = run_backtest(symbols, "V467-60min")

if result and result.get('all_trades'):
    out_path = OUTPUT_DIR / 'v467_200.json'
    result['stock_results'].sort(key=lambda r: -r['n_trades'])
    json.dump({'stock_results': result['stock_results'],
               'all_trades': result['all_trades'],
               'summary': result['summary']}, open(str(out_path), 'w'), indent=2)
    print(f"\n  Saved: {out_path}")
