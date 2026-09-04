# V100 Task Rerun + Monitor/Live Field Verification

## Trigger

Use this when the user says a previous SMC task keeps failing and asks to rerun it, especially with a value that looks like a task ID/session ID, and the requested work involves `/monitor` or `/live` blank fields such as:

- 选股日期 / 加入日期
- 引擎 / engine
- Zone / zone_type / zone_low / zone_high
- 成本线 / cost_line / costLine
- 波动 / volatility_pct / volatilityPct / volClass

## Durable workflow

1. **Do not assume the provided ID is a cron job ID.**
   - Hermes conversation/session IDs can look like task IDs.
   - If `cronjob(action='run')` reports `Job with ID or name ... not found`, treat it as a session/task reference, not a scheduler failure.
   - Continue by rerunning the actual SMC script or operational command for the class of task.

2. **Rerun the actual operational pipeline, not just a frontend refresh.**
   - For current SMC daily selection/live-monitor tasks, run the daily ops pipeline:
     ```bash
     python3 /root/.hermes/scripts/v25/smc_daily_ops.py
     ```
   - Long runtime is expected for V98→V100 structural gates because large trade JSON files are parsed and rewritten.

3. **Restart the dashboard after data regeneration.**
   - Kill the current `8890` listener.
   - Start `python3 smc_unified.py` using Hermes background process tracking, not shell `nohup`/`&` in foreground commands.
   - Wait for `/api/summary` readiness before validating pages.

4. **API contract verification comes before browser verification.**
   Check both `/api/picks` and `/api/live-prices` for zero blanks in:
   ```text
   pick_date, pickDate, join_date, joinDate,
   engine,
   zone_type, zoneType, zone, zone_low/zoneLow, zone_high/zoneHigh,
   cost_line, costLine, smart_money_cost,
   vol_class, volClass, volatility_pct, volatilityPct
   ```

5. **Then verify the DOM.**
   - `/monitor` headers must include `选股日期`, `加入日期`, `引擎`, `Zone`, `成本线`, `波动`.
   - `/monitor` rows should display `ZoneType [low~high]`, cost line, volatility percentage/class, and no blanks for engine.
   - `/live` headers must include `选股日期`, `加入日期`, `成本线`, `Zone`, `波动`.
   - `/live` rows should display non-empty cost line and volatility.

## Reporting format for Lei

Use a compact table with exact row counts and missing-field counts. Do not over-explain the failed ID. State the actionable result:

| Surface | Rows | Missing critical fields | Status |
|---|---:|---:|---|
| `/api/picks` | N | 0 | OK |
| `/api/live-prices` | N | 0 | OK |
| `/monitor` | rendered | 0 visible blanks | OK |
| `/live` | rendered | 0 visible blanks | OK |

## Pitfalls

- `Job with ID or name ... not found` means the ID may be a conversation/session ID; it does not prove the SMC pipeline failed.
- Do not stop after API success; the user specifically cares about frontend rows being visible and synchronized.
- Do not patch only HTML. Blank fields usually require the shared field contract and API payload to be correct first.
- Avoid shell-level background wrappers when restarting `smc_unified.py`; use tracked background process tools so the service can be managed and logs checked.
