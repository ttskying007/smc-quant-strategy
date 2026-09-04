#!/usr/bin/env python3
import json
with open('/root/.hermes/smc_opt_v474/v45_full.json') as f:
    d = json.load(f)
print(type(d).__name__)
if isinstance(d, dict):
    print('keys:', list(d.keys())[:10])
elif isinstance(d, list) and len(d) > 0:
    d0 = d[0]
    print(f'list of {len(d)}, first type={type(d0).__name__}')
    if isinstance(d0, dict):
        print('first keys:', list(d0.keys())[:10])
