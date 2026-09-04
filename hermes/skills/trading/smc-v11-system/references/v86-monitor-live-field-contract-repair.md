# V86 Monitor/Live Field Contract Repair — 选股页/实时页字段同步

## Trigger

Use this reference when `/monitor` or `/live` shows blanks for:

- 选股日期 / 加入日期
- 引擎 engine
- Zone / zone_type / zone_low / zone_high
- 成本线 costLine / cost_line / smart_money_cost
- 波动 volClass / vol_class / volatilityPct / volatility_pct

This applies especially when the active production version is V85/V86+ but live monitor positions still come from durable `smc_monitor/positions.json` rows whose `raw_pick` may use older V66/V25 field names.

## Durable lesson

Do not fix only the HTML table. The correct repair point is the cross-surface contract plus the API payload:

1. Normalize source rows with `_apply_smc_field_contract(row, default_engine)` before rendering.
2. Emit both snake_case and camelCase browser aliases.
3. For monitor positions, merge `raw_pick` and position fields before applying the contract.
4. Verify APIs first, then browser DOM.

## Minimal field contract

Every pick/live row should have non-empty values for:

```text
pick_date / pickDate
join_date / joinDate
engine
zone_type / zoneType
zone_low / zoneLow
zone_high / zoneHigh
cost_line / costLine / smart_money_cost
vol_class / volClass
volatility_pct / volatilityPct
```

## Key fallback chains

### Engine

```python
engine = row.get('engine') or raw_pick.get('engine') or row.get('source') or ACTIVE_VERSION
```

This prevents the lower monitor table from showing a blank engine when position rows only have `source` or `raw_pick.engine`.

### Zone

```python
zone_type = row.get('zone_type') or row.get('signal_type') or zone.get('type') or row.get('v59_setup_family') or engine
zone_low = row.get('zone_low') or row.get('execution_zone_low') or row.get('raw_zone_low') or row.get('dz_low') or gate.get('zone_low')
zone_high = row.get('zone_high') or row.get('execution_zone_high') or row.get('raw_zone_high') or row.get('dz_high') or gate.get('zone_high')
```

Display as:

```text
{zone_type}
[zone_low~zone_high]
```

not just `[low~high]`, otherwise the user sees `zone` semantics missing even if prices exist.

### Cost line

```python
smart_money_cost = cost_line or v25_cost_line or ((zone_low + zone_high) / 2 if zone_low and zone_high else entry_price)
cost_line = smart_money_cost or entry_price
```

Also emit browser aliases:

```python
costLine = cost_line
smart_money_cost = cost_line
```

### Volatility / wave class

```python
volatility_pct = v25_atr_pct or atr_pct or risk_pct or sl_initial_pct or v25_sl_pct or 0
v25_vol_class = vol_class or market_state or regime or quality_tier or f"RISK {volatility_pct:.1f}%" or zone_type
vol_class = v25_vol_class
volClass = vol_class
volatilityPct = volatility_pct
```

The missing `vol_class` snake_case alias is a common cause of API checks failing even when `volClass` renders in JS.

## Verification recipe

Run after patch + restart:

```python
import json, urllib.request
for url in ['http://127.0.0.1:8890/api/picks', 'http://127.0.0.1:8890/api/live-prices']:
    data = json.load(urllib.request.urlopen(url, timeout=30))
    rows = data if isinstance(data, list) else data.get('picks', [])
    fields = [
        'pick_date','pickDate','join_date','joinDate','engine','zone_type','zoneType',
        'cost_line','costLine','smart_money_cost','volClass','vol_class','volatility_pct'
    ]
    if 'live-prices' in url:
        fields += ['volatilityPct','zoneLow','zoneHigh']
    print(url, len(rows), {k: sum(1 for r in rows if r.get(k) in (None,'',0,0.0,[])) for k in fields})
```

Expected result: every listed field has `0` blanks.

Then verify DOM:

- `/monitor` headers include `选股日期`, `加入日期`, `引擎`, `Zone`, `成本线`, `波动`.
- `/monitor` lower monitor table shows engine and `ZoneType [low~high]`.
- `/live` headers include `选股日`, `加入日`, `成本线`, `Zone`, `波动`.
- `/live` rows show cost line and volatility class/percentage, not `-`.

## Pitfalls

- A blank field in the lower `/monitor` table may come from `smc_monitor/positions.json`, not from `v86_picks.json`; inspect/merge `raw_pick` with position data.
- `join_date` may come from `join_date`, `joined_at`, `created_at`, or monitor-state `joined_at`; normalize to an 8-digit date for API and short date for DOM.
- Do not only patch frontend JS fallbacks. If `/api/picks` or `/api/live-prices` still emits blanks, downstream pages and future checks will regress.
- Restart `smc_unified.py` after patching and verify with both API and browser snapshot; Python import tests alone do not prove live service state.
