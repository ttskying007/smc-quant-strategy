#!/usr/bin/env python3
"""Check V45 JSON structure and generate report"""
import json
from pathlib import Path
from collections import Counter

V45 = json.loads(Path('/root/.hermes/smc_opt_v45/v45_full.json').read_bytes())
print('keys:', list(V45.keys()))
if 'summary' in V45:
    print('summary:', V45['summary'])
    print('trades count from summary:', V45['summary'].get('n_trades', 0))
if 'trades' in V45:
    print('trades:', len(V45['trades']))
elif 'all_trades' in V45:
    print('all_trades:', len(V45['all_trades']))
if 'stock_results' in V45:
    print('stocks:', len(V45['stock_results']))
    s0 = V45['stock_results'][0]
    print('sample stock keys:', list(s0.keys()))

# Try to find where trades are
for k, v in V45.items():
    if isinstance(v, list) and len(v) > 0:
        print(f'  key={k}: len={len(v)}, sample={v[0] if isinstance(v[0], dict) else type(v[0])}')
