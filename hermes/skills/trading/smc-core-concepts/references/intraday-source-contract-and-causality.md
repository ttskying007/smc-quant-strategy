# Intraday Source Contract and Causal MTF Research

Use this before promoting any SMC multi-timeframe entry model.

## Non-negotiable order

1. Audit data availability on the intended full historical window before coding a strategy.
2. Verify per-symbol coverage by year, timestamp slots, missing days, IPO dates, suspensions, and response failures.
3. Verify price-scale compatibility between daily POI data and intraday bars.
4. If daily and intraday prices differ because one is qfq/adjusted and the other is raw, **do not compare their price levels directly**.
5. Reconstruct daily OHLC from the same intraday raw source, then re-run the semantic oracle on that same-scale daily series.
6. Only after source and semantic gates pass may the lifecycle be evaluated:
   `daily fresh POI → intraday first touch → reclaim/hold → next intraday open entry → T+1 exit replay`.

## Data-source audit pattern

Do not trust a provider's requested bar count. Request the maximum and measure the returned data.

For every source, record:

| Check | Required evidence |
|---|---|
| Effective range | actual first/last timestamps, not requested dates |
| Historical coverage | symbols with bars in each target year |
| Bar geometry | expected A-share 60min slots and non-boundary incomplete days |
| Universe coverage | success/failure count plus IPO-vs-data-missing classification |
| Cross-source consistency | aggregate intraday OHLC versus source-native daily OHLC |
| Price-scale contract | raw/qfq/hfq status; date-level scale mismatch audit |

A provider can be usable even if new IPOs lack 2023 data; classify those as listing-limited, not source failures. A mature stock missing a required year is a hard data failure.

## Known source behavior (must be re-probed, not assumed)

- Tencent 60min can silently return far fewer bars than requested.
- mootdx uses `frequency`, not `category`; frequency `3` is 60min. Its historical horizon must be measured with pagination.
- Sina's HTTP `CN_MarketData.getKLineData` endpoint has yielded long raw 60min A-share histories using `scale=60`, `ma=no`, `datalen=10000`. Its 60min aggregation matched its own raw daily series in verification. Treat this as a source candidate, not a permanent availability guarantee.
- Raw intraday bars may not match a qfq daily cache around corporate-action periods. This is a scale contract issue, not an entry signal.

## Anti-leakage rules for MTF entry

- Touch is observable only after the touch bar closes.
- Reclaim/hold confirmation is observable only after its designated closing bar(s).
- Entry must be no earlier than the next intraday bar's open after the final confirmation.
- Never evaluate entry quality with a future confirmation feature (`takeover_2`, `bull_count_3`, later hold bars, post-entry pullback, MFE/MAE, exit outcome).
- Daily structure pivots remain unavailable until their right-side confirmation period ends.
- Enforce A-share T+1 in the replay and record zero same-day exits as a release gate.

## Promotion gate

An intraday candidate is research-only until all of these pass:

- data coverage and source-scale audit;
- independent semantic re-derivation of daily primitives;
- chronological out-of-sample test with fixed rule;
- full-market T+1 replay;
- predeclared economic thresholds and per-year minimum sample coverage;
- per-trade provenance: `event → POI → touch → confirmation → entry → exit`.

Do not replace missing coverage with a recent-only result, and do not call an execution refinement a production improvement until it is validated over the same historical population as the baseline.
