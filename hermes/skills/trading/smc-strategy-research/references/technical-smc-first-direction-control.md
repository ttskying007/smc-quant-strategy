# Technical-SMC-First Direction Control

Use this reference when a strategy-research session drifts toward funding, PIT announcements, or corporate disclosures while the user's objective remains SMC price-structure correctness.

## Primary rule

Auxiliary information sources may support diagnostics, but they must not become the signal generator unless the user explicitly changes the strategy objective. Re-anchor on raw OHLCV and the smallest causal technical state machine.

## Canonical technical path

`confirmed swing -> SSL/BSL liquidity pool -> one-time sweep -> BOS/CHOCH -> displacement -> backward causal OB/FVG -> first touch -> reclaim/hold -> next eligible entry`

## Semantic checks before performance

- A structural pivot must have completed right-side confirmation before it can be broken.
- A swept liquidity level must be tracked as consumed; repeated dips/re-crosses cannot mint duplicate events.
- A bullish/bearish OB must be located backward from the structural event as the last valid opposite candle, not by scanning event-after pullback candles forward.
- FVG geometry must be tied to the displacement sequence and retain its causal three-candle identity.
- Entry requires ordered touch/reclaim/hold confirmation; do not treat a historical contract or high WR as proof that the current scanner uses the same ontology.
- Run a full-universe, no-write supply-chain audit with counts at every stage: `context -> event -> POI -> touch/reclaim -> entry -> release`.

## Diagnosis and closure

If the audit fails, classify the result as a signal-semantics/source mismatch. Do not rescue it with WR/RR, risk, target, hold, or market-state filters. Rebuild the smallest causal technical generator, independently audit anchors and chronology, then authorize at most one frozen strict-T+1 replay. Keep production `EMPTY_BOOK`/fail-closed until the rebuilt current scanner and replay contract agree.

## Evidence pattern from the V81/V85/V88 audit

The legacy daily path used rolling 3–5-bar highs/lows and an event-after bearish candle for POI construction. A full-market no-write audit found abundant raw events but severe semantic mismatch: many candidates did not close above a prior confirmed swing, zones were at/after the event, and zones did not match the nearest backward bearish candle. This is a structural source mismatch, not a frontend shortage or a reason to tune release filters.
