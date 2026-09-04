# V152 production promotion closure pattern

Use this when a research/backtest variant has passed gates and needs to become the current SMC dashboard/API contract without polluting live picks.

## Durable lesson

A promotable historical/backtest contract must be split into two artifacts:

1. **Historical production trades** for `/api/summary`, backtest tables, K-line trade overlays, and audit reports.
2. **Live/current picks** that remain sourced from the full-market daily scanner. Do not expose historical trades as current tradable candidates.

For V152 this meant writing:

- `smc_opt_v152_hybrid_lifecycle_gate/v152_report.json`
- `smc_opt_v152_hybrid_lifecycle_gate/v152_trades.json`
- `smc_opt_v152_hybrid_lifecycle_gate/v152_trades.csv`
- `smc_opt_v152_hybrid_lifecycle_gate/v152_picks.json` as `[]`
- `smc_opt_v152_hybrid_lifecycle_gate/v152_active_picks.json` as `[]`

The historical rows carried `pick_scope=HISTORICAL_BEST` and `is_active_pick=false`; this is the explicit guard that prevents current-pick pollution.

## Promotion steps

1. Re-read the source summary and refuse promotion unless its release gate passes.
2. Convert the validated rows into a stable field contract:
   - `engine`, `version`, `strategy_version`
   - `symbol`, `pick_date`, `select_date`, `join_date`, `entry_date`, `exit_date`
   - `entry_price`, `exit_price`, `pnl_pct`, `won`
   - `zone_type`, `signal_type`, `zone_low`, `zone_high`, `cost_line`, `smart_money_cost`
   - `sl`, `sl_price`, `risk_pct`, `tp/tp1/tp2/tp3`, `rr`, `rr_realized`
   - `market_state`, `combo_family`, `event_type`, `entry_mode`
   - `lifecycle_status`, `lifecycle_action`, rule/threshold fields
   - `t1_violation`, `strict_audit_status`, `signal_correctness_claim`
3. Write a report with gates:
   - source release gate pass
   - `n >= 120`
   - `wr >= 90` if that is the release standard for this contract
   - avg PnL within the allowed baseline delta
   - `t1_zero`
   - `field_missing_zero`
   - `no_live_historical_picks`
4. Add the new contract directory to `smc_unified.py` promoted routing:
   - define `Vxxx_DIR`
   - `_promoted_contract_dir()` returns the new directory first when its report exists
   - `_promoted_trade_file()` returns its trades file
   - `reload_metrics()` returns its report
   - `_active_pick_mtime()` includes its active-picks file if needed for cache invalidation
5. Restart the dashboard and verify with real HTTP calls.

## Required verification

Minimum successful closure output must include actual tool results for:

- `/api/summary`: expected version/engine/trade count/win rate/avg PnL
- `/api/picks/contract`: confirm active picks are not historical trades
- `/api/picks`: list count and source shape
- `/api/live-prices`: still responds from the live/watch pipeline
- `/api/reload`: no crash on repeat call
- `/api/kline_full?symbol=<known_trade>&tf=daily&ver=V88`: the K-line route returns the promoted engine trade overlay with zone/cost-line fields
- frontend root HTML contains the promoted version label and headline metrics
- process/port check shows the intended `smc_unified.py` instance is serving port 8890

## Pitfalls

- Do not trust one `/api/summary` call immediately after restart if an old process is still bound to port 8890. Check the PID/port and repeat after the correct server is live.
- If a background server start exits with `Address already in use`, treat the existing bound process as the serving process only after verifying its `/api/summary` shows the promoted version.
- `/api/reload` can fail once during a process race; repeat it after confirming the serving PID. The durable lesson is to verify the final steady-state response, not to mark reload as broken.
- Never promote by only writing metrics. K-line overlays and pick contract isolation must be verified too.

## V152 concrete acceptance snapshot

- Engine: `V152_HYBRID_LIFECYCLE_GATE`
- Trades: 127
- WR: 92.91%
- Avg PnL: +2.9407%
- Median PnL: +2.6034%
- Loss rate: 7.09%
- Hard exit rate: 37.8%
- T+1 violations: 0
- Historical rows exposed as active picks: 0
- Frontend title: `SMC V152 Dashboard`
