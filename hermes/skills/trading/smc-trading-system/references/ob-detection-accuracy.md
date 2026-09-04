# OB Detection Accuracy Issues

## Core Problem

User periodically reports "OB不准确" (Order Blocks are inaccurate). Root causes span detection parameters and signal evaluation logic.

## SMC2026 Detector: Scan Window Too Wide

```python
# signals_v22.py line 143
for j in range(sw.bar_idx-1, max(0,sw.bar_idx-25), -1):
```

Scans 25 bars backward from each swing. Finds first reverse-direction candle, but at 25 bars this can pick candles far from the swing.

**Example from 600519.SH**: OB_Bull at bar=238 has next swing L at bar=256 (18 bars away). This OB is too far from the swing to be a true Order Block.

**Pine reference**: SMC 2026 script scans backward but with a tighter displacement_mult=1.3 filter (candle range must be >=1.3x average range). Our code uses `displacement > avg_price * 0.003` which is 200x weaker.

## Displacement Filter Too Weak

```python
# Current (line 149): 0.3% of average price
if displacement > avg_price * 0.003:
```

For a stock at 1400, this requires displacement > 4.2 points — almost any price move passes.

**Pine equivalent**: `displacement > range_avg * 1.3` where range_avg is the true average range over 14 bars. At 1400 with ATR=30, Pine requires displacement > 39, our code requires > 4.2. ~10x difference.

## OB_Bull Between Two Swing Lows

When an OB_Bull sits between two consecutive swing lows (e.g., bar=262 with prev swing at 256 and next at 270), it's ambiguous which swing this OB belongs to. In SMC theory, the OB is the candle that CREATES the next swing — it must be immediately preceding it (1-3 bars max).

Fix: require `next_swing_distance <= 5` for OB_Bull signals.

## LuxAlgo OB: Low Confidence

LuxAlgo OBs all have confidence=0.65 (hardcoded at line 133). This is insufficient to distinguish quality. The SMC2026 OBs have confidence=0.75. When both detectors produce an OB at the same bar, the merged list keeps whichever was added first.

In practice, many LuxAlgo OBs mark non-significant range breaks that aren't true order blocks at structural swing points.

## Diagnostic Command

```bash
cd /root/.hermes/scripts && python3 /tmp/diag_ob.py SYMBOL
```

Shows each OB_Bull with its preceding/next swing distance.

## Applied Fix (2026-05-15)

Both OB detectors tightened in `signals_v22.py`:

### SMC2026 (`detect_ob_smc2026`)
- Scan window: **25 → 5 bars** (`range(sw.bar_idx-1, max(0,sw.bar_idx-5), -1)`)
- Displacement: **`avg_price*0.003` → `ATR*0.5`** (matches Pine's directional intent, ~0.5 ATR for A-share daily data)
- Confidence: **0.65 → 0.80**
- Strength: `disp/atr*3` (ATR-scaled, max 10.0)

### LuxAlgo (`detect_ob_luxalgo`)
- Scan window: **30 → 5 bars**
- Added swing proximity: skip if `break_bar - swing_bar > 8`
- Added ATR-based displacement: `> atr*0.3` for both bull/bear
- Kept confidence at 0.75

### Before/After on 000712.SZ
- OB count: 16 → 10 (removed 6 mid-trend false OBs)
- Bar=122 OB that was 85 bars from next swing → eliminated
- All remaining OBs ≤4 bars from their associated swing point
- Confidence all 0.80 (SMC2026, no more ambiguous 0.65 LuxAlgo OBs)

### Impact on V15 Backtest
- V13 trades: 621→510 (-18%), WR 94.5%→78.0% (honest data — fewer zones means remaining ones get breached more)
- V12 trades: 211→71 (-66%), WR 100%→95.8% (still excellent, tighter OB = fewer but higher quality trend entries)
- Combined: 832→581, WR 95.9%→80.2%
