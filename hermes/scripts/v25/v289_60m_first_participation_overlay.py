#!/usr/bin/env python3
"""V289 no-write: participation overlay on V288 same-source 60m-first rows."""
from __future__ import annotations
import bisect, csv, json, math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any
BASE=Path('/root/.hermes'); AUDIT=BASE/'smc_audit'; KDIR=BASE/'kline_cache'
V288=json.loads((AUDIT/'v288_same_source_60m_first_latest.json').read_text())
ROWS=Path(V288['artifacts']['best_rows'])
INDMAP=AUDIT/'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
TS=datetime.now().strftime('%Y%m%d_%H%M%S'); OUT=AUDIT/f'v289_60m_first_participation_overlay_no_write_{TS}'; LATEST=AUDIT/'v289_60m_first_participation_overlay_latest.json'

def sf(x:Any,d=math.nan):
    try:
        if x is None or x=='': return d
        v=float(x); return v if not math.isnan(v) else d
    except Exception: return d

def dn(x):
    s=''.join(ch for ch in str(x or '').replace('-','') if ch.isdigit()); return s[:8] if len(s)>=8 else ''

def sym_from_path(p:Path):
    stem=p.stem.replace('_daily_750',''); code,ex=stem.split('_',1); return f'{code}.{ex}'

def bret(x):
    if math.isnan(x): return 'RET_NA'
    if x<-1: return 'RET<-1'
    if x<0: return 'RET_-1_0'
    if x<1: return 'RET_0_1'
    return 'RET>=1'

def bup(x):
    if math.isnan(x): return 'UP_NA'
    if x<35: return 'UP<35'
    if x<50: return 'UP35_50'
    if x<65: return 'UP50_65'
    return 'UP>=65'

def brel(x):
    if math.isnan(x): return 'REL_NA'
    if x<-10: return 'REL<-10'
    if x<0: return 'REL_-10_0'
    if x<10: return 'REL0_10'
    return 'REL>=10'

def blank(): return {'n':0,'wins':0,'sum':0.0,'loss':0,'micro':0,'tp':0,'sl':0,'gap_sl':0,'time':0,'years':defaultdict(lambda:[0,0]),'months':defaultdict(lambda:[0,0]),'symbols':set()}

def add(a,r):
    pnl=sf(r.get('pnl'),0); reason=str(r.get('reason',''))
    a['n']+=1; a['wins']+=pnl>0; a['sum']+=pnl; a['loss']+=pnl<=0; a['micro']+=0<pnl<1
    a['tp']+=reason=='TP'; a['sl']+=reason=='SL'; a['gap_sl']+=reason=='GAP_SL'; a['time']+=reason.startswith('TIME')
    y=r['entry_date'][:4]; m=r['entry_date'][:6]; a['years'][y][0]+=1; a['years'][y][1]+=pnl>0; a['months'][m][0]+=1; a['months'][m][1]+=pnl>0; a['symbols'].add(r['symbol'])

def metrics(a,stock_count):
    n=a['n']
    if not n: return {'n':0}
    yc={y:int(v[0]) for y,v in sorted(a['years'].items())}; ywr={y:round(v[1]/v[0]*100,2) for y,v in sorted(a['years'].items())}
    mc={m:int(v[0]) for m,v in sorted(a['months'].items())}; mwr={m:round(v[1]/v[0]*100,2) for m,v in sorted(a['months'].items())}
    return {'n':int(n),'wr':round(a['wins']/n*100,4),'avg':round(a['sum']/n,4),'loss':int(a['loss']),'micro':round(a['micro']/n*100,2),'tp_pct':round(a['tp']/n*100,2),'sl_pct':round(a['sl']/n*100,2),'gap_sl_pct':round(a['gap_sl']/n*100,2),'time_pct':round(a['time']/n*100,2),'symbols':len(a['symbols']),'per_stock':round(n/stock_count,4),'year_counts':yc,'year_wr':ywr,'min_year_n':min(yc.values()) if yc else 0,'min_year_wr':round(min(ywr.values()) if ywr else 0,2),'month_count':len(mc),'min_month_n':min(mc.values()) if mc else 0,'min_month_wr':round(min(mwr.values()) if mwr else 0,2)}

def build_prev(sym_ind):
    daily=defaultdict(list); ind_daily=defaultdict(lambda:defaultdict(list))
    for fp in KDIR.glob('*_daily_750.json'):
        try: sym=sym_from_path(fp)
        except Exception: continue
        ind=sym_ind.get(sym)
        if not ind: continue
        try: bars=json.loads(fp.read_text())
        except Exception: continue
        seq=[]
        for b in bars:
            d=dn(b.get('t') or b.get('date')); c=sf(b.get('c'))
            if d and not math.isnan(c): seq.append((d,c))
        seq.sort()
        for i in range(1,len(seq)):
            d,c=seq[i]; pc=seq[i-1][1]
            if pc>0:
                ret=(c/pc-1)*100; daily[d].append((sym,ind,ret)); ind_daily[d][ind].append(ret)
    dates=sorted(daily); mkt={}; indmap={}
    for d,rows in daily.items():
        vals=[x[2] for x in rows]; mkt[d]={'mkt_up':sum(v>0 for v in vals)/len(vals)*100,'mkt_ret':median(vals),'mkt_s1':sum(v>1 for v in vals)/len(vals)*100}
    for d,mp in ind_daily.items():
        for ind,vals in mp.items():
            if len(vals)>=5: indmap[(d,ind)]={'ind_up':sum(v>0 for v in vals)/len(vals)*100,'ind_ret':median(vals),'ind_s1':sum(v>1 for v in vals)/len(vals)*100}
    def prev(d):
        i=bisect.bisect_left(dates,d)-1; return dates[i] if i>=0 else ''
    return prev,mkt,indmap

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    sym_ind={r['symbol']:r.get('industry','') for r in json.loads(INDMAP.read_text()) if r.get('symbol')}
    prev,mkt,indf=build_prev(sym_ind)
    rows=[]
    with ROWS.open() as f:
        for r in csv.DictReader(f):
            ind=sym_ind.get(r['symbol'],'UNKNOWN'); pd=prev(dn(r['entry_date'])); mf=mkt.get(pd,{}); inf=indf.get((pd,ind),{})
            r.update({'industry':ind,'prev_date':pd,**mf,**inf})
            r['rel_up']=sf(r.get('ind_up'))-sf(r.get('mkt_up')); r['rel_ret']=sf(r.get('ind_ret'))-sf(r.get('mkt_ret'))
            rows.append(r)
    stock_count=len({r['symbol'] for r in rows})
    raw=blank(); ag=defaultdict(blank)
    for r in rows:
        add(raw,r)
        dims={
            'mkt_ret':bret(sf(r.get('mkt_ret'))), 'ind_ret':bret(sf(r.get('ind_ret'))), 'mkt+ind_ret':f"M_{bret(sf(r.get('mkt_ret')))}|I_{bret(sf(r.get('ind_ret')))}", 'mkt+ind_up':f"M_{bup(sf(r.get('mkt_up')))}|I_{bup(sf(r.get('ind_up')))}", 'rel_ret':brel(sf(r.get('rel_ret'))), 'risk+participation':f"{r.get('risk_bucket')}|M_{bret(sf(r.get('mkt_ret')))}|I_{bret(sf(r.get('ind_ret')))}", 'gap+participation':f"{r.get('gap_bucket')}|M_{bret(sf(r.get('mkt_ret')))}|I_{bret(sf(r.get('ind_ret')))}", 'vol+participation':f"{r.get('vol_bucket')}|M_{bret(sf(r.get('mkt_ret')))}|I_{bret(sf(r.get('ind_ret')))}"}
        for dim,val in dims.items(): add(ag[(dim,val)],r)
    surfaces=[]
    for (dim,val),a in ag.items():
        m=metrics(a,stock_count)
        if m['n']>=40: surfaces.append({'dimension':dim,'value':val,**m})
    surfaces.sort(key=lambda x:(x['min_year_wr'],x['wr'],x['avg'],x['n']), reverse=True)
    # save filtered rows for best sizable surface
    best_large=next((x for x in surfaces if x['n']>=120 and x['min_year_n']>=20), surfaces[0] if surfaces else None)
    summary={'version':'V289_60M_FIRST_PARTICIPATION_OVERLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source_rows':str(ROWS),'rows':len(rows),'raw_best_v288':metrics(raw,stock_count),'best_large':best_large,'top_surfaces':surfaces[:50],'artifacts':{'out_dir':str(OUT)}}
    (OUT/'v289_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)); LATEST.write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps({'latest':str(LATEST),'raw':summary['raw_best_v288'],'best_large':best_large,'top10':surfaces[:10]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
