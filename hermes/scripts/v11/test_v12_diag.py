#!/usr/bin/env python3
"""Diagnose why V12 OB detection produces 0 results on 688800 60min."""
import sys, json, os
sys.path.insert(0, '/root/.hermes/scripts/v11')

from signals_v12 import detect_swings_v12, detect_ob_v12, calc_adaptive_thresholds

# Load data
cache_dir = '/root/.hermes/kline_cache_60min'
with open(os.path.join(cache_dir, '688800_SH_60min_200.json')) as f:
    ohlcv = json.load(f)

n = len(ohlcv)
print(f"Data: {n} bars, range: {ohlcv[0]['o']}-{ohlcv[-1]['c']}")
print(f"First 5 bars: {[(b['o'],b['h'],b['l'],b['c'],b.get('v',0)) for b in ohlcv[:5]]}")

adaptive = calc_adaptive_thresholds(ohlcv)
print(f"Adaptive: {adaptive}")

# Get swings
swing_highs, swing_lows = detect_swings_v12(ohlcv, left=8, right=3, adaptive=adaptive)
print(f"\nSwing highs: {len(swing_highs)}")
for i, (idx, price) in enumerate(swing_highs[:10]):
    bar = ohlcv[idx]
    print(f"  SH[{i}] idx={idx} price={price:.2f} range={bar['h']-bar['l']:.2f} close={bar['c']:.2f}")

print(f"\nSwing lows: {len(swing_lows)}")
for i, (idx, price) in enumerate(swing_lows[:10]):
    bar = ohlcv[idx]
    print(f"  SL[{i}] idx={idx} price={price:.2f} range={bar['h']-bar['l']:.2f} close={bar['c']:.2f}")

# Manual OB scan from first few swing highs
print("\n=== MANUAL BACKWARD SCAN FROM SWING HIGHS ===")
displacement_mult = 1.3

for sh_idx, sh_price in swing_highs[:10]:
    print(f"\nSwing HIGH at idx={sh_idx}, price={sh_price:.2f}")
    print(f"  Bar: o={ohlcv[sh_idx]['o']:.2f} h={ohlcv[sh_idx]['h']:.2f} l={ohlcv[sh_idx]['l']:.2f} c={ohlcv[sh_idx]['c']:.2f}")

    # Scan backward
    found_ob = False
    for back_i in range(sh_idx - 1, max(sh_idx - 20, 4), -1):
        bar = ohlcv[back_i]
        is_bear = bar['c'] < bar['o']
        is_bull = bar['c'] > bar['o']
        body_pct = abs(bar['c'] - bar['o']) / max(bar['o'], 0.01) * 100

        if is_bull:
            continue

        if is_bear:
            # Found a bearish bar
            bar_range = bar['h'] - bar['l']
            displacement = sh_price - bar['l']
            dis_ratio = displacement / max(bar_range, 0.001)

            # Count bullish impulse bars between this bar and the swing high
            imp_count = 0
            for j in range(back_i + 1, sh_idx):
                if ohlcv[j]['c'] > ohlcv[j]['o']:
                    imp_count += 1
                else:
                    break

            print(f"  OB candidate at idx={back_i}: bear body={body_pct:.2f}% "
                  f"range={bar_range:.2f} disp={dis_ratio:.2f}x imp={imp_count}")

            if dis_ratio >= displacement_mult and imp_count >= 2 and body_pct >= 0.5:
                print(f"  ✓ VALID OB!")
                found_ob = True
                break
            else:
                reasons = []
                if dis_ratio < displacement_mult: reasons.append(f"disp<{displacement_mult}")
                if imp_count < 2: reasons.append("imp<2")
                if body_pct < 0.5: reasons.append("small_body")
                print(f"  ✗ Rejected: {', '.join(reasons)}")
                break  # One bearish bar found = end of scan

    if not found_ob:
        print(f"  No OB found scanning backward to idx={max(sh_idx-20, 4)}")
