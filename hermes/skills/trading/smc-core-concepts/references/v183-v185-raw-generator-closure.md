# V183-V185 raw generator closure

Date: 2026-06-26

## Trigger

Use after V175/V180-V182 closure when the next question is whether to continue researching by building a new candidate generator from raw daily K-line data instead of filtering V128/V167/V175 artifacts.

## Predeclared gates

Production upgrade usable:
- non-leaking source-side rule;
- T+1 violations = 0;
- combined/all engine `n >= 260`;
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

## Completed raw-generator audits

### V183 raw SSL sweep lifecycle generator

Artifact: `/root/.hermes/smc_audit/v183_structure_lifecycle_generator_20260626_120140/`

Generator source: raw daily OHLCV only, not V128/V167/V175 filter.

Semantic chain:
`prior weak/compressed context -> confirmed prior swing-low SSL sweep -> micro CHOCH -> demand zone -> touch+reclaim -> next-open entry`.

Result:
- `n=1898`, `WR=44.26%`, `Avg=0.3772%`, median `-2.4599%`.
- Year WR: 2023 `41.21%`, 2024 `37.38%`, 2025 `54.37%`, 2026 `35.93%`.
- SL/GAP_SL rate `51.84%`; T+1 violations `0`; overlap vs V175 `0`.
- Decision: `V183_NO_USABLE_ENGINE__NO_WRITE`.

Root cause:
- Raw SSL sweep + micro CHOCH without V132 true-takeover semantics is not a strong A-share daily signal.
- Winners/losers are not separable by simple pre-entry source fields (`risk_pct`, `zone_width`, `sweep_pierce`, wick ratio); median differences are small.

### V184 reaction-confirmed variants over V183 supply

Artifact: `/root/.hermes/smc_audit/v184_v183_reaction_confirmation_20260626_120605/`

Variants tested:
- `react1_close_above_zone`
- `react2_higher_close`
- `displacement_0p6atr`
- `no_low_break_3bar`

Best result:
- `no_low_break_3bar`: `n=609`, `WR=48.44%`, `Avg=1.0347%`, `min_year_n=52`, `all_year_WR_min=35.03%`, SL/GAP_SL `40.72%`, T+1 `0`.
- Decision: `V184_NO_USABLE_REACTION_ENGINE__NO_WRITE`.

Root cause:
- Waiting for extra reaction reduces SL rate but does not repair signal quality; yearly stability remains structurally bad, especially 2024.
- Therefore V183 failure is candidate supply quality, not only entry timing.

### V185 raw BOS continuation demand-zone generator

Fast artifact: `/root/.hermes/smc_audit/v185_raw_bos_continuation_fast_20260626_121849/`

Generator source: raw daily OHLCV only.

Semantic chain:
`confirmed swing structure -> BOS continuation above prior swing high -> last bearish demand candle -> retrace+reclaim -> next-open entry`.

Result:
- `n=35704`, `WR=41.06%`, `Avg=0.2994%`, median `-2.6949%`.
- Production robustness years from 2023+: `n=35687`, `WR=41.06%`, `Avg=0.2989%`.
- Year WR from 2023+: 2023 `31.29%`, 2024 `34.04%`, 2025 `47.16%`, 2026 `39.44%`.
- SL/GAP_SL rate `56.59%`; T+1 violations `0`; overlap vs V175 `5`.
- Best simple source-side frontier found during follow-up search only reached about `WR=50.51%`, `Avg=1.455%`, `n=196`, `all_year_WR_min=32.26%`.
- Decision: `V185_NO_USABLE_ENGINE__NO_WRITE`.

Root cause:
- Generic BOS continuation demand-zone logic produces too many false continuation setups in A-shares.
- Simple source-side filters on BOS strength, risk, zone width, RR, and zone distance from swing low cannot approach the V175/V172 quality frontier.

## Updated closure decision

Closed paths now include:
1. More scalar filters on V172/V175.
2. Generic exit overlays on V175.
3. 60min historical production exits with current cache coverage.
4. V167 leftover child engine.
5. Waiting extra daily bars after V128 reclaim.
6. Fixed runner exits for the best V167 leftover child.
7. Raw daily SSL-sweep lifecycle generator without true-takeover semantics.
8. Extra reaction confirmation over raw SSL supply.
9. Raw daily BOS-continuation demand-zone generator.
10. Simple source-side threshold search over raw BOS continuation rows.

## Next research direction

Do **not** continue tuning raw daily SSL/BOS generators. They fail at signal supply quality.

The next plausible qualitative direction is one of:
- reconstruct V132-style true-takeover features directly from raw OHLCV as a first-class generator, then compare to V175/V167 lineage;
- obtain deeper historical intraday/60min data before making execution-layer claims;
- build a market-regime/context classifier that is still pre-entry and non-leaking, because V183/V185 failures show event/POI definitions alone do not separate A-share winners.

Any next version must stay shadow-only until it passes the gates above.
