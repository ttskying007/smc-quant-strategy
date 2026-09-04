#!/usr/bin/env python3
"""V286 no-write: rolling time-segment stock DNA audit on V280 temporal grammar events.

Tests Lei's hypothesis: a stock's operator/big-money pattern is period-specific,
so DNA must be learned from a recent window and applied only to the next segment.

No production/frontend/watchlist writes.
"""
from __future__ import annotations

import csv, json, math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
EVENTS = AUDIT / 'v280_layered_state_grammar_no_write_20260702_205055/v280_events.csv'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v286_rolling_period_stock_dna_no_write_{TS}'
LATEST = AUDIT / 'v286_rolling_period_stock_dna_latest.json'
TEST_START = datetime(2024, 1, 1)
TEST_END = datetime(2026, 12, 31)


def sf(x: Any, d: float = math.nan) -> float:
    try:
        if x is None or x == '': return d
        v = float(x)
        return v if not math.isnan(v) else d
    except Exception:
        return d


def parse_date(s: str) -> datetime:
    return datetime.strptime(str(s)[:8], '%Y%m%d')


def ym(dt: datetime) -> str:
    return dt.strftime('%Y-%m')


def next_month(dt: datetime) -> datetime:
    return datetime(dt.year + (dt.month == 12), 1 if dt.month == 12 else dt.month + 1, 1)


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


def row_keys(r: dict[str, Any]) -> list[tuple[str, str]]:
    fam, reg = str(r['family']), str(r['regime'])
    risk = bucket_risk(sf(r.get('risk')))
    liq = bucket_liq(sf(r.get('liq_age')))
    delay = bucket_delay(sf(r.get('reaction_delay')))
    rng = bucket_range(sf(r.get('range60')))
    volenv = str(r.get('vol_env') or 'VOLENV_NA')
    volr = bucket_vol_ratio(sf(r.get('vol_ratio')))
    disp = 'DISP_Y' if str(r.get('displacement')) == 'True' else 'DISP_N'
    return [
        ('family', fam),
        ('family_regime', f'{fam}|{reg}'),
        ('family_regime_risk', f'{fam}|{reg}|{risk}'),
        ('family_regime_liq_risk', f'{fam}|{reg}|{liq}|{risk}'),
        ('family_regime_delay', f'{fam}|{reg}|{delay}'),
        ('family_regime_range_risk', f'{fam}|{reg}|{rng}|{risk}'),
        ('family_regime_vol', f'{fam}|{reg}|{volenv}'),
        ('family_regime_volr', f'{fam}|{reg}|{volr}'),
        ('family_regime_disp_risk', f'{fam}|{reg}|{disp}|{risk}'),
    ]


def blank() -> dict[str, Any]:
    return {'n': 0, 'wins': 0, 'sum': 0.0, 'loss': 0, 'tp': 0, 'sl': 0, 'time': 0,
            'micro': 0, 'months': defaultdict(lambda: [0, 0]), 'years': defaultdict(lambda: [0, 0]), 'symbols': set()}


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'), 0.0); reason = str(r.get('reason') or '')
    a['n'] += 1; a['wins'] += pnl > 0; a['sum'] += pnl; a['loss'] += pnl <= 0
    a['tp'] += reason == 'TP'; a['sl'] += reason == 'SL'; a['time'] += reason.startswith('TIME')
    a['micro'] += 0 < pnl < 1; a['symbols'].add(r['symbol'])
    a['months'][r['month']][0] += 1; a['months'][r['month']][1] += pnl > 0
    a['years'][str(r['year'])][0] += 1; a['years'][str(r['year'])][1] += pnl > 0


def metrics(a: dict[str, Any], stock_count: int) -> dict[str, Any]:
    n = int(a['n'])
    if not n: return {'n': 0}
    mwr = {m: round(v[1] / v[0] * 100, 2) for m, v in sorted(a['months'].items()) if v[0]}
    mcnt = {m: int(v[0]) for m, v in sorted(a['months'].items()) if v[0]}
    ywr = {y: round(v[1] / v[0] * 100, 2) for y, v in sorted(a['years'].items()) if v[0]}
    ycnt = {y: int(v[0]) for y, v in sorted(a['years'].items()) if v[0]}
    return {
        'n': n, 'wr': round(a['wins'] / n * 100, 4), 'avg': round(a['sum'] / n, 4),
        'loss': int(a['loss']), 'micro': round(a['micro'] / n * 100, 2),
        'tp_pct': round(a['tp'] / n * 100, 2), 'sl_pct': round(a['sl'] / n * 100, 2),
        'time_pct': round(a['time'] / n * 100, 2), 'symbols': len(a['symbols']),
        'per_stock_all_stocks': round(n / stock_count, 4), 'month_count': len(mcnt),
        'min_month_n': min(mcnt.values()) if mcnt else 0,
        'min_month_wr': round(min(mwr.values()) if mwr else 0, 2),
        'year_counts': ycnt, 'year_wr': ywr,
        'min_year_n': min(ycnt.values()) if ycnt else 0,
        'min_year_wr': round(min(ywr.values()) if ywr else 0, 2),
    }


def train_stat(rows: list[dict[str, Any]], start: datetime, end: datetime, per_symbol: bool) -> dict[tuple, list[float]]:
    out: dict[tuple, list[float]] = defaultdict(lambda: [0, 0, 0.0])
    for r in rows:
        if not (start <= r['dt'] < end):
            continue
        pnl = sf(r['pnl'], 0.0)
        for dim, val in r['keys']:
            key = (r['symbol'], dim, val) if per_symbol else (dim, val)
            st = out[key]; st[0] += 1; st[1] += pnl > 0; st[2] += pnl
    return out


def fit_from_stats(stats: dict[tuple, list[float]], grid: dict[str, Any], per_symbol: bool) -> dict[str, tuple[str, str, dict[str, Any]]]:
    fits: dict[str, tuple[str, str, dict[str, Any]]] = {}
    best = None
    for key, st in stats.items():
        n, wins, total = int(st[0]), int(st[1]), float(st[2])
        min_n = grid['min_n'] if per_symbol else max(grid['min_n'] * 25, 80)
        if n < min_n:
            continue
        wr, avg = wins / n * 100, total / n
        if wr < grid['min_wr'] or avg < grid['min_avg']:
            continue
        m = {'n': n, 'wr': round(wr, 4), 'avg': round(avg, 4), 'score': (avg, wr, math.log1p(n))}
        if per_symbol:
            sym, dim, val = key
            old = fits.get(sym)
            if old is None or m['score'] > old[2]['score']:
                fits[sym] = (dim, val, m)
        else:
            dim, val = key
            if best is None or m['score'] > best[2]['score']:
                best = (dim, val, m)
    if not per_symbol and best:
        return {'__GLOBAL__': best}
    return fits


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    with EVENTS.open() as fh:
        for r in csv.DictReader(fh):
            dt = parse_date(r['entry_date'])
            if dt.year not in {2023, 2024, 2025, 2026}:
                continue
            rr = dict(r); rr['dt'] = dt; rr['month'] = ym(dt); rr['keys'] = row_keys(rr)
            rows.append(rr)
    rows.sort(key=lambda r: (r['dt'], r['symbol'], r['family']))
    stock_count = len({r['symbol'] for r in rows})
    rows_by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        rows_by_month[r['month']].append(r)

    raw_test = blank()
    for r in rows:
        if TEST_START <= r['dt'] <= TEST_END:
            add(raw_test, r)

    months = []
    cur, last_dt = TEST_START, min(TEST_END, max(r['dt'] for r in rows))
    while cur <= last_dt:
        months.append(cur); cur = next_month(cur)

    grids = [
        {'name': 'fast_90d_n2_wr55_avgpos', 'days': 90, 'min_n': 2, 'min_wr': 55.0, 'min_avg': 0.0},
        {'name': 'medium_180d_n3_wr52_avgpos', 'days': 180, 'min_n': 3, 'min_wr': 52.0, 'min_avg': 0.0},
        {'name': 'slow_360d_n5_wr50_avgpos', 'days': 360, 'min_n': 5, 'min_wr': 50.0, 'min_avg': 0.0},
        {'name': 'pnl_180d_n3_wr50_avg05', 'days': 180, 'min_n': 3, 'min_wr': 50.0, 'min_avg': 0.5},
    ]

    selected_rows_path = OUT / 'v286_selected_rows.csv'
    selector_results = []
    with selected_rows_path.open('w', newline='') as fh:
        fieldnames = [k for k in rows[0].keys() if k not in {'dt', 'keys'}] + [
            'selector_type', 'grid', 'train_start', 'train_end', 'selected_dim', 'selected_value', 'train_n', 'train_wr', 'train_avg'
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames); writer.writeheader()
        for grid in grids:
            for selector_type, per_symbol in [('rolling_stock_dna', True), ('rolling_global_rule', False)]:
                agg = blank(); by_month = defaultdict(blank); selected_counts = {}; selected_rule_hist = defaultdict(int)
                for ms in months:
                    me = next_month(ms); train_start = ms - timedelta(days=grid['days'])
                    stats = train_stat(rows, train_start, ms, per_symbol)
                    fits = fit_from_stats(stats, grid, per_symbol)
                    selected_counts[ym(ms)] = len(fits)
                    for r in rows_by_month.get(ym(ms), []):
                        fit = fits.get(r['symbol']) if per_symbol else fits.get('__GLOBAL__')
                        if not fit:
                            continue
                        dim, val, tm = fit
                        if (dim, val) not in r['keys']:
                            continue
                        add(agg, r); add(by_month[ym(ms)], r); selected_rule_hist[(dim, val)] += 1
                        writer.writerow({k: v for k, v in r.items() if k not in {'dt', 'keys'}} | {
                            'selector_type': selector_type, 'grid': grid['name'],
                            'train_start': train_start.strftime('%Y%m%d'), 'train_end': (ms - timedelta(days=1)).strftime('%Y%m%d'),
                            'selected_dim': dim, 'selected_value': val, 'train_n': tm['n'], 'train_wr': tm['wr'], 'train_avg': tm['avg'],
                        })
                selector_results.append({
                    'selector_type': selector_type, 'grid': grid,
                    'selected_rules_or_symbols_by_month': selected_counts,
                    'walk_forward': metrics(agg, stock_count),
                    'monthly_metrics': {m: metrics(a, stock_count) for m, a in sorted(by_month.items())},
                    'top_selected_rules_in_test_rows': [
                        {'dim': k[0], 'value': k[1], 'n': v}
                        for k, v in sorted(selected_rule_hist.items(), key=lambda x: x[1], reverse=True)[:20]
                    ],
                })

    design_audit = {
        'current_combination_scheme_v280': [
            'REV_SSL_CHOCH_OB: SSL sweep -> confirmed swing-high break/displacement -> true bearish candle OB -> touch+reclaim -> next-day entry',
            'UP_CONT_BOS_OB: confirmed swing-high BOS/displacement -> true bearish candle OB -> touch+reclaim -> next-day entry',
            'ABSORB_SSL_FAST_MSS: SSL sweep -> local 5-bar MSS -> last bearish candle POI -> next-day entry',
            'RANGE_LOW_SWEEP_RECLAIM: RANGE regime -> range-low SSL sweep/reclaim -> same-bar POI -> next-day entry',
        ],
        'interval_adaptation_status': 'PARTIAL: V279/V280 adapt liq_win and wait from each stock pre-event swing_gap. V285/V286 select bucketed liq_age/reaction_delay/range/risk, but do not yet learn continuous per-stock interval parameters.',
        'multi_timeframe_status': 'TESTED_NOT_SOLVED: V283 coarse 60m overlay and V284 60m sequence were overlays on daily zones; both failed. Same-source 60m-first generator is not yet implemented.',
        'rolling_period_dna_status': 'THIS_SCRIPT_TESTS: rolling 90/180/360-day per-stock and global rule selection for next-month rows using only prior-window outcomes.',
        'smc_theory_gap': 'Existing DNA is mostly historical rule-performance + simple pre-entry buckets. It lacks explicit operator lifecycle state: accumulation/manipulation/distribution, active POI family, rhythm shift, and same-source lower-timeframe takeover POI.',
    }
    summary = {
        'version': 'V286_ROLLING_PERIOD_STOCK_DNA_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'inputs': {'events': str(EVENTS), 'rows': len(rows), 'symbols': stock_count, 'test_months': [ym(m) for m in months]},
        'design_audit': design_audit,
        'raw_v280_test_2024_2026': metrics(raw_test, stock_count),
        'rolling_selectors': selector_results,
        'artifacts': {'selected_rows': str(selected_rows_path)},
        'decision': 'NO_PRODUCTION_WRITE__ROLLING_PERIOD_DNA_RESEARCH_ONLY',
    }
    (OUT / 'v286_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:18000])


if __name__ == '__main__':
    main()
