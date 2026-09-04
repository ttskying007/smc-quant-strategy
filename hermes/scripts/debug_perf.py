#!/usr/bin/env python3
"""Debug performance key"""
import json, os
d = json.load(open(os.path.expanduser('~/.hermes/smc_opt_v4/signal_details_full.json')))
print(f"Total: {len(d)}")
print(f"Performance keys: {list(d[0]['performance'].keys())}")
print(json.dumps(d[0]['performance'], indent=2))