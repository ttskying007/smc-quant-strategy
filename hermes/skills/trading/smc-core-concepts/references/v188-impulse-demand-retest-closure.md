# V188 impulse-demand retest and post-V175 closure extension

Date: 2026-06-25

## Trigger
Use after V175/V180-V182 closure when considering whether to keep iterating old V128/V167/V175 filters or build another raw candidate generator.

## Predeclared usability gates
Production upgrade:
- non-leaking source-side rule;
- T+1 violations = 0;
- combined engine `n >= 260`;
- `min_year_n >= 40`;
- `WR >= 84%`;
- `AvgPnL >= 6.2%`;
- `all_year_WR_min >= 82%`;
- `micro_profit_pct <= 1%`;
- no frontend/watchlist/API mutation before dry-run passes.

Research child engine:
- 100% non-overlap vs V175;
- `n >= 120`;
- `min_year_n >= 20`;
- `WR >= 86%`;
- `AvgPnL >= 6.5%`;
- `all_year_WR_min >= 83%`;
- T+1 violations = 0.

## Additional completed research

### V183 classical SSL sweep -> CHOCH -> OB -> reclaim
Artifact: `/root/.hermes/smc_audit/v183_classical_sweep_ob_generator_20260625_131931/`
Decision: `FAIL_NO_WRITE`.
Metrics: `n=63`, `WR=30.16%`, `Avg=-0.1649%`, `min_year_n=3`, T+1=0.
Conclusion: forcing classical sweep/CHOCH supply is not the path; it is too sparse and low quality.

### V184 V85 runner frontier
Artifact: `/root/.hermes/smc_audit/v184_v85_runner_frontier_20260625_132418/`
Decision: `V184_V85_RUNNER_NO_PRODUCTION_GATE__NO_WRITE`.
Base child `n=559`, `WR=78.53%`, `Avg=2.4255%`, micro `9.12%`; combined with V175 `n=806`, `WR=80.15%`, `Avg=3.536%`.
Conclusion: old V85 runner pool is broad but creates micro-profit/low-average pollution and does not upgrade V175.

### V185 market breadth + target geometry
Artifact: `/root/.hermes/smc_audit/v185_market_breadth_target_geometry_20260625_135122/`
Decision: `V185_NO_PRODUCTION_OR_RESEARCH_PASS__BREADTH_TARGET_FILTER_CLOSED`.
V129 target-exit base remains negative expectancy (`Avg≈-1.36%`) with extreme micro-profit pollution (`~66%`).
Conclusion: prior-day breadth and target geometry do not rescue V128 target-exit pool.

### V186 micro-HL post-reclaim confirmation
Artifact: `/root/.hermes/smc_audit/v186_micro_hl_takeover_generator_20260625_135750/`
Decision: `V186_NO_RESEARCH_CHILD_PASS__MICRO_TAKEOVER_CLOSED`.
Best `n=603`, `WR=44.44%`, `Avg=-0.293%`, T+1=0.
Conclusion: simple post-reclaim candle strength / micro higher-low confirmation is not a standalone qualitative path.

### V187 accumulation breakout retest
Artifact: `/root/.hermes/smc_audit/v187_fast_accumulation_breakout_retest_20260625_141203/`
Decision: `V187_NO_RESEARCH_CHILD_PASS__ACCUMULATION_BREAKOUT_RETEST_CLOSED`.
Best `n=8`, `WR=50%`, `Avg=1.0196%`, T+1=0.
Conclusion: raw accumulation-breakout-retest is too sparse and unstable.

### V188 impulse -> demand-zone retest -> reclaim raw generator
Artifact: `/root/.hermes/smc_audit/v188_impulse_demand_retest_generator_20260625_143626/`
Decision: `V188_NO_RESEARCH_CHILD_PASS__IMPULSE_DEMAND_RETEST_CLOSED`.
Best non-overlap child: `n=1595`, `WR=42.13%`, `Avg=0.1039%`, `min_year_n=78`, `all_year_WR_min=34.62%`, T+1=0.
Combined with V175: `n=1842`, `WR=47.72%`, `Avg=0.9011%`, T+1=0.
A follow-up source-field threshold search over the generated V188 candidates found `0` frontiers above even relaxed (`WR>=70`, `Avg>=3`) requirements.
Conclusion: momentum/impulse demand retest produces many candidates but too many SL/GAP_SL; it is not a valid SMC supply upgrade.

## 60min data coverage follow-up
- Tencent 60min endpoint is reachable, but historical depth is limited (`m60` around 320-500 bars, roughly late-2025/2026 for tested symbols).
- V179 remains blocked for older V175 TIME rows because 60min historical coverage cannot be expanded to 2023/2024 from this source.
- Do not promote 60min exit logic until a true historical intraday data source is available and coverage exceeds the predeclared threshold.

## Closed directions after V188
Do not keep spending cycles on:
1. Scalar filters over V128/V167/V172/V175.
2. Relabeling classical sweep/CHOCH as if it is the production edge.
3. Generic BE/partial/trailing exits over V175.
4. Fixed runners for leftover V167/V85 pools.
5. Raw breakout/retest/accumulation/impulse generators without a stronger institutional-cost semantic.
6. 60min production exit claims with current Tencent historical depth.

## Remaining direction with highest chance of qualitative change
The next valid research direction must introduce a **new pre-entry semantic feature source**, not another filter over existing rows. Candidate directions:
- historical intraday/level-2 data acquisition for true execution timing and TIME-row diagnostics;
- sector/industry relative-strength and limit-up chain context computed strictly before entry;
- institutional cost / anchored VWAP-like demand control built from raw OHLCV before entry;
- full active-pick rematerialization pipeline from latest V128 scanner snapshot, because current V175 active picks can be stale relative to regenerated V128, but this is an operational sync task, not a new strategy edge.

Until one of those new feature sources is available, V175 remains the only production-usable engine and the research conclusion is to stop artifact-slicing loops.