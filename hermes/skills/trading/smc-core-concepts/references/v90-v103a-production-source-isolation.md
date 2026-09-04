# V90/V103A Production Source Isolation and Closure Audit

Use when the SMC frontend/API shows inconsistent counts, only a few active picks, or live prices for rows that look like completed historical trades.

## Durable lesson

A production pick chain can pass backtest/release metrics while the frontend is still unsafe if `summary`, `/api/picks`, `/api/live-prices`, monitor state, and daily scanner read different sources.

Do not treat `ACTIVE_CANDIDATE` labels as proof of current tradability. First prove the row is ex-ante current:

- no `exit_date`, `exit_reason`, `net_pnl_pct`, realized `hold_bars`, MFE/MAE-derived gate fields in active/live rows;
- source engine/file is latest full-market daily scanner, not historical trade or risk-gate audit output;
- `data_date` equals latest market date from K-line cache / scan report;
- `pick_scope=ACTIVE_CANDIDATE` only when still inside the entry window; expired rows become `WATCH_ONLY` with explicit `watch_reason`;
- `/api/live-prices` echoes `pickScope`, `isActivePick`, and `dataDate` so the live page cannot silently recalculate historical completed trades as current PnL.

## Audit checklist

1. **Source inventory**
   - Read promoted trade/report/pick paths in the frontend router.
   - Check if `_promoted_contract_dir`, `_promoted_trade_file`, pick merge helpers, and summary metrics prioritize the same version.
   - If V103A-like audit files contain historical completed rows, keep them as audit artifacts and do not route them into active/live pages.

2. **Full-market daily completeness**
   - Validate requested universe, ok count, failed ratio, latest cache date count, latest cache ratio, and ops data date.
   - If refresh summary says `failed=requested` but cache latest date count is high, derive failed count from `requested - latest_count/ok` rather than failing a stale refresh field.
   - A daily scan with zero current tradable candidates is valid; the gate should prove fresh coverage and scan execution, not force trades.

3. **Active/window semantics**
   - Keep scanner output available for context, but only `bars_since_entry <= 3` can be tradable active in A-share daily production.
   - Rows older than the entry window must be `WATCH_ONLY`, `is_active_pick=false`, and carry a reason like `BARS_SINCE_ENTRY_X_GT_3`.
   - Contract summaries should report `tradable_active_pick_count` separately from display rows that include WATCH_ONLY.

4. **T+1 execution semantics**
   - Automatic/manual daily picks selected on the same date must become `NEXT_DAY_PENDING`, not `OPEN`, even during market hours.
   - Next trading day fill uses live price and records `filled_at`/buy date later than `pick_date`.
   - Keep regression tests covering stale historical pick rejection, next-day live fill, same-day pending during market open/closed, and next-day pending fill.

5. **API smoke tests**
   - `/api/picks`: count, scopes, engines, no exit/net fields, data_date latest.
   - `/api/live-prices`: pickScope/isActivePick/dataDate present, no exitDate, source matches picks.
   - `/api/picks/contract`: tradable active count excludes WATCH_ONLY.
   - `/api/summary`: if metrics remain historical/backtest, report that explicitly; do not infer current tradability from summary metrics.

## Pitfalls

- `ACTIVE_CANDIDATE` in an audit file can be a historical completed trade. Always inspect fields, not labels.
- `summary=V102` while `picks/live=V103A` is a source-mismatch failure even if both are high-performing versions.
- `entry_idx < reclaim_idx` invalidates a claim of reclaim-confirmed entry even when aggregate WR looks strong.
- Shadow scanners (e.g. V91) should not be merged into production/live rows unless explicitly promoted; otherwise current picks become a mixed-source set.
- GitNexus `detect-changes` may fail outside a git repo; still run required impact analysis before edits, then use py_compile, gates, and API smoke tests as verification.
