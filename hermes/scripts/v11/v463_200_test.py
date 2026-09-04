#!/usr/bin/env python3
"""V46.3 策略C 200只验证 — OB-only + 反转过滤 + V45入口"""
import json, sys, time
sys.path.insert(0, '/root/.hermes/scripts')

# Force reimport from file
if 'v11.v463_engine' in sys.modules:
    del sys.modules['v11.v463_engine']
from v11.v463_engine import run_backtest, CACHE_DIR, OUTPUT_DIR

symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_daily_300.json')])[:200]
print(f"Testing {len(symbols)} stocks...")

result = run_backtest(symbols, label="V463-OB-Rev")

if result and result.get('summary'):
    out_path = OUTPUT_DIR / 'v463_200.json'
    json.dump(result['summary'], open(str(out_path), 'w'))
    print(f"\nSaved: {out_path}")
