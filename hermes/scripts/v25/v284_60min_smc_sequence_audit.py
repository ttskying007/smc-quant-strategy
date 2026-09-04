#!/usr/bin/env python3
"""V284 no-write: true 60min SMC sequence overlay on V280 daily grammar.

Purpose: test whether daily time-ordered SMC candidates fail because the entry
precondition is missing at lower timeframe.  Unlike V283's coarse ret/position
features, this audit detects a 60m internal sequence using only bars strictly
before the daily entry date (normally the previous trading day):

  zone/SSL touch -> reclaim -> micro MSS/BOS -> optional HL retest/hold

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
from typing import Any

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
K60A = BASE / 'kline_cache_60min'
K60B = BASE / 'kline_cache'
EVENTS = AUDIT / 'v280_layered_state_grammar_no_write_20260702_205055/v280_events.csv'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v284_60min_smc_sequence_no_write_{TS}'
LATEST = AUDIT / 'v284_60min_smc_sequence_latest.json'


def sf(x: Any, d: float = math.nan) -> float:
    try:
        if x is None or x == '':
            return d
        v = float(x)
        return v if not math.isnan(v) else d
    except Exception:
        return d


def dn(x: Any) -> str:
    s = ''.join(ch for ch in str(x or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def sym_from_name(p: Path) -> str:
    stem = p.stem.replace('_60min_500', '')
    code, ex = stem.split('_', 1)
    return f'{code}.{ex}'


def blank() -> dict[str, Any]:
    return {
        'n': 0, 'wins': 0, 'sum': 0.0, 'loss': 0, 'tp': 0, 'sl': 0, 'time': 0,
        'years': defaultdict(lambda: [0, 0]), 'symbols': set(),
    }


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'), 0)
    y = str(r.get('year') or dn(r.get('entry_date'))[:4])
    reason = str(r.get('reason', ''))
    a['n'] += 1
    a['wins'] += pnl > 0
    a['sum'] += pnl
    a['loss'] += pnl <= 0
    a['tp'] += reason == 'TP'
    a['sl'] += reason == 'SL'
    a['time'] += reason.startswith('TIME')
    a['years'][y][0] += 1
    a['years'][y][1] += pnl > 0
    a['symbols'].add(r.get('symbol', ''))


def metrics(a: dict[str, Any]) -> dict[str, Any]:
    n = a['n']
    if not n:
        return {'n': 0}
    yc = {y: int(v[0]) for y, v in sorted(a['years'].items()) if v[0]}
    ywr = {y: round(v[1] / v[0] * 100, 2) for y, v in sorted(a['years'].items()) if v[0]}
    return {
        'n': n,
        'wr': round(a['wins'] / n * 100, 2),
        'avg': round(a['sum'] / n, 3),
        'loss': a['loss'],
        'tp_pct': round(a['tp'] / n * 100, 2),
        'sl_pct': round(a['sl'] / n * 100, 2),
        'time_pct': round(a['time'] / n * 100, 2),
        'symbols': len(a['symbols']),
        'yc': yc,
        'ywr': ywr,
        'min_year_n': min(yc.values()) if yc else 0,
        'minwr': round(min(ywr.values()) if ywr else 0, 2),
    }


def bucket_risk(x: float) -> str:
    if math.isnan(x): return 'RISK_NA'
    if x < 4: return 'RISK<4'
    if x < 6: return 'RISK4_6'
    if x < 8: return 'RISK6_8'
    return 'RISK>=8'


def bucket_range(x: float) -> str:
    if math.isnan(x): return 'RNG_NA'
    if x < 15: return 'RNG<15'
    if x < 25: return 'RNG15_25'
    return 'RNG>=25'


def load_60m() -> tuple[dict[tuple[str, str], list[dict[str, float]]], dict[str, list[str]], int]:
    files: dict[str, Path] = {}
    for root in [K60A, K60B]:
        if not root.exists():
            continue
        for fp in root.glob('*_60min_500.json'):
            try:
                sym = sym_from_name(fp)
            except Exception:
                continue
            if sym not in files:
                files[sym] = fp
    bars_by_day: dict[tuple[str, str], list[dict[str, float]]] = {}
    dates_by_sym: dict[str, list[str]] = defaultdict(list)
    for sym, fp in files.items():
        try:
            bars = json.loads(fp.read_text())
        except Exception:
            continue
        day: dict[str, list[dict[str, float]]] = defaultdict(list)
        for b in bars:
            d = dn(b.get('t') or b.get('date'))
            if d:
                nb = {
                    'o': sf(b.get('o')), 'c': sf(b.get('c')),
                    'h': sf(b.get('h')), 'l': sf(b.get('l')),
                    'v': sf(b.get('v'), 0.0), 't': str(b.get('t') or b.get('date') or ''),
                }
                if not any(math.isnan(nb[k]) for k in ['o', 'c', 'h', 'l']):
                    day[d].append(nb)
        for d, bs in day.items():
            bs = sorted(bs, key=lambda x: x['t'])
            if len(bs) >= 3:
                bars_by_day[(sym, d)] = bs
                dates_by_sym[sym].append(d)
    return bars_by_day, {s: sorted(set(ds)) for s, ds in dates_by_sym.items()}, len(files)


def prev_date(dates_by_sym: dict[str, list[str]], sym: str, entry: str) -> str:
    ds = dates_by_sym.get(sym, [])
    i = bisect.bisect_left(ds, entry) - 1
    return ds[i] if i >= 0 else ''


def seq_features(bs: list[dict[str, float]], zone_low: float, zone_high: float) -> dict[str, Any]:
    """Detect same-day 60m sequence relative to daily demand zone.

    The sequence is intentionally conservative with only 4 A-share 60m bars/day:
    - touch: wick overlaps the demand zone or sweeps below it.
    - reclaim: after touch, close returns above zone_low.
    - micro_mss: after reclaim, close breaks the max high before/till touch.
    - hl_hold: after mss, no later close below zone_low and any retest holds above zone_low.
    """
    if math.isnan(zone_low) or math.isnan(zone_high) or zone_low <= 0 or zone_high < zone_low:
        return {'seq': 'ZONE_NA'}
    day_o, day_c = bs[0]['o'], bs[-1]['c']
    day_hi, day_lo = max(b['h'] for b in bs), min(b['l'] for b in bs)
    day_rng = (day_hi / day_lo - 1) * 100 if day_lo > 0 else math.nan
    pos = (day_c - day_lo) / (day_hi - day_lo) * 100 if day_hi > day_lo else math.nan
    ret = (day_c / day_o - 1) * 100 if day_o > 0 else math.nan

    touch_i = None
    sweep_i = None
    for i, b in enumerate(bs):
        overlap = b['l'] <= zone_high and b['h'] >= zone_low
        ssl_sweep = b['l'] < zone_low * 0.997
        if overlap or ssl_sweep:
            touch_i = i
            if ssl_sweep:
                sweep_i = i
            break
    if touch_i is None:
        return {'seq': 'NO_ZONE_TOUCH', 'ret60': ret, 'pos60': pos, 'range60': day_rng}

    reclaim_i = None
    for j in range(touch_i, len(bs)):
        if bs[j]['c'] >= zone_low:
            reclaim_i = j
            break
    if reclaim_i is None:
        return {'seq': 'TOUCH_NO_RECLAIM', 'touch_i': touch_i, 'sweep_i': sweep_i, 'ret60': ret, 'pos60': pos, 'range60': day_rng}

    pre_hi = max(b['h'] for b in bs[:max(1, touch_i + 1)])
    mss_i = None
    for j in range(reclaim_i, len(bs)):
        # tiny penetration buffer avoids one-tick equality being counted as structure break
        if bs[j]['c'] > pre_hi * 1.001:
            mss_i = j
            break
    if mss_i is None:
        return {'seq': 'RECLAIM_NO_MSS', 'touch_i': touch_i, 'reclaim_i': reclaim_i, 'sweep_i': sweep_i, 'ret60': ret, 'pos60': pos, 'range60': day_rng}

    later = bs[mss_i + 1:]
    retest = any(b['l'] <= max(zone_high, pre_hi) and b['l'] >= zone_low * 0.997 for b in later)
    close_break = any(b['c'] < zone_low for b in bs[mss_i:])
    hl_hold = not close_break and (not later or min(b['l'] for b in later) >= zone_low * 0.997)
    strong_close = day_c >= max(zone_high, pre_hi) and pos >= 60

    if hl_hold and (retest or strong_close):
        seq = 'FULL_TAKEOVER'
    elif not close_break:
        seq = 'MSS_HOLD_NO_RETEST'
    else:
        seq = 'MSS_THEN_FAIL'
    return {
        'seq': seq, 'touch_i': touch_i, 'reclaim_i': reclaim_i, 'mss_i': mss_i, 'sweep_i': sweep_i,
        'retest60': retest, 'hl_hold60': hl_hold, 'strong_close60': strong_close,
        'ret60': ret, 'pos60': pos, 'range60': day_rng,
    }


def main() -> None:
    bars_by_day, dates_by_sym, nfiles = load_60m()
    rows: list[dict[str, Any]] = []
    with EVENTS.open(newline='') as f:
        for r in csv.DictReader(f):
            sym = r['symbol']
            ed = dn(r['entry_date'])
            pd = prev_date(dates_by_sym, sym, ed)
            bs = bars_by_day.get((sym, pd))
            if not bs:
                continue
            zlow, zhigh = sf(r.get('zone_low')), sf(r.get('zone_high'))
            ft = seq_features(bs, zlow, zhigh)
            nr = dict(r)
            nr['prev60_date'] = pd
            nr.update(ft)
            rows.append(nr)

    ag: dict[tuple[str, str], dict[str, Any]] = defaultdict(blank)
    for r in rows:
        fam = r['family']; reg = r['regime']; seq = r.get('seq', 'NA')
        risk = sf(r.get('risk')); rng = sf(r.get('range60')); vol = str(r.get('vol_env'))
        sweep = 'SWEEPY' if r.get('sweep_i') not in (None, '', 'None') else 'SWEEPN'
        hold = 'HOLDY' if r.get('hl_hold60') in (True, 'True', '1', 1) else 'HOLDN'
        dims = {
            'seq': str(seq),
            'family+seq': f'{fam}|{seq}',
            'family+regime+seq': f'{fam}|{reg}|{seq}',
            'family+regime+seq+sweep': f'{fam}|{reg}|{seq}|{sweep}',
            'family+regime+seq+risk': f'{fam}|{reg}|{seq}|{bucket_risk(risk)}',
            'family+regime+seq+range': f'{fam}|{reg}|{seq}|{bucket_range(rng)}',
            'family+regime+seq+vol': f'{fam}|{reg}|{seq}|{vol}',
            'family+regime+seq+hold': f'{fam}|{reg}|{seq}|{hold}',
        }
        for k, v in dims.items():
            add(ag[(k, v)], r)

    surfaces = []
    for (dim, val), a in ag.items():
        m = metrics(a)
        if m['n'] >= 20:
            surfaces.append({'dimension': dim, 'value': val, **m})
    surfaces.sort(key=lambda x: (x['minwr'], x['wr'], x['avg'], x['n']), reverse=True)
    large = [x for x in surfaces if x['n'] >= 100 and x['min_year_n'] >= 20]

    seq_ag: dict[str, dict[str, Any]] = defaultdict(blank)
    for r in rows:
        add(seq_ag[str(r.get('seq', 'NA'))], r)
    seq_summary = {k: metrics(v) for k, v in sorted(seq_ag.items())}

    summary = {
        'version': 'V284_60MIN_SMC_SEQUENCE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'source_events': str(EVENTS),
        'sixty_min_files': nfiles,
        'rows_with_60m_prevday': len(rows),
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'best_large': large[0] if large else None,
        'seq_summary': seq_summary,
        'top_surfaces': surfaces[:100],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'v284_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    with (OUT / 'v284_top_surfaces.csv').open('w', newline='') as f:
        fields = ['dimension', 'value', 'n', 'wr', 'avg', 'min_year_n', 'minwr', 'tp_pct', 'sl_pct', 'time_pct', 'symbols', 'yc', 'ywr']
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in surfaces[:500]:
            w.writerow({k: r.get(k) for k in fields})
    with (OUT / 'v284_rows.csv').open('w', newline='') as f:
        fields = ['symbol','entry_date','year','family','regime','seq','prev60_date','pnl','reason','risk','zone_low','zone_high','touch_i','reclaim_i','mss_i','sweep_i','retest60','hl_hold60','strong_close60','ret60','pos60','range60']
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(json.dumps({'out': str(OUT), 'latest': str(LATEST), 'rows': len(rows), 'best_large': summary['best_large'], 'seq_summary': seq_summary, 'top': surfaces[:8]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
