# EMPTY_BOOK visual audit, V517 display, and structural-RR feasibility

## Scope

Use when a SMC deployment has no promoted production strategy (`EMPTY_BOOK`) but retains frozen research and quarantined historical artifacts.

## Core separation

`EMPTY_BOOK` must block only production effects:

- no current BUY / watchlist / position writes;
- no historical backtest row reused as a current candidate;
- no manual monitor insertion as a bypass.

It must **not** erase the inspection surface. Retain, with explicit labels:

1. Interactive K-line: version selector, timeframe selector, signal-family toggles, swings, BUY/SELL, SL and TP overlays.
2. Frozen research replay: full transaction ledger with signal date, strict T+1 entry date, entry, structural SL, structural target, planned R, exit and PnL.
3. Historical artifact audit: old picks/backtests in a separate read-only route, never aggregated into current production metrics or active picks.
4. Dashboard links that make the three layers discoverable: current production state, frozen research audit, legacy artifact audit.

## Display contract

A visual SMC overlay (Swing / OB / FVG / Sweep / BOS / CHOCH) may be rendered alongside a research replay only if it is labelled **display-only context**. It cannot add trade rows or silently expand the replay's entry condition. The research trade must separately show its actual causal chain and execution fields.

For every replay row, the K-line contract should state:

```text
causal combination -> signal/response date -> T+1 entry
-> structural SL anchor -> structural TP anchor -> planned RR
-> actual exit reason and PnL
```

## Structural TP is not automatically tradeable

A structural SL and structural target can be causally valid but economically infeasible. Verify planned RR before declaring a strategy promotable.

The V517 effort-result study was audited with a pre-entry-only feasibility condition:

```text
entry = following eligible open
SL = sweep low × 0.99
TP = nearest prior visible confirmed swing high
require planned RR >= 1.5 before opening outcomes
```

Result (2026-07-17): 404 source seeds -> 79 feasible (2023/24/25/26: 16/35/19/9), failing the minimum support gate of total >=300 and each year >=40. Strict replay of the 79 gave WR 30.38%, AvgNet +0.401%, PF 1.1178; therefore it is not promotable. Do not use a sparse high-R subset as a production substitute.

## Verification checklist

- API/K-line sample has nonzero SMC visual signals and swings.
- Chart option contains BUY, SL, TP overlays for a replay trade.
- Replay ledger count matches frozen artifact count.
- Current scanner rows come solely from the current committed epoch.
- Legacy rows use a distinct audit scope and cannot reach monitor/position APIs.
- Recompute planned RR from displayed entry, SL and TP; do not trust a copied summary field.
- If a new feasibility gate shrinks support below its predeclared gate, stop promotion before oracle/replay variants.
