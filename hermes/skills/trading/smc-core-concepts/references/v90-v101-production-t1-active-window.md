# V90/V101 Production T+1 Active-Window Closure Pattern

Use this when an SMC production task involves daily full-market scanning, monitor ingestion, stale active picks, or A-share execution timing.

## Problem Pattern

A scanner can correctly generate historical/recent candidates, but production becomes unsafe when downstream monitor ingestion treats old candidates as executable `ACTIVE_CANDIDATE` rows. This creates two failure modes:

1. **Historical active pollution** — candidates from weeks ago still appear tradable because `pick_scope=ACTIVE_CANDIDATE` was preserved.
2. **Same-day execution violation** — an automatic daily pick can be converted to `OPEN` during the same session instead of waiting for the next trading day.

For A-share SMC production, both are hard release blockers.

## Required Production Rules

- Daily scanner output may keep old setups for analysis, but only rows inside the executable window may remain active.
- Use a small explicit active window, e.g. `MAX_ACTIVE_BARS = 3`; rows with `bars_since_entry > MAX_ACTIVE_BARS` must become `WATCH_ONLY` with a clear `watch_reason`.
- Automatic sources (`auto_daily`, `manual_daily`) must not fill same-day picks. They should enter `NEXT_DAY_PENDING`; only a later trading date may fill them using live price.
- Pending rows must not have `filled_at`; `filled_at` is only written when the buy actually occurs.
- The monitor ledger must use real `buy_date` from `filled_at`, not `pick_date` or planned entry date.

## Minimal Monitor Pattern

Add a helper with this semantics:

```python
def should_delay_entry_until_next_trading_day(pick_date, source='auto_daily', entry_dt=None):
    if source not in ('auto_daily', 'manual_daily'):
        return False
    return not t1_entry_allowed(pick_date, entry_dt or now_iso())
```

Use it in `to_position()` and `ingest_daily_picks()`:

- If delay is required, do not fetch/use live execution price yet.
- Keep planned `entry_price`, `sl`, and `tp1` as plan fields.
- Set `status='NEXT_DAY_PENDING'`, `pending_reason='WAIT_NEXT_TRADING_DAY_ENTRY'`, and `filled_at=''`.
- In `fill_pending_orders()`, require `t1_entry_allowed(pick_date, today)` before converting to `OPEN`, then fetch live price and recompute SL/TP from the actual fill.

## Daily Completeness Gate Semantics

Do not fail a daily completeness gate just because there are zero active picks for the latest market date. Zero active candidates is valid when no setup passes the production contract.

The gate should prove:

- K-line refresh/cache latest date coverage is sufficient.
- Daily scanner/ops ran against that latest market date.
- Candidate counts are separated into active tradable vs WATCH_ONLY.

A failed API refresh summary can report `ok=0`, but if the cache itself proves enough latest-date rows, use the cache latest-date count as the grounding source for coverage rather than treating the transient refresh summary as absolute truth.

## Verification Checklist

Run/maintain regression tests covering:

1. Stale historical pick never opens at contract price.
2. Non-stale prior-day pick fills at live price during market time.
3. Same-day auto pick remains `NEXT_DAY_PENDING` even during market time.
4. Non-trading-time auto pick remains pending and does not write `filled_at`.
5. Later trading day pending fill uses live price and sets `filled_at`/buy date.

Then verify production files:

- `same_day_open_violations == 0`
- `ledger_same_day_buy_violations == 0`
- `production_reviews_clean_only == true`
- `production_closed_positions_clean_only == true`
- daily completeness gate passes with latest cache coverage and scanner date, even if active candidate count is zero.
