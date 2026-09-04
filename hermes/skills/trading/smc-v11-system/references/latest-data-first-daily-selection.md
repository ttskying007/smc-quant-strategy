# Latest-data-first daily selection workflow

When SMC daily picks look stale (for example the candidate page shows an old latest date), do not only rerun the current production overlay engine. First verify whether the production engine is scanning fresh market data or merely re-filtering an older trade snapshot.

## Durable lesson

A daily production loop must run in this order:

1. Refresh full-market daily K-line cache to the newest available date.
2. Scan the refreshed cache for latest complete-day SMC candidates.
3. Merge the latest scan output into the active production candidate file with explicit provenance fields.
4. Ingest latest-date candidates into realtime monitoring.
5. Refresh API/UI caches and write an ops log containing data freshness, scan, merge, and ingest results.

If step 1 is missing, candidates can remain stuck at the last date present in an old source snapshot even though the server/cron is running correctly.

## Proven implementation pattern from the V66 repair

Files used in the repair:

- `v25/refresh_daily_750.py` — refreshes Tencent fqkline 750-bar daily cache for the full A-share universe.
- `v25/daily_scan.py` — scans refreshed cache and writes latest scan picks.
- `v25/smc_daily_ops.py` — orchestrates refresh → V66 selector → daily scan → merge latest scan into V66 → ingest latest-date candidates.
- `smc_unified.py` — frontend/API cache must invalidate on both active trades mtime and active picks mtime.

The corrected daily order is:

```text
refresh_daily_750.py
  → v66_engine.py historical/overlay selector
  → daily_scan.py latest complete-day scan
  → merge latest daily-scan picks into smc_opt_v66/v66_picks.json
  → ingest_daily_picks(latest_scan_date)
  → write ops_latest.json / ops_logs/YYYYMMDD.json
```

## Required diagnostics in ops logs

Record at least:

- `kline_refresh.summary.latest_counts` — distribution of latest K-line dates after refresh.
- `daily_scan.returncode` and scan stdout tail.
- `daily_scan_merge.ok`, `added`, `latest_scan_date`, and symbols added.
- `pick_diagnostics.latest_pick_date` — latest active candidate date after merge.
- `pick_diagnostics.source_latest_date` — latest historical source date before fresh scan, when applicable.
- `pick_diagnostics.kept_latest_date` — latest date kept by the overlay engine before fresh scan, when applicable.
- `daily_ingest.ingest_date`, `today_pick_count`, `added`.

This prevents a false conclusion like "UI stale" when the real issue is "production selector is re-filtering an old source snapshot".

## Complete-day rule

Tencent daily K-line may expose the current trading date intraday. For daily SMC signal generation, prefer the latest complete executable daily bar. During market hours this may be the prior trading day even if cache contains today’s partial daily bar. Log both data freshness and selected scan date so the reason is visible.

## API/UI cache pitfall

If active candidates are appended to `v66_picks.json` but the frontend cache only watches `v66_trades.json` mtime, `/api/picks`, `/monitor`, and `/live` can continue serving old candidates. Cache validity must include both active trade file and active pick file mtimes.

## Verification checklist

After the repair, verify:

- K-line refresh reports most stocks at the newest date.
- `/api/logs` shows `kline_refresh`, `daily_scan`, `daily_scan_merge`, and `daily_ingest` populated.
- `/api/picks` max candidate date equals the latest complete scan date.
- `/monitor` displays the latest-date candidates.
- `/api/live-prices` includes the newly ingested candidates with non-empty cost line and volatility fields.
- Cron calls the closed-loop/daily ops script, not an old version-specific script that only replays snapshots.
