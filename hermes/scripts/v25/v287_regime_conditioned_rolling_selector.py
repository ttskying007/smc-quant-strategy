#!/usr/bin/env python3
"""V287 no-write audit: regime-conditioned rolling selector on V280 temporal grammar.

Purpose: continue Lei's requested closed-loop research after V285/V286.
Test whether a parent market/industry participation regime can choose which SMC
story family / interval bucket works in the next month, using only pre-entry and
prior-window data.

No production/frontend/watchlist writes.
"""
from __future__ import annotations

import bisect, csv, json, math
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
OUT = AUDIT / f'v287_regime_conditioned_rolling_no_write_{TS}'
LATEST = AUDIT / 'v287_regime_conditioned_rolling_latest.json'
TEST_START = datetime(2024, 1, 1)
TEST_END = datetime(2026, 12, 31)


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


def parse_date(s: str) -> datetime:
    return datetime.strptime(str(s)[:8], '%Y%m%d')


def ym(dt: datetime) -> str:
    return dt.strftime('%Y-%m')


def next_month(dt: datetime) -> datetime:
    return datetime(dt.year + (dt.month == 12), 1 if dt.month == 12 else dt.month + 1, 1)


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
    if x < 10: return 'REL0_10'
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


def load_industry_map() -> dict[str, str]:
    items = json.loads(INDMAP.read_text())
    out: dict[str, str] = {}
    for r in items:
        sym = r.get('symbol'); ind = r.get('industry') or ''
        if sym and ind:
            out[sym] = ind
    return out


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
            d = dn(b.get('t') or b.get('date')); c = sf(b.get('c'))
            if d and not math.isnan(c):
                seq.append((d, c))
        seq.sort()
        for i in range(1, len(seq)):
            d, c = seq[i]; pc = seq[i-1][1]
            if pc > 0:
                ret = (c / pc - 1) * 100
                daily[d].append((sym, ind, ret))
                ind_daily[d][ind].append(ret)
    dates = sorted(daily)
    mkt_by_date: dict[str, dict[str, float]] = {}
    ind_by_date: dict[tuple[str, str], dict[str, float]] = {}
    for d, rows in daily.items():
        vals = [r[2] for r in rows]
        mkt_by_date[d] = {
            'mkt_n': len(vals),
            'mkt_up_pct': sum(v > 0 for v in vals) / len(vals) * 100,
            'mkt_med_ret': median(vals),
            'mkt_strong1_pct': sum(v > 1 for v in vals) / len(vals) * 100,
        }
    for d, mp in ind_daily.items():
        for ind, vals in mp.items():
            if len(vals) < 5:
                continue
            ind_by_date[(d, ind)] = {
                'ind_n': len(vals),
                'ind_up_pct': sum(v > 0 for v in vals) / len(vals) * 100,
                'ind_med_ret': median(vals),
                'ind_strong1_pct': sum(v > 1 for v in vals) / len(vals) * 100,
            }
    def prev_date(d: str) -> str:
        i = bisect.bisect_left(dates, d) - 1
        return dates[i] if i >= 0 else ''
    return prev_date, mkt_by_date, ind_by_date


def blank() -> dict[str, Any]:
    return {'n': 0, 'wins': 0, 'sum': 0.0, 'loss': 0, 'tp': 0, 'sl': 0, 'time': 0,
            'micro': 0, 'months': defaultdict(lambda: [0, 0]), 'years': defaultdict(lambda: [0, 0]), 'symbols': set()}


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'), 0.0); reason = str(r.get('reason') or '')
    a['n'] += 1; a['wins'] += pnl > 0; a['sum'] += pnl
    a['loss'] += pnl <= 0; a['micro'] += 0 < pnl < 1
    a['tp'] += reason == 'TP'; a['sl'] += reason == 'SL'; a['time'] += reason.startswith('TIME')
    a['symbols'].add(r['symbol'])
    a['months'][r['month']][0] += 1; a['months'][r['month']][1] += pnl > 0
    a['years'][str(r['year'])][0] += 1; a['years'][str(r['year'])][1] += pnl > 0


def metrics(a: dict[str, Any], stock_count: int) -> dict[str, Any]:
    n = int(a['n'])
    if not n:
        return {'n': 0}
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
        'month_counts': mcnt, 'month_wr': mwr,
        'year_counts': ycnt, 'year_wr': ywr,
        'min_year_n': min(ycnt.values()) if ycnt else 0,
        'min_year_wr': round(min(ywr.values()) if ywr else 0, 2),
    }


def row_keys(r: dict[str, Any]) -> list[tuple[str, str]]:
    fam, reg = r['family'], r['regime']
    risk = bucket_risk(sf(r.get('risk')))
    liq = bucket_liq(sf(r.get('liq_age')))
    delay = bucket_delay(sf(r.get('reaction_delay')))
    rng = bucket_range(sf(r.get('range60')))
    volenv = str(r.get('vol_env') or 'VOL_NA')
    mret = bucket_ret(sf(r.get('prev_mkt_med_ret')))
    iret = bucket_ret(sf(r.get('prev_ind_med_ret')))
    mup = bucket_up(sf(r.get('prev_mkt_up_pct')))
    iup = bucket_up(sf(r.get('prev_ind_up_pct')))
    relret = bucket_rel(sf(r.get('prev_ind_vs_mkt_med_ret')))
    parent = f'MRET={mret}|IRET={iret}|MUP={mup}|IUP={iup}'
    compact_parent = f'MRET={mret}|IRET={iret}'
    return [
        ('parent_family', f'{compact_parent}|{fam}'),
        ('parent_family_regime', f'{compact_parent}|{fam}|{reg}'),
        ('parent_family_risk', f'{compact_parent}|{fam}|{risk}'),
        ('parent_family_regime_risk', f'{compact_parent}|{fam}|{reg}|{risk}'),
        ('parent_family_liq_risk', f'{compact_parent}|{fam}|{liq}|{risk}'),
        ('parent_family_range_risk', f'{compact_parent}|{fam}|{rng}|{risk}'),
        ('parent_family_delay', f'{compact_parent}|{fam}|{delay}'),
        ('parent_family_vol', f'{compact_parent}|{fam}|{volenv}'),
        ('parent_full_family_regime_risk', f'{parent}|{fam}|{reg}|{risk}'),
        ('parent_relret_family_regime_risk', f'{compact_parent}|RELRET={relret}|{fam}|{reg}|{risk}'),
    ]


def train_stats(rows: list[dict[str, Any]], start: datetime, end: datetime) -> dict[tuple[str, str], list[float]]:
    out: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0, 0, 0.0])
    for r in rows:
        if not (start <= r['dt'] < end):
            continue
        pnl = sf(r.get('pnl'), 0.0)
        for dim, val in r['keys']:
            st = out[(dim, val)]
            st[0] += 1; st[1] += pnl > 0; st[2] += pnl
    return out


def fit_rules(stats: dict[tuple[str, str], list[float]], grid: dict[str, Any]) -> dict[tuple[str, str], dict[str, float]]:
    fits = {}
    for key, st in stats.items():
        n, wins, total = int(st[0]), int(st[1]), float(st[2])
        if n < grid['min_n']:
            continue
        wr = wins / n * 100; avg = total / n
        if wr >= grid['min_wr'] and avg >= grid['min_avg']:
            fits[key] = {'n': n, 'wr': round(wr, 4), 'avg': round(avg, 4), 'score': avg * 10 + wr + math.log1p(n)}
    # keep top K rules to prevent accidental broad overfit fan-out
    top = sorted(fits.items(), key=lambda kv: (kv[1]['score'], kv[1]['n']), reverse=True)[:grid['top_k']]
    return dict(top)


def loss_decomp(rows: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    ag = defaultdict(blank)
    for r in rows:
        if sf(r.get('pnl'), 0.0) > 0:
            continue
        for k in [
            ('family', r['family']),
            ('family_regime', f"{r['family']}|{r['regime']}"),
            ('reason', str(r.get('reason'))),
            ('mkt_ind', f"{bucket_ret(sf(r.get('prev_mkt_med_ret')))}|{bucket_ret(sf(r.get('prev_ind_med_ret')))}"),
            ('risk', bucket_risk(sf(r.get('risk')))),
        ]:
            add(ag[k], r)
    out = []
    for (dim, val), a in ag.items():
        if a['n'] >= 10:
            out.append({'dimension': dim, 'value': val, **metrics(a, 1)})
    out.sort(key=lambda x: (x['n'], x['sl_pct']), reverse=True)
    return out[:limit]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sym_ind = load_industry_map()
    prev_date, mkt_by_date, ind_by_date = build_prev_features(sym_ind)
    rows: list[dict[str, Any]] = []
    with EVENTS.open(newline='') as fh:
        for r in csv.DictReader(fh):
            dt = parse_date(r['entry_date'])
            if dt.year not in {2023, 2024, 2025, 2026}:
                continue
            sym = r['symbol']; d = dn(r['entry_date']); ind = sym_ind.get(sym, 'UNKNOWN')
            pd = prev_date(d)
            nr = dict(r)
            nr['dt'] = dt; nr['month'] = ym(dt); nr['industry'] = ind; nr['prev_date'] = pd
            nr.update({f'prev_{k}': v for k, v in mkt_by_date.get(pd, {}).items()})
            nr.update({f'prev_{k}': v for k, v in ind_by_date.get((pd, ind), {}).items()})
            nr['prev_ind_vs_mkt_up'] = sf(nr.get('prev_ind_up_pct')) - sf(nr.get('prev_mkt_up_pct'))
            nr['prev_ind_vs_mkt_med_ret'] = sf(nr.get('prev_ind_med_ret')) - sf(nr.get('prev_mkt_med_ret'))
            nr['keys'] = row_keys(nr)
            rows.append(nr)
    rows.sort(key=lambda x: (x['dt'], x['symbol'], x['family']))
    stock_count = len({r['symbol'] for r in rows})
    raw_test = blank()
    for r in rows:
        if TEST_START <= r['dt'] <= TEST_END:
            add(raw_test, r)

    months = []
    cur, last_dt = TEST_START, min(TEST_END, max(r['dt'] for r in rows))
    while cur <= last_dt:
        months.append(cur); cur = next_month(cur)

    grids = [
        {'name': 'parent_180d_n80_wr58_avg1_top20', 'days': 180, 'min_n': 80, 'min_wr': 58.0, 'min_avg': 1.0, 'top_k': 20},
        {'name': 'parent_360d_n120_wr56_avg1_top30', 'days': 360, 'min_n': 120, 'min_wr': 56.0, 'min_avg': 1.0, 'top_k': 30},
        {'name': 'parent_540d_n180_wr54_avg1_top40', 'days': 540, 'min_n': 180, 'min_wr': 54.0, 'min_avg': 1.0, 'top_k': 40},
        {'name': 'parent_360d_n80_wr60_avg2_top20', 'days': 360, 'min_n': 80, 'min_wr': 60.0, 'min_avg': 2.0, 'top_k': 20},
    ]
    selected_path = OUT / 'v287_selected_rows.csv'
    fieldnames = [k for k in rows[0].keys() if k not in {'dt', 'keys'}] + ['selector_grid', 'selected_dim', 'selected_value', 'train_n', 'train_wr', 'train_avg']
    selector_results = []
    with selected_path.open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames); w.writeheader()
        for grid in grids:
            sel_agg = blank(); by_month = {}; selected_count = {}; selected_rows = []
            for m0 in months:
                start, end = m0.replace(day=1), next_month(m0)
                train_start = datetime.fromordinal(start.toordinal() - grid['days'])
                rules = fit_rules(train_stats(rows, train_start, start), grid)
                selected_count[ym(start)] = len(rules)
                month_agg = blank()
                for r in rows:
                    if not (start <= r['dt'] < end):
                        continue
                    hit = None
                    for key in r['keys']:
                        if key in rules:
                            hit = key; break
                    if not hit:
                        continue
                    add(sel_agg, r); add(month_agg, r); selected_rows.append(r)
                    out = {k: r.get(k) for k in fieldnames}
                    out.update({'selector_grid': grid['name'], 'selected_dim': hit[0], 'selected_value': hit[1],
                                'train_n': rules[hit]['n'], 'train_wr': rules[hit]['wr'], 'train_avg': rules[hit]['avg']})
                    w.writerow(out)
                by_month[ym(start)] = metrics(month_agg, stock_count)
            selector_results.append({
                'grid': grid,
                'selected_rule_count_by_month': selected_count,
                'walk_forward': metrics(sel_agg, stock_count),
                'monthly_metrics': by_month,
                'loss_decomp': loss_decomp(selected_rows),
            })

    # non-walk-forward descriptive frontier: reveals whether parent features can ever form stable pockets.
    surface_aggs = defaultdict(blank)
    for r in rows:
        if not (TEST_START <= r['dt'] <= TEST_END):
            continue
        for key in r['keys']:
            add(surface_aggs[key], r)
    surfaces = []
    for (dim, val), a in surface_aggs.items():
        m = metrics(a, stock_count)
        if m['n'] >= 100:
            surfaces.append({'dimension': dim, 'value': val, **m})
    surfaces.sort(key=lambda x: (x['min_year_wr'], x['wr'], x['avg'], x['n']), reverse=True)

    summary = {
        'version': 'V287_REGIME_CONDITIONED_ROLLING_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source_events': str(EVENTS), 'industry_map': str(INDMAP), 'rows': len(rows), 'symbols': stock_count,
        'design': {
            'hypothesis': 'Parent market/industry participation regime should choose SMC family/rhythm for the next month.',
            'non_leakage': 'prev market/industry features use previous trading day; rolling selector trains only before each test month.',
            'scope': 'Research/no-write only; no production/frontend/watchlist mutation.',
        },
        'raw_v280_test_2024_2026': metrics(raw_test, stock_count),
        'rolling_selectors': selector_results,
        'top_descriptive_parent_surfaces': surfaces[:40],
        'artifacts': {'selected_rows': str(selected_path), 'out_dir': str(OUT)},
    }
    (OUT / 'v287_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({
        'latest': str(LATEST), 'out': str(OUT), 'raw': summary['raw_v280_test_2024_2026'],
        'selectors': [{'grid': x['grid']['name'], 'wf': x['walk_forward']} for x in selector_results],
        'top_surface': surfaces[:5],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
