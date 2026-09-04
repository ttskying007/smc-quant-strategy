# Daily Ops Observability for SMC Frontend

Use this when the user reports that SMC pages feel like a “盲盒” (black box): stale picks, no visible reason for no selections, unclear SL triggers, or missing review/analysis status.

## Required observability contract

A production SMC dashboard must show not only final picks, but the full operational chain:

1. **Daily selector status**
   - Current system date and run timestamp.
   - Selector command / return code.
   - Latest pick date in production picks.
   - Today pick count.
   - Whether today picks were auto-ingested into realtime monitor.
   - If no today picks: explicit reason (`NO_TODAY_PICKS`, selector error, stale source file, no trading day, etc.).

2. **Pick funnel / rejection reasons**
   - Active vs expired/review-only pick counts.
   - Signal family counts.
   - Reject reason counts, e.g. `REENTRY_BQ_LT_60`, `REENTRY_EXACT_HIGH_EXTENDED_RANGE`.
   - Per-pick match score / quality score / setup family.
   - Where possible, include where a stock was filtered out rather than only showing final survivors.

3. **Realtime monitor state**
   - Open/closed position counts.
   - Buy/sell ledger totals and today totals.
   - Trigger reason for sell events (`SL_HIT`, `TP_HIT`, `GAP_SL_HIT`, etc.).
   - Preserve a durable ledger independent of page refreshes.

4. **Review / autopsy state**
   - Recent closed reviews.
   - SL root-cause bucket: entry problem vs signal accuracy problem vs stop design / zone failure / market regime.
   - Diagnosis text and repair plan.
   - Design match status when available.

5. **Analysis state**
   - Trades, wins/losses, WR, avg PnL, total PnL.
   - Exit reason distribution.
   - File freshness for picks/trades/report/positions/reviews/ledger/cron logs.

## Implementation pattern used in this session

- Add one deterministic daily script, e.g. `v25/smc_daily_ops.py`, that runs the active production selector and writes:
  - `/root/.hermes/smc_monitor/ops_latest.json`
  - `/root/.hermes/smc_monitor/ops_logs/YYYYMMDD.json`
- Add `/logs` frontend page and `/api/logs` backend endpoint.
- Add a cron entry that calls the daily script on trading days.
- If today picks exist, auto-ingest them into realtime monitor from the same daily script.
- If today picks do not exist, record `NO_TODAY_PICKS` and show latest pick date prominently.

## Pitfalls

- Do not treat stale visible dates as a UI-only bug. First verify whether the production selector actually produced today’s picks.
- Do not confuse a risk-overlay/backtest filter with a daily full-market selector. If a “production” version only reads historical trade JSON and applies gates, rerunning it daily can succeed while the candidate sample remains stale. Diagnose source latest date vs kept latest date vs visible candidate latest date; see `references/v66-closed-loop-overlay-vs-daily-scan.md`.
- Do not stop at aggregate metrics. The user expects mechanism-level visibility: which gate rejected candidates, what match score survived, and why SL/review outcomes happened.
- Do not leave daily cron pointing at retired engine scripts after version promotion. Cron must follow the active production selector or a stable wrapper script.
- Do not silently auto-ingest stale picks. Only ingest picks whose pick/entry date equals the current daily log date.

## Verification checklist

- `python3 -m py_compile smc_unified.py v25/smc_daily_ops.py`
- Run daily ops script manually once and inspect `ops_latest.json`.
- Verify `/api/logs` returns `date`, `pick_diagnostics`, `daily_ingest`, `live_summary`, `review_summary`, `analysis_summary`.
- If candidates are stale, verify `/api/logs.pick_diagnostics` includes `source_latest_date`, `kept_latest_date`, `latest_pick_date`, and `rejected_after_active_latest[]` so the reason for the stale visible date is explicit.
- Verify `/logs` renders:
  - 今日选股
  - 最新选股日
  - 今日汇入
  - 筛除原因
  - 当前候选样本
  - 止损复盘归因
  - 文件更新时间
- Verify `/monitor`, `/live`, `/analysis`, `/autopsy` still load after adding the logs page.
