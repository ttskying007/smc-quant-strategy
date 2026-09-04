# Consolidated SMC operations guards

This reference absorbs the former `smc-branch-validation`, `smc-frontend-sync`, and `smc-production-ops` skills under the class-level `smc-v11-system` umbrella.

## Branch validation / promotion gates

Use when comparing repair branches against a frozen baseline. Keep the baseline immutable, split one diagnosis per branch, run full-market validation, require schema checks, then compare against strict promotion gates. Inspect `n_trades`, WR, SL/hard-SL rate, avg/total PnL, PF, raw/display split, raw-zone presence, entry modes, exit reasons, market states, and signal buckets.

A profitable branch is not automatically promotable. Do not widen global gates, do not mix continuation and retest paths, and do not allow entries above the raw zone high on the promotable path. Promote only when full-market run, schema checks, execution boundary, strict acceptance gate, and intended-failure improvement all pass.

## Frontend/API/watchlist field sync

Use for selection-page missing columns, watchlist fields blank, `zone` blank, realtime cost/volatility blanks, and mismatches between current active candidates, historical trades, K-line charts, and push reports.

Principles:
- Locate the field source before changing table headers.
- Current candidates must come from watchlist/active-candidate sources, not historical trades.
- Synchronize backend row construction, API fields, JS renderers, pages, K-line overlays, and push/report fields together.
- Verify with both API JSON and browser pages.

Key fallbacks:
- pick date: `pick_date -> conf_date -> retrace_date -> signal_date -> entry_date`
- join date: `join_date -> added_date -> watch_date -> pick_date -> conf_date -> signal_date`
- zone: `zone -> zone_type -> signal_type -> entry_type -> setup_type -> signal_name`, or `zone.type -> zone.kind -> zone.name`
- cost: `smart_money_cost -> cost -> entry_price -> signal_price -> price`
- volatility: explicit volatility fields or `(high-low)/prev_close*100`; if unavailable, return `volatility_missing_reason` rather than silently blanking.

NEXT_DAY_PENDING must be a first-class state in selection statistics and `/api/live-prices`, but pending rows must not trigger SL/TP/PnL sell logic.

## Production daily ops guardrails

A latest-date daily scan is validation evidence, not production by default. Unverified sequences must be quarantined as `VALIDATION_ONLY` with explicit reasons and must not enter realtime monitoring until full-market gate evidence exists.

Expected reasons:
- `DAILY_SCAN_QUARANTINED_UNTIL_SEQUENCE_BACKTEST`
- `DAILY_SCAN_VALIDATION_ONLY_NOT_AUTO_INGESTED`

Before active production/realtime admission, require full-market multi-year backtest, production-strategy consistency, auditable entry/exit fields, A-share T+1 enforcement, synchronized picks/realtime/K-line/logs/analysis/autopsy, and HTTP/browser verification.

If unverified rows entered realtime, back up positions/ledger, remove validation-only rows from active monitoring, and preserve audit evidence.

Task timestamps must be visible consistently on `/logs`, `/analysis`, and `/autopsy` with start, finish, duration, return code, selector, latest scan, merge, and ingest fields.
