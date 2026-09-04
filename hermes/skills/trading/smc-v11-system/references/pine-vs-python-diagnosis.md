# Pine-vs-Python 赋值语义诊断

2026-05-12. The most common bug when translating Pine Script to Python is NOT algorithmic — it's assignment semantics.

## Pine `:=` vs Python `=`

Pine: `last_swing_high := swing_high_ms` → DIRECT OVERWRITE with latest value.
Python (WRONG): `if sw['price'] > last_swing_high: last_swing_high = sw['price']` → TRACKS MAXIMUM.
Python (RIGHT): `last_swing_high = sw['price']` → DIRECT OVERWRITE (Pine exact).

Bug manifestation: CHOCH/BOS detection requires breaking the NEWEST swing, not the all-time-high. Using max/min tracking made break conditions nearly impossible to satisfy.

## Pine `ta.pivothigh(N, N)` symmetric confirmation

Pine: `ta.pivothigh(high, 5, 5)` — left=5 AND right=5 (symmetric).
V16 (WRONG): `detect_swings(left=5, right=2)` — always asymmetric.
V17 (FIXED): `detect_swings(left=5, right=5)` — symmetric, Pine exact.

The right=2 confirmation was too loose — produced swings at minor wiggles instead of structural pivots.

## 300-bar vs Full-Chart Density

Pine runs on thousands of bars. Our daily data is 300 bars.
- EQL: ATR200×0.1 threshold designed for thousands of pivot points fails on 300 bars.
- Fix: Three-mode fallback (consecutive → nearby → wide) with progressively relaxed thresholds.

## Diagnosis Checklist

When comparing Pine output to Python output:
1. Check swing detection symmetry (left==right?)
2. Check variable update semantics (overwrite vs max/min?)
3. Check bar-count-dependent thresholds (ATR period, spacing, density)
4. Trace single stock 200-bar: print every swing, every OB, every break
