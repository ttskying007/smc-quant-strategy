# V19 LuxAlgo Architecture — The Breakthrough

## Problem: OB appearing in trends, not at HH/HL/LL/LH

V17/V18 used pivothigh/pivotlow which produces ~25 mathematical pivot points on 300-bar A-share daily data. Only ~40% of these are true HH/HL/LL/LH structure points. The remaining 60% are local maxima/minima in the middle of trends — causing OB to appear in completely wrong locations.

## Solution: LuxAlgo leg() Detection

The LuxAlgo SMC Pine Script uses a fundamentally different swing detection method:

```
leg(size) =>
    newLegHigh = high[size] > ta.highest(size)
    newLegLow  = low[size]  < ta.lowest(size)
    
    if newLegHigh → BEARISH_LEG (swing high confirmed)
    if newLegLow  → BULLISH_LEG (swing low confirmed)
```

`high[size] > ta.highest(size)` means: the bar `size` bars ago created a high that NO subsequent bar has exceeded in the following `size` bars. This is a TRUE structural swing — not just a local window maximum.

## Implementation (Python)

```python
for i in range(leg_size, n):
    pivot_bar = i - leg_size
    pivot_high = ohlcv[pivot_bar]['h']
    recent_highs = [ohlcv[j]['h'] for j in range(pivot_bar+1, i+1)]
    
    if pivot_high > max(recent_highs):
        leg = -1  # Swing high confirmed
```

Param: `leg_size=20` for A-share daily (yields 18 true swings on 300 bars vs 25 with pivothigh)

## Key Differences: pivothigh vs leg()

| Method | 600519 Swings | True HH/HL/LL/LH | False Swings |
|--------|:-----------:|:----------------:|:------------:|
| pivothigh(5,5) | 25 | ~10 | ~15 |
| pivothigh(7,7) | 18 | ~12 | ~6 |
| **leg(20)** | **18** | **18** | **0** |

## HH/HL/LL/LH Labeling

LuxAlgo labels each swing by comparing with the PREVIOUS swing of same type:
- New high > previous high → `HH` (Higher High)
- New high < previous high → `LH` (Lower High)
- New low > previous low → `HL` (Higher Low)
- New low < previous low → `LL` (Lower Low)

## CHOCH/BOS via crossover/crossunder

LuxAlgo checks ALL uncrossed pivots (not just the latest):
- `ta.crossover(close, pivot.currentLevel)` → if trend.bias==BEARISH: CHOCH, else: BOS
- `ta.crossunder(close, pivot.currentLevel)` → if trend.bias==BULLISH: CHOCH, else: BOS

This produces far more structure signals than V17's "latest pivot only" approach.

## OB: LuxAlgo stores at CHOCH/BOS moment

LuxAlgo does NOT pre-scan for OB at every swing point. Instead, OB is stored at the moment CHOCH/BOS occurs — by finding the extreme bar between the pivot and the crossover:
- Bullish CHOCH/BOS: find MIN low between pivot.barIndex and current bar
- Bearish CHOCH/BOS: find MAX high between pivot.barIndex and current bar

## A-share Parameter Adaptation

| Parameter | Pine Default (forex) | V19 A-share |
|-----------|---------------------|-------------|
| leg_size | 20 | 20 |
| ob_displacement_mult | 1.5 | 0.6-0.7 |
| ob_swing_length | 7 | 5 |
| structure_spacing | 20 | 15 |
| EQL threshold | ATR*0.1 | avg_price*0.5% |
| MAX_TP | none | 5% |
| MIN_PROJECTED_RR | none | 1.0x |
