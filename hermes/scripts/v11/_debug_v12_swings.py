#!/usr/bin/env python3
"""Debug: why V12 swing-backward OB finds nothing."""
import json, sys, os
sys.path.insert(0, '/root/.hermes/scripts')
os.chdir('/root/.hermes/scripts/v11')

from signals_v12 import detect_swings_v12, detect_ob_v12, calc_adaptive_thresholds

with open('/root/.hermes/kline_cache_60min/600997_SH_60min_200.json') as f:
    ohlcv = json.load(f)
if not isinstance(ohlcv, list):
    ohlcv = ohlcv.get('data', ohlcv.get('klines', ohlcv))

print(f"Bars: {len(ohlcv)}, price range: {ohlcv[0]['c']:.2f} to {ohlcv[-1]['c']:.2f}")

adaptive = calc_adaptive_thresholds(ohlcv)
print(f"Adaptive: atr_pct={adaptive['atr_pct']:.2f}%, swing_min_pct={adaptive['swing_min_pct']:.2f}%")
print(f"ob_strength_min={adaptive['ob_strength_min']:.2f}, fvg_min_width={adaptive['fvg_min_width']:.5f}")

# Swings
swing_highs, swing_lows = detect_swings_v12(ohlcv)
print(f"\nV12 Swings: {len(swing_highs)} highs, {len(swing_lows)} lows")
for i, p in swing_highs[:8]:
    b = ohlcv[i]
    print(f"  High[{i:3d}] price={p:.3f} o={b['o']:.3f} h={b['h']:.3f} l={b['l']:.3f} c={b['c']:.3f}")
for i, p in swing_lows[:8]:
    b = ohlcv[i]
    print(f"  Low[{i:3d}] price={p:.3f} o={b['o']:.3f} h={b['h']:.3f} l={b['l']:.3f} c={b['c']:.3f}")

# Now test backward scan for each swing high
print("\n=== Testing backward scan from each Swing High ===")
n = len(ohlcv)
for sh_idx, sh_price in swing_highs[:8]:
    if sh_idx < 5: continue
    print(f"\n--- Swing High [{sh_idx}] price={sh_price:.3f} ---")
    # Show bars going backward
    for bi in range(sh_idx - 1, max(sh_idx - 12, 0), -1):
        b = ohlcv[bi]
        is_bear = b['c'] < b['o']
        is_bull = b['c'] > b['o']
        body_pct = abs(b['c'] - b['o']) / max(b['o'], 0.01) * 100
        br = b['h'] - b['l']
        dis = sh_price - b['l']
        dis_ratio = dis / max(br, 0.001)
        tag = ""
        if is_bear and dis_ratio >= 1.3:
            # Check if next bars are bullish
            impulse = 0
            for k in range(bi+1, min(bi+6, n)):
                if ohlcv[k]['c'] > ohlcv[k]['o']:
                    impulse += 1
                else:
                    break
            if impulse >= 2:
                tag = " *** POTENTIAL OB ***"
            else:
                tag = f" (impulse={impulse}b)"
        dir_label = 'BEAR' if is_bear else 'BULL' if is_bull else 'doji'
        print(f"    [{bi:3d}] dir={dir_label:4s} body={body_pct:.2f}% range={br:.3f} dis_ratio={dis_ratio:.2f}{tag}")
