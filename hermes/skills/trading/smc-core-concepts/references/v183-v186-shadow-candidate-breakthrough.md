# V183-V186 shadow research: V175 + V185 child breakthrough

Date: 2026-06-26

## Trigger

Use when continuing post-V175 SMC research and deciding what is usable/unusable after V177-V182 closure.

## Gates

Production combined candidate usable:
- source-side non-leaking selector;
- T+1 / same-day exit violations = 0;
- combined engine `n >= 260`;
- `min_year_n >= 40`;
- `WR >= 84%`;
- `AvgPnL >= 6.2%`;
- `all_year_WR_min >= 82%`;
- `micro_profit_pct <= 1%`;
- no frontend/watchlist/API mutation before formal promotion.

Research child engine usable:
- 100% non-overlap vs V175;
- `n >= 120`;
- `min_year_n >= 20`;
- `WR >= 86%`;
- `AvgPnL >= 6.5%`;
- `all_year_WR_min >= 83%`;
- T+1 violations = 0.

## V183: genuinely new range-spring generator failed

Artifact: `/root/.hermes/smc_audit/v183_new_generator_range_spring_20260625_233937`

Direct full-market K-line generator (range liquidity spring -> reclaim/takeover -> demand POI) scanned 4655 cache files / 4652 valid symbols. It is independent of V128/V167/V175, but failed badly:
- best top candidate `W30_rp0.35_sw1.0`: all `n=181`, `WR=54.7%`, `Avg=1.2096%`, `yearMin=20%`, `micro=3.87%`;
- no production or child gate passed.

Conclusion: naive range spring is not a usable SMC supply generator for this system.

## V184: V181 best child hybrid runner nearly crossed the frontier

Artifact: `/root/.hermes/smc_audit/v184_v181_child_hybrid_runner_20260625_235352`

Base child: `V167 excluded from V175 AND v132_bull_count_3>=3`.

Best executable overlay: `p50_time10_after_entry`:
- take 50% at original TP touch;
- BE-lock remainder;
- if no stop, close remainder at entry+10 bars.

Metrics before additional source-side filtering:
- child: `n=175`, `WR=87.43%`, `Avg=6.4884%`, `micro=0%`, but weak yearly spread (`2026 n=7`, `2023 WR=78.38%`);
- combined with V175: `n=422`, `WR=85.31%`, `Avg=6.2314%`, `minYear=45`, `yearMin=80.95%`, `micro=0.71%`.

Conclusion: execution overlay solved Avg/micro, but 2023 year floor was still too weak.

## V185: first combined shadow candidate passed production gate

Artifact: `/root/.hermes/smc_audit/v185_formal_candidate_v175_plus_child_20260626_001218`

Selector (source-side only):
`V167 excluded non-overlap AND v132_bull_count_3>=3 AND risk_pct>=3.0133 AND v132_reclaim_body_range_pct>=50`

Execution: V184 `p50_time10_after_entry` overlay.

Leak audit:
- selector leak fields: `[]`;
- overlap with V175: `0`;
- combined same-day exit violations: `0`;
- production/frontend/watchlist write: `False`.

Metrics:
- V175 baseline: `n=247`, `WR=83.81%`, `Avg=6.0493%`, `minYear=38`, `yearMin=81.71%`, `micro=1.21%`.
- V185 child: `n=87`, `WR=93.10%`, `Avg=8.0206%`, `minYear=3`, `yearMin=82.35%`, `micro=0%`, same-day=0.
- Combined: `n=334`, `WR=86.23%`, `Avg=6.5628%`, `minYear=41`, `yearMin=82.81%`, `micro=0.90%`, same-day=0.

Decision: `V185_COMBINED_PRODUCTION_GATE_PASS__SHADOW_ONLY`.

Important nuance: V185 child alone does **not** pass child gate because `n=87` and yearly counts are small. It is only usable as a combined V175+V185 overlay candidate until a larger independent child supply is found.

## V186: robustness sensitivity supports shadow-promotion design

Artifact: `/root/.hermes/smc_audit/v186_v185_robustness_sensitivity_20260626_001356`

Grid around the V185 thresholds tested 49 adjacent variants. `9/49` passed the combined production gate, so the result is not a single threshold knife-edge.

Representative passing variants:
- `risk>=3.0 & body>=48`: child `n=93`; combined `n=340`, `WR=86.47%`, `Avg=6.6571%`, `minYear=42`, `yearMin=83.33%`, `micro=0.88%`.
- `risk>=3.0133 & body>=50`: child `n=87`; combined `n=334`, `WR=86.23%`, `Avg=6.5628%`, `minYear=41`, `yearMin=82.81%`, `micro=0.90%`.
- `risk>=2.5 & body>=48`: child `n=105`; combined `n=352`, `WR=86.36%`, `Avg=6.5261%`, `minYear=44`, `yearMin=82.61%`, `micro=0.85%`.

Leave-one-year-out for chosen rule remained directionally stable on WR/Avg, but 2024-excluded micro rose to `1.44%`; do not ignore this in promotion review.

Decision: `V186_ROBUST_ENOUGH_FOR_SHADOW_PROMOTION_DESIGN`.

## Current direction

Closed/unusable:
- naive new range-spring generator V183;
- generic V175 exit overlays V177;
- 60min historical exits with current coverage V179;
- unfiltered V167 leftovers V181;
- fixed full-runner child exits V182.

Usable next artifact:
- V185/V186 is the first material qualitative improvement since V175.
- Treat it as a **shadow combined production candidate**, not a direct production promotion yet.

Next concrete step:
1. Formalize V185 into a reproducible script under `scripts/v25` only after GitNexus impact analysis if editing repo code.
2. Recompute active candidates from current latest V128/V167-style dry-run source, not historical trade files.
3. Run frontend/API dry-run checks with zero watchlist mutation first.
4. Only after dry-run and current active synchronization pass, consider promotion routing.
