# Daily closed-loop timeout and V88/V99 report-path lesson (2026-06-16)

## Trigger
Daily cron reported:

```text
Script timed out after 120s: /root/.hermes/scripts/v25/smc_daily_closed_loop.py
```

The failure was not a strategy crash. The outer cron/script timeout was too short for the modern V88/V90/V98/V99 daily workflow.

## Observed timings
A normal `smc_daily_ops.py` run can exceed 12 minutes before the top-level closed-loop script proceeds to the active engine and audits:

| Subprocess | Result | Duration |
|---|---:|---:|
| `refresh_daily_750.py --workers 20` | returncode 0 | ~113s |
| `v90_daily_full_market_scanner.py` | returncode 0 | ~199s |
| `v98_reachable_5r_probability_gate.py` + `v99_high_wr_production_gate.py` | returncode 0 | ~416s |

Total for ops alone: ~728s. A 120s timeout is guaranteed to create false failure reports; even 600s may be too short for the full top-level `smc_daily_closed_loop.py` because it runs ops plus V88 production contract/audits.

## Required handling
1. Treat `Script timed out after 120s` as an operational timeout first, not as evidence of release-gate failure.
2. Inspect `/root/.hermes/smc_monitor/ops_logs/YYYYMMDD.json` and `/root/.hermes/smc_monitor/ops_latest.json` before changing strategy code.
3. Check subprocess `returncode`, `duration_sec`, latest market date, field audits, T+1 violations, and active pick counts.
4. If subprocesses returned 0 and reports were written, report the timeout as a wrapper timeout and recommend increasing the cron/script timeout to at least 1800–2400s.
5. Do not create a next Vxx solely for timeout. Only create a next surgical version if metrics/gates actually regress after reading the generated reports.

## V88/V99 path pitfall
`smc_daily_closed_loop.py` historically looks for generic paths like:

```text
/root/.hermes/smc_opt_v88/v88_report.json
/root/.hermes/smc_audit/v88_release_gate.json
/root/.hermes/smc_audit/v88_closed_loop_90d_review.json
```

But current V88 production-contract artifacts live primarily under:

```text
/root/.hermes/smc_opt_v88_production_contract/
```

And V99 high-WR gate artifacts live under:

```text
/root/.hermes/smc_opt_v99_high_wr_gate/v99_report.json
/root/.hermes/smc_opt_v99_high_wr_gate/v99_active_picks.json
```

If the daily closed-loop JSON has empty `report`, `release_gate`, or `closed_loop_summary`, first suspect stale report paths before assuming the strategy produced no data.

## Verification checklist after a timeout report
Run/inspect:

```bash
ps -eo pid,ppid,etime,cmd | grep -E 'smc_daily_closed_loop|smc_daily_ops|v88_apply_production_contract|v88_.*audit|v88_release_gate' | grep -v grep || true
```

Then inspect:

```text
/root/.hermes/smc_monitor/ops_logs/YYYYMMDD.json
/root/.hermes/smc_monitor/ops_latest.json
/root/.hermes/smc_opt_v90_daily_full_market_scanner/v90_daily_scan_report.json
/root/.hermes/smc_opt_v99_high_wr_gate/v99_report.json
```

Key healthy signs:

- refresh/selector/shadow selector `returncode = 0`
- `latest_market_date` updated
- field audits all zero missing
- `t1_violations = 0`
- no new data-date picks means the production gate found no qualified candidates, not necessarily a bug
- frontend smoke endpoints and `POST /api/reselect` still work
