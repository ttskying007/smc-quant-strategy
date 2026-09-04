# SMC frontend mixed numeric/string route crash

Date: 2026-06-26

## Symptom
- Port `8890` is listening and API endpoints such as `/api/summary` work, but browser page `/` returns `Empty reply from server`.
- Log `/root/.hermes/logs/smc_unified_8890.log` shows route exceptions such as:
  - `TypeError: unsupported operand type(s) for +: 'int' and 'str'` in `build_dashboard`, `build_backtest`, or `build_analysis`
  - `TypeError: '>' not supported between instances of 'str' and 'int'`
  - `ValueError: Unknown format code 'f' for object of type 'str'` in `build_autopsy`

## Root cause
New production artifacts may serialize numeric fields (`pnl_pct`, `sl_pct`, `rr`, `hold_bars`, prices) as strings. HTML route code that aggregates or formats these fields directly (`sum(t.get('pnl_pct', 0))`, `t.get('pnl_pct') > 0`, `{value:.2f}`) crashes the request handler. Because the server is `BaseHTTPServer`, the process stays alive and API routes may still work, making it look like only the page is down.

## Fix pattern
- Do not change strategy artifacts to fix display issues.
- Normalize numeric fields at render/summary boundaries with the existing `_float_or_zero()` helper.
- Patch all affected HTML routes, not only `/`:
  - `build_dashboard`
  - `build_backtest`
  - `build_analysis`
  - `build_compare` if it aggregates pnl
  - `build_autopsy`
  - versioned summary paths if they aggregate old-version data

## Verification
1. `python3 -m py_compile /root/.hermes/scripts/smc_unified.py`
2. Restart `smc_unified.py` on port 8890.
3. Curl smoke all major routes:
   - `/`
   - `/backtest`
   - `/analysis`
   - `/compare`
   - `/autopsy`
   - `/monitor`
   - `/live`
   - `/kline`
   - `/api/summary`
   - `/api/picks?version=V175`
   - `/api/live-prices?version=V175`
4. Confirm each returns HTTP 200 and log tail after restart contains no new exception.

## GitNexus note
If editing `smc_unified.py` under a GitNexus-indexed context, run impact analysis on each edited symbol. `normalize_v27_trades` can show CRITICAL impact because it feeds shared caches; a safe surgical numeric-cast-only change still requires full route smoke verification.
