# V19 Pine SMC 2026 vs Our Implementation — 6 Critical Gaps

Deep comparison between `/root/.hermes/scripts/v11/pine_refs/smc_2026.pine` (1247 lines) and V17/V18.

## Gap 1: OB — Displacement is HARD filter, not scoring

**Pine (line 453):** `if disp > (rng * ob_displacement_mult)` — hard gate
**V17 error:** Made displacement scoring-only, allowing OBs with tiny displacement
**V19 fix:** Restored hard filter. `ob_displacement_mult=0.6` for A-share (Pine default 1.5 for forex)

## Gap 2: OB — Swing source is pivothigh, not zigzag

**Pine:** `ta.pivothigh(high, 7, 7)` — structural swings with right confirmation
**V17 error:** Zigzag 2% produces ~29 swings, many NOT true HH/HL
**V19 fix:** LuxAlgo leg(20) — 18 true structure swings, 0 false

## Gap 3: OB Scanning Range

**Pine:** `for i = ob_swing_length+1 to ob_swing_length+ob_lookback`
**V17 bug:** Offset by 7 bars — scanning [swing-8, swing-20] instead of [swing-1, swing-10]
**V19 fix:** Range corrected to `sl_bar - i` where `i` starts at 7

## Gap 4: CHOCH/BOS Spacing

**Pine:** 20-bar minimum spacing between labels
**V17:** 15-bar spacing → too many noisy labels
**V19 fix:** LuxAlgo approach — check ALL uncrossed pivots, not just latest. Natural spacing from leg(20).

## Gap 5: FVG Pure Gap

**Pine:** `low > high[2]` — pure gap, no color/body checks
**V17 error:** Added 3-candle color filter → filtered real FVGs
**V19 fix:** Pure gap only. ATR*0.5 minimum size filter.

## Gap 6: OB Storage Timing

**Pine/LuxAlgo:** OB stored at CHOCH/BOS moment, finding extreme between pivot and crossover
**V17 error:** Pre-scanned OB at every swing point independently
**V19 fix:** Dual approach — SMC 2026 standalone + LuxAlgo at-CHOCH moment
