# V71 Context→Event→POI State Machine Lesson

## Trigger

Use this when an SMC A-share system keeps failing even after field fixes, T+1 fixes, TP/SL changes, or replacing FVG with OB. The durable lesson: a single-stock POI cannot be validated in isolation. Demand Zone validity depends on the larger SMC story.

## Core correction

Do **not** treat `FVG_Demand`, `OB_Demand`, or an OB anchored to a sweep source as sufficient. First classify the full story:

1. **Market context**
   - `UP_CONTINUATION_CONTEXT`: HH/HL continuation; BOS pullback setups can be valid.
   - `DOWN_REVERSAL_NEEDED_CONTEXT`: LH/LL; long needs SSL sweep + CHOCH/MSS before demand POI.
   - `RANGE_OR_TRANSITION_CONTEXT`: require extra confirmation; otherwise POI is ambiguous.
   - `DOWN_CONTINUATION_DANGER`: demand zones are usually invalid unless a strong CHOCH and OTE reclaim occur.
2. **Event type**
   - Continuation: `BOS/MSS → pullback to Demand POI`.
   - Reversal: `SSL sweep → CHOCH/MSS → pullback to Demand POI`.
   - No trade if the event does not match context.
3. **POI position**
   - Entry must be in discount/OTE relative to the impulse leg.
   - FVG is an imbalance/helper, not automatically a smart-money cost area.
   - Prefer OB or OB+FVG overlap; require POI not already closed below.
4. **Entry confirmation**
   - Price must touch POI and reclaim/react before entry.
   - No reaction before entry means the POI is not proven active.
   - Closing below POI before entry means the zone is likely dead/mitigated.
5. **Exit semantics**
   - SL is not just fixed %: use POI close-break, prior HL/SSL break, or structure invalidation.
   - TP should target prior HH/BSL/liquidity pool or next structural objective.

## Audit pattern

When diagnosing this failure class, produce a non-production audit first:

- For every trade, derive only pre-entry facts.
- Classify: market context, liquidity event, structure event, POI discount/OTE position, POI touch/reclaim, POI closed-below state.
- Bucket outcomes by `smc_story`, `market_context`, `pd_zone`, and `primary_fail`.
- Search gates only after the state labels exist; do not tune TP/SL before proving the story.

## Failure labels worth tracking

| Label | Meaning |
|---|---|
| `NO_POI_REACTION_BEFORE_ENTRY` | Price reached POI but no reclaim/reaction happened before buy. |
| `PRICE_NOT_IN_DISCOUNT_POI` | Entry/zone is not in discount or OTE of the impulse leg. |
| `POI_ALREADY_CLOSED_BROKEN` | Price closed below demand before entry; zone likely dead. |
| `TOO_DEEP_POSSIBLE_STRUCTURE_BREAK` | Retrace is deep enough to be structural damage, not normal pullback. |
| `NO_VALID_LIQ_OR_STRUCTURE_EVENT` | POI exists but lacks a valid SMC event chain. |

## Session evidence pattern

A useful audit found that only ~23.6% of V68 trades had a complete SMC story. The main defects were missing POI reaction, non-discount POIs, and zones already closed below before entry. This confirmed that the root cause was missing Context→Event→POI→Reaction state modeling, not FVG-vs-OB naming or field plumbing.

## Implementation note

The next engine should be built as a layered state machine, not a flat signal list:

```text
Layer 1: Market context
Layer 2: SMC event: sweep / BOS / CHOCH / MSS
Layer 3: POI: OB / OB+FVG / OTE / auxiliary FVG
Layer 4: Entry confirmation: touch + reclaim + no close-break
Layer 5: Exit semantics: POI break / structure break / liquidity target
```
