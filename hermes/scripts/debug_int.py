#!/usr/bin/env python3
"""Find the int"""
import json, os
cache_dir = '/root/.hermes/kline_cache'
for f in os.listdir(cache_dir):
    if not f.endswith('_daily_300.json'): continue
    path = os.path.join(cache_dir, f)
    try:
        with open(path) as fp:
            bars = json.load(fp)
        for b in bars:
            t = b.get('t')
            if isinstance(t, int):
                print(f"INT FOUND: {f} t={t}")
                break
            elif not isinstance(t, str):
                print(f"OTHER: {f} t={t} type={type(t)}")
                break
    except:
        pass
    break  # only first file

# Also test the exact code that fails
print("\n--- Replicating error ---")
with open(os.path.join(cache_dir, '920163_BJ_daily_300.json')) as fp:
    bars = json.load(fp)

# What detect_entries_v4 returns:
from smc_engine_v4 import detect_entries_v4
params = {'fvg_threshold': 0.26, 'score_threshold': 1.7, 'sl_mult': 2.5, 'tp_mult': 2.1}
entries = detect_entries_v4(bars, params)
print(f"entries keys: {list(entries.keys())}")
if entries.get('strict'):
    e = entries['strict'][0]
    idx = e.get('idx', 0)
    print(f"idx={idx} type={type(idx)}")
    # THIS is the error call
    try:
        t = bars[idx].get('t','')
        print(f"t={t} type={type(t)}")
        print(f"len(t)={len(str(t))}")
    except Exception as ex:
        print(f"Error: {ex}")
        
# Check if idx could be out of range
print(f"bars len={len(bars)}")
print(f"idx={idx}")
if idx < len(bars):
    print(f"bar at idx: {bars[idx]}")
else:
    print(f"IDX OUT OF RANGE! bars={len(bars)} idx={idx}")