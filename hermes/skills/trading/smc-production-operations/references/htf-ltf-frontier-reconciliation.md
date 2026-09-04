# HTF→LTF research-frontier reconciliation

## When to use

Use after a user requests continued SMC research with higher-timeframe trend and lower-timeframe entry, especially when prior studies have already tested daily/weekly context, minute entries, volume, and PIT data.

## Required distinction

A new timeframe alone is **not** a new causal ontology. Do not reopen a closed HTF→LTF chain by replacing m15 with m60, changing the parent trend lookback, or changing an entry/volume/stop/target/hold threshold. Those are variants.

A legal new study needs an independent causal information dimension, or a newly qualified source contract that materially changes available point-in-time information.

## Reconciliation sequence

1. Read the authoritative latest decision for each source and ontology; do not rely on an older passing artifact.
2. Separate:
   - source qualification;
   - outcome-blind support;
   - independent identity oracle;
   - one frozen strict-T+1 replay;
   - promotion eligibility.
3. Reconcile all related paths before declaring an HTF→LTF direction untested. Include raw m60-only, source-derived daily→m60, price-only m15, volume/displacement m15, and HTF trend→m15 studies.
4. If all are terminal, publish one no-write frontier reconciliation with explicit `usable`, `unusable`, `only_reopen_condition`, branch decisions, and `EMPTY_BOOK` state.

## Concrete evidence from V548–V552

- V548→V550→V551 tested completed weekly+daily HL/BOS trend before source-isolated Sina m15 SSL/displacement/reclaim entry. The independent Oracle matched 220/220 identities; the frozen strict-T+1 replay had 35 trades, WR 40%, and 2025 AvgNet -1.2235%. It is closed.
- V374/V375/V377/V381 already closed the available full-history raw Sina m60 branches, including source-derived raw daily POI→m60 execution.
- V408 tested Eastmoney 5/15/30m exact historical-date availability across 2023–2026; no historical bars were returned, so no replay was authorized.
- V552 reconciled the terminal branches and retained `EMPTY_BOOK`; its conclusion was that only new date-sensitive PIT information or a genuinely new qualified full-history same-source intraday provider can reopen research.

## Pitfalls

- A local cache integrity result is not automatically a new strategy authorization.
- Do not allow a user-authorized 1–2 year exploratory replay to become production evidence.
- Never cite a positive total PnL when support, yearly stability, or WR gates failed.
- Do not write scanner, frontend, watchlist, or production artifacts during a frontier reconciliation.
