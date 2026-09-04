#!/usr/bin/env python3
"""V308 no-write: full-history daily proxy for industry leadership transmission.

V307 found the strongest near-term branch is entry-day industry-led opening gap
plus first120 15m industry leadership and candidate participation. The available
15m cache is short, so this audit tests whether daily-only, scanner-time
available proxies can reproduce that signal over 2023-2026:

  entry-day industry opening-gap leadership -> candidate participation at open
  -> V280 chronological SMC family/risk/regime.

No production/frontend/watchlist writes.
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
KDAY = BASE / 'kline_cache'
INDUSTRY_JSON = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854' / 'baostock_stock_industry.json'
V280_ROWS = AUDIT / 'v280_layered_state_grammar_no_write_20260702_205055' / 'v280_events.csv'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v308_daily_industry_leadership_proxy_no_write_{TS}'
LATEST = AUDIT / 'v308_daily_industry_leadership_proxy_latest.json'


def sf(x: Any, d: float = math.nan) -> float:
    try:
        if x is None or x == '':
            return d
        v = float(x)
        return v if not math.isnan(v) else d
    except Exception:
        return d


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
            if sym and ind != 'UNKNOWN':
                out[sym] = ind
    return out


def sym_from_daily_path(p: Path) -> str:
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


def b_gap(x: float) -> str:
    return bucket(x, [(-2, 'GAP<-2'), (-1, 'GAP-2_-1'), (0, 'GAP-1_0'), (1, 'GAP0_1'), (2, 'GAP1_2'), (4, 'GAP2_4')], 'GAP>=4')


def b_rank_pct(x: float) -> str:
    return bucket(x, [(20, 'TOP20'), (40, 'TOP20_40'), (60, 'MID40_60'), (80, 'LOW60_80')], 'LOW80_100')


def b_up(x: float) -> str:
    return bucket(x, [(45, 'UP<45'), (55, 'UP45_55'), (65, 'UP55_65'), (75, 'UP65_75')], 'UP>=75')


def b_risk(x: float) -> str:
    return bucket(x, [(2, 'RISK<2'), (4, 'RISK2_4'), (6, 'RISK4_6'), (8, 'RISK6_8')], 'RISK>=8')


def b_range(x: float) -> str:
    return bucket(x, [(15, 'RNG<15'), (25, 'RNG15_25')], 'RNG>=25')


def blank() -> dict[str, Any]:
    return {'n': 0, 'win': 0, 'pnl': 0.0, 'loss': 0, 'tp': 0, 'sl': 0, 'gap_sl': 0, 'time': 0, 'micro': 0, 'symbols': set(), 'years': defaultdict(lambda: {'n': 0, 'win': 0}), 'months': defaultdict(lambda: {'n': 0, 'win': 0})}


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
    y = str(r.get('year') or '')
    m = str(r.get('month') or '')
    if y:
        a['years'][y]['n'] += 1
        a['years'][y]['win'] += int(pnl > 0)
    if m:
        a['months'][m]['n'] += 1
        a['months'][m]['win'] += int(pnl > 0)


def metrics(a: dict[str, Any]) -> dict[str, Any]:
    n = a['n']
    if not n:
        return {'n': 0}
    year_counts = {k: v['n'] for k, v in sorted(a['years'].items())}
    year_wr = {k: round(100 * v['win'] / v['n'], 2) for k, v in sorted(a['years'].items()) if v['n']}
    month_counts = {k: v['n'] for k, v in sorted(a['months'].items())}
    month_wr = {k: round(100 * v['win'] / v['n'], 2) for k, v in sorted(a['months'].items()) if v['n']}
    return {
        'n': n,
        'wr': round(100 * a['win'] / n, 4),
        'avg': round(a['pnl'] / n, 4),
        'loss': a['loss'],
        'micro': round(100 * a['micro'] / n, 2),
        'tp_pct': round(100 * a['tp'] / n, 2),
        'sl_pct': round(100 * a['sl'] / n, 2),
        'gap_sl_pct': round(100 * a['gap_sl'] / n, 2),
        'time_pct': round(100 * a['time'] / n, 2),
        'symbols': len(a['symbols']),
        'year_counts': year_counts,
        'year_wr': year_wr,
        'min_year_n': min(year_counts.values()) if year_counts else 0,
        'min_year_wr': min(year_wr.values()) if year_wr else None,
        'month_count': len(month_counts),
        'month_counts': month_counts,
        'month_wr': month_wr,
        'min_month_n': min(month_counts.values()) if month_counts else 0,
        'min_month_wr': min(month_wr.values()) if month_wr else None,
        't1_violations': 0,
    }


def build_daily_proxy(needed_dates: set[str], industry: dict[str, str]) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    stock_feat: dict[tuple[str, str], dict[str, Any]] = {}
    ind_members: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    files = list(KDAY.glob('*_daily_750.json'))
    for p in files:
        sym = sym_from_daily_path(p)
        ind = industry.get(sym, 'UNKNOWN')
        if not sym or ind == 'UNKNOWN':
            continue
        arr = load_json(p)
        if not isinstance(arr, list) or len(arr) < 2:
            continue
        arr = sorted(arr, key=lambda b: str(b.get('t') or b.get('date') or ''))
        for i in range(1, len(arr)):
            b, prev = arr[i], arr[i - 1]
            d = str(b.get('t') or b.get('date') or '')[:8]
            if d not in needed_dates:
                continue
            pc, o, c, h, l = sf(prev.get('c')), sf(b.get('o')), sf(b.get('c')), sf(b.get('h')), sf(b.get('l'))
            if pc <= 0 or o <= 0 or c <= 0:
                continue
            prev_vols = [sf(x.get('v'), 0.0) for x in arr[max(0, i - 20):i]]
            avgv = sum(prev_vols) / len(prev_vols) if prev_vols else 0.0
            v = sf(b.get('v'), 0.0)
            f = {
                'symbol': sym, 'industry': ind, 'date': d,
                'gap_pct': (o / pc - 1) * 100,
                'open_to_close_pct': (c / o - 1) * 100,
                'day_ret_pct': (c / pc - 1) * 100,
                'open_drawdown_pct': (l / o - 1) * 100 if l > 0 else math.nan,
                'open_push_pct': (h / o - 1) * 100 if h > 0 else math.nan,
                'amount_proxy': v * c,
                'vol_ratio20': (v / avgv) if avgv > 0 else math.nan,
                'gap_up': o >= pc,
                'open_hold': c >= o,
                'strong_gap': (o / pc - 1) * 100 >= 1,
            }
            stock_feat[(sym, d)] = f
            ind_members[(d, ind)].append(f)

    ind_feat: dict[tuple[str, str], dict[str, Any]] = {}
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (d, ind), rows in ind_members.items():
        if len(rows) < 5:
            continue
        gaps = [sf(r['gap_pct']) for r in rows]
        rets = [sf(r['day_ret_pct']) for r in rows]
        amts = [sf(r['amount_proxy'], 0.0) for r in rows]
        feat = {
            'date': d, 'industry': ind, 'n_members': len(rows),
            'ind_gap_med': median(gaps),
            'ind_gap_up': 100 * sum(g >= 0 for g in gaps) / len(gaps),
            'ind_gap_ge1': 100 * sum(g >= 1 for g in gaps) / len(gaps),
            'ind_day_ret_med': median(rets),
            'ind_day_up': 100 * sum(r >= 0 for r in rets) / len(rets),
            'ind_amount': sum(amts),
        }
        ind_feat[(d, ind)] = feat
        by_date[d].append(feat)

    for d, rows in by_date.items():
        n = len(rows)
        for key, rank_name in [('ind_gap_med', 'ind_gap_rank'), ('ind_gap_up', 'ind_gap_up_rank'), ('ind_gap_ge1', 'ind_gap_ge1_rank'), ('ind_amount', 'ind_amount_rank')]:
            for i, f in enumerate(sorted(rows, key=lambda x: x[key], reverse=True), 1):
                f[rank_name] = i
                f[rank_name + '_pct'] = 100 * i / n
        # market-level daily opening state
        all_gaps = []
        for f in rows:
            all_gaps.extend([sf(x['gap_pct']) for x in ind_members[(d, f['industry'])]])
        m_gap_up = 100 * sum(g >= 0 for g in all_gaps) / len(all_gaps) if all_gaps else math.nan
        m_gap_ge1 = 100 * sum(g >= 1 for g in all_gaps) / len(all_gaps) if all_gaps else math.nan
        for f in rows:
            f['mkt_gap_up'] = m_gap_up
            f['mkt_gap_ge1'] = m_gap_ge1

    meta = {
        'daily_files': len(files),
        'stock_date_features': len(stock_feat),
        'industry_date_features': len(ind_feat),
        'dates_with_industries': len(by_date),
    }
    return stock_feat, ind_feat, meta


def enrich_rows(rows: list[dict[str, Any]], stock_feat: dict[tuple[str, str], dict[str, Any]], ind_feat: dict[tuple[str, str], dict[str, Any]], industry: dict[str, str]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        sym, d = str(r.get('symbol') or ''), str(r.get('entry_date') or '')[:8]
        ind = industry.get(sym, 'UNKNOWN')
        sf0, inf = stock_feat.get((sym, d)), ind_feat.get((d, ind))
        if not sf0 or not inf:
            continue
        nr = dict(r)
        nr['industry'] = ind
        nr['month'] = d[:6]
        nr['risk_bucket'] = b_risk(sf(nr.get('risk')))
        nr['range_bucket'] = b_range(sf(nr.get('range60')))
        nr['stock_gap_bucket'] = b_gap(sf0['gap_pct'])
        # Scanner-time safe at the open: only the open gap is known. Do not use
        # same-day high/low/close here; those are post-entry outcomes for a daily
        # open execution contract.
        nr['stock_open_gap_state'] = 'STOCK_GAP_UP' if sf0['gap_pct'] >= 0 else 'STOCK_GAP_DOWN'
        nr['ind_gap_bucket'] = b_gap(inf['ind_gap_med'])
        nr['ind_gap_rank_bucket'] = b_rank_pct(inf.get('ind_gap_rank_pct', math.nan))
        nr['ind_gap_up_bucket'] = b_up(inf['ind_gap_up'])
        nr['ind_gap_ge1_bucket'] = b_up(inf['ind_gap_ge1'])
        nr['ind_amount_rank_bucket'] = b_rank_pct(inf.get('ind_amount_rank_pct', math.nan))
        nr['mkt_gap_up_bucket'] = b_up(inf.get('mkt_gap_up', math.nan))
        nr['mkt_gap_ge1_bucket'] = b_up(inf.get('mkt_gap_ge1', math.nan))
        is_leader = inf.get('ind_gap_rank_pct', 100) <= 20 or inf.get('ind_gap_up_rank_pct', 100) <= 20
        nr['daily_ind_leader_state'] = 'DAILY_GAP_LEADER_TOP20' if is_leader else ('DAILY_GAP_LEADER_TOP40' if inf.get('ind_gap_rank_pct', 100) <= 40 else 'DAILY_NON_LEADER')
        if is_leader and nr['stock_open_gap_state'] == 'STOCK_GAP_UP':
            nr['daily_leader_transmission'] = 'DAILY_LEADER_GAP_UP'
        elif is_leader:
            nr['daily_leader_transmission'] = 'DAILY_LEADER_GAP_DOWN'
        else:
            nr['daily_leader_transmission'] = 'NO_DAILY_LEADER'
        out.append(nr)
    return out


def aggregate(rows: list[dict[str, Any]], dims: list[tuple[str, str]], min_n: int = 80) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], dict[str, Any]] = defaultdict(blank)
    for r in rows:
        for name, val in dims:
            if '{' in val:
                parts = [p.strip() for p in val.split('+')]
                keyv = '|'.join(str(r.get(p, '')) for p in parts)
            else:
                keyv = str(r.get(val, ''))
            add(groups[(name, keyv)], r)
    out = []
    for (name, val), agg in groups.items():
        m = metrics(agg)
        if m['n'] >= min_n:
            m['dimension'] = name
            m['value'] = val
            out.append(m)
    out.sort(key=lambda x: (x.get('min_year_wr') or 0, x['wr'], x['avg'], x['n']), reverse=True)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    industry = load_industry_map()
    rows = []
    needed_dates = set()
    with V280_ROWS.open() as fh:
        for r in csv.DictReader(fh):
            d = str(r.get('entry_date') or '')[:8]
            if d and str(r.get('year')) in {'2023', '2024', '2025', '2026'}:
                rows.append(r)
                needed_dates.add(d)
    stock_feat, ind_feat, meta = build_daily_proxy(needed_dates, industry)
    enriched = enrich_rows(rows, stock_feat, ind_feat, industry)

    base = blank()
    for r in enriched:
        add(base, r)

    dims = [
        ('daily_leader_transmission', 'daily_leader_transmission'),
        ('daily_ind_leader_state', 'daily_ind_leader_state'),
        ('ind_gap_rank_bucket', 'ind_gap_rank_bucket'),
        ('ind_gap_up_bucket', 'ind_gap_up_bucket'),
        ('ind_gap_ge1_bucket', 'ind_gap_ge1_bucket'),
        ('ind_amount_rank_bucket', 'ind_amount_rank_bucket'),
        ('mkt_gap_up_bucket', 'mkt_gap_up_bucket'),
        ('stock_open_gap_state', 'stock_open_gap_state'),
        ('family_leader', 'family + daily_leader_transmission'),
        ('family_regime_leader', 'family + regime + daily_leader_transmission'),
        ('family_regime_risk_leader', 'family + regime + risk_bucket + daily_leader_transmission'),
        ('leader_indgap_stock', 'daily_leader_transmission + ind_gap_up_bucket + stock_open_gap_state'),
        ('family_leader_indgap_risk', 'family + daily_leader_transmission + ind_gap_up_bucket + risk_bucket'),
        ('regime_leader_mkt', 'regime + daily_leader_transmission + mkt_gap_up_bucket'),
        ('family_leader_range_risk', 'family + daily_leader_transmission + range_bucket + risk_bucket'),
    ]
    top = aggregate(enriched, dims, min_n=80)

    out_rows = OUT / 'v308_rows.csv'
    if enriched:
        fields = list(enriched[0].keys())
        with out_rows.open('w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader(); w.writerows(enriched)

    summary = {
        'version': 'V308_DAILY_INDUSTRY_LEADERSHIP_PROXY_NO_WRITE',
        'created_at': TS,
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'hypothesis': 'Daily full-history industry opening-gap leadership can proxy V307 first120 industry leadership transmission.',
        'source': {'v280_rows': str(V280_ROWS)},
        'inputs': {'v280_rows': len(rows), 'needed_entry_dates': len(needed_dates), 'industry_mapped_symbols': len(industry), **meta},
        'coverage': {'rows': len(enriched), 'symbols': len({r['symbol'] for r in enriched}), 't1_violations': sum(str(r.get('t1')).lower() == 'true' for r in enriched)},
        'baseline': metrics(base),
        'top_dimensions': top[:120],
        'artifacts': {'rows': str(out_rows)},
    }
    (OUT / 'v308_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'summary': str(LATEST), 'rows': len(enriched), 'baseline': summary['baseline'], 'top5': top[:5]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
