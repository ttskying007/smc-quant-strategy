#!/usr/bin/env python3
"""V293 no-write: entry-session first60 participation + lifecycle overlay on V292.

V292 found that buying after next-session first60 hold/continuation improves GAP_SL
and Avg but monthly lows remain poor.  This audit tests the next concrete proxy the
skill notes require when 15m/auction/order-book data is absent: after the first 60m
confirmation is known, does same-hour market/industry participation plus pre-entry
operator lifecycle separate real takeover from false continuation?

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
K60_DIRS = [BASE / 'kline_cache_60min', BASE / 'kline_cache']
INDMAP = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
V292 = json.loads((AUDIT / 'v292_next_session_60m_confirmation_latest.json').read_text())
ROWS = Path(V292['artifacts']['best_rows'])
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v293_entry60_participation_lifecycle_no_write_{TS}'
LATEST = AUDIT / 'v293_entry60_participation_lifecycle_latest.json'


def sf(x: Any, d: float = math.nan) -> float:
    try:
        if x is None or x == '':
            return d
        v = float(x)
        return v if not math.isnan(v) else d
    except Exception:
        return d


def dn(x: Any) -> str:
    s = ''.join(ch for ch in str(x or '').replace('-', '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def symbol_from_path(p: Path) -> str | None:
    stem = p.stem.replace('_60min_500', '')
    if '_' not in stem:
        return None
    code, ex = stem.split('_', 1)
    if len(code) != 6:
        return None
    return f'{code}.{ex}'


def path60(sym: str) -> Path | None:
    code, ex = sym.split('.')
    for d in K60_DIRS:
        p = d / f'{code}_{ex}_60min_500.json'
        if p.exists():
            return p
    return None


def brange(x: float) -> str:
    if math.isnan(x): return 'ACC_NA'
    if x < 4: return 'ACC_TIGHT<4'
    if x < 7: return 'ACC_MID4_7'
    return 'ACC_WIDE>=7'


def bdepth(x: float) -> str:
    if math.isnan(x): return 'SWP_NA'
    if x < 1: return 'SWP_SHALLOW<1'
    if x < 3: return 'SWP_MID1_3'
    return 'SWP_DEEP>=3'


def bimp(x: float) -> str:
    if math.isnan(x): return 'IMP_NA'
    if x < 0.5: return 'IMP_WEAK<0.5'
    if x < 1.5: return 'IMP_MID0.5_1.5'
    return 'IMP_STRONG>=1.5'


def bret(x: float) -> str:
    if math.isnan(x): return 'RET_NA'
    if x < -1: return 'RET<-1'
    if x < 0: return 'RET_-1_0'
    if x < 1: return 'RET_0_1'
    return 'RET>=1'


def bup(x: float) -> str:
    if math.isnan(x): return 'UP_NA'
    if x < 35: return 'UP<35'
    if x < 50: return 'UP35_50'
    if x < 65: return 'UP50_65'
    return 'UP>=65'


def brel(x: float) -> str:
    if math.isnan(x): return 'REL_NA'
    if x < -10: return 'REL<-10'
    if x < 0: return 'REL_-10_0'
    if x < 10: return 'REL0_10'
    return 'REL>=10'


def bconfirm(x: float) -> str:
    if math.isnan(x): return 'CONF_NA'
    if x <= 0: return 'CONF<=0'
    if x < 1: return 'CONF0_1'
    if x < 2: return 'CONF1_2'
    if x < 4: return 'CONF2_4'
    return 'CONF>=4'


def bvol(x: float) -> str:
    if math.isnan(x): return 'EVOL_NA'
    if x < 0.8: return 'EVOL<0.8'
    if x < 1.2: return 'EVOL0.8_1.2'
    if x < 2: return 'EVOL1.2_2'
    return 'EVOL>=2'


def blank() -> dict[str, Any]:
    return {'n': 0, 'wins': 0, 'sum': 0.0, 'loss': 0, 'micro': 0, 'tp': 0, 'sl': 0,
            'gap_sl': 0, 'time': 0, 'years': defaultdict(lambda: [0, 0]),
            'months': defaultdict(lambda: [0, 0]), 'symbols': set()}


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'), 0.0); reason = str(r.get('reason', ''))
    a['n'] += 1; a['wins'] += pnl > 0; a['sum'] += pnl; a['loss'] += pnl <= 0
    a['micro'] += 0 < pnl < 1; a['tp'] += reason == 'TP'; a['sl'] += reason == 'SL'
    a['gap_sl'] += reason == 'GAP_SL'; a['time'] += reason.startswith('TIME')
    y = str(r.get('entry_date', ''))[:4]; m = str(r.get('entry_date', ''))[:6]
    a['years'][y][0] += 1; a['years'][y][1] += pnl > 0
    a['months'][m][0] += 1; a['months'][m][1] += pnl > 0
    a['symbols'].add(r.get('symbol', ''))


def metrics(a: dict[str, Any], stock_count: int, source_n: int = 0) -> dict[str, Any]:
    n = int(a['n'])
    if not n:
        return {'n': 0, 'fill_rate': 0.0}
    yc = {y: int(v[0]) for y, v in sorted(a['years'].items()) if v[0]}
    ywr = {y: round(v[1] / v[0] * 100, 2) for y, v in sorted(a['years'].items()) if v[0]}
    mc = {m: int(v[0]) for m, v in sorted(a['months'].items()) if v[0]}
    mwr = {m: round(v[1] / v[0] * 100, 2) for m, v in sorted(a['months'].items()) if v[0]}
    return {'n': n, 'fill_rate': round(n / source_n * 100, 2) if source_n else 100.0,
            'wr': round(a['wins'] / n * 100, 4), 'avg': round(a['sum'] / n, 4),
            'loss': int(a['loss']), 'micro': round(a['micro'] / n * 100, 2),
            'tp_pct': round(a['tp'] / n * 100, 2), 'sl_pct': round(a['sl'] / n * 100, 2),
            'gap_sl_pct': round(a['gap_sl'] / n * 100, 2), 'time_pct': round(a['time'] / n * 100, 2),
            'symbols': len(a['symbols']), 'per_stock': round(n / stock_count, 4),
            'year_counts': yc, 'year_wr': ywr, 'min_year_n': min(yc.values()) if yc else 0,
            'min_year_wr': round(min(ywr.values()) if ywr else 0, 2),
            'month_count': len(mc), 'min_month_n': min(mc.values()) if mc else 0,
            'min_month_wr': round(min(mwr.values()) if mwr else 0, 2)}


def load_bars(sym: str, cache: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    if sym in cache:
        return cache[sym]
    p = path60(sym)
    if not p:
        cache[sym] = []
        return []
    try:
        cache[sym] = json.loads(p.read_text())
    except Exception:
        cache[sym] = []
    return cache[sym]


def build_entry60_context(sym_ind: dict[str, str]):
    market = defaultdict(list)
    industry = defaultdict(lambda: defaultdict(list))
    stock_first = {}
    files = []
    seen = set()
    for d in K60_DIRS:
        for p in d.glob('*_60min_500.json'):
            sym = symbol_from_path(p)
            if not sym or sym in seen:
                continue
            seen.add(sym); files.append((sym, p))
    for sym, p in files:
        ind = sym_ind.get(sym)
        if not ind:
            continue
        try:
            bars = json.loads(p.read_text())
        except Exception:
            continue
        by_date = {}
        vols = []
        for b in bars:
            d = dn(b.get('t'))
            if not d or d in by_date:
                continue
            o, c, h, l, v = sf(b.get('o')), sf(b.get('c')), sf(b.get('h')), sf(b.get('l')), sf(b.get('v'), 0.0)
            if o <= 0 or math.isnan(c):
                continue
            medv = median(vols[-20:]) if vols[-20:] else math.nan
            volx = v / medv if medv and medv > 0 else math.nan
            ret = (c / o - 1) * 100
            pos = (c - l) / (h - l) * 100 if h > l else math.nan
            rec = {'ret': ret, 'up': ret > 0, 'strong1': ret > 1, 'volx': volx, 'pos': pos}
            by_date[d] = rec
            stock_first[(sym, d)] = rec
            market[d].append((sym, ind, ret, volx))
            industry[d][ind].append((ret, volx))
            vols.append(v)
    mctx = {}; ictx = {}
    for d, rows in market.items():
        rets = [r[2] for r in rows]
        volxs = [r[3] for r in rows if not math.isnan(r[3])]
        mctx[d] = {'entry60_mkt_n': len(rets), 'entry60_mkt_ret': median(rets),
                   'entry60_mkt_up': sum(v > 0 for v in rets) / len(rets) * 100,
                   'entry60_mkt_s1': sum(v > 1 for v in rets) / len(rets) * 100,
                   'entry60_mkt_volx': median(volxs) if volxs else math.nan}
    for d, mp in industry.items():
        for ind, rows in mp.items():
            if len(rows) < 5:
                continue
            rets = [r[0] for r in rows]
            volxs = [r[1] for r in rows if not math.isnan(r[1])]
            ictx[(d, ind)] = {'entry60_ind_n': len(rets), 'entry60_ind_ret': median(rets),
                              'entry60_ind_up': sum(v > 0 for v in rets) / len(rets) * 100,
                              'entry60_ind_s1': sum(v > 1 for v in rets) / len(rets) * 100,
                              'entry60_ind_volx': median(volxs) if volxs else math.nan}
    return stock_first, mctx, ictx, len(files)


def lifecycle(row: dict[str, Any], bars: list[dict[str, Any]]) -> dict[str, Any]:
    out = {}
    sweep = int(sf(row.get('sweep_i60'), -1)); mss = int(sf(row.get('mss_i60'), -1)); zl = sf(row.get('zone_low'))
    if not bars or sweep < 25 or mss >= len(bars) or mss < 0:
        return out
    pre = bars[max(0, sweep - 20):sweep]
    hs = [sf(b.get('h')) for b in pre]; ls = [sf(b.get('l')) for b in pre]
    if hs and ls and min(ls) > 0:
        out['acc_range_pct'] = (max(hs) / min(ls) - 1) * 100
    out['sweep_depth2'] = sf(row.get('sweep_depth'))
    out['mss_impulse'] = sf(row.get('local_high_break'))
    sig_day = dn(row.get('signal_time'))
    post = [b for b in bars[mss + 1:min(len(bars), mss + 5)] if dn(b.get('t')) == sig_day]
    if post and zl > 0:
        out['post_hold_min_pct'] = (min(sf(b.get('l')) for b in post) / zl - 1) * 100
    acc = brange(sf(out.get('acc_range_pct'))); sw = bdepth(sf(out.get('sweep_depth2'))); imp = bimp(sf(out.get('mss_impulse')))
    out.update({'acc_bucket': acc, 'sweep_bucket': sw, 'impulse_bucket': imp,
                'lifecycle_combo': f'{acc}|{sw}|{imp}'})
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sym_ind = {r['symbol']: r.get('industry', '') for r in json.loads(INDMAP.read_text()) if r.get('symbol')}
    stock_first, mctx, ictx, sixty_files = build_entry60_context(sym_ind)
    cache = {}
    rows = []
    with ROWS.open() as f:
        for r in csv.DictReader(f):
            sym = r['symbol']; d = dn(r['entry_date']); ind = sym_ind.get(sym, 'UNKNOWN')
            nr = dict(r); nr['industry'] = ind
            for k, v in stock_first.get((sym, d), {}).items(): nr['stock60_' + k] = v
            for k, v in mctx.get(d, {}).items(): nr[k] = v
            for k, v in ictx.get((d, ind), {}).items(): nr[k] = v
            nr['entry60_ind_vs_mkt_ret'] = sf(nr.get('entry60_ind_ret')) - sf(nr.get('entry60_mkt_ret'))
            nr['entry60_ind_vs_mkt_up'] = sf(nr.get('entry60_ind_up')) - sf(nr.get('entry60_mkt_up'))
            nr.update(lifecycle(nr, load_bars(sym, cache)))
            rows.append(nr)

    stock_count = len({r['symbol'] for r in rows})
    raw = blank(); ag = defaultdict(blank)
    for r in rows:
        add(raw, r)
        dims = {
            'entry60_mkt_ind_ret': f"M_{bret(sf(r.get('entry60_mkt_ret')))}|I_{bret(sf(r.get('entry60_ind_ret')))}",
            'entry60_mkt_ind_up': f"M_{bup(sf(r.get('entry60_mkt_up')))}|I_{bup(sf(r.get('entry60_ind_up')))}",
            'entry60_ind_rel_ret': brel(sf(r.get('entry60_ind_vs_mkt_ret'))),
            'entry60_stock_ret': bret(sf(r.get('stock60_ret'))),
            'entry60_stock_volx': bvol(sf(r.get('stock60_volx'))),
            'confirm_gap': bconfirm(sf(r.get('open_to_confirm_pct'))),
            'confirm_gap+ind_ret': f"{bconfirm(sf(r.get('open_to_confirm_pct')))}|I_{bret(sf(r.get('entry60_ind_ret')))}",
            'risk_after_fill+ind_ret': f"{r.get('risk_bucket')}|I_{bret(sf(r.get('entry60_ind_ret')))}",
            'lifecycle': r.get('lifecycle_combo', 'LC_NA'),
            'lifecycle+entry60_ind': f"{r.get('lifecycle_combo', 'LC_NA')}|I_{bret(sf(r.get('entry60_ind_ret')))}",
            'lifecycle+confirm': f"{r.get('lifecycle_combo', 'LC_NA')}|{bconfirm(sf(r.get('open_to_confirm_pct')))}",
            'lifecycle+ind+confirm': f"{r.get('lifecycle_combo', 'LC_NA')}|I_{bret(sf(r.get('entry60_ind_ret')))}|{bconfirm(sf(r.get('open_to_confirm_pct')))}",
        }
        for dim, val in dims.items():
            add(ag[(dim, val)], r)

    surfaces = []
    for (dim, val), a in ag.items():
        m = metrics(a, stock_count, len(rows))
        if m['n'] >= 20:
            surfaces.append({'dimension': dim, 'value': val, **m})
    surfaces.sort(key=lambda x: (x['min_year_wr'], x['wr'], x['avg'], x['n']), reverse=True)
    best_large = next((x for x in surfaces if x['n'] >= 80 and x['min_year_n'] >= 20), surfaces[0] if surfaces else None)

    rows_path = OUT / 'v293_enriched_rows.csv'
    if rows:
        fields = list(rows[0].keys())
        # Preserve later-added fields too.
        for r in rows:
            for k in r.keys():
                if k not in fields:
                    fields.append(k)
        with rows_path.open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)

    summary = {'version': 'V293_ENTRY60_PARTICIPATION_LIFECYCLE_NO_WRITE',
               'generated_at': datetime.now().isoformat(timespec='seconds'),
               'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
               'hypothesis': 'After V292 first60 hold confirmation, same-hour market/industry breadth and pre-entry lifecycle may separate real takeover from false continuation.',
               'source_rows': str(ROWS), 'source_n': len(rows), 'sixty_min_files': sixty_files,
               'raw_v292_best': metrics(raw, stock_count, len(rows)),
               'best_large': best_large, 'top_surfaces': surfaces[:60],
               'artifacts': {'out_dir': str(OUT), 'enriched_rows': str(rows_path), 'summary': str(OUT / 'v293_summary.json')}}
    (OUT / 'v293_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'latest': str(LATEST), 'raw': summary['raw_v292_best'], 'best_large': best_large, 'top10': surfaces[:10]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
