#!/usr/bin/env python3
"""V466 Daily 200-stock test"""
from pathlib import Path
import sys
sys.path.insert(0, '/root/.hermes/scripts')

# Load first 200 stocks from daily cache
CACHE = Path('/root/.hermes/kline_cache')
symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                  for f in CACHE.glob('*_daily_300.json')])

test_syms = symbols[:200]
print(f"Testing V466-Daily on {len(test_syms)} stocks (200-test)...")

from v11.v466_daily import run_backtest
result = run_backtest(test_syms, "V466-Daily-200")

if result and result.get('all_trades'):
    out_path = Path('/root/.hermes/smc_opt_v466') / 'v466_200.json'
    import json
    json.dump(result['all_trades'], open(str(out_path), 'w'))
    print(f"\nSaved: {out_path}")
