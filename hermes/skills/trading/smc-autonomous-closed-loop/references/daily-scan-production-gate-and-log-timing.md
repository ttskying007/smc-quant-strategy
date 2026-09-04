# Daily Scan Production Gate + Log Timing

## Durable lesson

Daily latest-date scanners are discovery tools, not production selectors. A daily scan row such as `OB → PINBAR` may be useful for audit/backtest, but it must not be written as `ACTIVE_CANDIDATE` or auto-ingested into realtime monitoring until it has passed the same production gate as the active SMC version.

## Required contract

When merging latest daily scan output into active picks:

- Set unvalidated daily scan candidates to `pick_scope = VALIDATION_ONLY`.
- Set `is_active_pick = false`.
- Add `validation_status = NEEDS_SEQUENCE_BACKTEST`.
- Add a clear `validation_reason` explaining that the sequence is not yet production-gated.
- Do not count these rows as `daily_ingest.added`.
- Do not write them into realtime `positions.json` or `trade_ledger.json`.
- Keep them visible in logs/daily candidate files for audit and future full-market backtest.

## Correct flow

```text
refresh K-line
→ daily_scan.py discovers candidates
→ merge as VALIDATION_ONLY
→ show in logs with reason
→ run full-market sequence backtest / mechanism audit
→ only then promote to ACTIVE_CANDIDATE if accepted
```

## Log observability requirement

Ops logs should expose timing for every step:

- task name
- `started_at`
- `finished_at`
- `duration_sec`
- return code or OK/FAIL
- result/reason/error

Minimum task rows: K线刷新, V66选择器, 最新日扫, 日扫合并, 监控汇入.
