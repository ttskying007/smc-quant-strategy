# V66 closed-loop automation: overlay vs daily full-market scan

Use this when Lei asks why the SMC candidate page is stale even though the daily job ran, or when promoting a backtest/overlay version to production.

## Session lesson

A daily cron that reruns `v66_engine.py` is not necessarily a fresh daily selector. In the observed V66 setup:

```text
smc_opt_v65/v65_trades.json or v65_source_v64_trades.json
  -> V66 risk overlay gates
  -> smc_opt_v66/v66_trades.json
  -> smc_opt_v66/v66_picks.json
```

V66 was a **risk overlay on an existing trade snapshot**, not a full-market scanner from latest K-line data. Therefore the frontend candidate sample can remain stale even when cron, logs, and API endpoints all run successfully.

Concrete diagnostic pattern from 2026-06-02:

| Field | Value | Meaning |
|---|---:|---|
| `latest_pick_date` | `20260519` | latest active V66 candidate kept by production picks |
| `source_latest_date` | `20260521` | latest record in V65 source pool |
| `kept_latest_date` | `20260519` | latest V66 trade after gates |
| `today_count` | `0` | no 20260602 production candidate |
| newer rejected record | `002235.SZ / 20260521` | rejected by V66, not a UI bug |
| reject reason | `REENTRY_EXACT_HIGH_EXTENDED_RANGE` | `near_high_pct=0.0`, `range_atr=4.421` hit the exact-high extended-range gate |

## Required distinction in future reports

When a user asks “为什么候选最新日期还是 X”, do not stop at “selector produced no today picks”. Split the diagnosis into three dates:

1. **Source latest date** — latest date in the upstream scan/trade pool.
2. **Kept latest date** — latest date after the active production gates.
3. **Visible candidate latest date** — latest date in the active frontend pick sample.

Also list any records newer than the visible candidate date that were rejected, with gate reason and key numeric fields.

## Production promotion gate

Before claiming a version is a daily production selector, verify its source model:

- If it reads a historical trades JSON and applies gates, label it as an **overlay/backtest filter**.
- If it reads latest K-line cache/API, scans the full market, emits today candidates, and then applies gates, label it as a **daily full-market scanner**.
- A complete daily closed loop requires:

```text
latest full-market K-lines
  -> signal detection / setup generation
  -> production gates
  -> today picks
  -> auto-ingest to monitor
  -> live SL/TP polling
  -> ledger
  -> closed_reviews
  -> logs/analysis/autopsy UI
```

## Frontend/logging requirement

`/api/logs` and `/logs` should expose:

- `latest_pick_date`
- `source_latest_date`
- `kept_latest_date`
- `today_count`
- `rejected_after_active_latest[]` with symbol/date/family/zone/score/reject_reason/trend_ctx

This prevents stale candidate pages from becoming a “盲盒”.
