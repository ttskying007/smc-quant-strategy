# V68 frontend production sync — active version + field contract

Use this when promoting a new SMC engine version to the 8890 dashboard and the monitor/live pages show stale rows or blank Zone/成本线/波动 fields.

## Durable lesson

A new engine artifact directory is not enough. The dashboard has **four independent readers** that must all know the new version:

1. `ACTIVE_VERSION`, `ACTIVE_TRADE_FILE`, `ACTIVE_PICK_FILE`
2. version-specific readers: `get_version_trades()` and `get_version_picks()`
3. path registry: `_active_version_paths()`
4. scoped pick lifecycle: `_normalize_pick_scope()`, `get_active_picks()`, and `build_monitor()` filtering

If any of these remains on the previous production version, one surface can look fixed while another still renders old rows or empty fields.

## Required promotion checklist

### 1. Register active files

Add the new version before the previous production version:

```python
ACTIVE_VERSION = ('V68' if Path('/root/.hermes/smc_opt_v68_strict_ld/v68_report.json').exists()
                  else 'V66' if Path('/root/.hermes/smc_opt_v66/v66_report.json').exists()
                  ...)

ACTIVE_TRADE_FILE = (Path('/root/.hermes/smc_opt_v68_strict_ld/v68_trades.json') if ACTIVE_VERSION == 'V68'
                     else ...)

ACTIVE_PICK_FILE = (Path('/root/.hermes/smc_opt_v68_strict_ld/v68_picks.json') if ACTIVE_VERSION == 'V68'
                    else ...)
```

### 2. Register version readers

```python
if version == 'V68':
    raw = _load_json_list(V68_DIR/'v68_trades.json', [])
    return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw] if lite else raw

if version == 'V68':
    return normalize_v27_picks(_load_json_list(V68_DIR/'v68_picks.json', []), get_version_trades('V68', lite=False))
```

### 3. Register path metadata

`_active_version_paths()` must return script/out_dir/prefix/engine/trades/picks/watchlist/metrics for the new version. Backtest, docs, analysis, and reselect code rely on this registry.

### 4. Include the version in scoped-pick logic

Add the version to all current/scoped engine tuples:

- `normalize_v27_picks()` current scoped versions
- `_normalize_pick_scope()` current version list
- `get_active_picks()` list that returns `ACTIVE_CANDIDATE` + `WATCH_ONLY`

Pitfall: if `pick_scope` is a custom string such as `STRICT_LD_V68_LIMIT`, `_normalize_pick_scope()` will preserve it and `get_active_picks()` returns zero rows. Candidate files should use `pick_scope: ACTIVE_CANDIDATE` or `WATCH_ONLY`; put strategy identity in `pick_scope`-independent fields like `engine`, `source`, `reason`, or `entry_model`.

### 5. Live page source precedence

`/api/live-prices` can silently prefer durable old monitor positions (`load_positions()`) over the new pick file. For a newly promoted candidate engine, bypass old monitor positions or explicitly gate them by active version:

```python
positions = load_positions() if load_positions else []
use_monitor_positions = bool(positions) and ACTIVE_VERSION != 'V68'
pending_fill_pre = fill_pending_orders() if (fill_pending_orders and use_monitor_positions) else {'changed': 0}
open_positions = [p for p in positions if p.get('status') == 'OPEN'] if use_monitor_positions else []
pending_positions = [p for p in positions if p.get('status') == 'NEXT_DAY_PENDING'] if use_monitor_positions else []
```

Otherwise `/api/picks` can show the new engine while `/api/live-prices` still shows old V66 rows.

### 6. Recency filter caveat

The live API has a 45-day fallback filter. Backtest-derived candidate picks may have older entry dates even though they are the current candidate set. For such promotion/validation engines, skip the filter or generate true current watchlist dates; otherwise live returns `无近期选股(45天内)` despite valid picks.

### 7. Field contract for every pick row

Every pick/live row must carry non-empty values for:

```text
pick_date/select_date, join_date, zone_type, zone_low, zone_high,
cost_line/smart_money_cost, volatility_pct/v25_vol_class,
entry_price, sl, tp1, engine
```

`_apply_smc_field_contract()` can fill many fields, but the artifact generator should emit them directly so physical JSON also passes audit.

## Verification script pattern

After restart, verify both APIs and both pages:

```python
import json, urllib.request
for path, fields in {
  '/api/picks': ['pick_date','select_date','join_date','zone_type','zone_low','zone_high','cost_line','smart_money_cost','volatility_pct'],
  '/api/live-prices': ['pickDate','joinDate','zoneType','zoneLow','zoneHigh','costLine','volClass','volatility_pct'],
}.items():
    data = json.load(urllib.request.urlopen('http://127.0.0.1:8890' + path, timeout=20))
    rows = data.get('picks') if isinstance(data, dict) and 'picks' in data else data
    assert rows, path
    missing = {f: sum(1 for r in rows if r.get(f) in (None, '', 0, 0.0, [])) for f in fields}
    assert all(v == 0 for v in missing.values()), (path, missing)
```

Browser DOM check:

```javascript
[...document.querySelectorAll('table')].map((t,i)=>({
  i,
  headers:[...t.querySelectorAll('thead th')].map(th=>th.textContent.trim()),
  first:[...t.querySelectorAll('tbody tr:first-child td')].map(td=>td.textContent.trim()).slice(0,18)
}))
```

The monitor page often has two tables: old durable monitor positions first, active pick table second. Validate the table containing headers `引擎/选股日期/加入日期/Zone/成本线/波动`, not only the first table.

## Impact-analysis note

Before editing `smc_unified.py`, run GitNexus impact on touched symbols. In this class of change, `_api_live_prices` is usually LOW risk, while `get_version_trades()`, `get_version_picks()`, and `_active_version_paths()` can report HIGH/CRITICAL because many dashboard surfaces depend on them. Treat that as a blast-radius warning and keep edits minimal and version-gated.
