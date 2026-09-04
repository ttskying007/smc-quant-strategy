# V211-V214 V185+V211 true-takeover2 persistence shadow breakthrough

Date: 2026-06-26

## Trigger

Use when continuing after V208-V210 V185 loss-root-cause closure. The user asked to keep researching after V185, especially low-WR rows, until a qualitative improvement is found.

## Fixed gates

Post-V185 production improvement requires:
- source-side / non-leaking selector only;
- T+1 same-day violations = 0;
- combined `n >= 300`, `min_year_n >= 40`;
- `WR >= 87%`, `AvgPnL >= 6.8%`, `all_year_WR_min >= 84%`;
- `micro_profit_pct <= 1%`;
- no frontend/watchlist/API production writes before independent audit and current scanner rematerialization.

Standalone research child gate remains stricter for independent child validity; if child yearly coverage is below gate, it can only be used as a combined-engine add-on.

## Artifacts

- V211 supply search: `/root/.hermes/smc_audit/v211_v164_persistence_supply_probe_20260626_183011/`
- V212 independent integrity audit: `/root/.hermes/smc_audit/v212_v211_independent_integrity_audit_20260626_183543/`
- V213 source-side dedup validation: `/root/.hermes/smc_audit/v213_v211_dedup_rule_validation_20260626_183624/`
- V214 shadow materialization: `/root/.hermes/smc_audit/v214_v211_shadow_materialization_no_write_20260626_183703/`

## Candidate rule

V211 top rule from V164 corrected BUY pool, excluding all V185 `symbol+entry_date` rows:

```text
v132_reclaim_class == TRUE_TAKEOVER_2
AND v132_bull_count_3 >= 3
AND v132_post_zone_pullback_depth_pct_3 <= 3
```

Execution replay used strict T+1 daily path:
- SL = `zone_low * 0.99`;
- TP = `entry + 1.5R`;
- 50% partial at TP;
- runner BE lock after TP;
- close remaining at entry+10 bars if no BE/SL.

## Duplicate correction

V212 found raw V211 child had 204 rows but 34 duplicated `symbol+entry_date`. This invalidated the raw top metric as directly promotable.

V213 applied deterministic source-side dedup (no outcome fields):
- prefer `DEMAND_OB`, then `OB+FVG`, then `FVG_Demand`;
- prefer `SSL_SWEEP_CHOCH_REVERSAL` before `BOS_CONTINUATION`;
- then lower `risk_pct`, lower `entry_chase_above_zone_pct`.

## Validated metrics after dedup

| engine | n | WR | AvgPnL | minYear | yearWRmin | micro | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| V185 baseline | 334 | 86.23% | 6.5628% | 41 | 82.81% | 0.90% | 0 |
| V211 child dedup | 170 | 95.29% | 7.3401% | 19 | 87.88% | 0.59% | 0 |
| V185+V211 combined | 504 | 89.29% | 6.8250% | 74 | 86.75% | 0.79% | 0 |

Child year counts: 2023=19, 2024=48, 2025=70, 2026=33. Child alone is not standalone production because `min_year_n=19`, but as an add-on it lifts the combined engine above the post-V185 gate.

## Integrity checks

- Selector leak fields: `[]`.
- Overlap with V185 by `symbol+entry_date`: `0`.
- Same-day/T+1 violations: `0`.
- Raw duplicate issue corrected by source-side dedup.
- V214 is shadow/no-write only: `production_write=false`, `frontend_write=false`, `watchlist_write=false`.
- Active/current picks: `0` in the frozen V164 artifact since no V211 top-rule rows were `>=20260601`; current scanner dry-run must be rebuilt before any active/live claim.

## Decision

V211/V214 is a new qualitative shadow candidate beyond V185:
- usable as a historical combined-engine research breakthrough;
- not yet production-routed;
- not yet current-active/live validated;
- requires formal current scanner rematerialization and endpoint mapping before any frontend/API route.

## Current scanner rebuild follow-up (V215-V216, 2026-06-27)

Artifacts:
- Current V161/V164 dry-run rerun refreshed `/root/.hermes/smc_audit/v161_dry_run_scanner_contract_20260622/` and `/root/.hermes/smc_audit/v164_corrected_scanner_dry_run_20260622/` from latest V128 (`latest_market_date=20260626`).
- V215 current V211 rematerialization: `/root/.hermes/smc_audit/v215_current_v211_active_rematerialize_no_write_20260627_021211/`.
- V216 actionable gate: `/root/.hermes/smc_audit/v216_v211_current_actionable_gate_no_write_20260627_021305/`.

Result:
- Current V164 recent BUY rows: `228`.
- V211 top rule current raw rows: `1`, dedup rows: `1`, selector leak fields: `[]`, overlap with V185 active/history: `0`.
- The only row is `600790.SH / 20260424`, `BOS_CONTINUATION + DEMAND_OB`, `bars_since_entry=41`.
- Because V211 execution contract is max-hold 10 bars, V216 marks this row expired: `actionable_rows=0`, `expired_rows=1`.
- Decision: `V216_NO_ACTIONABLE_CURRENT_V211_ROWS__HISTORICAL_GATE_PASS_ONLY_NO_WRITE`.

Operational implication:
- V211/V214 remains a historical combined-engine quality breakthrough (`V185+V211`), but has **no current actionable active-pick increment** on the latest scanner snapshot.
- Do not route V214/V211 to frontend/watchlist/API as active production until a future current scanner run yields rows with `bars_since_entry <= 10` and the same no-leak/no-overlap/write-flag checks pass.
- If there are zero actionable current rows, endpoint routing smoke is not meaningful; keep it shadow/no-write and continue from either V185 production stabilization or a genuinely new pre-entry supply/data layer.
