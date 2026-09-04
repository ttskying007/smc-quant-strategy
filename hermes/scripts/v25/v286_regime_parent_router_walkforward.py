#!/usr/bin/env python3
"""V286 no-write: market/industry regime parent router for V280 time-ordered SMC events.

Hypothesis: V285 showed per-stock DNA does not generalize.  The next minimal
question is whether an entry-time parent regime (previous-day market + industry
participation) can select which V280 grammar family/risk surface to trade in a
walk-forward manner.

No production/frontend/watchlist writes.  All market/industry features use only
the trading day before entry_date.
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
KDIR = BASE / 'kline_cache'
AUDIT = BASE / 'smc_audit'
EVENTS = AUDIT / 'v280_layered_state_grammar_no_write_20260702_205055/v280_events.csv'
INDMAP = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v286_regime_parent_router_walkforward_no_write_{TS}'
LATEST = AUDIT / 'v286_regime_parent_router_walkforward_latest.json'
YEARS = ['2023', '2024', '2025', '2026']
TEST_YEARS = ['2024', '2025', '2026']


def sf(x: Any, d: float = math.nan) -> float:
    try:
        if x is None or x == '':
            return d
        v = float(x)
        return v if not math.isnan(v) else d
    except Exception:
        return d


def dn(x: Any) -> str:
    s = ''.join(ch for ch in str(x or '').replace('-', '')[:12] if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def symbol_from_path(p: Path) -> str:
    stem = p.stem.replace('_daily_750', '')
    code, exch = stem.split('_', 1)
    return f'{code}.{exch}'


def bucket_ret(x: float) -> str:
    if math.isnan(x): return 'RET_NA'
    if x < -1: return 'RET<-1'
    if x < 0: return 'RET_-1_0'
    if x < 1: return 'RET_0_1'
    return 'RET>=1'


def bucket_up(x: float) -> str:
    if math.isnan(x): return 'UP_NA'
    if x < 35: return 'UP<35'
    if x < 50: return 'UP35_50'
    if x < 65: return 'UP50_65'
    return 'UP>=65'


def bucket_rel(x: float) -> str:
    if math.isnan(x): return 'REL_NA'
    if x < -10: return 'REL<-10'
    if x < 0: return 'REL_-10_0'
    if x < 10: return 'REL_0_10'
    return 'REL>=10'


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


def bucket_range(x: float) -> str:
    if math.isnan(x): return 'RNG_NA'
    if x < 15: return 'RNG<15'
    if x < 25: return 'RNG15_25'
    return 'RNG>=25'


def bucket_delay(x: float) -> str:
    if math.isnan(x): return 'DLY_NA'
    if x <= 0: return 'DLY0'
    if x <= 1: return 'DLY1'
    if x <= 3: return 'DLY2_3'
    return 'DLY>3'


def blank() -> dict[str, Any]:
    return {'n': 0, 'wins': 0, 'sum': 0.0, 'loss': 0, 'micro': 0, 'tp': 0, 'sl': 0, 'time': 0,
            'years': defaultdict(lambda: [0, 0]), 'months': defaultdict(lambda: [0, 0]), 'symbols': set()}


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'), 0.0)
    y = str(r.get('year') or dn(r.get('entry_date'))[:4])
    m = dn(r.get('entry_date'))[:6]
    reason = str(r.get('reason') or '')
    a['n'] += 1
    a['wins'] += pnl > 0
    a['sum'] += pnl
    a['loss'] += pnl <= 0
    a['micro'] += 0 < pnl < 1
    a['tp'] += reason == 'TP'
    a['sl'] += reason == 'SL'
    a['time'] += reason.startswith('TIME')
    a['years'][y][0] += 1
    a['years'][y][1] += pnl > 0
    if m:
        a['months'][m][0] += 1
        a['months'][m][1] += pnl > 0
    a['symbols'].add(r.get('symbol', ''))


def merge(dst: dict[str, Any], src: dict[str, Any]) -> None:
    dst['n'] += src['n']; dst['wins'] += src['wins']; dst['sum'] += src['sum']
    dst['loss'] += src['loss']; dst['micro'] += src['micro']; dst['tp'] += src['tp']; dst['sl'] += src['sl']; dst['time'] += src['time']
    dst['symbols'].update(src['symbols'])
    for y, v in src['years'].items():
        dst['years'][y][0] += v[0]; dst['years'][y][1] += v[1]
    for m, v in src['months'].items():
        dst['months'][m][0] += v[0]; dst['months'][m][1] += v[1]


def metrics(a: dict[str, Any]) -> dict[str, Any]:
    n = int(a['n'])
    if not n:
        return {'n': 0}
    yc = {y: int(v[0]) for y, v in sorted(a['years'].items()) if v[0]}
    ywr = {y: round(v[1] / v[0] * 100, 2) for y, v in sorted(a['years'].items()) if v[0]}
    mc = {m: int(v[0]) for m, v in sorted(a['months'].items()) if v[0]}
    mwr = {m: round(v[1] / v[0] * 100, 2) for m, v in sorted(a['months'].items()) if v[0]}
    valid_mwr = [w for m, w in mwr.items() if mc[m] >= 20]
    return {
        'n': n, 'wr': round(a['wins'] / n * 100, 4), 'avg': round(a['sum'] / n, 4), 'loss': int(a['loss']),
        'micro': round(a['micro'] / n * 100, 2), 'tp_pct': round(a['tp'] / n * 100, 2),
        'sl_pct': round(a['sl'] / n * 100, 2), 'time_pct': round(a['time'] / n * 100, 2),
        'symbols': len(a['symbols']), 'yc': yc, 'ywr': ywr,
        'min_year_n': min(yc.values()) if yc else 0, 'minwr': round(min(ywr.values()) if ywr else 0, 2),
        'months': len(mc), 'min_month_wr_n20': round(min(valid_mwr), 2) if valid_mwr else None,
    }


def load_industry_map() -> dict[str, str]:
    rows = json.loads(INDMAP.read_text())
    return {r['symbol']: r.get('industry', '') for r in rows if r.get('symbol') and r.get('industry')}


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
    mkt_by_date = {}
    ind_by_date = {}
    for d, rows in daily.items():
        vals = [r[2] for r in rows]
        mkt_by_date[d] = {
            'mkt_n': len(vals), 'mkt_up_pct': sum(v > 0 for v in vals) / len(vals) * 100,
            'mkt_med_ret': median(vals), 'mkt_strong1_pct': sum(v > 1 for v in vals) / len(vals) * 100,
        }
    for d, mp in ind_daily.items():
        for ind, vals in mp.items():
            if len(vals) < 5:
                continue
            ind_by_date[(d, ind)] = {
                'ind_n': len(vals), 'ind_up_pct': sum(v > 0 for v in vals) / len(vals) * 100,
                'ind_med_ret': median(vals), 'ind_strong1_pct': sum(v > 1 for v in vals) / len(vals) * 100,
            }
    def prev_date(d: str) -> str:
        i = bisect.bisect_left(dates, d) - 1
        return dates[i] if i >= 0 else ''
    return prev_date, mkt_by_date, ind_by_date


def enrich_rows() -> list[dict[str, str]]:
    sym_ind = load_industry_map()
    prev_date, mkt_by_date, ind_by_date = build_prev_features(sym_ind)
    rows = []
    with EVENTS.open(newline='') as fh:
        for r in csv.DictReader(fh):
            if r.get('year') not in YEARS:
                continue
            sym = r['symbol']; d = dn(r['entry_date']); ind = sym_ind.get(sym, 'UNKNOWN'); pd = prev_date(d)
            mf = mkt_by_date.get(pd, {})
            inf = ind_by_date.get((pd, ind), {})
            nr = dict(r)
            nr.update({'industry': ind, 'prev_date': pd})
            for k, v in mf.items(): nr['prev_' + k] = v
            for k, v in inf.items(): nr['prev_' + k] = v
            nr['prev_ind_vs_mkt_up'] = sf(nr.get('prev_ind_up_pct')) - sf(nr.get('prev_mkt_up_pct'))
            nr['prev_ind_vs_mkt_med_ret'] = sf(nr.get('prev_ind_med_ret')) - sf(nr.get('prev_mkt_med_ret'))
            rows.append(nr)
    return rows


def row_keys(r: dict[str, Any]) -> list[tuple[str, str]]:
    fam = r['family']; reg = r['regime']
    risk = bucket_risk(sf(r.get('risk')))
    liq = bucket_liq(sf(r.get('liq_age')))
    rng = bucket_range(sf(r.get('range60')))
    dly = bucket_delay(sf(r.get('reaction_delay')))
    vol = r.get('vol_env') or 'VOL_NA'
    disp = 'DISP_Y' if str(r.get('displacement')) == 'True' else 'DISP_N'
    mret = bucket_ret(sf(r.get('prev_mkt_med_ret')))
    iret = bucket_ret(sf(r.get('prev_ind_med_ret')))
    mup = bucket_up(sf(r.get('prev_mkt_up_pct')))
    iup = bucket_up(sf(r.get('prev_ind_up_pct')))
    relret = bucket_rel(sf(r.get('prev_ind_vs_mkt_med_ret')))
    relup = bucket_rel(sf(r.get('prev_ind_vs_mkt_up')))
    state = f'M{mret}|I{iret}'
    state_rel = f'{state}|R{relret}'
    broad = f'M{mup}|I{iup}|U{relup}'
    return [
        ('state_family', f'{state}|{fam}'),
        ('state_family_regime', f'{state}|{fam}|{reg}'),
        ('state_family_regime_risk', f'{state}|{fam}|{reg}|{risk}'),
        ('state_family_regime_risk_liq', f'{state}|{fam}|{reg}|{risk}|{liq}'),
        ('state_family_risk_range', f'{state}|{fam}|{risk}|{rng}'),
        ('state_family_vol_risk', f'{state}|{fam}|{vol}|{risk}'),
        ('state_rel_family_regime_risk', f'{state_rel}|{fam}|{reg}|{risk}'),
        ('broad_family_regime_risk', f'{broad}|{fam}|{reg}|{risk}'),
        ('state_family_delay_disp', f'{state}|{fam}|{dly}|{disp}'),
    ]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = enrich_rows()
    key_cache = [row_keys(r) for r in rows]
    baseline = blank()
    for r in rows:
        add(baseline, r)

    key_year: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(blank)
    for r, keys in zip(rows, key_cache):
        for dim, val in keys:
            add(key_year[(dim, val, r['year'])], r)

    grids = [
        {'name': 'loose_n200_wr52_avg05', 'min_n': 200, 'min_wr': 52.0, 'min_avg': 0.5, 'minwr': 0.0, 'max_rules': 40},
        {'name': 'balanced_n300_wr55_avg10_minyr45', 'min_n': 300, 'min_wr': 55.0, 'min_avg': 1.0, 'minwr': 45.0, 'max_rules': 25},
        {'name': 'strict_n150_wr60_avg15_minyr50', 'min_n': 150, 'min_wr': 60.0, 'min_avg': 1.5, 'minwr': 50.0, 'max_rules': 20},
        {'name': 'coverage_n800_wr53_avg08_minyr45', 'min_n': 800, 'min_wr': 53.0, 'min_avg': 0.8, 'minwr': 45.0, 'max_rules': 15},
    ]

    def fit_rules(test_year: str, grid: dict[str, Any]) -> list[dict[str, Any]]:
        train_years = [y for y in ['2023', '2024', '2025'] if y < test_year]
        candidates: dict[tuple[str, str], dict[str, Any]] = defaultdict(blank)
        for (dim, val, y), a in key_year.items():
            if y in train_years:
                merge(candidates[(dim, val)], a)
        rules = []
        for (dim, val), a in candidates.items():
            m = metrics(a)
            train_year_count = len(m.get('yc', {}))
            minwr_ok = True if train_year_count < 2 else m.get('minwr', 0) >= grid['minwr']
            if m['n'] >= grid['min_n'] and m['wr'] >= grid['min_wr'] and m['avg'] >= grid['min_avg'] and minwr_ok:
                score = (m['avg'], m['wr'], m['minwr'], math.log1p(m['n']))
                rules.append({'dim': dim, 'val': val, 'train': {k: v for k, v in m.items() if k != 'months'}, 'score': score})
        rules.sort(key=lambda x: x['score'], reverse=True)
        return rules[:grid['max_rules']]

    selector_rows_path = OUT / 'v286_selected_rows.csv'
    rule_rows_path = OUT / 'v286_selected_rules.csv'
    selector_results = []
    with selector_rows_path.open('w', newline='') as fr, rule_rows_path.open('w', newline='') as rr:
        row_fields = list(rows[0].keys()) + ['grid', 'matched_rule_dim', 'matched_rule_val', 'train_n', 'train_wr', 'train_avg']
        rule_fields = ['grid', 'test_year', 'dim', 'val', 'train_n', 'train_wr', 'train_avg', 'train_minwr', 'train_yc', 'train_ywr']
        wrow = csv.DictWriter(fr, fieldnames=row_fields); wrow.writeheader()
        wrule = csv.DictWriter(rr, fieldnames=rule_fields); wrule.writeheader()
        for grid in grids:
            agg = blank(); by_year = {y: blank() for y in TEST_YEARS}; selected_count_by_year = {}; rules_by_year = {}
            for test_year in TEST_YEARS:
                rules = fit_rules(test_year, grid)
                rules_by_year[test_year] = len(rules)
                selected_count_by_year[test_year] = 0
                rule_map = {(r['dim'], r['val']): r for r in rules}
                for rule in rules:
                    tr = rule['train']
                    wrule.writerow({'grid': grid['name'], 'test_year': test_year, 'dim': rule['dim'], 'val': rule['val'],
                                    'train_n': tr.get('n'), 'train_wr': tr.get('wr'), 'train_avg': tr.get('avg'),
                                    'train_minwr': tr.get('minwr'), 'train_yc': json.dumps(tr.get('yc'), ensure_ascii=False),
                                    'train_ywr': json.dumps(tr.get('ywr'), ensure_ascii=False)})
                for r, keys in zip(rows, key_cache):
                    if r['year'] != test_year:
                        continue
                    matched = None
                    for k in keys:
                        if k in rule_map:
                            matched = rule_map[k]
                            break
                    if matched:
                        add(agg, r); add(by_year[test_year], r); selected_count_by_year[test_year] += 1
                        tr = matched['train']
                        out = dict(r)
                        out.update({'grid': grid['name'], 'matched_rule_dim': matched['dim'], 'matched_rule_val': matched['val'],
                                    'train_n': tr.get('n'), 'train_wr': tr.get('wr'), 'train_avg': tr.get('avg')})
                        wrow.writerow(out)
            selector_results.append({'grid': grid, 'rules_by_test_year': rules_by_year, 'selected_rows_by_test_year': selected_count_by_year,
                                     'walk_forward': metrics(agg), 'by_year_detail': {y: metrics(a) for y, a in by_year.items()}})

    # Also report non-walk-forward top surfaces across test years for diagnosis only.
    diagnostic_aggs: dict[tuple[str, str], dict[str, Any]] = defaultdict(blank)
    for r, keys in zip(rows, key_cache):
        if r['year'] in TEST_YEARS:
            for dim, val in keys:
                add(diagnostic_aggs[(dim, val)], r)
    diag = []
    for (dim, val), a in diagnostic_aggs.items():
        m = metrics(a)
        if m['n'] >= 100:
            diag.append({'dimension': dim, 'value': val, **m})
    diag.sort(key=lambda x: (x['minwr'], x['wr'], x['avg'], x['n']), reverse=True)

    summary = {
        'version': 'V286_REGIME_PARENT_ROUTER_WALKFORWARD_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'source_events': str(EVENTS), 'industry_map': str(INDMAP),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'inputs': {'rows': len(rows), 'symbols': len({r['symbol'] for r in rows}), 'years': YEARS},
        'baseline_all': metrics(baseline),
        'baseline_test_years': {},
        'walk_forward_selectors': selector_results,
        'diagnostic_top_nonwalkforward_surfaces': diag[:50],
        'artifacts': {'selected_rows': str(selector_rows_path), 'selected_rules': str(rule_rows_path), 'out_dir': str(OUT)},
    }
    test_base = blank()
    for r in rows:
        if r['year'] in TEST_YEARS:
            add(test_base, r)
    summary['baseline_test_years'] = metrics(test_base)
    (OUT / 'v286_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'out': str(OUT), 'latest': str(LATEST), 'baseline_test': summary['baseline_test_years'], 'selectors': selector_results}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
