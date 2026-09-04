#!/usr/bin/env python3
"""V288 no-write audit: same-source 60m-first SMC generator.

Tests the next direction from V284/V287: instead of taking daily zones and asking
whether 60m confirms them, generate the POI/takeover sequence on 60m first, then
execute on the next daily session with strict T+1 exit replay.

No production/frontend/watchlist writes.
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
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v288_same_source_60m_first_no_write_{TS}'
LATEST = AUDIT / 'v288_same_source_60m_first_latest.json'


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


def sym_from_60(p: Path) -> str:
    stem = p.stem.replace('_60min_500', '').replace('_60m', '')
    code, exch = stem.split('_', 1)
    return f'{code}.{exch}'


def sym_to_day_path(sym: str) -> Path:
    code, exch = sym.split('.')
    return KDAY / f'{code}_{exch}_daily_750.json'


def load_daily(sym: str):
    p = sym_to_day_path(sym)
    if not p.exists(): return []
    try: bars = json.loads(p.read_text())
    except Exception: return []
    out = []
    for b in bars:
        d = dn(b.get('t') or b.get('date'))
        if d:
            out.append({'d': d, 'o': sf(b.get('o')), 'h': sf(b.get('h')), 'l': sf(b.get('l')), 'c': sf(b.get('c'))})
    out.sort(key=lambda x: x['d'])
    return out


def next_daily_index(daily, signal_day: str):
    for i, b in enumerate(daily):
        if b['d'] > signal_day:
            return i
    return None


def replay_daily(daily, entry_i: int, entry: float, sl: float, rr: float, max_hold: int):
    if entry_i is None or entry_i >= len(daily) - 2 or entry <= 0 or sl <= 0 or sl >= entry:
        return None
    tp = entry + rr * (entry - sl)
    # Strict A-share T+1: entry day cannot exit; replay starts next daily bar.
    for j in range(entry_i + 1, min(len(daily), entry_i + 1 + max_hold)):
        b = daily[j]
        o, h, l, c = b['o'], b['h'], b['l'], b['c']
        if math.isnan(o) or math.isnan(h) or math.isnan(l):
            continue
        if o <= sl:
            return {'exit_date': b['d'], 'exit': o, 'reason': 'GAP_SL', 'pnl': (o / entry - 1) * 100, 'hold': j - entry_i}
        if l <= sl:
            return {'exit_date': b['d'], 'exit': sl, 'reason': 'SL', 'pnl': (sl / entry - 1) * 100, 'hold': j - entry_i}
        if h >= tp:
            return {'exit_date': b['d'], 'exit': tp, 'reason': 'TP', 'pnl': (tp / entry - 1) * 100, 'hold': j - entry_i}
    j = min(len(daily) - 1, entry_i + max_hold)
    b = daily[j]
    return {'exit_date': b['d'], 'exit': b['c'], 'reason': f'TIME{max_hold}', 'pnl': (b['c'] / entry - 1) * 100, 'hold': j - entry_i}


def blank():
    return {'n':0,'wins':0,'sum':0.0,'loss':0,'micro':0,'tp':0,'sl':0,'time':0,'gap_sl':0,'years':defaultdict(lambda:[0,0]),'months':defaultdict(lambda:[0,0]),'symbols':set()}


def add(a, r):
    pnl = sf(r.get('pnl'), 0.0); reason = str(r.get('reason',''))
    a['n'] += 1; a['wins'] += pnl > 0; a['sum'] += pnl; a['loss'] += pnl <= 0; a['micro'] += 0 < pnl < 1
    a['tp'] += reason == 'TP'; a['sl'] += reason == 'SL'; a['gap_sl'] += reason == 'GAP_SL'; a['time'] += reason.startswith('TIME')
    y = r['entry_date'][:4]; m = r['entry_date'][:6]
    a['years'][y][0] += 1; a['years'][y][1] += pnl > 0; a['months'][m][0] += 1; a['months'][m][1] += pnl > 0
    a['symbols'].add(r['symbol'])


def metrics(a, stock_count):
    n=a['n']
    if not n: return {'n':0}
    yc={y:int(v[0]) for y,v in sorted(a['years'].items()) if v[0]}
    ywr={y:round(v[1]/v[0]*100,2) for y,v in sorted(a['years'].items()) if v[0]}
    mc={m:int(v[0]) for m,v in sorted(a['months'].items()) if v[0]}
    mwr={m:round(v[1]/v[0]*100,2) for m,v in sorted(a['months'].items()) if v[0]}
    return {'n':int(n),'wr':round(a['wins']/n*100,4),'avg':round(a['sum']/n,4),'loss':int(a['loss']),
            'micro':round(a['micro']/n*100,2),'tp_pct':round(a['tp']/n*100,2),'sl_pct':round(a['sl']/n*100,2),
            'gap_sl_pct':round(a['gap_sl']/n*100,2),'time_pct':round(a['time']/n*100,2),'symbols':len(a['symbols']),
            'per_stock':round(n/stock_count,4),'year_counts':yc,'year_wr':ywr,'min_year_n':min(yc.values()) if yc else 0,
            'min_year_wr':round(min(ywr.values()) if ywr else 0,2),'month_count':len(mc),'min_month_n':min(mc.values()) if mc else 0,
            'min_month_wr':round(min(mwr.values()) if mwr else 0,2)}


def find_60m_files():
    seen = {}
    for d in K60_DIRS:
        for p in d.glob('*_60min_500.json'):
            try: sym = sym_from_60(p)
            except Exception: continue
            # prefer dedicated 60min dir
            seen.setdefault(sym, p)
    return seen


def detect_events(sym: str, bars60: list[dict[str, Any]], daily: list[dict[str, Any]]):
    events = []
    if len(bars60) < 80 or len(daily) < 80:
        return events
    day_by_date = {b['d']: i for i,b in enumerate(daily)}
    last_signal_day = ''
    for i in range(30, len(bars60) - 5):
        b = bars60[i]
        t = str(b.get('t') or '')
        day = dn(t)
        if not day or day == last_signal_day:
            continue
        lows20 = [sf(x.get('l')) for x in bars60[i-20:i] if not math.isnan(sf(x.get('l')))]
        highs8 = [sf(x.get('h')) for x in bars60[i-8:i] if not math.isnan(sf(x.get('h')))]
        if len(lows20) < 15 or len(highs8) < 5:
            continue
        ssl = min(lows20); local_high = max(highs8)
        low, close, high, vol = sf(b.get('l')), sf(b.get('c')), sf(b.get('h')), sf(b.get('v'), 0)
        if not (low < ssl * 0.997 and close > ssl):
            continue
        sweep_depth = (ssl / low - 1) * 100 if low > 0 else math.nan
        # require volume expansion vs previous 20 60m bars, but bucket not hard gate.
        vols = [sf(x.get('v'), 0) for x in bars60[i-20:i] if sf(x.get('v'), 0) > 0]
        volr = vol / (sum(vols)/len(vols)) if vols else math.nan
        for j in range(i + 1, min(len(bars60), i + 5)):
            bj = bars60[j]
            if sf(bj.get('c')) <= local_high * 1.002:
                continue
            # Last bearish 60m candle from sweep window is the same-source POI.
            poi = None
            for k in range(j, max(-1, i - 8), -1):
                bk = bars60[k]
                if sf(bk.get('c')) < sf(bk.get('o')):
                    poi = (k, sf(bk.get('l')), sf(bk.get('h'))); break
            if not poi:
                break
            poi_i, zl, zh = poi
            if zl <= 0 or zh <= 0 or zh <= zl:
                break
            sig_day = dn(bj.get('t'))
            entry_i = next_daily_index(daily, sig_day)
            if entry_i is None:
                break
            entry = daily[entry_i]['o']
            gap_from_zone = (entry / zl - 1) * 100 if zl > 0 else math.nan
            risk = (entry / (zl * 0.992) - 1) * 100 if zl > 0 else math.nan
            if math.isnan(entry) or entry <= 0:
                break
            events.append({'symbol': sym, 'signal_time': str(bj.get('t')), 'signal_day': sig_day, 'entry_date': daily[entry_i]['d'],
                           'entry_i': entry_i, 'entry': entry, 'zone_low': zl, 'zone_high': zh, 'poi_i60': poi_i,
                           'sweep_i60': i, 'mss_i60': j, 'sweep_depth': sweep_depth, 'vol_ratio': volr,
                           'gap_from_zone': gap_from_zone, 'risk': risk, 'local_high_break': (sf(bj.get('c'))/local_high-1)*100})
            last_signal_day = day
            break
    return events


def bucket(x, cuts, labels):
    if math.isnan(x): return 'NA'
    for c,l in zip(cuts, labels):
        if x < c: return l
    return labels[-1]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = find_60m_files()
    stock_count = len(files)
    raw_events = []
    scanned = 0
    for sym, fp in sorted(files.items()):
        daily = load_daily(sym)
        try: bars60 = json.loads(fp.read_text())
        except Exception: continue
        evs = detect_events(sym, bars60, daily)
        raw_events.extend(evs); scanned += 1
    variants = []
    for rr in [1.2, 1.5, 2.0, 2.5]:
        for hold in [5, 10, 15, 20]:
            for risk_cap in [4, 6, 8, 12]:
                name=f'rr{rr}_h{hold}_risk{risk_cap}'
                agg=blank(); rows=[]
                for e in raw_events:
                    if sf(e['risk']) <= 0 or sf(e['risk']) > risk_cap: continue
                    if sf(e['gap_from_zone']) > risk_cap + 1.0: continue
                    daily = load_daily(e['symbol'])
                    sl = e['zone_low'] * 0.992
                    out = replay_daily(daily, int(e['entry_i']), sf(e['entry']), sl, rr, hold)
                    if not out: continue
                    r = dict(e); r.update(out); r['variant']=name; r['rr']=rr; r['max_hold']=hold; r['risk_cap']=risk_cap
                    # safety: same-day sell is a violation; should not happen because replay starts entry_i+1.
                    r['t1_violation'] = r['exit_date'] <= r['entry_date']
                    add(agg, r); rows.append(r)
                variants.append({'variant':name,'rr':rr,'max_hold':hold,'risk_cap':risk_cap, **metrics(agg, stock_count), 't1_violations':sum(1 for r in rows if r['t1_violation'])})
    variants.sort(key=lambda x:(x.get('min_year_wr',0), x.get('wr',0), x.get('avg',0), x.get('n',0)), reverse=True)
    best = variants[0] if variants else None
    # Write rows for best variant.
    best_rows=[]
    if best:
        rr, hold, risk_cap = best['rr'], best['max_hold'], best['risk_cap']
        for e in raw_events:
            if sf(e['risk']) <= 0 or sf(e['risk']) > risk_cap: continue
            if sf(e['gap_from_zone']) > risk_cap + 1.0: continue
            daily=load_daily(e['symbol']); out=replay_daily(daily, int(e['entry_i']), sf(e['entry']), e['zone_low']*0.992, rr, hold)
            if not out: continue
            r=dict(e); r.update(out); r['variant']=best['variant']; r['t1_violation']=r['exit_date'] <= r['entry_date']
            r['risk_bucket']=bucket(sf(r['risk']), [2,4,6,8], ['R<2','R2_4','R4_6','R6_8','R>=8'])
            r['gap_bucket']=bucket(sf(r['gap_from_zone']), [1,3,5,8], ['G<1','G1_3','G3_5','G5_8','G>=8'])
            r['vol_bucket']=bucket(sf(r['vol_ratio']), [0.8,1.2,2.0], ['VOL<0.8','VOL0.8_1.2','VOL1.2_2','VOL>=2'])
            add_row = r
            best_rows.append(add_row)
    ag=defaultdict(blank)
    for r in best_rows:
        for k in [('risk',r['risk_bucket']),('gap',r['gap_bucket']),('vol',r['vol_bucket']),('reason',r['reason'])]:
            add(ag[k], r)
    decomp=[]
    for (dim,val),a in ag.items():
        if a['n']>=10:
            decomp.append({'dimension':dim,'value':val,**metrics(a,stock_count)})
    decomp.sort(key=lambda x:(x['wr'],x['avg'],x['n']), reverse=True)
    rows_path=OUT/'v288_best_rows.csv'
    if best_rows:
        fields=list(best_rows[0].keys())
        with rows_path.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(best_rows)
    summary={'version':'V288_SAME_SOURCE_60M_FIRST_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
             'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
             'design':{'hypothesis':'Generate 60m SSL sweep→reclaim→MSS→same-source 60m POI first, then next daily open entry; do not reuse daily zone overlay.',
                       'coverage_warning':'Local 60m cache is ~500 bars and mostly recent 2025/2026; this is full-market over available 60m cache, not full 2023-2026.'},
             'inputs':{'sixty_min_files':stock_count,'scanned':scanned,'raw_events':len(raw_events)},
             'best_variant':best,'top_variants':variants[:30],'best_decomp':decomp[:30],
             'artifacts':{'out_dir':str(OUT),'best_rows':str(rows_path) if best_rows else ''}}
    (OUT/'v288_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    LATEST.write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps({'latest':str(LATEST),'out':str(OUT),'inputs':summary['inputs'],'best':best,'top5':variants[:5],'decomp':decomp[:8]},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
