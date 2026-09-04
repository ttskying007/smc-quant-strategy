# SMC Frontend Architecture Reference

> Originally `smc-unified-frontend` standalone skill. Absorbed into `smc-v11-system`.
> The umbrella skill covers routing, versions, and basic frontend info. This file preserves deep ECharts rendering and maintenance knowledge.

## Signal Drawing Architecture (13 types)

All signals render via `SIG_STYLE` config dict mapping signal type to:
- markArea (rectangular zones: FVG, OB, BPR, IFVG, etc.)
- markLine coords (line signals: Sweep, CHOCH, BOS, MSS, EQL)
- markPoint (entry/exit pins, HH/HL swing dots)

### Signal Chain Rendering (V7.0+)
```
signal_chain: [{'type': 'Sweep_SSL', 'bar': 268}, {'type': 'Pinbar_Bull', 'bar': 271, 'price': 9.55}]
→ markPoint roundRect letter markers (A, B, C...) 
→ markLine dashed connector 
→ final connector to BUY pin
```

### Signal Grade Coloring (V9)
- Grade A: Gold (#FFD700) — strong signal
- Grade B: Silver (#C0C0C0) — medium signal
- Grade C: Bronze (#CD7F32) — basic signal
- ⚠️ Caveat: Grade scoring negatively correlates with performance (A<B<C), colors may mislead

## Data Flow

```
signals_v11.detect_all_signals_v11(ohlcv, tf)
  → 13 signal types {type, idx, upper, lower, price, strength, confidence}
  → mapped to SIG_STYLE for rendering

Trade engine results (V465/V466/V467 flat arrays or V469 dict)
  → trade_map rebuilt at server start: symbol → [trade, ...]
  → stock dropdown generated from trade_map.keys()

OHLCV data (daily/60min)
  → loaded by symbol → ECharts candlestick
  → date index for signal positioning + 60min→daily index mapping
```

## ECharts Pitfalls (Critical)

### pitfall 0: V27 signal type names don't match SIG_STYLE_MAP keys
- V27 `v27_recent_signals.json` stores types as bare names: `'OB'`, `'BPR'`, `'OTE'`, `'SWEEP'`
- `SIG_STYLE_MAP` keys use suffixed names: `'OB_Bull'`, `'BPR_Bull'`, `'OTE_Bull'`, `'Sweep_SSL'`
- JS `buildMarkAreas()` skips signals where `SIG_STYLE_MAP[s.type].fill` is undefined
- Fix: in `_api_kline_full`, map types when building V27 signals_list:
  ```python
  type_map = {'OB':'OB_Bull','OTE':'OTE_Bull','BPR':'BPR_Bull',
              'FVG':'FVG_Bull','SWEEP':'Sweep_SSL',
              'BOS':'BOS_Bull','CHOCH':'CHOCH_Bull','MSS':'MSS_Bull',
              'PO3':'PO3_Acc'}
  mapped_type = type_map.get(raw_type, raw_type)
  ```
- Verify: `echarts.getInstanceByDom(chart).getOption().series[0].markArea.data.length` must be > 0

### pitfall 1: `echarts.init(dom, 'dark')` fails silently
- ECharts 5 dark theme NOT bundled by default
- Fix: `echarts.init(dom)` + apply dark colors via CSS/option

### pitfall 2: markArea format
- MUST be `[[{xAxis,yAxis},{xAxis,yAxis}],...]` NOT `[{data:[...]},...]`
- Wrong format → silent fail (no render, no error)

### pitfall 3: markPoint format — coord vs value
- **Wrong**: `{value: [dateStr, price], symbol: 'triangle', ...}` → no render
- **Correct**: `{coord: [dateStr, price], value: "HH", symbol: 'triangle', ...}`

### pitfall 4: markLine coords format
- NEED label+line separation: `[{xAxis:...},{xAxis:...}]` in pairs
- Setting both xAxis AND yAxis on horizontal lines → renders as single point instead of full-width line
- Fix: only yAxis for horizontal, only xAxis for vertical

### pitfall 5: Python f-string + JS curly braces
- `{series:[{name:...}]}` in f-strings → parsed as expression placeholders
- Fix: `{{series:[{{name:...}}]}}` (double braces) or pre-build JS as Python variable via `json.dumps()`

### pitfall 6: Patch produces `\\n` literal text
- `skill_manage action=patch` with `\\n` in old/new strings → literal backslash-n in file
- Fix: use `execute_code` with Python scripts instead of patch for multi-line code

### pitfall 7: Python module cache
- `from module import fn` caches in `sys.modules`
- Editing source file → old bytecode still runs
- Fix: MUST kill process + restart (deleting .pyc insufficient)

### pitfall 8: write_file f-string multiline truncation
- Writing Python source with f-strings via write_file → `\n` becomes real newlines → SyntaxError
- Fix: scan merged multiline f-strings + `py_compile` verify

## File Structure

| File | Description |
|------|-------------|
| `/root/.hermes/scripts/smc_unified.py` | Main server (~932 lines), routing V1-V9 + nav + homepage cards |
| `/root/.hermes/scripts/v6_module.py` | V6 stats panel + per-stock (267 lines) |
| `/root/.hermes/scripts/v7_module.py` | V7/V8/V9 K-line viewer (696 lines), signals/trades/TP-SL/grade colors |
| `/tmp/echarts.min.js` | ECharts 5 library (local copy, CDN blocked by GFW) |

## ⚠️ monitor_page.py is a DEAD FILE (2026-05-15)

`build_monitor_page()` is actually defined inline in `smc_unified.py` ~line 817, NOT in `monitor_page.py`. The file exists but is never imported. Edit `smc_unified.py` directly.

## Server Restart Protocol

After modifying `smc_unified.py`:
```bash
fuser -k 8890/tcp
find /root/.hermes/scripts/__pycache__ -delete
python3 smc_unified.py &
```

## Health Check Diagnostics

### Three-Step Diagnosis (execute in order)

**Step 1 — Is frontend alive?**
```bash
curl -s --max-time 3 http://127.0.0.1:8890/ | head -3
```
No output = not running. HTML returned = alive.

**Step 2 — Check port occupancy:**
```bash
ss -tlnp | grep -E ':(864[0-9]|889[0-9])'
```
- 8890: SMC unified frontend
- 8644/8643: Hermes main gateway
- 8642/8645/8646: stale gateway (should clean)
- 8648: Hermes WebUI

**Step 3 — Check process conflicts:**
```bash
ps aux | grep hermes | grep -v grep
```
Multiple `hermes gateway run --replace` = conflict.

### Cleanup Flow
1. Identify main gateway (longest-lived, usually smallest PID)
2. Kill extras: `kill <PID1> <PID2> ...`
3. Confirm: `ss -tlnp | grep 864` should show only 8644+8643
4. Restart frontend: `cd /root/.hermes/scripts && python3 smc_unified.py &`
5. Verify: `curl -s --max-time 3 http://127.0.0.1:8890/v17 | head -1` → `<!DOCTYPE html>`

### Common Symptoms → Root Cause

| Symptom | Root Cause | Fix |
|---------|------------|-----|
| 8890 no response | smc_unified.py not running | Start it |
| 8890 responds but /vXX empty | Python module cache stale | Kill + restart |
| Multiple gateway processes | Repeated `gateway run` without cleanup | Kill extras |
| WebUI unstable | Gateway conflict (multiple instances) | Keep only one gateway |

## Port Accumulation Cleanup

After multiple SMC frontend iterations (V7~V20), old frontend processes may accumulate on different ports. Diagnose:
```bash
ss -tlnp | grep -E ':(887[0-9]|888[0-9]|889[0-9])'
```
Release stale ports: `fuser -k <PORT>/tcp`
Active ports: 8890 (SMC), 8648 (WebUI), 8644 (gateway).
