#!/usr/bin/env python3
"""V283 no-write: 60min previous-day reaction overlay on V280 layered grammar.

Only uses 60m bars dated before entry_date (the previous trading day), because
V280 daily grammar buys on next-day open after daily confirmation.  This is a
recent-window audit because available 60m cache is ~500 bars.
"""
from __future__ import annotations
import csv, json, math, bisect
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from statistics import median

BASE=Path('/root/.hermes'); AUDIT=BASE/'smc_audit'; K60A=BASE/'kline_cache_60min'; K60B=BASE/'kline_cache'
EVENTS=AUDIT/'v280_layered_state_grammar_no_write_20260702_205055/v280_events.csv'
TS=datetime.now().strftime('%Y%m%d_%H%M%S'); OUT=AUDIT/f'v283_60min_reaction_overlay_no_write_{TS}'; LATEST=AUDIT/'v283_60min_reaction_overlay_latest.json'

def sf(x,d=math.nan):
    try:
        if x is None or x=='': return d
        v=float(x); return v if not math.isnan(v) else d
    except Exception: return d

def dn(x):
    s=''.join(ch for ch in str(x or '') if ch.isdigit())
    return s[:8] if len(s)>=8 else ''

def sym_from_name(p):
    stem=p.stem.replace('_60min_500',''); code,ex=stem.split('_',1); return f'{code}.{ex}'

def blank(): return {'n':0,'wins':0,'sum':0.0,'loss':0,'tp':0,'sl':0,'time':0,'years':defaultdict(lambda:[0,0]),'symbols':set()}
def add(a,r):
    pnl=sf(r.get('pnl'),0); y=str(r.get('year') or dn(r.get('entry_date'))[:4]); reason=str(r.get('reason',''))
    a['n']+=1; a['wins']+=pnl>0; a['sum']+=pnl; a['loss']+=pnl<=0; a['tp']+=reason=='TP'; a['sl']+=reason=='SL'; a['time']+=reason.startswith('TIME'); a['years'][y][0]+=1; a['years'][y][1]+=pnl>0; a['symbols'].add(r.get('symbol',''))
def metrics(a):
    n=a['n']
    if not n: return {'n':0}
    yc={y:int(v[0]) for y,v in sorted(a['years'].items()) if v[0]}; ywr={y:round(v[1]/v[0]*100,2) for y,v in sorted(a['years'].items()) if v[0]}
    return {'n':n,'wr':round(a['wins']/n*100,2),'avg':round(a['sum']/n,3),'loss':a['loss'],'tp_pct':round(a['tp']/n*100,2),'sl_pct':round(a['sl']/n*100,2),'time_pct':round(a['time']/n*100,2),'symbols':len(a['symbols']),'yc':yc,'ywr':ywr,'min_year_n':min(yc.values()) if yc else 0,'minwr':round(min(ywr.values()) if ywr else 0,2)}

def bret(x):
    if math.isnan(x): return 'NA'
    if x < -1: return '<-1'
    if x < 0: return '-1_0'
    if x < 1: return '0_1'
    return '>=1'
def bpos(x):
    if math.isnan(x): return 'NA'
    if x < 35: return 'LOW_<35'
    if x < 60: return 'MID_35_60'
    return 'HIGH_>=60'
def byn(x): return 'Y' if x else 'N'

# Load 60m daily features per symbol/date.
features={}; dates_by_sym=defaultdict(list); files={}
for root in [K60A,K60B]:
    for fp in root.glob('*_60min_500.json'):
        try: sym=sym_from_name(fp)
        except Exception: continue
        if sym in files: continue
        files[sym]=fp
for sym,fp in files.items():
    try: bars=json.loads(fp.read_text())
    except Exception: continue
    day=defaultdict(list)
    for b in bars:
        d=dn(b.get('t') or b.get('date'))
        if d: day[d].append(b)
    for d,bs in day.items():
        bs=sorted(bs, key=lambda x: str(x.get('t') or x.get('date')))
        o=sf(bs[0].get('o')); c=sf(bs[-1].get('c')); hi=max(sf(b.get('h')) for b in bs); lo=min(sf(b.get('l')) for b in bs)
        if not o or math.isnan(c) or math.isnan(hi) or math.isnan(lo) or hi<=lo: continue
        first_hi=max(sf(b.get('h')) for b in bs[:2]); last_close=c
        pos=(c-lo)/(hi-lo)*100
        upbars=sum(sf(b.get('c'))>sf(b.get('o')) for b in bs)
        last2=sum(sf(b.get('c'))>sf(b.get('o')) for b in bs[-2:])
        features[(sym,d)]={'ret60':(c/o-1)*100,'pos60':pos,'upbars60':upbars,'last2up60':last2,'mss60':last_close>first_hi,'range60intraday':(hi/lo-1)*100}
        dates_by_sym[sym].append(d)
for sym in dates_by_sym: dates_by_sym[sym]=sorted(set(dates_by_sym[sym]))

def prev60_date(sym,entry):
    ds=dates_by_sym.get(sym,[]); i=bisect.bisect_left(ds,entry)-1
    return ds[i] if i>=0 else ''

rows=[]
with EVENTS.open(newline='') as f:
    for r in csv.DictReader(f):
        sym=r['symbol']; ed=dn(r['entry_date']); pd=prev60_date(sym,ed); ft=features.get((sym,pd))
        if not ft: continue
        nr=dict(r); nr['prev60_date']=pd; nr.update(ft)
        # zone touch on prev60 day: did intraday low actually test daily zone area before buy?
        rows.append(nr)

ag=defaultdict(blank)
for r in rows:
    fam=r['family']; reg=r['regime']; risk=sf(r.get('risk')); vol=str(r.get('vol_env'))
    ret=sf(r.get('ret60')); pos=sf(r.get('pos60')); mss=bool(r.get('mss60')); last2=sf(r.get('last2up60'),0)>=2
    dims={
        'family+prev60_ret':f'{fam}|RET{bret(ret)}',
        'family+prev60_pos':f'{fam}|POS{bpos(pos)}',
        'family+prev60_mss':f'{fam}|MSS{byn(mss)}',
        'family+prev60_combo':f'{fam}|RET{bret(ret)}|POS{bpos(pos)}|MSS{byn(mss)}|L2{byn(last2)}',
        'family+regime+prev60_combo':f'{fam}|{reg}|RET{bret(ret)}|POS{bpos(pos)}|MSS{byn(mss)}|L2{byn(last2)}',
    }
    if fam=='ABSORB_SSL_FAST_MSS' and risk>8 and vol=='LOW_VOL':
        dims['ABSORB_LOWVOL_RISK8+prev60']=f'RET{bret(ret)}|POS{bpos(pos)}|MSS{byn(mss)}|L2{byn(last2)}'
    for k,v in dims.items(): add(ag[(k,v)],r)

sur=[]
for (dim,val),a in ag.items():
    m=metrics(a)
    if m['n']>=20: sur.append({'dimension':dim,'value':val,**m})
sur.sort(key=lambda x:(x['minwr'],x['wr'],x['avg'],x['n']), reverse=True)
large=[x for x in sur if x['n']>=100 and x['min_year_n']>=20]
summary={'version':'V283_60MIN_REACTION_OVERLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'source_events':str(EVENTS),'sixty_min_files':len(files),'rows_with_60m_prevday':len(rows),'production_write':False,'frontend_write':False,'watchlist_write':False,'best_large':large[0] if large else None,'top_surfaces':sur[:80]}
OUT.mkdir(parents=True,exist_ok=True); (OUT/'v283_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)); LATEST.write_text(json.dumps(summary,ensure_ascii=False,indent=2))
with (OUT/'v283_top_surfaces.csv').open('w',newline='') as f:
    fields=['dimension','value','n','wr','avg','min_year_n','minwr','tp_pct','sl_pct','time_pct','symbols','yc','ywr']; w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); [w.writerow({k:r.get(k) for k in fields}) for r in sur[:300]]
print(json.dumps({'out':str(OUT),'latest':str(LATEST),'files':len(files),'rows':len(rows),'best_large':summary['best_large'],'top':sur[:5]},ensure_ascii=False,indent=2))
