# V175 live-guard + `/api/picks` parity lesson (2026-06-23)

## Trigger
V175 semantic split artifacts were promoted correctly, but the raw active-pick artifact still contained 26 recent scanner candidates. `/api/live-prices` applied current-price guard and correctly showed only 3 BUY / 23 WATCH_ONLY, while `/api/picks` initially exposed all candidates without the same current-price guard fields/status.

## Durable lesson
For SMC production/live frontend sync, **`/api/picks` and `/api/live-prices` must agree on buyability**. Do not let the selection page show stale/recent scanner rows as buyable when live/last cached price says the candidate already hit TP, hit SL, or drifted too far from entry.

## Required pattern
1. Apply semantic field contract first (`_apply_smc_field_contract`).
2. Apply current-price live guard to active picks as well as live-prices:
   - use current live price when market open;
   - otherwise use last cached daily K-line close;
   - reject BUY when `current <= SL`, `current >= TP`, or `abs((current-entry)/entry) > threshold`.
3. Emit explicit fields on `/api/picks` rows:
   - `current_price`, `last_price`, `last_price_date`
   - `current_entry_gap_pct`
   - `live_guard_status`, `live_guard_reason`
   - `tradable`, `buy_enabled`, `trade_action` / `tradeAction`
   - `status` / `monitor_status`
4. Verify both endpoints after restart and again after `POST /api/reselect`.

## Acceptance checks
```text
/api/picks BUY/WATCH_ONLY == /api/live-prices BUY/WATCH_ONLY
BUY rows satisfy: not TP hit, not SL hit, abs(current-entry) <= live_guard_threshold_pct
WATCH_ONLY reasons are counted and human-readable
/api/resonance has zero empty ctxSeq
POST /api/reselect {"version":"V175"} does not revert `/api/picks` to stale BUY rows
```

## V175 observed result
After the fix:

| Surface | Result |
|---|---:|
| `/api/picks` | 26 rows = 3 BUY / 23 WATCH_ONLY |
| `/api/live-prices` | 26 rows = 3 BUY / 23 WATCH_ONLY |
| WATCH_ONLY_TP_ALREADY_HIT | 13 |
| WATCH_ONLY_PRICE_NOT_NEAR_ENTRY | 9 |
| WATCH_ONLY_SL_ALREADY_HIT | 1 |
| `/api/reselect V175` | ok=true, parity preserved |

## Related report-output lesson
When generating a semantic/label-only promotion report, put preserved economics at both:
- nested provenance field (`source_metrics_preserved_from_v172`), and
- top-level report fields (`n`, `win_rate`, `avg_pnl`, `sl_rate`, `min_year`, `t1_violations`, `year_counts`, `year_wr`).

This prevents downstream summaries from printing `None` even when nested metrics exist.
