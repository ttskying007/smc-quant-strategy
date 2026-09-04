# V27 SMC Audit & Sync Checklist

## Trigger
Use when users report that SMC signals are inaccurate, or when backtest, picks, chart markers, and analysis views disagree.

## What to verify
1. **Signal semantics first**
   - Confirm the definition of each signal, not just its count.
   - Check whether the implementation still matches the intended event order.

2. **Entry logic**
   - For zone retests, prefer wick-touch semantics over close-only semantics unless the strategy explicitly says otherwise.
   - Check that the entry condition does not accidentally use future zones or future-confirmed structure.

3. **Win/loss contract**
   - Do not assume a `won` field exists in historical trade data.
   - Treat `pnl_pct > 0` as the canonical fallback when `won` is missing.

4. **Cross-surface synchronization**
   - Backtest trades, pick lists, K-line markers, summary stats, and review pages must all read from the same semantic contract.
   - Any derived UI flag must be computed consistently in backend and frontend.

5. **Regression proof**
   - Re-run full scans after fixes.
   - Compare trade count, WR, exit distribution, and pick count before/after.
   - Verify that a syntax check or compile check still passes.

## Common failure patterns
- Close-only zone touches that miss wick retests.
- UI reading a field that only exists in newer trade exports.
- Picks and trades drifting because one layer adds compatibility fallbacks and another does not.
- Signal labels staying the same while the meaning changed.

## Recommended output format
When reporting an audit, use:
- scope
- findings
- root causes
- impact
- fixes
- verification
- remaining risks
