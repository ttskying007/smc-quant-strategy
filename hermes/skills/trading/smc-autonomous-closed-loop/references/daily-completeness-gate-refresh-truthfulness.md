# Daily completeness gate: distinguish stale counters from real under-refresh

## Trigger
Use this when `v66_daily_completeness_gate.py` or the daily SMC closed-loop reports a kline completeness failure after `refresh_daily_750.py` / `smc_daily_ops.py`.

## Durable lesson
Do not automatically patch the gate to pass just because a previous session had a stale/inconsistent `failed` counter. First compare three independent sources:

1. `/root/.hermes/smc_monitor/kline_refresh_latest.json`
   - `requested`, `ok`, `failed`, `latest_counts`, `top_errors`
2. `/root/.hermes/smc_monitor/ops_latest.json`
   - `kline_refresh.summary`, `data_date`, selector/shadow return codes
3. Cache-derived truth from `kline_cache/*_daily_750.json`
   - count files by final `t`/`date`

## Interpretation rule

| Condition | Meaning | Action |
|---|---|---|
| `ok >= MIN_OK` and cache latest-date count/ratio pass, but `failed` is absurd or stale | telemetry inconsistency | It is valid to compute effective failed as `requested - max(ok, latest_count)` or cap `failed` by cache freshness. Record this explicitly. |
| `ok < MIN_OK`, cache latest-date count below threshold, and failed ratio above threshold | real under-refresh | Do **not** bypass or relax the gate. Report completeness as failed and do not claim closed-loop completion. |
| daily scan ran on latest market date but active picks are zero | valid no-signal outcome | Do not fail completeness just because there are no latest active picks; verify scan freshness instead. |

## Example threshold reading
If `requested=4905`, `ok=4017`, `failed=888`, latest cache date count `4005`, failed ratio `18.1%`, and thresholds require `ok>=4500`, latest count `>=4500`, failed ratio `<=8%`, then this is a genuine refresh failure. The correct conclusion is: daily ops/shadow may have completed, but the production data completeness gate is not closed.

## Reporting
Report gate status separately from strategy/shadow status:

- `daily_ops returncode`: execution health
- `refresh completeness`: data health
- `scan latest date`: selector freshness
- `active/tradable candidates`: production output
- `release/completeness gate`: release eligibility

Never convert an under-refreshed day into a passing release just to finish the loop.