#!/usr/bin/env python3
"""Check signal_details_full format"""
import json, os
d = json.load(open(os.path.expanduser('~/.hermes/smc_opt_v4/signal_details_full.json')))
print(f"Total entries: {len(d)}")
print(f"Type of first: {type(d[0])}")
print(f"Keys: {list(d[0].keys())}")
print(f"signals type: {type(d[0].get('signals'))}")
print(f"signals len: {len(d[0].get('signals',[]))}")

# Check perf
s = d[0]
if 'perf' in s:
    print(f"perf: {json.dumps(s['perf'], indent=2)}")
else:
    print(f"perf not found. Has keys: {[k for k in s.keys()]}")
    # check nested
    if 'signals' in s and s['signals'] and isinstance(s['signals'], list):
        print(f"First signal keys: {list(s['signals'][0].keys())}")