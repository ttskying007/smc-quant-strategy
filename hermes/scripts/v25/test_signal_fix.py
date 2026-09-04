#!/usr/bin/env python3
"""Test signal detection with new OB displacement filter."""
import json, sys
sys.path.insert(0, '/root/.hermes/scripts/v25')
from pathlib import Path
from smc_core_pine_like import detect_all_signals_pine_like

fp = Path('/root/.hermes/kline_cache/600519_SH_daily_300.json')
if not fp.exists():
    fp = Path('/root/.hermes/kline_cache/600519.SH_daily_300.json')
data = json.loads(fp.read_bytes())
print(f'Loaded {len(data)} bars')

res = detect_all_signals_pine_like(data)
sig = res['signals']
sm = res['summary']
print(f'Signals: FVG={sm["n_fvg"]} Sweep={sm["n_sweep"]} OB={sm["n_ob"]} '
      f'Struct={sm["n_swing_structure"]}+{sm["n_internal_structure"]} internal')
print(f'Swings: {sm["n_swing_highs"]}H/{sm["n_swing_lows"]}L')
print(f'EQH/EQL={sm["n_eqh_eql"]}, BPR={sm["n_bpr"]}, OTE={sm["n_ote"]}')

# Check OB details
obs = sig['obs']
if obs:
    low_disp = [ob for ob in obs if ob.get('displacement_ratio', 0) < 1.0]
    print(f'OBs with displacement < 1.0: {len(low_disp)}/{len(obs)}')
    print(f'Sample OBs (first 5):')
    for ob in obs[:5]:
        print(f'  bar={ob["index"]} dir={ob["direction"]} '
              f'zl={ob.get("zone_low",0):.2f} zh={ob.get("zone_high",0):.2f} '
              f'conf={ob["confidence"]} disp={ob.get("displacement_ratio","N/A")}')
else:
    print('No OBs found')

# Check sweeps
sweeps = sig['sweeps']
if sweeps:
    dirs = {'bull': 0, 'bear': 0}
    for sw in sweeps:
        dirs[sw['direction']] = dirs.get(sw['direction'], 0) + 1
    print(f'Sweeps: SSL={dirs["bull"]} BSL={dirs["bear"]} total={len(sweeps)}')
    
    # Check cooldown
    last_idx = {'bull': -999, 'bear': -999}
    violations = 0
    for sw in sweeps:
        d = sw['direction']
        if sw['index'] - last_idx[d] < 3:
            violations += 1
        last_idx[d] = sw['index']
    print(f'Sweep cooldown violations (< 3 bars): {violations}')
else:
    print('No sweeps found')

# Structure events
struct = sig['structure']
if struct:
    types = {}
    for ev in struct:
        t = ev.get('type', '?')
        types[t] = types.get(t, 0) + 1
    print(f'Structure events: {types}')
else:
    print('No structure events')
