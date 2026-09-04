# V185 cron recovery: picks/live guard SL/TP parity (2026-07-02)

## Trigger
A 120s cron wrapper timeout for `v25/smc_daily_closed_loop.py` left the daily V185 closed-loop report missing even though `smc_daily_ops.py` had completed and `ops_latest.json` existed for the day.

## Recovery pattern
1. Check residual children first:
   ```bash
   ps -eo pid,ppid,etimes,cmd | grep -E 'smc_daily_closed_loop|smc_daily_ops' | grep -v grep || true
   ```
2. If no child remains and `/root/.hermes/smc_daily_closed_loop/YYYYMMDD_v185_closed_loop.json` is missing, run the real wrapper once from `/root/.hermes/scripts` with a long timeout:
   ```bash
   cd /root/.hermes/scripts
   python3 v25/smc_daily_closed_loop.py
   ```
3. Verify the wrapper output reports `ok=true`, `version=V185`, `pass=true`, and writes the dated report.
4. Verify `/root/.hermes/smc_audit/v185_daily_rematerialize_latest.json` has `ok=true`, `version=V185`, and current-day `generated_at`.

## Field-sync pitfall found
`/api/picks` and `/api/live-prices` can disagree if `/api/picks` live guard does not compute fallback SL/TP the same way as `/api/live-prices`.

Concrete failure:
- `/api/picks` classified `002401.SZ` as `WATCH_ONLY_PRICE_NOT_NEAR_ENTRY`.
- `/api/live-prices` classified the same symbol as `WATCH_ONLY_SL_ALREADY_HIT`.

Root cause:
- `_apply_current_price_live_guard()` used only flat `sl` / `sl_price` and `tp1` / `tp`.
- `_api_live_prices()` also derived `sl_price` from `risk_pct` / `sl_initial_pct` and `tp_price` from `tp_tiers[0].price`.

Allowed minimal fix under the closed-loop rule:
- Patch only the frontend/API sync helper, not production strategy artifacts.
- In `_apply_current_price_live_guard()`:
  - if flat SL is missing, derive `sl = entry * (1 - risk_pct / 100)` from `risk_pct` or `sl_initial_pct`;
  - if flat TP is missing, derive TP from first `tp_tiers[].price`.

## Required parity smoke after fix
Run API checks after restarting `smc_unified.py`:
- `/api/summary` reports `version=V185`.
- `/api/picks`, `/api/resonance`, and `/api/live-prices` have the same symbol set.
- `/api/resonance` has zero empty/`None`/`null` `ctxSeq` values.
- `/api/picks` and `/api/live-prices` have identical per-symbol `live_guard_status`.
- `POST /api/reselect {"version":"V185"}` returns `ok=true` and `version=V185`.
- `/api/kline_full?...ver=V185` returns `version=V185`.

## GitNexus note
Before patching `_apply_current_price_live_guard`, run:
```bash
gitnexus analyze --skip-git /root/.hermes/scripts   # if index is stale / folder has no .git
gitnexus impact _apply_current_price_live_guard --repo scripts
```
Expected blast radius for this helper is low and routes through `Handler._route` / API GET/POST paths. `gitnexus detect-changes` may fail outside a git repo because it relies on `git diff`; report that limitation rather than blocking verification.
