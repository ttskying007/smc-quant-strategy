# V81 Context-First Smart Money Lifecycle Generator Lesson

Session date: 2026-06-12

## Why this reference exists

A repeated failure mode appeared across V70-V81: changing FVG to OB, anchoring OB to sweep origin, or tuning SL/TP did not solve the core SMC problem. The durable lesson is that **single-stock POI detection is insufficient unless the broad environment first says Demand Zones are allowed to work**.

This is not a frontend/field/T+1 issue and not an OB/FVG label issue. It is a signal-layer architecture issue.

## Correct generation order

Future SMC generators should create candidates in this order, not post-filter old trades:

1. **Broad environment permission**
   - Demand-valid: `ACCUMULATION`, `RECOVERY`, `BULL_CONTINUATION`
   - Risk states: `BEAR_RISK`, `DISTRIBUTION`, `MIXED`
   - Risk states should not accept ordinary continuation; they may only allow explicit reversal stories such as SSL sweep → CHOCH.

2. **Single-stock trend regime**
   - `UP_CONTINUATION`
   - `DOWN_REVERSAL_REQUIRED`
   - `RECOVERY_TRANSITION`
   - `RANGE_TRANSITION`

3. **SMC event**
   - Continuation: BOS/CHOCH/MSS-style break in an allowed continuation environment.
   - Reversal: SSL sweep followed by CHOCH/MSS, especially in risk/bear environments.

4. **POI location**
   - POI should be a demand area created by the event/pullback sequence, not merely the last arbitrary OB before a signal.
   - POI must be in discount/deep-discount relative to the active swing.
   - Use event → pullback POI → reclaim order; avoid selecting future-confirmed or unrelated historical zones.

5. **Entry location**
   - Require POI touch and later reclaim.
   - The same bar that pierces/touches the POI should not count as its own reclaim confirmation.
   - A close breaking the POI before reclaim invalidates the candidate.

6. **Exit semantics**
   - Distinguish at least:
     - `TAKE_PROFIT_LIQUIDITY_TARGET`
     - `EXIT_POI_CLOSE_BREAK`
     - `EXIT_TREND_STRUCTURE_DAMAGE`
     - `TIME_STOP_NO_SEMANTIC_EXIT`
   - For A-shares, T+1 must be enforced by construction: exit scanning starts after the entry date; no-next-bar candidates should be removed, not cosmetically shifted.

## V81 prototype result

A fresh V81 generator was created with tests for:

- accumulation environment allowing BOS → POI → reclaim;
- mixed environment blocking plain continuation;
- bear-risk environment allowing only SSL sweep → CHOCH reversal;
- POI discount validation and close-break invalidation;
- separate exit semantics;
- liquidity target above entry, not stale break-level target.

The full 4,655-stock scan produced many candidates but was not production-ready:

| Metric | V81 prototype |
|---|---:|
| Candidates | 47,612 |
| WR | 53.27% |
| Avg PnL | -0.1160% |
| POI close break | 28.05% |
| Trend damage | 9.84% |
| TP liquidity target hit | 61.57% |

Interpretation: the architecture moved in the right direction, but the quality gate is still too broad. The next step is not more candidate expansion; it is Smart Money behavior quality gating.

## Next-step rule for future sessions

When this class of failure appears again, do not start by tuning TP/SL or replacing FVG/OB labels. Build or modify the generator so candidate creation is context-first:

```
Environment permission → trend regime → SMC event → POI → touch/reclaim entry → semantic exit
```

Then verify with tests before full scan.

## V82 quality-gate direction

V82 should focus on reducing the broad false-positive layer:

| Layer | Required improvement |
|---|---|
| Environment | Split true/false RECOVERY; treat MIXED as blocked unless range accumulation is proven. |
| Trend | Continuation must show durable HH/HL, not one-bar break only. |
| Event | SSL sweep must have meaningful pierce and fast reclaim; BOS must not immediately fall back. |
| POI | Require stronger reaction: later reclaim, two-bar response, or higher-low after touch. |
| Exit | Remove no-next-bar candidates; classify POI break/trend damage before generic time-stop. |

## Pitfalls

- Do not call an old candidate “smart money” merely because it has an OB/FVG zone.
- Do not use aggregate WR/RR as proof that the signal layer is correct; inspect story buckets and semantic exits.
- Do not allow MIXED/RECOVERY to pass without proving demand validity. These states were major contamination buckets.
- Do not let same-day T+1 exits be “fixed” by shifting after simulation; enforce T+1 at the exit scan boundary.
