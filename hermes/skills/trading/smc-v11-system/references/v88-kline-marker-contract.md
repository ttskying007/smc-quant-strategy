# V88/V90/V91 K-line marker field contract

## Trigger

Use this when the user reports that the K-line chart no longer shows:

- buy/entry markers
- TP/SL lines
- signal sequence labels
- active pick overlays

This can happen even when `/monitor` and `/live` field contracts are passing.

## Durable root causes

1. **K-line page defaults drift from production**
   - The page may default to an old version like `V66` while `ACTIVE_VERSION=V88`.
   - `/kline?symbol=...&ver=V88` must populate the symbol input and version dropdown from URL params before `loadKline()` runs.
   - The route must accept both `symbol=` and legacy `s=`.

2. **Current watchlist rows are not always historical trades**
   - V88 active picks can include V90/V91 scanner rows.
   - These rows may have no historical backtest trade for the same symbol/date.
   - If `_api_kline_full` only overlays `trades`, the chart shows no buy marker / TP / SL for current candidates.

3. **Sequence indices vary by engine**
   - V91/V90 rows may use `sweep_idx`, `event_idx`, `zone_idx`, `touch_idx`, `reclaim_idx`, `conf_index`, `entry_idx`.
   - Older branches only handled `zone_bar`, V46+ `source_event_idx`, or V30/V31 strict chain fields.
   - Add a generic index-chain fallback before version-specific branches.

## Minimal repair pattern

In `smc_unified.py`:

1. `build_kline(symbol='600519.SH', version=None)` defaults `version = version or ACTIVE_VERSION`.
2. `/kline` route uses:
   - `sym = qs.get('symbol', qs.get('s', ['600519.SH']))[0]`
   - `ver = qs.get('ver', qs.get('version', [ACTIVE_VERSION]))[0]`
   - `build_kline(sym, ver)`
3. K-line JS initializes controls from URL before `loadKline()`:
   - `symbol` or `s`
   - `ver` or `version`
   - `tf`
4. `_api_kline_full` overlays `stock_pick` as an open `ACTIVE` trade when there is no matching historical trade:
   - `entry_date`: `entry_date || join_date || pick_date || select_date || signal_date`
   - `entry_price`: `entry_price || price || cost_line || smart_money_cost`
   - `sl`: via `_apply_smc_field_contract()` from `sl/sl_price/risk_pct`
   - `tp_price`: `tp_price || tp || tp1 || target_price`
   - `_combo`: `ACTIVE`
   - `entry_detail`: `kline_active_pick_overlay`
5. Add generic sequence highlighting from candidate index fields:
   - `sweep_idx -> LIQ`
   - `event_idx/source_event_idx -> source_event`
   - `zone_idx -> Z:<zone_type>`
   - `touch_idx -> TOUCH`
   - `reclaim_idx -> RECLAIM`
   - `conf_index -> conf_type/entry_mode/CONF`
   - `entry_idx -> ENTRY`

## Verification checklist

Run syntax and deterministic API checks:

```bash
python3 -m py_compile /root/.hermes/scripts/smc_unified.py
python3 /root/.hermes/scripts/v25/test_kline_markers_v88.py
```

For at least one V91 active candidate and one V88 production candidate, verify:

- `/api/kline_full?symbol=<sym>&tf=daily&ver=V88` returns `trade_count >= 1`
- `highlight` is non-empty
- first trade has non-blank `entry_date`, `entry_price`, `sl`, `sl_pct`, `tp_price`, `tp_pct`, `_chart_idx`, `_combo`, `zone_type`
- Browser ECharts option has non-empty `series[0].markPoint.data`
- Browser ECharts option has SL/TP entries in `series[0].markLine.data`

Known-good examples from this session:

| Symbol | Expected |
|---|---|
| `300205.SZ` | V91 active pick; should have one `ACTIVE` trade overlay and sequence labels |
| `002262.SZ` | V88/V91 candidate; should show historical + active markers |
| `600483.SH` | historical/live holding; should show buy/SL/TP and sequence |

## Pitfall

Do not stop at the API status line (`750 bars | 90 signals | 1 trades`). Inspect ECharts `markPoint` and `markLine` from the browser console or DOM runtime. API trades can exist while chart rendering is empty if the page loaded the wrong version/symbol or URL params were ignored.
