#!/usr/bin/env python3
"""V45 Full 4800 stock scanner - no output buffering"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
from v11.v45_engine import run_backtest, OUTPUT_DIR, CACHE_DIR

symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_daily_300.json')])

result = run_backtest(symbols, "V45-FULL")

if result:
    out_path = OUTPUT_DIR / 'v45_full.json'
    with open(str(out_path), 'w') as f:
        json.dump({
            'summary': result['summary'],
            'stock_results': result['stock_results'],
        }, f)
    print(f"\n  Full results saved: {out_path}")
    print(json.dumps(result['summary']))
