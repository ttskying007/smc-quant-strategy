#!/usr/bin/env python3
"""V304 no-write: entry-session 15m market/industry diffusion overlay.

V303 proved individual first/second 15m executable confirmation does not rescue
V302. This audit tests a new entry-time information layer: whether the same
first/second 15m buy window has synchronized market + industry participation and
stock volume persistence. It only reads V303 rows + local 15m/industry caches and
writes audit artifacts; it never writes production/frontend/watchlist files.
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
V303_LATEST = AUDIT / 'v303_executable_15m_entry_timing_latest.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v304_entry15_market_industry_diffusion_no_write_{TS}'
LATEST = AUDIT / 'v304_entry15_market_industry_diffusion_latest.json'


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


def sym_from_15_path(p: Path) -> str:
    parts = p.name.split('_')
    if len(parts) < 3:
        return ''
    return f'{parts[0]}.{parts[1]}'


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


def day_groups(bars: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    g: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for b in bars:
        d = dn(b.get('d') or b.get('t'))
        if d:
            g[d].append(b)
    for rows in g.values():
        rows.sort(key=lambda r: str(r.get('t') or ''))
    return g


def symbol_day_features(p: Path, need_dates: set[str]) -> dict[str, dict[str, Any]]:
    sym = sym_from_15_path(p)
    if not sym:
        return {}
    x = load_json(p)
    if not isinstance(x, list):
        return {}
    groups = day_groups(x)
    dates = sorted(groups)
    first2_amt: dict[str, float] = {}
    raw: dict[str, dict[str, Any]] = {}
    for d in dates:
        rows = groups[d]
        if len(rows) < 2:
            continue
        b1, b2 = rows[0], rows[1]
        o1, c1, c2 = sf(b1.get('o')), sf(b1.get('c')), sf(b2.get('c'))
        h1, h2 = sf(b1.get('h')), sf(b2.get('h'))
        l1, l2 = sf(b1.get('l')), sf(b2.get('l'))
        v1, v2 = sf(b1.get('v'), 0.0), sf(b2.get('v'), 0.0)
        if o1 <= 0 or min(c1, c2, h1, h2, l1, l2) <= 0:
            continue
        amt1 = v1 * c1
        amt2 = amt1 + v2 * c2
        first2_amt[d] = amt2
        raw[d] = {
            'symbol': sym,
            'date': d,
            'f1_ret': (c1 / o1 - 1) * 100,
            'f2_ret': (c2 / o1 - 1) * 100,
            'f1_green': c1 >= o1,
            'f2_green': c2 >= o1,
            'f1_low_dd': (l1 / o1 - 1) * 100,
            'f2_low_dd': (min(l1, l2) / o1 - 1) * 100,
            'f1_push': (h1 / o1 - 1) * 100,
            'f2_push': (max(h1, h2) / o1 - 1) * 100,
            'f1_amt': amt1,
            'f2_amt': amt2,
        }
    out: dict[str, dict[str, Any]] = {}
    for i, d in enumerate(dates):
        if d not in need_dates or d not in raw:
            continue
        prev = [first2_amt[x] for x in dates[max(0, i - 5):i] if x in first2_amt and first2_amt[x] > 0]
        base = sum(prev) / len(prev) if prev else math.nan
        r = dict(raw[d])
        r['stock_amt_vr'] = r['f2_amt'] / base if base and not math.isnan(base) else math.nan
        out[d] = r
    return out


def bucket(x: float, cuts: list[tuple[float, str]], last: str) -> str:
    if math.isnan(x):
        return 'NA'
    for c, name in cuts:
        if x < c:
            return name
    return last


def b_up(x: float) -> str:
    return bucket(x, [(45, 'UP<45'), (55, 'UP45_55'), (65, 'UP55_65')], 'UP>=65')


def b_ret(x: float) -> str:
    return bucket(x, [(-0.5, 'RET<-0.5'), (0, 'RET-0.5_0'), (0.5, 'RET0_0.5'), (1.0, 'RET0.5_1')], 'RET>=1')


def b_vr(x: float) -> str:
    return bucket(x, [(0.8, 'VR<0.8'), (1.2, 'VR0.8_1.2'), (2.0, 'VR1.2_2')], 'VR>=2')


def b_rel(x: float) -> str:
    return bucket(x, [(-1, 'REL<-1'), (0, 'REL-1_0'), (1, 'REL0_1')], 'REL>=1')


def blank() -> dict[str, Any]:
    return {'n': 0, 'win': 0, 'sum': 0.0, 'loss': 0, 'micro': 0, 'tp': 0, 'sl': 0, 'gap': 0, 'time': 0, 'symbols': set(), 'mc': defaultdict(int), 'mw': defaultdict(int), 't1': 0}


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'))
    a['n'] += 1
    a['sum'] += pnl
    a['symbols'].add(r['symbol'])
    if pnl > 0:
        a['win'] += 1
        a['mw'][r['month']] += 1
    else:
        a['loss'] += 1
    if 0 < abs(pnl) < 0.6:
        a['micro'] += 1
    reason = str(r.get('reason', ''))
    if reason == 'TP':
        a['tp'] += 1
    elif reason == 'SL':
        a['sl'] += 1
    elif reason == 'GAP_SL':
        a['gap'] += 1
    elif reason.startswith('TIME'):
        a['time'] += 1
    a['mc'][r['month']] += 1
    if str(r.get('t1_violation')).lower() == 'true':
        a['t1'] += 1


def finalize(a: dict[str, Any]) -> dict[str, Any]:
    n = a['n']
    if n == 0:
        return {'n': 0}
    mwr = {k: round(a['mw'][k] / v * 100, 2) for k, v in sorted(a['mc'].items()) if v}
    return {
        'n': n,
        'wr': round(a['win'] / n * 100, 4),
        'avg': round(a['sum'] / n, 4),
        'loss': a['loss'],
        'micro': round(a['micro'] / n * 100, 2),
        'tp_pct': round(a['tp'] / n * 100, 2),
        'sl_pct': round(a['sl'] / n * 100, 2),
        'gap_sl_pct': round(a['gap'] / n * 100, 2),
        'time_pct': round(a['time'] / n * 100, 2),
        'symbols': len(a['symbols']),
        'month_count': len(a['mc']),
        'month_counts': dict(sorted(a['mc'].items())),
        'month_wr': mwr,
        'min_month_n': min(a['mc'].values()) if a['mc'] else 0,
        'min_month_wr': min(mwr.values()) if mwr else None,
        't1_violations': a['t1'],
    }


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    a = blank()
    for r in rows:
        add(a, r)
    return finalize(a)


def top_variants(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = defaultdict(blank)
    allowed_modes = {'FIRST15_ACC_HOLD', 'FIRST15_TAKEOVER', 'SECOND15_CONT', 'FIRST30_NO_DUMP'}
    for r in rows:
        if r['entry_mode'] not in allowed_modes or r['diffusion_available'] != 'true':
            continue
        combos = [
            f"mode={r['entry_mode']}|mup={r['m_up_bucket']}|iup={r['i_up_bucket']}",
            f"mode={r['entry_mode']}|iup={r['i_up_bucket']}|svr={r['stock_vr_bucket']}",
            f"mode={r['entry_mode']}|mup={r['m_up_bucket']}|iup={r['i_up_bucket']}|ivr={r['i_vr_bucket']}",
            f"mode={r['entry_mode']}|mret={r['m_ret_bucket']}|iret={r['i_ret_bucket']}|rel={r['rel_bucket']}",
            f"mode={r['entry_mode']}|open={r['open_bucket']}|risk={r['risk2_bucket']}|iup={r['i_up_bucket']}|svr={r['stock_vr_bucket']}",
            f"mode={r['entry_mode']}|dd={r['dd_bucket']}|risk={r['risk2_bucket']}|mup={r['m_up_bucket']}|iup={r['i_up_bucket']}",
            f"mode={r['entry_mode']}|acc={r['acc_bucket']}|sweep={r['sweep_bucket']}|iup={r['i_up_bucket']}|rel={r['rel_bucket']}",
            f"mode={r['entry_mode']}|iup={r['i_up_bucket']}|ivr={r['i_vr_bucket']}|rel={r['rel_bucket']}|svr={r['stock_vr_bucket']}",
        ]
        for c in combos:
            add(groups[c], r)
    out = []
    for name, a in groups.items():
        m = finalize(a)
        if m['n'] >= 120 and m['month_count'] >= 3:
            m['variant'] = name
            out.append(m)
    return sorted(out, key=lambda x: (x.get('min_month_wr') or -999, x['wr'], x['avg'], x['n']), reverse=True)[:50]


def main() -> None:
    latest = load_json(V303_LATEST)
    if not isinstance(latest, dict):
        raise SystemExit(f'Missing V303 latest: {V303_LATEST}')
    v303_rows = Path(latest['artifacts']['rows'])
    if not v303_rows.exists():
        raise SystemExit(f'Missing V303 rows: {v303_rows}')

    rows: list[dict[str, Any]] = []
    need_dates: set[str] = set()
    with v303_rows.open() as fh:
        for r in csv.DictReader(fh):
            rows.append(r)
            d = dn(r.get('entry_date'))
            if d:
                need_dates.add(d)

    industry = load_industry_map()
    by_symbol_date: dict[tuple[str, str], dict[str, Any]] = {}
    market: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    indagg: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    files = sorted(K15.glob('*_15min_800.json'))
    for p in files:
        sym = sym_from_15_path(p)
        feats = symbol_day_features(p, need_dates)
        if not feats:
            continue
        ind = industry.get(sym, 'UNKNOWN')
        for d, f in feats.items():
            by_symbol_date[(sym, d)] = f
            for cut in ('f1', 'f2'):
                ret = f[f'{cut}_ret']
                vr = f['stock_amt_vr']
                market[d][f'{cut}_ret'].append(ret)
                market[d][f'{cut}_up'].append(1.0 if ret > 0 else 0.0)
                if not math.isnan(vr):
                    market[d][f'{cut}_vr'].append(vr)
                indagg[(d, ind)][f'{cut}_ret'].append(ret)
                indagg[(d, ind)][f'{cut}_up'].append(1.0 if ret > 0 else 0.0)
                if not math.isnan(vr):
                    indagg[(d, ind)][f'{cut}_vr'].append(vr)

    def agg_features(sym: str, d: str, cut: str) -> dict[str, float]:
        ind = industry.get(sym, 'UNKNOWN')
        m = market.get(d, {})
        ia = indagg.get((d, ind), {})
        m_rets, i_rets = m.get(f'{cut}_ret', []), ia.get(f'{cut}_ret', [])
        m_ups, i_ups = m.get(f'{cut}_up', []), ia.get(f'{cut}_up', [])
        m_vrs, i_vrs = m.get(f'{cut}_vr', []), ia.get(f'{cut}_vr', [])
        return {
            'm_ret_med': median(m_rets) if m_rets else math.nan,
            'i_ret_med': median(i_rets) if i_rets else math.nan,
            'm_up_pct': sum(m_ups) / len(m_ups) * 100 if m_ups else math.nan,
            'i_up_pct': sum(i_ups) / len(i_ups) * 100 if i_ups else math.nan,
            'm_vr_med': median(m_vrs) if m_vrs else math.nan,
            'i_vr_med': median(i_vrs) if i_vrs else math.nan,
            'industry': ind,
            'industry_n': len(i_rets),
            'market_n': len(m_rets),
        }

    enriched: list[dict[str, Any]] = []
    for r in rows:
        sym, d = r['symbol'], dn(r['entry_date'])
        bar_no = int(sf(r.get('entry_bar_no'), -1))
        cut = 'f1' if bar_no == 1 else 'f2' if bar_no == 2 else ''
        base = by_symbol_date.get((sym, d))
        nr = dict(r)
        nr['diffusion_available'] = 'false'
        if cut and base:
            af = agg_features(sym, d, cut)
            stock_ret = base[f'{cut}_ret']
            stock_vr = base['stock_amt_vr']
            nr.update({
                'diffusion_available': 'true',
                'diffusion_cut': cut,
                'industry': af['industry'],
                'industry_n': af['industry_n'],
                'market_n': af['market_n'],
                'stock_15_ret': round(stock_ret, 4),
                'stock_amt_vr': round(stock_vr, 4) if not math.isnan(stock_vr) else '',
                'market_ret_med': round(af['m_ret_med'], 4) if not math.isnan(af['m_ret_med']) else '',
                'industry_ret_med': round(af['i_ret_med'], 4) if not math.isnan(af['i_ret_med']) else '',
                'market_up_pct': round(af['m_up_pct'], 4) if not math.isnan(af['m_up_pct']) else '',
                'industry_up_pct': round(af['i_up_pct'], 4) if not math.isnan(af['i_up_pct']) else '',
                'market_vr_med': round(af['m_vr_med'], 4) if not math.isnan(af['m_vr_med']) else '',
                'industry_vr_med': round(af['i_vr_med'], 4) if not math.isnan(af['i_vr_med']) else '',
                'rel_to_industry_ret': round(stock_ret - af['i_ret_med'], 4) if not math.isnan(af['i_ret_med']) else '',
                'm_up_bucket': b_up(af['m_up_pct']),
                'i_up_bucket': b_up(af['i_up_pct']),
                'm_ret_bucket': b_ret(af['m_ret_med']),
                'i_ret_bucket': b_ret(af['i_ret_med']),
                'stock_vr_bucket': b_vr(stock_vr),
                'i_vr_bucket': b_vr(af['i_vr_med']),
                'rel_bucket': b_rel(stock_ret - af['i_ret_med']) if not math.isnan(af['i_ret_med']) else 'NA',
            })
        else:
            nr.update({
                'diffusion_cut': '', 'industry': industry.get(sym, 'UNKNOWN'), 'industry_n': '', 'market_n': '',
                'stock_15_ret': '', 'stock_amt_vr': '', 'market_ret_med': '', 'industry_ret_med': '',
                'market_up_pct': '', 'industry_up_pct': '', 'market_vr_med': '', 'industry_vr_med': '',
                'rel_to_industry_ret': '', 'm_up_bucket': 'NA', 'i_up_bucket': 'NA', 'm_ret_bucket': 'NA',
                'i_ret_bucket': 'NA', 'stock_vr_bucket': 'NA', 'i_vr_bucket': 'NA', 'rel_bucket': 'NA',
            })
        enriched.append(nr)

    OUT.mkdir(parents=True, exist_ok=True)
    rows_path = OUT / 'v304_rows.csv'
    fieldnames = list(enriched[0].keys()) if enriched else []
    with rows_path.open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(enriched)

    available_rows = [r for r in enriched if r['diffusion_available'] == 'true']
    mode_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in available_rows:
        mode_groups[r['entry_mode']].append(r)
    summary = {
        'version': 'V304_ENTRY15_MARKET_INDUSTRY_DIFFUSION_NO_WRITE',
        'created_at': TS,
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'hypothesis': 'Entry-time first/second 15m synchronized market+industry participation and stock amount persistence can filter V303 fake takeovers.',
        'source': {'v303_latest': str(V303_LATEST), 'v303_rows': str(v303_rows)},
        'inputs': {
            'v303_rows': len(rows),
            'needed_entry_dates': len(need_dates),
            'k15_files': len(files),
            'symbol_date_features': len(by_symbol_date),
            'industry_mapped_symbols': len(industry),
        },
        'coverage': {
            'diffusion_available_rows': len(available_rows),
            'diffusion_available_pct': round(len(available_rows) / len(rows) * 100, 4) if rows else 0,
            't1_violations': sum(1 for r in enriched if str(r.get('t1_violation')).lower() == 'true'),
        },
        'baseline_all_v303': metrics(enriched),
        'baseline_diffusion_available': metrics(available_rows),
        'mode_metrics': {k: metrics(v) for k, v in sorted(mode_groups.items())},
        'top_variants': top_variants(enriched),
        'artifacts': {'dir': str(OUT), 'rows': str(rows_path), 'latest': str(LATEST)},
    }
    summary['best_variant'] = summary['top_variants'][0] if summary['top_variants'] else {'n': 0}
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (OUT / 'v304_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({
        'summary': str(LATEST),
        'rows': len(enriched),
        'available': len(available_rows),
        'best': summary['best_variant'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
