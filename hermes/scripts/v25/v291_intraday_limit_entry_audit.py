#!/usr/bin/env python3
"""V291 no-write: executable intraday limit-entry audit for V288 60m-first rows.

V288 generated same-source 60m SSL->reclaim->MSS->POI but entered at next daily open.
This tests a different direction: do not change the signal; change execution to a
pre-placed next-session intraday limit at the same-source 60m POI, then keep strict
A-share T+1 exits. Only entry-day 60m bars are used to decide whether the limit
would fill; exits still start from the next daily bar.
"""
from __future__ import annotations
import csv, json, math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
K60_DIRS = [BASE / 'kline_cache_60min', BASE / 'kline_cache']
KDAY = BASE / 'kline_cache'
V288 = json.loads((AUDIT / 'v288_same_source_60m_first_latest.json').read_text())
ROWS = Path(V288['artifacts']['best_rows'])
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v291_intraday_limit_entry_no_write_{TS}'
LATEST = AUDIT / 'v291_intraday_limit_entry_latest.json'


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


def sym_paths(sym: str):
    code, ex = sym.split('.')
    return [d / f'{code}_{ex}_60min_500.json' for d in K60_DIRS], KDAY / f'{code}_{ex}_daily_750.json'


def load60(sym: str, cache: dict[str, list[dict[str, Any]]]):
    if sym in cache:
        return cache[sym]
    paths, _ = sym_paths(sym)
    for p in paths:
        if p.exists():
            try:
                cache[sym] = json.loads(p.read_text())
                return cache[sym]
            except Exception:
                break
    cache[sym] = []
    return []


def load_daily(sym: str, cache: dict[str, list[dict[str, Any]]]):
    if sym in cache:
        return cache[sym]
    _, p = sym_paths(sym)
    if not p.exists():
        cache[sym] = []
        return []
    try:
        raw = json.loads(p.read_text())
    except Exception:
        cache[sym] = []
        return []
    out = []
    for b in raw:
        d = dn(b.get('t') or b.get('date'))
        if d:
            out.append({'d': d, 'o': sf(b.get('o')), 'h': sf(b.get('h')), 'l': sf(b.get('l')), 'c': sf(b.get('c'))})
    out.sort(key=lambda x: x['d'])
    cache[sym] = out
    return out


def replay_daily(daily: list[dict[str, Any]], entry_date: str, entry: float, sl: float, rr: float, max_hold: int):
    idx = next((i for i, b in enumerate(daily) if b['d'] == entry_date), None)
    if idx is None or idx >= len(daily) - 2 or entry <= 0 or sl <= 0 or sl >= entry:
        return None
    tp = entry + rr * (entry - sl)
    # Strict T+1: cannot exit on entry_date, replay starts next daily bar.
    for j in range(idx + 1, min(len(daily), idx + 1 + max_hold)):
        b = daily[j]
        o, h, l, c = b['o'], b['h'], b['l'], b['c']
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


def target_price(r: dict[str, str], mode: str):
    zl, zh = sf(r.get('zone_low')), sf(r.get('zone_high'))
    daily_open = sf(r.get('entry'))
    if zl <= 0 or zh <= 0 or zh < zl:
        return math.nan
    if mode == 'daily_open':
        return daily_open
    if mode == 'zone_high':
        return zh
    if mode == 'zone_mid':
        return (zl + zh) / 2
    if mode == 'zone_low':
        return zl
    if mode == 'zone_382':
        return zl + (zh - zl) * 0.382
    if mode == 'zone_618':
        return zl + (zh - zl) * 0.618
    return math.nan


def fill_intraday(row: dict[str, str], mode: str, bars60: list[dict[str, Any]], max_bars: int):
    entry_date = row['entry_date']
    target = target_price(row, mode)
    if mode == 'daily_open':
        return {'filled': True, 'fill_price': target, 'fill_time': entry_date + '_open', 'wait60': 0}
    if math.isnan(target) or target <= 0:
        return {'filled': False}
    daybars = [b for b in bars60 if dn(b.get('t')) == entry_date]
    if max_bars > 0:
        daybars = daybars[:max_bars]
    for i, b in enumerate(daybars):
        o, h, l = sf(b.get('o')), sf(b.get('h')), sf(b.get('l'))
        if math.isnan(o) or math.isnan(h) or math.isnan(l):
            continue
        # Conservative buy-limit semantics: if touched, record the limit price,
        # not a potentially better open below the limit.
        if l <= target <= max(h, o):
            return {'filled': True, 'fill_price': target, 'fill_time': str(b.get('t')), 'wait60': i}
        if o <= target:
            return {'filled': True, 'fill_price': target, 'fill_time': str(b.get('t')), 'wait60': i}
    return {'filled': False}


def blank():
    return {'n':0,'wins':0,'sum':0.0,'loss':0,'micro':0,'tp':0,'sl':0,'gap_sl':0,'time':0,'years':defaultdict(lambda:[0,0]),'months':defaultdict(lambda:[0,0]),'symbols':set(),'miss':0}


def add(a, r):
    pnl = sf(r.get('pnl'), 0.0); reason = str(r.get('reason', ''))
    a['n'] += 1; a['wins'] += pnl > 0; a['sum'] += pnl; a['loss'] += pnl <= 0; a['micro'] += 0 < pnl < 1
    a['tp'] += reason == 'TP'; a['sl'] += reason == 'SL'; a['gap_sl'] += reason == 'GAP_SL'; a['time'] += reason.startswith('TIME')
    y = r['entry_date'][:4]; m = r['entry_date'][:6]
    a['years'][y][0] += 1; a['years'][y][1] += pnl > 0
    a['months'][m][0] += 1; a['months'][m][1] += pnl > 0
    a['symbols'].add(r['symbol'])


def metrics(a, stock_count: int, source_n: int = 0):
    n = a['n']
    if not n:
        return {'n':0, 'fill_rate':0.0 if source_n else 0.0}
    yc = {y:int(v[0]) for y,v in sorted(a['years'].items())}
    ywr = {y:round(v[1]/v[0]*100,2) for y,v in sorted(a['years'].items()) if v[0]}
    mc = {m:int(v[0]) for m,v in sorted(a['months'].items())}
    mwr = {m:round(v[1]/v[0]*100,2) for m,v in sorted(a['months'].items()) if v[0]}
    return {'n':int(n),'fill_rate':round(n/source_n*100,2) if source_n else 100.0,'wr':round(a['wins']/n*100,4),'avg':round(a['sum']/n,4),'loss':int(a['loss']),'micro':round(a['micro']/n*100,2),'tp_pct':round(a['tp']/n*100,2),'sl_pct':round(a['sl']/n*100,2),'gap_sl_pct':round(a['gap_sl']/n*100,2),'time_pct':round(a['time']/n*100,2),'symbols':len(a['symbols']),'per_stock':round(n/stock_count,4),'year_counts':yc,'year_wr':ywr,'min_year_n':min(yc.values()) if yc else 0,'min_year_wr':round(min(ywr.values()) if ywr else 0,2),'month_count':len(mc),'min_month_n':min(mc.values()) if mc else 0,'min_month_wr':round(min(mwr.values()) if mwr else 0,2)}


def bucket(x: float, cuts: list[float], labels: list[str]):
    if math.isnan(x):
        return 'NA'
    for c, l in zip(cuts, labels):
        if x < c:
            return l
    return labels[-1]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with ROWS.open() as f:
        source = list(csv.DictReader(f))
    stock_count = len({r['symbol'] for r in source})
    c60, cd = {}, {}
    variants, variant_rows = [], {}
    modes = ['daily_open', 'zone_high', 'zone_618', 'zone_mid', 'zone_382', 'zone_low']
    wait_options = {'first2_60m':2, 'all_session':0}
    for mode in modes:
        waits = {'daily_open': 0} if mode == 'daily_open' else wait_options
        for wait_name, max_bars in waits.items():
            name = f'{mode}_{wait_name}'
            agg = blank(); rows = []
            for r in source:
                sym = r['symbol']
                bars60 = load60(sym, c60)
                fill = fill_intraday(r, mode, bars60, max_bars)
                if not fill.get('filled'):
                    continue
                daily = load_daily(sym, cd)
                entry = sf(fill['fill_price'])
                sl = sf(r['zone_low']) * 0.992
                out = replay_daily(daily, r['entry_date'], entry, sl, 1.2, 20)
                if not out:
                    continue
                row = dict(r)
                row.update(out)
                row.update({'entry_mode': mode, 'wait_mode': wait_name, 'entry': entry, 'fill_time': fill['fill_time'], 'wait60': fill['wait60'], 'rr': 1.2, 'max_hold': 20})
                row['risk_after_fill'] = (entry / sl - 1) * 100 if sl > 0 else math.nan
                row['discount_vs_open'] = (entry / sf(r.get('entry')) - 1) * 100 if sf(r.get('entry')) > 0 else math.nan
                row['t1_violation'] = row['exit_date'] <= row['entry_date']
                add(agg, row); rows.append(row)
            m = metrics(agg, stock_count, len(source))
            m['variant'] = name; m['entry_mode'] = mode; m['wait_mode'] = wait_name; m['t1_violations'] = sum(1 for x in rows if x['t1_violation'])
            variants.append(m); variant_rows[name] = rows
    variants.sort(key=lambda x: (x.get('min_year_wr',0), x.get('wr',0), x.get('avg',0), x.get('n',0)), reverse=True)
    best = variants[0] if variants else None
    best_rows = variant_rows.get(best['variant'], []) if best else []
    ag = defaultdict(blank)
    for r in best_rows:
        dims = {
            'reason': r.get('reason',''),
            'risk_after_fill': bucket(sf(r.get('risk_after_fill')), [2,4,6,8], ['R<2','R2_4','R4_6','R6_8','R>=8']),
            'discount_vs_open': bucket(sf(r.get('discount_vs_open')), [-5,-3,-1,0], ['DISC<-5','DISC-5_-3','DISC-3_-1','DISC-1_0','NO_DISC']),
            'wait60': bucket(sf(r.get('wait60')), [1,2,3], ['WAIT0','WAIT1','WAIT2','WAIT>=3']),
        }
        for dim, val in dims.items():
            add(ag[(dim, val)], r)
    decomp = []
    for (dim, val), a in ag.items():
        if a['n'] >= 20:
            decomp.append({'dimension':dim, 'value':val, **metrics(a, stock_count, len(best_rows))})
    decomp.sort(key=lambda x: (x['wr'], x['avg'], x['n']), reverse=True)
    rows_path = OUT / 'v291_best_rows.csv'
    if best_rows:
        fields = list(best_rows[0].keys())
        with rows_path.open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(best_rows)
    summary = {'version':'V291_INTRADAY_LIMIT_ENTRY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'hypothesis':'Keep V288 same-source 60m signal, but replace next daily open chase with executable next-session buy limits at 60m POI levels; exits remain strict T+1.','source_rows':str(ROWS),'source_n':len(source),'raw_v288_best':V288['best_variant'],'best_variant':best,'top_variants':variants[:20],'best_decomp':decomp[:30],'artifacts':{'out_dir':str(OUT),'best_rows':str(rows_path)}}
    (OUT / 'v291_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'latest':str(LATEST),'best':best,'top10':variants[:10],'decomp_top10':decomp[:10]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
