# V185 refresh timeout with rematerialize pass — 2026-07-04

## Trigger
Use this when the V185 daily closed-loop wrapper exits `ok=true` / `pass=true`, but the embedded `smc_daily_ops.py` step has `returncode=1` because `refresh_daily_750.py --workers 20` hit its 900s subprocess timeout.

## Observed pattern
- Real wrapper was run as a Hermes-tracked background process from `/root/.hermes/scripts`:
  - `PYTHONUNBUFFERED=1 python3 v25/smc_daily_closed_loop.py`
- It completed successfully after waiting beyond short cron/tool timeouts and emitted:
  - `{"ok": true, "version": "V185", "out": "/root/.hermes/smc_daily_closed_loop/20260704_v185_closed_loop.json", "pass": true, "wr": 86.23}`
- The dated closed-loop report contained:
  - `active_version=V185`
  - `report.version=V185`
  - `decision=V185_DAILY_REMATERIALIZE_PASS`
  - V185 production gate booleans all true
  - `production_write=true`, `frontend_write=true`, `watchlist_write=true`, `cron_productionized=true`
- `smc_daily_ops.py` still recorded failure only because refresh timed out:
  - `subprocess.TimeoutExpired: ... refresh_daily_750.py --workers 20 ... timed out after 900 seconds`
- Cache audit showed actual coverage was good enough for the latest trading date:
  - 4655 `*_daily_750.json` cache files
  - 4637 files latest at `20260703`
  - 0 empty/bad files

## Verification checklist
Before declaring success with caveat, verify all of the following:

1. Wait for the real wrapper to exit; do not report while `smc_daily_closed_loop.py`, `smc_daily_ops.py`, or `refresh_daily_750.py` children remain alive.
2. Read `/root/.hermes/smc_daily_closed_loop/YYYYMMDD_v185_closed_loop.json` and confirm:
   - top-level `active_version == V185`
   - nested `report.version == V185`
   - nested decision is `V185_DAILY_REMATERIALIZE_PASS`
   - gate booleans are all true
3. Confirm fresh V185 rematerialization artifacts:
   - `/root/.hermes/smc_audit/v185_daily_rematerialize_latest.json`
   - `/root/.hermes/smc_audit/v185_daily_rematerialize_YYYYMMDD_HHMMSS.json`
   - `v185_active_picks.json`, `v185_picks.json`, `v185_report.json` refreshed
4. Audit actual kline cache coverage by reading both `date` and `t` bar keys; do not rely solely on the refresh subprocess return code.
5. Smoke live frontend/API:
   - `/api/summary` reports V185
   - `/api/picks` returns active rows
   - `/api/live-prices` returns a dict whose live rows are under `picks` (not only `prices`/`data`/`items`)
   - `/api/resonance` non-empty
   - `/api/kline_full?...ver=V185` returns payload
   - `POST /api/reselect {"version":"V185"}` returns `ok=true`, `version=V185`
6. Compare `/api/picks` and `/api/live-prices["picks"]` by symbol for live-guard parity; require zero mismatches.
7. Run `py_compile` for `smc_unified.py` and `v25/v185_*.py` if any verification touched code paths or before final reporting.

## Reporting rule
If rematerialize, gates, cache coverage, API smoke, reselect, and picks/live-prices parity all pass, report the run as successful with an explicit caveat that `smc_daily_ops.py` failed due to refresh timeout. Do **not** mutate production artifacts or strategy code for this pattern.

If cache coverage is genuinely under threshold or API/parity checks fail, do not claim closed-loop completion; diagnose the failing layer first.