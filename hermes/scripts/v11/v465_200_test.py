#!/usr/bin/env python3
"""V465 60min 200-stock test"""
from pathlib import Path
import sys
sys.path.insert(0, '/root/.hermes/scripts')

# Load first 200 stocks from 60min cache
CACHE = Path('/root/.hermes/kline_cache_60min')
symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                  for f in CACHE.glob('*_60min_200.json')])

test_syms = symbols[:200]
print(f"Testing V465-60min on {len(test_syms)} stocks...")

from v11.v465_engine import run_backtest
result = run_backtest(test_syms, "V465-60min")

if result and result.get('all_trades'):
    out_path = Path('/root/.hermes/smc_opt_v465') / 'v465_200.json'
    import json
    json.dump(result['all_trades'], open(str(out_path), 'w'))
    print(f"\nSaved: {out_path}")
