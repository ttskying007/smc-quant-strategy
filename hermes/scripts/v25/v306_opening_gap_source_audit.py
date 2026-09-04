#!/usr/bin/env python3
"""V306 no-write: opening gap source + morning persistence audit.

After V303-V305 showed first/second/morning 15m persistence is still only a
state layer, this script tests the next concrete branch: whether the entry-day
opening gap source (market-wide, industry-led, stock-isolated, or unsupported)
explains fake takeovers. It reads V305 rows and local daily/industry data only,
then writes audit artifacts under smc_audit. No production/frontend/watchlist
writes.
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
V305_LATEST = AUDIT / 'v305_morning15_persistence_latest.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v306_opening_gap_source_no_write_{TS}'
LATEST = AUDIT / 'v306_opening_gap_source_latest.json'


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


def dn(x: Any) -> str:
    s = str(x or '')
    return s[:8] if len(s) >= 8 else ''


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


def sym_from_day_path(p: Path) -> str:
    parts = p.name.split('_')
    if len(parts) < 3:
        return ''
    return f'{parts[0]}.{parts[1]}'


def daily_paths() -> list[Path]:
    # Prefer 750-bar caches when both 750 and 300 exist for the same symbol.
    best: dict[str, Path] = {}
    for p in KDAY.glob('*_daily_*.json'):
        sym = sym_from_day_path(p)
        if not sym:
            continue
        old = best.get(sym)
        if old is None or ('_daily_750' in p.name and '_daily_750' not in old.name):
            best[sym] = p
    return list(best.values())


def bucket(x: float, cuts: list[tuple[float, str]], last: str) -> str:
    if math.isnan(x):
        return 'NA'
    for c, name in cuts:
        if x < c:
            return name
    return last


def b_gap(x: float) -> str:
    return bucket(x, [(-2, 'GAP<-2'), (-1, 'GAP-2_-1'), (0, 'GAP-1_0'), (1, 'GAP0_1'), (3, 'GAP1_3')], 'GAP>=3')


def b_up(x: float) -> str:
    return bucket(x, [(45, 'UP<45'), (55, 'UP45_55'), (65, 'UP55_65')], 'UP>=65')


def b_rel(x: float) -> str:
    return bucket(x, [(-1, 'REL<-1'), (0, 'REL-1_0'), (1, 'REL0_1'), (2, 'REL1_2')], 'REL>=2')


def b_rank(x: float) -> str:
    return bucket(x, [(30, 'RANK<30'), (60, 'RANK30_60'), (80, 'RANK60_80')], 'RANK>=80')


def build_gap_features(needed_dates: set[str], industry: dict[str, str]) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_date_ind: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    sym_date: dict[tuple[str, str], dict[str, Any]] = {}
    files = daily_paths()
    for p in files:
        sym = sym_from_day_path(p)
        if not sym:
            continue
        x = load_json(p)
        if not isinstance(x, list) or len(x) < 2:
            continue
        rows = []
        for b in x:
            d = dn(b.get('t') or b.get('date'))
            o, c = sf(b.get('o')), sf(b.get('c'))
            if d and o > 0 and c > 0:
                rows.append({'d': d, 'o': o, 'c': c})
        rows.sort(key=lambda r: r['d'])
        ind = industry.get(sym, 'UNKNOWN')
        for i in range(1, len(rows)):
            d = rows[i]['d']
            if d not in needed_dates:
                continue
            prev_c = rows[i - 1]['c']
            if prev_c <= 0:
                continue
            gap = (rows[i]['o'] / prev_c - 1) * 100
            ret = (rows[i]['c'] / prev_c - 1) * 100
            rec = {'symbol': sym, 'industry': ind, 'date': d, 'gap': gap, 'ret': ret}
            by_date[d].append(rec)
            by_date_ind[(d, ind)].append(rec)
            sym_date[(sym, d)] = rec

    market: dict[str, dict[str, float]] = {}
    for d, arr in by_date.items():
        gaps = [r['gap'] for r in arr]
        rets = [r['ret'] for r in arr]
        market[d] = {
            'm_gap_med': median(gaps),
            'm_gap_up': 100 * sum(g > 0 for g in gaps) / len(gaps),
            'm_gap_hot': 100 * sum(g >= 1 for g in gaps) / len(gaps),
            'm_ret_med': median(rets),
        }

    indfeat: dict[tuple[str, str], dict[str, float]] = {}
    for key, arr in by_date_ind.items():
        gaps = [r['gap'] for r in arr]
        rets = [r['ret'] for r in arr]
        indfeat[key] = {
            'i_gap_med': median(gaps),
            'i_gap_up': 100 * sum(g > 0 for g in gaps) / len(gaps),
            'i_gap_hot': 100 * sum(g >= 1 for g in gaps) / len(gaps),
            'i_ret_med': median(rets),
            'i_size': len(arr),
        }

    out: dict[tuple[str, str], dict[str, Any]] = {}
    for (sym, d), rec in sym_date.items():
        ind = rec['industry']
        m = market.get(d, {})
        ii = indfeat.get((d, ind), {})
        peers = sorted((r['gap'] for r in by_date_ind.get((d, ind), [])))
        rank = math.nan
        if peers:
            rank = 100 * sum(g <= rec['gap'] for g in peers) / len(peers)
        m_gap = sf(m.get('m_gap_med'))
        i_gap = sf(ii.get('i_gap_med'))
        rel_ind = rec['gap'] - i_gap if not math.isnan(i_gap) else math.nan
        rel_mkt = rec['gap'] - m_gap if not math.isnan(m_gap) else math.nan
        if rec['gap'] >= 1.0 and i_gap >= 0.8 and i_gap - m_gap >= 0.25:
            src = 'INDUSTRY_GAP_LED'
        elif rec['gap'] >= 1.0 and m_gap >= 0.5 and sf(m.get('m_gap_up')) >= 55:
            src = 'MARKET_GAP_LED'
        elif rec['gap'] >= 1.0 and i_gap < 0.5 and m_gap < 0.5 and rel_ind >= 1.0:
            src = 'STOCK_ISOLATED_GAP'
        elif rec['gap'] < 0:
            src = 'NO_GAP_OR_DOWN'
        elif rec['gap'] >= 1.0:
            src = 'UNSUPPORTED_GAP'
        else:
            src = 'SMALL_GAP'
        feat = {
            'stock_gap': rec['gap'], 'gap_source': src,
            'gap_bucket2': b_gap(rec['gap']),
            'm_gap_med': m_gap, 'm_gap_up': sf(m.get('m_gap_up')), 'm_gap_hot': sf(m.get('m_gap_hot')),
            'i_gap_med': i_gap, 'i_gap_up': sf(ii.get('i_gap_up')), 'i_gap_hot': sf(ii.get('i_gap_hot')),
            'rel_gap_ind': rel_ind, 'rel_gap_mkt': rel_mkt, 'ind_gap_rank': rank,
            'm_gap_bucket': b_gap(m_gap), 'm_gap_up_bucket': b_up(sf(m.get('m_gap_up'))),
            'i_gap_bucket': b_gap(i_gap), 'i_gap_up_bucket': b_up(sf(ii.get('i_gap_up'))),
            'rel_ind_bucket': b_rel(rel_ind), 'rank_bucket': b_rank(rank),
        }
        out[(sym, d)] = feat
    meta = {'daily_files': len(files), 'market_dates': len(market), 'symbol_date_features': len(out)}
    return out, meta


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
    out: list[dict[str, Any]] = []
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
    out: list[dict[str, Any]] = []
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
    src = load_json(V305_LATEST)
    if not isinstance(src, dict):
        raise RuntimeError(f'cannot read V305 latest summary: {V305_LATEST}')
    rows_path = Path(str(src.get('artifacts', {}).get('rows') or ''))
    if not rows_path.exists() and src.get('created_at'):
        rows_path = AUDIT / f"v305_morning15_persistence_no_write_{src['created_at']}" / 'v305_rows.csv'
    if not rows_path.exists():
        raise RuntimeError(f'cannot locate V305 rows from {V305_LATEST}')
    rows: list[dict[str, Any]] = []
    needed_dates: set[str] = set()
    with rows_path.open() as fh:
        for r in csv.DictReader(fh):
            if str(r.get('t1_violation')).lower() == 'true':
                continue
            rows.append(dict(r))
            needed_dates.add(str(r.get('entry_date') or ''))
    industry = load_industry_map()
    gaps, gap_meta = build_gap_features(needed_dates, industry)
    enriched: list[dict[str, Any]] = []
    missing_gap = 0
    for r in rows:
        feat = gaps.get((str(r.get('symbol')), str(r.get('entry_date'))))
        if not feat:
            missing_gap += 1
            continue
        rr = dict(r)
        for k, v in feat.items():
            rr[k] = v
        # A compact causal class: gap source plus whether the selected morning window did not fade.
        mode = str(rr.get('entry_mode') or '')
        morning_ok = mode in {'MORNING120_NO_FADE', 'MORNING120_PERSIST', 'MORNING60_TAKEOVER'}
        rr['gap_morning_class'] = f"{rr['gap_source']}|{'MORNING_OK' if morning_ok else 'MORNING_WEAK'}"
        enriched.append(rr)
    base = blank()
    for r in enriched:
        add(base, r)
    dims = ['gap_source', 'gap_morning_class', 'gap_bucket2', 'm_gap_bucket', 'i_gap_bucket', 'm_gap_up_bucket', 'i_gap_up_bucket', 'rel_ind_bucket', 'rank_bucket', 'entry_mode', 'open_bucket', 'risk2_bucket', 'acc_bucket', 'sweep_bucket']
    combos = [
        ['gap_source', 'entry_mode'],
        ['gap_source', 'risk2_bucket'],
        ['gap_source', 'm120_iup_bucket'],
        ['gap_source', 'm120_mup_bucket'],
        ['gap_source', 'i_gap_up_bucket', 'm120_iup_bucket'],
        ['gap_source', 'rank_bucket', 'risk2_bucket'],
        ['gap_morning_class', 'risk2_bucket'],
        ['gap_morning_class', 'i_gap_up_bucket'],
        ['gap_source', 'acc_bucket', 'sweep_bucket'],
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    out_rows = OUT / 'v306_rows.csv'
    fieldnames = sorted(set().union(*(r.keys() for r in enriched))) if enriched else []
    with out_rows.open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(enriched)
    summary = {
        'version': 'V306_OPENING_GAP_SOURCE_NO_WRITE',
        'created_at': TS,
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'hypothesis': 'Entry-day opening gap source may identify whether V302/V305 morning takeovers are market/industry supported or isolated fake takeovers.',
        'source': {'v305_latest': str(V305_LATEST), 'v305_rows': str(rows_path)},
        'inputs': {'v305_rows': len(rows), 'needed_entry_dates': len(needed_dates), 'industry_mapped_symbols': len(industry), 'missing_gap_features': missing_gap, **gap_meta},
        'coverage': {'rows': len(enriched), 'symbols': len({r['symbol'] for r in enriched}), 't1_violations': sum(str(r.get('t1_violation')).lower() == 'true' for r in enriched)},
        'baseline': metrics(base),
        'top_dimensions': top_groups(enriched, dims),
        'top_combos': top_combos(enriched, combos),
        'artifacts': {'dir': str(OUT), 'rows': str(out_rows), 'summary': str(OUT / 'v306_summary.json')},
    }
    (OUT / 'v306_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'latest': str(LATEST), 'rows': len(enriched), 'baseline': summary['baseline'], 'best_combo': summary['top_combos'][0] if summary['top_combos'] else None}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
