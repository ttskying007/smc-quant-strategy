# OB Detection Accuracy Debugging Methodology

## The Problem
User reports "OB在趋势中间, 而非高低点位" — OB signals appearing in the middle of trends rather than at swing points.

## Diagnostic Script
`python3 /tmp/diag_ob.py SYMBOL` — prints OB_Bull signals with distance to nearest swing points.

## Root Causes Found

### 1. SMC2026 scan window too wide
**Before**: `range(sw.bar_idx-1, max(0, sw.bar_idx-25), -1)` — scans 25 bars back
**After**: `range(sw.bar_idx-1, max(0, sw.bar_idx-5), -1)` — scans 5 bars back
**Effect**: Eliminates OBs associated with swings 25 bars away

### 2. Displacement filter too weak
**Before**: `displacement > avg_price * 0.003` (0.3% of price — negligible)
**After**: `displacement > ATR * 0.5` (Pine's 1.3x scaled for A股)
**Effect**: Only significant OBs survive

### 3. LuxAlgo scan window too wide
**Before**: `range(break_bar-1, max(0, break_bar-30), -1)` — 30 bars
**After**: `range(break_bar-1, max(0, break_bar-5), -1)` — 5 bars
**Added**: Swing proximity check `if break_bar - sw_bar > 8: continue`

### 4. Confidence upgrade
SMC2026 confidence: 0.65 → 0.80 (with strength=min(10, disp/ATR*3))
LuxAlgo strength: 6.0 → 7.0

## Verification
000712.SZ: 16 OB → 10 OB (6 false removed)
All remaining OB within 4 bars of nearest swing

## Key Insight
The OB should be the candle RIGHT BEFORE the swing, typically 1-3 bars away. If the scan window is too wide, it finds reverse candles much earlier that happen to match the criteria but are not actually at the swing turning point.
