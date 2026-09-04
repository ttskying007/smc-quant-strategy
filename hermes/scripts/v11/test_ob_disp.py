#!/usr/bin/env python3
"""Diagnostic: check what displacement ratios we're getting from OB detection"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_vPine import detect_all_signals_vPine, detect_ob_vPine, _find_swing_highs_vPine, _find_swing_lows_vPine

# Load one stock
fpath = '/root/.hermes/kline_cache_60min/688800_SH_60min_200.json'
data = json.loads(open(fpath).read())
for bar in data:
    if 'date' not in bar and 't' in bar:
        bar['date'] = str(bar['t'])

print(f"Bars: {len(data)}")

# Quick swings
qh = _find_swing_highs_vPine(data, 8)
ql = _find_swing_lows_vPine(data, 8)
print(f"Quick swings: {len(qh)} highs, {len(ql)} lows")

# Pine swings
from v11.signals_vPine import detect_swings_vPine, calc_adaptive_thresholds
adap = calc_adaptive_thresholds(data)
ph, pl = detect_swings_vPine(data, left=5, right=3, min_swing_pct=0.5)
print(f"Pine swings (L=5,R=3): {len(ph)} highs, {len(pl)} lows")

# Check OB displacement directly
from v11.signals_vPine import detect_ob_vPine
obs = detect_ob_vPine(data, swings=(qh, ql), displacement_mult=1.3, adaptive=adap)

print(f"\nAll OBs detected: {len(obs)}")
if obs:
    ratios = [s.get('displacement_ratio', s.get('metadata', {}).get('displacement_ratio', 0)) for s in obs]
    ob_types = [s.get('ob_type', s.get('metadata', {}).get('ob_type', 'N/A')) for s in obs]
    print(f"  ob_type distribution: {dict((t, ob_types.count(t)) for t in set(ob_types))}")
    ratios_over_1 = [r for r in ratios if r >= 1.0]
    print(f"  w/ disp>=1.0: {len(ratios_over_1)}/{len(ratios)}")
    ratios_over_05 = [r for r in ratios if r >= 0.5]
    print(f"  w/ disp>=0.5: {len(ratios_over_05)}/{len(ratios)}")
    if ratios:
        print(f"  min: {min(ratios):.2f}, max: {max(ratios):.2f}, avg: {sum(ratios)/len(ratios):.2f}")
        print(f"  sample ratios: {[round(r,2) for r in ratios[:20]]}")
    
    for s in obs[:10]:
        print(f"  OB type={s['type']} idx={s['idx']} disp={s.get('displacement_ratio', 0):.2f} swing_idx={s.get('swing_idx', 'N/A')} ob_type={s.get('ob_type', 'N/A')} dir={s.get('direction','?')}")
else:
    print("No OBs detected - let's check swings used")
    print(f"  Swing highs: {[(i,round(p,2)) for i,p in qh[:5]]} ...")
    print(f"  Swing lows: {[(i,round(p,2)) for i,p in ql[:5]]} ...")
