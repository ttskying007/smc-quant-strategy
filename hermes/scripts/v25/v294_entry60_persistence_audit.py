#!/usr/bin/env python3
"""V294 no-write: second/third 60m participation persistence after V292 first60 hold.

V293 showed the strongest current layer is entry-session first60 market+industry
synchronous breadth.  This audit tests the next concrete question: is that first
hour a durable takeover, or only an opening pulse?  We simulate executable delayed
entries at second/third 60m close when stock, market and industry participation
persist, then replay daily T+1 exits.

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
KDAY = BASE / 'kline_cache'
INDMAP = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
V293 = json.loads((AUDIT / 'v293_entry60_participation_lifecycle_latest.json').read_text())
ROWS = Path(V293['artifacts']['enriched_rows'])
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v294_entry60_persistence_no_write_{TS}'
LATEST = AUDIT / 'v294_entry60_persistence_latest.json'


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
    return f'{code}.{ex}' if len(code) == 6 else None


def path60(sym: str) -> Path | None:
    code, ex = sym.split('.')
    for d in K60_DIRS:
        p = d / f'{code}_{ex}_60min_500.json'
        if p.exists():
            return p
    return None


def pathday(sym: str) -> Path:
    code, ex = sym.split('.')
    return KDAY / f'{code}_{ex}_daily_750.json'


def load_json(p: Path) -> list[dict[str, Any]]:
    try:
        return json.loads(p.read_text())
    except Exception:
        return []


def load60(sym: str, cache: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    if sym not in cache:
        p = path60(sym)
        cache[sym] = load_json(p) if p else []
    return cache[sym]


def loadday(sym: str, cache: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    if sym in cache:
        return cache[sym]
    rows = []
    for b in load_json(pathday(sym)):
        d = dn(b.get('t') or b.get('date'))
        if d:
            rows.append({'d': d, 'o': sf(b.get('o')), 'h': sf(b.get('h')), 'l': sf(b.get('l')), 'c': sf(b.get('c'))})
    rows.sort(key=lambda x: x['d'])
    cache[sym] = rows
    return rows


def daybars(bars: list[dict[str, Any]], d: str) -> list[dict[str, Any]]:
    return [b for b in bars if dn(b.get('t')) == d]


def replay(daily: list[dict[str, Any]], entry_date: str, entry: float, sl: float, rr: float = 1.2, max_hold: int = 20) -> dict[str, Any] | None:
    idx = next((i for i, b in enumerate(daily) if b['d'] == entry_date), None)
    if idx is None or idx >= len(daily) - 2 or entry <= 0 or sl <= 0 or sl >= entry:
        return None
    tp = entry + rr * (entry - sl)
    for j in range(idx + 1, min(len(daily), idx + 1 + max_hold)):
        b = daily[j]
        o, h, l = b['o'], b['h'], b['l']
        if math.isnan(o) or math.isnan(h) or math.isnan(l):
            continue
        if o <= sl:
            return {'exit_date': b['d'], 'exit': o, 'reason': 'GAP_SL', 'pnl': (o / entry - 1) * 100, 'hold': j - idx}
        if l <= sl:
            return {'exit_date': b['d'], 'exit': sl, 'reason': 'SL', 'pnl': (sl / entry - 1) * 100, 'hold': j - idx}
        if h >= tp:
            return {'exit_date': b['d'], 'exit': tp, 'reason': 'TP', 'pnl': (tp / entry - 1) * 100, 'hold': j - idx}
    j = min(len(daily) - 1, idx + max_hold)
    b = daily[j]
    return {'exit_date': b['d'], 'exit': b['c'], 'reason': f'TIME{max_hold}', 'pnl': (b['c'] / entry - 1) * 100, 'hold': j - idx}


def blank() -> dict[str, Any]:
    return {'n': 0, 'wins': 0, 'sum': 0.0, 'loss': 0, 'micro': 0, 'tp': 0, 'sl': 0,
            'gap_sl': 0, 'time': 0, 'years': defaultdict(lambda: [0, 0]),
            'months': defaultdict(lambda: [0, 0]), 'symbols': set()}


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'), 0.0)
    reason = str(r.get('reason', ''))
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


def bup(x: float) -> str:
    if math.isnan(x): return 'UP_NA'
    if x < 50: return 'UP<50'
    if x < 65: return 'UP50_65'
    if x < 75: return 'UP65_75'
    return 'UP>=75'


def bdecay(x: float) -> str:
    if math.isnan(x): return 'DECAY_NA'
    if x < -15: return 'DECAY<-15'
    if x < -5: return 'DECAY_-15_-5'
    if x < 5: return 'DECAY_STABLE'
    return 'DECAY_EXPAND'


def bret(x: float) -> str:
    if math.isnan(x): return 'RET_NA'
    if x < 0: return 'RET<0'
    if x < 1: return 'RET0_1'
    return 'RET>=1'


def build_k_context(sym_ind: dict[str, str], ks: tuple[int, ...] = (1, 2, 3)) -> tuple[dict[tuple[str, str, int], dict[str, float]], dict[tuple[str, int], dict[str, float]], dict[tuple[str, str, int], dict[str, float]], int]:
    stock: dict[tuple[str, str, int], dict[str, float]] = {}
    market_rows: dict[tuple[str, int], list[float]] = defaultdict(list)
    ind_rows: dict[tuple[str, str, int], list[float]] = defaultdict(list)
    seen = set(); files = []
    for d in K60_DIRS:
        for p in d.glob('*_60min_500.json'):
            sym = symbol_from_path(p)
            if not sym or sym in seen or sym not in sym_ind:
                continue
            seen.add(sym); files.append((sym, p))
    for sym, p in files:
        ind = sym_ind[sym]
        byday: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for b in load_json(p):
            d = dn(b.get('t'))
            if d:
                byday[d].append(b)
        for d, bars in byday.items():
            bars.sort(key=lambda x: str(x.get('t')))
            if not bars:
                continue
            open0 = sf(bars[0].get('o'))
            if open0 <= 0:
                continue
            for k in ks:
                if len(bars) < k:
                    continue
                slice_b = bars[:k]
                close_k = sf(slice_b[-1].get('c'))
                low_k = min(sf(b.get('l')) for b in slice_b)
                high_k = max(sf(b.get('h')) for b in slice_b)
                if close_k <= 0 or math.isnan(low_k):
                    continue
                ret = (close_k / open0 - 1) * 100
                rec = {'ret': ret, 'up': float(ret > 0), 'low': low_k, 'high': high_k, 'close': close_k}
                stock[(sym, d, k)] = rec
                market_rows[(d, k)].append(ret)
                ind_rows[(d, ind, k)].append(ret)
    mctx = {}
    for key, rets in market_rows.items():
        mctx[key] = {'mkt_ret_k': median(rets), 'mkt_up_k': sum(v > 0 for v in rets) / len(rets) * 100, 'mkt_n_k': len(rets)}
    ictx = {}
    for key, rets in ind_rows.items():
        if len(rets) >= 5:
            ictx[key] = {'ind_ret_k': median(rets), 'ind_up_k': sum(v > 0 for v in rets) / len(rets) * 100, 'ind_n_k': len(rets)}
    return stock, mctx, ictx, len(files)


def simulate(rows: list[dict[str, Any]], sym_ind: dict[str, str], stock_ctx, mctx, ictx) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cache_day: dict[str, list[dict[str, Any]]] = {}
    out_rows = []
    variants = []
    stock_count = len({r['symbol'] for r in rows})
    configs = []
    for k in (2, 3):
        for mu in (50, 65):
            for iu in (50, 65):
                for require_decay in (False, True):
                    configs.append({'k': k, 'mup': mu, 'iup': iu, 'decay': require_decay})
    for cfg in configs:
        agg = blank(); local = []
        for r in rows:
            sym = r['symbol']; d = dn(r['entry_date']); ind = sym_ind.get(sym, '')
            zl = sf(r.get('zone_low')); zh = sf(r.get('zone_high'))
            s1 = stock_ctx.get((sym, d, 1), {}); sk = stock_ctx.get((sym, d, cfg['k']), {})
            m1 = mctx.get((d, 1), {}); mk = mctx.get((d, cfg['k']), {})
            i1 = ictx.get((d, ind, 1), {}); ik = ictx.get((d, ind, cfg['k']), {})
            if not sk or not mk or not ik or zl <= 0 or zh <= 0:
                continue
            m_up = sf(mk.get('mkt_up_k')); i_up = sf(ik.get('ind_up_k'))
            m_decay = m_up - sf(m1.get('mkt_up_k')); i_decay = i_up - sf(i1.get('ind_up_k'))
            if m_up < cfg['mup'] or i_up < cfg['iup']:
                continue
            if cfg['decay'] and (m_decay < -5 or i_decay < -5):
                continue
            if sf(sk.get('low')) <= zl or sf(sk.get('close')) <= zh:
                continue
            if cfg['k'] >= 2 and sf(sk.get('close')) < sf(s1.get('close')) * 0.995:
                continue
            entry = sf(sk.get('close'))
            sl = zl * 0.992
            res = replay(loadday(sym, cache_day), d, entry, sl)
            if not res:
                continue
            nr = dict(r)
            nr.update(res)
            nr.update({'entry': entry, 'entry_mode': f"k{cfg['k']}_persist_m{cfg['mup']}_i{cfg['iup']}_{'nodecay' if cfg['decay'] else 'raw'}",
                       'confirm_k': cfg['k'], 'persist_mkt_up': m_up, 'persist_ind_up': i_up,
                       'persist_mkt_decay': m_decay, 'persist_ind_decay': i_decay,
                       'persist_stock_ret': sf(sk.get('ret')), 'persist_mkt_ret': sf(mk.get('mkt_ret_k')),
                       'persist_ind_ret': sf(ik.get('ind_ret_k')), 'persist_stock_hold_zone': True,
                       'risk_after_persist': (entry / sl - 1) * 100 if sl > 0 else math.nan,
                       't1_violation': res['exit_date'] <= d})
            add(agg, nr); local.append(nr)
        m = metrics(agg, stock_count, len(rows))
        m.update({'variant': f"k{cfg['k']}_mup{cfg['mup']}_iup{cfg['iup']}_{'nodecay' if cfg['decay'] else 'raw'}",
                  'config': cfg, 't1_violations': sum(1 for x in local if x['t1_violation'])})
        variants.append((m, local))
        out_rows.extend(local)
    variants.sort(key=lambda x: (x[0].get('min_year_wr', 0), x[0].get('wr', 0), x[0].get('avg', 0), x[0].get('n', 0)), reverse=True)
    return [v[0] for v in variants], variants[0][1] if variants else []


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sym_ind = {r['symbol']: r.get('industry', '') for r in json.loads(INDMAP.read_text()) if r.get('symbol')}
    with ROWS.open() as f:
        source = list(csv.DictReader(f))
    stock_count = len({r['symbol'] for r in source})
    raw = blank()
    for r in source:
        add(raw, r)
    stock_ctx, mctx, ictx, files60 = build_k_context(sym_ind)
    variants, best_rows = simulate(source, sym_ind, stock_ctx, mctx, ictx)

    ag = defaultdict(blank)
    for r in best_rows:
        dims = {
            'persist_mkt_ind_up': f"M_{bup(sf(r.get('persist_mkt_up')))}|I_{bup(sf(r.get('persist_ind_up')))}",
            'persist_decay': f"M_{bdecay(sf(r.get('persist_mkt_decay')))}|I_{bdecay(sf(r.get('persist_ind_decay')))}",
            'persist_ret': f"M_{bret(sf(r.get('persist_mkt_ret')))}|I_{bret(sf(r.get('persist_ind_ret')))}|S_{bret(sf(r.get('persist_stock_ret')))}",
            'risk_after_persist': bret(sf(r.get('risk_after_persist')) - 4),
            'reason': r.get('reason', ''),
        }
        for dim, val in dims.items():
            add(ag[(dim, val)], r)
    decomp = []
    for (dim, val), a in ag.items():
        m = metrics(a, stock_count, len(best_rows))
        if m['n'] >= 10:
            decomp.append({'dimension': dim, 'value': val, **m})
    decomp.sort(key=lambda x: (x['min_year_wr'], x['wr'], x['avg'], x['n']), reverse=True)

    rows_path = OUT / 'v294_best_rows.csv'
    if best_rows:
        fields = list(best_rows[0].keys())
        for r in best_rows:
            for k in r:
                if k not in fields:
                    fields.append(k)
        with rows_path.open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(best_rows)
    summary = {'version': 'V294_ENTRY60_PERSISTENCE_NO_WRITE',
               'generated_at': datetime.now().isoformat(timespec='seconds'),
               'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
               'hypothesis': 'After first60 hold, second/third 60m market+industry persistence may separate opening pulse from durable takeover.',
               'source_rows': str(ROWS), 'source_n': len(source), 'sixty_min_files': files60,
               'raw_v293_source': metrics(raw, stock_count, len(source)),
               'best_variant': variants[0] if variants else None, 'top_variants': variants[:20],
               'best_decomp': decomp[:40],
               'artifacts': {'out_dir': str(OUT), 'best_rows': str(rows_path), 'summary': str(OUT / 'v294_summary.json')}}
    (OUT / 'v294_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'latest': str(LATEST), 'raw': summary['raw_v293_source'], 'best': summary['best_variant'], 'top10': variants[:10], 'decomp_top10': decomp[:10]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
