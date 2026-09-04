# V144/V145 Shadow Dry-Run Read-Only Preview Route Verification

Use this when exposing shadow/backtest rows to the SMC UI/API without promoting them to production.

## Pattern

- Add a dedicated read-only preview endpoint instead of merging rows into production surfaces:
  - `GET /api/v144-dry-run-preview?scope=latest_per_symbol|recent45|all`
- The endpoint may read shadow audit JSON files and apply display field normalization, but must not write or mutate:
  - `/api/picks`
  - `/api/live-prices`
  - watchlist / monitor state
  - morning push artifacts
  - production version/config
- Every preview row must remain display-only:
  - `shadow_only=true`
  - `production_write=false` when present
  - `trade_action=NO_BUY`
  - no BUY/OPEN/NEXT_DAY_PENDING-like status
- Do not leak outcome fields into preview rows used for UI display/selection contracts:
  - `net_pnl_pct`, `pnl_pct`, `exit_reason`, `exit_date`, `won`, `tp_hit`, `sl_hit`, `mfe_pct`, `mae_pct`

## Verification checklist

Run a post-change probe that checks all surfaces in one pass:

| Check | Expected |
|---|---:|
| `python3 -m py_compile smc_unified.py` | PASS |
| `/api/summary` version/engine | unchanged production version |
| `/api/picks` V144 rows | 0 |
| `/api/picks` BUY-like rows | 0 unless production already has valid active buys |
| `/api/live-prices` V144 rows | 0 |
| `/api/live-prices` BUY-like rows | 0 unless production already has valid active buys |
| preview rows | non-zero if audit JSON exists |
| preview `shadow_only` | all rows |
| preview `trade_action=NO_BUY` | all rows |
| preview outcome leak | 0 |

## Minimal probe

```python
import json, urllib.request
base='http://127.0.0.1:8890'

def get(path):
    with urllib.request.urlopen(base+path, timeout=30) as r:
        return json.loads(r.read().decode())

def rows(obj):
    return obj if isinstance(obj, list) else obj.get('picks') or obj.get('rows') or []

def has_shadow_version(r, version='V144'):
    txt=' '.join(str(r.get(k,'')) for k in ['engine','source','version','shadow_engine','display_engine','trade_action','production_version'])
    return version in txt

def buy_like(r):
    return str(r.get('trade_action') or r.get('action') or r.get('monitor_status') or r.get('status') or '').upper() in {'BUY','OPEN','NEXT_DAY_PENDING'}

def outcome_leak(r):
    leak_keys={'net_pnl_pct','pnl_pct','exit_reason','exit_date','won','tp_hit','sl_hit','mfe_pct','mae_pct'}
    return any(k in r and r.get(k) not in (None,'') for k in leak_keys)

summary=get('/api/summary')
picks=rows(get('/api/picks'))
live=rows(get('/api/live-prices'))
preview=rows(get('/api/v144-dry-run-preview?scope=latest_per_symbol'))
print(json.dumps({
  'summary_version': summary.get('version'),
  'summary_engine': summary.get('engine'),
  'picks_shadow_count': sum(has_shadow_version(r) for r in picks),
  'picks_buy_like_count': sum(buy_like(r) for r in picks),
  'live_shadow_count': sum(has_shadow_version(r) for r in live),
  'live_buy_like_count': sum(buy_like(r) for r in live),
  'preview_count': len(preview),
  'preview_shadow_only': sum(bool(r.get('shadow_only')) for r in preview),
  'preview_no_buy': sum(str(r.get('trade_action','')).upper()=='NO_BUY' for r in preview),
  'preview_buy_like': sum(buy_like(r) for r in preview),
  'preview_outcome_leak': sum(outcome_leak(r) for r in preview),
}, ensure_ascii=False, indent=2))
```

## Concrete verified example

2026-06-21 verification after adding `/api/v144-dry-run-preview`:

- production stayed `V102 / V102_BALANCED_VOLUME_GATE`
- `/api/picks`: 49 rows, V144 pollution 0, BUY-like 0
- `/api/live-prices`: 5 rows, V144 pollution 0, BUY-like 0
- preview rows: `latest_per_symbol=265`, `recent45=30`, `all=273`
- preview latest rows: `shadow_only=265/265`, `NO_BUY=265/265`, BUY-like 0, outcome leak 0

Conclusion: shadow UI/API preview can be added safely only when the production surfaces remain unchanged and the preview contract proves display-only/no-buy/no-outcome-leak semantics.
