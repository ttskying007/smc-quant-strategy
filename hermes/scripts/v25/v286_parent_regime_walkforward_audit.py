#!/usr/bin/env python3
"""V286 no-write: parent-regime walk-forward selector for V280 SMC time grammars.

Question: V285 showed per-stock DNA does not generalize. Test the next
architecture: use only entry-before market/industry participation plus SMC grammar
attributes as a parent selector, trained on prior years only, then validate on
2024-2026. No production/frontend/watchlist writes.
"""
from __future__ import annotations

import bisect
import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
KDIR = BASE / 'kline_cache'
EVENTS = AUDIT / 'v280_layered_state_grammar_no_write_20260702_205055/v280_events.csv'
INDMAP = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v286_parent_regime_walkforward_no_write_{TS}'
LATEST = AUDIT / 'v286_parent_regime_walkforward_latest.json'
TEST_YEARS = ['2024', '2025', '2026']
ALL_YEARS = ['2023', '2024', '2025', '2026']


def sf(x: Any, d: float = math.nan) -> float:
    try:
        if x is None or x == '':
            return d
        v = float(x)
        return v if not math.isnan(v) else d
    except Exception:
        return d


def dn(x: Any) -> str:
    s = ''.join(ch for ch in str(x or '').replace('-', '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def symbol_from_path(p: Path) -> str:
    stem = p.stem.replace('_daily_750', '')
    code, exch = stem.split('_', 1)
    return f'{code}.{exch}'


def load_industry_map() -> dict[str, str]:
    items = json.loads(INDMAP.read_text())
    return {r['symbol']: r.get('industry') or 'UNKNOWN' for r in items if r.get('symbol')}


def build_prev_features(sym_ind: dict[str, str]):
    daily: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    ind_daily: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for fp in KDIR.glob('*_daily_750.json'):
        try:
            sym = symbol_from_path(fp)
        except Exception:
            continue
        ind = sym_ind.get(sym)
        if not ind:
            continue
        try:
            bars = json.loads(fp.read_text())
        except Exception:
            continue
        seq = []
        for b in bars:
            d = dn(b.get('t') or b.get('date'))
            c = sf(b.get('c'))
            if d and not math.isnan(c):
                seq.append((d, c))
        seq.sort()
        for i in range(1, len(seq)):
            d, c = seq[i]
            pc = seq[i - 1][1]
            if pc > 0:
                ret = (c / pc - 1) * 100
                daily[d].append((sym, ind, ret))
                ind_daily[d][ind].append(ret)
    dates = sorted(daily)
    mkt = {}
    indf = {}
    for d, rows in daily.items():
        vals = [x[2] for x in rows]
        mkt[d] = {
            'mkt_n': len(vals),
            'mkt_up_pct': sum(v > 0 for v in vals) / len(vals) * 100,
            'mkt_med_ret': median(vals),
            'mkt_strong1_pct': sum(v > 1 for v in vals) / len(vals) * 100,
        }
    for d, by_ind in ind_daily.items():
        for ind, vals in by_ind.items():
            if len(vals) < 5:
                continue
            indf[(d, ind)] = {
                'ind_n': len(vals),
                'ind_up_pct': sum(v > 0 for v in vals) / len(vals) * 100,
                'ind_med_ret': median(vals),
                'ind_strong1_pct': sum(v > 1 for v in vals) / len(vals) * 100,
            }

    def prev_date(d: str) -> str:
        i = bisect.bisect_left(dates, d) - 1
        return dates[i] if i >= 0 else ''

    return prev_date, mkt, indf


def b_ret(x: float) -> str:
    if math.isnan(x): return 'RET_NA'
    if x < -1: return 'RET<-1'
    if x < 0: return 'RET_-1_0'
    if x < 1: return 'RET_0_1'
    return 'RET>=1'


def b_up(x: float) -> str:
    if math.isnan(x): return 'UP_NA'
    if x < 35: return 'UP<35'
    if x < 50: return 'UP35_50'
    if x < 65: return 'UP50_65'
    return 'UP>=65'


def b_rel(x: float) -> str:
    if math.isnan(x): return 'REL_NA'
    if x < -10: return 'REL<-10'
    if x < 0: return 'REL_-10_0'
    if x < 10: return 'REL_0_10'
    return 'REL>=10'


def b_risk(x: float) -> str:
    if math.isnan(x): return 'RISK_NA'
    if x < 2: return 'RISK<2'
    if x < 4: return 'RISK2_4'
    if x < 6: return 'RISK4_6'
    if x < 8: return 'RISK6_8'
    return 'RISK>=8'


def b_liq(x: float) -> str:
    if math.isnan(x) or x >= 900: return 'LIQ_NA'
    if x <= 3: return 'LIQ<=3'
    if x <= 8: return 'LIQ4_8'
    if x <= 20: return 'LIQ9_20'
    return 'LIQ>20'


def b_rng(x: float) -> str:
    if math.isnan(x): return 'RNG_NA'
    if x < 15: return 'RNG<15'
    if x < 25: return 'RNG15_25'
    return 'RNG>=25'


def blank() -> dict[str, Any]:
    return {'n': 0, 'wins': 0, 'sum': 0.0, 'loss': 0, 'tp': 0, 'sl': 0, 'time': 0,
            'micro': 0, 'years': defaultdict(lambda: [0, 0]), 'symbols': set()}


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'), 0.0)
    y = str(r.get('year') or dn(r.get('entry_date'))[:4])
    reason = str(r.get('reason') or '')
    a['n'] += 1
    a['wins'] += pnl > 0
    a['sum'] += pnl
    a['loss'] += pnl <= 0
    a['tp'] += reason == 'TP'
    a['sl'] += reason == 'SL'
    a['time'] += reason.startswith('TIME')
    a['micro'] += 0 < pnl < 1
    a['years'][y][0] += 1
    a['years'][y][1] += pnl > 0
    a['symbols'].add(r.get('symbol', ''))


def merge(dst: dict[str, Any], src: dict[str, Any]) -> None:
    dst['n'] += src['n']; dst['wins'] += src['wins']; dst['sum'] += src['sum']
    dst['loss'] += src['loss']; dst['tp'] += src['tp']; dst['sl'] += src['sl']
    dst['time'] += src['time']; dst['micro'] += src['micro']; dst['symbols'].update(src['symbols'])
    for y, v in src['years'].items():
        dst['years'][y][0] += v[0]; dst['years'][y][1] += v[1]


def metrics(a: dict[str, Any]) -> dict[str, Any]:
    n = int(a['n'])
    if not n:
        return {'n': 0}
    yc = {y: int(v[0]) for y, v in sorted(a['years'].items()) if v[0]}
    ywr = {y: round(v[1] / v[0] * 100, 2) for y, v in sorted(a['years'].items()) if v[0]}
    return {
        'n': n,
        'wr': round(a['wins'] / n * 100, 4),
        'avg': round(a['sum'] / n, 4),
        'loss': int(a['loss']),
        'micro': round(a['micro'] / n * 100, 2),
        'tp_pct': round(a['tp'] / n * 100, 2),
        'sl_pct': round(a['sl'] / n * 100, 2),
        'time_pct': round(a['time'] / n * 100, 2),
        'symbols': len(a['symbols']),
        'yc': yc,
        'ywr': ywr,
        'min_year_n': min(yc.values()) if yc else 0,
        'minwr': round(min(ywr.values()) if ywr else 0, 2),
    }


def enrich_rows() -> list[dict[str, Any]]:
    sym_ind = load_industry_map()
    prev_date, mkt, indf = build_prev_features(sym_ind)
    rows = []
    with EVENTS.open(newline='') as f:
        for r in csv.DictReader(f):
            if r.get('year') not in set(ALL_YEARS):
                continue
            sym = r['symbol']
            d = dn(r.get('entry_date'))
            ind = sym_ind.get(sym, 'UNKNOWN')
            pd = prev_date(d)
            nr = dict(r)
            nr['industry'] = ind
            nr['prev_date'] = pd
            for k, v in mkt.get(pd, {}).items(): nr['prev_' + k] = v
            for k, v in indf.get((pd, ind), {}).items(): nr['prev_' + k] = v
            nr['prev_ind_vs_mkt_up'] = sf(nr.get('prev_ind_up_pct')) - sf(nr.get('prev_mkt_up_pct'))
            nr['prev_ind_vs_mkt_med_ret'] = sf(nr.get('prev_ind_med_ret')) - sf(nr.get('prev_mkt_med_ret'))
            rows.append(nr)
    return rows


def row_keys(r: dict[str, Any]) -> list[tuple[str, str]]:
    fam = r['family']; reg = r['regime']
    mret = b_ret(sf(r.get('prev_mkt_med_ret'))); iret = b_ret(sf(r.get('prev_ind_med_ret')))
    mup = b_up(sf(r.get('prev_mkt_up_pct'))); iup = b_up(sf(r.get('prev_ind_up_pct')))
    relret = b_rel(sf(r.get('prev_ind_vs_mkt_med_ret'))); relup = b_rel(sf(r.get('prev_ind_vs_mkt_up')))
    risk = b_risk(sf(r.get('risk'))); liq = b_liq(sf(r.get('liq_age'))); rng = b_rng(sf(r.get('range60')))
    vol = r.get('vol_env') or 'VOLENV_NA'
    return [
        ('family', fam),
        ('family_regime', f'{fam}|{reg}'),
        ('parent_mkt_ind_family', f'{mret}|{iret}|{fam}'),
        ('parent_mkt_ind_family_regime', f'{mret}|{iret}|{fam}|{reg}'),
        ('parent_up_family_regime', f'{mup}|{iup}|{fam}|{reg}'),
        ('parent_rel_family_regime', f'{mret}|{relret}|{fam}|{reg}'),
        ('parent_full_family_regime', f'{mret}|{iret}|{mup}|{iup}|{fam}|{reg}'),
        ('parent_mkt_ind_family_regime_risk', f'{mret}|{iret}|{fam}|{reg}|{risk}'),
        ('parent_mkt_ind_family_regime_liq', f'{mret}|{iret}|{fam}|{reg}|{liq}'),
        ('parent_mkt_ind_family_regime_range', f'{mret}|{iret}|{fam}|{reg}|{rng}'),
        ('parent_mkt_ind_family_regime_vol', f'{mret}|{iret}|{fam}|{reg}|{vol}'),
    ]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = enrich_rows()
    baseline_all = blank(); baseline_test = blank()
    by_key_year: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(blank)
    key_cache = []
    for r in rows:
        add(baseline_all, r)
        if r['year'] in TEST_YEARS:
            add(baseline_test, r)
        keys = row_keys(r)
        key_cache.append(keys)
        for dim, val in keys:
            add(by_key_year[(dim, val, r['year'])], r)

    grids = [
        {'name': 'loose_parent_n100_wr50_avgpos', 'min_n': 100, 'min_wr': 50.0, 'min_avg': 0.0, 'min_train_year_n': 30},
        {'name': 'balanced_parent_n200_wr52_avg05', 'min_n': 200, 'min_wr': 52.0, 'min_avg': 0.5, 'min_train_year_n': 50},
        {'name': 'strict_parent_n300_wr55_avg1', 'min_n': 300, 'min_wr': 55.0, 'min_avg': 1.0, 'min_train_year_n': 80},
        {'name': 'stability_parent_n150_minyr48', 'min_n': 150, 'min_wr': 50.0, 'min_avg': 0.0, 'min_train_year_n': 40, 'min_train_minwr': 48.0},
    ]

    def train_rules(test_year: str, grid: dict[str, Any]) -> set[tuple[str, str]]:
        train_years = [y for y in ['2023', '2024', '2025'] if y < test_year]
        candidates: dict[tuple[str, str], dict[str, Any]] = defaultdict(blank)
        for (dim, val, y), a in by_key_year.items():
            if y in train_years:
                merge(candidates[(dim, val)], a)
        selected = []
        for key, a in candidates.items():
            m = metrics(a)
            if m['n'] < grid['min_n'] or m['wr'] < grid['min_wr'] or m['avg'] < grid['min_avg']:
                continue
            if m['min_year_n'] < grid['min_train_year_n']:
                continue
            if m['minwr'] < grid.get('min_train_minwr', 0):
                continue
            score = (m['minwr'], m['avg'], m['wr'], math.log1p(m['n']))
            selected.append((score, key, m))
        selected.sort(reverse=True)
        # cap rules to avoid turning the selector into a broad whitelist.
        return {key for _, key, _ in selected[:20]}

    summaries = []
    selected_path = OUT / 'v286_selected_rows.csv'
    fieldnames = list(rows[0].keys()) + ['grid', 'selected_dim', 'selected_value']
    with selected_path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for grid in grids:
            agg = blank(); by_year = {y: blank() for y in TEST_YEARS}; selected_counts = {}
            for test_year in TEST_YEARS:
                rules = train_rules(test_year, grid)
                selected_counts[test_year] = len(rules)
                for r, keys in zip(rows, key_cache):
                    if r['year'] != test_year:
                        continue
                    hit = next(((d, v) for d, v in keys if (d, v) in rules), None)
                    if not hit:
                        continue
                    add(agg, r); add(by_year[test_year], r)
                    out = dict(r); out.update({'grid': grid['name'], 'selected_dim': hit[0], 'selected_value': hit[1]})
                    writer.writerow(out)
            summaries.append({
                'grid': grid,
                'selected_rules_by_test_year': selected_counts,
                'walk_forward': metrics(agg),
                'by_test_year': {y: metrics(by_year[y]) for y in TEST_YEARS},
            })

    # Also rank non-walk-forward dimensions on test years as diagnostic ceiling, not production proof.
    diag = defaultdict(blank)
    for r, keys in zip(rows, key_cache):
        if r['year'] not in TEST_YEARS:
            continue
        for dim, val in keys:
            add(diag[(dim, val)], r)
    diag_rows = []
    for (dim, val), a in diag.items():
        m = metrics(a)
        if m['n'] >= 100:
            diag_rows.append({'dimension': dim, 'value': val, **m})
    diag_rows.sort(key=lambda x: (x['minwr'], x['wr'], x['avg'], x['n']), reverse=True)

    summary = {
        'version': 'V286_PARENT_REGIME_WALKFORWARD_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'inputs': {'events': str(EVENTS), 'industry_map': str(INDMAP), 'rows': len(rows)},
        'raw_all': metrics(baseline_all),
        'raw_test_2024_2026': metrics(baseline_test),
        'walk_forward_parent_selectors': summaries,
        'diagnostic_best_test_dimensions': diag_rows[:30],
        'artifacts': {'selected_rows': str(selected_path), 'summary': str(OUT / 'v286_summary.json')},
    }
    (OUT / 'v286_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    with (OUT / 'v286_diagnostic_dimensions.csv').open('w', newline='') as f:
        fields = ['dimension', 'value', 'n', 'wr', 'avg', 'min_year_n', 'minwr', 'tp_pct', 'sl_pct', 'time_pct', 'symbols', 'yc', 'ywr']
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in diag_rows[:500]:
            w.writerow({k: r.get(k) for k in fields})
    print(json.dumps({'latest': str(LATEST), 'out': str(OUT), 'raw_test': summary['raw_test_2024_2026'], 'selectors': summaries, 'top_diag': diag_rows[:5]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
