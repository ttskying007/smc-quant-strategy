# V185 successful full rerun: artifact paths and zero-pick semantics (2026-07-11)

A Hermes-tracked rerun of `v25/smc_daily_closed_loop.py` completed cleanly after about 12 minutes. The wrapper final line was `ok=true`, `version=V185`, `pass=true`, `wr=86.23`.

## Verify the active V185 contract from these paths

- Dated wrapper report: `/root/.hermes/smc_daily_closed_loop/YYYYMMDD_v185_closed_loop.json`
- Ops truth: `/root/.hermes/smc_monitor/ops_logs/YYYYMMDD.json` and `ops_latest.json`
- Rematerialized contract:
  - `/root/.hermes/smc_opt_v185_combined_production_candidate/v185_trades.json`
  - `/root/.hermes/smc_opt_v185_combined_production_candidate/v185_active_picks.json`
  - `/root/.hermes/smc_opt_v185_combined_production_candidate/v185_picks.json`
  - `/root/.hermes/smc_opt_v185_combined_production_candidate/v185_report.json`
  - `/root/.hermes/smc_audit/v185_daily_rematerialize_latest.json`

Do not assume artifacts live in `/root/.hermes/smc_opt_v185/` or `smc_monitor/`; those legacy-looking paths may be absent even when V185 rematerialization has passed.

## Gate and cache interpretation

On this pass, all V185 promotion predicates passed: sample size, year coverage, WR, average PnL, minimum annual WR, micro-profit cap, and T+1=0. Ops recorded all core stages at return code 0 and refresh `ok=4655`. Direct cache inspection found 4,637 of 4,655 `*_daily_750.json` files with latest date `20260710`, supporting the established >=4,500 latest-date coverage rule. Cache rows can expose the date under either `date` or `t`.

## API verification and empty-state behavior

`/api/summary` and `/api/kline_full?...ver=V185` must identify V185; `POST /api/reselect {"version":"V185"}` must return `ok=true`. This pass had zero V185 active production picks, so `/api/picks`, `/api/resonance`, and `/api/live-prices` were empty/zero-row. That is valid production parity, not a frontend failure; state the zero-pick result explicitly and compare zero-to-zero guard maps.

`/api/autopsy/closed-loop` returned `{}` because it loads a 90-day review artifact, not the dated daily closed-loop report. Treat it as an endpoint smoke result unless a nonempty 90-day artifact is required by the specific release gate.

## Reporting

Report the dated report and live API version separately, note the zero active-pick state, mention cache coverage and any threshold used, and confirm no residual `smc_daily_closed_loop.py`, `smc_daily_ops.py`, or `refresh_daily_750.py` children before final success.