---
name: intraday-causal-strategy-research
description: Build and validate intraday price-action strategy state machines with causal timestamps, lifecycle integrity, independent raw-bar oracles, and one-shot preregistered replay.
---

# Intraday Causal Strategy Research

Use for intraday SMC/price-action research when a candidate must be proved semantically correct before any performance replay, promotion, or live scanning.

## Non-negotiable sequence

1. **Freeze the semantic ontology before outcomes.** State each causal node, its observable timestamp, cancellation reasons, and terminal states. Do not start from WR, RR, SL/TP, a desired trade count, or a historical filter.
2. **Build a one-way state machine.** Each state must move only forward or terminate. Persist all terminal records—not just valid candidates.
3. **Audit raw-bar semantics independently.** A separate implementation must read raw OHLC and validate the generator's pivots, ordering, zones, lifecycle, and entry identities without importing the generator.
4. **Review deterministic examples.** Produce one valid, one reaction-failure, and one invalidation example selected by deterministic identity, not post-entry outcome.
5. **Only then preregister one replay.** Freeze execution, target, structural invalidation, A-share T+1 exit treatment, collision policy, and support/quality gates before reading results.
6. **Fail closed.** A semantic, support, or frozen-replay failure closes the ontology. Do not tune windows, thresholds, POI definitions, stops, targets, holding time, or selectors after outcomes are known.

## Required semantic artifacts

Every state-machine record should retain:

```text
symbol, timeframe,
liquidity pivot time, pivot confirmation time,
sweep time and price,
pre-event structure reference and its confirmation,
CHOCH/MSS time,
displacement start/end,
OB and FVG time,
zone bounds,
first-touch/reclaim/hold/entry timestamps,
invalidation timestamp and terminal reason
```

Artifacts must explicitly state `research_only=true`, `production_write=false`, `frontend_write=false`, and `watchlist_write=false`.

## Lifecycle integrity rules

- A pivot cannot be used before its right-side confirmation is available.
- A structure break must reference a pivot already confirmed before its triggering event.
- A causal OB is traced backward from the displacement leg; it is never automatically the break bar or an arbitrary historical opposite candle.
- A first zone touch determines the lifecycle. A failed reclaim or zone-low breach cancels immediately; a later touch cannot revive the setup.
- A symbol has one active chain at a time; a new root event cancels an unfinished old chain.
- A valid entry identity must be unique by `symbol + entry_time`.

## Verification checklist

Before replay, independently show zero for:

- early pivot use;
- causal timestamp inversion;
- OB equal to structure-break bar;
- an earlier zone touch before the recorded first touch;
- second-touch reclaim admission;
- duplicate actionable identities.

A semantic pass proves only causal consistency. It is not evidence of discretionary signal truth, economic edge, complete market coverage, or production readiness.

## References

- `references/intraday-reversal-state-machine-semantic-gate.md` — detailed SSL sweep → CHOCH → displacement → pristine POI gate and strict replay boundary.
