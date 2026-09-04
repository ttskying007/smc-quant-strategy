# Intraday Source Completeness and Causality Gate

Use this before claiming an A-share multi-timeframe (daily → 60min) signal is backtestable or promotable.

## Why this gate exists

A valid daily SMC event does not make a 60-minute entry study valid. The intraday layer must have complete historical coverage, a stable time contract, and prices aligned to the daily series. A short recent cache cannot stand in for a multi-year study.

## Source feasibility pattern

Baostock's `query_history_k_data_plus` supports historical A-share `frequency='60'` requests. For normal SH/SZ A shares, a representative 2023–2026 probe returned four terminal bars per complete trading day:

- `10:30:00`
- `11:30:00`
- `14:00:00`
- `15:00:00`

Use `adjustflag='2'` (forward-adjusted) consistently for both the daily and 60min datasets used by a new study. Do not join a freshly fetched Baostock adjusted 60min series to a stale/independently adjusted daily cache by absolute price: later corporate actions can change the scale of historical qfq prices between providers or fetch dates.

## Mandatory source audit before strategy generation

For every symbol in the actual research universe:

1. Query the entire requested historical span at 60min.
2. Record provider status, first/last timestamp, bar count, distinct trading dates, and counts by calendar year.
3. Require exactly the expected four 60min terminal slots on every returned trading date; materialize exceptions.
4. Distinguish a new listing (no pre-IPO history expected) from a source failure. Do not silently exclude failures.
5. Independently aggregate each 60min day and compare its OHLCV to the daily series from the **same provider and adjustment mode**. A mismatch blocks the dataset.
6. Persist a no-write audit report with universe count, exchange/board coverage, per-year coverage, zero-bar symbols, partial-day symbols, and examples of every failure class.

A sample probe is source discovery only. It is **not** sufficient for a full-market historical claim.

## Legal MTF entry contract

Only after the source audit passes, build entries with this causal order:

`daily event/POI known → 60min first touch → 60min reclaim/hold confirmation → next 60min open entry → daily structural SL / already-confirmed liquidity target → A-share T+1 exit replay`

Required per-row fields:

`daily_event_idx`, `poi_idx`, `m60_touch_idx`, `m60_reclaim_idx`, `m60_confirm_idx`, `entry_idx`, `entry_timestamp`, `exit_idx`.

Hard checks:

- `poi_idx <= m60_touch_idx <= m60_reclaim_idx <= m60_confirm_idx < entry_idx < exit_idx`
- Entry must use the next executable open, not the confirmation close or a same-bar high/low.
- No selector may read a future confirmation counter (for example a post-reclaim `_2`/`_3` feature) while entering before that counter is observable.
- T+1 violations must equal zero.

## Promotion boundary

Passing source completeness proves only that an intraday experiment is possible. It does not prove a signal edge. Promotion still needs a fresh full-universe chronological replay, independent semantic re-derivation, per-year/month stability, and the established economic thresholds.
