# V17 Signal Detection — Key Lessons (2026-05-12)

## 1. OB Detection: First-Match, Not Displacement-First

**Root Cause**: Pine's `disp > rng * 1.5` is a quality filter, not a position filter. Using it as hard filter caused the engine to skip the correct OB candle (bar 25, ratio=0.34) and pick a weaker distant candle (bar 22, ratio=2.94).

**Fix**: OB = first matching candle closest to swing (scan from swing-1 backward, stop at first hit). Displacement ratio used only for strength scoring + proximity_bonus (closer to swing = higher quality).

**Code pattern**:
```python
for back_offset in range(1, ob_lookback + 1):  # swing-1 to swing-N
    bar = ohlcv[sl_bar - back_offset]
    if bar['c'] < bar['o']:  # first bearish candle = Bull OB
        # displacement for scoring only, NOT filtering
        disp = bar['l'] - sl_price
        strength = calc_strength(disp, rng) + proximity_bonus
        if strength >= min_strength: break  # weak OB → keep scanning
        # FOUND OB at back_offset bars before swing
```

## 2. Consensus Swing Detection (HH/HL/LL/LH)

**Root Cause**: Mathematical pivots (pivothigh/pivotlow) don't match human SMC structure. Single-lookback pivots include minor wiggles.

**Fix**: Multi-lookback consensus — detect swings at 6 lookback levels (5,8,10,12,15,20), keep only those appearing in ≥3/6 lookbacks.

**Result**: 600519 swings 25→21 (filtered 4 minor pivots). All downstream signals now at true structure points.

## 3. SWEEP Detection for A-Share Daily

**Root Cause**: wick_ratio=1.2 filtered valid sweeps where rejection was via close (not long wick). penetration=ATR×0.5 too strict.

**Fix**: 
- min_wick_ratio = 0.5 (allow close-based rejection)
- min_penetration = max(ATR×0.35, avg_price×0.003) (0.3% minimum)
- sweep_window = 25 bars (was 15)

## 4. MSS Tuning

**Fix**: min_spacing=25 (was 15), min_break_pct=0.5% (was 0.3%). Internal swings (3,3) remain for MSS.

## 5. Displacement Direction (Bull/Bear OB)

Standard SMC pattern, NOT Pine's capitulation pattern:
- Bull OB: bearish candle ABOVE swing low → `disp = OB_low - swing_low` (positive when OB above swing)
- Bear OB: bullish candle BELOW swing high → `disp = swing_high - OB_high` (positive when OB below swing)

## 6. CHOCH/BOS Minimum Break

Filter: break_pct < 0.3% → skip (prevents 0.09% noise breaks on minor level touches)

## Result Summary (4800 stocks, V5)

```
Trades: 58,658 | WR: 91.0% | P&L: +6.10%/trade
TP hit: 83.6% | SL hit: 9.0% | Trailing: 7.2%
SL sources: FVG=35% OB=41% EQL=8% CHOCH=6% SSL=5% BOS=5%
```
