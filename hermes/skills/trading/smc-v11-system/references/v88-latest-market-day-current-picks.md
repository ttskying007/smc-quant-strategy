# V88 current-picks latest-market-day contract

## Trigger
Use this when `/monitor` or `/live` shows V88 current picks whose latest pick/join date is older than the latest market data date.

## Symptom from session
- Current natural date: 2026-06-14 (Sunday)
- Latest market data date: `20260612`
- Scanner reports had `latest_market_date=20260612`
- UI showed current picks from `pick_date=20260528`, `join_date=20260529`
- After removing V88 historical reps, stale V90/V91 recent-window candidates were still being shown as current picks.

## Root cause
The first fix filtered to the latest scanner `pick_date`, but V90/V91 scanner files are recent-window outputs (`RECENT_BARS=45`), not a daily-only watchlist. Their max `pick_date` can be weeks behind the current/latest market date. Filtering by max pick date still allows stale rows to appear as current.

## Correct contract
For V88 `/monitor`, `/api/picks`, and fallback `/live` current-pick surfaces:

1. Never use `v88_picks.json` as current picks; it is a 3-year production/backtest artifact.
2. Read scanner reports (`v91_shadow_scan_report.json`, `v90_daily_scan_report.json`) for `latest_market_date`.
3. Only show scanner rows where latest market date appears in either:
   - `pick_date` / `select_date`, or
   - `join_date` / `entry_date`
4. If no rows match latest market date, show `0` current picks. Do **not** fall back to 45-day recent candidates.
5. Header/status must show scanner report recency (`run_at`, `latest_market_date`), not stale ops metadata.
6. Monitor category counts must be derived from current monitor positions only; do not show old global category counters when active picks are 0.

## Verification pattern
Run after changes:

```bash
python3 -m py_compile /root/.hermes/scripts/smc_unified.py
python3 /root/.hermes/scripts/v25/test_v88_current_picks_contract.py
```

Then verify APIs/pages:

```bash
curl -s http://127.0.0.1:8890/api/picks | jq length
curl -s http://127.0.0.1:8890/api/live-prices | jq '{error,total,picks:(.picks|length), dataDate, scanMeta}'
```

Expected for no latest-day candidates:
- `/api/picks`: `[]`
- `/monitor`: `V88 当前有效选股 — 0只`, `最新有效选股:-`, `RawFile:0只`
- `/live`: `无实时监控持仓`, `dataDate` and `scanMeta.latest_scan_date` equal latest market date
- No stale category tags such as old `FVG:68 / OB:52` when current picks are 0.
