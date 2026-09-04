# SMC Frontend Field Normalization Lessons

Use this reference when fixing SMC dashboard/API blank fields in `smc_unified.py`, especially `/monitor`, `/api/picks`, `/live-prices`, and `/api/live-prices`.

## Durable pattern

When engine output JSON lacks fields expected by the frontend, fix the shared normalization layer first, not each cell renderer independently. Keep backend API and frontend table mapping synchronized.

## Monitor / picks page checklist

- Add display columns only after confirming `/api/picks` returns the same normalized fields.
- Normalize `engine` with a production-version fallback, e.g. current `ACTIVE_VERSION`, so historical pick records do not render blank.
- Normalize `zone_type` from the available signal fields, for example:
  - `zone_type`
  - `signal_type`
  - version-specific setup family field such as `v59_setup_family`
- If zone price bounds are unavailable, show the signal/zone type text instead of rendering an empty or misleading `0` range.
- Treat selection date and join date separately:
  - `select_date`: usually the normalized `pick_date` from the pick/watchlist record.
  - `join_date`: should come from active monitor state when possible, commonly `positions.json.created_at`, joined by `(symbol, pick_date)`.
- Keep table metadata synchronized after adding columns: header cells, row cells, empty-state `colspan`, export/API field lists if present.

## Live prices page checklist

- `costLine` should never fall through to `0` if a valid entry/cost proxy exists. Fallback chain:
  1. `smart_money_cost`
  2. `cost_line`
  3. `entry_price`
- `volClass` should never render blank. Fallback chain:
  1. `market_state`
  2. `regime`
  3. `quality_tier`
  4. derived risk label from `sl_pct` / `risk_pct`
  5. `zone_type`
- Verify both API JSON and browser-rendered table cells. A passing API alone is insufficient for Lei's SMC workflow.

## Verification commands / probes

After patching and restarting the 8890 service, verify:

- `/monitor` HTML contains the new columns and non-empty cells.
- `/api/picks` returns `engine`, `zone_type`, `select_date`, `join_date`.
- `/api/live-prices` returns non-zero `costLine` and non-empty `volClass`.
- Browser render shows the same values; do not rely only on backend JSON.

## Pitfalls

- Current watchlist rows may not have `entry_date`; use `pick_date/conf_date/retrace_date/signal_date` style fallback where available.
- Historical trade records are not a substitute for active watchlist/current picks.
- Avoid broad refactors in `smc_unified.py`; prefer a small normalization patch that keeps old data compatible.
- Do not claim completion until API and visual browser checks both pass.
