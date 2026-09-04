# V185 full-wrapper timeout + parity verification — 2026-07-03

## Trigger
Cron/compaction recovery for V185 needed the real configured wrapper to run from `/root/.hermes/scripts`:

```bash
python3 v25/smc_daily_closed_loop.py
```

A foreground 600s Hermes `terminal()` call timed out before the wrapper completed. This was not a strategy failure. The wrapper's internal `smc_daily_ops.py` can legitimately spend ~14+ minutes in `refresh_daily_750.py --workers 20` before producing the dated closed-loop report.

## Recovery pattern that worked
1. Check for residual child processes before rerunning:
   ```bash
   pgrep -af 'smc_daily_closed_loop|smc_daily_ops|refresh_daily_750|v185_daily_rematerialize|smc_unified' || true
   ```
2. If no duplicate child is active and the dated report is stale/missing, start the real wrapper as a Hermes-tracked background process with completion notification:
   ```bash
   cd /root/.hermes/scripts
   python3 v25/smc_daily_closed_loop.py
   ```
   Use `background=true` + `notify_on_complete=true`, then `process wait/poll` until it exits. Do not rely on a 600s foreground timeout for this class of run.
3. After completion, verify the wrapper's own JSON line, not just old artifacts. Expected shape observed:
   ```json
   {"ok": true, "version": "V185", "out": "/root/.hermes/smc_daily_closed_loop/20260703_v185_closed_loop.json", "pass": true, "wr": 86.23}
   ```
4. Verify dated report and ops logs are freshly updated:
   - `/root/.hermes/smc_daily_closed_loop/YYYYMMDD_v185_closed_loop.json`
   - `/root/.hermes/smc_monitor/ops_latest.json`
   - `/root/.hermes/smc_monitor/ops_logs/YYYYMMDD.json`
   - `/root/.hermes/smc_audit/v185_daily_rematerialize_latest.json`
5. Verify `steps[0].returncode == 0` for `smc_daily_ops.py` and `steps[1].returncode == 0` for `v185_daily_rematerialize.py` inside the dated report. Earlier partial reports may have `smc_daily_ops.py` timeout/fail while rematerialize succeeds; replace them by allowing the real wrapper to finish.

## Expected V185 production gate/artifact checks
Observed pass values:
- `active_version`: `V185`
- `report.version`: `V185`
- `win_rate`: `86.23`
- `total_trades`: `334`
- `active_pick_count`: `6`
- promotion gate booleans all true: `n>=260`, `min_year_n>=40`, `WR>=84`, `AvgPnL>=6.2`, `all_year_WR_min>=82`, `micro_profit_pct<=1`, `T+1=0`
- rematerialized artifacts exist:
  - `/root/.hermes/smc_opt_v185_combined_production_candidate/v185_active_picks.json`
  - `/root/.hermes/smc_opt_v185_combined_production_candidate/v185_picks.json`
  - `/root/.hermes/smc_opt_v185_combined_production_candidate/v185_report.json`
  - `/root/.hermes/smc_opt_v185_combined_production_candidate/v185_trades.json`

## API/frontend/watchlist/report 口径一致 smoke
Run the post-wrapper parity smoke against live port 8890:
- `/api/summary` should serve V185, `total_trades=334`.
- `/api/picks` should be OK.
- `/api/resonance` should be OK.
- `/api/live-prices` should return 6 V185 rows; off-hours may include the expected Chinese closed-market message, but row guard statuses are still usable.
- `/api/kline_full?symbol=300349.SZ&tf=daily&ver=V185` should return V185 and daily bars.
- `POST /api/reselect {"version":"V185"}` should succeed and write `history/v185_picks_YYYYMMDD.json`.
- Compare per-symbol guard status between `/api/picks` and `/api/live-prices`; success case on 2026-07-03 had `compared=6`, `mismatch_count=0`.

## Cache/completeness nuance
After the full wrapper completed, `ops_latest.json` showed:
- `kline_refresh.returncode=0`
- `requested=4905`, `ok=4648`, `failed=257`
- latest cache coverage around `20260702`: `4631` from ops summary / `4638` from direct cache audit in the same session

This is a pass under the existing V185 daily completeness pattern; do not rerun provider refresh just because some BJ/sparse symbols report `rows=1`.

## Final process hygiene
Before reporting success, confirm no residual closed-loop/daily-ops/refresh/rematerialize processes remain. It is normal for only the live `smc_unified.py` frontend process to remain on port 8890.
