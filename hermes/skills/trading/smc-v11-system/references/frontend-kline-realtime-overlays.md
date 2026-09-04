# SMC Frontend K-line + Realtime Sync Lessons

Use this when fixing SMC frontend/API synchronization around K-line overlays, monitor positions, realtime prices, and market-closed/suspended display.

## Durable lessons

1. **K-line page must be execution-aware, not only backtest-aware**
   - Historical `trades` files are not enough for current holdings.
   - Overlay durable monitor positions from `load_positions()` onto `/api/kline_full` so live holdings display BUY/PENDING points even if they are not present in backtest trade files.
   - For OPEN positions, use real buy date from `created_at`/`buy_date`; for `NEXT_DAY_PENDING`, use `pick_date` as pending marker date.

2. **K-line overlays must include BUY + SL + TP**
   - Build synthetic trade rows with at least:
     - `entry_date`
     - `entry_price`
     - `sl_price` or `sl`
     - `tp1` / `tp_price`
     - `exit_date` empty for live open positions
     - `exit_reason` as `OPEN` or `NEXT_DAY_PENDING`
   - Do not draw fake SELL markers for OPEN/PENDING positions. Only draw SELL if `exit_price > 0` and `exit_date` exists.

3. **Weekly K-line needs explicit UI and cache routing**
   - Add `weekly` to the timeframe selector.
   - `/api/kline_full?tf=weekly` should load weekly cache files such as:
     - `symbol_weekly_200.json`
     - `symbol_weekly_300.json`
   - Date-to-index mapping for weekly bars must map a daily buy date to the first weekly bar whose bar date is >= buy date; if beyond cache end, place it on the last bar.

4. **Realtime page must always show a last known price**
   - Do not show only `休市` or blank when market is closed or Tencent realtime quote is absent.
   - Fallback to latest cached daily K-line close (`c`) as `lastPrice`.
   - Return both:
     - `livePrice`: true realtime quote, may be 0 outside trading or suspended
     - `lastPrice`: realtime quote if available, otherwise latest cached close
   - Use `lastPrice` for display/PnL fallback, but separate its status.

5. **Separate market quote status from monitor/holding status**
   - Realtime API/page should expose/display independent columns:
     - `行情状态`: `实时`, `休市-最后K线`, `停牌/无实时-最后K线`, `无价格`
     - `最后价格`: fallback price plus date
     - `持仓状态`: `HOLDING`, `SL_CLOSE`, `TP_CLOSE`, `NEXT_DAY_PENDING`, etc.
   - Avoid overwriting holding status with market status.

## Verification checklist

Run API-level verification before claiming done:

- `/live` HTML contains `最后价格`, `行情状态`, `持仓状态`.
- `/kline?s=<symbol>` HTML contains weekly option.
- `/api/live-prices` returns for every row:
  - `lastPrice > 0` when cached K-line exists
  - non-empty `priceStatus`
  - original monitor `status`
- `/api/kline_full?symbol=<symbol>&tf=daily&ver=<active>` returns live overlay trade with BUY/PENDING and SL/TP.
- `/api/kline_full?symbol=<symbol>&tf=weekly&ver=<active>` returns bars and same BUY/PENDING + SL/TP overlay.

## Common pitfalls

- Treating `NO_DATA` as “休市” loses last known prices and hides suspended/no-realtime cases.
- Filtering K-line overlays only from historical trade files hides current monitor positions.
- Daily date strings (`YYYYMMDD`) do not exactly match weekly bar dates; exact `date_map.get()` fails for weekly. Use nearest-forward index mapping.
- Drawing SELL markers for live open positions creates false exits on the chart.
