# Daily closed-loop secondary refresh false failure — 2026-06-28

## Trigger

Cron/context-compaction recovery left no dated closed-loop report for the day. A first `smc_daily_ops.py` orphan had already completed successfully, but `/root/.hermes/smc_daily_closed_loop/20260628_v185_closed_loop.json` was missing.

## Correct recovery sequence

1. Check that no `smc_daily_ops.py` / `smc_daily_closed_loop.py` child is still alive before rerunning.
2. Inspect `/root/.hermes/smc_monitor/ops_latest.json` and the dated ops log to confirm whether the first daily ops pass completed.
3. If daily ops completed but the dated closed-loop report is absent, run the real wrapper once as a Hermes-tracked background process:

   ```bash
   cd /root/.hermes/scripts/v25
   python3 smc_daily_closed_loop.py
   ```

4. Wait for the wrapper to finish and verify it emitted the dated report.
5. Smoke the live frontend/API, including reselect support for the active version:

   ```text
   /api/summary
   /api/autopsy/closed-loop
   /api/picks
   /api/resonance
   /api/kline_full?symbol=300349.SZ&tf=daily&ver=V185
   POST /api/reselect {"version":"V185"}
   ```

## Important pitfall

A wrapper rerun may overwrite `ops_latest.json` with a second provider-refresh failure even though the first daily ops pass had already refreshed the local K-line cache successfully. On 2026-06-28:

- First refresh: `requested=4905`, `ok=4655`, `failed=250`, latest `20260626=4637`.
- Second refresh during wrapper rerun: `ok=0`, `failed=4905`, all `Expecting value: line 1 column 1`.
- Direct cache audit still showed `4655` non-empty cache files and `4637` files latest at `20260626`.

Do not report the final overwritten refresh counter alone as the truth. Audit the actual cache files and support both row date keys:

```python
dt = row.get('date') or row.get('t') or row.get('time')
```

If cache coverage is still healthy, report the secondary refresh as a supplier empty-response/limit caveat, not as a production completeness failure. Do not repeatedly rerun the refresh.

## 2026-06-28 verification facts

- Wrapper output: `/root/.hermes/smc_daily_closed_loop/20260628_v185_closed_loop.json`.
- Wrapper result: `ok=true`, `version=V185`, `pass=true`, `wr=86.23`.
- V185 metrics: `334` trades, WR `86.23%`, AvgPnL `6.5628%`, min yearly sample `41`, min yearly WR `82.81%`, micro profit `0.9%`, T+1 violations `0`.
- V231 decision: `V231_NO_CURRENT_ACTIONABLE_ROWS__KEEP_SHADOW_MONITORING_NO_WRITE`.
- V236 decision: `V236_NO_CURRENT_ACTIONABLE_ROWS__KEEP_SHADOW_MONITORING_NO_WRITE`.
- Daily ingest: `added=0`, `reason=NO_LATEST_DATA_PICKS`.
- API smoke passed, including `POST /api/reselect {"version":"V185"}` returning V185 successfully.
