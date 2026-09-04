#!/usr/bin/env python3
"""V292 no-write: next-session 60m confirmation entries for V288 same-source rows.

V291 proved next-day limit pullback into the 60m POI is toxic. This tests the
opposite executable direction: wait for next-session 60m continuation/hold evidence
before buying, without using any exit/outcome field and with strict T+1 daily exits.
"""
from __future__ import annotations
import csv, json, math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
BASE=Path('/root/.hermes'); AUDIT=BASE/'smc_audit'; K60=[BASE/'kline_cache_60min',BASE/'kline_cache']; KDAY=BASE/'kline_cache'
V288=json.loads((AUDIT/'v288_same_source_60m_first_latest.json').read_text()); ROWS=Path(V288['artifacts']['best_rows'])
TS=datetime.now().strftime('%Y%m%d_%H%M%S'); OUT=AUDIT/f'v292_next_session_60m_confirmation_no_write_{TS}'; LATEST=AUDIT/'v292_next_session_60m_confirmation_latest.json'

def sf(x:Any,d=math.nan):
    try:
        if x is None or x=='': return d
        v=float(x); return v if not math.isnan(v) else d
    except Exception: return d

def dn(x):
    s=''.join(ch for ch in str(x or '').replace('-','') if ch.isdigit()); return s[:8] if len(s)>=8 else ''

def paths(sym):
    c,e=sym.split('.'); return [d/f'{c}_{e}_60min_500.json' for d in K60], KDAY/f'{c}_{e}_daily_750.json'

def load60(sym,cache):
    if sym in cache: return cache[sym]
    ps,_=paths(sym)
    for p in ps:
        if p.exists():
            try: cache[sym]=json.loads(p.read_text()); return cache[sym]
            except Exception: pass
    cache[sym]=[]; return []

def loadday(sym,cache):
    if sym in cache: return cache[sym]
    _,p=paths(sym)
    if not p.exists(): cache[sym]=[]; return []
    try: raw=json.loads(p.read_text())
    except Exception: cache[sym]=[]; return []
    out=[]
    for b in raw:
        d=dn(b.get('t') or b.get('date'))
        if d: out.append({'d':d,'o':sf(b.get('o')),'h':sf(b.get('h')),'l':sf(b.get('l')),'c':sf(b.get('c'))})
    out.sort(key=lambda x:x['d']); cache[sym]=out; return out

def replay(daily, entry_date, entry, sl, rr=1.2, max_hold=20):
    idx=next((i for i,b in enumerate(daily) if b['d']==entry_date),None)
    if idx is None or idx>=len(daily)-2 or entry<=0 or sl<=0 or sl>=entry: return None
    tp=entry+rr*(entry-sl)
    for j in range(idx+1, min(len(daily), idx+1+max_hold)):
        b=daily[j]; o,h,l=b['o'],b['h'],b['l']
        if math.isnan(o) or math.isnan(h) or math.isnan(l): continue
        if o<=sl: return {'exit_date':b['d'],'exit':o,'reason':'GAP_SL','pnl':(o/entry-1)*100,'hold':j-idx}
        if l<=sl: return {'exit_date':b['d'],'exit':sl,'reason':'SL','pnl':(sl/entry-1)*100,'hold':j-idx}
        if h>=tp: return {'exit_date':b['d'],'exit':tp,'reason':'TP','pnl':(tp/entry-1)*100,'hold':j-idx}
    j=min(len(daily)-1,idx+max_hold); b=daily[j]
    return {'exit_date':b['d'],'exit':b['c'],'reason':f'TIME{max_hold}','pnl':(b['c']/entry-1)*100,'hold':j-idx}

def blank(): return {'n':0,'wins':0,'sum':0.0,'loss':0,'micro':0,'tp':0,'sl':0,'gap_sl':0,'time':0,'years':defaultdict(lambda:[0,0]),'months':defaultdict(lambda:[0,0]),'symbols':set()}

def add(a,r):
    pnl=sf(r.get('pnl'),0); reason=str(r.get('reason',''))
    a['n']+=1; a['wins']+=pnl>0; a['sum']+=pnl; a['loss']+=pnl<=0; a['micro']+=0<pnl<1; a['tp']+=reason=='TP'; a['sl']+=reason=='SL'; a['gap_sl']+=reason=='GAP_SL'; a['time']+=reason.startswith('TIME')
    y=r['entry_date'][:4]; m=r['entry_date'][:6]; a['years'][y][0]+=1; a['years'][y][1]+=pnl>0; a['months'][m][0]+=1; a['months'][m][1]+=pnl>0; a['symbols'].add(r['symbol'])

def metrics(a,stock_count,source_n=0):
    n=a['n']
    if not n: return {'n':0,'fill_rate':0.0}
    yc={y:int(v[0]) for y,v in sorted(a['years'].items())}; ywr={y:round(v[1]/v[0]*100,2) for y,v in sorted(a['years'].items())}; mc={m:int(v[0]) for m,v in sorted(a['months'].items())}; mwr={m:round(v[1]/v[0]*100,2) for m,v in sorted(a['months'].items())}
    return {'n':int(n),'fill_rate':round(n/source_n*100,2) if source_n else 100.0,'wr':round(a['wins']/n*100,4),'avg':round(a['sum']/n,4),'loss':int(a['loss']),'micro':round(a['micro']/n*100,2),'tp_pct':round(a['tp']/n*100,2),'sl_pct':round(a['sl']/n*100,2),'gap_sl_pct':round(a['gap_sl']/n*100,2),'time_pct':round(a['time']/n*100,2),'symbols':len(a['symbols']),'per_stock':round(n/stock_count,4),'year_counts':yc,'year_wr':ywr,'min_year_n':min(yc.values()) if yc else 0,'min_year_wr':round(min(ywr.values()) if ywr else 0,2),'month_count':len(mc),'min_month_n':min(mc.values()) if mc else 0,'min_month_wr':round(min(mwr.values()) if mwr else 0,2)}

def confirm(row,bars,mode):
    ed=row['entry_date']; zl=sf(row['zone_low']); zh=sf(row['zone_high']); open0=sf(row['entry'])
    ds=[b for b in bars if dn(b.get('t'))==ed]
    if not ds: return None
    b0=ds[0]; o0,h0,l0,c0=sf(b0.get('o')),sf(b0.get('h')),sf(b0.get('l')),sf(b0.get('c'))
    if mode=='first60_bull_hold_zone' and c0>o0 and l0>zl and c0>zh: return {'entry':c0,'fill_time':str(b0.get('t')),'wait60':0}
    if mode=='first60_strong_hold' and c0>o0 and l0>zh and c0/open0-1>0.005: return {'entry':c0,'fill_time':str(b0.get('t')),'wait60':0}
    if mode=='first2_close_above_open_high':
        for i,b in enumerate(ds[:2]):
            c=sf(b.get('c'))
            if c>h0*1.002 and sf(b.get('l'))>zl: return {'entry':c,'fill_time':str(b.get('t')),'wait60':i}
    if mode=='first3_momentum_no_zone_break':
        for i,b in enumerate(ds[:3]):
            if sf(b.get('l'))<=zl: return None
            if sf(b.get('c'))>max(h0,zh)*1.003: return {'entry':sf(b.get('c')),'fill_time':str(b.get('t')),'wait60':i}
    return None

def bucket(x,cuts,labels):
    if math.isnan(x): return 'NA'
    for c,l in zip(cuts,labels):
        if x<c: return l
    return labels[-1]

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with ROWS.open() as f: source=list(csv.DictReader(f))
    stock_count=len({r['symbol'] for r in source}); c60={}; cd={}
    modes=['first60_bull_hold_zone','first60_strong_hold','first2_close_above_open_high','first3_momentum_no_zone_break']
    variants=[]; rows_by={}
    for mode in modes:
        agg=blank(); rows=[]
        for r in source:
            sym=r['symbol']; fill=confirm(r,load60(sym,c60),mode)
            if not fill: continue
            entry=sf(fill['entry']); sl=sf(r['zone_low'])*0.992; out=replay(loadday(sym,cd),r['entry_date'],entry,sl)
            if not out: continue
            row=dict(r); row.update(out); row.update({'entry_mode':mode,'entry':entry,'fill_time':fill['fill_time'],'wait60':fill['wait60'],'risk_after_fill':(entry/sl-1)*100 if sl>0 else math.nan,'open_to_confirm_pct':(entry/sf(r.get('entry'))-1)*100 if sf(r.get('entry'))>0 else math.nan})
            row['t1_violation']=row['exit_date']<=row['entry_date']; add(agg,row); rows.append(row)
        m=metrics(agg,stock_count,len(source)); m['variant']=mode; m['t1_violations']=sum(1 for r in rows if r['t1_violation']); variants.append(m); rows_by[mode]=rows
    variants.sort(key=lambda x:(x.get('min_year_wr',0),x.get('wr',0),x.get('avg',0),x.get('n',0)),reverse=True)
    best=variants[0] if variants else None; best_rows=rows_by.get(best['variant'],[]) if best else []
    ag=defaultdict(blank)
    for r in best_rows:
        dims={'risk_after_fill':bucket(sf(r['risk_after_fill']),[2,4,6,8],['R<2','R2_4','R4_6','R6_8','R>=8']),'open_to_confirm':bucket(sf(r['open_to_confirm_pct']),[0,1,2,4],['<=0','0_1','1_2','2_4','>=4']),'wait60':bucket(sf(r['wait60']),[1,2,3],['WAIT0','WAIT1','WAIT2','WAIT>=3']),'reason':r['reason']}
        for dim,val in dims.items(): add(ag[(dim,val)],r)
    decomp=[]
    for (dim,val),a in ag.items():
        if a['n']>=15: decomp.append({'dimension':dim,'value':val,**metrics(a,stock_count,len(best_rows))})
    decomp.sort(key=lambda x:(x['wr'],x['avg'],x['n']),reverse=True)
    rows_path=OUT/'v292_best_rows.csv'
    if best_rows:
        with rows_path.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(best_rows[0].keys())); w.writeheader(); w.writerows(best_rows)
    summary={'version':'V292_NEXT_SESSION_60M_CONFIRMATION_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'hypothesis':'V291 showed POI limit pullback is toxic; test buying only after next-session 60m hold/continuation confirmation, with strict T+1 exits.','source_rows':str(ROWS),'source_n':len(source),'raw_v288_best':V288['best_variant'],'best_variant':best,'top_variants':variants,'best_decomp':decomp[:30],'artifacts':{'out_dir':str(OUT),'best_rows':str(rows_path)}}
    (OUT/'v292_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)); LATEST.write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps({'latest':str(LATEST),'best':best,'variants':variants,'decomp_top10':decomp[:10]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
