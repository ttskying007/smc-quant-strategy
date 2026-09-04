#!/usr/bin/env python3
"""V307 no-write: true industry leadership transmission audit.

V306 found that industry-led opening gaps are the strongest state layer, but
coverage was concentrated in 202605/202606. This audit tests the next concrete
branch: whether the candidate's industry is a true entry-day first120 15m leader
(ret/up/amount ranks across all industries), and whether the candidate stock
participates in that leader move.
"""
from __future__ import annotations

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
K15 = BASE / 'kline_cache_15min'
INDUSTRY_JSON = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854' / 'baostock_stock_industry.json'
V306_LATEST = AUDIT / 'v306_opening_gap_source_latest.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v307_industry_leadership_transmission_no_write_{TS}'
LATEST = AUDIT / 'v307_industry_leadership_transmission_latest.json'


def sf(x: Any, d: float = math.nan) -> float:
    try:
        if x is None or x == '':
            return d
        v = float(x)
        return v if not math.isnan(v) else d
    except Exception:
        return d


def dn(x: Any) -> str:
    s = str(x or '')
    return s[:8] if len(s) >= 8 else ''


def load_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def load_industry_map() -> dict[str, str]:
    x = load_json(INDUSTRY_JSON)
    out: dict[str, str] = {}
    if isinstance(x, list):
        for r in x:
            sym = str(r.get('symbol') or '')
            ind = str(r.get('industry') or '').strip() or 'UNKNOWN'
            if sym:
                out[sym] = ind
    return out


def sym_from_15_path(p: Path) -> str:
    parts = p.name.split('_')
    if len(parts) < 3:
        return ''
    return f'{parts[0]}.{parts[1]}'


def bucket(x: float, cuts: list[tuple[float, str]], last: str) -> str:
    if math.isnan(x):
        return 'NA'
    for c, name in cuts:
        if x < c:
            return name
    return last


def b_rank(x: float) -> str:
    return bucket(x, [(20, 'TOP<=20'), (40, 'TOP20_40'), (60, 'MID40_60'), (80, 'LOW60_80')], 'LOW>80')


def b_ret(x: float) -> str:
    return bucket(x, [(-1, 'RET<-1'), (0, 'RET-1_0'), (1, 'RET0_1'), (2, 'RET1_2')], 'RET>=2')


def b_up(x: float) -> str:
    return bucket(x, [(45, 'UP<45'), (55, 'UP45_55'), (65, 'UP55_65')], 'UP>=65')


def b_amt_rank(x: float) -> str:
    return bucket(x, [(20, 'AMT_TOP20'), (40, 'AMT20_40'), (60, 'AMT40_60')], 'AMT_LOW')


def day_groups(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    g: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for b in rows:
        d = dn(b.get('d') or b.get('t'))
        if d:
            g[d].append(b)
    for arr in g.values():
        arr.sort(key=lambda r: str(r.get('t') or ''))
    return g


def build_leadership(needed_dates: set[str], industry: dict[str, str]) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    stock_feat: dict[tuple[str, str], dict[str, Any]] = {}
    ind_date_members: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    k15_files = list(K15.glob('*_15min_800.json'))
    for p in k15_files:
        sym = sym_from_15_path(p)
        ind = industry.get(sym, 'UNKNOWN')
        if not sym or ind == 'UNKNOWN':
            continue
        x = load_json(p)
        if not isinstance(x, list):
            continue
        groups = day_groups(x)
        for d in needed_dates:
            rows = groups.get(d)
            if not rows or len(rows) < 8:
                continue
            o0 = sf(rows[0].get('o'))
            if o0 <= 0:
                continue
            part4, part8 = rows[:4], rows[:8]
            c4, c8 = sf(part4[-1].get('c')), sf(part8[-1].get('c'))
            if c4 <= 0 or c8 <= 0:
                continue
            amt4 = sum(sf(b.get('v'), 0.0) * sf(b.get('c'), 0.0) for b in part4)
            amt8 = sum(sf(b.get('v'), 0.0) * sf(b.get('c'), 0.0) for b in part8)
            f = {
                'symbol': sym, 'industry': ind, 'date': d,
                's60_ret': (c4 / o0 - 1) * 100,
                's120_ret': (c8 / o0 - 1) * 100,
                's120_amt': amt8,
                's120_green': c8 >= o0,
                's60_green': c4 >= o0,
                's120_low_dd': (min(sf(b.get('l')) for b in part8) / o0 - 1) * 100,
                's120_push': (max(sf(b.get('h')) for b in part8) / o0 - 1) * 100,
            }
            stock_feat[(sym, d)] = f
            ind_date_members[(d, ind)].append(f)

    ind_feat: dict[tuple[str, str], dict[str, Any]] = {}
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (d, ind), arr in ind_date_members.items():
        if len(arr) < 5:
            continue
        rets = [sf(r['s120_ret']) for r in arr]
        amt = sum(sf(r['s120_amt'], 0.0) for r in arr)
        feat = {
            'date': d, 'industry': ind, 'n_members': len(arr),
            'ind120_ret_med': median(rets),
            'ind120_up': 100 * sum(r >= 0 for r in rets) / len(rets),
            'ind120_hot': 100 * sum(r >= 1 for r in rets) / len(rets),
            'ind120_amt': amt,
        }
        ind_feat[(d, ind)] = feat
        by_date[d].append(feat)

    for d, arr in by_date.items():
        ret_sorted = sorted(arr, key=lambda x: x['ind120_ret_med'], reverse=True)
        up_sorted = sorted(arr, key=lambda x: x['ind120_up'], reverse=True)
        amt_sorted = sorted(arr, key=lambda x: x['ind120_amt'], reverse=True)
        n = len(arr)
        for i, f in enumerate(ret_sorted, 1):
            f['ind_ret_rank'] = i
            f['ind_ret_pct_rank'] = 100 * i / n
        for i, f in enumerate(up_sorted, 1):
            f['ind_up_rank'] = i
            f['ind_up_pct_rank'] = 100 * i / n
        for i, f in enumerate(amt_sorted, 1):
            f['ind_amt_rank'] = i
            f['ind_amt_pct_rank'] = 100 * i / n

    meta = {'k15_files': len(k15_files), 'stock_date_features': len(stock_feat), 'industry_date_features': len(ind_feat), 'dates_with_industries': len(by_date)}
    return stock_feat, ind_feat, meta


def blank() -> dict[str, Any]:
    return {'n': 0, 'win': 0, 'pnl': 0.0, 'loss': 0, 'tp': 0, 'sl': 0, 'gap_sl': 0, 'time': 0, 'micro': 0, 'symbols': set(), 'months': defaultdict(lambda: {'n': 0, 'win': 0})}


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'))
    a['n'] += 1
    a['pnl'] += pnl
    a['win'] += int(pnl > 0)
    a['loss'] += int(pnl <= 0)
    a['micro'] += int(0 < pnl < 0.6)
    reason = str(r.get('reason') or '')
    a['tp'] += int(reason == 'TP')
    a['sl'] += int(reason == 'SL')
    a['gap_sl'] += int(reason == 'GAP_SL')
    a['time'] += int(reason.startswith('TIME'))
    a['symbols'].add(str(r.get('symbol') or ''))
    m = str(r.get('month') or '')
    a['months'][m]['n'] += 1
    a['months'][m]['win'] += int(pnl > 0)


def metrics(a: dict[str, Any]) -> dict[str, Any]:
    n = a['n']
    if n <= 0:
        return {'n': 0}
    mw = {m: round(100 * v['win'] / v['n'], 2) for m, v in sorted(a['months'].items()) if v['n']}
    mc = {m: v['n'] for m, v in sorted(a['months'].items()) if v['n']}
    return {
        'n': n, 'wr': round(100 * a['win'] / n, 4), 'avg': round(a['pnl'] / n, 4),
        'loss': a['loss'], 'micro': round(100 * a['micro'] / n, 2),
        'tp_pct': round(100 * a['tp'] / n, 2), 'sl_pct': round(100 * a['sl'] / n, 2),
        'gap_sl_pct': round(100 * a['gap_sl'] / n, 2), 'time_pct': round(100 * a['time'] / n, 2),
        'symbols': len(a['symbols']), 'month_count': len(mc), 'month_counts': mc, 'month_wr': mw,
        'min_month_n': min(mc.values()) if mc else 0, 'min_month_wr': min(mw.values()) if mw else None,
        't1_violations': 0,
    }


def top_groups(rows: list[dict[str, Any]], dims: list[str], min_n: int = 80) -> list[dict[str, Any]]:
    out = []
    for dim in dims:
        g: dict[str, dict[str, Any]] = defaultdict(blank)
        for r in rows:
            v = str(r.get(dim) or '')
            if v and v != 'NA':
                add(g[v], r)
        for v, a in g.items():
            m = metrics(a)
            if m['n'] >= min_n:
                m['dimension'] = dim
                m['value'] = v
                out.append(m)
    out.sort(key=lambda x: (x.get('min_month_wr') or -999, x['wr'], x['avg'], x['n']), reverse=True)
    return out[:80]


def top_combos(rows: list[dict[str, Any]], combos: list[list[str]], min_n: int = 80) -> list[dict[str, Any]]:
    out = []
    for ds in combos:
        g: dict[str, dict[str, Any]] = defaultdict(blank)
        for r in rows:
            vals = [str(r.get(d) or '') for d in ds]
            if all(vals) and 'NA' not in vals:
                add(g['|'.join(vals)], r)
        for k, a in g.items():
            m = metrics(a)
            if m['n'] >= min_n:
                m['combo'] = '+'.join(ds)
                m['value'] = k
                out.append(m)
    out.sort(key=lambda x: (x.get('min_month_wr') or -999, x['wr'], x['avg'], x['n']), reverse=True)
    return out[:120]


def main() -> None:
    src = load_json(V306_LATEST)
    if not isinstance(src, dict):
        raise RuntimeError(f'cannot read V306 summary: {V306_LATEST}')
    rows_path = Path(str(src.get('artifacts', {}).get('rows') or ''))
    if not rows_path.exists():
        raise RuntimeError(f'cannot locate V306 rows from {V306_LATEST}')
    rows: list[dict[str, Any]] = []
    needed_dates: set[str] = set()
    with rows_path.open() as fh:
        for r in csv.DictReader(fh):
            if str(r.get('t1_violation')).lower() == 'true':
                continue
            rows.append(dict(r))
            needed_dates.add(str(r.get('entry_date') or ''))
    industry = load_industry_map()
    stock_feat, ind_feat, meta = build_leadership(needed_dates, industry)
    enriched: list[dict[str, Any]] = []
    missing = 0
    for r in rows:
        sym = str(r.get('symbol'))
        d = str(r.get('entry_date'))
        ind = industry.get(sym, 'UNKNOWN')
        sf0 = stock_feat.get((sym, d))
        inf = ind_feat.get((d, ind))
        if not sf0 or not inf:
            missing += 1
            continue
        rr = dict(r)
        rr['industry'] = ind
        rr['s120_ret2'] = sf0['s120_ret']
        rr['s120_dd2'] = sf0['s120_low_dd']
        rr['s120_push2'] = sf0['s120_push']
        rr['candidate_participation'] = 'PARTICIPATE' if sf0['s120_ret'] >= 0 and sf0['s120_low_dd'] > -1.5 else 'FADE_OR_DD'
        for k in ['ind120_ret_med', 'ind120_up', 'ind120_hot', 'ind120_amt', 'ind_ret_rank', 'ind_up_rank', 'ind_amt_rank', 'ind_ret_pct_rank', 'ind_up_pct_rank', 'ind_amt_pct_rank']:
            rr[k] = inf[k]
        rr['ind_ret_rank_bucket'] = b_rank(sf(inf['ind_ret_pct_rank']))
        rr['ind_up_rank_bucket'] = b_rank(sf(inf['ind_up_pct_rank']))
        rr['ind_amt_rank_bucket'] = b_amt_rank(sf(inf['ind_amt_pct_rank']))
        rr['ind120_ret_bucket'] = b_ret(sf(inf['ind120_ret_med']))
        rr['ind120_up_bucket2'] = b_up(sf(inf['ind120_up']))
        leader = sf(inf['ind_ret_pct_rank']) <= 20 or sf(inf['ind_up_pct_rank']) <= 20
        rr['industry_leader_state'] = 'LEADER_TOP20' if leader else ('LEADER_TOP40' if sf(inf['ind_ret_pct_rank']) <= 40 or sf(inf['ind_up_pct_rank']) <= 40 else 'NON_LEADER')
        rr['leader_transmission'] = f"{rr['industry_leader_state']}|{rr['candidate_participation']}"
        enriched.append(rr)

    base = blank()
    for r in enriched:
        add(base, r)
    dims = ['industry_leader_state', 'candidate_participation', 'leader_transmission', 'ind_ret_rank_bucket', 'ind_up_rank_bucket', 'ind_amt_rank_bucket', 'ind120_ret_bucket', 'ind120_up_bucket2', 'gap_source', 'gap_morning_class']
    combos = [
        ['industry_leader_state', 'candidate_participation'],
        ['leader_transmission', 'gap_source'],
        ['leader_transmission', 'risk2_bucket'],
        ['leader_transmission', 'acc_bucket', 'sweep_bucket'],
        ['ind_ret_rank_bucket', 'ind_up_rank_bucket', 'candidate_participation'],
        ['ind_ret_rank_bucket', 'gap_source', 'candidate_participation'],
        ['ind_up_rank_bucket', 'gap_source', 'risk2_bucket'],
        ['industry_leader_state', 'gap_source', 'm120_iup_bucket'],
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    out_rows = OUT / 'v307_rows.csv'
    fieldnames = sorted(set().union(*(r.keys() for r in enriched))) if enriched else []
    with out_rows.open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(enriched)
    summary = {
        'version': 'V307_INDUSTRY_LEADERSHIP_TRANSMISSION_NO_WRITE',
        'created_at': TS,
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'hypothesis': 'True first120 industry leadership transmission may be stronger than simple industry gap source.',
        'source': {'v306_latest': str(V306_LATEST), 'v306_rows': str(rows_path)},
        'inputs': {'v306_rows': len(rows), 'needed_entry_dates': len(needed_dates), 'industry_mapped_symbols': len(industry), 'missing_leadership_features': missing, **meta},
        'coverage': {'rows': len(enriched), 'symbols': len({r['symbol'] for r in enriched}), 't1_violations': sum(str(r.get('t1_violation')).lower() == 'true' for r in enriched)},
        'baseline': metrics(base),
        'top_dimensions': top_groups(enriched, dims),
        'top_combos': top_combos(enriched, combos),
        'artifacts': {'dir': str(OUT), 'rows': str(out_rows), 'summary': str(OUT / 'v307_summary.json')},
    }
    (OUT / 'v307_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'latest': str(LATEST), 'rows': len(enriched), 'baseline': summary['baseline'], 'best_combo': summary['top_combos'][0] if summary['top_combos'] else None}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
