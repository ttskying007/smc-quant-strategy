#!/usr/bin/env python3
"""Comprehensive check: trace actual signal types through V13 detection chain."""
import sys
sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v12 import *

import json
cache_dir = '/root/.hermes/kline_cache_60min'
sym = '002245.SZ'
fp = f'{cache_dir}/{sym.replace(".","_")}_60min_200.json'
ohlcv = json.loads(open(fp).read())

adaptive = calc_adaptive_thresholds(ohlcv)
sw = detect_swings_v13_60min(ohlcv, left=8, right=3, adaptive=adaptive)
swings = (sw[0], sw[1])

# Check what detect_ob_v12 RETURNS
obs1 = detect_ob_v12(ohlcv, adaptive=adaptive, swings=swings, tf='60min', body_pct_min=0.08, displacement_mult=1.0, require_volume=True)
print(f"detect_ob_v12 returns: {len(obs1)} items, first type={type(obs1[0]).__name__ if obs1 else 'empty'}")
if obs1:
    first = obs1[0]
    if isinstance(first, Signal):
        print(f"  Signal: type={first.type}, confidence={first.confidence:.3f}")
        print(f"  has metadata key in to_dict: {'metadata' in first.to_dict()}")
        print(f"  to_dict keys: {list(first.to_dict().keys())[:15]}")
    elif isinstance(first, dict):
        print(f"  Dict: type={first.get('type')}, confidence={first.get('confidence')}")

# Check what detect_ob_v13_60min returns
obs2 = detect_ob_v13_60min(ohlcv, adaptive=adaptive, swings=swings, tf='60min')
print(f"\ndetect_ob_v13_60min returns: {len(obs2)} items")
types = {}
for s in obs2:
    tn = type(s).__name__
    types[tn] = types.get(tn, 0) + 1
print(f"  Type distribution: {types}")
if obs2:
    first = obs2[0]
    if isinstance(first, dict):
        print(f"  Dict: keys={list(first.keys())[:15]}")
        has_meta = 'metadata' in first
        print(f"  Has 'metadata' key: {has_meta}")
        print(f"  Has 'at_structure' key: {'at_structure' in first}")
        print(f"  Has 'body_pct' key: {'body_pct' in first}")
    elif isinstance(first, Signal):
        print(f"  Signal: metadata keys={list(first.metadata.keys())[:10]}")
    print(f"  [0] type={first.get('type','?')} conf={first.get('confidence',0):.3f}")

# Check detect_all_signals_v13_60min
sr = detect_all_signals_v13_60min(ohlcv, tf='60min')
all_s = sr.get('all', [])
print(f"\ndetect_all_signals_v13_60min: {len(all_s)} total signals")
type_counts = {}
for s in all_s:
    tn = type(s).__name__
    type_counts[tn] = type_counts.get(tn, 0) + 1
print(f"  Type distribution: {type_counts}")

# Check a few with 'OB' in type
for sig in all_s[:1]:
    print(f"  Sample: type={type(sig).__name__}, keys={list(sig.keys())[:20] if isinstance(sig,dict) else 'N/A'}")
    if isinstance(sig, dict):
        metab = 'metadata' in sig
        print(f"  .get('metadata'): {sig.get('metadata', 'NOT FOUND')}")
        
print("\nDone.")
