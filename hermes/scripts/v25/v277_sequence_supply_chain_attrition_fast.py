#!/usr/bin/env python3
"""V277 no-write fast full-market chronological SMC sequence attrition audit.

Fixes V276 timeout by aggregating in-stream instead of materializing tens of
millions of variant rows. Full market, 2023-2026, no production/frontend writes.
"""
from __future__ import annotations
import json, math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

BASE=Path('/root/.hermes'); KDIR=BASE/'kline_cache'; TS=datetime.now().strftime('%Y%m%d_%H%M%S')
OUT=BASE/f'smc_audit/v277_sequence_supply_chain_attrition_fast_no_write_{TS}'
LATEST=BASE/'smc_audit/v277_sequence_supply_chain_attrition_fast_latest.json'
YEARS={'2023','2024','2025','2026'}
BOS_LBS=[10,20,40]; DEMAND_LBS=[3,5,8,12,20]; SSL_WINS=[0,5,10,20,40,80]; WAITS=[3,5,8,12,20]
MODES=['strict','soft_mid','touch_bull','support_hold']

def f(x:Any,d=math.nan)->float:
    try:
        if x is None or x=='': return d
        v=float(x); return v if not math.isnan(v) else d
    except Exception: return d

def ds(b): return str(b.get('t',b.get('date',''))).replace('.0','')[:8]
def sym(p:Path):
    s=p.stem.replace('_daily_750',''); c,e=s.split('_',1); return f'{c}.{e}'

def mode_ok(mode,b,zl,zh):
    o=f(b.get('o')); c=f(b.get('c')); h=f(b.get('h')); l=f(b.get('l'))
    if any(math.isnan(x) for x in (o,c,h,l)) or h<=l or l>zh*1.005: return False
    rng=h-l
    if mode=='strict': return c>=zh and c>o and (c-l)/rng>=0.55
    if mode=='soft_mid': return c>=(zl+zh)/2 and (c-l)/rng>=0.45
    if mode=='touch_bull': return c>o and c>=zl
    if mode=='support_hold': return c>=zl
    return False

def replay(bars,ei,entry,sl,rr=1.5,max_hold=10):
    if ei+1>=len(bars): return None
    tp=entry+(entry-sl)*rr; last=min(len(bars)-1,ei+max_hold); xp=f(bars[last].get('c')); xi=last; reason=f'TIME{max_hold}'
    for i in range(ei+1,last+1):
        lo=f(bars[i].get('l')); hi=f(bars[i].get('h'))
        if lo<=sl: xi=i; xp=sl; reason='SL'; break
        if hi>=tp: xi=i; xp=tp; reason='TP'; break
    return {'pnl':(xp/entry-1)*100,'year':ds(bars[ei])[:4],'exit_reason':reason,'t1':ds(bars[xi])==ds(bars[ei])}

def blank(): return {'n':0,'wins':0,'pnl_sum':0.0,'pnl_vals':[],'micro':0,'loss':0,'t1':0,'years':defaultdict(lambda:[0,0]),'symbols':set()}
def add(acc,pnl,year,symbol,t1=False):
    acc['n']+=1; acc['wins']+=int(pnl>0); acc['pnl_sum']+=pnl; acc['pnl_vals'].append(pnl); acc['micro']+=int(0<pnl<1); acc['loss']+=int(pnl<=0); acc['t1']+=int(bool(t1)); acc['years'][year][0]+=1; acc['years'][year][1]+=int(pnl>0); acc['symbols'].add(symbol)
def met(acc):
    n=acc['n']
    if not n: return {'n':0}
    vals=sorted(acc['pnl_vals']); med=vals[n//2] if n%2 else (vals[n//2-1]+vals[n//2])/2
    yc={y:v[0] for y,v in sorted(acc['years'].items())}; ywr={y:round(v[1]/v[0]*100,2) for y,v in sorted(acc['years'].items()) if v[0]}
    return {'n':n,'wr':round(acc['wins']/n*100,4),'avg':round(acc['pnl_sum']/n,4),'median':round(med,4),'loss':acc['loss'],'micro':round(acc['micro']/n*100,4),'min_year_n':min(yc.values()) if yc else 0,'year_counts':yc,'year_wr':ywr,'all_year_wr_min':round(min(ywr.values()) if ywr else 0,2),'symbols':len(acc['symbols']),'per_stock_3y':round(n/max(len(acc['symbols']),1),4),'t1':acc['t1']}

def scan_one(path):
    s=sym(path)
    try: bars=json.loads(path.read_text())
    except Exception: return {'symbol':s,'ok':False}, []
    n=len(bars)
    if n<90: return {'symbol':s,'ok':False,'bars':n}, []
    ssl=[]; bos={lb:[] for lb in BOS_LBS}; bull=0; bear=0
    for i in range(40,n-2):
        if ds(bars[i])[:4] not in YEARS: continue
        o=f(bars[i].get('o')); c=f(bars[i].get('c')); h=f(bars[i].get('h')); l=f(bars[i].get('l'))
        if any(math.isnan(x) for x in (o,c,h,l)) or h<=l: continue
        bull+=int(c>o); bear+=int(c<o)
        prev20=bars[i-20:i]; pl=min(f(x.get('l')) for x in prev20)
        if l<pl and c>pl: ssl.append(i)
        if c>o:
            for lb in BOS_LBS:
                if c>max(f(x.get('h')) for x in bars[i-lb:i]): bos[lb].append(i)
    return {'symbol':s,'ok':True,'bars':n,'ssl_n':len(ssl),'bullish_n':bull,'bearish_n':bear, **{f'bos{lb}_n':len(v) for lb,v in bos.items()}}, (bars,ssl,bos)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    paths=sorted(KDIR.glob('*_daily_750.json'))
    primitive=[]; spec_acc=defaultdict(blank); timeline_acc=defaultdict(blank); raw_unique=blank(); seen_raw=set()
    attr=defaultdict(int)
    for pi,p in enumerate(paths,1):
        st,data=scan_one(p); primitive.append(st)
        if not st.get('ok'):
            continue
        bars,ssl,bos=data; s=st['symbol']; ssl_sorted=ssl; ssl_set=set(ssl)
        seen_local=set()
        for lb,events in bos.items():
            attr[(lb,'bos_events')]+=len(events)
            for ei in events:
                # nearest demand within max lookback
                di=None
                for k in range(ei-1,max(ei-max(DEMAND_LBS)-1,-1),-1):
                    if f(bars[k].get('c')) < f(bars[k].get('o')): di=k; break
                if di is None: continue
                dist=ei-di; zl=f(bars[di].get('l')); zh=max(f(bars[di].get('o')),f(bars[di].get('c')))
                if math.isnan(zl) or math.isnan(zh) or zl<=0 or zh<=zl: continue
                attr[(lb,'with_demand20')]+=1
                ssl_age=None; last_ssl=None
                for j in ssl_sorted:
                    if j<ei: last_ssl=j
                    else: break
                if last_ssl is not None: ssl_age=ei-last_ssl
                first={}
                for mode in MODES:
                    for ri in range(ei+1,min(ei+max(WAITS),len(bars)-2)+1):
                        if mode_ok(mode,bars[ri],zl,zh): first[mode]=ri; break
                if not first: continue
                attr[(lb,'with_any_retest20')]+=1
                for mode,ri in first.items():
                    delay=ri-ei; entry_i=ri+1
                    if entry_i>=len(bars): continue
                    entry=f(bars[entry_i].get('o')); sl=zl*0.99; risk=(entry/sl-1)*100; chase=(entry/zh-1)*100
                    if not (0.8<=risk<=12): continue
                    ex=replay(bars,entry_i,entry,sl)
                    if ex is None or ex['year'] not in YEARS: continue
                    # raw unique opportunity count across any parameterization
                    rawk=(s,entry_i)
                    if rawk not in seen_raw:
                        seen_raw.add(rawk); add(raw_unique,ex['pnl'],ex['year'],s,ex['t1'])
                    for dlb in DEMAND_LBS:
                        if dist>dlb: continue
                        for win in SSL_WINS:
                            if win and (ssl_age is None or ssl_age>win): continue
                            rel='NO_SSL_REQ' if win==0 else ('SSL_BEFORE_DEMAND' if last_ssl<di else ('SSL_ON_DEMAND' if last_ssl==di else 'SSL_AFTER_DEMAND_BEFORE_BOS'))
                            for wait in WAITS:
                                if delay>wait: continue
                                key=(lb,dlb,win,mode,wait)
                                dk=(key,s,entry_i)
                                if dk in seen_local: continue
                                seen_local.add(dk)
                                add(spec_acc[key],ex['pnl'],ex['year'],s,ex['t1'])
                                for tkey in [('relation',rel),('mode',mode),('relation_mode',rel,mode),('ssl_win_mode',win,mode),('delay_mode',delay,mode),('relation_delay',rel,delay)]:
                                    add(timeline_acc[tkey],ex['pnl'],ex['year'],s,ex['t1'])
        if pi%500==0: print(f'scanned {pi}/{len(paths)} specs={len(spec_acc)} raw_unique={raw_unique["n"]}',flush=True)
    # serialize primitive stats
    import csv
    prim_path=OUT/'v277_per_stock_primitive_counts.csv'
    keys=sorted({k for r in primitive for k in r.keys()})
    with prim_path.open('w',newline='') as fcsv:
        w=csv.DictWriter(fcsv,fieldnames=keys); w.writeheader(); w.writerows(primitive)
    surface=[]
    for key,acc in spec_acc.items():
        m=met(acc)
        if m['n']>=100:
            lb,dlb,win,mode,wait=key; surface.append({'bos_lb':lb,'demand_lb':dlb,'ssl_win':win,'mode':mode,'wait':wait,**m})
    surface=sorted(surface,key=lambda r:(r['wr'],r['avg'],r['n']),reverse=True)
    pd.DataFrame(surface).to_csv(OUT/'v277_parameter_surface.csv',index=False)
    timeline=[]
    for key,acc in timeline_acc.items():
        m=met(acc)
        if m['n']>=100:
            timeline.append({'surface':str(key[0]),'key':'|'.join(map(str,key[1:])),**m})
    timeline=sorted(timeline,key=lambda r:(r['wr'],r['avg'],r['n']),reverse=True)
    pd.DataFrame(timeline).to_csv(OUT/'v277_timeline_surfaces.csv',index=False)
    # primitive summary from primitive list without pandas heavy needs
    ok=[r for r in primitive if r.get('ok')]
    def desc(col):
        vals=sorted(float(r.get(col,0) or 0) for r in ok); n=len(vals)
        if not n: return {}
        def q(p): return vals[min(n-1,int((n-1)*p))]
        return {'count':n,'mean':round(sum(vals)/n,4),'min':vals[0],'25%':q(.25),'50%':q(.5),'75%':q(.75),'90%':q(.9),'95%':q(.95),'max':vals[-1]}
    primitive_summary={'stocks':len(ok),'ssl_total':int(sum(r.get('ssl_n',0) or 0 for r in ok)),'ssl_per_stock':desc('ssl_n')}
    for lb in BOS_LBS:
        primitive_summary[f'bos{lb}_total']=int(sum(r.get(f'bos{lb}_n',0) or 0 for r in ok)); primitive_summary[f'bos{lb}_per_stock']=desc(f'bos{lb}_n')
    attrition={f'bos{lb}':{'bos_events':attr[(lb,'bos_events')],'with_demand20':attr[(lb,'with_demand20')],'with_any_retest20':attr[(lb,'with_any_retest20')],'demand20_pct':round(attr[(lb,'with_demand20')]/max(attr[(lb,'bos_events')],1)*100,4),'retest20_pct_of_bos':round(attr[(lb,'with_any_retest20')]/max(attr[(lb,'bos_events')],1)*100,4)} for lb in BOS_LBS}
    largest=sorted(surface,key=lambda r:(r['n'],r['wr'],r['avg']),reverse=True)[:30]
    summary={'version':'V277_SEQUENCE_SUPPLY_CHAIN_ATTRITION_FAST_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'out_dir':str(OUT),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'inputs':{'kline_files':len(paths),'years':sorted(YEARS)},'primitive_summary':primitive_summary,'sequence_attrition':attrition,'raw_unique_opportunities_any_spec':met(raw_unique),'surface_count':len(surface),'top_quality_surfaces':surface[:30],'largest_surfaces':largest,'top_timeline_surfaces':timeline[:30],'artifacts':{'per_stock_primitive_counts':str(prim_path),'parameter_surface':str(OUT/'v277_parameter_surface.csv'),'timeline_surfaces':str(OUT/'v277_timeline_surfaces.csv')},'decision':'NO_PRODUCTION_WRITE__TIME_ORDER_COMBO_ATTRITION_DIAGNOSIS_ONLY'}
    (OUT/'v277_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)); LATEST.write_text(json.dumps(summary,ensure_ascii=False,indent=2)); print(json.dumps(summary,ensure_ascii=False,indent=2)[:14000])
if __name__=='__main__': main()
