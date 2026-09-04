#!/usr/bin/env python3
"""V286 no-write: walk-forward parent-regime router for V280 temporal SMC events.

Question: V285 showed per-stock DNA does not generalize and V282 showed
market/industry participation helps in-sample but is not production-safe by
itself.  This audit tests the next concrete hypothesis: can a global parent
regime router, trained only on prior years, choose which chronological grammar
surfaces to trade in the next year?

No production/frontend/watchlist writes.
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
OUT = AUDIT / f'v286_walkforward_regime_router_no_write_{TS}'
LATEST = AUDIT / 'v286_walkforward_regime_router_latest.json'
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


def blank() -> dict[str, Any]:
    return {'n': 0, 'wins': 0, 'sum': 0.0, 'loss': 0, 'tp': 0, 'sl': 0, 'time': 0,
            'micro': 0, 'years': defaultdict(lambda: [0, 0]), 'symbols': set()}


def merge(dst: dict[str, Any], src: dict[str, Any]) -> None:
    dst['n'] += src['n']; dst['wins'] += src['wins']; dst['sum'] += src['sum']
    dst['loss'] += src['loss']; dst['tp'] += src['tp']; dst['sl'] += src['sl']
    dst['time'] += src['time']; dst['micro'] += src['micro']; dst['symbols'].update(src['symbols'])
    for y, v in src['years'].items():
        dst['years'][y][0] += v[0]; dst['years'][y][1] += v[1]


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


def metrics(a: dict[str, Any], stock_count: int = 4655) -> dict[str, Any]:
    n = int(a['n'])
    if n == 0:
        return {'n': 0}
    yc = {y: int(v[0]) for y, v in sorted(a['years'].items()) if v[0]}
    ywr = {y: round(v[1] / v[0] * 100, 2) for y, v in sorted(a['years'].items()) if v[0]}
    return {'n': n, 'wr': round(a['wins'] / n * 100, 4), 'avg': round(a['sum'] / n, 4),
            'loss': int(a['loss']), 'micro': round(a['micro'] / n * 100, 2),
            'tp_pct': round(a['tp'] / n * 100, 2), 'sl_pct': round(a['sl'] / n * 100, 2),
            'time_pct': round(a['time'] / n * 100, 2), 'symbols': len(a['symbols']),
            'per_stock_3y_all_stocks': round(n / stock_count, 4), 'yc': yc, 'ywr': ywr,
            'min_year_n': min(yc.values()) if yc else 0,
            'minwr': round(min(ywr.values()) if ywr else 0, 2)}


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


def bucket_volr(x: float) -> str:
    if math.isnan(x): return 'VOLR_NA'
    if x < 0.8: return 'VOLR<0.8'
    if x < 1.2: return 'VOLR0.8_1.2'
    if x < 2.0: return 'VOLR1.2_2'
    return 'VOLR>=2'


def load_industry_map() -> dict[str, str]:
    items = json.loads(INDMAP.read_text())
    out = {}
    for r in items:
        sym = r.get('symbol'); ind = r.get('industry') or ''
        if sym and ind:
            out[sym] = ind
    return out


def build_prev_features(sym_ind: dict[str, str]):
    daily = defaultdict(list)
    ind_daily = defaultdict(lambda: defaultdict(list))
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
    indmap = {}
    for d, rows in daily.items():
        vals = [r[2] for r in rows]
        mkt[d] = {'mkt_n': len(vals), 'mkt_up_pct': sum(v > 0 for v in vals) / len(vals) * 100,
                  'mkt_med_ret': median(vals), 'mkt_strong1_pct': sum(v > 1 for v in vals) / len(vals) * 100}
    for d, mp in ind_daily.items():
        for ind, vals in mp.items():
            if len(vals) < 5:
                continue
            indmap[(d, ind)] = {'ind_n': len(vals), 'ind_up_pct': sum(v > 0 for v in vals) / len(vals) * 100,
                                'ind_med_ret': median(vals), 'ind_strong1_pct': sum(v > 1 for v in vals) / len(vals) * 100}
    def prev_date(d: str) -> str:
        i = bisect.bisect_left(dates, d) - 1
        return dates[i] if i >= 0 else ''
    return prev_date, mkt, indmap


def row_keys(r: dict[str, Any]) -> list[tuple[str, str]]:
    fam = r['family']; reg = r['regime']; vol = r.get('vol_env') or 'VOLENV_NA'
    risk = bucket_risk(sf(r.get('risk')))
    liq = bucket_liq(sf(r.get('liq_age')))
    delay = bucket_delay(sf(r.get('reaction_delay')))
    rng = bucket_range(sf(r.get('range60')))
    volr = bucket_volr(sf(r.get('vol_ratio')))
    disp = 'DISP_Y' if str(r.get('displacement')) == 'True' else 'DISP_N'
    mret = bucket_ret(sf(r.get('prev_mkt_med_ret')))
    iret = bucket_ret(sf(r.get('prev_ind_med_ret')))
    mup = bucket_up(sf(r.get('prev_mkt_up_pct')))
    iup = bucket_up(sf(r.get('prev_ind_up_pct')))
    relret = bucket_rel(sf(r.get('prev_ind_vs_mkt_med_ret')))
    relup = bucket_rel(sf(r.get('prev_ind_vs_mkt_up')))
    base = [
        ('family', fam),
        ('family_regime', f'{fam}|{reg}'),
        ('family_regime_risk', f'{fam}|{reg}|{risk}'),
        ('family_regime_liq_risk', f'{fam}|{reg}|{liq}|{risk}'),
        ('family_regime_range_risk', f'{fam}|{reg}|{rng}|{risk}'),
        ('family_regime_delay', f'{fam}|{reg}|{delay}'),
        ('family_regime_volr', f'{fam}|{reg}|{volr}'),
        ('family_regime_disp_risk', f'{fam}|{reg}|{disp}|{risk}'),
        ('family_regime_mret_iret', f'{fam}|{reg}|M_{mret}|I_{iret}'),
        ('family_regime_mup_iup', f'{fam}|{reg}|M_{mup}|I_{iup}'),
        ('family_regime_risk_mret_iret', f'{fam}|{reg}|{risk}|M_{mret}|I_{iret}'),
        ('family_regime_range_risk_mret_iret', f'{fam}|{reg}|{rng}|{risk}|M_{mret}|I_{iret}'),
        ('family_regime_liq_risk_mret_iret', f'{fam}|{reg}|{liq}|{risk}|M_{mret}|I_{iret}'),
        ('family_regime_vol_risk_mret_iret', f'{fam}|{reg}|{vol}|{risk}|M_{mret}|I_{iret}'),
        ('family_regime_risk_mret_iret_relret', f'{fam}|{reg}|{risk}|M_{mret}|I_{iret}|RELRET_{relret}'),
        ('family_regime_risk_mup_iup_relup', f'{fam}|{reg}|{risk}|M_{mup}|I_{iup}|RELUP_{relup}'),
    ]
    return base


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sym_ind = load_industry_map()
    prev_date, mkt_by_date, ind_by_date = build_prev_features(sym_ind)
    rows: list[dict[str, Any]] = []
    with EVENTS.open() as fh:
        for r in csv.DictReader(fh):
            if r.get('year') not in YEARS:
                continue
            sym = r['symbol']; d = dn(r['entry_date']); ind = sym_ind.get(sym, 'UNKNOWN'); pd = prev_date(d)
            nr = dict(r)
            nr['industry'] = ind; nr['prev_date'] = pd
            for k, v in mkt_by_date.get(pd, {}).items(): nr['prev_' + k] = v
            for k, v in ind_by_date.get((pd, ind), {}).items(): nr['prev_' + k] = v
            nr['prev_ind_vs_mkt_up'] = sf(nr.get('prev_ind_up_pct')) - sf(nr.get('prev_mkt_up_pct'))
            nr['prev_ind_vs_mkt_med_ret'] = sf(nr.get('prev_ind_med_ret')) - sf(nr.get('prev_mkt_med_ret'))
            rows.append(nr)

    stock_count = len({r['symbol'] for r in rows})
    baseline_all = blank(); baseline_test = blank()
    for r in rows:
        add(baseline_all, r)
        if r['year'] in TEST_YEARS:
            add(baseline_test, r)

    key_year: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(blank)
    row_key_cache: list[list[tuple[str, str]]] = []
    for r in rows:
        keys = row_keys(r)
        row_key_cache.append(keys)
        for dim, val in keys:
            add(key_year[(dim, val, r['year'])], r)

    grids = [
        {'name': 'broad_prior_regime', 'min_n': 300, 'min_wr': 52.0, 'min_avg': 0.5, 'min_year_n': 50, 'min_minwr': 45.0, 'top_k': 10},
        {'name': 'balanced_prior_regime', 'min_n': 150, 'min_wr': 55.0, 'min_avg': 1.0, 'min_year_n': 30, 'min_minwr': 48.0, 'top_k': 8},
        {'name': 'strict_prior_regime', 'min_n': 80, 'min_wr': 58.0, 'min_avg': 1.5, 'min_year_n': 20, 'min_minwr': 50.0, 'top_k': 6},
        {'name': 'quality_prior_regime', 'min_n': 50, 'min_wr': 62.0, 'min_avg': 2.0, 'min_year_n': 10, 'min_minwr': 52.0, 'top_k': 5},
    ]

    def train_rules(test_year: str, grid: dict[str, Any]) -> list[dict[str, Any]]:
        train_years = [y for y in YEARS if y < test_year]
        candidates = defaultdict(blank)
        for (dim, val, y), a in key_year.items():
            if y in train_years:
                merge(candidates[(dim, val)], a)
        rules = []
        for (dim, val), a in candidates.items():
            m = metrics(a, stock_count)
            if m['n'] < grid['min_n'] or m['wr'] < grid['min_wr'] or m['avg'] < grid['min_avg']:
                continue
            # For 2024 only 2023 is available; for later years require the declared per-year floor.
            if len(train_years) > 1 and (m['min_year_n'] < grid['min_year_n'] or m['minwr'] < grid['min_minwr']):
                continue
            # Penalize overly broad weak rules; reward annual floor and sample size.
            score = (m['minwr'], m['wr'], m['avg'], math.log1p(m['n']))
            rules.append({'dimension': dim, 'value': val, 'train_years': train_years, 'train': m, 'score': score})
        rules.sort(key=lambda x: x['score'], reverse=True)
        return rules[:int(grid['top_k'])]

    results = []
    rules_path = OUT / 'v286_selected_rules.csv'
    selected_path = OUT / 'v286_selected_rows.csv'
    with rules_path.open('w', newline='') as rf, selected_path.open('w', newline='') as sfh:
        rule_fields = ['grid', 'test_year', 'rank', 'dimension', 'value', 'train_n', 'train_wr', 'train_avg', 'train_minwr', 'train_yc', 'train_ywr']
        rw = csv.DictWriter(rf, fieldnames=rule_fields); rw.writeheader()
        row_fields = list(rows[0].keys()) + ['grid', 'matched_rule_count', 'matched_rules']
        sw = csv.DictWriter(sfh, fieldnames=row_fields); sw.writeheader()
        for grid in grids:
            agg = blank(); by_year = {y: blank() for y in TEST_YEARS}
            selected_rules_by_year = {}
            for test_year in TEST_YEARS:
                rules = train_rules(test_year, grid)
                selected_rules_by_year[test_year] = [{'dimension': r['dimension'], 'value': r['value'], 'train': r['train']} for r in rules]
                for i, r in enumerate(rules, 1):
                    rw.writerow({'grid': grid['name'], 'test_year': test_year, 'rank': i, 'dimension': r['dimension'],
                                 'value': r['value'], 'train_n': r['train']['n'], 'train_wr': r['train']['wr'],
                                 'train_avg': r['train']['avg'], 'train_minwr': r['train']['minwr'],
                                 'train_yc': json.dumps(r['train']['yc'], ensure_ascii=False),
                                 'train_ywr': json.dumps(r['train']['ywr'], ensure_ascii=False)})
                rule_set = {(r['dimension'], r['value']) for r in rules}
                for r, keys in zip(rows, row_key_cache):
                    if r['year'] != test_year:
                        continue
                    matches = sorted(set(keys) & rule_set)
                    if not matches:
                        continue
                    add(agg, r); add(by_year[test_year], r)
                    out = dict(r)
                    out['grid'] = grid['name']
                    out['matched_rule_count'] = len(matches)
                    out['matched_rules'] = json.dumps([f'{d}:{v}' for d, v in matches], ensure_ascii=False)
                    sw.writerow(out)
            results.append({'grid': grid, 'walk_forward': metrics(agg, stock_count),
                            'by_year': {y: metrics(a, stock_count) for y, a in by_year.items()},
                            'selected_rules_by_year': selected_rules_by_year})

    # Explain the remaining 2026 failure by regime buckets over the whole test period.
    bucket_aggs = defaultdict(blank)
    for r in rows:
        if r['year'] not in TEST_YEARS:
            continue
        fam = r['family']; reg = r['regime']; risk = bucket_risk(sf(r.get('risk')))
        mret = bucket_ret(sf(r.get('prev_mkt_med_ret'))); iret = bucket_ret(sf(r.get('prev_ind_med_ret')))
        iup = bucket_up(sf(r.get('prev_ind_up_pct'))); relret = bucket_rel(sf(r.get('prev_ind_vs_mkt_med_ret')))
        dims = {
            'family_regime_risk': f'{fam}|{reg}|{risk}',
            'family_regime_mret_iret': f'{fam}|{reg}|M_{mret}|I_{iret}',
            'family_regime_risk_mret_iret': f'{fam}|{reg}|{risk}|M_{mret}|I_{iret}',
            'family_regime_risk_mret_iret_relret': f'{fam}|{reg}|{risk}|M_{mret}|I_{iret}|RELRET_{relret}',
            'family_regime_risk_iup': f'{fam}|{reg}|{risk}|IUP_{iup}',
        }
        for dim, val in dims.items():
            add(bucket_aggs[(dim, val)], r)
    top_contexts = []
    for (dim, val), a in bucket_aggs.items():
        m = metrics(a, stock_count)
        if m['n'] >= 100:
            top_contexts.append({'dimension': dim, 'value': val, **m})
    top_contexts.sort(key=lambda x: (x['minwr'], x['wr'], x['avg'], x['n']), reverse=True)

    summary = {
        'version': 'V286_WALKFORWARD_REGIME_ROUTER_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'source_events': str(EVENTS), 'industry_map': str(INDMAP),
        'rows': len(rows), 'symbols': stock_count,
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'baseline_all_years': metrics(baseline_all, stock_count),
        'baseline_test_years_2024_2026': metrics(baseline_test, stock_count),
        'walk_forward_results': results,
        'top_contexts_test_years_in_sample_diagnostic': top_contexts[:40],
        'artifacts': {'out_dir': str(OUT), 'selected_rules': str(rules_path), 'selected_rows': str(selected_path), 'summary': str(OUT / 'v286_summary.json')},
        'interpretation': {
            'tested_hypothesis': 'Prior-year global parent regime can route V280 chronological grammar families using only previous-day market/industry state and event-time grammar buckets.',
            'decision_rule': 'A router is production-candidate only if walk-forward 2024/2025/2026 all stay stable with enough trades; in-sample context pockets are diagnostic only.'
        }
    }
    (OUT / 'v286_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'out': str(OUT), 'latest': str(LATEST), 'baseline_test': summary['baseline_test_years_2024_2026'],
                      'walk_forward': [{'grid': r['grid']['name'], 'wf': r['walk_forward']} for r in results]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
