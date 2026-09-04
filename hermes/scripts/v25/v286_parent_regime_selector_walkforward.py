#!/usr/bin/env python3
"""V286 no-write: parent market/industry regime selector for V280 temporal grammar.

Tests the next hypothesis after V285: per-stock DNA is not stable enough; quality
may require a parent regime gate (previous-day market/industry participation) that
selects which chronological SMC grammar family/rule is allowed for the next day.

All features are available before entry: V280 event fields + previous trading-day
market/industry participation. No production/frontend/watchlist writes.
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
OUT = AUDIT / f'v286_parent_regime_selector_no_write_{TS}'
LATEST = AUDIT / 'v286_parent_regime_selector_latest.json'
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
    return {'n': 0, 'wins': 0, 'sum': 0.0, 'loss': 0, 'micro': 0,
            'tp': 0, 'sl': 0, 'time': 0, 'years': defaultdict(lambda: [0, 0]), 'symbols': set()}


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'), 0.0)
    y = str(r.get('year') or dn(r.get('entry_date'))[:4])
    reason = str(r.get('reason') or '')
    a['n'] += 1; a['wins'] += pnl > 0; a['sum'] += pnl; a['loss'] += pnl <= 0; a['micro'] += 0 < pnl < 1
    a['tp'] += reason == 'TP'; a['sl'] += reason == 'SL'; a['time'] += reason.startswith('TIME')
    a['years'][y][0] += 1; a['years'][y][1] += pnl > 0; a['symbols'].add(r.get('symbol', ''))


def merge(dst: dict[str, Any], src: dict[str, Any]) -> None:
    dst['n'] += src['n']; dst['wins'] += src['wins']; dst['sum'] += src['sum']; dst['loss'] += src['loss']; dst['micro'] += src['micro']
    dst['tp'] += src['tp']; dst['sl'] += src['sl']; dst['time'] += src['time']; dst['symbols'].update(src['symbols'])
    for y, v in src['years'].items():
        dst['years'][y][0] += v[0]; dst['years'][y][1] += v[1]


def metrics(a: dict[str, Any], stock_count: int = 4655) -> dict[str, Any]:
    n = int(a['n'])
    if not n: return {'n': 0}
    yc = {y: int(v[0]) for y, v in sorted(a['years'].items()) if v[0]}
    ywr = {y: round(v[1] / v[0] * 100, 2) for y, v in sorted(a['years'].items()) if v[0]}
    return {'n': n, 'wr': round(a['wins'] / n * 100, 4), 'avg': round(a['sum'] / n, 4),
            'loss': int(a['loss']), 'micro': round(a['micro'] / n * 100, 2),
            'tp_pct': round(a['tp'] / n * 100, 2), 'sl_pct': round(a['sl'] / n * 100, 2),
            'time_pct': round(a['time'] / n * 100, 2), 'symbols': len(a['symbols']),
            'per_stock_3y_all_stocks': round(n / stock_count, 4), 'yc': yc, 'ywr': ywr,
            'min_year_n': min(yc.values()) if yc else 0, 'minwr': round(min(ywr.values()) if ywr else 0, 2)}


def row_rule_keys(r: dict[str, str]) -> list[tuple[str, str]]:
    fam = r['family']; reg = r['regime']
    risk = bucket_risk(sf(r.get('risk'))); liq = bucket_liq(sf(r.get('liq_age')))
    delay = bucket_delay(sf(r.get('reaction_delay'))); rng = bucket_range(sf(r.get('range60')))
    volenv = r.get('vol_env') or 'VOLENV_NA'; volr = bucket_vol_ratio(sf(r.get('vol_ratio')))
    disp = 'DISP_Y' if str(r.get('displacement')) == 'True' else 'DISP_N'
    return [
        ('family', fam), ('family_regime', f'{fam}|{reg}'), ('family_regime_risk', f'{fam}|{reg}|{risk}'),
        ('family_regime_liq', f'{fam}|{reg}|{liq}'), ('family_regime_delay', f'{fam}|{reg}|{delay}'),
        ('family_regime_range', f'{fam}|{reg}|{rng}'), ('family_regime_vol', f'{fam}|{reg}|{volenv}'),
        ('family_regime_volr', f'{fam}|{reg}|{volr}'), ('family_regime_disp_risk', f'{fam}|{reg}|{disp}|{risk}'),
        ('family_regime_liq_risk', f'{fam}|{reg}|{liq}|{risk}'), ('family_regime_range_risk', f'{fam}|{reg}|{rng}|{risk}'),
        ('family_regime_vol_risk', f'{fam}|{reg}|{volenv}|{risk}'), ('family_regime_delay_risk', f'{fam}|{reg}|{delay}|{risk}'),
    ]


def state_keys(r: dict[str, str]) -> list[tuple[str, str]]:
    mret = bucket_ret(sf(r.get('prev_mkt_med_ret'))); iret = bucket_ret(sf(r.get('prev_ind_med_ret')))
    mup = bucket_up(sf(r.get('prev_mkt_up_pct'))); iup = bucket_up(sf(r.get('prev_ind_up_pct')))
    relret = bucket_rel(sf(r.get('prev_ind_vs_mkt_med_ret'))); relup = bucket_rel(sf(r.get('prev_ind_vs_mkt_up')))
    return [
        ('mret_iret', f'M_{mret}|I_{iret}'),
        ('mret_iret_relret', f'M_{mret}|I_{iret}|RELRET_{relret}'),
        ('mup_iup', f'M_{mup}|I_{iup}'),
        ('mup_iup_relup', f'M_{mup}|I_{iup}|RELUP_{relup}'),
        ('market_only', f'MRET_{mret}|MUP_{mup}'),
    ]


def load_industry_map() -> dict[str, str]:
    items = json.loads(INDMAP.read_text())
    return {r['symbol']: r.get('industry') or '' for r in items if r.get('symbol') and r.get('industry')}


def build_prev_features(sym_ind: dict[str, str]):
    daily = defaultdict(list); ind_daily = defaultdict(lambda: defaultdict(list))
    for fp in KDIR.glob('*_daily_750.json'):
        try: sym = symbol_from_path(fp)
        except Exception: continue
        ind = sym_ind.get(sym)
        if not ind: continue
        try: bars = json.loads(fp.read_text())
        except Exception: continue
        seq = []
        for b in bars:
            d = dn(b.get('t') or b.get('date')); c = sf(b.get('c'))
            if d and not math.isnan(c): seq.append((d, c))
        seq.sort()
        for i in range(1, len(seq)):
            d, c = seq[i]; pc = seq[i - 1][1]
            if pc and pc > 0:
                ret = (c / pc - 1) * 100
                daily[d].append((sym, ind, ret)); ind_daily[d][ind].append(ret)
    dates = sorted(daily); mkt_by_date = {}; ind_by_date = {}
    for d, rows in daily.items():
        vals = [r[2] for r in rows]
        mkt_by_date[d] = {'mkt_n': len(vals), 'mkt_up_pct': sum(v > 0 for v in vals) / len(vals) * 100,
                          'mkt_med_ret': median(vals), 'mkt_strong1_pct': sum(v > 1 for v in vals) / len(vals) * 100}
    for d, mp in ind_daily.items():
        for ind, vals in mp.items():
            if len(vals) < 5: continue
            ind_by_date[(d, ind)] = {'ind_n': len(vals), 'ind_up_pct': sum(v > 0 for v in vals) / len(vals) * 100,
                                     'ind_med_ret': median(vals), 'ind_strong1_pct': sum(v > 1 for v in vals) / len(vals) * 100}
    def prev_date(d: str) -> str:
        i = bisect.bisect_left(dates, d) - 1
        return dates[i] if i >= 0 else ''
    return prev_date, mkt_by_date, ind_by_date


def load_rows() -> list[dict[str, str]]:
    sym_ind = load_industry_map(); prev_date, mkt_by_date, ind_by_date = build_prev_features(sym_ind)
    rows = []
    with EVENTS.open(newline='') as f:
        for r in csv.DictReader(f):
            if r.get('year') not in {'2023', '2024', '2025', '2026'}: continue
            sym = r['symbol']; d = dn(r['entry_date']); ind = sym_ind.get(sym, 'UNKNOWN'); pd = prev_date(d)
            nr = dict(r); nr.update({'industry': ind, 'prev_date': pd})
            for k, v in mkt_by_date.get(pd, {}).items(): nr['prev_' + k] = v
            for k, v in ind_by_date.get((pd, ind), {}).items(): nr['prev_' + k] = v
            nr['prev_ind_vs_mkt_up'] = sf(nr.get('prev_ind_up_pct')) - sf(nr.get('prev_mkt_up_pct'))
            nr['prev_ind_vs_mkt_med_ret'] = sf(nr.get('prev_ind_med_ret')) - sf(nr.get('prev_mkt_med_ret'))
            nr['_rules'] = row_rule_keys(nr); nr['_states'] = state_keys(nr)
            rows.append(nr)
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_rows(); stock_count = len({r['symbol'] for r in rows})
    baseline = blank(); test_baseline = blank()
    for r in rows:
        add(baseline, r)
        if r['year'] in TEST_YEARS: add(test_baseline, r)

    # Pre-aggregate by (state_dim,state_val,rule_dim,rule_val,year).
    by_state_rule_year = defaultdict(blank)
    for r in rows:
        y = r['year']
        for sdim, sval in r['_states']:
            for rdim, rval in r['_rules']:
                add(by_state_rule_year[(sdim, sval, rdim, rval, y)], r)

    grids = [
        {'name': 'loose_state_n20_wr52_avg0', 'min_n': 20, 'min_wr': 52.0, 'min_avg': 0.0},
        {'name': 'balanced_state_n50_wr54_avg05', 'min_n': 50, 'min_wr': 54.0, 'min_avg': 0.5},
        {'name': 'strict_state_n100_wr56_avg1', 'min_n': 100, 'min_wr': 56.0, 'min_avg': 1.0},
        {'name': 'broad_state_n100_wr52_avg05', 'min_n': 100, 'min_wr': 52.0, 'min_avg': 0.5},
    ]

    def fit(test_year: str, grid: dict[str, Any]) -> dict[tuple[str, str], tuple[str, str, dict[str, Any]]]:
        train_years = [y for y in ['2023', '2024', '2025'] if y < test_year]
        candidates = defaultdict(blank)
        for (sdim, sval, rdim, rval, y), a in by_state_rule_year.items():
            if y in train_years:
                merge(candidates[(sdim, sval, rdim, rval)], a)
        selected = {}
        for (sdim, sval, rdim, rval), a in candidates.items():
            m = metrics(a, stock_count)
            if m['n'] >= grid['min_n'] and m['wr'] >= grid['min_wr'] and m['avg'] >= grid['min_avg']:
                score = (m['avg'], m['wr'], math.log1p(m['n']))
                key = (sdim, sval)
                old = selected.get(key)
                if old is None or score > old[2]['score']:
                    selected[key] = (rdim, rval, {**m, 'score': score})
        return selected

    summaries = []; selected_rows_out = []
    for grid in grids:
        agg = blank(); per_year_counts = {}
        selected_by_year = {}
        for ty in TEST_YEARS:
            selected = fit(ty, grid); selected_by_year[ty] = len(selected); per_year_counts[ty] = 0
            for r in rows:
                if r['year'] != ty: continue
                matched = None
                for sdim, sval in r['_states']:
                    sel = selected.get((sdim, sval))
                    if sel and (sel[0], sel[1]) in r['_rules']:
                        matched = (sdim, sval, sel)
                        break
                if matched:
                    add(agg, r); per_year_counts[ty] += 1
                    selected_rows_out.append({
                        'grid': grid['name'], 'selected_test_year': ty, 'selected_state_dim': matched[0],
                        'selected_state_val': matched[1], 'selected_rule_dim': matched[2][0], 'selected_rule_val': matched[2][1],
                        'train_n': matched[2][2]['n'], 'train_wr': matched[2][2]['wr'], 'train_avg': matched[2][2]['avg'],
                        **{k: v for k, v in r.items() if not k.startswith('_')},
                    })
        summaries.append({'grid': grid, 'selected_states_by_test_year': selected_by_year, 'selected_rows_by_test_year': per_year_counts,
                          'walk_forward': metrics(agg, stock_count)})

    # Non-walk-forward diagnostic: top state+rule surfaces on 2024-2026 only.
    diag = defaultdict(blank)
    for r in rows:
        if r['year'] not in TEST_YEARS: continue
        for sdim, sval in r['_states']:
            for rdim, rval in r['_rules']:
                add(diag[(sdim, sval, rdim, rval)], r)
    top_diag = []
    for (sdim, sval, rdim, rval), a in diag.items():
        m = metrics(a, stock_count)
        if m['n'] >= 100:
            top_diag.append({'state_dim': sdim, 'state_val': sval, 'rule_dim': rdim, 'rule_val': rval, **m})
    top_diag.sort(key=lambda x: (x['minwr'], x['wr'], x['avg'], x['n']), reverse=True)

    fields = ['grid','selected_test_year','selected_state_dim','selected_state_val','selected_rule_dim','selected_rule_val','train_n','train_wr','train_avg','symbol','entry_date','year','family','regime','pnl','reason','risk','zone_low','zone_high','event_i','poi_i','reaction_delay','swing_gap','liq_age','range60','vol_env','vol_ratio','displacement','t1','industry','prev_date','prev_mkt_n','prev_mkt_up_pct','prev_mkt_med_ret','prev_mkt_strong1_pct','prev_ind_n','prev_ind_up_pct','prev_ind_med_ret','prev_ind_strong1_pct','prev_ind_vs_mkt_up','prev_ind_vs_mkt_med_ret']
    sel_path = OUT / 'v286_selected_rows.csv'
    with sel_path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in selected_rows_out:
            w.writerow({k: r.get(k) for k in fields})
    diag_path = OUT / 'v286_top_state_rule_surfaces.csv'
    with diag_path.open('w', newline='') as f:
        fields2 = ['state_dim','state_val','rule_dim','rule_val','n','wr','avg','min_year_n','minwr','tp_pct','sl_pct','time_pct','symbols','yc','ywr']
        w = csv.DictWriter(f, fieldnames=fields2); w.writeheader()
        for r in top_diag[:500]: w.writerow({k: r.get(k) for k in fields2})

    summary = {'version': 'V286_PARENT_REGIME_SELECTOR_WALKFORWARD_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
               'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
               'inputs': {'events': str(EVENTS), 'rows': len(rows), 'symbols': stock_count, 'test_years': TEST_YEARS,
                          'industry_map': str(INDMAP), 'feature_timing': 'previous trading day market/industry only'},
               'raw_all_years': metrics(baseline, stock_count), 'raw_test_years_2024_2026': metrics(test_baseline, stock_count),
               'walk_forward_parent_selectors': summaries, 'top_diagnostic_state_rule_surfaces_2024_2026': top_diag[:30],
               'artifacts': {'selected_rows': str(sel_path), 'top_state_rule_surfaces': str(diag_path)},
               'decision': 'Parent market/industry regime selector tested with prior-year-only fitting; inspect walk_forward annual robustness before production consideration.'}
    (OUT / 'v286_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'out': str(OUT), 'latest': str(LATEST), 'raw_test': summary['raw_test_years_2024_2026'],
                      'selectors': summaries, 'top_diag': top_diag[:5]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
