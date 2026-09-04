# V46 Post-Mortem: Why Retest Entry + Adaptive Trailing Failed

## Summary

V46 attempted 3 simultaneous changes to fix V45's OB false-positive problem:
1. Reversal OB detection (is_reversal_ob)
2. Price retest before entry (find_retest_entry)
3. Adaptive ATR-based trailing (replacing V38.4 3-profile)

Results (200 stocks): WR=81.5%, RR=2.21x — massive regression from V45 baseline (WR=96.2%, RR=8.94x).

## Root Cause Analysis

### Fix 1: Reversal OB — CORRECT ✅
is_reversal_ob() eliminated 54% of uptrend-pullback false OB signals. This was adopted into V463 (Strategy C) and proved valuable.

### Fix 2: Retest Entry — FAILED ❌
Expected: Price retests signal zone → better entry → fewer losses
Actual: Retest window finds activation in 1-2 bars, but misses the immediate entry that captured the move

A-share daily data analysis:
- 99.6% of profitable trades exit within 1 bar
- avg hold = 1.0 bars (V463) → retest adds 0-1 bar delay
- Retest entry WR=84.6% vs immediate entry WR=96.2% (same signal quality!)
- Cause: If price never retests = missed trade. If price retests = it already printed profit
- In A-stock daily, "retest" == "re-entry after profit has run" — no edge

### Fix 3: Adaptive Trailing — FAILED ❌
Expected: ATR-based thresholds adapt to volatility → better RR
Actual: V38.4 3-profile trailing already optimized for 1-bar holds

Why V38.4 is optimal:
- BE at 0.2% = immediate protection from daily gap reversal
- Lock at 1.0%/1.5%/3.0%/6.0% = captures swings without over-locking
- Loose/bear/tight profiles correctly handle TP present/absent scenarios
- V38.4 survived 67,002 trade validation (V38 full 4800 scan)

Adaptive trailing's flaw: ATR-based thresholds are TOO GENEROUS for profitable trades that exit in 1 bar. The tight lock of V38.4 is exactly what protects profits in 1-bar exits.

## Lesson: Single-Variable Testing is Critical

V46's fatal flaw was changing 3 variables simultaneously. When metrics regressed, it was impossible to tell which change caused the damage. The V463 approach (reapply one fix at a time) correctly identified that:
1. Reversal OB → improvement (V45+rev → WR=98.0%)
2. Retest entry → harmful
3. Adaptive trailing → harmful

## Files

- /root/.hermes/scripts/v11/v46_engine.py — V46 engine (882 lines, archived)
- /root/.hermes/smc_opt_v46/v46_full.json — Full 4800: WR=81.4%, RR=2.44x
