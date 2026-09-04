# Causal SMC state-machine replay closure

## Scope

Use for a causal reversal state machine after semantic validation and before any production promotion.

## Semantic contract

The chain must be auditable as:

`confirmed SSL → wick sweep/reclaim → break of pre-sweep confirmed high → bullish displacement → displacement-derived causal demand OB/FVG → pristine first touch → immediate reclaim → hold → next tradable-bar entry`.

Enforce the three-layer separation:

- **L1:** confirmed SSL + sweep/reclaim, no buy.
- **L2:** close-accepted CHOCH/MSS and displacement; derive OB/FVG from the displacement leg, not a break bar or arbitrary candle.
- **L3:** strict lifecycle `FRESH → FIRST_TOUCH → RECLAIM → HOLD → ELIGIBLE_NEXT_BAR`; first-touch failure or zone-low invalidation cancels immediately, and later touches cannot revive the zone.

## Semantic gates before outcomes

Require zero: early pivot use, timestamp order violation, break-bar OB anchor, post-first-touch revival, and duplicate `symbol + entry_date` BUY. Maintain one active chain per structural event; new sweep/invalidation cancels stale chains. Candidate output needs all node times, zone bounds, cancellation reason, and entry identity.

## One frozen execution replay

Freeze **all** contract terms before results: entry, structural stop, pre-entry target/RR, strict T+1 start, gaps, collision ordering, time stop, fee, and serial position behavior. If a preliminary run lacks a frozen term, quarantine it and report no performance; correct only that omission, then perform one contract-complete replay.

Independently reproduce every trade from raw bars and verify: source identity, stop/target, exits, gap/collision/time-stop handling, fees, serial positions, duplicate IDs, and zero same-day exits.

## Closure rule

Semantic validity and economic promotability are independent. A contract-complete replay that fails preregistered support, annual stability, profitability, or execution gates closes the ontology:

`SEMANTIC_PASS → REPLAY_NOT_PROMOTABLE → NO_VARIANTS → NO_PRODUCTION`

Do not modify timing, windows, OB/FVG labels, stop, target, hold period, years, symbols, or filters to reopen it. Retain `EMPTY_BOOK`; never backfill production from historical replay trades.
