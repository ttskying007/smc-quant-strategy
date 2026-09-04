# SMC Frontend Field Contract Repair Pattern

Use this when `/monitor`, `/live`, `/api/picks`, or `/api/live-prices` shows blank dates, engine, Zone, cost line, volatility, or inconsistent field names after adding/changing an engine.

## Symptom

Typical user report:

- 选股页需要显示 `选股日期` / `加入日期`.
- 选股页下方实时监控表 engine / Zone 为空.
- 实时页 `成本线` / `波动` / Zone 为空.
- API objects have one naming style but browser JS expects another (`pick_date` vs `pickDate`, `cost_line` vs `costLine`).

## Durable fix

Centralize the cross-surface field contract in `_apply_smc_field_contract(row, default_engine=None)` and call it before data leaves every API/page surface.

Required canonical fields:

| Canonical | Browser alias | Fallbacks |
|---|---|---|
| `pick_date` | `pickDate` | `select_date`, `conf_date`, `confirm_date`, `retrace_date`, `entry_date`, `signal_date`, `date` |
| `join_date` | `joinDate` | `joined_date`, `joined_at`, `created_at`, `select_date`, `pick_date` |
| `zone_type` | `zoneType` | `signal_type`, nested `zone.type`, setup family, engine |
| `zone_low` | `zoneLow` | `execution_zone_low`, `raw_zone_low`, `dz_low`, `lower`, nested `zone.zone_low/low`, `production_gate.zone_low` |
| `zone_high` | `zoneHigh` | `execution_zone_high`, `raw_zone_high`, `dz_high`, `upper`, nested `zone.zone_high/high`, `production_gate.zone_high` |
| `cost_line` | `costLine` | `smart_money_cost`, `v25_cost_line`, midpoint of zone, entry price |
| `smart_money_cost` | — | `cost_line`, `v25_cost_line`, zone midpoint, entry price |
| `volatility_pct` | `volatilityPct` | `v25_atr_pct`, `atr_pct`, `risk_pct`, `sl_initial_pct`, `v25_sl_pct` |
| `v25_vol_class` | `volClass` | `vol_class`, `market_state`, `regime`, `quality_tier`, formatted `RISK x.x%`, zone type |

## Required call sites

1. `get_all_picks_scoped()` / `_normalize_pick_scope()` — normalize raw picks once.
2. `/api/picks` route — after joining monitor position dates/status, run every row through `_apply_smc_field_contract()` again.
3. `/api/live-prices` — run each pick through `_apply_smc_field_contract()` before computing live status.
4. Monitor positions table — merge durable position + `raw_pick` before rendering:

```python
raw_pick = p.get('raw_pick') if isinstance(p.get('raw_pick'), dict) else {}
contracted = _apply_smc_field_contract({**raw_pick, **p}, default_engine=raw_pick.get('engine') or ACTIVE_VERSION)
```

5. Lightweight trade cache — keep flat contract fields in `lite_keys` so K-line/analysis pages do not lose them.

## UI requirement

For Lei's SMC dashboard, the monitor tables should be phone-readable and explicitly show these columns where relevant:

- Main picks: `代码`, `引擎`, `选股日期`, `加入日期`, `Zone`, `成本线`, `波动`.
- Daily-to-live monitor table: add `引擎` and `Zone`; do not leave these implied by category.
- Live page: `选股日`, `加入日`, `买入日`, `成本线`, `Zone`, `波动` must render from API aliases, not hand-built fallbacks only.

## V99 / chained daily-ops rerun pattern

When the field-contract bug appears after adding a new shadow gate above an existing production picker (for example V99 reading V98 outputs), fix both the frontend API contract and the daily task handoff:

1. Ensure the daily ops runner uses the newest gate's `*_active_picks.json` first, with fallback to the previous gate only if the new file is absent/empty.
2. Include the newest gate's active-picks/report files in `ops_latest.json` file metadata so `/live` and `/monitor` status lines expose the actual source that was regenerated.
3. Preserve `latest_market_date` / `latest_date` in the new gate report, copied from the upstream report when available; otherwise derive it from active pick dates.
4. Regenerate the upstream gate and downstream gate in the same daily ops run; if the upstream full gate is slow, run it as a tracked background process and verify final `exit_code=0`, not just that output files exist.
5. After restart, verify API and browser surfaces together. A valid fix has non-empty fields in `/api/picks`, `/api/live-prices`, `/monitor`, and `/live`.

## Re-execution / stale task-id pattern

When the user says a previous task ID keeps failing and repeats the concrete requirements, first treat the ID as context, not as the source of truth. Session IDs or stale process IDs may no longer be runnable. Do not spend the turn chasing an unavailable historical job if the requirement is clear; re-run the field-contract diagnosis against the live frontend/API and complete the requested fix directly.

Recommended sequence:

1. Inspect the current `/api/picks` and `/api/live-prices` payloads first, because the previous run may already have partially fixed the issue.
2. Verify the live browser pages (`/monitor`, `/live`) after the API check; many blank-cell reports are JS alias/rendering drift even when raw JSON has values.
3. If API values are already non-empty and browser values render correctly, report the verified state instead of making unnecessary code changes.
4. If fields are missing, patch the central `_apply_smc_field_contract()` / API payload construction, not only the HTML cell.

## Verification gate

After patching, restart the 8890 service and verify both API and browser surfaces. If no code change was needed because the field contract is already live-correct, still run the same verification gate and report the concrete zero-missing counts.

Programmatic gate:

```python
import json, urllib.request

def get(url):
    return json.loads(urllib.request.urlopen(url, timeout=30).read().decode())

picks = get('http://127.0.0.1:8890/api/picks')
live = get('http://127.0.0.1:8890/api/live-prices')['picks']

def empty(v): return v is None or v == '' or v == '-' or v == 0 or v == 0.0

pick_fields = [
    'pick_date','select_date','join_date','pickDate','joinDate','engine',
    'zone_type','zone_low','zone_high','cost_line','smart_money_cost',
    'volatility_pct','zoneType','zoneLow','zoneHigh','costLine','volClass'
]
live_fields = [
    'pickDate','joinDate','entryDate','zoneType','zoneLow','zoneHigh',
    'costLine','volClass','volatility_pct'
]

assert all(sum(1 for r in picks if empty(r.get(f))) == 0 for f in pick_fields)
assert all(sum(1 for r in live if empty(r.get(f))) == 0 for f in live_fields)
```

Browser gate:

- `/monitor` lower realtime-monitor table shows `引擎` and `Zone` values, not blanks.
- `/live` rows show non-empty `成本线`, `Zone`, and `波动`.

## Pitfalls

- Do not fix only the HTML table. Empty browser cells usually originate from API alias drift.
- Do not assume monitor positions contain all fields directly; most durable positions need `raw_pick` merged back in.
- Do not overwrite semantic values: fill missing aliases/fallbacks only.
- Do not use historical trades as current picks; preserve the current pick-scope contract.
- Browser JS must stringify object-valued fields before string methods. V90/V91 rows may carry `smc_dna` / `combo_contract` as `{}`; code like `(p.smc_dna || '-').replaceAll('_',' ')` breaks `/live`. Use `typeof value === 'string' ? value : JSON.stringify(value || '-')`.
- `WATCH_ONLY` / `WATCH_ONLY_CONTEXT` rows are non-tradable context. Dashboard/monitor/live labels must say `观察` / `上下文`, not `Active` / `有效选股` / `持仓`, and live summaries must count them separately from real OPEN/NEXT_DAY_PENDING positions.