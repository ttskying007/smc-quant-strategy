#!/usr/bin/env python3
"""V287 no-write: focused audit of V286's strongest parent-regime pocket.

V286 showed that broad walk-forward parent selectors still fail in 2026, but a
specific diagnostic pocket is repeatedly strong: UP_CONT_BOS_OB in DOWN regime
when previous-day market and industry participation are both strong. This script
freezes that hypothesis and decomposes it by year/month/exit/industry without
production writes.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
V286 = BASE / 'scripts/v25/v286_parent_regime_walkforward_audit.py'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v287_strong_participation_upcont_pocket_no_write_{TS}'
LATEST = AUDIT / 'v287_strong_participation_upcont_pocket_latest.json'

spec = importlib.util.spec_from_file_location('v286_mod', V286)
v286 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v286)  # type: ignore[union-attr]


def sf(x: Any, d: float = math.nan) -> float:
    return v286.sf(x, d)


def year_month(d: str) -> str:
    s = v286.dn(d)
    return s[:6] if len(s) >= 6 else ''


def blank() -> dict[str, Any]:
    return {'n': 0, 'wins': 0, 'sum': 0.0, 'loss': 0, 'tp': 0, 'sl': 0, 'time': 0,
            'micro': 0, 'years': defaultdict(lambda: [0, 0]), 'symbols': set(),
            'months': defaultdict(lambda: [0, 0, 0.0]), 'industries': defaultdict(lambda: [0, 0, 0.0])}


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'), 0.0)
    y = str(r.get('year') or v286.dn(r.get('entry_date'))[:4])
    m = year_month(str(r.get('entry_date')))
    ind = str(r.get('industry') or 'UNKNOWN')
    reason = str(r.get('reason') or '')
    a['n'] += 1; a['wins'] += pnl > 0; a['sum'] += pnl; a['loss'] += pnl <= 0
    a['tp'] += reason == 'TP'; a['sl'] += reason == 'SL'; a['time'] += reason.startswith('TIME')
    a['micro'] += 0 < pnl < 1; a['symbols'].add(r.get('symbol',''))
    a['years'][y][0] += 1; a['years'][y][1] += pnl > 0
    a['months'][m][0] += 1; a['months'][m][1] += pnl > 0; a['months'][m][2] += pnl
    a['industries'][ind][0] += 1; a['industries'][ind][1] += pnl > 0; a['industries'][ind][2] += pnl


def metrics(a: dict[str, Any]) -> dict[str, Any]:
    n = int(a['n'])
    if n == 0: return {'n': 0}
    yc = {y: int(v[0]) for y, v in sorted(a['years'].items()) if v[0]}
    ywr = {y: round(v[1] / v[0] * 100, 2) for y, v in sorted(a['years'].items()) if v[0]}
    months = []
    for m, v in sorted(a['months'].items()):
        if v[0]: months.append({'month': m, 'n': int(v[0]), 'wr': round(v[1]/v[0]*100,2), 'avg': round(v[2]/v[0],3)})
    inds = []
    for ind, v in a['industries'].items():
        if v[0] >= 5: inds.append({'industry': ind, 'n': int(v[0]), 'wr': round(v[1]/v[0]*100,2), 'avg': round(v[2]/v[0],3)})
    inds.sort(key=lambda x: (x['n'], x['avg']), reverse=True)
    bad_months = [x for x in months if x['n'] >= 5 and x['wr'] < 45]
    return {'n': n, 'wr': round(a['wins']/n*100,4), 'avg': round(a['sum']/n,4), 'loss': int(a['loss']),
            'micro': round(a['micro']/n*100,2), 'tp_pct': round(a['tp']/n*100,2),
            'sl_pct': round(a['sl']/n*100,2), 'time_pct': round(a['time']/n*100,2),
            'symbols': len(a['symbols']), 'yc': yc, 'ywr': ywr,
            'min_year_n': min(yc.values()) if yc else 0, 'minwr': round(min(ywr.values()) if ywr else 0,2),
            'monthly': months, 'bad_months_n_ge_5': bad_months, 'top_industries': inds[:20]}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = v286.enrich_rows()

    def strong_mkt_ind(r): return sf(r.get('prev_mkt_med_ret')) >= 1 and sf(r.get('prev_ind_med_ret')) >= 1
    def euphoric_breadth(r): return sf(r.get('prev_mkt_up_pct')) >= 65 and sf(r.get('prev_ind_up_pct')) >= 65
    def upcont_down(r): return r['family'] == 'UP_CONT_BOS_OB' and r['regime'] == 'DOWN'
    def risk8(r): return sf(r.get('risk')) >= 8
    def rng25(r): return sf(r.get('range60')) >= 25
    def highvol(r): return r.get('vol_env') == 'HIGH_VOL'
    def rel_0_10(r):
        x = sf(r.get('prev_ind_vs_mkt_med_ret'))
        return 0 <= x < 10

    rules: list[tuple[str, Callable[[dict[str, Any]], bool]]] = [
        ('BASE_all_V280', lambda r: True),
        ('ABSORB_DOWN_STRONG_MKT_IND', lambda r: r['family']=='ABSORB_SSL_FAST_MSS' and r['regime']=='DOWN' and strong_mkt_ind(r)),
        ('UPCONT_DOWN_STRONG_MKT_IND', lambda r: upcont_down(r) and strong_mkt_ind(r)),
        ('UPCONT_DOWN_STRONG_MKT_IND_RISK8', lambda r: upcont_down(r) and strong_mkt_ind(r) and risk8(r)),
        ('UPCONT_DOWN_STRONG_MKT_IND_RISK8_RNG25', lambda r: upcont_down(r) and strong_mkt_ind(r) and risk8(r) and rng25(r)),
        ('UPCONT_DOWN_STRONG_MKT_IND_RISK8_EUPHORIA', lambda r: upcont_down(r) and strong_mkt_ind(r) and risk8(r) and euphoric_breadth(r)),
        ('UPCONT_DOWN_STRONG_MKT_IND_RISK8_REL0_10', lambda r: upcont_down(r) and strong_mkt_ind(r) and risk8(r) and rel_0_10(r)),
        ('UPCONT_DOWN_STRONG_MKT_IND_HIGHVOL', lambda r: upcont_down(r) and strong_mkt_ind(r) and highvol(r)),
    ]
    out_rules = []
    rows_csv = OUT / 'v287_rule_rows.csv'
    with rows_csv.open('w', newline='') as f:
        fieldnames = list(rows[0].keys()) + ['rule']
        w = csv.DictWriter(f, fieldnames=fieldnames); w.writeheader()
        for name, pred in rules:
            a = blank()
            for r in rows:
                if pred(r):
                    add(a, r)
                    if name != 'BASE_all_V280':
                        rr = dict(r); rr['rule'] = name; w.writerow(rr)
            out_rules.append({'rule': name, **metrics(a)})

    # test-period only scoreboard, because V286 diagnostic ranking was 2024-2026.
    test_rules = []
    for name, pred in rules[1:]:
        a = blank()
        for r in rows:
            if r.get('year') in {'2024','2025','2026'} and pred(r):
                add(a, r)
        test_rules.append({'rule': name, **metrics(a)})
    test_rules.sort(key=lambda x: (x['minwr'], x['wr'], x['avg'], x['n']), reverse=True)

    summary = {'version': 'V287_STRONG_PARTICIPATION_UPCONT_POCKET_NO_WRITE',
               'generated_at': datetime.now().isoformat(timespec='seconds'),
               'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
               'source': str(V286), 'rules_all_years': out_rules, 'rules_test_2024_2026_ranked': test_rules,
               'artifacts': {'rule_rows': str(rows_csv), 'summary': str(OUT / 'v287_summary.json')}}
    (OUT / 'v287_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'latest': str(LATEST), 'out': str(OUT), 'test_ranked': test_rules[:6]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
