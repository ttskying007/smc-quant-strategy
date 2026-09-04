# Daily Scan Production Gate + Log Timing

## Durable lesson

Daily latest-date scanners are discovery tools, not production selectors. A daily scan row such as `OB → PINBAR` may be useful for audit/backtest, but it must not be written as `ACTIVE_CANDIDATE` or auto-ingested into realtime monitoring until it has passed the same production gate as the active SMC version.

## Required contract

When merging latest daily scan output into V66/Vxx picks:

- Set unvalidated daily scan candidates to `pick_scope = VALIDATION_ONLY`.
- Set `is_active_pick = false`.
- Add `validation_status = NEEDS_SEQUENCE_BACKTEST`.
- Add a clear `validation_reason` explaining that the sequence is not yet production-gated.
- Do not count these rows as `daily_ingest.added`.
- Do not write them into realtime `positions.json` or `trade_ledger.json`.
- Keep them visible in logs/daily candidate files for audit and future full-market backtest.

## Pitfall observed

A daily K-line refresh workflow was wired as:

```text
refresh K-line → daily_scan.py → merge into V66 picks → auto ingest into realtime monitor
```

This caused `OB → PINBAR` rows from `daily_scan_after_kline_refresh` to bypass V66 historical/backtest validation and enter realtime monitoring. That violates Lei's SMC production rule: current candidates must be lifecycle-driven and production-gated, not simply latest scanner hits.

## Correct behavior

The safe path is:

```text
refresh K-line
→ daily_scan.py discovers candidates
→ merge as VALIDATION_ONLY
→ show in logs with reason
→ run full-market sequence backtest / mechanism audit
→ only then promote to ACTIVE_CANDIDATE if accepted
```

## Log observability requirement

The ops log should expose timing for every step so failures and stale state are visible from the frontend:

- task name
- `started_at`
- `finished_at`
- `duration_sec`
- return code or OK/FAIL
- result/reason/error

Minimum task rows:

```text
K线刷新
V66选择器
最新日扫
日扫合并
监控汇入
```

This makes it clear whether a task actually ran, how long it ran, and which step blocked selection or realtime ingestion.
