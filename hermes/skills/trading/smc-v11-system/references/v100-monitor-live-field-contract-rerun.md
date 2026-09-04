# V100 monitor/live field-contract rerun verification

Use this when a prior SMC frontend/scheduler task keeps failing and the user asks to rerun/recover, especially for `/monitor` and `/live` field blanks.

## Durable recovery pattern

1. **Rerun the scheduler/job first, then verify outputs**
   - Run the daily ops chain from `/root/.hermes/scripts`.
   - Treat successful exit as necessary but not sufficient; continue to API/page verification.

2. **Do not assume the frontend is down just because a restart fails**
   - If starting `smc_unified.py` returns `OSError: [Errno 98] Address already in use`, inspect the existing listener on port `8890` and validate against that running process.
   - Only kill/restart when the listener is stale or serving old data. Avoid blind restart loops.

3. **Reload frontend cache before checking fields**
   - Call `/api/reload` after regeneration/restart so V100/V88 route caches pick up fresh `trades/picks/report` files.

4. **Verify both API contracts and rendered pages**
   - `/api/picks` and `/api/live-prices` must both have zero missing values for the cross-surface fields below.
   - `/monitor` and `/live` must return HTTP 200 and not render `None`/`NaN` blanks in user-facing field cells.

## Required field contract for monitor/live fixes

For each active row verify at least:

```text
symbol
engine
pick_date / pickDate / 选股日期
join_date / joinDate / 加入日期
zone / zone_type
cost_line / costLine / smart_money_cost
volatility_pct / volatilityPct / volatility
sl / tp1 / tp2 / tp3
```

For live rows, check both snake_case and camelCase aliases because the page JS may read camelCase while the API/data file uses snake_case.

## Known frontend/API trap

- `/monitor` may be correct while `/live` is still blank if `_api_live_prices()` does not propagate `costLine`, `volatilityPct`, `zone`, or date aliases into its result rows.
- Conversely, `/api/live-prices` can contain values while the HTML appears blank if the JS table reads a different alias. Verify both JSON and rendered page.

## Acceptance shape for Lei

Report as a compact table only after verification, including:

- task rerun status / exit code
- 8890 service status
- `/api/picks` missing field count
- `/api/live-prices` missing field count
- `/monitor` and `/live` page status
- one representative active pick row with `代码 / 引擎 / 选股日期 / 加入日期 / Zone / 成本线 / 波动`

Do not stop at “任务已执行”; the completion standard is field-level verification across scheduler output, API, and both pages.