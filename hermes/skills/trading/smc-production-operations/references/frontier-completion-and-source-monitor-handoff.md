# Frontier completion and source-monitor handoff

## Purpose

Use after an autonomous research run that explored all currently authorized branches and must decide whether to continue, close, or wait for a new data dimension.

## Required reconciliation inputs

Check four independent domains:

1. **Price-only frontier** — the latest W/D/60m or OHLCV ontology closure.
2. **Independent PIT branches** — every genuinely new date-sensitive external-information ontology attempted since the prior closure.
3. **Source qualification** — source timing, date addressability, denominator, continuity, namespace isolation, and cache integrity.
4. **Production boundary** — authoritative registry, buy permission, active candidate count, fallback prohibition, and write state.

Do not infer completion from one latest report. Read the terminal artifacts for each domain and persist a machine-readable reconciliation report.

## Gate semantics

- A source/support failure closes the exact ontology before outcomes; do not run an Oracle or replay after a failed pre-outcome support floor.
- An economic replay failure closes the exact ontology; do not rescue with thresholds, windows, symbols, years, timing, POI, SL/TP, holding period, or regime subsets.
- Cache integrity is not full-universe coverage and is not strategy authorization.
- A witness source may detect drift or availability but must not fill missing bars in the primary historical series.
- A completed cache does not reopen an economically failed ontology.

## Completion assertions

The final report should assert, not merely describe:

- every authorized branch is either closed economically or closed before outcomes by a support/identity/source gate;
- no outcomes were opened for support-gated branches;
- no production, frontend, watchlist, position, or registry writes occurred during research;
- the authoritative registry remains fail-closed when no strategy is licensed;
- the only legal reopening condition is a genuinely independent PIT information dimension or a complete canonical historical microstructure source.

Suggested terminal decision:

```text
RESEARCH_GOAL_COMPLETE_UNDER_AVAILABLE_INFORMATION
__NO_QUALITATIVE_CHANGE__EMPTY_BOOK__SOURCE_MONITORING_ONLY
```

## Source-monitor handoff

A retained monitor must be operationally separate from strategy work:

- use a fixed dependency-complete virtualenv/interpreter;
- use an executable wrapper and test the exact wrapper path;
- write only health/coverage artifacts and logs;
- schedule with one explicit owner;
- run once while fail-closed;
- compare the production registry SHA-256 before and after;
- report provider health and cache audit separately from `buy_enabled` and strategy authorization.

The monitor must not call scanner, replay, candidate materialization, pending-order, watchlist, position, or registry-promotion code. Provider namespaces remain isolated; cross-source overlap is evidence only, never a repair path.

## Evidence pattern

For each branch record:

```text
branch → source qualification → outcome-blind support → identity Oracle → frozen replay → metric audit → terminal decision
```

For source health record:

```text
provider login/probe → cache counts → per-source integrity → cross-source witness → monitor schedule → registry unchanged
```
