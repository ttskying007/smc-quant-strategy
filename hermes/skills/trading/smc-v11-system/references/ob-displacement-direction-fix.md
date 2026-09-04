# OB Displacement Direction — Critical Bug & Fix

## The Bug

V16/V17 (before fix) used Pine's displacement formula:
```python
# Bull OB: bearish candle → swing LOW
disp = sl_price - bar['l']  # swing_low - OB_low
```

This is Pine's formula (`swing_low_ob - hist_low`), BUT it detects a DIFFERENT pattern than standard SMC:

**Pine pattern (capitulation)**: OB candle wicks BELOW the swing low → price bounces → swing forms ABOVE the OB's low.
- Requires: OB_low < swing_low → `disp = swing_low - OB_low` is POSITIVE
- This is the "capitulation wick reversal" — rare in A-share daily data
- Result: 0 OBs on most stocks (e.g., CMB had 0 OBs)

**Standard SMC pattern**: OB candle is ABOVE the swing → price drops from OB to swing → reversal.
- Requires: OB_low > swing_low → `disp = OB_low - swing_low` is POSITIVE  
- This is the "last sell candle before the drop" — common in A-share daily data
- Fix: `disp = bar['l'] - sl_price` (reversed)

## The Fix

```python
# Bull OB (standard SMC): OB is ABOVE the swing
disp = bar['l'] - sl_price  # OB_low - swing_low (positive when OB above swing)

# Bear OB (standard SMC): OB is BELOW the swing  
disp = sh_price - bar['h']  # swing_high - OB_high (positive when OB below swing)
```

## Impact (600036.SH / CMB)

Before fix: OB=0 (no OBs detected)
After fix: OB=24 (all at correct structural positions)

## Impact (4800 stocks, all versions)

OB entries became viable after this fix. Combined with consensus swings and quality filtering, OB entries contribute 38% of trades with improving quality.

## Lesson

Pine Script implementations sometimes encode market-specific patterns (capitulation detection) that don't match the standard SMC definition. When porting Pine to Python, verify the GEOMETRIC relationship (OB position relative to swing), not just the mathematical formula.
