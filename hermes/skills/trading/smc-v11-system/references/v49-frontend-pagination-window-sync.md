# V49 Frontend Pagination + Manual Backtest Window Sync Lessons

Session lesson from V49 SMC dashboard work.

## Problem class

When `/backtest` supports a manual date/window rerun, the detailed trade table must render the complete filtered trade set. A static server-rendered `<tbody>{trade_rows}</tbody>` can appear incomplete when the date window produces many rows, and K-line detail panels can become unusable when SMC signals or HH/HL/LH/LL pivot rows exceed the visible area.

## Required frontend pattern

1. Keep backend filtering authoritative:
   - The active trade JSON/report or manual rerun result defines the full filtered row set.
   - The frontend table must not apply another hidden row cap.
   - Do not deduplicate or truncate detailed trade rows unless the UI explicitly labels it.

2. Render detailed tables from a JSON array on the client:
   - Build `BT_ROWS`/equivalent from the already-filtered `display_trades`.
   - Use a dedicated `<tbody id="...">` populated by JS.
   - Show a visible page status: current page, total pages, rows on page, total rows.

3. Pagination controls:
   - Default page size: 100.
   - Allow 50 / 100 / 200 / 500.
   - Provide 上一页 / 下一页 buttons.
   - Clamp page index to `[1, pages]` so repeated clicks never blank the table.

4. Apply the same pagination component to K-line detail panels:
   - SMC detailed signals (`signals_list`).
   - HH/HL/LH/LL high-low pivot list (`wave_swings`/`swings`).
   - Stock-specific trade list.

5. Reset detail pages when loading a new symbol/version:
   - `tablePages = {signals:1, swings:1, trades:1}` before rendering new data.

## Verification checklist

After patching `smc_unified.py`:

```bash
cd /root/.hermes/scripts
python3 -m py_compile smc_unified.py
python3 - <<'PY'
import sys
sys.path.insert(0,'.')
import smc_unified
html = smc_unified.build_backtest()
assert 'var BT_ROWS=' in html
assert 'bt-page-info' in html
assert 'bt-page-size' in html
assert 'bt-trade-body' in html
khtml = smc_unified.build_kline('603685.SH')
assert 'var tablePages' in khtml
assert 'function pageControls' in khtml
assert "pageControls('signals'" in khtml
assert "pageControls('swings'" in khtml
assert "pageControls('trades'" in khtml
print('frontend pagination ok')
PY
```

Then restart the 8890 frontend and verify via HTTP:

```bash
python3 - <<'PY'
import urllib.request, json
base='http://127.0.0.1:8890'
back=urllib.request.urlopen(base+'/backtest',timeout=20).read().decode('utf-8','ignore')
kl=urllib.request.urlopen(base+'/kline?s=603685.SH',timeout=20).read().decode('utf-8','ignore')
api=json.loads(urllib.request.urlopen(base+'/api/kline_full?symbol=603685.SH&ver=V49',timeout=30).read())
assert 'var BT_ROWS=' in back and 'bt-page-info' in back and 'bt-trade-body' in back
assert 'function pageControls' in kl and "pageControls('signals'" in kl and "pageControls('swings'" in kl
assert api.get('signal_count',0) >= 0 and len(api.get('wave_swings') or api.get('swings') or []) >= 0
print('http pagination sync ok')
PY
```

## Pitfall

Do not solve this by raising a hardcoded table limit. The user expects all manually selected backtest rows to remain accessible. The durable fix is client-side pagination over the complete filtered dataset, plus the same paginated treatment for high-volume K-line detail tables.
