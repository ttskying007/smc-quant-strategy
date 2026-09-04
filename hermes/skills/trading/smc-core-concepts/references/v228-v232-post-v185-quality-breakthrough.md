# V228-V232 post-V185 research continuation: participation + new supply breakthrough

Date: 2026-06-27

## Trigger
Use when continuing after V185/V211/V221/V227 and the user asks whether low-WR rows have been fully analyzed, what direction remains, and whether continued research produced a qualitative change.

## Predeclared gates
After V214/V185+V211 already improved V185, the next production-quality candidate must beat that stronger baseline, not merely V185:

- source-side / non-leaking selector only;
- T+1 same-day violations = 0;
- `n >= 500`;
- `min_year_n >= 70`;
- `WR >= 90%`;
- `AvgPnL >= 7.0%`;
- `all_year_WR_min >= 88%`;
- `micro_profit_pct <= 1%`;
- no frontend/watchlist/API production writes until independent audit and current scanner smoke pass.

Research overlay only:
- `n >= 450`, `min_year_n >= 55`, `WR >= 90%`, `AvgPnL >= 6.9%`, `all_year_WR_min >= 87%`, `micro <= 1%`, T+1=0.

## Artifacts

- V228 participation overlay on V214: `/root/.hermes/smc_audit/v228_v214_participation_plus_supply_audit_no_write_20260627_053321/`
- V229 independent overlay audit/current smoke: `/root/.hermes/smc_audit/v229_v228_overlay_independent_audit_current_smoke_no_write_20260627_053543/`
- V230 new-supply expansion search: `/root/.hermes/smc_audit/v230_v228_plus_new_supply_expansion_probe_no_write_20260627_053747/`
- V231 independent production-candidate audit: `/root/.hermes/smc_audit/v231_v230_candidate_independent_audit_no_write_20260627_053946/`
- V232 current scanner smoke: `/root/.hermes/smc_audit/v232_v231_current_scanner_smoke_no_write_20260627_054114/`

All are no-write research artifacts: `production_write=false`, `frontend_write=false`, `watchlist_write=false`.

## V228/V229 result: low-WR cause confirmed

V214 baseline (V185 + V211 dedup child):

| n | WR | AvgPnL | minYear | yearWRmin | micro | losses | T+1 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 504 | 89.29% | 6.8250% | 74 | 86.75% | 0.79% | 54 | 0 |

The remaining weak rows are mainly V175 rows occurring after overheated previous-day participation. Best research overlay:

```text
keep all V185_CHILD and V211_CHILD;
keep V175_BASELINE only when previous-day all-market strong1 breadth <= 33.25962
```

Audited V229 metrics:

| set | n | WR | AvgPnL | minYear | yearWRmin | micro | losses | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V214 baseline | 504 | 89.29% | 6.8250% | 74 | 86.75% | 0.79% | 54 | 0 |
| V228_R1 selected | 454 | 91.19% | 7.0633% | 69 | 87.50% | 0.88% | 40 | 0 |
| V228_R1 excluded | 50 | 72.00% | 4.6605% | 5 | 58.33% | 0.00% | 14 | 0 |

Selector fields: `v228_source_bucket`, `v228_all_strong1_pct`, `v228_prev_market_date`; leak fields `[]`; time-order bad `0`.

Interpretation: this is real, non-leaking evidence that overheated prior-day broad participation damages the older V175 demand-reclaim rows. It was research-only because sample/year gates were just short (`n=454`, `minYear=69`, `yearWRmin=87.5`).

## V230/V231 qualitative breakthrough

V230 added **new non-overlap supply** from the V164 replay pool on top of V228_R1, instead of stacking more filters. Independent V231 rule:

```text
Base:
  V228_R1 selected rows

Add new child rows from V164 replay pool, excluding all V214/V185/V211 historical keys:
  market_state == ACCUMULATION
  AND v132_bull_count_3 >= 3
  AND v132_post_zone_pullback_depth_pct_3 <= 5
  AND previous-day all-market strong1 breadth <= 42

Dedup source-side only:
  prefer DEMAND_OB, then OB+FVG, then FVG_Demand;
  prefer SSL_SWEEP_CHOCH_REVERSAL before BOS_CONTINUATION;
  then lower risk_pct and lower entry_chase_above_zone_pct.
```

V231 independent audit:

| set | n | WR | AvgPnL | minYear | yearWRmin | micro | losses | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V228_R1 base | 454 | 91.19% | 7.0633% | 69 | 87.50% | 0.88% | 40 | 0 |
| V230 new child | 87 | 94.25% | 7.2083% | 4 | 89.80% | 1.15% | 5 | 0 |
| V231 combined | 541 | 91.68% | 7.0867% | 73 | 88.75% | 0.924% | 45 | 0 |

Integrity:
- selector leak fields: `[]`;
- previous market date < entry date: `time_order_bad_count=0`;
- raw eligible rows: `106`;
- dedup child rows: `87`;
- duplicate `symbol+entry_date` groups corrected by source-side dedup: `15`;
- overlap with V214/V185/V211 history: `0`;
- overlap with V228 base: `0`;
- production gate: **PASS**;
- decision: `V231_PRODUCTION_GATE_PASS__SHADOW_ONLY_NEEDS_CURRENT_SCANNER_ENDPOINT_MAPPING`.

This is a qualitative change over V185/V214 because it changes both dimensions:
1. it removes overheated broad-participation V175 rows; and
2. it adds fresh ACCUMULATION-state takeover supply under cool-market conditions.

## Current scanner status (V232)

V232 applied V231 rule to the latest V164 dry-run scanner snapshot (`latest_market_date=20260626`):

| metric | value |
|---|---:|
| recent45 dry rows | 2014 |
| raw V231 current rule rows | 1 |
| dedup rows | 1 |
| overlap rows | 0 |
| expired rows | 1 |
| new actionable rows (`bars_since_entry <= 10`) | 0 |
| existing V185 active rows | 6 |

Decision: `V232_NO_NEW_ACTIONABLE_CURRENT_ROWS__HISTORICAL_GATE_PASS_ONLY_NO_WRITE`.

Operational implication: V231 is a validated historical production-gate candidate, but it has no new current actionable row on the latest scanner snapshot. Do not route it to frontend/live watchlist as active production until a future current scanner run yields non-expired rows and endpoint mapping passes.

## What is usable / not usable

Usable now:
- V185 remains the production baseline currently routed to cron/API/frontend.
- V214/V185+V211 remains a validated historical combined improvement but has no current active increment.
- V231 is the next best historical production-gate candidate and should be promoted only to shadow-candidate status for continued scanner monitoring.

Not usable now:
- V228/V229 alone: research overlay only; fails production by sample/yearWR.
- V230 raw search before V231 independent audit: not usable without V231 integrity checks.
- V231 live production/watchlist routing today: not usable because V232 found 0 new actionable current rows.
- Any further scalar-only filtering of V185/V175/V214 rows: closed unless it beats the strict V231-level gate.

## Next required step

Continue with V231 shadow monitoring/current rematerialization, not production routing:

1. Add a no-write V231 daily current scanner audit that runs after the V164/V185 refresh.
2. It should emit current non-expired V231 rows only when:
   - selector leak fields `[]`;
   - previous market date < entry date;
   - overlap with existing V185/V214/V231 history is 0;
   - `bars_since_entry <= 10`;
   - T+1 contract and field pollution checks pass.
3. If it produces current actionable rows, then run endpoint mapping smoke before any frontend/API production write.

## V231 daily shadow monitor implemented 2026-06-27

Implemented the required no-write monitor:

- Script: `/root/.hermes/scripts/v25/v231_daily_current_shadow_audit.py`
- Latest summary: `/root/.hermes/smc_audit/v231_daily_current_shadow_audit_latest.json`
- Daily ops integration: `/root/.hermes/scripts/v25/smc_daily_ops.py` now runs `run_v231_shadow_audit()` after V185 rematerialization and embeds `v231_shadow_audit` into `ops_latest.json`.

Validation on 2026-06-27:

| check | result |
|---|---|
| `py_compile` | ok for `v231_daily_current_shadow_audit.py` and `smc_daily_ops.py` |
| dry source | `/root/.hermes/smc_audit/v164_corrected_scanner_dry_run_20260622/v164_dryrun_rows.json` |
| latest market date | `20260626` |
| recent45 rows | `2014` |
| raw V231 current rows | `1` |
| dedup rows | `1` |
| expired rows | `1` |
| overlap rows | `0` |
| time-order bad | `0` |
| active outcome pollution | `0` |
| selector leak fields | `[]` |
| new actionable rows | `0` |
| decision | `V231_NO_CURRENT_ACTIONABLE_ROWS__KEEP_SHADOW_MONITORING_NO_WRITE` |
| `smc_daily_ops.py` | ok=true, version V185, shadow V231 |

Interpretation: V231 remains the best historical production-gate candidate, but current scanner has no non-expired actionable V231 increment yet. Continue daily shadow monitoring; do not route V231 to frontend/API/watchlist until `new_actionable_rows > 0` and endpoint mapping smoke passes.

GitNexus caveat: `npx gitnexus impact`/`detect-changes` were attempted before/after editing `smc_daily_ops.py`, but Node 26 fails to load `tree-sitter-c-sharp` native build (`abi=147`). Record as tooling blocker, not a pass.

## V233-V236 continued low-WR analysis + V235 qualitative upgrade

Artifacts:
- V233 V231 loss frontier: `/root/.hermes/smc_audit/v233_v231_loss_frontier_no_write_20260627_113637/`
- V234 new-supply frontier: `/root/.hermes/smc_audit/v234_v231_new_supply_frontier_no_write_20260627_114529/`
- V235 true market-breadth + new-supply search: `/root/.hermes/smc_audit/v235_v231_market_breadth_new_supply_no_write_20260627_114711/`
- V236 independent audit/current smoke: `/root/.hermes/smc_audit/v236_v235_independent_audit_current_smoke_no_write_20260627_114943/`
- V236 daily shadow monitor script: `/root/.hermes/scripts/v25/v236_daily_current_shadow_audit.py`
- Latest V236 shadow summary: `/root/.hermes/smc_audit/v236_daily_current_shadow_audit_latest.json`

Predeclared next strict gate over V231:

| gate | threshold |
|---|---:|
| n | >=500 |
| min_year_n | >=70 |
| WR | >=92% |
| AvgPnL | >=7.2% |
| all_year_WR_min | >=89% |
| micro_profit_pct | <=1% |
| T+1 | 0 |

V233 showed scalar pruning alone is not enough:

| candidate | n | WR | Avg | minYear | yearWRmin | loss |
|---|---:|---:|---:|---:|---:|---:|
| V231 baseline | 541 | 91.68% | 7.0867% | 73 | 88.75% | 45 |
| best scalar prune (`reclaim_body<=67.6471`) | 521 | 91.75% | 7.0991% | 71 | 88.75% | 43 |

Loss cause after V231:
- weak side remains inherited V175_BASELINE rows: `n=197`, `WR=86.80%`, `Avg=6.4018%`, yearWRmin `83.33%`, 26 losses;
- V211/V230 child rows are much cleaner but not enough current supply alone;
- losers have lower pre-entry participation/positioning (`br/up3/pos20` weaker) and higher reclaim close-position/chase;
- conclusion: low-WR rows are not fixed by another scalar filter; need participation-aware new supply.

V234 tried new supply without true market breadth and did not pass strict gate:

| best V234 | n | WR | Avg | minYear | yearWRmin | loss |
|---|---:|---:|---:|---:|---:|---:|
| V233 mild base + 26 child | 547 | 91.77% | 7.2103% | 71 | 88.51% | 45 |

V235 added previous-market `br_above_ma20` from `/root/.hermes/smc_audit/v185_market_breadth_cache.csv` plus non-overlap new supply and produced a strict historical pass:

Rule:
```text
Base:
  V231 rows with v132_reclaim_body_range_pct <= 67.6471
Add non-overlap child rows from V230 pool where:
  market_state in {ACCUMULATION, BEAR_RISK}
  event_type == SSL_SWEEP_CHOCH_REVERSAL
  poi_source in {DEMAND_OB, OB+FVG, FVG_Demand}
  v132_bull_count_3 >= 3
  v132_post_zone_pullback_depth_pct_3 <= 20
  previous-day allStrong1 between 20 and 55
  previous-day br_above_ma20 between 35 and 70
Dedup:
  prefer DEMAND_OB, then OB+FVG, then FVG_Demand;
  prefer SSL_SWEEP_CHOCH_REVERSAL; then lower risk/chase.
```

V236 independent reconstruction using recomputed allStrong1 from kline cache confirmed:

| set | n | WR | Avg | minYear | yearWRmin | micro | loss | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base selected | 521 | 91.75% | 7.0991% | 71 | 88.75% | 0.77% | 43 | 0 |
| new child | 37 | 100.00% | 9.2958% | 1 | 100.00% | 0.00% | 0 | 0 |
| combined V236 | 558 | 92.29% | 7.2448% | 72 | 90.28% | 0.72% | 43 | 0 |

Integrity:
- production gate: all true (`n>=500`, `min_year_n>=70`, `WR>=92`, `Avg>=7.2`, `yearWRmin>=89`, `micro<=1`, `T+1=0`);
- selector leak fields: `[]`;
- overlap with V231 history for new child: `0`;
- time-order bad: `0`;
- production/frontend/watchlist writes: all false.

Current scanner smoke:
- latest market date `20260626`;
- recent45 rows `2014`;
- V231 raw current rows `1`, expired `1`, actionable `0`;
- V236 raw current rows `0`, actionable `0`.

Operational status:
- V185 remains production routed to cron/API/frontend.
- V236 is now the best historical production-gate candidate, but only shadow-monitored because current scanner has no actionable rows.
- `smc_daily_ops.py` now runs both V231 and V236 no-write shadow audits and records `v236_shadow_audit` in `ops_latest.json`.
- Do not promote V236 to frontend/live watchlist until `new_actionable_rows > 0` and endpoint mapping smoke passes.

Decision: `V236_HISTORICAL_GATE_PASS__SHADOW_MONITORING_NO_WRITE`.

## V237-V238 post-V236 continuation (2026-06-29)

Artifacts:
- V237 scalar/loss closure: `/root/.hermes/smc_audit/v237_post_v236_loss_and_scalar_closure_no_write_20260629_101830/`
- V237 scalar frontier source: `/root/.hermes/smc_audit/v237_post_v236_loss_and_supply_search_no_write_20260629_095425/`
- V238 focused new-supply search: `/root/.hermes/smc_audit/v238_focused_post_v236_new_supply_no_write_20260629_101652/`
- Latest summaries:
  - `/root/.hermes/smc_audit/v237_post_v236_loss_and_scalar_closure_latest.json`
  - `/root/.hermes/smc_audit/v238_focused_post_v236_new_supply_latest.json`

Post-V236 strict gate was intentionally raised:

| gate | production threshold | research threshold |
|---|---:|---:|
| n | >=550 | >=520 |
| min_year_n | >=70 | >=65 |
| WR | >=93% | >=92.5% |
| AvgPnL | >=7.4% | >=7.3% |
| all_year_WR_min | >=91% | >=90% |
| micro_profit_pct | <=1% | <=1% |
| T+1 | 0 | 0 |

V237 remaining-loss attribution after V236:

| bucket | n | WR | Avg | losses | loss share |
|---|---:|---:|---:|---:|---:|
| V175_BASELINE | 264 | 89.02% | 6.6403 | 29 | 67.44% |
| V211_CHILD | 170 | 95.29% | 7.3401 | 8 | 18.60% |
| V185_CHILD | 87 | 93.10% | 8.0206 | 6 | 13.95% |
| V230_CHILD | 37 | 100.00% | 9.2958 | 0 | 0.00% |

Exit-loss attribution:
- `SL`: 24 losses / 55.81% of all remaining losses.
- `TIME`: 12 losses / 27.91%.
- `TIME10`: 5 losses / 11.63%.
- `GAP_SL`: 2 losses / 4.65%.

Best V237 scalar/pair pruning did **not** pass production/research width:

| rule | n | WR | Avg | minYear | yearWRmin | decision |
|---|---:|---:|---:|---:|---:|---|
| `v236_br_above_ma20>=25.2999` | 451 | 94.46% | 7.6311 | 43 | 90.70% | too narrow |
| `v236_br_above_ma20>=20.7461 AND v236_all_strong1_pct>=4.05521` | 456 | 94.52% | 7.6614 | 46 | 89.13% | too narrow |

Decision: `V237_SCALAR_PAIR_PRUNING_CLOSED__NO_POST_V236_PRODUCTION_GATE_PASS`.

V238 focused new-supply continuation found a **research-only** frontier, not production:

Best V238:

```text
Base: V236 rows with previous-day br_above_ma20 >= 13.8778
Add V230 non-overlap child where:
  market_state in {ACCUMULATION, BEAR_RISK}
  event_type == SSL_SWEEP_CHOCH_REVERSAL
  poi_source in {DEMAND_OB, OB+FVG}
  v132_bull_count_3 >= 3
  v132_post_zone_pullback_depth_pct_3 <= 40
  previous-day allStrong1 between 10 and 55
  previous-day br_above_ma20 between 35 and 70
```

| set | n | WR | Avg | minYear | yearWRmin | micro | losses | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V236 baseline | 558 | 92.29% | 7.2448 | 72 | 90.28% | 0.72% | 43 | 0 |
| V238 best combined | 577 | 92.89% | 7.5939 | 71 | 90.14% | 0.69% | 41 | 0 |
| V238 child only | 49 | 91.84% | 9.9027 | 2 | 71.43% | 0.00% | 4 | 0 |

Decision: `V238_RESEARCH_GATE_ONLY__NOT_PRODUCTION` because it improves WR/Avg but fails strict production thresholds (`WR<93`, `yearWRmin<91`) and child-only year coverage is weak.

Current standing conclusion:
- V185 remains live production baseline.
- V236 remains best historical shadow candidate with production-gate pass, but current scanner still has `new_actionable_rows=0`.
- V237 closed scalar/pair pruning: high-WR pockets are too narrow.
- V238 is useful research evidence that market-breadth-confirmed non-overlap child supply can lift Avg materially, but it is not production-safe.
- Next valid research direction is **not another scalar prune**; it should either:
  1. rebuild child supply with broader year coverage under the V238 semantics, or
  2. add a current-scanner-compatible source feature bridge so V236/V238 can be monitored on the latest V90 scanner fields, then only promote if current actionable rows appear and endpoint smoke passes.

## V239-V241 continuation after V238 (2026-07-01)

Artifacts:
- V239 broader child-supply search: `/root/.hermes/smc_audit/v239_post_v238_broader_child_supply_search_no_write_20260701_085740/`
- V239 latest summary: `/root/.hermes/smc_audit/v239_post_v238_broader_child_supply_search_latest.json`
- V240 current scanner field-bridge smoke: `/root/.hermes/smc_audit/v240_v239_current_scanner_smoke_latest.json`
- V241 current scanner with breadth bridge: `/root/.hermes/smc_audit/v241_v239_current_scanner_with_breadth_bridge_latest.json`

V239 tested the correct next direction from V238: broader non-overlap child supply under the V238 semantics, not another scalar prune. It searched 23,040 no-write combinations using only source-side selector fields and produced **research-gate pass but no production-gate pass**.

V239 best:

```text
Base: V236 rows with previous-day br_above_ma20 >= 13.8778
Add non-overlap child rows from V230 pool where:
  market_state in {ACCUMULATION, BEAR_RISK}
  event_type == SSL_SWEEP_CHOCH_REVERSAL
  poi_source in {DEMAND_OB, OB+FVG}
  v132_bull_count_3 >= 3
  v132_post_zone_pullback_depth_pct_3 <= 40
  previous-day allStrong1 between 10 and 55
  previous-day br_above_ma20 between 35 and 70
  entry_chase_above_zone_pct <= 2.5
Dedup source-side:
  prefer DEMAND_OB, then OB+FVG, then lower risk/chase.
```

| set | n | WR | Avg | minYear | yearWRmin | micro | losses | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V236 baseline | 558 | 92.29% | 7.2448 | 72 | 90.28% | 0.72% | 43 | 0 |
| V238 best | 577 | 92.89% | 7.5939 | 71 | 90.14% | 0.69% | 41 | 0 |
| V239 best | 567 | 93.12% | 7.5846 | 70 | 90.00% | 0.71% | 39 | 0 |

V239 interpretation:
- It is a real improvement on WR and loss count versus V238, but not a production promotion.
- It fails the predeclared production gate because `n<570`, `Avg<7.6`, and `all_year_WR_min=90.0<91.0`.
- The child bucket is strong but year-imbalanced: `n=37`, WR `94.59%`, Avg `10.78%`, but only `2026=1` and `2024=3`; therefore it cannot be used to claim production-grade cross-year robustness.
- Remaining weak floor is no longer “child-supply syntax”; it is year-floor/base-regime weakness: 2023 WR `90.72%` and 2026 WR `90.00%` block the raised gate.

V240/V241 current scanner bridge result:
- Current dry scanner structural fields exist.
- `v230_all_strong1_pct` is not directly present in the scanner output.
- V241 mapped it safely from `/root/.hermes/smc_audit/v185_market_breadth_cache.csv` using `br_strong_r5`; this matches historical V230/V236 sampled rows (`v230_all_strong1_pct ≈ br_strong_r5`).
- With the bridge applied to latest dry scanner rows (`dry_recent45_rows=2014`), V239 current rule produced `raw_rule_rows=0`, `new_actionable_rows=0`.

Decision:
- `V239_RESEARCH_GATE_PASS__NOT_PRODUCTION`.
- `V241_NO_CURRENT_ACTIONABLE_ROWS__KEEP_V239_RESEARCH_ONLY_NO_WRITE`.
- V185 remains production; V236 remains best production-gate historical shadow; V238/V239 are research-only evidence.
- Do not route V239 to frontend/API/watchlist.

Next valid research direction:
1. Stop broad child-supply threshold search unless a new source layer is added; it is now exhausted at research-only.
2. Next work should be **year-floor repair**, specifically 2023/2026 loss regimes and SL/TIME failure modes under V236/V239, not global threshold tuning.
3. A candidate becomes usable only if it beats: `n>=570`, `min_year_n>=70`, `WR>=93%`, `AvgPnL>=7.6%`, `all_year_WR_min>=91%`, `micro<=1%`, `T+1=0`, plus current scanner actionable rows and endpoint smoke.

## V242-V243 year-floor repair and exit replay closure (2026-07-01)

Artifacts:
- V242 year-floor repair search: `/root/.hermes/smc_audit/v242_post_v239_year_floor_repair_no_write_20260701_091807/`
- V242 latest summary: `/root/.hermes/smc_audit/v242_post_v239_year_floor_repair_latest.json`
- V243 exit replay: `/root/.hermes/smc_audit/v243_v239_exit_replay_no_write_20260701_092856/`
- V243 latest summary: `/root/.hermes/smc_audit/v243_v239_exit_replay_latest.json`

V242 reconstructed V239 from V236 `br>=13.8778` + V230 non-overlap child spec and directly attacked the raised gate bottleneck:

| set | n | WR | Avg | minYear | yearWRmin | micro | losses | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V185 production | 334 | 86.23% | 6.5628 | 41 | 82.81% | 0.90% | 46 | 0 |
| V236 | 558 | 92.29% | 7.2448 | 72 | 90.28% | 0.72% | 43 | 0 |
| V239 approx | 565 | 93.10% | 7.6021 | 70 | 90.00% | 0.71% | 39 | 0 |
| V239 base | 528 | 92.99% | 7.3796 | 69 | 89.86% | 0.76% | 37 | 0 |
| V239 child | 37 | 94.59% | 10.7771 | 1 | 66.67% | 0.00% | 2 | 0 |

Remaining V239 loss focus:
- total losses `39`;
- 2023 losses `9`, 2026 losses `7`;
- exit-loss counts: `SL=21`, `TIME=10`, `TIME10=7`, `GAP_SL=1`.

Weak-year source-side deltas:
- 2023 losers have much lower prior breadth (`v236_br_above_ma20` loss mean `28.39` vs winner `47.19`) and lower strong participation (`v236_all_strong1_pct` `9.67` vs `15.37`), plus higher risk/chase/reclaim-close-position.
- 2026 losers do **not** show the same breadth separation (`br_above_ma20` loss `41.25` vs winner `41.39`); their damage is more path/stock-specific with much worse MAE (`-8.53` vs `+1.37`) and longer hold.
- Therefore a single global scalar/breadth gate cannot repair both 2023 and 2026 without collapsing coverage.

V242 tested 8,640 no-write combinations of base breadth rules + non-overlap V230 child supply:

| result | count |
|---|---:|
| frontier rows | 707 |
| research-pass rows | 314 |
| production-pass rows | 0 |

Best V242 candidate:

| n | WR | Avg | minYear | yearWRmin | micro | losses |
|---:|---:|---:|---:|---:|---:|---:|
| 580 | 92.93% | 7.5183 | 73 | 90.41% | 0.69% | 41 |

Rule:
```text
Base: V236 rows with br_above_ma20 >= 10
Child: V230 non-overlap rows where
  market_state in {ACCUMULATION, BEAR_RISK}
  event=SSL_SWEEP_CHOCH_REVERSAL
  poi_source in {DEMAND_OB, OB+FVG}
  v132_bull_count_3 >= 3
  pullback_depth_3 <= 20
  allStrong1 10..55
  br_above_ma20 30..70
  entry_chase_above_zone_pct <= 2.5
```

Decision: `V242_RESEARCH_ONLY__YEAR_FLOOR_NOT_REPAIRED` because `WR<93`, `Avg<7.6`, and `yearWRmin<91`.

V243 then tested whether the remaining SL/TIME failures are repairable by exit-parameter changes instead of signal/source changes. It replayed 36 variants over the V239 row set: `max_hold in {10,12,15,20}`, `SL multiplier in {1.0,1.15,1.3}`, `TP multiplier in {1.0,0.85,0.7}` with T+1 start preserved.

Best replay by sorted objective:

| n | WR | Avg | minYear | yearWRmin | micro | losses |
|---:|---:|---:|---:|---:|---:|---:|
| 565 | 91.15% | 9.6855 | 70 | 82.86% | 0.35% | 50 |

Decision: `V243_EXIT_REPLAY_NO_PRODUCTION_PASS__FAILURE_IS_SIGNAL_YEAR_FLOOR_NOT_EXIT_PARAMETERS`.

Interpretation:
- Extending hold / widening SL / lowering TP can lift average by letting large winners run or take earlier profit, but it worsens WR and year floor badly.
- The remaining bottleneck is not exit tuning. It is source/signal-year-floor: 2023 needs stronger pre-entry participation filter or new year-robust child supply; 2026 needs a different source layer because broad breadth no longer separates winners from losers.

Updated standing direction after V243:
1. V185 remains production.
2. V236 remains best historical production-gate shadow candidate until independent audit/current smoke of newer candidates.
3. V239/V242 are research-only; they show high potential but cannot be promoted.
4. Do not continue scalar/broad child threshold search or exit-parameter replay.
5. Next valid qualitative research requires a **new source layer**: sector/industry participation, true historical intraday generator, or a fresh scanner field that separates 2026 path-failure rows before entry. Without a new source layer, further iteration is likely curve-fitting.

## V244-V246 industry source-layer breakthrough (2026-07-01)

Artifacts:
- V244 industry participation probe: `/root/.hermes/smc_audit/v244_post_v243_industry_participation_probe_no_write_20260701_151619/`
- V245 source-field separator probe: `/root/.hermes/smc_audit/v245_source_field_separator_probe_no_write_20260701_152330/`
- V246 historical candidate: `/root/.hermes/smc_audit/v246_industry_addback_candidate_no_write_20260701_153401/`
- V247 current smoke: `/root/.hermes/smc_audit/v247_v246_current_smoke_latest.json`
- V248 independent audit: `/root/.hermes/smc_audit/v248_v246_independent_audit_latest.json`
- V246 daily shadow monitor: `/root/.hermes/scripts/v25/v246_daily_current_shadow_audit.py`
- Latest summaries: `/root/.hermes/smc_audit/v246_industry_addback_candidate_latest.json`, `/root/.hermes/smc_audit/v246_daily_current_shadow_audit_latest.json`

V244 added the required new source layer: Baostock CSRC industry classification + previous-day industry participation computed from local K-line cache. It tested 1,840 no-write combinations. Industry alone did not pass research/production:

| candidate | n | WR | Avg | minYear | yearWRmin | losses | decision |
|---|---:|---:|---:|---:|---:|---:|---|
| V244 best | 597 | 93.30% | 7.3616% | 74 | 89.19% | 40 | no gate pass |

V245 found the real weak source bucket: excluding `C27医药制造业` produced a clean research pass but was too narrow for production:

| rule | n | WR | Avg | minYear | yearWRmin | losses |
|---|---:|---:|---:|---:|---:|---:|
| `v244_industry != C27医药制造业` | 561 | 93.94% | 7.5432% | 71 | 91.55% | 34 |

V246 then tested a source-side addback rule for the two weak industries (`C27医药制造业`, `C32有色金属冶炼和压延加工业`) and produced the first post-V236 raised-gate historical production pass:

```text
Base: V244 best candidate rows.
Keep all rows except weak industries C27/C32.
For C27/C32 rows, add back only when:
  previous-day industry strong1 >= 31.1688
  OR previous-day broad br_above_ma20 >= 46.8561
```

Metrics:

| set | n | WR | Avg | minYear | yearWRmin | micro | losses | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V244 best baseline | 597 | 93.30% | 7.3616% | 74 | 89.19% | 0.50% | 40 | 0 |
| V246 selected | 573 | 94.42% | 7.6022% | 71 | 92.22% | 0.35% | 32 | 0 |
| V246 excluded | 24 | 66.67% | 1.6179% | 3 | 0.00% | 4.17% | 8 | 0 |

Predeclared raised production gate passed:
- `n>=570`: pass (`573`)
- `min_year_n>=70`: pass (`71`)
- `WR>=93`: pass (`94.42%`)
- `AvgPnL>=7.6`: pass (`7.6022%`)
- `all_year_WR_min>=91`: pass (`92.22%`)
- `micro<=1`: pass (`0.35%`)
- `T+1=0`: pass
- selector leak fields: `[]`

Decision: `V246_HISTORICAL_PRODUCTION_GATE_PASS__NO_WRITE__NEEDS_INDEPENDENT_AUDIT_AND_CURRENT_SCANNER_SMOKE`.

Usable now:
- V246 is a historical production-gate pass and the first qualitative post-V236 improvement.

Not usable yet:
- V246 must not be routed to frontend/API/watchlist until an independent reconstruction/audit and latest current-scanner smoke pass. Current production remains V185; V236 remains the prior shadow baseline until V246 audit closure.

Next required step:
1. V246 is now independently reconstructed and audited; historical gate remains passed, but with local monthly stability risks.
2. Keep V246 as no-write daily shadow monitoring only. Current production remains V185 until `v246_daily_current_shadow_audit_latest.json` reports `new_actionable_rows > 0` and endpoint mapping smoke passes.
3. Do not apply the historical V236-base breadth rule directly to arbitrary current scanner rows: current dry rows do not carry V236-base materialization identity, and doing so over-selects unrelated rows. The daily V246 monitor must use only the current-scanner-compatible V239/V244 new-supply branch until a dedicated base generator exists.
4. If V246 current rows appear, verify: selector leak fields `[]`, previous-date joins `< entry_date`, overlap with V185/V231/V236/V246 history = 0, `bars_since_entry <= 10`, T+1/field pollution = 0, then run endpoint mapping smoke before any frontend/API/watchlist write.
