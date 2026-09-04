# V183-V206 V185 production-candidate closure

Date: 2026-06-26

## Trigger

Use after V175/V180-V182 closure when deciding whether continued SMC research produced a qualitative change, and whether V185 can be considered usable.

## Predeclared gates

Production combined engine is usable only if all pass:
- non-leaking source-side selector;
- no same-day/T+1 violations;
- combined `n >= 260`;
- `min_year_n >= 40`;
- `WR >= 84%`;
- `AvgPnL >= 6.2%`;
- `all_year_WR_min >= 82%`;
- `micro_profit_pct <= 1%`;
- no frontend/watchlist/API mutation before shadow dry-run and endpoint mapping pass.

Standalone child engine is research-usable only if:
- non-overlap vs V175 = 100%;
- `n >= 120`;
- `min_year_n >= 20`;
- `WR >= 86%`;
- `AvgPnL >= 6.5%`;
- `all_year_WR_min >= 83%`;
- T+1 violations = 0.

## Closed failed branches

After V180-V182 closed exit-layer/scalar-filter/leftover routes, further generator attempts were audited:
- V183/V184 fresh context/lifecycle and reaction-confirmation generators: failed, broad WR only ~40-50%, no production gate.
- V185 raw BOS continuation fast generator: failed (`n=35704`, WR `41.06%`, Avg `0.299%`, SL rate `56.6%`), despite no leak/T+1=0.
- V190/V191 board/peer/limit-up style filters: failed due micro-profit pollution, weak year stability, or negative Avg.
- Multiple non-leak frontier probes failed until the V185 combined candidate was formalized.

## Qualitative change found: V185 combined engine

Formal artifact:
- `/root/.hermes/smc_audit/v185_formal_candidate_v175_plus_child_20260626_001218/`
- Decision: `V185_COMBINED_PRODUCTION_GATE_PASS__SHADOW_ONLY`.

Rule:
- Child selector: `V167 excluded non-overlap AND v132_bull_count_3>=3 AND risk_pct>=3.0133 AND v132_reclaim_body_range_pct>=50`.
- Execution: `V184 p50_time10_after_entry` — 50% at TP, rest BE-locked, close at entry+10 bars if no stop.
- Selector leak fields: `[]`.
- Child overlap with V175: `0`.
- Same-day/T+1 violations combined: `0`.
- No production/frontend/watchlist writes.

Metrics independently rechecked in V206:

| Pool | n | WR | AvgPnL | minYear | yearWRmin | micro | same-day |
|---|---:|---:|---:|---:|---:|---:|---:|
| V175 baseline | 247 | 83.81% | 6.0493% | 38 | 81.71% | 1.21% | 0 |
| V185 child | 87 | 93.10% | 8.0206% | 3 | 82.35% | 0.00% | 0 |
| V185 combined | 334 | 86.23% | 6.5628% | 41 | 82.81% | 0.90% | 0 |

Interpretation:
- V185 child alone is **not** standalone production/research child by the strict child gate because `n=87` and `min_year_n=3` are too small.
- V185 combined with V175 **does pass the production combined gate** and is the first post-V175 qualitative improvement: larger sample, higher WR, higher AvgPnL, lower micro-profit, T+1 clean.

## Robustness

Artifact:
- `/root/.hermes/smc_audit/v186_v185_robustness_sensitivity_20260626_001356/`
- Decision: `V186_ROBUST_ENOUGH_FOR_SHADOW_PROMOTION_DESIGN`.
- 9/49 nearby `(risk_thr, body_thr)` variants passed combined gate.
- Chosen rule `risk>=3.0133, body>=50`: combined `n=334`, WR `86.23%`, Avg `6.5628%`, minYear `41`, yearWRmin `82.81%`, micro `0.9%`.
- Leave-one-year-out remained acceptable except the 2024 holdout has micro `1.44%`, so V185 should be promoted only with shadow monitoring, not overclaimed as final.

## Shadow promotion bridge

V203 formal readiness/current dry-run:
- `/root/.hermes/smc_audit/v203_v185_formal_readiness_current_dryrun_20260626_064312/`
- Decision: `V203_V185_FORMAL_CANDIDATE_VALIDATED__PROMOTION_BRIDGE_NEXT_SHADOW_ONLY`.
- Formal integrity: eligible rows `87`, child rows `87`, missing/extra `0`, overlap V175 `0`, selector leak `[]`, same-day `0`.
- Current latest V128 dry-run produced 6 active shadow rows, latest entry date `20260616`.

V204 shadow materialization:
- `/root/.hermes/smc_audit/v204_v185_shadow_materialization_no_write_20260626_064406/`
- Decision: `V204_SHADOW_MATERIALIZATION_READY__NO_PRODUCTION_WRITE`.
- Historical rows `334`, active rows `6`.
- Active old event labels `0`, outcome pollution `0`, same-day `0`, write flags all false.

V205 endpoint mapping smoke:
- `/root/.hermes/smc_audit/v205_v185_shadow_endpoint_mapping_smoke_20260626_085805/`
- Decision: `V205_SHADOW_ENDPOINT_MAPPING_PASS__READY_FOR_CODE_IMPACT_ANALYSIS`.
- Mock `/api/picks` rows `6`, missing required fields `{}`, old labels `0`, outcome pollution `0`, write pollution `0`, shadow false `0`.

V206B live guard correction:
- `/root/.hermes/smc_audit/v206b_v185_shadow_live_guard_corrected_20260626_132348/`
- Decision: `V206B_V185_SHADOW_LIVE_GUARD_CORRECTED__NO_PRODUCTION_WRITE`.
- Active rows `6`, Tencent quotes fetched for all 6.
- Status: `LIVE_ABOVE_ENTRY=4`, `LIVE_BELOW_ZONE_LOW=2`, avg live PnL `+8.722%`.
- Important correction: active shadow rows do **not** contain TP/SL, so V206B only classifies live price vs entry/zone; do not classify TP/SL from missing TP/SL fields.

## Current decision

Usable:
- V175 remains valid production baseline.
- V185 combined is a validated **shadow production candidate** and constitutes a qualitative improvement over V175.

Not usable:
- V185 child alone is not standalone due low yearly coverage.
- Failed V183/V184/V185 raw/V190/V191 branches should not be continued by more scalar filters.
- Do not use missing TP/SL in active shadow rows to claim TP/SL status.

Next concrete step before any production routing:
1. Run GitNexus impact analysis on the SMC frontend/API router symbols in `smc_unified.py`.
2. Patch only the version routing/materialization paths needed to expose V185 shadow/production candidate.
3. Restart `smc_unified.py:8890`.
4. Verify `/api/summary`, `/api/picks?version=V185`, `/api/live-prices?version=V185`, field pollution, active count, and no historical active pollution.
5. Keep V185 in shadow/production-candidate mode until live guard and current scanner refresh prove stable.
