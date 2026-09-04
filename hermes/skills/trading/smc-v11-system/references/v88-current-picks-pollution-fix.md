# V88 current-picks pollution fix (2026-06-14)

## Symptom
`/monitor` showed `V88 当前有效选股 — 884只`, while V88 yearly backtest had only ~70 2026 trades. The page mixed:

- `v88_picks.json`: 3-year production-contract/backtest representatives (532 rows; historical trades, mislabeled `ACTIVE_CANDIDATE`)
- `v91_active_picks.json`: recent-window scanner candidates (333 rows, many 30-44 bars old)
- `v90_active_picks.json`: recent-window scanner candidates (33 rows, many 30-42 bars old)

This made historical/stale scanner rows look like current daily picks.

## Root cause
V88 active pick cache loaded `ACTIVE_PICK_FILE` (`v88_picks.json`) first, then merged V90/V91 scanner rows. The merge functions appended scanner rows to historical V88 rows and did not reduce scanner rows to the latest daily batch. `_normalize_pick_scope()` preserved `ACTIVE_CANDIDATE`, so all 884 rows reached `/api/picks`.

## Fix pattern
For V88 monitor/live surfaces, use only the latest daily scanner batch:

1. Exclude `v88_picks.json` from current pick surfaces. It is a 3-year production/backtest artifact, not a live watchlist.
2. Merge V90/V91 scanner files, then keep only rows whose `pick_date` equals the max scanner `pick_date`.
3. Dedupe by `(symbol, pick_date/entry_date, engine, entry_idx)`.
4. Keep `/backtest` and K-line historical trade overlays on `v88_trades.json`; do not change backtest data.

Current verification after fix:

- `/api/picks`: 6 rows, all `V91_SHADOW_ZONE_ENTRY_SCANNER`, `pick_date=20260528`, `entry_date/join_date=20260529`
- `/monitor`: heading `V88 当前有效选股 — 6只`, `RawFile:6只`
- `/api/live-prices`: 6 rows, zero blanks for `cost_line`, `volatility_pct`, `zone_type`, `pick_date`, `join_date`

Regression test: `/root/.hermes/scripts/v25/test_v88_current_picks_contract.py`.
