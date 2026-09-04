#!/usr/bin/env python3
"""Quick test of signals_v12.py V2 OB detection on 688800 60min."""
import sys, json, os
sys.path.insert(0, '/root/.hermes/scripts/v11')

from signals_v12 import detect_all_signals_v12, detect_ob_v12, detect_swings_v12, calc_adaptive_thresholds
from signals_v11 import detect_all_signals_v11

cache_dir = '/root/.hermes/kline_cache_60min'
with open(os.path.join(cache_dir, '688800_SH_60min_200.json')) as f:
    ohlcv = json.load(f)

print(f"=== 688800 60min: {len(ohlcv)} bars ===")

# V11
v11 = detect_all_signals_v11(ohlcv)
v11_ob = [s for s in v11.get('all', []) if 'OB_Bull' in s.get('type', '')]

# V12
adaptive = calc_adaptive_thresholds(ohlcv)
v12 = detect_all_signals_v12(ohlcv, {'adaptive': adaptive, 'ob_displacement_mult': 1.3})
v12_ob = [s for s in v12.get('all', []) if 'OB_Bull' in s.get('type', '')]

print(f"\nV11 OB_Bull: {len(v11_ob)}")
print(f"V12 OB_Bull: {len(v12_ob)}")

print(f"\n--- V11 OB (idx, price, str, conf) ---")
for s in v11_ob:
    print(f"  idx={s['idx']:4d} price={s['price']:8.2f} str={s.get('strength',0):5.1f} conf={s.get('confidence',0):.3f}")

print(f"\n--- V12 OB (idx, price, str, conf, disp, imp, swing_idx) ---")
for s in v12_ob:
    print(f"  idx={s['idx']:4d} price={s['price']:8.2f} str={s.get('strength',0):5.1f} conf={s.get('confidence',0):.3f} "
          f"disp={s.get('displacement_ratio',0):.2f}x imp={s.get('impulse_bars',0)} swing_H={s.get('swing_high_idx',0)}")

# Full breakdown
print(f"\nV12 full breakdown:")
for k in ['FVG_Bull', 'FVG_Bear', 'OB_Bull', 'OB_Bear', 'Sweep', 'CHOCH_Bull', 'CHOCH_Bear', 'BOS_Bull', 'BOS_Bear']:
    c = len(v12.get(k, []))
    if c: print(f"  {k}: {c}")

sh = v12.get('swing_highs', [])
sl = v12.get('swing_lows', [])
print(f"\nV12 swings: {len(sh)} highs, {len(sl)} lows")

# Verify: V12 OB should be BEFORE swing high (backward scan)
print(f"\n=== VERIFICATION: OB before swing high? ===")
all_good = True
for s in v12_ob:
    sw_idx = s.get('swing_high_idx', 0)
    ob_idx = s['idx']
    ok = '✓' if sw_idx > ob_idx else '✗'
    if sw_idx <= ob_idx: all_good = False
    print(f"  OB={ob_idx} → SH={sw_idx} ({sw_idx-ob_idx} bars) {ok}")
print(f"  All correct: {all_good}")

# V12 only has correct-location OBs that are at real structural POIs
print(f"\n=== KEY METRIC: Average OB-SH gap ===")
diffs = [s.get('swing_high_idx', 0) - s['idx'] for s in v12_ob if s.get('swing_high_idx', 0) > s['idx']]
if diffs:
    print(f"  Avg gap: {sum(diffs)/len(diffs):.1f} bars (range {min(diffs)}-{max(diffs)})")
