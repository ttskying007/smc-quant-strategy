# V536 multi-timeframe raw cache, source health, and retention

## Scope

Before any 2023–2026 research on 15m/60m/daily/weekly price structure, volume absorption, Spring/Test, SOS/Backup, or Selling Climax, produce a complete, reproducible raw-OHLCV layer.

## Data contract

- Use one historic raw writer for each replay series. Baostock `adjustflag=3` supplied SH/SZ raw OHLCV in this implementation.
- **Probe the exact target date range before choosing request chunks.** Do not retain a quarterly/yearly chunking rule merely because an earlier source probe suggested a cap. A full-range 15m probe returned all expected 2023–2026 bars (13,696 for `000001.SZ`); full-range requests are preferred when the slot audit validates them.
- Keep raw daily independently. Daily provider OHLCV can differ slightly from an aggregation of intraday bars, especially for volume/session accounting.
- A canonical 60m layer may be deterministically aggregated from four same-source raw 15m bars, with endpoints `10:30`, `11:30`, `14:00`, and `15:00`.
- Construct weekly only from independent raw daily bars.
- Validate each symbol against raw daily availability before atomic persistence:
  - 15m: exactly 16 A-share session bars/trading day.
  - 60m: exactly 4 session bars/trading day.
  - timestamps strictly ordered; OHLC positive and internally valid.
  - weekly exact aggregation from daily.
- Do not persist a partially valid symbol. A restart must identify completed symbols from the canonical cache and resume at the first missing symbol.
- Explicitly quarantine unsupported exchange/source cohorts; never claim universal coverage by silently dropping them.

## Multi-source health

Sina/Tencent can be independent live/overlap witnesses, but they must never fill missing historic rows in a Baostock raw replay series. A witness probe must record health, time overlap, and price delta. A nonzero delta is a source-contract mismatch, not permission to choose whichever source makes an outcome better.

Health check order:

1. Probe raw daily/15m primary source.
2. Probe witness sources.
3. Compare same-timestamp closes over overlap.
4. Allow build only when primary source passes; retain witness failures/deltas as audit facts.

## Scheduling, deadlines, and disk safety

- Use a lock-protected batch controller: health check → bounded cache batch → health check.
- Before promising a completion deadline, measure a full missing-symbol build and calculate capacity from the verified single-writer/concurrency contract. Do not claim a deadline that the measured source throughput cannot meet.
- If randomized scheduling is requested, randomize only **safe orchestration**: bounded symbol count per batch and a bounded inter-batch pause. Never randomize or shorten the required per-symbol 2023–2026 history range; that creates an incomplete replay series.
- Keep batch sizes below the scheduler hard runtime limit. If using a time-boxed accelerator, hold the same lock and leave the regular scheduler disabled until the accelerator exits.
- Do not introduce unverified multi-session source concurrency merely to meet a deadline. First test it; preserve fail-closed completeness gates.
- Keep current raw cache, current production state, sessions, snapshots, and frozen audit evidence.
- Reclaim disk only from clearly obsolete duplicate reports/logs, bounded system journals, and recreatable package caches. Validate free space and current raw-cache file counts after cleanup.
- Retention automation must use explicit age/path rules; it must not wildcard-delete `smc_audit`, `intraday_cache`, `kline_cache`, registry, pending, positions, sessions, or snapshots.
