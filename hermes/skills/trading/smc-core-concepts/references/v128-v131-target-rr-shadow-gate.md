# V128→V131 Target-RR Shadow Gate Lesson

Use when an SMC scanner/shadow candidate set looks profitable under semantic/time-stop exits, or when a high-WR candidate pool still has poor expectancy.

## Durable lesson

A candidate generator can look profitable if winners are allowed to drift to a fixed time-stop while losers exit on structure damage. Before promoting any scanner/shadow layer, re-evaluate every candidate with a non-leaking, pre-entry target model.

## Required diagnostic sequence

1. Preserve production identity first: write only shadow/audit files until the new layer passes full stability gates. Do not alter picks/API/frontend/watchlist during the diagnostic.
2. Re-score the same candidate rows under a realistic target-exit model:
   - target = nearest pre-entry BSL/prior high above entry, known strictly before `entry_idx`; fallback to fixed 1.5R only when no pre-entry BSL exists.
   - T+1 strict: begin exit evaluation at the bar after entry; same-day exit is a hard violation.
   - exit ordering: target hit first, then POI close-break / structure damage, then time-stop.
3. Compare original semantic/time-stop exit vs target-exit metrics:
   - If original Avg is positive but target-exit Avg is negative, treat original as a time-stop drift artifact.
   - Report win average and loss average; high WR is not enough when average loss dwarfs average win.
4. Bucket by target RR before changing signal labels:
   - Very low pre-entry target RR (e.g. <0.4R) often creates “small win / large loss” expectancy even at ~78–80% WR.
   - Validate candidate gates such as `0.6 <= pre_entry_target_rr <= 1.2` before promoting.
5. Only then test stricter semantic gates such as source, reclaim strength, zone width, market state, and chase distance.
6. Full stability audit is mandatory: by year, by month, recent45, source, market_state, exit_reason, and T+1 violations.

## V128→V131 observed pattern

- V128 parallel source split (`DEMAND_OB`, `FVG_Demand`, `OB+FVG`) was structurally useful but not enough for production.
- V128 original no-target exit showed positive Avg because winners often reached `TIME_STOP_NO_SEMANTIC_EXIT`; this was not a valid production target model.
- Re-evaluating with pre-entry BSL / 1.5R targets turned the all-candidate pool into high-WR but negative-expectancy behavior: small winners, large POI-break losses.
- The real root cause was target/risk geometry, not merely POI source labeling.
- Strict research gates improved quality but reduced sample size; small positive subsets should remain research-only until yearly/monthly coverage is sufficient.

## V132 reclaim takeover classifier observed pattern

- V132 separated `FVG_Demand` reclaim into `TRUE_TAKEOVER_*`, `FAILED_RECLAIM_*`, `UNCLEAR_RECLAIM`, and isolated `RECOVERY_SEPARATE` using only ex-ante reclaim/post-reclaim candle fields.
- `RECOVERY_SEPARATE` remained structurally weak (`n=1637`, `WR=23.82%`, `Avg=-1.8995%`, hard-exit `69.09%`) and must not be mixed into takeover gates.
- `TRUE_TAKEOVER_3_STRICT` materially improved the existing baseline outcome (`n=439`, `WR=67.43%`, `Avg=8.8938%`, hard-exit `25.97%`; recent45 `n=23`, `WR=78.26%`) but a delayed confirmation entry collapsed execution quality (`n=439`, `WR=44.19%`, `Avg=1.1917%`). Treat this as a signal-quality label, not a standalone delayed-entry production rule.
- `FAILED_RECLAIM_1/3` buckets confirmed the failure mode: high loss/hard-exit rates and near-zero/negative expectancy. Use them for downgrade/reject diagnostics.
- Decision: `V132_FVG_RECLAIM_TAKEOVER_SHADOW_BACKTEST_DONE_NO_PRODUCTION_CHANGE`. It is shadow/backtest only until later scanner-time contract, source isolation, and frontend/watchlist routing are verified.

## Promotion rule

Do not promote a scanner layer when:

- target-exit Avg is negative on the full candidate pool;
- one or more years with meaningful sample size are negative;
- recent45 coverage is tiny;
- the only strong subset has fewer than a robust multi-year sample.

Prefer the next iteration to rebuild/extend the candidate generator around pre-entry target quality rather than patch production with a narrow filter.
