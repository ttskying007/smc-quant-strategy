# Daily closed-loop wrapper timeout and shadow-selector handling

## Trigger
Use this when the scheduled SMC closed-loop job reports a wrapper timeout such as:

```text
Script timed out after 120s: /root/.hermes/scripts/v25/smc_daily_closed_loop.py
```

## Lesson
A 120s wrapper timeout is usually a false failure. The daily closed-loop can legitimately take 7–15+ minutes because `smc_daily_ops.py` runs kline refresh, production selector, and shadow selectors/gates such as V99/V100/V101 and sometimes V98 reachable-5R probability scans.

Do **not** create a next Vxx or alter strategy code from this error alone.

## Required triage
1. Inspect whether a previous timed-out child is still running before starting another full loop:
   - Look for `smc_daily_closed_loop.py`, `smc_daily_ops.py`, `v90_daily_full_market_scanner.py`, `v98_reachable_5r_probability_gate.py`, `v99_high_wr_production_gate.py`, `v100_structural_net_gate.py`, `v101_mtf_dna_combo_contract.py`.
   - If an earlier process is still progressing, let it finish or kill only the duplicate retry you started; do not leave competing full-market scans.
2. Inspect current artifacts before diagnosing strategy failure:
   - `/root/.hermes/smc_monitor/ops_logs/YYYYMMDD.json`
   - `/root/.hermes/smc_monitor/ops_latest.json`
   - `/root/.hermes/smc_daily_closed_loop/YYYYMMDD_vXX_closed_loop.json`
   - active production report such as `/root/.hermes/smc_opt_v88_production_contract/v88_production_report.json`
3. If rerun is required, use a long timeout/background wait. Expect several minutes.
4. For a verification rerun where V98 already completed or is known to be the long pole, `SMC_DAILY_OPS_SKIP_V98=1` can shorten the rerun while still exercising V90/V99/V100/V101 and V88 contract application. Do not use this as the only production-quality run if V98 output is stale or missing.
5. Treat `pass: null` / `wr: null` from the wrapper as non-fatal if the active report stores gate fields in a version-specific structure. Verify the actual report’s `production_gate`, field audit, T+1 count, trade/pick counts, and API smoke instead.

## Verification checklist
- Confirm dated closed-loop json was written.
- Confirm ops log for today was written and includes `data_date`, selector return code, shadow selector return code, daily ingest status, and pick diagnostics.
- Confirm active production report has zero field missing, zero T+1 violations, and gate booleans are passing.
- Verify frontend/API endpoints: `/api/summary`, `/api/autopsy/closed-loop`, `/api/picks`, `/api/resonance`.
- Verify `/api/resonance` has zero empty/`None`/`null` `ctxSeq` values.

## Reporting guidance
Report the timeout as a wrapper timeout if the rerun/artifacts pass. State explicitly whether new production picks exist today; if `today_count=0` but `data_date` is current, explain that the latest data synced but no row passed the production gate.