# Raw-Daily → True MTF Research Closure

Use when intraday SMC research depends on historical bars that are available only from a 60-minute source.

## Non-negotiable source contract

1. Build the research universe from the local symbol registry, but use legacy daily data **only as calendar/reference metadata**. Never use its adjusted OHLCV values for POIs, signal geometry, entry, or outcome.
2. Aggregate a raw daily bar only from exactly four valid 60-minute slots: `10:30`, `11:30`, `14:00`, `15:00`.
3. Record every source-day anomaly. Drop an anomalous day rather than repairing it; increment a `segment_id` after each market-calendar gap so daily signal logic cannot see across it.
4. Account for every symbol explicitly: eligible, day-quarantined, IPO-after-start, delisted/pre-window, or hard unexplained source failure. A data gate passes only when unexplained failures are zero.

## Required semantic boundary

Before any MTF trade replay, run two independent implementations over the rebuilt raw-daily segments and require exact agreement for:

- confirmed 3-left/3-right swings, visible only at pivot + 3;
- BOS/CHOCH close beyond a confirmed swing by 0.2%; canonicalize MSS to its underlying CHOCH identity when comparing structural-break geometry;
- backward event-anchored nearest opposite-candle OB within 10 bars;
- three-bar FVG using the exact numeric expression `(gap / price) > 0.0005` to avoid floating-expression mismatch;
- confirmed-swing sweep: 0.3% wick pierce plus close reclaim, maximum 60 bars from the pivot.

A zero mismatch differential establishes semantic equivalence and causality; it does **not** establish economic edge.

## True MTF execution contract

For a raw-daily fresh demand POI:

`daily event close → later trading-date 60m first touch → reclaim(close > zone_high) → subsequent hold(close > zone_high and low >= zone_low) → next 60m open`

- Never let same-day 60m bars after the daily close be treated as earlier-known daily information.
- Cancel a POI if a pre-entry 60m close falls below `zone_low`.
- Use only a structural target confirmed before entry.
- Enforce one causal candidate per symbol/open (choose latest known source context); replay positions serially per symbol.
- For A shares, exits begin only on a later trading date. If SL and TP share a bar, execute SL first.

## Promotion ordering

First audit source coverage, raw-daily lineage, semantic differential, time order, duplicate open, overlap, and T+1. Then evaluate the predeclared economic gate. If the economic gate fails, close the branch immediately: do not run promotion-only Oracle/shadow/UI work and do not use its clean mechanics as evidence of a tradable strategy.

## Verified closure example

A full-market same-source run can have perfect data lineage, zero semantic mismatch, zero time-order/T+1/overlap defects, and still fail economically. In the 2026-07 validation, a raw-daily Bull BOS/CHOCH demand-OB → 60m touch/reclaim/hold replay produced 4,832 serial trades, WR 35.3891%, average PnL -0.1562%, minimum annual WR 32.04%, and micro-profit rate 2.4007%. This is a branch-closure result, not a production candidate.
