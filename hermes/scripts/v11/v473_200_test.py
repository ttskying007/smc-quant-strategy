#!/usr/bin/env python3
"""V473 200-stock verification test"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
from v11.v473_engine import run_backtest, OUTPUT_DIR, CACHE_DIR

symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_60min_200.json')])[:200]

result = run_backtest(symbols, "V473-60min")

if result and result.get('all_trades'):
    result['stock_results'].sort(key=lambda r: -r['n_trades'])
    out_path = OUTPUT_DIR / 'v473_200.json'
    json.dump({
        'stocks': result['stock_results'],
        'trades': result['all_trades'],
        'summary': result['summary'],
    }, open(str(out_path), 'w'))
    print(f"\n  Saved: {out_path}")
