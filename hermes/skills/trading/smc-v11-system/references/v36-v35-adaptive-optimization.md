# V36/V35 Adaptive Optimization Notes (2026-05-23)

## Current active frontend engine
- `smc_unified.py` selects V36 first when `/root/.hermes/smc_opt_v36/v36_trades.json` exists.
- V36 metrics (`v36_metrics.json`): 12 trades, WR 83.3%, SL rate 8.3%, total PnL +20.64.
- V36 fixes prior V35 overlap issues: one executable entry per symbol/date, OB preferred over overlapping FVG, FVG restricted to RANGE; BPR quarantined.

## V35 adaptive experiment from task t_07db6615
File: `/root/.hermes/scripts/v25/v35_adaptive.py`
Output: `/root/.hermes/smc_opt_v35_adaptive/`

What it adds:
- deterministic multi-horizon profiles: FAST_INTERNAL, BASE_SWING, SLOW_LOW_VOL
- dynamic SL/TP/trailing by entry-time ATR, market state, zone width
- starts from V34D audited signal chain to avoid signal correctness regression
- no future-label selection; errors are recorded rather than silently swallowed

Full run result: 7 trades, WR 100.0%, SL rate 0.0%, total PnL +11.05. It reduces SLs but is not promoted over V36 because it has lower coverage and lower total PnL.

## Decision rule
Do not auto-promote an adaptive exit variant just because WR/SL improves. Promote only if it preserves audited signal correctness and improves the overall frontier versus active V36: no duplicate/overlap trades, no FVG TREND_UP SL cluster, equal-or-better total PnL at acceptable SL rate.
