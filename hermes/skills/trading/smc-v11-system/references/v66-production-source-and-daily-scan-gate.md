# V66 production source, daily-scan quarantine, and page-date inspection

## Durable lesson

V66 dashboard output can look current while the production pick source is still historical. Before diagnosing "no latest picks" or allowing daily-scan candidates into production, verify the source chain and gate results separately from K-line freshness.

Current V66 shape observed in this class of issue:

```text
V64 historical trades
→ V65 loss-review gate (`smc_opt_v65/v65_trades.json`)
→ V66 recent REENTRY risk overlay (`v66_engine.py`, source=`v65_trades.json`)
→ V66 trades/picks
```

Therefore V66 page labels do not mean the latest K-line scanner is producing same-mechanism V66 candidates. If `v66_report.json.source == "v65_trades.json"`, V66 is an overlay on V65 trades, not a fresh all-market scanner.

## Mandatory inspection before explaining/latest-pick issues

1. Confirm active source:
   - Read/report `smc_opt_v66/v66_report.json`: `profile`, `source`, `n_source`, `n_trades`, `n_rejected`.
   - Inspect `v25/v66_engine.py` for `SRC` if needed.
2. Compare date layers explicitly:
   - `ops_latest.json.data_date` / K-line refresh latest date.
   - `pick_diagnostics.source_latest_date` (V65 source latest).
   - `pick_diagnostics.kept_latest_date` / `latest_pick_date` (V66 kept latest).
   - Page window date (`/backtest`, `/analysis`, `/autopsy`).
3. For a disputed window, count rows across the chain:
   - `v65_source_v64_trades.json`
   - `v65_trades.json`
   - `v65_rejected.json`
   - `v65_watch_only.json`
   - `v66_trades.json`
   - `v66_rejected.json`
4. Only after this decide whether "few picks" is normal gate behavior or data-source failure.

## Daily scan gate pitfall

`daily_scan.py` may find latest-date candidates (for example `OB → PINBAR`) that do not exist in V65/V66 backtest trades. These candidates must not become production `ACTIVE_ENTRY` or realtime positions unless they pass the same historical backtest/replay/autopsy/analysis gate.

Correct handling for non-V66-proven daily-scan rows:

```text
pick_scope = VALIDATION_ONLY
is_active_pick = false
validation_status = NEEDS_SEQUENCE_BACKTEST
reason = DAILY_SCAN_SEQUENCE_NOT_IN_V66_BACKTEST
```

A valid daily task can therefore show:

```text
data_date = latest market date
latest_pick_date = older V66 kept date
latest daily_scan candidates = validation-only
production ingest added = 0
```

This is not a task failure; it means no latest-date candidate passed the current production mechanism.

## Join-date display pitfall

On the pick page, `join_date` is not guaranteed to exist in `v66_picks.json`. It may be derived from realtime monitor state (`positions.json.created_at`) by `(symbol, pick_date/select_date/entry_date)`.

When checking empty join dates:

- Verify `/api/picks` `join_date`/`created_at` counts.
- Verify `positions.json` OPEN and CLOSED records for matching symbols/pick dates.
- Distinguish:
  - never ingested candidates: join date legitimately blank;
  - closed positions: may have `created_at` in `positions.json` but the pick-page matching/display may not surface it;
  - open positions: should usually display `created_at` as join date.

Do not call this a market-data problem without checking monitor state.

## Reporting standard for Lei

For this class of SMC issue, report in compact tables:

- source chain and active source;
- date-layer comparison;
- disputed window counts across V64/V65/V66;
- whether the result is gate-normal vs data-source fault;
- explicit statement if no code was changed.
