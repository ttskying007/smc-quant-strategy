# V185 cron productionization gap

Date: 2026-06-26

## Trigger

Use when auditing whether SMC production has fully moved to V185, especially for questions like “当前定时任务是不是执行 V185，是否覆盖数据更新/同步/选股/实时/文档/分析/复盘？”

## Verified state

V185 can be promoted in frontend/API while the scheduled operational loop still runs the older V88/V90/V101 chain. Do not infer cron productionization from `/api/summary` alone.

Validated signals from this session:

| surface | observed state | interpretation |
|---|---|---|
| `/api/summary` | `version=V185`, engine `V185_COMBINED_V175_PLUS_TRUE_TAKEOVER_CHILD`, 334 trades, WR 86.2, Avg 6.56 | frontend/API default route is V185 |
| `/api/picks` and `/api/picks?version=V185` | 6 active rows, V185 engine, no completed-trade pollution | V185 active-pick artifact is routed |
| `/api/live-prices` | 6 V185 rows, `tradableLiveCount=0`, `watchContextCount=6`, `WATCH_ONLY/NON_TRADABLE_CONTEXT` | live guard is using V185 payload |
| Hermes cron job `SMC Autonomous Closed Loop V65+` | script `v25/smc_daily_closed_loop.py` | cron name is stale; inspect script before concluding version |
| `smc_daily_closed_loop.py` | parses `ACTIVE_VERSION`; current active is still `V88`, then runs `smc_daily_ops.py` + `v88_apply_production_contract.py` | scheduled closed-loop is not fully V185-aware |
| `smc_daily_ops.py` | refreshes K-line, runs `v90_daily_full_market_scanner.py`, V98/V99/V100/V101 shadow stages, writes `ops_latest.json` with V88/V90/V101 diagnostics | data update/sync/analysis/review are still old-chain diagnostics |
| `smc_morning_push.py` | title line hardcoded `版本: V88`; reads default API picks | morning report may show V185 data but label/diagnostic contract is stale |
| extra cron `SMC V167 live degradation audit` | still scheduled | old degradation audit may mislead after V185 promotion |

## Audit procedure

1. List Hermes cron jobs and system crontab.
2. Inspect the scheduled script, not just job name.
3. Check these exact surfaces:
   - `/api/summary`
   - `/api/picks`
   - `/api/picks?version=V185`
   - `/api/live-prices`
   - `/api/live-prices?version=V185`
   - latest `~/.hermes/smc_daily_closed_loop/*.json`
   - `~/.hermes/smc_monitor/ops_latest.json`
   - latest `~/.hermes/smc_push_reports/*.md`
4. Classify each surface separately: frontend route, active picks, live guard, daily scanner, closed-loop report, morning push, analysis/docs/review.
5. If only API is V185 but cron scripts still execute V88/V90/V101, report “V185 is frontend/API-promoted, not full cron productionized.”

## Required productionization work before claiming full V185 scheduled execution

- Add or patch a V185-aware daily materialization/refresh path.
- Update `smc_daily_closed_loop.py` so the active production path can run V185 artifacts instead of falling back to `v88_apply_production_contract.py`.
- Update `smc_daily_ops.py` diagnostics and files table to include V185 artifacts and avoid V88/V90/V101-only stale reasons.
- Update `smc_morning_push.py` to derive/display the actual API production version instead of hardcoding `版本: V88`.
- Reassess or disable old V167 live degradation cron once V185 is production baseline, otherwise call it explicitly “legacy audit.”
- Smoke-test `/`, `/monitor`, `/live`, `/analysis`, `/docs`, `/api/summary`, `/api/picks`, `/api/live-prices`, and the generated closed-loop report for consistent V185 language and no historical-pollution rows.

## Productionization applied 2026-06-26

Implemented minimal V185 cron productionization:

- Added `/root/.hermes/scripts/v25/v185_daily_rematerialize.py`.
  - Validates V185 trades/active picks.
  - Enforces T+1 violations = 0.
  - Clears active-pick outcome fields.
  - Rewrites `v185_report.json`, `v185_picks.json`, `v185_active_picks.json`, `v185_active_picks.csv`.
  - Writes `/root/.hermes/smc_audit/v185_daily_rematerialize_latest.json`.
- Patched `smc_daily_closed_loop.py`:
  - Detects promoted V185 report before falling back to `ACTIVE_VERSION=V88`.
  - Uses `v185_daily_rematerialize.py` as the V185 production engine.
  - Writes `*_v185_closed_loop.json` reports with V185 metrics.
- Patched `smc_daily_ops.py`:
  - Keeps K-line refresh + V90 scanner as source-data refresh.
  - Stops executing legacy V98/V99/V100/V101 shadow selector in the production daily ops path.
  - Uses V185 active/trades/report for pick diagnostics, analysis summary, ops files table, and daily ingest source.
- Patched `smc_morning_push.py`:
  - Reads `/api/summary` and prints actual production `version`/`engine` instead of hardcoded `V88`.
- Cron changes:
  - Renamed closed-loop cron to `SMC Autonomous Closed Loop V185`.
  - Renamed morning push cron to `SMC Morning V185 Holdings Picks Push`.
  - Paused legacy `SMC V167 live degradation audit` cron.

Verification output from 2026-06-26:

| check | result |
|---|---|
| `py_compile` | ok for `v185_daily_rematerialize.py`, `smc_daily_closed_loop.py`, `smc_daily_ops.py`, `smc_morning_push.py` |
| `v185_daily_rematerialize.py` | `trades=334`, `active_picks=6`, `WR=86.23`, `Avg=6.5628`, `T+1=0`, active outcome pollution `0` |
| `smc_daily_ops.py` | ok; `analysis_summary.version=V185`; legacy V98-V101 shadow selector skipped |
| `smc_daily_closed_loop.py` | ok; output `/root/.hermes/smc_daily_closed_loop/20260626_v185_closed_loop.json`; steps `smc_daily_ops.py` and `v185_daily_rematerialize.py` both return 0 |
| `smc_morning_push.py` | ok; report header shows `版本: V185｜引擎: V185_COMBINED_V175_PLUS_TRUE_TAKEOVER_CHILD` |
| `/api/summary` | V185, engine `V185_COMBINED_V175_PLUS_TRUE_TAKEOVER_CHILD`, `334`, `86.2`, `6.56` |
| `/api/picks` | 6 rows, all V185 engine, event `DEMAND_OB_TRUE_TAKEOVER_RUNNER_CHILD`, completed pollution 0 |
| `/api/live-prices` | 6 rows, all V185 engine, `tradableLiveCount=0`, `watchContextCount=6`, completed pollution 0 |
| `/analysis`, `/docs` | contain V185 and no V88 in first 5KB smoke region |

GitNexus caveat: required impact/detect checks were attempted, but `npx gitnexus` fails under Node 26 because `tree-sitter-c-sharp` has no native build for ABI 147. Record this blocker rather than claiming GitNexus passed.

## Pitfall

A common false positive is: `/api/summary` says V185, therefore all scheduled jobs are V185. This is wrong. The SMC frontend router can prefer V185 artifacts while the cron operational pipeline still refreshes and diagnoses older V88/V90/V101 files. After the 2026-06-26 patch above, verify the cron scripts and `ops_latest.json` still show V185 before claiming this remains fixed.

2026-07-07 follow-up: when V185 has zero active rows, `v185_daily_rematerialize.py` must still derive `latest_market_date` from `/root/.hermes/smc_monitor/kline_refresh_latest.json` rather than falling back to the archived active-close date. Otherwise production report can show stale `latest_market_date` while ops/API live data are already refreshed. Verify parity: production report `latest_market_date`, ops `data_date`, and `/api/live-prices.dataDate` should all match the latest refreshed market date.
