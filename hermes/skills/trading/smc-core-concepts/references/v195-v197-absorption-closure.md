# V195-V197 absorption generator closure

Date: 2026-06-25

## Trigger
Use when continuing post-V175 SMC research after V192-V194, especially if considering raw absorption / failed-breakdown demand generators, source-quality filters, or market-breadth overlays.

## Fixed usability gates

Research child engine usable:
- 100% non-overlap vs V175;
- `n >= 120`;
- `min_year_n >= 20`;
- `WR >= 86%`;
- `AvgPnL >= 6.5%`;
- `all_year_WR_min >= 83%`;
- `micro_profit_pct <= 1%`;
- T+1 violations = 0.

Production upgrade usable:
- combined engine `n >= 260`;
- `min_year_n >= 40`;
- `WR >= 84%`;
- `AvgPnL >= 6.2%`;
- `all_year_WR_min >= 82%`;
- `micro_profit_pct <= 1%`;
- T+1 violations = 0;
- no frontend/watchlist/API mutation before dry-run passes.

## V195 — raw absorption demand reclaim generator

Artifact: `/root/.hermes/smc_audit/v195_raw_absorption_generator_20260625_164256/`

Contract:
- raw daily K-line cache only;
- not V128/V167/V175 filtering;
- detects impulse/sweep-origin demand zone, multiple demand tests, lower-wick absorption, reclaim, next-open entry;
- T+1 enforced;
- shadow-only, no frontend/watchlist/API writes.

Result:
- Decision: `UNUSABLE`.
- `n=1636`, `WR=43.40%`, `Avg=2.3344%`, `median=-2.938%`.
- `min_year_n=100`, yearly WR: 2023 `18.0%`, 2024 `30.21%`, 2025 `51.95%`, 2026 `42.11%`.
- T+1 violations = 0.
- Exit mix: `SL=653`, `GAP_SL=50`, `EXIT_ZONE_CLOSE_BREAK_NEXT_OPEN=102`, `TP=288`, `TIME=543`.
- Overlap vs V175 by symbol+entry_date only `1`; non-overlap `1635`.

Interpretation: raw absorption/reclaim produces some large winners but is not stable. 2023/2024 failure proves it is not a robust production child.

## V196 — source-quality frontier over V195

Artifact: `/root/.hermes/smc_audit/v196_v195_absorption_quality_frontier_20260625_165011/`

Tested source-side fields only:
- shock type;
- test count;
- lower-wick dominance;
- reclaim close position;
- reclaim volume vs test volume;
- event volume vs test volume;
- RR / chase / risk / zone width.

Result:
- Decision: `V196_NO_RESEARCH_CHILD_PASS__ABSORPTION_QUALITY_FRONTIER_CLOSED`.
- Research pass count: `0`; near frontier count: `0`.
- Best-looking rules improved Avg but failed size/year stability:
  - `shock=SWEEP & reclaim_pos>=0.7 & chase<=0.5`: `n=67`, `WR=62.69%`, `Avg=5.5651%`, `min_year_n=2`, `yearMin=20.0%`, micro `0%`.
  - `shock=SWEEP & reclaim_vol_vs_test>=1.2 & chase<=0.5`: `n=62`, `WR=61.29%`, `Avg=5.4716%`, `min_year_n=1`, `yearMin=0%`.

Interpretation: there is a narrow current-regime SWEEP/chase edge, but it is not year-stable and not enough for a research child.

## V197 — V195 absorption + full-market breadth context

Artifact: `/root/.hermes/smc_audit/v197_v195_absorption_breadth_context_20260625_165810/`

Contract:
- attaches pre-entry market breadth at `reclaim_date` from `/root/.hermes/smc_audit/v185_market_breadth_cache.csv`;
- tests breadth predicates (`br_r5_pos`, `br_above_ma20`, `br_weak_r5`, `br_net_strong_weak`) combined with V195 source-quality predicates;
- T+1 and non-overlap maintained;
- shadow-only.

Result:
- Decision: `V197_NO_RESEARCH_CHILD_PASS__ABSORPTION_BREADTH_CONTEXT_CLOSED`.
- Research pass count: `0`; near frontier count: `0`.
- Best rules again lifted Avg but failed coverage/year stability:
  - `br_net_strong_weak>=0 & shock=SWEEP & chase<=0.5`: `n=59`, `WR=71.19%`, `Avg=6.8063%`, `min_year_n=2`, `yearMin=20.0%`, micro `0%`.
  - `br_r5_pos>=50 & shock=SWEEP & chase<=0.5`: `n=54`, `WR=72.22%`, `Avg=6.7834%`, `min_year_n=2`, `yearMin=20.0%`, micro `0%`.

Interpretation: breadth can identify a high-Avg 2025-heavy pocket, but it does not create a robust 2023-2026 child engine. It remains an observation, not production/research pass.

## Closed after V197

Closed:
1. raw failed-breakdown / absorption demand reclaim generator from daily OHLCV;
2. source-quality filters over that absorption generator;
3. broad-market breadth overlay over that absorption generator.

Important nuance:
- V197 produced the first post-V175 pocket with Avg > 6.5 and zero micro pollution, but it is only `n≈54-59` and yearly unstable. This is **not usable** under the fixed gates.
- Do not promote it, do not write frontend/watchlists, and do not weaken gates to fit it.

## Remaining direction

The old search substrate is exhausted through V197:
- V128/V129 realistic exits are dominated by micro-profit target wins and POI break losses.
- Raw daily OHLCV generators (classical sweep, continuation, accumulation, impulse, limit-up retest, absorption) all fail robust year-stable gates.
- Breadth/sector/current-board overlays improve pockets but do not solve supply quality.

Next qualitative change requires a genuinely new information layer, not another scalar filter:
1. true historical intraday data across 2023-2026 for execution and TIME-row diagnosis;
2. historical sector/industry membership + sector-level lifecycle, not current-board-only mapping;
3. stronger pre-entry target model that rejects micro BSL targets at candidate creation;
4. active-pick rematerialization from latest V128 as operational sync only, not strategy research.

Until one of those new data/semantic layers is available, V175 remains the only production-usable engine in this chain.
