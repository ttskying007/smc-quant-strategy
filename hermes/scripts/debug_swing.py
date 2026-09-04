#!/usr/bin/env python3
"""Debug swing resonance"""
import json, logging, sys
logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, '/root/.hermes/scripts')

from v11.resonance_v11 import calc_swing_resonance
from v11.data_loader import load_cached_ohlcv

ohlcv = load_cached_ohlcv('000001.SZ', 'daily', 300)
print(f"Data: {len(ohlcv)} bars, last={ohlcv[-1].get('date','')} C={ohlcv[-1]['c']}")

# Check swing detection at each level
n = len(ohlcv)
for left, right, name in [(3,3,'micro'), (8,5,'meso'), (20,8,'macro'), (50,15,'mega')]:
    if n < left + right + 1:
        print(f"  {name}: not enough bars")
        continue
    recent = ohlcv[-min(left + right + 5, n):]
    center = len(recent) - right - 1
    if center < left or center + right >= len(recent):
        print(f"  {name}: center={center} out of range")
        continue
    center_bar = recent[center]
    is_high = all(recent[center]['h'] >= recent[j]['h'] for j in range(center - left, center + right + 1))
    is_low = all(recent[center]['l'] <= recent[j]['l'] for j in range(center - left, center + right + 1))
    print(f"  {name}: center_idx={n - len(recent) + center} is_high={is_high} is_low={is_low}")
    
    if is_high or is_low:
        after_bars = recent[center + 1:] if center + 1 < len(recent) else []
        if len(after_bars) >= 3:
            after_trend = 'up' if after_bars[-1]['c'] > after_bars[0]['c'] else 'down'
            print(f"    -> {after_trend}")
        else:
            print(f"    -> not enough after-bars ({len(after_bars)})")

score = calc_swing_resonance(ohlcv)
print(f"\nSwing score: {score}")
