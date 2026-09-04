# Daily closed-loop compaction / timeout recovery and manual report

## When this applies

Use this when the Hermes cron/chat context compacts, the wrapper appears to have stopped early, or `smc_daily_closed_loop.py` does not leave a dated file under `/root/.hermes/smc_daily_closed_loop/`, but child SMC processes may still be running.

## Recovery sequence

1. **Do not immediately rerun the whole pipeline.** First check whether child processes are still alive:
   - `smc_daily_ops.py`
   - `v90_daily_full_market_scanner.py`
   - `v98_reachable_5r_probability_gate.py`
   - `v99_high_wr_production_gate.py`
   - `v100_structural_net_gate.py`
   - `v101_mtf_dna_combo_contract.py`
2. If a child is alive, wait for it to finish rather than launching a duplicate refresh/selector pass. The long pole can be V98 or V101; 10–15 minutes is normal.
3. After children exit, inspect `/root/.hermes/smc_monitor/ops_logs/YYYYMMDD.json` and `/root/.hermes/smc_monitor/ops_latest.json`.
4. Regenerate the active production contract only if needed and cheap enough for the active version, e.g. for V88:
   - `python3 /root/.hermes/scripts/v25/v88_apply_production_contract.py`
5. Run smoke checks against the already-running frontend APIs:
   - `/api/summary`
   - `/api/autopsy/closed-loop`
   - `/api/picks`
   - `/api/live-prices`
6. If the wrapper did not create a dated report, synthesize one under `/root/.hermes/smc_daily_closed_loop/YYYYMMDD_vXX_closed_loop.json` from:
   - `ops_logs/YYYYMMDD.json`
   - active production report, e.g. `smc_opt_v88_production_contract/v88_production_report.json`
   - API smoke results
   - a daily completeness gate evaluation

## Completeness gate reminder

Do not report closed-loop production success if the data refresh is incomplete, even when selector and shadow selectors exit 0. Keep daily scan/shadow rows validation/watch-only when any of these fail:

- requested < 4800
- ok < 4500
- failed ratio > 8%
- latest-date cache count < 4500
- latest-date ratio < 94%
- ops data date does not match cache latest date
- daily scan did not run for latest market date

## Report wording

If production contract metrics pass but completeness fails, the decision should be explicit:

> NO_PROMOTION_OR_NEW_VERSION: production contract regenerated and ops/shadow selectors completed, but current daily completeness gate fails. Daily scan/shadow rows remain validation/watch-only unless production gate and completeness requirements pass.

This avoids falsely treating a successful selector run as a production promotion signal when market data coverage is insufficient.
