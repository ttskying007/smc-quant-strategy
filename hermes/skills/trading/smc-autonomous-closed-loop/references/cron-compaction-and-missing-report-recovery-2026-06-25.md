# Cron compaction + missing closed-loop report recovery (2026-06-25)

## Trigger
Use this when a scheduled SMC cron run is resumed after context compaction or wrapper timeout and the visible conversation contains only partial tool results / artifact paths, especially:

- `ops_latest.json` or `ops_logs/YYYYMMDD.json` exists or is being written.
- The dated closed-loop report under `/root/.hermes/smc_daily_closed_loop/YYYYMMDD_vXX_closed_loop.json` is missing.
- SMC child processes may still be alive.

## Recovery pattern

1. **Do not infer completion from missing report alone.** First inspect live processes for `smc_daily_closed_loop.py`, `smc_daily_ops.py`, selector scripts, and scanner children.
2. **If a child is alive, wait; do not launch duplicates.** Poll until it exits or until the dated ops log/report appears.
3. **After the child exits, verify artifacts independently:**
   - `/root/.hermes/smc_monitor/ops_logs/YYYYMMDD.json`
   - `/root/.hermes/smc_monitor/ops_latest.json`
   - `/root/.hermes/smc_daily_closed_loop/YYYYMMDD_vXX_closed_loop.json`
   - relevant selector outputs such as V90/V98/V99/V100/V101 active-pick/report files.
4. **If daily ops completed but the closed-loop report is still missing, run the real closed-loop wrapper once with Hermes-tracked background execution:**
   ```bash
   cd /root/.hermes/scripts/v25
   python3 smc_daily_closed_loop.py
   ```
   Start it as a tracked background process when it may exceed the per-call wait limit, then wait/poll the process rather than launching another copy.
5. **Verify final state before reporting:**
   - dated closed-loop report exists;
   - `ops_latest.json` has the current date/data_date;
   - no SMC closed-loop/ops/scanner child processes remain;
   - smoke `/api/summary`, `/api/autopsy/closed-loop`, and `/api/picks` from the report or by a separate API check.

## Pitfall

Do not run `python3 smc_daily_closed_loop.py --help` as a harmless help probe unless the script actually has argparse/help handling. This wrapper ignores argv and executes the full job, which can create an accidental second long-running closed-loop process.

## Reporting pattern

Report the concrete artifact paths and the actual state:

- closed-loop report path and timestamp;
- ops log/latest paths;
- daily scan/merge status;
- production/tradable vs watch-only counts;
- whether the latest data date produced zero new production entries vs a sync failure;
- smoke test results;
- whether any residual processes remain.

If `release_gate` is absent for the active version, say exactly that instead of implying it passed.
