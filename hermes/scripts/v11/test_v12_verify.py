#!/usr/bin/env python3
"""Verify V12 hybrid OBs are positioned correctly."""
import sys, json, os
sys.path.insert(0, '/root/.hermes/scripts/v11')
from signals_v12 import detect_all_signals_v12, calc_adaptive_thresholds

cache_dir = '/root/.hermes/kline_cache_60min'

# Test 688800
with open(os.path.join(cache_dir, '688800_SH_60min_200.json')) as f:
    ohlcv = json.load(f)

adaptive = calc_adaptive_thresholds(ohlcv)
v12 = detect_all_signals_v12(ohlcv, {'adaptive': adaptive, 'ob_displacement_mult': 1.3})

ob_bull = [s for s in v12.get('all', []) if 'OB_Bull' in s.get('type', '')]

print(f"=== 688800 60min: {len(ob_bull)} V12 Bullish OBs ===\n")

swing_highs = v12.get('swing_highs', [])
sh_set = {s['idx']: s['price'] for s in swing_highs}

# Check each OB
for s in ob_bull:
    method = s.get('ob_method', 'unknown')
    ob_idx = s['idx']
    disp = s.get('displacement_ratio', 0)
    imp = s.get('impulse_bars', 0)
    obj_price = s['price']
    
    # Find nearest forward swing high
    near_sh = None
    for sh in swing_highs:
        if sh['idx'] > ob_idx and sh['idx'] <= ob_idx + 25:
            near_sh = sh
            break
    
    pos_str = f"→ SH at {near_sh['idx']} ({near_sh['idx']-ob_idx}b)" if near_sh else "→ NO SH within 25b"
    
    print(f"  OB={ob_idx:3d} price={obj_price:7.2f} disp={disp:.2f}x imp={imp} method={method:16s} {pos_str}")

print(f"\n=== Verify OB-SH gaps ===")
valid = [s for s in ob_bull if s.get('swing_high_idx', 0) > s['idx']]
hybrid = [s for s in ob_bull if s.get('ob_method') == 'hybrid_forward']
swing_ob = [s for s in ob_bull if s.get('ob_method') == 'swing_backward_v2']

print(f"  Total: {len(ob_bull)}, Swing-backward: {len(swing_ob)}, Hybrid-forward: {len(hybrid)}")
if swing_ob:
    gaps = [s['swing_high_idx'] - s['idx'] for s in swing_ob]
    print(f"  Swing-backward avg OB-SH gap: {sum(gaps)/len(gaps):.1f} bars")

# Check hybrid OBs: what swing high do they correspond to?
print(f"\nHybrid OB positioning check:")
for s in hybrid:
    ob_idx = s['idx']
    near_sh = None
    for sh in swing_highs:
        if sh['idx'] > ob_idx and sh['idx'] <= ob_idx + 20:
            near_sh = sh
            break
    if near_sh:
        gap = near_sh['idx'] - ob_idx
        print(f"  OB={ob_idx} → SH={near_sh['idx']} ({gap}b gap) ✓" if gap >= 1 else f"  OB={ob_idx} → SH={near_sh['idx']} ({gap}b gap)")
    else:
        print(f"  OB={ob_idx} → NO SH within 20b")
