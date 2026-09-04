# Partial-history M15 research: early participation is not takeover

## Scope

Use a complete source-isolated available interval (for example 2025-04..2026-07) to research an SMC strategy. This is allowed even when full 2023+ canonical intraday history is missing; it remains research-only until separately production-qualified.

## Reusable causal protocol

1. Freeze a new object before outcomes: daily confirmed 3L/3R SSL sweep + close reclaim, then a defined next-session intraday observation and entry time.
2. Enforce support after every pre-entry attrition stage, not only at raw-seed level: total `n>=1000`, each available calendar year `n>=300`.
3. Independently rebuild the full raw identity set, requiring zero missing and zero extra identities.
4. Before opening outcomes, derive a structural stop and a nearest unconsumed target confirmed before entry. Require `planned_RR>=1.5` and a fixed observable horizon.
5. Run exactly one strict T+1 replay: exit evaluation begins the next trading day, fee and same-bar precedence frozen.
6. Close the exact contract if any quality gate fails; no selection by year, symbol, breadth, RR, stop, target, hold, or winner/loser statistic.

## Mechanism lesson

A chain such as

`daily SSL sweep/reclaim -> next-session first120 sector expansion -> first120 stock participation -> 13:00 entry`

can pass all source, support, Oracle, pre-entry RR, and T+1 requirements yet fail economically. If payoff is adequate but stop exits dominate, the evidence says the sector’s early participation is **not** proof that the individual reversal survived structurally after entry.

Do not turn the observed winner/loss medians into a filter. The next ontology must change the causal event itself: make **post-lunch individual structural survival** (e.g., externally confirmed M15 break plus protected higher low) a pre-entry condition, then restart the entire outcome-blind chain.

## Boundary

- Partial-history success is not permission to claim full-history/current production readiness.
- Partial-history failure is not a reason to stop strategy research altogether.
- `EMPTY_BOOK` prevents production writes; it does not prevent no-write research using valid existing data.
