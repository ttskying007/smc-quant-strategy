# V137 KEEP_WATCH Shadow Refinement Lesson

Use this reference when a future SMC lifecycle/shadow task has already proven UI/API dry-run safety and needs the next research-only refinement step.

## Boundary

`KEEP_WATCH` is not a buy signal. Refining `KEEP_WATCH` into strong/weak tiers is still shadow/research only unless a fresh executable entry/exit strategy loop is proven.

A valid shadow refinement payload must keep:

- `shadow_only=true`
- `tradable=false`
- `buy_enabled=false`
- `trade_action=NO_BUY`
- no realized outcome fields such as `pnl_pct`, `exit_date`, `exit_reason`, `hold_bars`

## V137 Pattern

After V136 dry-run mapping, audit only the `KEEP_WATCH` population and split it into non-tradable tiers.

Recommended analysis outputs:

- base `KEEP_WATCH` n / WR / avg PnL / recent WR;
- loser failure-tag taxonomy;
- market-state, event-type, reclaim-class, risk, zone-width, entry-chase buckets;
- single-rule and combo-rule scans;
- refined shadow payload with strong/weak watch tiers only.

## Failure Tags That Mattered In V137

For `KEEP_WATCH` losers, the dominant tags were:

- `NON_RECOVERY`
- `RECLAIM_CLASS_NOT_TT2`
- `BEAR_MIXED`
- `NO_STRICT_TAKEOVER_3`
- `NO_TRUE_TAKEOVER_2`
- elevated risk / entry chase in smaller buckets

The key interpretation: the issue was not UI/API plumbing. The signal layer still mixed non-recovery, mixed-bear-state, and non-strict-takeover samples.

## Useful Shadow Filters

V137 found the most useful quality variable was strict takeover:

- `v132_true_takeover_3_strict` was the strongest single variable.
- `v134_watch_strict_t0` helped, but alone was not enough.
- A conservative strong-shadow rule was:

```text
v134_watch_strict_t0
AND v132_true_takeover_2
AND v133_entry_chase_le_5
AND v133_risk_le_8
AND v133_reclaim_close_above_zone_le_8
```

This improved the shadow subset but still did not justify BUY promotion.

## Market-State Interpretation

In V137, `MIXED` was a major drag and should be downgraded or excluded in later research. `BEAR_RISK` performed better than expected, suggesting the lifecycle model behaved more like a post-bear-risk recovery/takeover observer than a trend-continuation entry model.

## Next-Step Gate

Do not continue threshold tuning after V137. The next proper step is to rebuild executable entry/exit semantics from the strong shadow tier:

1. Verify whether `true_takeover_3_strict` creates a real executable entry after confirmation.
2. Check entry chase and next-open executability.
3. Audit T+1 maximum adverse excursion after the candidate entry.
4. Decide whether `MIXED` is a hard reject.
5. Replace time-stop-only thinking with structural TP/SL semantics.

Only after this can a candidate move from shadow watch-tier research toward a production backtest.