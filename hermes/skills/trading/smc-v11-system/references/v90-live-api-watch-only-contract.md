# V90 / live API WATCH_ONLY Contract Closure

Use this reference when SMC frontend/live APIs show different counts between `/api/picks` and `/api/live-prices`, or when WATCH_ONLY rows appear on the live page.

## Durable lesson

`/api/picks` and `/api/live-prices` do not have to return the same row count:

- `/api/picks` is the production candidate file contract and should expose the current scoped pick set from the production scanner.
- `/api/live-prices` may apply a recency/window filter for display, but must not silently convert WATCH_ONLY rows into live holdings.

A count mismatch is acceptable only if the response makes the semantics explicit with fields such as `tradableLiveCount`, `watchContextCount`, `pickScope`, `isActivePick`, `isTradableLive`, and `tradable`.

## Required closure checks

When closing production candidate/live API issues, verify all of these with real API calls and gates:

| Check | Required result |
|---|---|
| `/api/picks` source | Latest production scanner rows only; no historical completed trade files |
| `/api/picks` scopes | Count `ACTIVE_CANDIDATE` separately from `WATCH_ONLY` |
| `/api/live-prices` tradable count | Explicit `tradableLiveCount`; do not infer from row count |
| WATCH_ONLY live rows | `isTradableLive=false`, `tradable=false`, `pnlPct=0`, `pnl_pct=0`, `hold_bars=0` |
| WATCH_ONLY status | Use context status such as `WATCH_ONLY_CONTEXT`, not `HOLDING`, `NO_LIVE_LAST_PRICE`, `SL_HIT`, or `TP_HIT` |
| Completed-trade pollution | No `exit_date`, realized `net_pnl_pct`, or historical `exit_reason` on current candidates |
| Data date | `dataDate` must come from actual data/scan freshness, not stale pick/signal date |
| T+1 | Same-day daily picks must enter `NEXT_DAY_PENDING`; no same-day BUY/SELL completion |

## Pitfall: stale pick date is not data freshness

Do not use `latest_pick_date` or candidate event date as market data freshness. A scanner can legitimately have old WATCH_ONLY candidates while the K-line cache and latest scan date are fresh. Prefer:

1. K-line refresh/latest cache date.
2. Daily ops `data_date`.
3. Latest full-market scanner report date, e.g. `latest_market_date`.

## Pitfall: live display rows are not positions

If no durable monitor `OPEN` / `NEXT_DAY_PENDING` rows exist, fallback scanner rows shown on `/api/live-prices` are context only. Do not compute current PnL, SL/TP hit status, or exit reason for non-tradable WATCH_ONLY rows. Use explicit context status and zero PnL instead.

## Reporting pattern for Lei

Report in compact tables:

- API count/source table: `/api/picks`, `/api/live-prices`, `/api/picks/contract`, `/api/summary`.
- Gate table: daily completeness, release gate, T+1 regression, py_compile.
- Current production state: tradable active count, WATCH_ONLY count, data date, scan date.
- Unproven items: signal semantic correctness, historical audit artifacts, refresh writer/network issue if not fixed.

Avoid saying “fixed” based only on code changes. Use API responses and gate files as proof.
