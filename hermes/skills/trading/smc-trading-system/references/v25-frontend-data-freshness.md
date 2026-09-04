# V25 Frontend Data Freshness Architecture

## Problem (2026-05-18 audit)

`smc_unified.py` had 27 module-level `V*_TRADES` / `V*_PICKS` variables (lines 32-59)
loaded ONCE at startup, then NEVER refreshed. Every page that used them showed stale data:

| Page | Stale Source | Version Frozen |
|------|-------------|----------------|
| `/` Dashboard | `V24_TRADES` line 600 | V24 |
| `/monitor` | `V22_TRADES` line 744 | V22 (years old) |
| `/kline` trade API | `ver_map` of 12 V*_TRADES | V12-V21 mix |
| All pages | `reload_trades()` missing V25 | No V25 trades visible |

## Solution: Three-Part Fix

### 1. Remove all module-level stale variables (lines 32-59)
```
BEFORE: 27 variables (V9_TRADES through V24_TRADES, V9_PICKS through V24_PICKS)
AFTER:  Single _vdata() lazy-load helper + V18_IMPROV (static reference)
```

### 2. Per-request reload functions
```python
def _vdata(path, default=None):
    return load_json(Path(path), default or [])

def reload_trades():  # Prefers V25 → V24 → ... → V17
def reload_picks():   # Prefers V25 → V24 → ... → V17
```

### 3. All page builders use reloaded data
```python
# build_dashboard line 600:
trade_by_sym_dash = {t['symbol']: t for t in (trades or [])}  # was: V24_TRADES

# build_monitor line 744:
trade_by_sym = {t['symbol']: t for t in (reload_trades() or [])}  # was: V22_TRADES

# kline API line 1909: ver_map rebuilt per-request from disk
ver_map = {
    'V25': _vdata('/root/.hermes/smc_opt_v25/v25_trades.json'),
    'V24': _vdata('/root/.hermes/smc_opt_v24/v24_trades.json'),
    ...
}
```

## Force-Refresh Endpoint

`/api/reload` — forces reload of all data:
```python
elif path == '/api/reload':
    trades = reload_trades()
    picks = reload_picks()
    self._json({'status': 'reloaded', 'trades': len(trades), 'picks': len(picks)})
```

After `v25/full_scan.py` regenerates picks, hit `/api/reload` — all pages immediately see new data.

## Audit Checklist (for future frontend changes)

After any change to smc_unified.py:
- [ ] `grep -n 'V[0-9].*_TRADES\|V[0-9].*_PICKS' smc_unified.py` returns ZERO
- [ ] All `build_*()` functions use `reload_trades()`/`reload_picks()`, not module-level vars
- [ ] `reload_trades()` includes the current engine version first in its chain
- [ ] `/api/reload` endpoint responds correctly
- [ ] All 9 pages return valid HTML with fresh data

## Verification

```
curl -s http://localhost:8890/api/reload
→ {"status":"reloaded","trades":184,"picks":200}
```

All pages verified responding (2026-05-18):
Dashboard(10KB) Analysis(7KB) Backtest(93KB) Monitor(129KB) Live(13KB) 
Compare(75KB) Autopsy(5KB) LiveAPI(60p) ReloadAPI(184t/200p)
