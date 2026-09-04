# V183-V184 supply payoff and reaction quality closure

Date: 2026-06-25

## Trigger
Use after V180-V182 closure when considering whether to keep researching by filtering existing V85/V90/V128/V175 artifacts, or whether a genuinely new signal generator is required.

## Gates reused
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

Research child usable:
- 100% non-overlap vs V175;
- `n >= 120`;
- `min_year_n >= 20`;
- `WR >= 86%`;
- `AvgPnL >= 6.5%`;
- `all_year_WR_min >= 83%`;
- T+1 violations = 0.

## V183: source payoff / known-BSL / fixed-exit probe
Artifact: `/root/.hermes/smc_audit/v183_supply_payoff_probe_20260625_222656/`

Scope:
- Source: `/root/.hermes/smc_opt_v85_mixed_accumulation_generator/v85_candidates.json` (23,307 rows).
- Computed pre-entry known BSL geometry with `known_bsl_target()`.
- Tested executable daily exits: close_20/40/60, rr1.5/2/3, BSL targets.
- Selection filters used source-side fields only: market state, path, risk, zone width, known-BSL-R, touch/entry timing.
- No production/frontend/watchlist writes.

Decision: `NO_GATE_PASS__SUPPLY_PAYOFF_SOURCE_FILTERS_INSUFFICIENT`.

Best high-payoff rows had large AvgPnL but failed WR/year/sample stability:
- `close_20 AND risk_pct>=2 AND known_bsl_r>=0.8`: n=86, WR=55.81%, Avg=11.8899%, min_year=11, yearWRmin=36.36%, T+1=0, non-overlap vs V175=100%.
- High payoff came from a volatile tail, not a stable engine.

## V184: reclaim/reaction quality feature probe
Artifact: `/root/.hermes/smc_audit/v184_reaction_quality_probe_20260625_223224/`

Scope:
- Same V85 candidate source.
- Added pre-entry reaction features:
  - touch depth inside zone;
  - reclaim close position;
  - reclaim body percentage;
  - reclaim close above zone;
  - entry chase above zone;
  - touch→reclaim bars;
  - reclaim volume ratio;
  - pre-reclaim close/low break of zone;
  - known-BSL-R.
- Tested semantic, rr2/rr3, BSL, and close-20 style exits.
- No outcome fields were used as selectors; future outcomes used only for evaluation.
- No production/frontend/watchlist writes.

Decision: `NO_GATE_PASS__REACTION_FEATURES_DO_NOT_CREATE_QUALITATIVE_ENGINE`.

Best high-payoff rows again failed WR/year stability:
- `close_20 AND market_state==ACCUMULATION AND reclaim_vol_ratio>=2.0`: n=229, WR=74.24%, Avg=19.0847%, min_year=10, yearWRmin=38.10%, micro=0.87%, T+1=0, non-overlap=100%.
- `close_20 AND market_state==ACCUMULATION AND reclaim_vol_ratio>=1.5`: n=401, WR=64.84%, Avg=15.6151%, min_year=20, yearWRmin=32.61%, T+1=0.

## Root conclusion
Existing V85/V90 supply can produce high average payoff only by accepting unstable tail-risk rows. Source-side reaction filters improve payoff but do not create a stable high-WR/high-Avg engine. This closes the "filter old V85/V90 supply harder" path under the strict V180-V182 gates.

## Next research direction
Do not continue scalar filtering on V85/V90/V128/V175. The next qualitative change must alter candidate generation itself:
1. Generate a new setup type rather than filtering current DEMAND_OB rows.
2. Candidate creation should explicitly model pre-entry accumulation + expansion + pullback/reclaim as separate lifecycle states.
3. Add a market-regime/year-stability audit at generation time; if one year is carrying the edge, reject before exit research.
4. Keep shadow-only until the strict production/child gates pass.
