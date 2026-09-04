# Continuation POI Lifecycle Canonicalization

Use when auditing daily bullish BOS-continuation candidates before any outcome/production study.

## Problem: event rows are not independent candidates

A single unmitigated demand OB can be referenced by several later BOS events. Counting each event as a separate candidate repeats the same POI lifecycle and biases aggregate transition rates toward zones with repeated structure breaks.

**Canonical lifecycle object**:

```text
(symbol, ob_idx, zone_low, zone_high)
```

Retain the earliest causal BOS event for that object:

```text
first_event = min(rows_for_same_object, key=event_idx)
```

This is source-time safe: it chooses only the first observed structure event and never selects by a later touch, reclaim, exit, or PnL.

## No-write lifecycle contract

For each canonical object, evaluate only after `event_idx`:

```text
BOS event
→ touch: wick low <= zone_high
→ reclaim: close > zone_high
→ takeover: a later bar closes > zone_high and low >= zone_low
```

Terminal states:

- `CANCEL_ZONE_INVALIDATED`: close < zone_low.
- `EXPIRE_NO_TOUCH_30B`: no touch in a fully observed 30-bar window.
- `EXPIRE_NO_RECLAIM_30B`: touched but no reclaim in a fully observed window.
- `EXPIRE_NO_HOLD_30B`: reclaimed but no later hold in a fully observed window.
- `WAIT_*_UNOBSERVED`: current right edge is incomplete; never record it as expiry/failure.
- `TAKEOVER_CONFIRMED`: lifecycle transition only, **not** a tradable signal or a profitable trade.

## Mandatory audit boundaries

1. Keep this stage non-tradable: no entry, exit, PnL, MFE/MAE, SL/TP, watchlist, frontend, or production writes.
2. Report raw-event and canonical-zone counts separately; never present the raw count as candidate supply.
3. For annual rates, exclude `WAIT_*_UNOBSERVED` from the denominator and disclose the unresolved count.
4. Semantic differential validation should independently re-derive pivots, BOS, backward event-anchored OB, sweep, and FVG before lifecycle analysis.
5. Do not promote based on takeover rate. A lifecycle state must later pass independent, source-time outcome validation and the normal full-market production gate.
6. Do not claim full-period M60 validation if the local intraday history does not cover every tested year.

## Example evidence (V351–V352, July 2026)

- 205,049 causal daily BOS seed rows reduced to 123,365 unique demand-OB objects after canonicalization; 81,684 rows were repeated events on an existing POI.
- The independent semantic differential found zero mismatches between the source implementation and the oracle.
- The lifecycle audit remained no-write and non-tradable.
