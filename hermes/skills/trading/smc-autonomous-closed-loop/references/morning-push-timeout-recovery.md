# Morning push timeout recovery

When `v25/smc_morning_push.py` times out under the cron wrapper, do not assume the morning report is unavailable and do not immediately launch repeated reruns.

## Observed pattern

- Cron wrapper may kill the job at 120s while `smc_morning_push.py` is still blocked in its preflight path.
- The morning push script can synchronously invoke `smc_daily_ops.py` before printing/sending the report; that child may run far longer than the wrapper timeout.
- Manual reruns with a longer timeout can also hang if an existing `smc_daily_ops.py` / closed-loop child is still alive.
- The useful recovery artifacts are often already available through:
  - `/root/.hermes/smc_monitor/ops_latest.json`
  - `http://127.0.0.1:8890/api/monitor/state`
  - `http://127.0.0.1:8890/api/picks`
  - `http://127.0.0.1:8890/api/live-prices`

## Recovery workflow

1. Check for still-running children before rerunning:
   ```bash
   ps -eo pid,ppid,etime,stat,cmd | grep -E 'smc_morning_push|smc_daily_ops|smc_closed_loop_ops|smc_unified.py' | grep -v grep || true
   ```
2. If a daily ops / closed-loop child is still alive, do **not** start another unchanged morning push. Treat the original timeout as a wrapper/preflight timeout until proven otherwise.
3. Build the recovery report from the latest completed artifacts and APIs:
   - `ops_latest.json`: generated_at, data_date, kline refresh summary, selector status.
   - `/api/monitor/state`: all `OPEN` positions and `NEXT_DAY_PENDING` positions.
   - `/api/picks`: production active picks only if `is_active_pick` and `pick_scope` is one of `ACTIVE_CANDIDATE`, `ACTIVE_ENTRY`, `POST_ENTRY_MONITOR`, `NEAR_ZONE_WATCH`; otherwise report scope/state counts such as `WATCH_ONLY`.
   - `/api/live-prices`: enrich current price / PnL when available, but keep holdings in the report even if live prices are blank.
4. De-duplicate open holdings by `(symbol, pick_date or entry_date, entry_price, sl_price, created_at)` before reporting.
5. Save the recovery report under `/root/.hermes/smc_push_reports/YYYYMMDD_HHMMSS_morning_push_cron_recovery.md`.
6. In cron context, if the prompt says final response is auto-delivered, do not call `send_message`; put the complete report in the final response.

## Report content checklist

- State that the original data-collection script timed out and include the timeout value.
- State whether a manual long-timeout rerun was attempted and whether it also timed out.
- Include `ops_latest` generation/data date.
- Include kline refresh requested/ok/failed counts and selector return code/duration.
- Include counts: OPEN, NEXT_DAY_PENDING, `/api/picks`, production active picks.
- Include **all** deduplicated OPEN holdings with pick date, buy date, symbol, cost, current price if available, PnL if available, SL, TP, status, and signal. Do not truncate to "first 40" or a sample in the saved recovery report; the user expects the full auditable holding table.
- Include all production active picks; if none, explicitly report the `/api/picks` scope/state distribution so the absence is explainable. When `/api/picks` returns a list of WATCH_ONLY rows, count the returned rows and scopes; do not summarize it as total 0 just because there are zero production/tradable rows.
- Include failures/risks, especially partial kline refresh and upstream empty/JSON parse errors.
- Before finalizing, re-check `ps` for `smc_daily_ops` / closed-loop children and state whether they are still running or have ended; this distinguishes a wrapper timeout from an actual pipeline stall.
