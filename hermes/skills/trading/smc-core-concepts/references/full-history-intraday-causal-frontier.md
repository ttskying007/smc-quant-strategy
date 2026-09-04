# Full-history intraday SMC causal frontier

Use when moving from daily SMC research to full-history intraday entry research, or when a seemingly causal intraday candidate needs production-grade closure.

## Non-negotiable release gate

A candidate is not production-eligible unless all pass:

| Dimension | Gate |
|---|---|
| Causality | Every setup field is visible before entry; `event → POI → touch → reclaim → hold → next-open` is materialized and audited. |
| Execution | A-share T+1; same-bar collision rule explicit; no same-symbol same-open duplicates; no overlapping positions. |
| Coverage | Required intraday slots are complete for every included date; malformed dates are hard boundaries or explicitly quarantined. |
| Economics | Predetermine n/year coverage, WR, average PnL, weak-year and micro-profit gates before testing. Do not optimize them after seeing outcomes. |
| Validation | Fixed-rule chronological OOS plus independent semantic re-derivation. |

## Data coverage audit

For 60-minute Chinese A-share data, validate every available daily date against the expected four slots: `10:30`, `11:30`, `14:00`, `15:00`. A date with missing/extra/malformed slots must not bridge pivots, signals, entries, or exits. Source coverage near 100% is not a full pass if any included date is malformed; quarantine those dates explicitly.

## Semantic pitfalls found in intraday SMC implementations

1. **MSS must use the intended local structure level.** `max(all known highs in a window)` is a delayed long-window breakout, not a local bullish MSS. If the contract says local reversal, anchor the break to the most recent *already confirmed* swing high.
2. **Correct semantic timing does not prove a tradeable edge.** A causal chain can still have ~60% stops. Treat this as source-signal failure, not an invitation to tune stops/targets.
3. **Candidate events are not trades.** Multiple state machines can emit the same symbol/open or create concurrent positions. Before reporting PnL, collapse same-open variants using a pre-entry deterministic rule, then replay one position per symbol chronologically until its actual exit.
4. **Do not use a prior-day context label as an automatic fix.** Test daily FVG/structure alignment only as a causal diagnostic first. If it does not materially improve out-of-sample quality, close it rather than stacking filters.
5. **PO3 is a distinct generator, not a parameter overlay.** Define accumulation from completed prior bars, manipulation from a sweep of that observed range, and distribution from a later break of that same range. It still needs the full execution and economic gates above.

## Research sequence

1. Audit source coverage and quarantine malformed intraday days.
2. Materialize raw intraday lifecycle candidates without production writes.
3. Run temporal and execution audits before reading PnL.
4. If the economic gate fails across years, close the whole semantic family.
5. Only then test a genuinely independent information layer (e.g. point-in-time cross-sectional participation), not more scalar filters on the same single-stock candle story.

## Important boundary

A local candle sequence plus a single-stock POI may be structurally valid but have insufficient predictive information. Do not claim an intraday entry model is improved merely because its bars, zones, and state transitions are causal; require the independent economic gate.
