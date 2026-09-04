#!/usr/bin/env python3
"""V287 no-write: same-source 60min SMC generator audit.

Prior V284 showed that projecting daily zones down to 60m does not work: the
60m takeover and daily POI were not same-source.  This script inverts the flow:
find 60m sweep/reclaim/MSS/HL structures first, then evaluate next-day A-share
T+1 outcomes on daily bars.  It is a research audit only; no production,
frontend, or watchlist writes.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
K60_DIRS = [BASE / 'kline_cache_60min', BASE / 'kline_cache']
KDAY = BASE / 'kline_cache'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v287_same_source_60m_generator_no_write_{TS}'
LATEST = AUDIT / 'v287_same_source_60m_generator_latest.json'
YEARS = {'2025', '2026'}  # 60m cache is recent only.


def sf(x: Any, d: float = math.nan) -> float:
    try:
        if x is None or x == '': return d
        v = float(x)
        return v if not math.isnan(v) else d
    except Exception:
        return d


def dn(x: Any) -> str:
    s = ''.join(ch for ch in str(x or '').replace('-', '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def symbol_from_60(p: Path) -> str:
    stem = p.stem.replace('_60min_500', '').replace('_60min', '')
    code, exch = stem.split('_', 1)
    return f'{code}.{exch}'


def day_path(sym: str) -> Path:
    code, exch = sym.split('.')
    return KDAY / f'{code}_{exch}_daily_750.json'


def load_daily(sym: str) -> list[dict[str, Any]]:
    p = day_path(sym)
    if not p.exists(): return []
    try: raw = json.loads(p.read_text())
    except Exception: return []
    out = []
    for b in raw:
        d = dn(b.get('t') or b.get('date'))
        o, h, l, c = sf(b.get('o')), sf(b.get('h')), sf(b.get('l')), sf(b.get('c'))
        if d and all(not math.isnan(x) and x > 0 for x in [o, h, l, c]):
            out.append({'d': d, 'o': o, 'h': h, 'l': l, 'c': c})
    out.sort(key=lambda x: x['d'])
    return out


def load_60_file(p: Path) -> list[dict[str, Any]]:
    try: raw = json.loads(p.read_text())
    except Exception: return []
    out = []
    for b in raw:
        t = ''.join(ch for ch in str(b.get('t') or '') if ch.isdigit())
        if len(t) < 12: continue
        o, h, l, c = sf(b.get('o')), sf(b.get('h')), sf(b.get('l')), sf(b.get('c'))
        v = sf(b.get('v'), 0.0)
        if all(not math.isnan(x) and x > 0 for x in [o, h, l, c]):
            out.append({'t': t[:12], 'd': t[:8], 'hm': t[8:12], 'o': o, 'h': h, 'l': l, 'c': c, 'v': v})
    out.sort(key=lambda x: x['t'])
    return out


def blank() -> dict[str, Any]:
    return {'n':0,'wins':0,'sum':0.0,'loss':0,'tp':0,'sl':0,'time':0,'micro':0,'years':defaultdict(lambda:[0,0]),'symbols':set()}


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'), 0.0); y = str(r.get('year') or '')
    reason = str(r.get('reason') or '')
    a['n'] += 1; a['wins'] += pnl > 0; a['sum'] += pnl; a['loss'] += pnl <= 0
    a['tp'] += reason == 'TP'; a['sl'] += reason == 'SL'; a['time'] += reason.startswith('TIME')
    a['micro'] += 0 < pnl < 1
    a['years'][y][0] += 1; a['years'][y][1] += pnl > 0; a['symbols'].add(r.get('symbol',''))


def metrics(a: dict[str, Any], stock_count: int) -> dict[str, Any]:
    n = a['n']
    if not n: return {'n':0}
    yc = {y:int(v[0]) for y,v in sorted(a['years'].items()) if v[0]}
    ywr = {y:round(v[1]/v[0]*100,2) for y,v in sorted(a['years'].items()) if v[0]}
    return {'n':int(n),'wr':round(a['wins']/n*100,4),'avg':round(a['sum']/n,4),'loss':int(a['loss']),
            'micro':round(a['micro']/n*100,2),'tp_pct':round(a['tp']/n*100,2),'sl_pct':round(a['sl']/n*100,2),
            'time_pct':round(a['time']/n*100,2),'symbols':len(a['symbols']),'per_stock':round(n/stock_count,4) if stock_count else 0,
            'yc':yc,'ywr':ywr,'min_year_n':min(yc.values()) if yc else 0,'minwr':round(min(ywr.values()) if ywr else 0,2)}


def replay_daily(daily: list[dict[str, Any]], entry_idx: int, entry: float, sl: float, tp: float, max_hold: int = 10) -> tuple[float, str, int, str]:
    # A-share T+1: entry at daily[entry_idx].o, earliest exit is entry_idx+1.
    if entry_idx + 1 >= len(daily): return math.nan, 'NO_FUTURE', 0, ''
    last_i = min(len(daily) - 1, entry_idx + max_hold)
    for i in range(entry_idx + 1, last_i + 1):
        b = daily[i]
        # conservative if both hit: SL first.
        if b['l'] <= sl:
            px = min(sl, b['o']) if b['o'] < sl else sl
            return (px / entry - 1) * 100, 'SL', i - entry_idx, b['d']
        if b['h'] >= tp:
            px = max(tp, b['o']) if b['o'] > tp else tp
            return (px / entry - 1) * 100, 'TP', i - entry_idx, b['d']
    b = daily[last_i]
    return (b['c'] / entry - 1) * 100, f'TIME{max_hold}', last_i - entry_idx, b['d']


def daily_state(daily: list[dict[str, Any]], idx: int) -> str:
    if idx < 21: return 'STATE_NA'
    c = daily[idx]['c']; c20 = daily[idx-20]['c']; high20 = max(b['h'] for b in daily[idx-20:idx]); low20 = min(b['l'] for b in daily[idx-20:idx])
    ret20 = (c / c20 - 1) * 100 if c20 else 0
    pos = (c - low20) / (high20 - low20) if high20 > low20 else 0.5
    if ret20 > 8 and pos > 0.6: return 'STATE_UP'
    if ret20 < -8 and pos < 0.4: return 'STATE_DOWN'
    return 'STATE_RANGE'


def risk_bucket(x: float) -> str:
    if math.isnan(x): return 'RISK_NA'
    if x < 2: return 'RISK<2'
    if x < 4: return 'RISK2_4'
    if x < 6: return 'RISK4_6'
    if x < 8: return 'RISK6_8'
    return 'RISK>=8'


def relvol_bucket(x: float) -> str:
    if math.isnan(x): return 'VOL_NA'
    if x < 0.8: return 'VOL<0.8'
    if x < 1.2: return 'VOL0.8_1.2'
    if x < 2.0: return 'VOL1.2_2'
    return 'VOL>=2'


def generate_for_symbol(sym: str, bars60: list[dict[str, Any]], daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_day = defaultdict(list)
    for b in bars60:
        by_day[b['d']].append(b)
    dates60 = sorted(by_day)
    d_idx = {b['d']: i for i, b in enumerate(daily)}
    events = []
    for k, d in enumerate(dates60):
        if d[:4] not in YEARS or k < 5 or d not in d_idx or d_idx[d] + 1 >= len(daily):
            continue
        daybars = by_day[d]
        prevbars = [x for pd in dates60[max(0, k-5):k] for x in by_day[pd]]
        if len(daybars) < 3 or len(prevbars) < 12:
            continue
        prev_low = min(b['l'] for b in prevbars)
        prev_high = max(b['h'] for b in prevbars)
        prev_vol = [b.get('v',0.0) for b in prevbars if b.get('v',0.0) > 0]
        avg_prev_vol = sum(prev_vol)/len(prev_vol) if prev_vol else math.nan
        day_vol = sum(b.get('v',0.0) for b in daybars)
        relvol = day_vol / (avg_prev_vol * len(daybars)) if avg_prev_vol and not math.isnan(avg_prev_vol) else math.nan
        low_i = min(range(len(daybars)), key=lambda i: daybars[i]['l'])
        low_b = daybars[low_i]
        swept = low_b['l'] < prev_low * 0.998
        if not swept:
            continue
        reclaim_i = None
        for i in range(low_i, len(daybars)):
            if daybars[i]['c'] > prev_low:
                reclaim_i = i; break
        if reclaim_i is None:
            family = 'SAME60_TOUCH_NO_RECLAIM'
            mss_i = None
        else:
            pre_high = max(b['h'] for b in daybars[:max(low_i,1)]) if low_i > 0 else daybars[0]['h']
            mss_i = None
            for i in range(reclaim_i, len(daybars)):
                if daybars[i]['c'] > pre_high * 1.001:
                    mss_i = i; break
            if mss_i is None:
                family = 'SAME60_RECLAIM_NO_MSS'
            else:
                post_low = min(b['l'] for b in daybars[mss_i:])
                close_pos = (daybars[-1]['c'] - low_b['l']) / (max(b['h'] for b in daybars) - low_b['l']) if max(b['h'] for b in daybars) > low_b['l'] else 0
                if post_low < prev_low * 0.995:
                    family = 'SAME60_MSS_FAIL'
                elif close_pos >= 0.7:
                    family = 'SAME60_FULL_TAKEOVER'
                else:
                    family = 'SAME60_MSS_HOLD_WEAK_CLOSE'
        entry_idx = d_idx[d] + 1
        entry = daily[entry_idx]['o']
        sl = low_b['l'] * 0.995
        risk_pct = (entry / sl - 1) * 100 if sl > 0 else math.nan
        if math.isnan(risk_pct) or risk_pct <= 0 or risk_pct > 15:
            continue
        tp = entry + (entry - sl) * 2.0
        pnl, reason, hold, exit_date = replay_daily(daily, entry_idx, entry, sl, tp, 10)
        if math.isnan(pnl):
            continue
        di = d_idx[d]
        events.append({
            'symbol': sym, 'signal_date': d, 'entry_date': daily[entry_idx]['d'], 'exit_date': exit_date,
            'year': daily[entry_idx]['d'][:4], 'family': family, 'daily_state': daily_state(daily, di),
            'pnl': pnl, 'reason': reason, 'hold': hold, 'entry': entry, 'sl': sl, 'tp': tp,
            'risk_pct': risk_pct, 'risk_bucket': risk_bucket(risk_pct), 'relvol': relvol,
            'relvol_bucket': relvol_bucket(relvol), 'prev_low': prev_low, 'prev_high': prev_high,
            'sweep_low': low_b['l'], 'reclaim_i': reclaim_i if reclaim_i is not None else -1,
            'mss_i': mss_i if mss_i is not None else -1,
            't1': False,
        })
    return events


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {}
    for d in K60_DIRS:
        for p in d.glob('*_60min_500.json'):
            try: sym = symbol_from_60(p)
            except Exception: continue
            # Prefer longer / first cache entry.
            if sym not in files or p.stat().st_size > files[sym].stat().st_size:
                files[sym] = p
    events = []
    covered = 0
    for sym, fp in sorted(files.items()):
        daily = load_daily(sym)
        bars60 = load_60_file(fp)
        if not daily or not bars60: continue
        evs = generate_for_symbol(sym, bars60, daily)
        if evs: covered += 1; events.extend(evs)
    stock_count = len(files)
    allagg = blank(); dims = defaultdict(blank)
    for r in events:
        add(allagg, r)
        dimvals = [
            ('family', r['family']),
            ('family+state', f"{r['family']}|{r['daily_state']}"),
            ('family+risk', f"{r['family']}|{r['risk_bucket']}"),
            ('family+state+risk', f"{r['family']}|{r['daily_state']}|{r['risk_bucket']}"),
            ('family+state+risk+vol', f"{r['family']}|{r['daily_state']}|{r['risk_bucket']}|{r['relvol_bucket']}"),
        ]
        for dim, val in dimvals:
            add(dims[(dim, val)], r)
    surfaces = []
    for (dim, val), a in dims.items():
        m = metrics(a, stock_count)
        if m['n'] >= 25:
            surfaces.append({'dimension': dim, 'value': val, **m})
    surfaces.sort(key=lambda x: (x['minwr'], x['wr'], x['avg'], x['n']), reverse=True)
    fields = ['symbol','signal_date','entry_date','exit_date','year','family','daily_state','pnl','reason','hold','entry','sl','tp','risk_pct','risk_bucket','relvol','relvol_bucket','prev_low','prev_high','sweep_low','reclaim_i','mss_i','t1']
    with (OUT/'v287_events.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in events: w.writerow({k:r.get(k) for k in fields})
    with (OUT/'v287_surfaces.csv').open('w', newline='') as f:
        sfields = ['dimension','value','n','wr','avg','min_year_n','minwr','tp_pct','sl_pct','time_pct','symbols','yc','ywr']
        w = csv.DictWriter(f, fieldnames=sfields); w.writeheader()
        for r in surfaces[:300]: w.writerow({k:r.get(k) for k in sfields})
    summary = {'version':'V287_SAME_SOURCE_60M_GENERATOR_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
               'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
               'inputs':{'sixty_min_symbols':stock_count,'symbols_with_events':covered,'events':len(events),'years':sorted(YEARS)},
               'baseline':metrics(allagg, stock_count),'top_surfaces':surfaces[:40],
               'artifacts':{'out_dir':str(OUT),'events':str(OUT/'v287_events.csv'),'surfaces':str(OUT/'v287_surfaces.csv')}}
    (OUT/'v287_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'latest':str(LATEST),'out':str(OUT),'baseline':summary['baseline'],'top_surfaces':surfaces[:10]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
