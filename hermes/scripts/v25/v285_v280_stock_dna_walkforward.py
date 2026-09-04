#!/usr/bin/env python3
"""V285 no-write: stock-DNA walk-forward selector on V280 temporal grammar events.

Question: if SMC primitives are assumed correct, is opportunity scarcity mainly a
fixed chronological-combo problem?  Use V280's multi-family time-ordered events
and test whether per-stock DNA (learned from prior years only) can select a
family/parameter pocket with materially better coverage/quality.

No production/frontend/watchlist writes.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
EVENTS = AUDIT / 'v280_layered_state_grammar_no_write_20260702_205055/v280_events.csv'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v285_v280_stock_dna_walkforward_no_write_{TS}'
LATEST = AUDIT / 'v285_v280_stock_dna_walkforward_latest.json'
TEST_YEARS = ['2024', '2025', '2026']


def sf(x: Any, d: float = math.nan) -> float:
    try:
        if x is None or x == '':
            return d
        v = float(x)
        return v if not math.isnan(v) else d
    except Exception:
        return d


def bucket_risk(x: float) -> str:
    if math.isnan(x): return 'RISK_NA'
    if x < 2: return 'RISK<2'
    if x < 4: return 'RISK2_4'
    if x < 6: return 'RISK4_6'
    if x < 8: return 'RISK6_8'
    return 'RISK>=8'


def bucket_liq(x: float) -> str:
    if math.isnan(x) or x >= 900: return 'LIQ_NA'
    if x <= 0: return 'LIQ0'
    if x <= 3: return 'LIQ1_3'
    if x <= 8: return 'LIQ4_8'
    if x <= 20: return 'LIQ9_20'
    return 'LIQ>20'


def bucket_delay(x: float) -> str:
    if math.isnan(x): return 'DLY_NA'
    if x <= 0: return 'DLY0'
    if x <= 1: return 'DLY1'
    if x <= 3: return 'DLY2_3'
    return 'DLY>3'


def bucket_range(x: float) -> str:
    if math.isnan(x): return 'RNG_NA'
    if x < 15: return 'RNG<15'
    if x < 25: return 'RNG15_25'
    return 'RNG>=25'


def bucket_vol_ratio(x: float) -> str:
    if math.isnan(x): return 'VOLR_NA'
    if x < 0.8: return 'VOLR<0.8'
    if x < 1.2: return 'VOLR0.8_1.2'
    if x < 2.0: return 'VOLR1.2_2'
    return 'VOLR>=2'


def blank() -> dict[str, Any]:
    return {'n': 0, 'wins': 0, 'sum': 0.0, 'loss': 0, 'tp': 0, 'sl': 0, 'time': 0,
            'micro': 0, 'years': defaultdict(lambda: [0, 0]), 'symbols': set()}


def add(a: dict[str, Any], row: dict[str, Any]) -> None:
    pnl = sf(row.get('pnl'), 0.0)
    y = str(row.get('year') or '')
    reason = str(row.get('reason') or '')
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
    a['symbols'].add(row.get('symbol', ''))


def metrics(a: dict[str, Any], stock_count: int = 4655) -> dict[str, Any]:
    n = int(a['n'])
    if n == 0:
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
        'per_stock_3y_all_stocks': round(n / stock_count, 4),
        'yc': yc,
        'ywr': ywr,
        'min_year_n': min(yc.values()) if yc else 0,
        'minwr': round(min(ywr.values()) if ywr else 0, 2),
    }


def row_keys(r: dict[str, str]) -> list[tuple[str, str]]:
    fam = r['family']; reg = r['regime']
    risk = bucket_risk(sf(r.get('risk')))
    liq = bucket_liq(sf(r.get('liq_age')))
    delay = bucket_delay(sf(r.get('reaction_delay')))
    rng = bucket_range(sf(r.get('range60')))
    volenv = r.get('vol_env') or 'VOLENV_NA'
    volr = bucket_vol_ratio(sf(r.get('vol_ratio')))
    disp = 'DISP_Y' if str(r.get('displacement')) == 'True' else 'DISP_N'
    return [
        ('family', fam),
        ('family_regime', f'{fam}|{reg}'),
        ('family_risk', f'{fam}|{risk}'),
        ('family_regime_risk', f'{fam}|{reg}|{risk}'),
        ('family_liq', f'{fam}|{liq}'),
        ('family_regime_liq', f'{fam}|{reg}|{liq}'),
        ('family_delay', f'{fam}|{delay}'),
        ('family_regime_delay', f'{fam}|{reg}|{delay}'),
        ('family_regime_range', f'{fam}|{reg}|{rng}'),
        ('family_regime_vol', f'{fam}|{reg}|{volenv}'),
        ('family_regime_volr', f'{fam}|{reg}|{volr}'),
        ('family_regime_disp_risk', f'{fam}|{reg}|{disp}|{risk}'),
        ('family_regime_liq_risk', f'{fam}|{reg}|{liq}|{risk}'),
        ('family_regime_range_risk', f'{fam}|{reg}|{rng}|{risk}'),
    ]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    with EVENTS.open() as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            if r.get('year') in {'2023', '2024', '2025', '2026'}:
                rows.append(r)

    stock_count = len({r['symbol'] for r in rows})
    baseline = blank()
    for r in rows:
        add(baseline, r)

    # Pre-aggregate by (symbol, selector_dimension, selector_value, year<test).
    by_symbol_key_year: dict[tuple[str, str, str, str], dict[str, Any]] = defaultdict(blank)
    global_key_year: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(blank)
    row_key_cache: list[list[tuple[str, str]]] = []
    for r in rows:
        keys = row_keys(r)
        row_key_cache.append(keys)
        y = r['year']; sym = r['symbol']
        for dim, val in keys:
            add(by_symbol_key_year[(sym, dim, val, y)], r)
            add(global_key_year[(dim, val, y)], r)

    grids = [
        {'name': 'loose_n3_wr50_avgpos', 'min_n': 3, 'min_wr': 50.0, 'min_avg': 0.0},
        {'name': 'balanced_n5_wr52_avgpos', 'min_n': 5, 'min_wr': 52.0, 'min_avg': 0.0},
        {'name': 'strict_n8_wr55_avgpos', 'min_n': 8, 'min_wr': 55.0, 'min_avg': 0.0},
        {'name': 'pnl_n5_wr50_avg05', 'min_n': 5, 'min_wr': 50.0, 'min_avg': 0.5},
    ]

    def fit_candidates(test_year: str, grid: dict[str, Any], per_symbol: bool) -> dict[str, tuple[str, str, dict[str, Any]]]:
        train_years = [y for y in ['2023', '2024', '2025'] if y < test_year]
        out: dict[str, tuple[str, str, dict[str, Any]]] = {}
        if per_symbol:
            candidates = defaultdict(blank)
            for (sym, dim, val, y), a in by_symbol_key_year.items():
                if y in train_years:
                    key = (sym, dim, val)
                    # merge aggregate a into candidates[key]
                    candidates[key]['n'] += a['n']; candidates[key]['wins'] += a['wins']; candidates[key]['sum'] += a['sum']
                    candidates[key]['loss'] += a['loss']; candidates[key]['tp'] += a['tp']; candidates[key]['sl'] += a['sl']
                    candidates[key]['time'] += a['time']; candidates[key]['micro'] += a['micro']; candidates[key]['symbols'].update(a['symbols'])
                    for yy, vv in a['years'].items():
                        candidates[key]['years'][yy][0] += vv[0]; candidates[key]['years'][yy][1] += vv[1]
            for (sym, dim, val), a in candidates.items():
                m = metrics(a, stock_count)
                if m['n'] >= grid['min_n'] and m['wr'] >= grid['min_wr'] and m['avg'] >= grid['min_avg']:
                    score = (m['avg'], m['wr'], math.log1p(m['n']))
                    old = out.get(sym)
                    if old is None or score > old[2]['score']:
                        out[sym] = (dim, val, {**m, 'score': score})
        else:
            candidates = defaultdict(blank)
            for (dim, val, y), a in global_key_year.items():
                if y in train_years:
                    key = (dim, val)
                    candidates[key]['n'] += a['n']; candidates[key]['wins'] += a['wins']; candidates[key]['sum'] += a['sum']
                    candidates[key]['loss'] += a['loss']; candidates[key]['tp'] += a['tp']; candidates[key]['sl'] += a['sl']
                    candidates[key]['time'] += a['time']; candidates[key]['micro'] += a['micro']; candidates[key]['symbols'].update(a['symbols'])
                    for yy, vv in a['years'].items():
                        candidates[key]['years'][yy][0] += vv[0]; candidates[key]['years'][yy][1] += vv[1]
            best = None
            for (dim, val), a in candidates.items():
                m = metrics(a, stock_count)
                if m['n'] >= max(grid['min_n'] * 30, 100) and m['wr'] >= grid['min_wr'] and m['avg'] >= grid['min_avg']:
                    score = (m['avg'], m['wr'], math.log1p(m['n']))
                    if best is None or score > best[2]['score']:
                        best = (dim, val, {**m, 'score': score})
            if best:
                return {'__GLOBAL__': best}
        return out

    selector_results = []
    selected_rows_path = OUT / 'v285_selected_rows.csv'
    with selected_rows_path.open('w', newline='') as fh:
        fieldnames = list(rows[0].keys()) + ['selector_type', 'grid', 'selected_dim', 'selected_value', 'train_n', 'train_wr', 'train_avg']
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for grid in grids:
            for selector_type, per_symbol in [('stock_dna', True), ('global_rule', False)]:
                agg = blank(); by_year = {y: blank() for y in TEST_YEARS}; selected_count_by_year = {}
                picked_hist = defaultdict(int)
                for test_year in TEST_YEARS:
                    fits = fit_candidates(test_year, grid, per_symbol)
                    selected_count_by_year[test_year] = len(fits)
                    for r, keys in zip(rows, row_key_cache):
                        if r['year'] != test_year:
                            continue
                        sym = r['symbol']
                        fit = fits.get(sym) if per_symbol else fits.get('__GLOBAL__')
                        if not fit:
                            continue
                        dim, val, train_m = fit
                        if (dim, val) not in keys:
                            continue
                        add(agg, r); add(by_year[test_year], r)
                        picked_hist[(dim, val)] += 1
                        writer.writerow({**r, 'selector_type': selector_type, 'grid': grid['name'], 'selected_dim': dim,
                                         'selected_value': val, 'train_n': train_m['n'], 'train_wr': train_m['wr'], 'train_avg': train_m['avg']})
                top_picks = [{'dim': k[0], 'value': k[1], 'n': v} for k, v in sorted(picked_hist.items(), key=lambda x: x[1], reverse=True)[:20]]
                selector_results.append({
                    'selector_type': selector_type,
                    'grid': grid,
                    'selected_symbols_by_test_year': selected_count_by_year,
                    'walk_forward': metrics(agg, stock_count),
                    'by_test_year': {y: metrics(a, stock_count) for y, a in by_year.items()},
                    'top_selected_rules_in_test_rows': top_picks,
                })

    # Non-leaky baselines for exactly the test years.
    test_all = blank()
    by_family = defaultdict(blank)
    by_dim_val = defaultdict(blank)
    for r, keys in zip(rows, row_key_cache):
        if r['year'] not in TEST_YEARS:
            continue
        add(test_all, r)
        add(by_family[r['family']], r)
        for dim, val in keys:
            add(by_dim_val[(dim, val)], r)
    family_metrics = [{'family': fam, **metrics(a, stock_count)} for fam, a in by_family.items()]
    family_metrics = sorted(family_metrics, key=lambda x: (x['wr'], x['avg'], x['n']), reverse=True)
    dim_metrics = [{'dimension': k[0], 'value': k[1], **metrics(a, stock_count)} for k, a in by_dim_val.items()]
    dim_metrics = sorted([x for x in dim_metrics if x['n'] >= 100], key=lambda x: (x['wr'], x['avg'], x['n']), reverse=True)[:50]

    # Coverage distribution: how many raw V280 chronological opportunities each stock has.
    cnt_by_sym = defaultdict(int)
    wins_by_sym = defaultdict(int)
    sum_by_sym = defaultdict(float)
    for r in rows:
        cnt_by_sym[r['symbol']] += 1
        pnl = sf(r['pnl'], 0)
        wins_by_sym[r['symbol']] += pnl > 0
        sum_by_sym[r['symbol']] += pnl
    vals = sorted(cnt_by_sym.values())
    def q(p: float) -> float:
        return vals[min(len(vals)-1, int((len(vals)-1)*p))] if vals else 0
    density = {'stocks': len(vals), 'mean': round(sum(vals)/max(1, len(vals)), 2), 'min': vals[0] if vals else 0,
               'p25': q(.25), 'p50': q(.5), 'p75': q(.75), 'p90': q(.9), 'p95': q(.95), 'max': vals[-1] if vals else 0}

    summary = {
        'version': 'V285_V280_STOCK_DNA_WALKFORWARD_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'inputs': {'events': str(EVENTS), 'rows': len(rows), 'symbols': stock_count, 'test_years': TEST_YEARS},
        'raw_v280_all_years': metrics(baseline, stock_count),
        'raw_v280_test_years_2024_2026': metrics(test_all, stock_count),
        'opportunity_density_per_stock_all_years': density,
        'walk_forward_selectors': selector_results,
        'test_year_family_metrics': family_metrics,
        'test_year_top_nonleaky_dimensions': dim_metrics,
        'artifacts': {'selected_rows': str(selected_rows_path)},
        'decision': 'NO_PRODUCTION_WRITE__STOCK_DNA_TEMPORAL_SELECTOR_RESEARCH_ONLY',
    }
    (OUT / 'v285_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:18000])


if __name__ == '__main__':
    main()
