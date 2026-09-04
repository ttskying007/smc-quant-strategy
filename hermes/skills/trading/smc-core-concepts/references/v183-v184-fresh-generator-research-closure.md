# V183-V184 fresh-generator research closure

Date: 2026-06-26

## Trigger

Use after V175/V180-V182 closure when deciding whether to continue with old-artifact filters or build a fresh SMC candidate generator.

## Predeclared gates

Production usable:
- non-leaking source-side rule;
- T+1 violations = 0;
- `n >= 260`;
- `min_year_n >= 40`;
- `WR >= 84%`;
- `AvgPnL >= 6.2%`;
- `all_year_WR_min >= 82%`;
- `micro_profit_pct <= 1%`;
- no frontend/watchlist/API mutation before dry-run passes.

Research child usable:
- 100% non-overlap vs production engine;
- `n >= 120`;
- `min_year_n >= 20`;
- `WR >= 86%`;
- `AvgPnL >= 6.5%`;
- `all_year_WR_min >= 83%`;
- T+1 violations = 0.

## V183 fresh reversal generator

Artifact: `/root/.hermes/smc_audit/v183_context_first_generator_20260626_140811/`

Built from daily K-line cache only, not V128/V167/V175 trades.
Generation order:
`drawdown environment -> SSL sweep -> CHOCH -> demand POI -> touch/reclaim -> next-open entry -> T+1 semantic exit`.

Full-market scan:
- files 4655, loaded 4632, too_short 23, errors 0.
- Decision: `V183_CONTEXT_FIRST_GENERATOR_NO_USABLE_ENGINE__NO_WRITE`.
- Best raw variant: `v183_c_deep_discount`, n=59, WR=54.24%, Avg=2.3249%, min_year=1, T+1=0.
- Combined dedupe: n=196, WR=48.47%, Avg=0.7835%, SL+GAP_SL=48.47%, T+1=0.

Root cause:
- Fresh reversal semantics generate correct-looking stories but POI survival is poor: SL/GAP_SL dominates around 44-55%.
- 2023/2024 rows are especially weak; filtering by simple pre-entry features did not create a robust multi-year child.
- Small high-WR pockets existed but had tiny/year-concentrated samples and failed all gates.

## V184 fresh continuation generator

Artifact: `/root/.hermes/smc_audit/v184_fast_accumulation_breakout_retest_20260626_142458/`

Built from daily K-line cache only.
Generation order:
`accumulation/base contraction -> structural breakout/BOS -> retest demand shelf -> reclaim -> next-open entry -> T+1 semantic exit`.

Full-market scan:
- files 4655, loaded 4632, too_short 23, errors 0.
- Decision: `V184_FAST_ACCUMULATION_BREAKOUT_RETEST_NO_USABLE_ENGINE__NO_WRITE`.
- Combined dedupe: n=1262, WR=46.75%, Avg=1.6123%, min_year=1, yearWRmin=31.31%, T+1=0.
- Best raw variant by Avg: `v184f_b_30d_tight`, n=459, WR=47.71%, Avg=1.8318%, T+1=0.

Root cause:
- Base breakout/retest is broad supply, not high-quality smart-money demand by itself.
- TP wins exist, but SL/GAP_SL remains ~44%; TIME rows are 20-25%, so the issue is signal supply quality, not only exit handling.
- 2025 concentration appears in some breadth-filtered pockets; this is not production-robust.

## Market breadth overlay check

A market-breadth overlay was tested using only pre-entry daily cache data:
- `breadth20`: percent of stocks with positive 20-day return.
- `near60hi`: percent of stocks closing within 10% of 60-day high.

Result:
- It improved some small/year-concentrated pockets but did not pass research or production gates.
- Example: V184 combined with `breadth20 60-65 & near60hi>=50` gave n=23, WR=82.61%, Avg=6.46%, but only 2025 rows; unusable.
- Example: V183 combined with strong breadth gave n=28, WR=82.14%, Avg=5.59%, min_year=1; unusable.

## Decision

Closed paths:
1. Filtering V167/V172/V175 leftovers.
2. Generic V175 exit overlays.
3. Delayed V128 reclaim confirmation.
4. Fixed runner exits on V181 child.
5. Fresh daily reversal generator without stronger POI survival proof.
6. Fresh daily accumulation breakout/retest generator without stronger smart-money quality proof.
7. Simple market-breadth overlay as a standalone production gate.

Current production-valid artifact remains V175 semantic split. V183/V184 are shadow-only research failures and must not be promoted.

## Next research direction

The next qualitative direction is not another scalar filter. Build a **POI survival classifier from pre-entry path structure** and then use it to generate candidates, not post-filter outcomes.

Required source-only features to test next:
- post-touch reaction strength before entry: reclaim body %, reclaim close position, higher-low count after touch;
- POI death risk before entry: number of closes below zone, max wick penetration, time spent inside zone;
- supply overhead geometry: nearest BSL distance, resistance-density above entry, target path cleanliness;
- market regime only as permission, not as final alpha;
- candidate must remain K-line/source-derived and shadow-only until passing gates.

Do not call V183/V184 failure a front-end/API issue. It is signal-supply quality: correct-looking stories still die at the POI too often.