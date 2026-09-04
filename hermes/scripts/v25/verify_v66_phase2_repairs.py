#!/usr/bin/env python3
"""Regression checks for V66 Phase2 repairs.
Run before and after fixes. Exits non-zero when any hard invariant fails.
"""
import json
import sys
import urllib.request
from pathlib import Path
from collections import Counter

ROOT = Path('/root/.hermes')

def load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return default

def f(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0

def blank(v):
    return v in (None, '', 0, '0', '-')

def date_key(v):
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''

def check_pick_file(path, latest_only=False):
    rows = load(path, [])
    if latest_only and rows:
        latest = max(date_key(r.get('pick_date') or r.get('entry_date')) for r in rows)
        rows = [r for r in rows if date_key(r.get('pick_date') or r.get('entry_date')) == latest]
    active = [r for r in rows if r.get('is_active_pick') and r.get('pick_scope') in ('ACTIVE_CANDIDATE', 'ACTIVE_ENTRY')]
    issues = Counter()
    for r in active:
        entry = f(r.get('entry_price') or r.get('price'))
        sl = f(r.get('sl') or r.get('v25_sl_price'))
        zl = f(r.get('zone_low') or r.get('dz_low'))
        zh = f(r.get('zone_high') or r.get('dz_high'))
        if not (r.get('zone_type') and zl and zh): issues['blank_zone'] += 1
        if blank(r.get('pick_date') or r.get('select_date')): issues['blank_pick_date'] += 1
        if blank(r.get('join_date') or r.get('pick_date') or r.get('select_date')): issues['blank_join_date'] += 1
        if blank(r.get('cost_line') or r.get('smart_money_cost') or r.get('v25_cost_line')): issues['blank_cost'] += 1
        if blank(r.get('volatility_pct') or r.get('risk_pct') or r.get('v25_sl_pct') or r.get('v25_vol_class')): issues['blank_vol'] += 1
        if entry and sl and entry <= sl: issues['entry_le_sl'] += 1
        if entry and zl and entry < zl: issues['entry_below_zone'] += 1
        if entry and zh and entry > zh * 1.008: issues['entry_too_far_above_zone'] += 1
        if str(r.get('market_state')) in ('RANGE', 'HIGH_VOL', 'UNDEFINED'): issues['bad_market_state_active'] += 1
        if str(r.get('zone_type')) == 'FVG_Bull' and r.get('sweep_tag') != 'SWEEP_TO_STRUCTURE': issues['fvg_without_sweep_active'] += 1
        if f(r.get('retrace_depth_pct') or r.get('retrace_pct')) > 70: issues['deep_retrace_active'] += 1
        # SL should be below zone low and not the exact hard-floor bug for all rows
        if sl and zl and abs(sl - zl * 0.995) / max(zl, 1e-9) < 0.001: issues['sl_exact_zone_floor'] += 1
    return {'path': str(path), 'rows': len(rows), 'active': len(active), 'issues': dict(issues), 'zone_counts': dict(Counter(r.get('zone_type') for r in active)), 'state_counts': dict(Counter(r.get('market_state') for r in active))}

def check_api(path):
    try:
        data = json.loads(urllib.request.urlopen('http://127.0.0.1:8890' + path, timeout=20).read().decode())
    except Exception as e:
        return {'path': path, 'error': str(e)}
    rows = data.get('picks', data if isinstance(data, list) else []) if isinstance(data, dict) else data
    issues = Counter()
    for r in rows:
        if path == '/api/picks':
            if blank(r.get('pick_date') or r.get('select_date')): issues['blank_pick_date'] += 1
            if blank(r.get('join_date')): issues['blank_join_date'] += 1
            if blank(r.get('zone_type')) and not (r.get('zone_low') and r.get('zone_high')): issues['blank_zone'] += 1
            if blank(r.get('cost_line') or r.get('smart_money_cost') or r.get('v25_cost_line')): issues['blank_cost'] += 1
            if blank(r.get('volatility_pct') or r.get('risk_pct') or r.get('v25_sl_pct') or r.get('v25_vol_class')): issues['blank_vol'] += 1
        else:
            if blank(r.get('pickDate') or r.get('pick_date')): issues['blank_pickDate'] += 1
            if blank(r.get('joinDate') or r.get('join_date')): issues['blank_joinDate'] += 1
            if blank(r.get('zoneType') or r.get('zone_type')) and not (r.get('zoneLow') and r.get('zoneHigh')): issues['blank_zone'] += 1
            if blank(r.get('costLine') or r.get('cost_line')): issues['blank_cost'] += 1
            if blank(r.get('volClass') or r.get('volatility_pct')): issues['blank_vol'] += 1
    return {'path': path, 'rows': len(rows), 'issues': dict(issues), 'sample': rows[:3]}

def main():
    report = {
        'v25_latest': check_pick_file(ROOT/'smc_opt_v25/v26_picks.json', latest_only=True),
        'v66': check_pick_file(ROOT/'smc_opt_v66/v66_picks.json', latest_only=False),
        'api_picks': check_api('/api/picks'),
        'api_live': check_api('/api/live-prices'),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    hard = Counter()
    for section in ('v25_latest', 'v66'):
        for k, v in report[section].get('issues', {}).items():
            if k in ('blank_zone','blank_pick_date','blank_join_date','blank_cost','blank_vol','entry_le_sl','entry_below_zone','bad_market_state_active','fvg_without_sweep_active'):
                hard[f'{section}.{k}'] += v
    for section in ('api_picks', 'api_live'):
        for k, v in report[section].get('issues', {}).items():
            if k.startswith('blank'):
                hard[f'{section}.{k}'] += v
    if hard:
        print('HARD_FAILURES=' + json.dumps(dict(hard), ensure_ascii=False), file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
