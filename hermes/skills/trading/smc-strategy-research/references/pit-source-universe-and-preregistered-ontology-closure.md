# PIT source-universe and preregistered-ontology closure

## Purpose

Use this when an independent public disclosure field is proposed as a new causal input to price-action/SMC research. It prevents two distinct errors:

1. treating phrase hits in a narrow archive as a complete event universe; and
2. rescuing an outcome-blind support failure by changing the pre-registered price structure.

## Source qualification comes before semantic selection

A source can only be used for the universe it actually defines. A complete archive of earnings forecasts is not automatically a complete archive of share repurchases, cancellations, unlocks, or convertible bonds merely because those phrases appear in some earnings documents.

A company-action source must establish all of the following before semantic cataloging:

- action-specific complete denominator, by year;
- immutable `symbol + announcement_id + publication_time` identity;
- amendments, cancellations, implementation, completion, and supersession rules;
- action type/stage taxonomy;
- primary numeric terms and effective dates (quantity, price, percentage, balance, unlock/conversion dates);
- independent raw-document parser/oracle and coverage reconciliation.

If the candidate archive has the wrong denominator, classify it as `CLOSED_SOURCE_CANDIDATE`. Do not create an event catalog, seeds, or a backtest from literal matches.

## Semantic catalog discipline

- Match only explicit statements inside the correct document section and reporting period.
- Reject title-only inference and incidental historical/context phrases.
- Canonicalize duplicate notices using an immutable, declared `symbol + date + publication_time + announcement_id` rule.
- Use a separate parser and simple independent Oracle; sets must agree exactly.
- Set support thresholds before extraction. If the exact semantic object misses them, close it without broadening wording, adding related announcement classes, changing years, or using a result-derived subset.

## PIT-to-SMC ontology discipline

After source and semantic support pass, pre-register one causal chain before outcomes are opened:

```text
publication timestamp
→ first completed exchange session after public availability
→ response event
→ causal fresh POI
→ first touch
→ later reclaim
→ hold
→ next eligible open
→ strict T+1 execution
```

Freeze at registration time:

- public availability and event-reset semantics;
- confirmed swing and displacement definitions;
- POI origin/freshness/invalidation and lifecycle windows;
- entry, structural stop, pre-entry structural target, minimum planned RR;
- gap, same-bar collision, fees, strict T+1, 20-session time stop, serial position policy;
- seed identity, outcome-blind support thresholds, independent Oracle equality contract, and replay/promotion gates.

A seed-support failure is not an economic failure. It closes the exact ontology **before replay**, so never inspect PnL or tune response/pivot/OB/touch/reclaim/hold windows, cache ranges, SL/TP, RR, years, symbols, regimes, or legacy SMC tags to rescue it.

## Representative outcomes

- A narrowly defined explicit-positive-forecast semantic object may be closed for insufficient semantic support. It must not be broadened opportunistically.
- A separately defined current-forecast loss-to-profit event may pass semantic support but its preregistered disclosure-response/OB-retest state machine can still fail outcome-blind seed support. Example: 1,672 canonical events yielded one valid seed; the correct conclusion is `CLOSED_ONTOLOGY_NO_REPLAY`, not a parameter search.
- An archive with 100% coverage for earnings texts can still fail company-action source qualification, because coverage is only valid for the earnings universe.

## Production boundary

Current scanner reconstruction is a separate, later task. Until source, semantics, seed support, Oracle, one frozen replay, and independent metrics all pass, do not write watchlists, frontend state, positions, pending orders, or production candidates. Historical events, seeds, and trades never populate current picks.
