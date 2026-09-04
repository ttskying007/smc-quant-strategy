# V233/V234 post-V231 loss frontier closure

Date: 2026-06-27

## Trigger
Use when continuing SMC research after V185 productionization and V231 historical production-gate candidate, especially when the user asks whether remaining low-WR/losing rows have been fully analyzed and what direction should be researched next.

## Predeclared usability gates

A new post-V231 production candidate must be source-side and non-leaking, with:

| metric | production gate |
|---|---:|
| T+1 violations | 0 |
| `n` | >= 500, or >= 520 for overlay+new-supply combined tests |
| `min_year_n` | >= 70 |
| `WR` | >= 92% |
| `AvgPnL` | >= 7.1% |
| `all_year_WR_min` | >= 89% |
| `micro_profit_pct` | <= 1% |
| current scanner | non-expired actionable rows required before watchlist/API routing |

Research overlay can be noted only if it is source-side, non-leaking, and materially improves WR/Avg without breaking year stability, but it must not be routed to production until the production gate and current scanner gate pass.

## Artifacts

- V233 all-feature exploratory frontier: `/root/.hermes/smc_audit/v233_v231_remaining_loss_root_cause_frontier_no_write_20260627_111510/`
- V233B source-only frontier: `/root/.hermes/smc_audit/v233b_v231_source_only_frontier_no_write_20260627_111718/`
- V234 overlay + new supply probe: `/root/.hermes/smc_audit/v234_fast_v233_overlay_plus_new_supply_probe_no_write_20260627_113030/`
- V231 daily current shadow rerun: `/root/.hermes/smc_audit/v231_daily_current_shadow_audit_no_write_20260627_113126/`

All were no-write research/shadow artifacts.

## Baseline context

V231 historical candidate remains the strongest post-V185 historical production-gate result:

| n | WR | AvgPnL | minYear | yearWRmin | micro | losses |
|---:|---:|---:|---:|---:|---:|---:|
| 541 | 91.68% | 7.0867% | 73 | 88.75% | 0.9242% | 45 |

Component split showed the remaining weakness is still the inherited V175 baseline rows, not the V230 new child supply:

| component | n | WR | AvgPnL | minYear | yearWRmin | losses |
|---|---:|---:|---:|---:|---:|---:|
| V175_BASELINE | 197 | 86.80% | 6.4018% | 33 | 83.33% | 26 |
| V211_CHILD | 170 | 95.29% | 7.3401% | 19 | 87.88% | 8 |
| V185_CHILD | 87 | 93.10% | 8.0206% | 3 | 82.35% | 6 |
| V230_NEW_CHILD | 87 | 94.25% | 7.2083% | 4 | 89.80% | 5 |

## Remaining loss root cause

The remaining low-WR rows are mainly old V175 baseline rows with source-side entry-quality problems:

- high `reclaim_close_pos`: reclaim candle closes too high, turning confirmation into chase;
- high `v132_reclaim_body_range_pct`: over-strong reclaim body, next-open entry already overheated;
- higher `risk_pct`: wider loss budget and worse damage per failure;
- wider `v85_zone_width_pct`: less precise POI semantics;
- inherited V175 rows lack V211/V230 persistence/ACCUMULATION supply quality.

This confirms that the remaining problem is candidate quality/source semantics, not generic TP/SL or delayed retouch execution.

## V233B source-only overlay result

Source-only frontier, excluding outcome/path/date/price-style leaks, found research overlays but no production pass:

| rule | n | WR | AvgPnL | minYear | yearWRmin | micro | decision |
|---|---:|---:|---:|---:|---:|---:|---|
| `reclaim_close_pos <= 0.9592` | 514 | 92.2179% | 7.1871% | 66 | 90.9091% | 0.9728% | research only |
| `v132_reclaim_body_range_pct <= 62.5` | 487 | 92.1971% | 7.1510% | 69 | 89.8551% | 0.6160% | research only |
| `reclaim_close_pos <= 0.9592 AND v132_reclaim_body_range_pct <= 62.5` | 463 | 92.6566% | 7.2453% | 62 | 90.3226% | 0.6479% | research only |

Decision: `V233B_SOURCE_ONLY_RESEARCH_OVERLAY_FOUND__NOT_PRODUCTION`.

Reason: WR/Avg/yearWR/micro are good, but sample/year coverage remains below production gate (`min_year_n < 70` and/or `n` below threshold). Do not promote these overlays directly.

## V234 overlay + new supply result

Tested:

```text
base = V231 rows where reclaim_close_pos <= 0.9592
+ non-overlap rows from V230 candidate pool
```

V234 base metrics:

| n | WR | AvgPnL | minYear | yearWRmin | micro | losses |
|---:|---:|---:|---:|---:|---:|---:|
| 514 | 92.2179% | 7.1871% | 66 | 90.9091% | 0.9728% | 40 |

Candidate pool: 10,280 non-overlap rows.

Grid dimensions:
- `market_state`
- `event_type`
- `v132_bull_count_3`
- `v132_post_zone_pullback_depth_pct_3`
- `risk_pct`
- `v132_reclaim_body_range_pct`
- `v228_all_strong1_pct`

Result: no combination passed the strict frontier. Decision: `V234_FAST_NO_NEW_SUPPLY_FRONTIER`.

Interpretation: forcing extra new supply into the V233B overlay either degrades quality or fails width/year/micro constraints. Do not continue this exact overlay-plus-supply grid.

## Current scanner status

Rerunning V231 current shadow monitor produced:

| metric | value |
|---|---:|
| latest market date | 20260626 |
| dry recent45 rows | 2014 |
| raw rule rows | 1 |
| dedup rows | 1 |
| expired rows | 1 |
| overlap rows | 0 |
| time-order bad | 0 |
| active outcome pollution | 0 |
| new actionable rows | 0 |

Decision: `V231_NO_CURRENT_ACTIONABLE_ROWS__KEEP_SHADOW_MONITORING_NO_WRITE`.

V231 remains a historical production-gate candidate but cannot be written to active watchlist until a non-expired current row appears and endpoint mapping smoke passes.

## What is usable / not usable

Usable now:
- V185 remains the current production baseline.
- V231 remains the best historical post-V185 production-gate candidate.
- V231 daily current shadow monitoring should continue.

Not usable now:
- V233B overlays as production: sample/year coverage short.
- V234 overlay + new supply: no strict frontier found.
- Any further scalar-only tuning of V185/V231 rows unless it beats the strict V231-level gate.
- V231 live/watchlist routing today: current scanner has zero non-expired actionable rows.

## Next research direction

Do not continue micro-threshold tuning on V185/V231 rows. The next qualitative-change path is a fresh V235 generator that creates new candidate supply rather than filtering old rows:

```text
Environment -> Accumulation/Recovery -> Sweep/Takeover -> POI reaction -> non-chase entry
```

V235 should require:
- cool/medium market participation, not overheated breadth;
- ACCUMULATION/RECOVERY environment priority;
- SSL sweep + takeover persistence or equivalent institutional event;
- Demand OB / OB+FVG with narrow, precise zones;
- reclaim that is strong enough to confirm but not too high (`reclaim_close_pos`/body not overheated);
- controlled `risk_pct` and `v85_zone_width_pct`;
- full-market multi-year validation with T+1 and year stability.

## Pitfall

A high-WR overlay such as `reclaim_close_pos <= 0.9592` is tempting because it clears WR/Avg/micro. Do not call it production-ready unless `min_year_n >= 70` and current scanner emits non-expired actionable rows. Otherwise it is only diagnostic evidence that V175-style chase remains the weakness.
