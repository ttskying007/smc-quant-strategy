# Compaction `继续` recovery for long SMC closed-loop runs

When a user says only `继续` after context compaction or provider 429 fallback during an SMC closed-loop / morning-push task, treat it as a request to resume the operational workflow, not to re-explain the old summary.

## Pattern

1. Load the SMC closed-loop skill and inspect current runtime state before acting.
   - Check for live `smc_daily_closed_loop.py`, `smc_daily_ops.py`, scanner, shadow selector, morning push, and `smc_unified.py` processes.
   - If an old child is still running, do **not** launch another copy; wait or monitor it.
2. Compare the latest dated report with `smc_monitor/ops_latest.json`.
   - A midnight closed-loop report can be stale after a later morning ops refresh.
   - Prefer the newest `generated_at` / mtime and explicitly distinguish older failed completeness gates from newer recovered ops output.
3. Smoke-test APIs before reporting status.
   - `/api/summary`
   - `/api/autopsy/closed-loop`
   - `/api/picks`
   - `/api/live-prices`
   - `/api/resonance`
4. For live guard counts, inspect both `/api/picks` and `/api/live-prices`.
   - They can differ because `/api/live-prices` includes existing holdings/context while `/api/picks` is the selection table.
   - Report source-specific counts; do not collapse them into one number.
5. If no SMC child process is running, first infer the unfinished work from the freshest scripts/artifacts before launching a broad closed-loop.
   - Example: if the latest edited scripts are `v177_exit_replay_research.py`, `v178_time_path_attribution.py`, and `v179_time_intraday_probe.py`, and `/root/.hermes/smc_audit/` lacks matching fresh `v177/v178/v179` artifact directories, run those scripts directly in sequence after `py_compile` instead of restarting daily ops.
   - Treat provider 429 or compaction as an interruption of the operational workflow, not evidence that the SMC process failed.
6. If a fresh long-running closed-loop is needed, start it as a tracked background process with completion notification.
   - Use `terminal(background=true, notify_on_complete=true)` for bounded long runs.
   - Poll/wait once if useful, but if it is still running, report the process/session id and current child stage; do not claim final completion.

## Reporting rule

Use a short operational status, not a long retrospective. Include:

- background session id / PID if a run is active;
- current child stage if known;
- stale vs fresh artifact distinction;
- API smoke status;
- source-specific live guard counts;
- explicit statement that the final closed-loop conclusion is pending until the background job exits.
