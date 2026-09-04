# SMC Frontend Field Contract Alias Repair

Session date: 2026-06-13

## Trigger

Use when Lei reports that SMC frontend tables show blank values for:

- 选股日期 / 加入日期
- 引擎下面的 `zone`
- 实时页成本线
- 实时页波动
- API rows containing `zone_type`, `zone_low`, `zone_high`, `cost_line`, or `volatility_pct` but the browser still renders `-` or empty cells

## Root cause pattern

The backend often has correct canonical fields, but frontend/API consumers expect multiple legacy aliases. A field audit that only checks canonical names is insufficient.

Common mismatch:

| Canonical exists | Alias missing | Symptom |
|---|---|---|
| `pick_date` | `pickDate`, `selectDate`, `选股日期` | date column empty in one surface |
| `join_date` | `joinDate`, `加入日期` | join date empty |
| `zone_type`, `zone_low`, `zone_high` | `zone` | engine/zone cell shows empty or `-` |
| `cost_line` | `costLine`, `smart_money_cost` | cost line blank |
| `volatility_pct` | `volatility`, `volatilityPct`, `volClass` | volatility blank |

## Required repair pattern

1. Fix the shared normalizer first: `/root/.hermes/scripts/smc_unified.py::_apply_smc_field_contract()`.
2. Add aliases without changing row semantics:
   - `pickDate`, `selectDate`, `选股日期`
   - `joinDate`, `加入日期`
   - `zone = "{zone_low:.2f}~{zone_high:.2f}"` fallback to `zone_type`
   - `costLine`
   - `volatility`, `volatilityPct`, `volClass`
3. If a scanner writes frontend-facing JSON directly, also fix it at source so disk artifacts pass audit before the web server normalizes them. For V90 this was `/root/.hermes/scripts/v25/v90_daily_full_market_scanner.py`.
4. Extend tests to check both canonical fields and browser/API aliases.

## Verification commands

```bash
cd /root/.hermes/scripts/v25
python3 v90_daily_full_market_scanner.py
cd /root/.hermes/scripts
python3 -m py_compile smc_unified.py v25/v90_daily_full_market_scanner.py v25/test_v90_daily_full_market_scanner.py v25/smc_daily_ops.py
cd /root/.hermes/scripts/v25
python3 - <<'PY'
import test_v90_daily_full_market_scanner as t
for name in sorted(n for n in dir(t) if n.startswith('test_')):
    getattr(t,name)()
print('ALL PASS')
PY
```

After restarting 8890, verify both APIs with alias-level auditing:

```python
import urllib.request, json
for name, url in [('picks','http://127.0.0.1:8890/api/picks'), ('live','http://127.0.0.1:8890/api/live-prices')]:
    data = json.load(urllib.request.urlopen(url, timeout=20))
    rows = data if isinstance(data, list) else data.get('picks') or data.get('data') or data.get('rows') or []
    fields = ['pick_date','join_date','pickDate','joinDate','选股日期','加入日期','engine','zone','zone_type','cost_line','costLine','volatility','volatility_pct','volatilityPct','vol_class','volClass']
    misses = {f: sum(1 for r in rows if r.get(f) in (None, '', [], {})) for f in fields}
    assert all(v == 0 for v in misses.values()), (name, misses)
```

## Acceptance gate

Do not claim the repair is complete until all pass:

| Surface | Required |
|---|---|
| scanner report | `field_audit_recent` and `field_audit_all` are all zero, including `zone` and `volatility` |
| `/api/picks` | 0 blanks for canonical + alias fields |
| `/api/live-prices` | 0 blanks for canonical + alias fields |
| browser `/monitor` | visible `选股日期/加入日期/Zone/成本线/波动` populated |
| browser `/live` | visible `选股日/加入日/成本线/Zone/波动` populated |

## Pitfall

A row can pass canonical backend audit while still failing the browser. Always audit the exact fields the frontend reads, not only the engine-native schema.
