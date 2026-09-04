# V183-V186 post-V175 generator closure

Date: 2026-06-25

## Trigger
Use when deciding whether post-V175 improvement can come from V128 target geometry, a fresh daily K-line lifecycle generator, or stricter reclaim confirmation.

## Predeclared usable / unusable gates
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
- higher WR by cutting AvgPnL or creating BE/micro-profit pollution;
- simply filtering/relabeling old V167/V172/V175 rows;
- daily generic OB/reclaim generator whose TP/SL classes are not separable by source-side structural features.

## Completed probes

### V183 target-geometry shadow probe
Artifact: `/root/.hermes/smc_audit/v183_target_geometry_shadow_probe_20260625_190206/`

Input: `/root/.hermes/smc_audit/v128_parallel_scanner_candidate_audit_20260620/v128_parallel_shadow_backtest_all.csv` plus K-line cache.

What it tested:
- source-side target geometry before entry: nearest prior BSL/swing high, recent high RR, range position, impulse/low-break hygiene;
- V175 overlap removed for child-engine testing;
- no outcome fields used for selection.

Result:
- feature rows: `38492`, missing/unanchored `523`, V175 overlap preserved separately;
- research pass count: `0`;
- best frontier still failed gate: `impulse AND quiet_lows AND bear_risk AND wide20 AND chase15` had `n=486`, `WR=46.5%`, `Avg=7.1358%`, yearly WR min `35.23%`, micro `1.85%`, T+1=0.

Decision: `V183_TARGET_GEOMETRY_NO_USABLE_CHILD__NEXT_TRUE_GENERATOR`.

Interpretation: pre-entry target geometry on top of existing V128 rows can raise Avg in some broad buckets but does not create stable WR/year coverage. It is not a production/research child engine.

### V184 fresh lifecycle generator
Artifact: `/root/.hermes/smc_audit/v184_lifecycle_generator_shadow_20260625_190528/`

What it tested:
- fresh generation directly from K-line cache, not V128/V167 filtering;
- lifecycle: structural bear/pullback context → demand OB → touch/reclaim reaction → target geometry → T+1 replay;
- scanned `4652` daily cache files.

Result:
- generated `130498` rows;
- base: `WR=42.93%`, `Avg=0.4846%`, median `-2.0172%`, yearly WR min `37.35%`;
- non-overlap vs V175: `130443` rows, `WR=42.92%`, `Avg=0.4821%`;
- T+1 violations `59` came from same-date/duplicate-date data artifacts and were excluded in subsequent mining;
- best simple top rule `target_rr>=2.5` still only `WR=43.11%`, `Avg=0.6221%`.

Decision: `V184_LIFECYCLE_GENERATOR_NO_GATE__REBUILD_EVENT_DEFINITION`.

Interpretation: a generic daily demand-OB + reclaim generator is too broad; it mostly identifies ordinary falling-knife rebounds, not institutional takeover.

### V185 V184 source-rule mining
Artifact: `/root/.hermes/smc_audit/v184_lifecycle_generator_shadow_20260625_190528/v185_v184_source_rule_mining/`

What it tested:
- source-only rules over V184 rows after excluding V175 overlap and T+1 violations;
- thresholds/combinations over risk, chase, zone width, target RR, reclaim close position/body, drawdown, range position, red candle count, lower-low count, V184 score.

Result:
- rows searched: `130384`;
- research pass count: `0`;
- frontier count: `0` under high-WR/high-Avg retention criteria;
- exit group source means were almost indistinguishable:
  - SL avg risk `5.4069`, chase `0.8837`, width `3.1787`, RR `2.3340`, drawdown `23.5087`, range_pos `0.2606`;
  - TP avg risk `5.4399`, chase `0.8680`, width `3.2304`, RR `2.2613`, drawdown `23.6735`, range_pos `0.2830`.

Interpretation: TP and SL outcomes are not separable by these daily source-side geometry features. The generator definition, not the threshold set, is the problem.

### V186 strict lifecycle generator
Artifact: `/root/.hermes/smc_audit/v186_strict_lifecycle_generator_20260625_191739/`

What it tested:
- fresh K-line generator with stricter post-reclaim true-takeover confirmation;
- require 3-bar confirmation after reclaim: bull_count >= 2, no close back inside zone, pullback below zone high <= 2%; entry after confirmation; T+1 replay;
- scanned `4649` daily files.

Result:
- generated `25680` rows, V175 overlap `0`;
- base/nonoverlap: `WR=46.62%`, `Avg=0.6049%`, median `-0.6298%`, yearly WR min `38.68%`, micro `4.82%`, T+1=0;
- best top rules remained around `WR≈46%`, Avg below `0.7%`; no research pass.

Decision: `V186_STRICT_LIFECYCLE_NO_GATE__EVENT_DEFINITION_STILL_TOO_WEAK`.

Interpretation: waiting for short post-reclaim confirmation improves median and removes T+1 issues but does not transform the signal. Generic daily OB/reclaim is still not the missing production-quality supply.

## Closed paths after V183-V186
1. V128 target-geometry filters.
2. Daily K-line generic demand OB/reclaim generator.
3. Post-reclaim 3-bar strict confirmation as a standalone generator.
4. Source-rule mining over generic daily lifecycle rows.

## Current direction
The next qualitative path cannot be “more thresholds” on V128/V184/V186. It must change the event definition itself.

Viable next research direction:
- Build a signal-registry / Pine-reference aligned generator that starts from confirmed swing/liquidity events, not arbitrary down candles.
- Candidate supply must require: confirmed structural anchor → liquidity event or wave takeover → POI generated from that anchor → reaction/entry → structural target.
- Daily generic OB is invalid unless anchored to a confirmed swing/liquidity/wave event.

Use V175 as current production baseline, not as a source for new rows:
- V175 remains valid/current for production economics: `247`, `WR=83.81%`, `Avg=6.0493%`, T+1=0.
- V175 active picks may need rematerialization from latest V128 snapshot when production synchronization is explicitly being performed, but that is a production-sync task, not a research improvement task.
