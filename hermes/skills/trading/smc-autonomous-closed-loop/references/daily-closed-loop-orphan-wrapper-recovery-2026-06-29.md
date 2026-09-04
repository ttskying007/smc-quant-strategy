# Daily closed-loop orphan/wrapper recovery — 2026-06-29

## Trigger
Cron/context compaction preserved an in-progress task where the initial closed-loop wrapper had timed out, an orphan `smc_daily_ops.py` was still running under PID 1, and the dated V185 closed-loop report for the current day was missing.

## Durable workflow lesson

1. **Do not launch a duplicate while `smc_daily_ops.py` is alive.**
   - Inspect process state for `smc_daily_ops.py` and `smc_daily_closed_loop.py` first.
   - Wait for the orphan daily-ops child to finish before deciding whether to rerun the wrapper.

2. **If the orphan finishes but the dated closed-loop report is still missing, run the real wrapper once under Hermes tracking.**
   - Command used successfully:
     ```bash
     cd /root/.hermes/scripts/v25 && python3 smc_daily_closed_loop.py
     ```
   - Use a tracked background process / long wait rather than a short foreground timeout.
   - Success signature in this session: `ok=true`, `version=V185`, `pass=true`, `wr=86.23`, output `/root/.hermes/smc_daily_closed_loop/YYYYMMDD_v185_closed_loop.json`.

3. **Verify artifacts from both the dated report and ops logs.**
   - Required files:
     - `/root/.hermes/smc_daily_closed_loop/YYYYMMDD_v185_closed_loop.json`
     - `/root/.hermes/smc_monitor/ops_logs/YYYYMMDD.json`
     - `/root/.hermes/smc_monitor/ops_latest.json`
     - V185 production artifacts under `/root/.hermes/smc_opt_v185_combined_production_candidate/`.

4. **Treat a second refresh `ok=0` as suspicious, not automatically fatal.**
   - In this recovery, the rerun overwrote `ops_latest.json` with `kline_refresh ok=0 / failed=4905 / Expecting value`, but direct cache audit showed `4655` daily_750 cache files, `0` read errors, and `4637` files already at latest market date `20260626`.
   - Always audit actual cache rows using both `date` and `t` keys before declaring data completeness failure or rerunning refresh repeatedly.

5. **API smoke must include V185 manual rerun and live-guard parity.**
   - Verify:
     - `/api/summary` serves V185.
     - `/api/picks` returns rows with live guard fields (`status`, `live_guard_status`, `current_price`, `current_entry_gap_pct`, `buy_enabled`, `isTradableLive`).
     - `/api/live-prices` agrees on tradable/watch counts.
     - `/api/resonance` has no empty/None/null `ctxSeq`/signal text rows.
     - `/api/kline_full?...&ver=V185` returns V185 data.
     - `/backtest` loads.
     - `POST /api/reselect {"version":"V185"}` returns `ok=true` and `version=V185`.

6. **Only report completion after confirming no residual closed-loop/daily-ops processes.**
   - Final process check should show no `smc_daily_ops.py` or `smc_daily_closed_loop.py` still running.

## Report phrasing pattern

Include all of the following in the concise cron report:

- Orphan process was waited out; no duplicate launched.
- Wrapper rerun happened only because the dated report was missing.
- Dated report path, size/mtime if available, wrapper exit status and core metrics.
- Production gate metrics and T+1 status.
- Cache completeness caveat if `ops_latest.kline_refresh` shows a false failure but cache audit passes.
- API smoke results, especially `/api/reselect` and live-guard parity.
- Final residual process check.
