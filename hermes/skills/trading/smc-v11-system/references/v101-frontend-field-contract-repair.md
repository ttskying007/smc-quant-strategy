# V101 Frontend Field Contract Repair

## Trigger
Use this reference when a promoted SMC contract layer (for example V101 over the V88/V100 frontend shell) shows blank or stale fields on `/monitor`, `/live`, `/api/picks`, `/api/live-prices`, or `/api/summary` after a selector/daily task rerun.

## Durable Lesson
Frontend field repair must cover the whole contract chain, not only the table template:

1. **Report stats adapter** — when the promoted report format changes, update the shared summary adapter (for example `_active_report_stats()`), not only the HTML labels. Include the new version in the production-stat branch (`V100`, `V101`, etc.) and map new report keys such as `production_total`, `production_stats`, `production_policy`, or `contract`.
2. **Daily ops summary** — ensure `smc_daily_ops.py` reads the actual report keys written by the promoted engine. Avoid stale placeholders like `counts`, `metrics`, or `by_combo_family` when the report now emits `production_total`, `active_pick_total`, `production_stats`, `combo_counts_production`, etc.
3. **Active-pick ingestion chain** — if the promoted version has its own active picks file, include it in the daily ingest source list before older versions so reruns do not silently fall back to stale V100/V90/V97 data.
4. **Alias contract** — verify both snake_case and camelCase aliases for frontend fields: `pick_date/pickDate`, `join_date/joinDate`, `cost_line/costLine`, `volatility_pct/volatilityPct`, `zone/zoneType`, plus engine/version fields.
5. **Restart and verify** — after patching, restart port `8890`, then verify API and browser-rendered pages. Do not stop at `py_compile`.

## Verification Checklist
Run the equivalent of these checks after repair:

- `python3 -m py_compile /root/.hermes/scripts/smc_unified.py /root/.hermes/scripts/v25/smc_daily_ops.py <promoted_engine>.py`
- `/api/summary` returns the promoted `version`, `engine`, `total_trades`, net `win_rate`, and `avg_pnl`.
- `/api/picks` has 0 missing for `pick_date`, `join_date`, `engine`, `zone`, `cost_line`, `volatility_pct`.
- `/api/live-prices` has 0 missing for `pickDate`, `joinDate`, `engine`, `zone`, `costLine`, `volatilityPct`.
- Browser `/monitor` shows the added date columns and non-empty engine/Zone/cost/volatility fields.
- Browser `/live` shows non-empty selected date, joined date, cost line, Zone, and volatility fields.
- Rerun `smc_daily_ops.py` and confirm exit code `0`; inspect `ops_latest.json` for promoted summary and `field_missing_active` all zero.

## Pitfalls
- A static HTML scan may count the JavaScript literal `undefined`; browser text and API field audits are the real signal for blank user-visible fields.
- A task ID reported by the user may be an old session ID, not a cron job ID. If rerun tooling cannot find it, execute the underlying daily ops script directly and verify the generated files.
- Long `smc_daily_ops.py` runs can spend several minutes in V98/V99/V100 child selectors. Check the child process and output files before killing; no stdout does not mean failure.
