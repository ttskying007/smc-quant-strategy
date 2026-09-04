# V183-V186 post-V175 research closure

Date: 2026-06-25

## Trigger

Use after V175 semantic split when deciding whether to keep filtering V128/V167/V175 artifacts or rebuild SMC candidate supply.

## Predeclared usable gates

Production combined engine:
- non-leaking source-side rule;
- T+1 violations = 0;
- combined `n >= 260`;
- `min_year_n >= 40` for 2023-2026;
- `WR >= 84%`;
- `AvgPnL >= 6.2%`;
- `all_year_WR_min >= 82%`;
- `micro_profit_pct <= 1%`;
- no frontend/watchlist/API mutation before dry-run passes.

Research child engine:
- 100% non-overlap vs V175;
- `n >= 120`;
- `min_year_n >= 20` for 2023-2026;
- `WR >= 86%`;
- `AvgPnL >= 6.5%`;
- `all_year_WR_min >= 83%`;
- T+1 violations = 0.

## Completed artifacts

- V183 classical sweep/CHOCH/OB generator: `/root/.hermes/smc_audit/v183_classical_sweep_ob_generator_20260625_131931/` — `FAIL_NO_WRITE`, `n=63`, `WR=30.16%`, `Avg=-0.1649%`, T+1=0.
- V183 fresh context lifecycle generator: `/root/.hermes/smc_audit/v183_fresh_context_lifecycle_generator_20260625_155910/` — no gate pass; best variants all WR≈38-43%, Avg≤0.89%.
- V183 context-first fresh generator: `/root/.hermes/smc_audit/v183_context_first_fresh_generator_20260625_163211/` — `UNUSABLE`, `n=3636`, `WR=31.35%`, `Avg=0.3758%`, one T+1 bug in prototype, no production writes.
- V183 target geometry probe: `/root/.hermes/smc_audit/v183_target_geometry_shadow_probe_20260625_190206/` — no usable child; high Avg frontier exists but WR/year robustness fails.
- V184 non-leaking frontier probe: `/root/.hermes/smc_audit/v184_nonleak_frontier_probe_20260625_193511/` — no non-leaking V183/V128 rule frontier passed. Context-first top frontier only `WR≈62.5%, Avg≈3.75%`; target-geometry top frontier was 2026-only/high-price regime and failed production.
- V185 market breadth/regime probe: `/root/.hermes/smc_audit/v185_market_regime_breadth_probe_20260625_195417/` — no pass. High-risk date-breadth buckets had `WR≈87%, Avg≈20%` but were missing historical years and failed micro/year gates.
- V186 V85 target-room seed probe: `/root/.hermes/smc_audit/v186_v85_target_room_seed_probe_20260625_200720/` — promising seed but not usable. Rule `V85 non-overlap AND target_pct>=10%` gave child `n=20`, `WR=90.0%`, `Avg=10.2933%`, T+1=0; combined with V175 `n=267`, `WR=84.27%`, `Avg=6.3672%`, T+1=0 but failed year-min (`81.4<82`), micro (`1.12>1`), and child sample/year robustness.

## Closed directions

Do not spend more cycles on these unless the data source changes:
1. Relabeling or scalar filtering V175/V172 rows.
2. Generic exit overlays on V175.
3. Classical SSL sweep→CHOCH→OB as a standalone fresh daily generator.
4. V128 target-geometry filters alone.
5. Cross-sectional/date breadth gates alone.
6. V167 leftover child engine and fixed runner exits.

## New actionable direction

The only promising seed is **V85 HOLD_ABOVE_POI + large liquidity target room**:

```text
Context-first demand permission
→ compact POI / HOLD_ABOVE_POI takeover
→ require pre-entry liquidity target room >= 10%
→ expand supply in a fresh generator, not by filtering old V85 rows
```

Reason:
- V85 has stable WR (`559`, `WR=89.09%`) but low Avg (`+2.71%`).
- The target-room subset has the desired Avg (`+10.29%`) and WR (`90%`) but only 20 rows.
- Therefore the next qualitative research should expand this exact mechanism's supply while preserving its semantics, not tune exits or mine V128 leftovers.

## Guardrails for the next generator

- Shadow-only until gates pass.
- No outcome fields in selectors.
- Enforce T+1 by construction.
- Required years 2023-2026 must all be represented; do not treat a 2026-only slice as production.
- Absolute price buckets are not valid SMC mechanisms unless translated into a structural/volatility/liquidity explanation.
- If the expanded target-room generator cannot produce at least `n>=120`, `WR>=86`, `Avg>=6.5`, `min_year>=20`, then mark it research-only and stop this branch.
