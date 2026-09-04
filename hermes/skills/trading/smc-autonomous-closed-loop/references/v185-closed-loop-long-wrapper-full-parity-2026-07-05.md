# V185 2026-07-05 closed-loop: long wrapper success + full parity verification

## Context
A cron/context-compaction recovery required running the real configured wrapper from `/root/.hermes/scripts`:

```bash
PYTHONUNBUFFERED=1 python3 v25/smc_daily_closed_loop.py
```

The wrapper ran longer than several 60s Hermes `process.wait` windows but ultimately exited `0` with:

```json
{"ok": true, "version": "V185", "out": "/root/.hermes/smc_daily_closed_loop/20260705_v185_closed_loop.json", "pass": true, "wr": 86.23}
```

## Durable procedure
When a V185 daily closed-loop wrapper is still alive after short waits:

1. Do **not** launch a duplicate wrapper while `smc_daily_closed_loop.py`, `smc_daily_ops.py`, or `refresh_daily_750.py` children are still alive.
2. Poll/wait the Hermes-tracked background process until final JSON appears, even if individual wait calls are clamped to 60s.
3. Treat the final wrapper JSON as the primary completion signal, then verify artifacts independently.
4. Verify both dated report and production artifacts because the production report/active picks may be rematerialized after the dated closed-loop report is first observed.

## Verification checklist used

### Dated closed-loop report
- `/root/.hermes/smc_daily_closed_loop/YYYYMMDD_v185_closed_loop.json`
- `active_version == V185`
- `steps` include:
  - `python3 smc_daily_ops.py` with `returncode: 0`
  - `python3 v185_daily_rematerialize.py` with `returncode: 0`

### Production artifacts
Known V185 production paths:

```text
/root/.hermes/smc_opt_v185_combined_production_candidate/v185_trades.json
/root/.hermes/smc_opt_v185_combined_production_candidate/v185_active_picks.json
/root/.hermes/smc_opt_v185_combined_production_candidate/v185_picks.json
/root/.hermes/smc_opt_v185_combined_production_candidate/v185_report.json
```

Verify `v185_report.json` carries:
- `version: V185`
- `decision: V185_DAILY_REMATERIALIZE_PASS`
- `production_write/frontend_write/watchlist_write: true`
- `cron_productionized: true`
- `active_outcome_pollution: 0`
- `historical_same_day_exit: 0`
- all `promotion_gate` booleans true

Observed stable V185 metrics in this pass:
- Trades: `334`
- WR: `86.23%`
- AvgPnL: `6.5628`
- Active picks: `6`

### Ops/completeness
Check:
- `/root/.hermes/smc_monitor/ops_latest.json`
- `/root/.hermes/smc_monitor/ops_logs/YYYYMMDD.json`
- `kline_refresh.returncode == 0`
- `daily_scan.ok == true`
- `daily_scan_merge.ok == true`
- `daily_ingest.ok == true`
- shadow audits return `0`

Cache audit should support both `date` and `t` bar fields when counting latest-date coverage.

### API/frontend parity
Smoke these endpoints before reporting success:

```text
GET  /api/summary
GET  /api/picks
GET  /api/resonance
GET  /api/live-prices
GET  /api/kline_full?symbol=300349.SZ&tf=daily&ver=V185
GET  /api/autopsy/closed-loop
POST /api/reselect {"version":"V185"}
```

Required parity outcomes:
- `/api/summary` reports V185 and production metrics.
- `/api/picks` row count equals `/api/live-prices` pick row count.
- Per-symbol `live_guard_status` between picks and live-prices has zero mismatches.
- `/api/resonance` has zero empty/`None`/`null` context/signal cells.
- `POST /api/reselect {"version":"V185"}` succeeds and reports V185 engine metadata.
- `/api/autopsy/closed-loop` may return `{}`; this is a known loader-path caveat, not by itself a failure.

### Final process hygiene
Before final report, verify no residual processes remain for:

```text
smc_daily_closed_loop|smc_daily_ops|refresh_daily_750
```

## Reporting caveat
If `v185_trades.json` retains an older source-material mtime but `v185_report.json`, `v185_active_picks.json`, `v185_picks.json`, closed-loop report, and ops logs are fresh and gates/API parity pass, report success with the mtime caveat rather than mutating production artifacts or strategy code.
