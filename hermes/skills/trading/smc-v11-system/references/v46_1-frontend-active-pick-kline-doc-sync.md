# V46.1 frontend active-pick/K-line/docs synchronization regression

## Trigger
Use this reference when an SMC frontend reports one of these after a backend/watchlist repair:

- `当前版本暂不支持重跑，ACTIVE_VERSION=V46_1`
- `当前无有效 ACTIVE_CANDIDATE`
- `/api/picks/contract` says `active_pick_count: 0` while `v46_1_watchlist.json` contains active rows
- `/kline` is still defaulting to an older version, or `/api/kline_full?ver=V46_1` is not using the V46.1 signal source
- `/docs` still describes old V19/V27/V45 architecture after V46.1 changes

## Durable lesson
Backend files being correct is not enough. For SMC work, every V46.1 repair must be verified through the live frontend process and every public entry point. Stale in-memory cache and old running processes can make the browser show pre-fix data even after files were patched.

## Required repair pattern

1. **Register V46.1 in the frontend rerun path**
   - In `smc_unified.py`, `/api/reselect` must include `V46_1` in its `engine_map`.
   - It should run `/root/.hermes/scripts/v25/v46_1_layered_3y.py`.
   - Result file routing for V46.1 must read the watchlist, not historical picks:
     - trades: `/root/.hermes/smc_opt_v46_1_layered_3y/v46_1_trades.json`
     - active pick source: `/root/.hermes/smc_opt_v46_1_layered_3y/v46_1_watchlist.json`
     - validation: `/root/.hermes/smc_opt_v46_1_layered_3y/v46_1_validation_summary.json`

2. **Invalidate frontend caches, not just reload files**
   - Add/use an `_invalidate_cache()` helper that resets:
     - `_CACHE_MTIME`
     - `_TRADES_CACHE`
     - `_TRADES_LITE_CACHE`
     - `_PICKS_CACHE`
     - `_SUMMARY_CACHE`
     - `_SUMMARY_MTIME`
   - `/api/reload` must call `_invalidate_cache()` before `reload_trades()` / `reload_picks()`.
   - After writing new watchlist/trades from `/api/reselect`, also invalidate these caches.

3. **Treat ACTIVE_CANDIDATE as active**
   - `normalize_v27_picks()` / pick normalization must not only accept `state == ACTIVE`; V46.1 watch rows use `state == ACTIVE_CANDIDATE` or `pick_scope == ACTIVE_CANDIDATE` plus `is_active_pick: true`.
   - `get_active_picks()` should return only real current candidates:
     - `pick_scope == ACTIVE_CANDIDATE`
     - `is_active_pick == true`
   - Historical backtest representatives must stay isolated from `/api/picks`.

4. **Default K-line UI to latest active version**
   - `/kline` version selector must put V46.1 first and selected:
     - `<option value="V46_1" selected>...`
   - `/api/kline_full?ver=V46_1` must use the same signal source as backtest:
     - Pine-like for FVG/BPR/EQL/OTE/LV
     - LuxAlgo V34 for structure/sweeps/OB/swing/internal structure
   - V46.1 highlight chain should include the indices carried by watch/trade rows:
     - `source_event_idx`
     - `zone_idx`
     - `retrace_index`
     - `conf_index`

5. **Update `/docs` when frontend data contracts change**
   The architecture document must explicitly state:
   - `ACTIVE_VERSION`
   - active trade file
   - active watchlist/pick file
   - rerun engine path
   - pick contract counts
   - whether historical best trades are isolated
   - K-line signal source and highlight-chain contract

6. **Restart the frontend process after patching**
   Editing `smc_unified.py` does not update the running server. Restart the process on port 8890, then verify by HTTP calls against `127.0.0.1:8890`.

## Verification checklist
Run syntax checks first:

```bash
cd /root/.hermes/scripts
python3 -m py_compile smc_unified.py v25/v46_1_layered_3y.py
```

Then verify through the live frontend server, not just importing the module:

```python
import urllib.request, json
base = 'http://127.0.0.1:8890'
print(urllib.request.urlopen(base + '/api/reload', timeout=30).read().decode()[:1000])
print(urllib.request.urlopen(base + '/api/picks/contract', timeout=30).read().decode()[:1000])
print(urllib.request.urlopen(base + '/api/picks', timeout=30).read().decode()[:1000])
for path in ['/monitor','/docs','/kline?s=000034.SZ']:
    html = urllib.request.urlopen(base + path, timeout=30).read().decode()
    print(path, 'V46_1=', 'V46_1' in html,
          'empty_active_msg=', '当前无有效 ACTIVE_CANDIDATE' in html,
          'doc_v46=', 'V46.1 当前生产契约' in html,
          'kline_default=', '<option value="V46_1" selected>' in html)
data = json.loads(urllib.request.urlopen(
    base + '/api/kline_full?symbol=000034.SZ&tf=daily&ver=V46_1', timeout=30
).read().decode())
print(data.get('version'), len(data.get('signals_list', [])), len(data.get('highlight', [])), data.get('error'))
```

Expected healthy shape:

```json
{
  "active_pick_count": 101,
  "historical_best_count": 0,
  "watch_only_count": 996,
  "raw_pick_file_count": 1097,
  "active_picks_not_historical_all_market": true
}
```

Counts may change after new data, but `active_pick_count` must not be zero when active rows exist in `v46_1_watchlist.json`, `/monitor` must not show the empty ACTIVE_CANDIDATE message, `/docs` must show V46.1 architecture text, and `/kline` must default to V46.1.

## Pitfall
Do not validate only by importing `smc_unified.py` in a fresh Python process. That can pass while the live 8890 server still serves stale code/cache. Always restart or verify the actual HTTP server process.
