# V98 Reachable 5R Probability Gate — High RR SL Autopsy Lesson

## Trigger
Use this reference when an SMC structural TP/SL engine keeps 5R+ targets but win rate drops and SL rate rises after switching from fixed RR exits to structural BSL/EQH/range-high targets.

## Core lesson
Do **not** lower TP back to 2R/3R just because 5R structural targets reduce win rate. First separate:

1. **Target space exists** — TP2_R >= 5, TP3_R >= 8.
2. **Target is reachable** — historical path quality supports price reaching 5R before true POI death.

V97 only required target space. V98 added a reachability/probability gate.

## Required autopsy before fixes
For all A-grade `SL_HIT` rows, replay the post-entry path and assign root buckets:

| Bucket | Meaning | Action |
|---|---|---|
| `POI_INVALIDATED_TRUE_ZONE_DEATH` | Close broke zone/SL; demand POI truly failed | Signal/POI quality issue; do not widen SL blindly |
| `SL_TOO_TIGHT_WICK_SWEEP_THEN_RECOVER` | Wick hit SL then recovered and later could reach target | Evaluate structural support depth; do not call it signal failure immediately |
| `PATH_STALLED_BEFORE_5R_REVERSAL` | Some MFE, but not enough for TP2 before reversal | Target/path reachability issue |
| `PATH_NO_UPSIDE_REACTION_TO_5R` | No meaningful upside response | Entry confirmation issue |
| `MIXED_PATH_FAILURE` | Ambiguous path | Keep for review, not production promotion |

Compute buckets over the full market, not samples.

## Empirical V97 finding
A structural 5R+ contract can have many valid-looking targets that are too far away:

| TP2_R bucket | Typical finding |
|---|---|
| 5~5.5R | Highest broad stability |
| 5.5~6.5R | Still usable |
| 6.5~8R | Starts degrading |
| 8~12R | Much lower reachability |
| >=12R | Often a bad bucket even if average PnL looks positive |

The durable conclusion is: **reachable 5R beats theoretical 12R+.**

## V98 gate pattern
A production A-grade gate should preserve high RR but add reachability:

```text
A_PRODUCTION =
    TP2_R >= 5
    TP3_R >= 8
    TP2_R < 12
    and one of:
        TP2_R in [5, 6.5)
        TP2_R < 8 and pd_zone == DEEP_DISCOUNT
        TP2_R < 8 and zone_width_pct < 0.8
```

Everything that still has structural targets but fails reachability should be demoted to `B_LIGHT_OR_OBSERVE` / `C_WATCH_ONLY`, not deleted.

## Verification checklist
After implementing a reachable-5R gate:

1. Full-market backtest, all cached stocks.
2. Compare old vs new:
   - A-grade trade count
   - WR
   - SL rate
   - average PnL
   - TP2 hits
   - SL hits
3. Confirm A-grade invariants:
   - no `tp2_rr < 5`
   - no `tp3_rr < 8`
   - no missing frontend fields
4. Sync dashboard/API in the same session:
   - `/api/picks`
   - `/api/live-prices`
   - current active picks source
   - daily ops runner
5. Do not claim complete until the frontend shows the new engine and field contract passes.

## Frontend/ops integration lesson
When promoting V98-like shadow selectors, update all of these together:

- selector script invoked by daily ops
- ops log paths/report keys
- dashboard priority source path
- cache mtime invalidation
- latest market date extraction (`latest_date` vs `latest_market_date`)
- active picks merge priority
- live-price field fallback verification

A common pitfall is generating the new backtest files but leaving the frontend on the previous V97/V91 source.