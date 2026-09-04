#!/usr/bin/env python3
"""V45 200-stock validation"""
import sys
sys.path.insert(0, '/root/.hermes/scripts')
from v11.v45_engine import run_backtest, OUTPUT_DIR, CACHE_DIR
import json

# Top 200 stocks (sorted)
symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_daily_300.json')])[:200]

result = run_backtest(symbols, "V45-200")

if result:
    out_path = OUTPUT_DIR / 'v45_200.json'
    summary = {
        'n_stocks': result['summary']['n_stocks'],
        'n_trades': result['summary']['n_trades'],
        'win_rate': result['summary']['win_rate'],
        'avg_rr': result['summary']['avg_rr'],
        'profit_factor': result['summary']['profit_factor'],
        'avg_pnl': result['summary']['avg_pnl'],
    }
    json.dump(summary, open(str(out_path), 'w'))
    print(f"\n  Summary saved: {out_path}")
    print(f"  Results: {json.dumps(summary)}")
