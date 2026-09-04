# V180-V182 research closure and supply-frontier lesson

Date: 2026-06-25

## Trigger

Use when deciding the next SMC research direction after V175 semantic split, especially when the user asks whether previous research is complete and what should be considered usable/unusable.

## Predeclared gates used

Production upgrade usable:
- non-leaking source-side rule;
- T+1 violations = 0;
- combined engine `n >= 260`;
- `min_year_n >= 40`;
- `WR >= 84%`;
- `AvgPnL >= 6.2%`;
- `all_year_WR_min >= 82%`;
- `micro_profit_pct <= 1%`;
- no frontend/watchlist/API mutation before dry-run passes.

Research child engine usable:
- 100% non-overlap vs V175;
- `n >= 120`;
- `min_year_n >= 20`;
- `WR >= 86%`;
- `AvgPnL >= 6.5%`;
- `all_year_WR_min >= 83%`;
- T+1 violations = 0.

Unusable:
- outcome leakage;
- any T+1 violation;
- better WR by cutting AvgPnL / creating BE or micro-profit pollution;
- 60min production claim with insufficient historical 60min coverage;
- simply relabeling V167/V172/V175 rows.

## Completed closure

V175 remains the verified production artifact:
- `n=247`, `WR=83.81%`, `Avg=6.0493%`, `min_year=38`, T+1=0.
- Semantic label is repaired to `DEMAND_OB_TRUE_TAKEOVER_RECLAIM`; classical SSL/CHOCH is not claimed by default.

V177 executable exit replay:
- Artifact: `/root/.hermes/smc_audit/v177_v175_executable_exit_replay_20260625_110818/`
- Decision: `V177_NO_EXECUTION_LAYER_IMPROVEMENT__NO_WRITE`.
- Best executable replay is base replay: `n=247`, `WR=83.00%`, `Avg=5.9985%`, below V175 baseline.
- Generic BE/partial/trailing exits raise WR in some variants but reduce AvgPnL or create BE/micro pollution.

V178 TIME attribution:
- Artifact: `/root/.hermes/smc_audit/v178_v175_time_path_attribution_20260625_110819/`
- TIME rows = 65.
- Path classes: `MID_MFE_0P5_1P2R_GIVEBACK=27`, `NEAR_TP_OR_LARGE_GIVEBACK=10`, `MIXED_SMALL_EDGE=10`, `TIME_WINNER_HELD_OK=9`, `NO_FOLLOW_THROUGH_LT_0P5R=9`.
- TIME is not one homogeneous exit bug.

V179 60min probe:
- Artifact: `/root/.hermes/smc_audit/v179_v175_time_60min_probe_20260625_110820/`
- 60min coverage only `9/65 = 13.85%`.
- Historical 60min execution cannot be promoted until data is filled.

V180 V128 source-side frontier:
- Artifact: `/root/.hermes/smc_audit/v180_v128_frontier_gate_research_20260625_1110/`
- V128 base: `n=39015`, `WR=35.96%`, `Avg=1.6576%`, hard-exit `57.45%`.
- No source-side filter combination passed production or research frontier.

V181 delayed takeover / wait-more-bars check:
- Artifact: `/root/.hermes/smc_audit/v181_v128_delayed_takeover_gate_20260625_1115/`
- Delayed confirmation variants (`hold1`, `hold2`, `takeover3`, `strict_no_low_break_2`) all failed. Waiting more bars after reclaim lowered/failed broad metrics.

V181 V167 leftover supply expansion:
- Artifact: `/root/.hermes/smc_audit/v181_signal_supply_expansion_probe_20260625_1145/`
- V167 excluded non-overlap pool: `n=546`, `WR=81.32%`, `Avg=3.8577%`, `min_year=42`, `yearWRmin=79.28%`.
- No non-overlapping child engine passed gate.
- Best near-frontier `v132_bull_count_3>=3`: child `n=175`, `WR=87.43%`, `Avg=4.7261%`; combined `n=422`, `WR=85.31%`, `Avg=5.5006%`; fails Avg/micro/gate.

V182 runner-exit probe on the best V181 child:
- Artifact: `/root/.hermes/smc_audit/v182_v181_child_runner_exit_probe_20260625_1155/`
- Child rule: `V167 excluded AND v132_bull_count_3>=3`.
- Runner exits lift Avg but break WR/year stability:
  - base child `WR=87.43%`, `Avg=4.7261%`;
  - 10d runner child `WR=74.86%`, `Avg=8.8054%`, combined `WR=80.09%`, `Avg=7.1922%`;
  - 20d runner child `WR=65.14%`, `Avg=10.2397%`, combined `WR=76.07%`, `Avg=7.7870%`.
- No runner variant passed production gate.

## Decision

Closed paths:
1. More scalar filters on V172/V175.
2. Generic exit overlays on V175.
3. 60min historical production exits with current cache.
4. Reusing V167 leftovers as a second child engine.
5. Waiting extra daily bars after V128 reclaim.
6. Simple fixed runner exits for the best V167 leftover child.

Next direction with potential for qualitative change:
- Build a genuinely new candidate generator, not a filter over current artifacts.
- The generator must change POI/event supply itself: e.g. new structure lifecycle source, pre-entry target geometry, or explicit supply/demand continuation model.
- Any new candidate must be shadow-only until it passes the production gate above.
