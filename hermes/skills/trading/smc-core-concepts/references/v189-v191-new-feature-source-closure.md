# V189-V191 post-V175 new feature-source closure

Date: 2026-06-25

## Trigger
Use when continuing SMC research after V175/V180-V188 and the user asks whether previous research is complete, what counts as usable/unusable, and what direction remains.

## Predeclared usability gates
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
- `micro_profit_pct <= 1%`;
- T+1 violations = 0.

Unusable:
- outcome leakage;
- any T+1 violation;
- higher WR created by micro-profit / BE pollution;
- insufficient year coverage or unstable yearly WR;
- simply slicing V128/V167/V172/V175 without a new pre-entry feature source.

## V189 — institutional cost / anchored VWAP pre-entry control
Artifact: `/root/.hermes/smc_audit/v189_cost_control_preentry_gate_20260625_150600/`

Source/evaluation:
- V129 realistic target-exit rows (`v129_v128_target_exit_all.csv`), not original V128 TIME drift outcome.
- Excludes V175 overlap by `symbol + entry_date`.
- Features are computed from local daily OHLCV before entry only: anchored VWAP from zone/event/touch to entry, entry vs AVWAP, touch/reclaim/entry volume ratio, hold-above-zone/AVWAP ratios, reclaim close/body strength.
- Audit-only; no frontend/watchlist/API mutation.

Result:
- Decision: `V189_NO_RESEARCH_CHILD_PASS__COST_CONTROL_FILTER_CLOSED`.
- Base non-overlap V129: `n=38711`, `WR=75.58%`, `Avg=-1.3706%`, micro `65.92%`, T+1=0.
- Frontier count `0`, near frontier count `0`.
- Best-looking cost-control rule: `BOS_CONTINUATION + DEMAND_OB + BULL_CONTINUATION + entry_vs_avwap<=-1 + target_rr>=0.8`: `n=53`, `WR=84.91%`, `Avg=3.7496%`, `min_year_n=7`, `all_year_WR_min=57.14%`, micro `1.89%` — fails size/year/Avg/micro gates.
- Several very high-WR rules (e.g. reclaim close/volume strength) are mostly micro-target wins: `WR≈95-98%` but `Avg<1%`, `micro≈60-80%`; unusable.

Conclusion:
- Anchored VWAP/cost-control features alone do not create a V175-grade child engine under realistic target exits.
- The apparent high WR is mostly tiny BSL/target wins, not a production-quality edge.

## V190 — A-share limit-up / attention-memory pre-entry source
Artifact: `/root/.hermes/smc_audit/v190_limitup_attention_memory_20260625_150832/`

Source/evaluation:
- V129 realistic target-exit rows.
- Features computed before entry from raw daily OHLCV: prior 20/60/120-day limit-up count, near-limit-up count, volume impulse count, days since attention, entry vs attention candle midpoint/high, prior 5-day volume and return state.
- Excludes V175 overlap; audit-only.

Result:
- Decision: `V190_NO_RESEARCH_CHILD_PASS__LIMITUP_ATTENTION_CLOSED`.
- Frontier count `0`, near frontier count `0`.
- Top rules again came from `FVG_Demand + BULL_CONTINUATION + low chase/risk`, with `WR≈84-85%` but `Avg<0` and micro `~74-76%`.
- Limit-up/attention variables did not lift Avg or yearly robustness.

Conclusion:
- A-share attention/limit-up memory does not rescue the V128 target-exit pool. It mainly increases tiny target hits and still fails average return and yearly stability.

## V191 — Eastmoney board/sector peer confirmation
Artifact: `/root/.hermes/smc_audit/v191_board_peer_confirmation_20260625_151759/`
Board cache: `/root/.hermes/smc_audit/v191_eastmoney_board_members_cache.json`

Source/evaluation:
- Eastmoney board list fetched through direct HTTP `push2.eastmoney.com` with proxy bypass because AkShare HTTPS/proxy failed.
- Full current board map: `496` boards, `5612` mapped stock codes; local kline coverage `4657` symbols.
- Features are computed before entry from peer OHLCV: max/avg peer positive breadth over 1d/5d, board median 1d/5d return, board limit-up rate, stock vs peer median 5d relative strength.
- Excludes V175 overlap; V129 realistic target exits; audit-only.

Result:
- Decision: `V191_NO_RESEARCH_CHILD_PASS__BOARD_PEER_CONFIRMATION_CLOSED`.
- Frontier count `0`, near frontier count `0`.
- Best board-driven rule (`FVG_Demand + BEAR_RISK + peer_med5>=12`) only `n=50`, `WR=90%`, `Avg=-0.0609%`, `min_year_n=1`, micro `60%`; unusable.
- Broader top rules reverted to the same micro-profit FVG/BULL_CONTINUATION cluster with negative average.

Conclusion:
- Current-board peer breadth/relative strength does not produce a non-overlap V175 child engine. It is not enough to overcome V129 target-exit negative expectancy and micro-profit pollution.

## Consolidated closure after V191
Closed additional directions:
1. Institutional-cost / anchored VWAP control over V128 candidates.
2. A-share limit-up / attention-memory overlays.
3. Eastmoney board/sector peer confirmation overlays.

Important interpretation:
- New pre-entry features were tested, not just old artifact slicing.
- All three failed because the V128/V129 pool's realistic target geometry is dominated by tiny target wins and POI break losses.
- High WR in V189-V191 is mostly micro-profit pollution; it is explicitly unusable under the gate.

## Remaining direction
The research loop should not continue with more scalar filters over V128/V167/V172/V175. The remaining valid paths require a genuinely new data/semantic layer:
- true historical intraday data source with coverage across 2023-2026 for execution/TIME diagnostics;
- a rebuilt generator whose target is not prior tiny BSL but a structurally meaningful liquidity pool with pre-entry RR quality;
- a sector/industry dataset with historical membership and fundamentals/flow, not only current Eastmoney board membership;
- operationally, V175 active picks can be rematerialized from latest V128, but that is sync hygiene, not a new strategy edge.

Until one of those is available, V175 remains the only production-usable engine and post-V175 research should stop artifact-slicing loops.