# V217-V218 V185 current live guard + 60m cache freshness audit

Date: 2026-06-27

## Trigger
Use when continuing after V185/V211 and checking whether current active picks are actionable, whether 60min data can support micro-resolution, or whether frontend/API active state is polluted.

## Artifacts
- V217 intraday active guard draft: `/root/.hermes/smc_audit/v217_v185_current_intraday_active_guard_20260627_021844/`
- V218 corrected API/live guard + 60m freshness audit: `/root/.hermes/smc_audit/v218_v185_active_api_live_guard_and_60m_freshness_20260627_021953/`

## Important API parsing pitfall
`/api/live-prices?version=V185` returns rows under `picks`, not `data`. A parser that only reads `data` will falsely report missing live fields. Correct extraction:

```python
items = payload.get('picks') or payload.get('data') or []
```

## V218 result
Decision: `V218_V185_ACTIVE_API_LIVE_GUARD_PASS__60M_CACHE_STALE_FOR_5_OF_6__NO_WRITE`.

Current V185 active rows: `6`.
API rows: `6`.
API meta:
- `total=6`
- `tradableLiveCount=0`
- `watchContextCount=6`
- `latestScanDate=20260626`
- `dataDate=20260627`
- `market_open=false`

Live guard state:
- `WATCH_ONLY_PRICE_NOT_NEAR_ENTRY`: 5
- `WATCH_ONLY_SL_ALREADY_HIT`: 1
- `trade_action=WATCH_ONLY`: 6/6

Price/zone state using API current prices:
- `ABOVE_ENTRY_CHASED`: 4
- `BELOW_ZONE_LOW`: 1 (`002401.SZ`, current 11.71 below zone_low 12.16)
- `INSIDE_ZONE`: 1 (`688277.SH`, current 16.30 inside 16.30~17.295)

60min local cache:
- fresh vs active entry date: 1/6 rows
- stale: 5/6 rows (many `*_60min_500.json` files stop at `202605131500` while active entries are June 2026)

## V219 active-symbol 60m refresh follow-up
Artifact: `/root/.hermes/smc_audit/v219_refresh_v185_active_60m_cache_and_guard_20260627_022226/`.

V219 refreshed Tencent 60m cache only for the 6 current V185 active symbols. This changed only local kline cache files and wrote audit artifacts; it did not mutate production/frontend/watchlist artifacts.

Refresh result:
- 6/6 refresh OK.
- All refreshed 60m files now end at `202606261500`.
- Previously stale files (`300327`, `688048`, `688486`, `688277`, `002937`) moved from `202605131500` to `202606261500`.

60m replay under derived V185 active contract (`SL=zone_low*0.99`, `TP=entry+1.5R`, strict T+1, first hit wins):
- `TP_HIT_60M_10D`: 5
- `SL_HIT_60M_10D`: 1 (`002401.SZ`, hit at `202606261030`)
- Current zone state: `ABOVE_ENTRY_CHASED=4`, `BELOW_ZONE_LOW=1`, `INSIDE_ZONE=1`.

Important interpretation:
- V219 proves active-symbol 60m refresh is feasible via Tencent and the 6 current rows are mostly already post-entry/chased, not fresh actionable entries.
- It is **not** a full historical 60m validation because only active symbols were refreshed.
- Do not promote any 60m-based production rule until full candidate universe has fresh 60m coverage and the same T+1/no-leak gates pass.

## Decision
- V185 historical/production metrics remain valid; current issue is actionability/live entry, not historical invalidation.
- API live guard is correctly preventing active picks from being treated as tradable (`WATCH_ONLY` all rows).
- Do **not** use local 60min cache for production micro-resolution unless freshness is verified per symbol/date. V217/V218 found stale 60m cache for most rows; V219 fixed only the 6 current V185 active symbols.
- Before any 60m-based entry refinement, first build/refresh a complete current 60m cache and gate on `m60_latest_date >= entry_date` for every candidate.
- No production/frontend/watchlist writes were made in V217/V218/V219.
