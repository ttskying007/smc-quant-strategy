# V185 closed-loop cron verification — 2026-07-07

## Trigger
Cron/context-compaction continuation for the V185 daily autonomous closed-loop where the active task list was preserved:

1. run wrapper from `/root/.hermes/scripts`
2. verify dated report/version/pass and V185 artifacts
3. smoke frontend/API/watchlist/report parity including reselect and live-guard parity
4. confirm no residual child processes

## Durable workflow lesson
When a foreground wait is clamped or times out, do not classify the wrapper as failed. Keep the real wrapper in a Hermes-tracked background process and poll/wait until the final JSON line appears.

Successful final wrapper line:

```json
{"ok": true, "version": "V185", "out": "/root/.hermes/smc_daily_closed_loop/20260707_v185_closed_loop.json", "pass": true, "wr": 86.23}
```

## Paths verified

- Dated closed-loop report: `/root/.hermes/smc_daily_closed_loop/20260707_v185_closed_loop.json`
- Ops logs are under `/root/.hermes/smc_monitor/`, not under `/root/.hermes/scripts/smc_monitor/` or `/root/.hermes/scripts/v25/smc_monitor/`:
  - `/root/.hermes/smc_monitor/ops_latest.json`
  - `/root/.hermes/smc_monitor/ops_logs/20260707.json`
- V185 rematerialize latest:
  - `/root/.hermes/smc_audit/v185_daily_rematerialize_latest.json`
- Production report:
  - `/root/.hermes/smc_opt_v185_combined_production_candidate/v185_report.json`

## Verification checklist that passed

### Report/artifact parity

- closed-loop `active_version == V185`
- embedded report `version == V185`
- production report `version == V185`
- `/api/summary.version == V185`
- engine matches across API summary, closed-loop report, and production report
- rounded WR matches (`86.2` API vs `86.23` report)
- `/api/picks` length matches production `active_pick_count`
- production `decision == V185_DAILY_REMATERIALIZE_PASS`
- `cron_productionized == true`
- `latest_market_date` matches across closed-loop and production report

### Production gate metrics

- trades: `334`
- WR: `86.23`
- avg PnL: `6.5628`
- min yearly sample: `41`
- all-year WR min: `82.81`
- micro-profit pct: `0.9`
- same-day exits: `0`
- active picks: `0`

### API smoke

- `GET /api/summary` returns `version=V185`, expected engine, WR around `86.2`
- `GET /api/picks` returns `[]`
- `GET /api/live-prices` has no realtime monitored holdings and zero picks
- `GET /api/resonance` returns `[]` with no bad signal rows to inspect
- `GET /api/autopsy/closed-loop` may return `{}`; endpoint reachability is enough because this loader can point at the 90D review artifact rather than the daily report
- `GET /api/kline_full?symbol=300349.SZ&tf=daily&ver=V185` returns `version=V185` and 750 K-lines
- `POST /api/reselect {"version":"V185"}` succeeds and returns `ok=true`, `version=V185`, `all_trades=334`, `active_candidates=0`

### Live-guard parity

If both `/api/picks` and `/api/live-prices["picks"]` are empty, parity is valid:

```json
{"picks_len": 0, "live_prices_picks_len": 0, "mismatch_count": 0}
```

### Cache coverage

For V185 2026-07-07 verification, cache audit returned:

```json
{"cache_files": 4655, "latest_threshold": "20260706", "latest_or_newer": 4638, "older_or_empty": 17, "errors": 0}
```

Treat this as sufficient when ops return codes and the production/rematerialization gates pass; report the coverage numbers rather than mutating production code.

## Residual process rule

Before final reporting, verify no residual daily children remain:

```bash
pgrep -af 'smc_daily_closed_loop.py|smc_daily_ops.py|refresh_daily_750.py|v185_daily_rematerialize.py' || true
```

The persistent `smc_unified.py` frontend on port 8890 is expected and should not be killed just to produce a clean process list.

## Final-report shape

Report concrete evidence: wrapper exit/final JSON, dated report path, production artifact paths, gate metrics, API smoke/reselect/live-guard parity, cache coverage, and residual-process status. Do not create a new Vxx or patch code when all of these pass.