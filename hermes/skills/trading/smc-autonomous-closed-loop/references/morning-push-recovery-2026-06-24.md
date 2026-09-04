# Morning push recovery example — 2026-06-24

## Why this matters
A 120s morning cron wrapper timeout can leave `smc_daily_ops.py` alive long after the wrapper exits. The right response is to treat it as a wrapper timeout, not a failed data pipeline, until the child process finishes or clearly stalls.

## Observed sequence

1. Morning context showed `smc_daily_ops.py` still running as an orphan/background child, first inside `v90_daily_full_market_scanner.py`, then `v98_reachable_5r_probability_gate.py`, then `v99_high_wr_production_gate.py`, then `v101_mtf_dna_combo_contract.py`.
2. Do not start another unchanged `smc_morning_push.py` while these children are alive.
3. Wait for the child process to finish naturally, then re-read `/root/.hermes/smc_monitor/ops_latest.json` rather than using the stale midnight copy.
4. Verify `/api/summary`, `/api/monitor/state`, `/api/picks`, and `/api/live-prices` on port 8890 after the child finishes.
5. Generate a local recovery report under `/root/.hermes/smc_push_reports/YYYYMMDD_HHMMSS_morning_push_cron_recovery.md` with all deduplicated OPEN holdings and all production active picks; do not truncate holdings.
6. Re-check `ps` and include whether any SMC child process remains.

## Concrete timings from this run

- Initial `ops_latest.json` was from `2026-06-24T00:16:36`; after waiting it updated to `2026-06-24T08:51:43`.
- Morning `smc_daily_ops.py` finished normally after the wrapper timeout.
- Kline refresh: `requested=4905`, `ok=4655`, `failed=250`, `returncode=0`.
- V90 selector: `returncode=0`, `duration_sec=211.6`.
- Shadow selector: `returncode=0`, `duration_sec=945.1`.
- API recovery snapshot: V175 frontend, 129 deduplicated OPEN holdings, 26 `/api/picks` rows, 3 live-guard-tradable rows.

## Pitfall
If the first `ops_latest.json` read is stale, do not report it as final. Wait for the still-running daily ops child, then re-read the file and rebuild the report from the fresh artifact plus live APIs.
