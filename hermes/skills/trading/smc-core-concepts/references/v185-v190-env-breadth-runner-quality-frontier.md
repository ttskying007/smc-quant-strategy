# V185-V190 env-breadth runner quality frontier

Date: 2026-06-25

## Trigger

Use after V175/V180-V184 closure when looking for a qualitative improvement beyond V175 without mutating production/frontend/watchlist artifacts.

## Predeclared gates

Production combined gate used in this research:
- source-side non-leaking rule;
- T+1 violations = 0;
- combined with V175: `n >= 260`;
- `min_year_n >= 40`;
- `WR >= 84%`;
- `AvgPnL >= 6.2%`;
- `all_year_WR_min >= 82%`;
- `micro_profit_pct <= 1%`;
- no frontend/watchlist/API mutation before dry-run passes.

Research child gate remains stricter for standalone child engines:
- 100% non-overlap vs V175;
- `n >= 120`;
- `min_year_n >= 20`;
- `WR >= 86%`;
- `AvgPnL >= 6.5%`;
- `all_year_WR_min >= 83%`;
- T+1 violations = 0.

## Completed results

### V184 — V164 enriched non-overlap search

Artifact: `/root/.hermes/smc_audit/v184_v164_enriched_nonoverlap_search_20260625_1228/`

- Joined V164 scanner-time fields to V128 backtest outcomes by `symbol + entry_date + event_type + poi_source`.
- Enforced non-overlap vs V175 by `symbol + entry_date`.
- No standalone child engine passed the research-child gate.
- Best near-frontier source-side cluster was:
  - `v132_bull_count_3>=3 & market_state==BEAR_RISK & v85_zone_width_pct>=3.1251`
  - child `n=175`, `WR=80.0%`, `Avg=15.2978%`, `all_year_WR_min=70.59%`; high avg but not stable enough.

### V185 — env breadth gate search

Artifact: `/root/.hermes/smc_audit/v185_env_breadth_gate_search_20260625_1238/`

Adding V74 broad-market breadth fields produced a combined V175+child production-gate pass under the original V128 shadow outcome:

Rule V185A:
```text
v132_bull_count_3 >= 3
AND event_bear_breadth >= 0.3352
AND entry_total >= 4543
AND v85_zone_width_pct >= 3.1251
AND nonoverlap_v175
```

Original-shadow combined metrics:
- combined `n=317`, `WR=84.23%`, `Avg=9.734%`, `min_year_n=47`, `all_year_WR_min=82.8%`, `micro=0.95%`.
- child `n=70`, `WR=85.71%`, `Avg=22.7359%`, non-overlap=100%.

Interpretation: this is a qualitative lead, but original V128 shadow outcome is not executable enough by itself.

### V186 — V129 executable target validation

Artifact: `/root/.hermes/smc_audit/v186_v185_candidate_executable_target_validation_20260625_1248/`

V185A under V129 pre-entry BSL/1.5R target:
- `n=70`, `WR=94.29%`, but `Avg=0.8906%`, `micro=62.86%`.

V185B under V129 target:
- `n=63`, `WR=95.24%`, but `Avg=0.4209%`, `micro=68.25%`.

Decision: V129 small target converts the edge into micro-profit pollution. It is **not usable** for production despite high WR.

### V187/V188/V189 — conservative runner validation

Artifacts:
- `/root/.hermes/smc_audit/v187_v185_runner_hold_validation_20260625_1255/`
- `/root/.hermes/smc_audit/v188_v187_conservative_trail_audit_20260625_1300/`
- `/root/.hermes/smc_audit/v189_v185_conservative_trail_grid_20260625_1305/`

Important correction:
- Same-bar high→trail stop update can be lookahead/ordering ambiguous on daily bars.
- V188/V189 use conservative trailing: stop for current bar is based only on highs observed before the current bar; current bar high updates stop only for subsequent bars.

Best robust V185A variants passed the combined production gate under conservative replay:

| Variant | Child n | Child WR | Child Avg | Combined n | Combined WR | Combined Avg | Year WR min | Micro | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `h60_act15_tr10` | 70 | 92.86% | 15.3068% | 317 | 85.80% | 8.0935% | 82.80% | 0.95% | 0 |
| `h20_act15_tr10` | 70 | 92.86% | 15.1747% | 317 | 85.80% | 8.0644% | 82.80% | 0.95% | 0 |
| `h60_act15_tr12` | 70 | 90.00% | 19.6742% | 317 | 85.17% | 9.0579% | 82.80% | 0.95% | 0 |
| `h20_act15_tr12` | 70 | 90.00% | 19.0615% | 317 | 85.17% | 8.9226% | 82.80% | 0.95% | 0 |

Best by combined Avg: `h60_act15_tr12`.
Best by WR/robustness balance: `h60_act15_tr10` or `h20_act15_tr10`.

## V190 current active dry-run

Artifact: `/root/.hermes/smc_audit/v190_v185_current_active_dryrun_20260625_1750/`

After rerunning V164 dry-run on latest V128 (`run_at=2026-06-25T15:24:41`, latest market date `20260625`):
- V164 dry-run integrity passed, no production/frontend/watchlist writes.
- V185A current recent45 count = 1.
- Latest candidate = `600392.SH`, entry_date `20260610`, entry_price `23.42`, `DEMAND_OB`, `SSL_SWEEP_CHOCH_REVERSAL`, `BEAR_RISK`, zone `22.23-22.955`, `v132_bull_count_3=3`, `event_bear_breadth=0.4729`, `entry_total=4616`, `v85_zone_width_pct=3.2614`.

## Decision

V185A + conservative runner is the first post-V175 direction that produced a real qualitative improvement candidate:
- Not a frontend/field fix.
- Not generic V175 exit overlay.
- Not a raw classical SMC generator.
- It uses source-side market breadth + takeover persistence + wide-zone filter, then a conservative runner to avoid micro-profit exits.

Status: **promotion candidate, not yet production-mutated**.

Reasons to keep it shadow-only until final release gate:
1. Child engine has only `n=70` and no 2023 child rows; the combined engine passes because V175 already covers 2023.
2. Rule was discovered on the same historical universe; needs release-style audit and preferably forward/live paper tracking.
3. Current active dry-run has only one candidate, so live validation will be slow.

## Next required steps

1. Build a formal V191 release candidate artifact, not just audit CSVs:
   - explicit rule contract;
   - conservative runner contract;
   - no outcome-field selector audit;
   - T+1 proof;
   - full combined V175+V185A metrics;
   - current active dry-run rows.
2. Run release gates against V191:
   - schema/field completeness;
   - duplicate key audit;
   - V175 overlap audit;
   - all-year metrics;
   - micro-profit audit;
   - intrabar-ordering disclaimer/contract.
3. Only after V191 passes should frontend/watchlist/API integration be considered.
