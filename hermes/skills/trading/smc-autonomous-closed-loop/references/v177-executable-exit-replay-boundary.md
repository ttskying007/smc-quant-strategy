# V177 executable exit replay boundary

Use this when continuing autonomous SMC research after V175/V176 and considering execution-layer changes without changing signal semantics.

## Context

V175 production baseline remained the gate reference:

| n | WR | AvgPnL | minYear | allYearWRmin | micro | T+1 |
|---:|---:|---:|---:|---:|---:|---:|
| 247 | 83.81% | 6.0493% | 38 | 81.71% | 0.81% | 0 |

V176 found no scalar/category filter worth promoting and pointed to TIME-exit execution research.

V177 rebuilt executable daily-bar exits from `v175_trades.json` + `kline_cache`, research-only, with:

- strict A-share T+1: exits start at `entry_idx + 1`;
- conservative daily OHLC order for long positions: gap/open stop, then stop, then TP;
- close-triggered variants exit at next open, not same close;
- no production/frontend/watchlist writes.

Artifacts:

- `/root/.hermes/smc_audit/v177_v175_executable_exit_replay_20260624_105520/summary.json`
- `/root/.hermes/smc_audit/v177_v175_executable_exit_replay_20260624_105520/report.md`
- `/root/.hermes/scripts/v25/v177_exit_replay_research.py`

## Result boundary

No generic executable exit rule passed production or research gate.

| variant | n | WR | AvgPnL | ΔAvg | minYear | allYearWRmin | micro | T+1 | decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| base_replay | 247 | 83.40% | 6.0077% | -0.0416 | 38 | 81.71% | 1.62% | 0 | FAIL |
| be_after_0p8r | 247 | 72.87% | 5.8069% | -0.2424 | 38 | 63.16% | 0.81% | 0 | FAIL |
| partial50_1p0r_lock_0p3r | 247 | 89.47% | 5.7849% | -0.2644 | 38 | 87.23% | 1.21% | 0 | FAIL |
| lock_0p3r_after_1p0r | 247 | 89.07% | 5.7459% | -0.3034 | 38 | 87.23% | 2.43% | 0 | FAIL |
| lock_0p5r_after_1p2r | 247 | 86.64% | 5.7387% | -0.3106 | 38 | 85.37% | 2.83% | 0 | FAIL |
| partial33_0p8r_be_rest | 247 | 93.52% | 5.7235% | -0.3258 | 38 | 89.36% | 2.83% | 0 | FAIL |
| close_fail_after_1p0r_next_open | 247 | 85.02% | 5.7105% | -0.3388 | 38 | 82.50% | 4.05% | 0 | FAIL |
| close_fail_after_0p8r_next_open | 247 | 85.02% | 5.6820% | -0.3673 | 38 | 83.75% | 6.48% | 0 | FAIL |

## Durable workflow lesson

Do not keep adding generic BE, trailing, lock-profit, or partial-profit grids to V175. These either cut winners, lower AvgPnL, increase BE/micro-profit pollution, or fail yearly robustness. A higher WR is not promotable when AvgPnL drops or micro pollution rises.

Next root-cause path:

1. Classify TIME rows by day-by-day R path.
2. Separate early-profit-then-giveback, no-follow-through, near-TP failure, and gap-driven cases.
3. Inspect first pullback depth after reclaim and whether reclaim confirmation dies structurally.
4. Use 60min data only for genuinely executable intraday partial/trailing tests; do not infer intraday order from daily OHLC.
5. Keep V175 unchanged until a full gate passes.
