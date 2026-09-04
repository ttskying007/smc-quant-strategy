# V177 Executable Exit Replay Boundary

Use this reference when continuing research after V175/V176 semantic split and loss-frontier work, especially when trying to recover extra edge from TIME exits without touching signal semantics.

## Context

V175 production/frontend baseline remained:

| n | WR | AvgPnL | min_year_n | all_year_WR_min | micro | T+1 |
|---:|---:|---:|---:|---:|---:|---:|
| 247 | 83.81% | 6.0493% | 38 | 81.71% | 0.81% | 0 |

V176 found no new production scalar/category filter and recommended an execution-layer replay focused on TIME exits with MFE around 0.5R–1.2R.

V177 reconstructed executable long-only bar-level alternatives from `v175_trades.json` + `kline_cache`, enforcing:

- T+1: exits only from `entry_idx + 1` onward.
- Conservative daily OHLC ordering: gap/open stop first, then stop, then TP.
- Close-triggered variants exit at next open, not same close.
- Research-only artifacts; no frontend/production/watchlist writes.

Artifacts from the session:

- `/root/.hermes/smc_audit/v177_v175_executable_exit_replay_20260624_105520/summary.json`
- `/root/.hermes/smc_audit/v177_v175_executable_exit_replay_20260624_105520/report.md`
- `/root/.hermes/scripts/v25/v177_exit_replay_research.py`

## Result

No executable exit / partial-profit variant passed production or research gate.

| variant | n | WR | AvgPnL | ΔAvg vs V175 | minYear | allYearWRmin | micro | T+1 | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| base_replay | 247 | 83.40% | 6.0077% | -0.0416 | 38 | 81.71% | 1.62% | 0 | FAIL |
| be_after_0p8r | 247 | 72.87% | 5.8069% | -0.2424 | 38 | 63.16% | 0.81% | 0 | FAIL |
| partial50_1p0r_lock_0p3r | 247 | 89.47% | 5.7849% | -0.2644 | 38 | 87.23% | 1.21% | 0 | FAIL |
| lock_0p3r_after_1p0r | 247 | 89.07% | 5.7459% | -0.3034 | 38 | 87.23% | 2.43% | 0 | FAIL |
| lock_0p5r_after_1p2r | 247 | 86.64% | 5.7387% | -0.3106 | 38 | 85.37% | 2.83% | 0 | FAIL |
| partial33_0p8r_be_rest | 247 | 93.52% | 5.7235% | -0.3258 | 38 | 89.36% | 2.83% | 0 | FAIL |
| close_fail_after_1p0r_next_open | 247 | 85.02% | 5.7105% | -0.3388 | 38 | 82.50% | 4.05% | 0 | FAIL |
| close_fail_after_0p8r_next_open | 247 | 85.02% | 5.6820% | -0.3673 | 38 | 83.75% | 6.48% | 0 | FAIL |

## Durable lesson

Do not keep adding generic BE / trailing / partial-profit rules after this boundary. They either:

- raise WR by cutting winners,
- lower average PnL below V175,
- increase BE/micro-profit pollution,
- or fail yearly robustness.

The next root-cause path is not another generic exit grid. It is path-level attribution of TIME rows:

1. Classify each TIME row by day-by-day R path.
2. Separate early profit then giveback, no-follow-through, near-TP failure, and gap-driven cases.
3. Inspect first pullback depth after reclaim and whether reclaim confirmation dies structurally.
4. Use 60min data only to test truly executable intraday partial/trailing behavior; do not infer intraday order from daily OHLC.
5. Keep V175 unchanged until a full gate passes.

## Reporting pattern

When reporting this class of execution-layer research to Lei, use a compact table with:

- decision,
- baseline metrics,
- each tested variant,
- pass/fail reason,
- artifact paths,
- next root-cause direction.

Do not overclaim a higher-WR variant if AvgPnL fell or micro/BE pollution rose.
