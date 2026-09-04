# Source qualification and prolonged EMPTY_BOOK closure

## Use

Use when a prolonged absence of current picks is suspected to be a broken scanner, a missing strategy supply source, or an over-tight production gate.

## Four-layer diagnosis

Reconstruct the period separately as:

1. **Data/control plane** — committed refresh denominator, stale/failed symbols, and whether a legacy selector emitted rows without a complete current epoch.
2. **Authorization** — strategy license, frozen replay/release result, and whether `buy_enabled` is false because no causal strategy is promoted.
3. **Raw current supply** — outcome-blind funnel: fresh universe → first structural stage → each causal stage → full setup. Persist all partial rows with `furthest_stage` and `next_required`.
4. **Economic research result** — distinguish a source/semantic failure from a fully qualified source whose one frozen strict-T+1 replay fails its fixed gates.

A legacy candidate visible during an incomplete refresh is not evidence that the market supplied a valid pick. A fresh current epoch with `production_strategy=null`, `buy_enabled=false`, and zero picks is a correct EMPTY_BOOK state, not a scanner outage.

## Research-frontier rule

After all existing price/volume/event ontologies are economically closed, do not resume them through thresholds, windows, entry timing, stop/target, holding period, year, symbol, or regime variants. The next admissible action is **source qualification only** for a genuinely independent raw information dimension.

A candidate source must pass before any market-data join or strategy definition:

- canonical universe denominator and complete decision-year coverage;
- date-addressable records with explicit PIT availability/publication timing;
- no silent request/pagination exclusion;
- no cross-source fill;
- all qualification work outcome-blind and no-write.

## HKEX Northbound-holdings pitfall

The public HKEX Stock Connect Northbound aggregate-holdings page cannot qualify as a 2023–2025 daily PIT source where it advertises only roughly 12 months of retention and quarterly publication from 2024-08-19. A provider can return a valid recent aggregate page while still failing the historical daily source contract. Record requested date, provider-effective date, retention/granularity notices, availability errors, and per-date row count; do not use the recent page as a partial substitute or start an ontology.

## Verification

- Verify source-only artifact has no OHLCV, signal, seed, trade, outcome, PnL, SL/TP, watchlist, frontend, or production writes.
- Verify `/api/summary` has `buy_enabled=false` and zero active BUY_VALID rows when no strategy is licensed; `/api/picks` must be empty.
- Verify the browser dashboard exposes the current funnel and labels all partial rows `RESEARCH_BLOCKED_NOT_EXECUTABLE`.
- If no qualified new source remains, explicitly close the research frontier and retain EMPTY_BOOK rather than inventing a next strategy iteration.
