# V88 daily automation contract

## Trigger
Use this when checking or repairing the daily SMC production pipeline: data update, scanner selection, V88 backtest/contract regeneration, analysis, review/autopsy, frontend/API sync, and morning push.

## Required end-to-end chain
A valid daily V88 run must cover all of these, in order:

1. **K-line refresh** — run `refresh_daily_750.py` and verify the latest market date from `smc_monitor/kline_refresh_latest.json`.
2. **Production scanner** — run `v90_daily_full_market_scanner.py`.
3. **Shadow/current-month scanner** — run `v91_shadow_zone_entry_scanner.py`; do not rely on V90 alone because V91 carries the active zone-entry/current-candidate layer.
4. **V88 production contract/backtest** — for ACTIVE_VERSION=V88, the executable is `v88_apply_production_contract.py`, not `v88_engine.py`.
5. **Ops snapshot** — write/update `smc_monitor/ops_latest.json` with V90 + V91 files, data date, latest pick date, active counts, review/analysis summaries, and file mtimes.
6. **Frontend smoke** — verify `/api/summary`, `/api/picks`, `/api/live-prices`, and `/api/autopsy/closed-loop` return without traceback and match the current data date.
7. **Field contract** — assert 0 blanks for pick/join date, zone type/range, cost line, volatility, entry, SL, TP.

## Scheduler verification checklist
Do not stop after seeing a cron entry. Verify the scheduler is actually firing the same script/version being inspected.

| Check | Command / source | Pass condition |
|---|---|---|
| Hermes cron exists | `hermes cron list --all` | SMC jobs listed |
| Hermes scheduler active | `hermes cron status` | not `Gateway is not running` |
| System crontab fallback | `crontab -l` | direct V88 pipeline entries exist if Hermes cron is not reliable |
| Last run freshness | `smc_monitor/ops_latest.json` / cron logs | `generated_at` after latest market refresh |
| Script version | cron job script path | uses `smc_daily_closed_loop.py` or current V88 wrapper, not obsolete V31/V66-only paths |

## Durable pitfall
Older daily scripts may silently be incomplete even when they exit 0:

- `smc_daily_ops.py` previously ran V90 but not V91, so current-month BEAR_RISK/V91 candidates were absent from ops reports.
- `smc_daily_closed_loop.py` previously tried `v88_engine.py`; V88 production actually runs through `v88_apply_production_contract.py`.
- `smc_morning_push.py` previously printed `版本: V66` even when the frontend was V88.

When auditing daily automation, compare **configured scripts**, **actual output artifacts**, and **frontend/API state**. A healthy dashboard after manual repair does not prove the scheduled task will keep it healthy tomorrow.

## Minimum regression tests
After modifying the daily pipeline, run or recreate these checks:

```bash
python3 -m py_compile \
  /root/.hermes/scripts/v25/smc_daily_ops.py \
  /root/.hermes/scripts/v25/smc_daily_closed_loop.py \
  /root/.hermes/scripts/v25/smc_morning_push.py

python3 /root/.hermes/scripts/v25/smc_daily_ops.py
python3 /root/.hermes/scripts/v25/smc_daily_closed_loop.py
python3 /root/.hermes/scripts/v25/test_frontend_field_contract_mpkfagiawk77km.py
python3 /root/.hermes/scripts/v25/test_v88_current_picks_contract.py
```

Expected key assertions:

- V90 returncode = 0
- V91 returncode = 0
- active version = V88
- engine path = `v88_apply_production_contract.py`
- `/api/picks` row count matches current-month V90+V91 candidate contract
- field blanks = 0
- T+1 violations = 0
