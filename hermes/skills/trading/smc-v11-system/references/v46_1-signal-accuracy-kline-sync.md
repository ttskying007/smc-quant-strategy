# V46.1 SMC Signal Accuracy + K-line Display Sync Lessons

## Trigger
Use this reference when working on SMC signal correctness, Pine/LuxAlgo alignment, backtest/watchlist synchronization, or the `/kline` chart markers in `smc_unified.py`.

## Durable lessons from the session

1. **Do not treat good WR/RR as proof of signal correctness.**
   - The user rejects aggregate metrics as a substitute for mechanism verification.
   - For SMC work, verify the signal definition and the exact bars/prices used by the engine and UI.

2. **BOS/CHOCH/MSS inaccuracies are usually definition-layer bugs, not parameter bugs.**
   - Pine/LuxAlgo structure uses leg/pivot state, crossed flags, and trend bias.
   - Mixing equal-scale `swing_len == internal_len` collapses swing/internal structure and can make many labels appear while still being wrong.
   - MSS should not be a vague duplicate of CHOCH. Treat it as its own internal-shift/failed-continuation/liquidity-sweep warning layer, with explicit evidence fields.

3. **Keep Pine/LuxAlgo and SMC2026 layers separate.**
   - LuxAlgo-style BOS/CHOCH: leg/displayStructure, trend bias, crossed-level state.
   - SMC2026-style OB: swing-strength / OB swing detection length / minimum strength filter from the user’s screenshot.
   - Do not merge these into one generic detector and then call it “Pine aligned.”

4. **K-line chart labels are part of signal verification, not cosmetics.**
   - The chart must show full, readable structure labels so the user can inspect bars visually:
     - `BOS↑`, `BOS↓`
     - `CHOCH↑`, `CHOCH↓`
     - `MSS↑`, `MSS↓`
     - `LIQ`, `OB`, `FVG`, `BRK`
   - Avoid ambiguous abbreviations such as `CH` for CHOCH when debugging signal correctness.
   - Do not hide Sweep labels during manual verification; sweeps are key to liquidity-sequence validation.

5. **Front-end synchronization checklist after any signal-engine change**
   - Backtest trades updated.
   - Active watchlist/picks updated from true watchlist, not historical trades.
   - `/api/kline_full` signal source matches the active engine’s mixed source.
   - K-line markPoint labels and markArea zones display the same signal family used by the engine.
   - Highlight sequence shows actual chain bars: source event → zone → retest → confirmation.
   - Analysis/autopsy pages read the same files as the active version.

6. **Avoid stopping at “restart needed.”**
   - If code changed, immediately verify syntax and the API/chart output when safe.
   - If process restart is blocked by the environment guard, report that the code patch is applied but UI reload is pending; do not imply the browser has already updated.

## Suggested implementation anchors

- Main UI file: `/root/.hermes/scripts/smc_unified.py`
- K-line API: `_api_kline_full()`
- Chart marker function: `buildSignalPoints(af)`
- Active Lux/Pine mixed signal injection around `/api/kline_full` should keep:
  - LuxAlgo-derived: `structure`, `sweeps`, `obs`, `swing_structure`, `internal_structure`
  - Pine-like-derived: `fvgs`, `bprs`, `eqh_eql`, `liquidity_voids`, etc.

## Review posture
For this user, the correct order is:
1. Code-level signal definition trace.
2. Pine/LuxAlgo/SMC2026 semantic comparison.
3. Minimal implementation fix.
4. Full-market rerun.
5. Per-trade audit of source event, zone, retest, confirmation, entry price/time, exit price/time.
6. UI synchronization check on K-line, backtest, monitor/watchlist, analysis, and autopsy pages.
