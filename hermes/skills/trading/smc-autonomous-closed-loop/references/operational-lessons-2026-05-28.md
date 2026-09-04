# SMC Operational Lessons — 2026-05-28

## Hard trading constraint: A-share T+1

A-share SMC backtests and execution must enforce T+1 strictly.

- `entry_date == exit_date` is a hard error, not a cosmetic issue.
- Engine behavior: do not allow same-day exit fills. If SL/TP/structure exit is touched on the entry day, defer evaluation/fill to the next eligible trading day.
- Audit behavior: release gate must fail any version with same-day buy/sell records.
- Frontend behavior: same-day exits must be visible as errors if they appear in historical files; they cannot enter official stats silently.

## K-line/backtest synchronization

When a trade appears in the backtest list, the same trade must also appear in:

1. K-line chart entry/exit markers.
2. K-line lower trade records table.
3. Closed-loop/autopsy drill-down if inside the selected window.

Required checks before claiming sync is complete:

- Compare backtest window trade keys `(symbol, entry_date, exit_date, entry_price)` against `/api/kline_full` output for sampled and failed symbols.
- Normalize date fields: kline cache uses `t`; trades may use `entry_date`, `signal_date`, `exit_date`.
- Normalize symbol mapping: `000027.SZ` ↔ `000027_SZ_daily_300.json`.
- Preserve key fields in lightweight cache: signal/zone/conf/entry/exit/source_event/family/BQ fields needed by frontend tables and overlays.

## Low win-rate period analysis

For windows such as `20260101~20260528`, never diagnose from aggregate WR alone. Required decomposition:

- By family: PRIMARY / CONTINUATION / REENTRY.
- By zone: OB / FVG / liquidity / sweep.
- By confirmation: BOS / CHOCH / MSS / rejection / hold.
- By entry: direct / retest / reentry / delayed.
- By exit: SL / TP / structure / time / gap.
- By T+1 violations.
- By market state and index regime.

Then inspect losing trades one by one and classify cause as signal accuracy, entry timing/price, exit rule, market regime, or data/frontend sync defect.

## Push/report readability

User requires SMC push/report output to be table-oriented and phone-readable:

- Use Markdown tables for holdings and picks.
- Use short Chinese column names.
- Show held/new marker clearly.
- Avoid long unstructured text lists.
- Truncate very long signal strings while preserving the important signal family/type.
