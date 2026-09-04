# V23 Monitor & Picks Data Pipeline Updates

## tp_tiers Format Evolution (V22→V23)

### V22: Flat percentage
```json
"tp_tiers": [10]   // just 10%
```
Monitor code expected a list of floats: `tp_list = p.get('tp_tiers', [])`

### V23: Structured tier tuples
```json
"tp_tiers": [["swing_high", 10.42, 24.8], ["FVG_resist", 9.98, 19.5], ...]
```
Format: `(source_name, price, distance_pct)`

### Fix: Multi-format parser in monitor
```python
tp_raw = p.get('tp_tiers', [])
if isinstance(tp_raw, str):
    # Parse "OB_resist:9.7(16.2%),FVG_resist:9.98(19.5%)"
    tp_list = [float(m.group(1)) for m in re.finditer(r'\(([\d.]+)%\)', tp_raw)]
elif isinstance(tp_raw, list) and tp_raw and isinstance(tp_raw[0], (list, tuple)):
    tp_list = [t[2] for t in tp_raw]  # Extract distance from tuples
```

## V23-Specific Field Mapping

V23 engine produces these fields that `build_monitor()` and `/api/live-prices` consume:

| Field | Source in v23_engine.py | Monitor Column |
|-------|------------------------|----------------|
| `symbol` | trade['symbol'] | 代码 |
| `engine` | 'V23' | 引擎 |
| `score` | len(ctx_seq)//4 | S (with bar) |
| `entry_quality` | conf_type.replace('_BOUNCE','确认') | 质量 |
| `retrace_pct` | entry_to_zone_pct | 回撤 |
| `price` | entry_price | 现价 |
| `dz_low/dz_high` | cost_line / cost_line×1.03 | Zone |
| `regime` | HV/ST/RG/WT | 状态 |
| `sl_initial_pct` | sl_distance | SL |
| `tp_tiers` | list of (name,price,dist%) tuples | TP |
| `ctx_seq` | BOS→CH→FVG→IDM string | 序列 |
| `detail` | zone_type→BOS→conf_type | K线tooltip |
| `entry_date` | date string YYYYMMDD | 45天过滤关键 |

## Date Pipeline (Must Not Break)
1. K-line cache: `d['t']` NOT `d['date']` 
2. Engine: `b.get('t', b.get('date', f'bar{i}'))`
3. Symbol mapping: trade "000027.SZ" → kline "000027_SZ_daily_300.json"
4. Pick generation: cross-reference `kline_dates[sym][zone_bar][1][:8]`

Missing `entry_date` → ALL picks filtered by 45-day recency → "无近期选股(45天内)"
