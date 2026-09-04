# V185 daily closed-loop wrapper timeout recovery — 2026-06-30

## Situation

The scheduled wrapper timed out after 120s while running `v25/smc_daily_closed_loop.py`, but the underlying `smc_daily_ops.py` child continued and completed. Treat this as an operational timeout until proven otherwise, not a strategy failure.

## Recovery sequence that worked

1. Check for real children before rerunning:
   ```bash
   pgrep -af 'smc_daily_closed_loop|smc_daily_ops|v185_daily_rematerialize|v185|smc_unified' | grep -v pgrep || true
   ss -ltnp 'sport = :8890' || true
   ```
2. If `smc_daily_ops.py` is still alive, wait; do not launch a duplicate wrapper.
3. After children exit, inspect:
   - `/root/.hermes/smc_monitor/ops_logs/YYYYMMDD.json`
   - `/root/.hermes/smc_monitor/ops_latest.json`
   - `/root/.hermes/smc_audit/v185_daily_rematerialize_latest.json`
   - `/root/.hermes/smc_daily_closed_loop/YYYYMMDD_v185_closed_loop.json`
4. If ops/rematerialize succeeded but the dated closed-loop report is missing, run the real wrapper exactly once from `/root/.hermes/scripts`:
   ```bash
   python3 v25/smc_daily_closed_loop.py
   ```
   Successful output shape observed:
   ```json
   {"ok": true, "version": "V185", "out": "/root/.hermes/smc_daily_closed_loop/YYYYMMDD_v185_closed_loop.json", "pass": true, "wr": 86.23}
   ```
5. Verify no daily child remains; only `smc_unified.py` should remain on port 8890.

## Verification gates used

- Dated report exists and has `active_version=V185`; nested report has `version=V185` and decision `V185_DAILY_REMATERIALIZE_PASS`.
- `v185_daily_rematerialize_latest.json` has `ok=true`, `version=V185`.
- `ops_latest.json` has `analysis_summary.version=V185` and recent `generated_at`.
- Production artifacts under `/root/.hermes/smc_opt_v185_combined_production_candidate/` align:
  - `v185_trades.json`
  - `v185_active_picks.json`
  - `v185_picks.json`
  - `v185_report.json`
- API smoke:
  - `/api/summary` returns `version=V185` and V185 engine.
  - `/api/picks`, `/api/resonance`, and `/api/live-prices` expose the same 6 symbols.
  - `/api/resonance` has no empty/`None` `ctxSeq` or `signalText`.
  - `/api/kline_full?...ver=V185` returns `version=V185`.
  - `POST /api/reselect {"version":"V185"}` returns `ok=true`, `version=V185`.

## Pitfalls

- A process-wait loop that searches with `pgrep -af` can match its own shell command if the command text contains `smc_daily_ops.py`; filter carefully or match only exact `python3 smc_daily_ops.py`/`python3 v25/smc_daily_closed_loop.py` process argv. Otherwise the wait loop can falsely report one child forever.
- `/api/autopsy/closed-loop` may return `{}` for V185 because it loads a version-specific 90D review artifact, not the daily dated closed-loop report. Treat `{}` as a caveat, not a production failure, when the daily report, rematerialize artifact, summary, picks, resonance, live-prices, kline, and reselect gates all pass.
- Do not patch production artifacts just because `/api/autopsy/closed-loop` is empty; first distinguish daily closed-loop report verification from 90D autopsy artifact availability.
