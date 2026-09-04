# SMC Frontend Performance & Debugging Guide

## When pages are slow or chart doesn't render

### 1. Process restart — must be clean
```
# Kill ALL instances (not just the known PID)
for pid in $(pgrep -f "smc_unified"); do kill -9 $pid 2>/dev/null; done
sleep 2
# Clear Python bytecode cache — MUST DO THIS or old .pyc runs
find /root/.hermes/scripts/ -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
# Verify all dead
pgrep -f smc_unified || echo "clean"
# Start fresh
cd /root/.hermes/scripts && python3 -u smc_unified.py &
```

### 2. Measure page speed (server-side)
```bash
for url in "http://localhost:8890/" "http://localhost:8890/backtest" "http://localhost:8890/monitor" "http://localhost:8890/kline?s=000001.SZ"; do
    curl -s -o /dev/null -w "$url: %{time_total}s\n" --max-time 10 "$url"
done
```

### 3. K-line chart not showing signals

**Symptom**: K-line candlesticks render but no signal rectangles (markAreas=0)

**Root cause chain**:
1. `v27_recent_signals.json` stores signal types as: `'OB'`, `'BPR'`, `'OTE'` (singular, no direction)
2. Frontend `SIG_FAMILY` / `SIG_STYLE_MAP` use keys like: `'OB_Bull'`, `'BPR_Bull'`, `'OTE_Bull'`
3. `buildMarkAreas()` lookup fails → `style.fill` undefined → signal skipped

**Fix**: Add type mapping in `_api_kline_full()`:
```python
type_map = {'OB':'OB_Bull', 'OTE':'OTE_Bull', 'BPR':'BPR_Bull',
            'FVG':'FVG_Bull', 'SWEEP':'Sweep_SSL',
            'BOS':'BOS_Bull', 'CHOCH':'CHOCH_Bull', 'MSS':'MSS_Bull',
            'PO3':'PO3_Acc'}
mapped_type = type_map.get(raw_type, raw_type)
# Also: family = SIG_FAMILY.get(mapped_type, 'ob')  — NOT hardcoded 'ob'
```

**Verification**: Browser console:
```javascript
var c=document.getElementById('chart');
var inst=echarts.getInstanceByDom(c);
inst.getOption().series[0].markArea.data.length  // should be > 0
```

### 4. Backtest page slow (47k trades → massive HTML)

**Root cause**: Every backtest page load renders ALL 47,448 trades as HTML table rows.

**Fixes applied**:
- Trade dedup by `(symbol, entry_date[:10], round(entry_price, 2))` — removes duplicate zone-type entries for same event
- Limit display to 100 trades
- Cumulative PnL chart sampled to 2000 points (from 47k)
- Removed `<meta http-equiv="refresh" content="120">` auto-refresh

### 5. Monitor / Picks page data inconsistency

**Root cause**: `build_monitor()` filtered picks by `entry_date >= today` using date strings. V27 picks have historical entry_dates (e.g., "20250704") which are always < today, resulting in empty filter.

**Fix**: Switch to state-based filtering:
```python
if any(p.get('state') for p in picks):
    active = [p for p in picks if p.get('state') == 'ACTIVE']
    historical = [p for p in picks if p.get('state') == 'HISTORICAL']
    picks = active + historical[:100]
```
Legacy date-based filtering only used for picks without `state` field.

### 6. K-line date format mismatch

**Symptom**: API returns trades but frontend shows 0 trades on chart.

**Root cause**: K-line dates have hyphens ("2025-02-17"), trade dates don't ("20250704"). `date_map` lookup fails.

**Fix**: Normalize both sides:
```python
d_norm = d_raw.replace('-', '')
date_map[d_raw] = i
if d_norm != d_raw:
    date_map[d_norm] = i
# Then try both on lookup:
ci = date_map.get(ed, -1)
if ci < 0:
    ci = date_map.get(ed.replace('-', ''), -1)
```

### 7. Version selector missing V27

**Symptom**: K-line page defaults to V19 in dropdown.

**Fix**: Add `<option value="V27">V27 严格SMC</option>` as first option in version `<select>`.

### 8. Memory caching (61MB JSON per request → 0.3s)

**Problem**: `reload_trades()` called `json.loads()` on 61MB `v27_trades.json` on EVERY request.

**Fix**:
```python
_TRADES_CACHE = None
_TRADES_LITE_CACHE = None  # stripped of nested zone/struct_event dicts

def _cache_valid():
    return Path('...v27_trades.json').stat().st_mtime == _CACHE_MTIME

def get_trades_cached(lite=True):
    if not _cache_valid():
        _refresh_cache()  # loads 61MB once, builds lite copy
    return _TRADES_LITE_CACHE if lite else _TRADES_CACHE
```

Lite copy strips `zone` and `struct_event` nested dicts (50% memory savings for frontend serving).

### 9. ver_map loading all versions unnecessarily

**Problem**: `_api_kline_full` built ver_map with ALL versions (V27-V12) by calling `_vdata()` for each, loading multiple JSON files per request.

**Fix**: Only load V27 from cache. Other versions lazy-load only when explicitly requested via `ver` parameter.

### 10. Chart checkboxes don't filter V27 signals

**Root cause**: V27 signals all had `family: 'ob'` hardcoded. Checkboxes control visibility by `family`, so only 'OB' checkbox affected ALL V27 signals.

**Fix**: Set family from `SIG_FAMILY.get(mapped_type, 'ob')` — BPR gets 'bpr', OTE gets 'ote', etc. Each checkbox now controls its signal type independently.

### 11. Coule code search (semble)

For quick navigation of `smc_unified.py` (2500+ lines), use:
```bash
~/.hermes/scripts/semble.sh search "how is version mapping done" /root/.hermes/scripts
~/.hermes/scripts/semble.sh search "build_monitor" /root/.hermes/scripts --top-k 5
```
Uses ~98% fewer tokens than grep+read. Model: `minishlab/potion-code-16M` (63MB cached at `~/.cache/huggingface/`).
Requires: `https_proxy=http://127.0.0.1:7890` + `HF_ENDPOINT=https://huggingface.co` (set by wrapper).
