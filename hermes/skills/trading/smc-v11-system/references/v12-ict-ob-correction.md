# V12 — Corrected ICT Order Block Detection (2026-05-11)

## The Core Bug in V11

V11's `detect_ob_v11()` scans **every candle** looking for "bearish bar + 2 bullish bars after" — this means any random bearish candle followed by 2 green candles gets marked as an OB. Result:

- OB positions are **2-5 bars offset** from the real structural POI
- Entry at wrong location → **1-bar holds** (entry/exit same bar or next bar)
- High WR/RR metrics but signals are at the **wrong price levels**

## V12 Fix: Backward Swing Scan

The correct ICT Order Block must be the **last opposite-direction candle BEFORE an impulsive move that reaches a swing point**.

### Bullish OB (buy signal)

```
Sequence:  ↓ OB (bearish) → ↑↑↑ impulse (bullish, 2+ bars) → swing HIGH
```

Scan backward from each **swing HIGH**:
1. **Phase 1 — Skip pullback**: Skip bearish bars immediately adjacent to the swing high (these are topping/pullback bars, not OBs)
2. **Phase 2 — Find impulse**: Find consecutive bullish bars going backward — this is the impulse that drove price to the high
3. **Phase 3 — OB**: The bearish bar BEFORE the impulse = real Bullish OB

**Displacement**: `swing_high_price - OB_low` must exceed `OB_range × 1.3`

### Bearish OB (sell signal)

```
Sequence:  ↑ OB (bullish) → ↓↓↓ impulse (bearish, 2+ bars) → swing LOW
```

Scan backward from each **swing LOW**, same 3-phase process. Displacement: `OB_high - swing_low_price`.

## Why V11's Direction Was Wrong

V11 scanned **every candle** for "is this bearish? are the next 2+ bars bullish?" — this produces OBs at ANY dip-and-bounce, regardless of structural significance. The correct approach restricts OBs to positions that:

1. Precede a real structural swing (confirmed by right-side confirmation)
2. Have sufficient displacement (price traveled far from OB to swing point)
3. Are the **last** opposite-direction bar before the impulse (not any random dip)

## Hybrid Mode for Coverage

Pure swing-backward scan produces ~30% of V11's OB count — too few for trading. Solution: **hybrid mode** with two passes:

1. **Primary** (swing_backward_v2): Swing-based backward scan — high quality, ~3 OBs/stock
2. **Secondary** (hybrid_forward): All-candle forward displacement scan — catches missed OBs with displacement >= 1.0x and proximity to swing high

## Parameter Reference

| Parameter | Swing-backward | Hybrid-forward | Notes |
|-----------|---------------|----------------|-------|
| displacement_mult | 1.3 | 0.8-1.0 | Hybrid relaxed since position is already filtered |
| min_impulse | 2 bars | 1 bar | Swing needs stronger confirmation |
| body_min | 0.15% | 0.15% | Same — displacement filter is the main gate |
| volume_required | Yes | Yes | Both passes need volume confirmation |
| lookback | 25 bars | 15 bars forward | |

## Source Code

`/root/.hermes/scripts/v11/signals_v12.py` — V12 complete signal engine with corrected OB, Pine-quality swings, and state machine structure.

`/root/.hermes/scripts/v11/test_v12_quick.py` — Verification script comparing V11 vs V12 OB detection.
