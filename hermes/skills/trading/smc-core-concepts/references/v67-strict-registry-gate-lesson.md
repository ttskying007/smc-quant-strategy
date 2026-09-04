# V67 Strict Registry Gate Lesson

## Trigger

Use this reference when rebuilding SMC signals from source, aligning Pine/LuxAlgo semantics, or deciding whether a strict semantic version can replace the current production engine.

## Session Finding

A strict Pine/LuxAlgo-style registry can pass bar-level semantic gates while still failing trading-effect gates. In the V67 candidate, all trades were generated from a new single-source registry rather than V59/V64/V66 overlay data:

- Strict semantic gate: `90551/90551` trades passed (`strict_pass=true`).
- OB semantics: `OB_Bull` was the nearest bearish candle before the BOS/CHOCH confirmation bar.
- FVG semantics: `FVG_Bull` used exact three-candle geometry (`low[i] > high[i-2] * min_gap`).
- Structure semantics: `BOS_Bull`/`CHOCH_Bull` required close breaking the stored confirmed swing high.
- Effect gate failed: WR `41.15%`, SL rate `58.71%`, avg pnl `+0.717%`.
- Promotion decision: rollback/keep production V66; do not wire V67 to frontend/default production.

## Durable Rule

`signal_semantic_strict_pass=true` is necessary for production promotion, but never sufficient. Promotion must require both:

1. Semantic correctness gate passes.
2. Effect gate meets production thresholds.

If semantics pass but effect fails, keep the candidate as an audit artifact and explicitly rollback/retain the previous production version.

## Implementation Pattern

When rebuilding from signal source:

1. Add a class-level `strict_smc_registry.py` or equivalent single source of truth.
2. Generate trades only from the strict registry, not from legacy trade overlays.
3. Store replay fields in every trade:
   - `zone_idx`
   - `conf_index`
   - `source_event_idx`
   - `entry_index`
   - `broken_swing_idx`
   - `broken_swing_price`
   - `raw_zone_low`
   - `raw_zone_high`
4. Run a semantic hard gate that independently reloads K-lines and verifies geometry.
5. Run full-market effect validation.
6. Run a promotion gate that records `PROMOTE_*` or `ROLLBACK_KEEP_*` without touching production files unless all gates pass.

## Pitfalls

- Do not infer signal correctness from WR/RR.
- Do not promote a semantically clean engine if WR/SL/avg pnl gates fail.
- Do not overwrite frontend/default production before the promotion gate passes.
- Do not let label-only/semantic-split versions bypass their source gate: explicitly assert the source `decision` and `field_contract_gate` before setting `production_write=true`.
- Display-only contract blanks (`signal_price`, DNA, MTF labels, combo key) must be filled at the source artifact and revalidated through `/api/summary`, `/api/picks`, `/api/live-prices`, and a browser smoke test.
- Do not treat strict Pine/LuxAlgo semantics as a complete strategy; it is only the signal-definition foundation. Add selection layers separately, while preserving strict semantic replayability.

## Directional Edge Addendum

A later V67 autopsy proved the failure was directional, not just under-filtered:

- V67 forward returns after entry were weaker than same-symbol random entries on every tested horizon.
- 1D mean edge `-0.2036%`, 5D mean edge `-0.2306%`, 10D mean edge `-0.7377%`, 20D mean edge `-0.8786%`.
- Positive-rate edge was negative on every horizon (`-1.8pp` to `-3.61pp`).
- Simple additions like SSL-sweep proxy or 60D discount filtering did not improve WR materially.
- Root cause: the registry mapped `close > confirmed swing high` directly to bullish trade direction. In A-share daily data this often captures late breakouts / gap fills / post-spike retraces rather than smart-money reversal demand.

New promotion rule:

```text
signal_semantic_strict_pass=true
AND directional_edge_pass=true
AND effect_pass=true
```

`directional_edge_pass` must compare candidate entries against same-symbol random baseline over multiple forward horizons. If the candidate is weaker than random, block promotion even if semantic geometry is perfect.

V69+ direction:

- Daily strict registry should remain a POI/geometry map only.
- Daily `SSL sweep → CHOCH → OB discount retrace` is not sufficient; V68 full-market validation still lost to same-symbol random on every horizon.
- Direction should come from lower-timeframe or post-zone reaction evidence, not from the daily CHOCH itself.
- FVG context on daily bars is not automatically positive; in V68 the FVG-present bucket underperformed FVG-absent.
- Any next candidate must prove directional edge before effect metrics are trusted.

