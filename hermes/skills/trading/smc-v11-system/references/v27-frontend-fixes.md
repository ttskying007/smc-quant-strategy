# V27 Frontend Bug Fixes & Performance Optimization (2026-05-20)

Compendium of all smc_unified.py bugs discovered and fixed during V27.1 deployment.

---

## 1. K-line Chart: No Signal Markers (CRITICAL)

**Symptom**: Chart renders candlesticks but 0 markAreas. Signal table shows data but nothing on chart.

**Root Cause**: V27 signal types from `v27_recent_signals.json` use bare names:
- `'OB'`, `'BPR'`, `'OTE'`, `'SWEEP'`, `'BOS'`, `'CHOCH'`, `'MSS'`
 
But `SIG_STYLE_MAP` (Python dict) and `SIG_FAMILY` (Python dict) use suffixed names:
- `'OB_Bull'`, `'BPR_Bull'`, `'OTE_Bull'`, `'Sweep_SSL'`, `'BOS_Bull'`, `'CHOCH_Bull'`, `'MSS_Bull'`

JS function `buildMarkAreas()` at line 271:
```javascript
var style=SIG_STYLE_MAP[s.type]||{};
if(!style.fill)return;  // ← SKIPS all V27 signals because type not in map
```

**Fix** (in `_api_kline_full`, where V27 signals_list is built):
```python
type_map = {'OB':'OB_Bull','OTE':'OTE_Bull','BPR':'BPR_Bull',
            'FVG':'FVG_Bull','SWEEP':'Sweep_SSL',
            'BOS':'BOS_Bull','CHOCH':'CHOCH_Bull','MSS':'MSS_Bull',
            'PO3':'PO3_Acc'}
mapped_type = type_map.get(raw_type, raw_type)
signals_list.append({
    'type': mapped_type,
    'family': SIG_FAMILY.get(mapped_type, 'ob'),
    ...
})
```

**Verification**: Check `echarts.getInstanceByDom(chart).getOption().series[0].markArea.data.length` — should be > 0.

---

## 2. Backtest Page: Extreme Slowness + Duplicate Trades

**Symptom**: Backtest page takes 2-5s, renders 5000+ DOM elements, shows duplicate trades (same symbol+date+price appearing 3x).

**Root Cause**: 
1. `build_backtest()` renders ALL 47,448 trades in HTML table (no limit).
2. Same BOS/CHOCH event generates 3 setups (OB, OTE, BPR zones), each becomes a separate trade with identical entry_date + entry_price. This is by design but causes duplicates in the frontend display.
3. Cumulative PnL ECharts renders all 47k data points.

**Fix**:
```python
# 1. Dedup by (symbol, entry_date, entry_price)
seen_trades = set()
deduped = []
for t in sorted_trades:
    key = (t.get('symbol',''), str(t.get('entry_date',''))[:10], round(t.get('entry_price',0), 2))
    if key not in seen_trades:
        seen_trades.add(key)
        deduped.append(t)
display_trades = deduped[:100]

# 2. Sample cumulative PnL to 2000 points
sample_step = max(1, len(sorted_trades) // 2000)
for i, t in enumerate(sorted_trades):
    cum += t.get('pnl_pct', 0)
    if i % sample_step == 0 or i == len(sorted_trades) - 1:
        cum_pnl_data.append([...])
```

---

## 3. Monitor Page: Wrong Picks (Date Filter Mismatch)

**Symptom**: Monitor shows empty or wrong picks. Picks API returns data but monitor page shows different content.

**Root Cause**: `build_monitor()` filters by `entry_date >= cutoff` where `cutoff = today - 1day`. V27 picks have `entry_date` like `'20250704'` (July 2025) which is < `'20260519'` (today). ALL picks filtered out.

**Fix**: V27 picks have `state` field ('ACTIVE' or 'HISTORICAL'). Use state-based filtering:
```python
# V27 picks have 'state' field
if any(p.get('state') for p in picks):
    active = [p for p in picks if p.get('state') == 'ACTIVE']
    historical = [p for p in picks if p.get('state') == 'HISTORICAL']
    picks = active + historical[:100]
else:
    # Legacy picks: fallback to date-based filtering
    ...
```

---

## 4. Performance: 61MB JSON Parsed on EVERY Request

**Symptom**: Dashboard/Backtest/Monitor each take 2-3s. `v27_trades.json` is 61MB/47k trades.

**Root Cause**: `reload_trades()` calls `json.loads()` on 61MB file on EVERY page request. Same for `reload_picks()`.

**Fix**: In-memory cache with mtime-based invalidation:
```python
_TRADES_CACHE = None
_TRADES_LITE_CACHE = None  # stripped of nested zone/struct_event dicts
_PICKS_CACHE = None
_CACHE_MTIME = 0

def _cache_valid():
    f = Path('/root/.hermes/smc_opt_v27/v27_trades.json')
    return f.exists() and f.stat().st_mtime == _CACHE_MTIME

def _refresh_cache():
    # Load once, build lite copy without zone/struct_event (50% memory savings)
    raw = json.loads(f.read_text())
    _TRADES_CACHE = raw
    _TRADES_LITE_CACHE = [{k:v for k,v in t.items() if k not in ('zone','struct_event')} for t in raw]
    ...

def get_trades_cached(lite=True):
    if not _cache_valid():
        _refresh_cache()
    return _TRADES_LITE_CACHE if lite else _TRADES_CACHE
```

**Result**: Dashboard 2.3s→0.3s (7.7x), Monitor 1.9s→0.3s (6x), K-line API 2.1s→0.06s (35x).

---

## 5. ver_map Loads ALL Versions on Every K-line Request

**Symptom**: `_api_kline_full` slow (~2s) even for cached trades.

**Root Cause**: `ver_map` at line 2148 loads 13 versions via `_vdata()` (each does `json.loads()`) on every K-line API call, even though user only requested V27.

**Fix**: 
```python
ver_map = {
    'V27': get_trades_cached(lite=True),  # fast: in-memory
    'V25': None, 'V24': None, ...  # lazy
}
if ver != 'V27' and ver in _ver_paths:
    ver_map[ver] = _vdata(_ver_paths[ver])
elif ver_map.get(ver) is None:
    ver_map[ver] = ver_map['V27']
```

---

## 6. Version Selector Missing V27

**Symptom**: K-line page defaults to V19. User selects versions from old list.

**Fix**: Add `<option value="V27">V27 严格SMC</option>` as first child of `<select id="ver">`. Update default ver-badge from "V25" to "V27".

---

## 7. K-line API: Too Many Signals Per Stock

**Symptom**: `v27_recent_signals.json` has 300-500 zone entries per stock. All sent to frontend → ECharts renders 500 markAreas → browser lag.

**Fix**: Limit to 200 most recent: `v27_markers = v27_symbol_data[-200:]`

---

## 8. Date Format Mismatch (K-line vs Trades)

**Symptom**: Trades=0 on K-line page even though V27 data has trades for the stock.

**Root Cause**: K-line dates like `'2025-02-17'` (with hyphens). Trade dates like `'20250704'` (no hyphens). `date_map` building fails to match.

**Fix**: Normalize both sides:
```python
d_raw = str(k.get('date', k.get('t', '')))[:10]
d_norm = d_raw.replace('-', '')
date_map[d_raw] = i
if d_norm != d_raw:
    date_map[d_norm] = i
```

---

## 9. Variable Scope Bugs

### `seq` UnboundLocalError
Line 2183: `seq_parts = set(seq.replace(...))` — but `seq` only defined inside `if zb >= 0` block. Fix: initialize `seq = ''` before the block.

### `zb` UnboundLocalError  
Line 2176: `if zb >= 0` — but `zb` only defined in `else` branch (older pick format). Fix: initialize `zb = -1` before if/else.

### `prev_trend` NameError (smc_core_v27.py)
`prev_trend` used in MSS check but `trend` already updated to `new_trend`. Fix: save `old_trend = trend` before update.

---

## 10. Monitor: Heavy trade_by_sym Lookup

**Symptom**: Monitor page slow despite picks cache.

**Root Cause**: `build_rows()` builds `trade_by_sym = {t['symbol']: t for t in reload_trades()}` — iterates ALL 47k trades for every monitor request even though the dict is never used.

**Fix**: Remove the line entirely.

---

## Summary Checklist for smc_unified.py Changes

When modifying the frontend:
1. ✅ Kill old process + clear `__pycache__` + restart
2. ✅ Verify with `curl` timing before/after
3. ✅ Check version selector includes V27 as default
4. ✅ Check date format normalization (hyphens vs no-hyphens)
5. ✅ Check signal type mapping (bare names → suffixed names)
6. ✅ Check state-based filtering for V27 picks (not date-based)
7. ✅ Check trade dedup and row limits
8. ✅ Check cumulative PnL data point sampling
9. ✅ Check variable initialization (seq, zb) before use
10. ✅ Remove heavy lookups (trade_by_sym)
