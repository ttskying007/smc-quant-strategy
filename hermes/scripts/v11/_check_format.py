#!/usr/bin/env python3
import json
with open('/root/.hermes/smc_opt_v467/v467_full_stocks.json') as f:
    data = json.load(f)
print(type(data).__name__, 'len=', len(data) if hasattr(data, '__len__') else '?')
if isinstance(data, dict):
    print('keys:', list(data.keys())[:5])
elif isinstance(data, list) and len(data) > 0:
    print('first item keys:', list(data[0].keys())[:10])
