#!/usr/bin/env python3
"""V278 no-write ultra-fast chronological SMC combo/parameter attrition audit.

Full-market 2023-2026. In-stream aggregates only; no production/frontend writes.
"""
from __future__ import annotations
import json, math, csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd
BASE=Path('/root/.hermes'); KDIR=BASE/'kline_cache'; TS=datetime.now().strftime('%Y%m%d_%H%M%S')
OUT=BASE/f'smc_audit/v278_sequence_combo_attrition_ultrafast_no_write_{TS}'; LATEST=BASE/'smc_audit/v278_sequence_combo_attrition_ultrafast_latest.json'
YEARS={'2023','2024','2025','2026'}; BOS_LBS=[10,20,40]; DEMAND_LBS=[3,5,8,12,20]; SSL_WINS=[0,10,20,40,80]; WAITS=[3,5,8,12,20]; MODES=['strict','soft_mid','touch_bull','support_hold']
def f(x:Any,d=math.nan):
    try:
        if x is None or x=='': return d
        v=float(x); return v if not math.isnan(v) else d
    except Exception: return d
def ds(b): return str(b.get('t',b.get('date',''))).replace('.0','')[:8]
def sym(p:Path):
    s=p.stem.replace('_daily_750',''); c,e=s.split('_',1); return f'{c}.{e}'
def okmode(m,b,zl,zh):
    o=f(b.get('o')); c=f(b.get('c')); h=f(b.get('h')); l=f(b.get('l'))
    if any(math.isnan(x) for x in (o,c,h,l)) or h<=l or l>zh*1.005: return False
    r=h-l
    return (m=='strict' and c>=zh and c>o and (c-l)/r>=0.55) or (m=='soft_mid' and c>=(zl+zh)/2 and (c-l)/r>=0.45) or (m=='touch_bull' and c>o and c>=zl) or (m=='support_hold' and c>=zl)
def replay(bars,ei,entry,sl):
    if ei+1>=len(bars): return None
    tp=entry+(entry-sl)*1.5; last=min(len(bars)-1,ei+10); xp=f(bars[last].get('c')); xi=last; reason='TIME10'
    for i in range(ei+1,last+1):
        lo=f(bars[i].get('l')); hi=f(bars[i].get('h'))
        if lo<=sl: xp=sl; xi=i; reason='SL'; break
        if hi>=tp: xp=tp; xi=i; reason='TP'; break
    return (xp/entry-1)*100, ds(bars[ei])[:4], reason, ds(bars[xi])==ds(bars[ei])
def blank(): return {'n':0,'wins':0,'sum':0.0,'micro':0,'loss':0,'t1':0,'years':defaultdict(lambda:[0,0]),'tp':0,'sl':0,'time':0}
def add(a,pnl,year,t1,reason):
    a['n']+=1; a['wins']+=pnl>0; a['sum']+=pnl; a['micro']+=0<pnl<1; a['loss']+=pnl<=0; a['t1']+=bool(t1); a['years'][year][0]+=1; a['years'][year][1]+=pnl>0; a['tp']+=reason=='TP'; a['sl']+=reason=='SL'; a['time']+=reason.startswith('TIME')
def met(a,stock_count=4655):
    n=a['n']
    if not n: return {'n':0}
    yc={y:int(v[0]) for y,v in sorted(a['years'].items())}; ywr={y:round(v[1]/v[0]*100,2) for y,v in sorted(a['years'].items()) if v[0]}
    return {'n':int(n),'wr':round(a['wins']/n*100,4),'avg':round(a['sum']/n,4),'loss':int(a['loss']),'micro':round(a['micro']/n*100,4),'min_year_n':min(yc.values()) if yc else 0,'year_counts':yc,'year_wr':ywr,'all_year_wr_min':round(min(ywr.values()) if ywr else 0,2),'per_stock_3y_all_stocks':round(n/stock_count,4),'tp_pct':round(a['tp']/n*100,2),'sl_pct':round(a['sl']/n*100,2),'time_pct':round(a['time']/n*100,2),'t1':int(a['t1'])}
def scan(path):
    s=sym(path)
    try: bars=json.loads(path.read_text())
    except Exception: return {'symbol':s,'ok':False},None
    n=len(bars)
    if n<90: return {'symbol':s,'ok':False,'bars':n},None
    ssl=[]; bos={lb:[] for lb in BOS_LBS}; bull=bear=0
    highs=[f(b.get('h')) for b in bars]; lows=[f(b.get('l')) for b in bars]; opens=[f(b.get('o')) for b in bars]; closes=[f(b.get('c')) for b in bars]; dates=[ds(b) for b in bars]
    for i in range(40,n-2):
        if dates[i][:4] not in YEARS: continue
        o=opens[i]; c=closes[i]; h=highs[i]; l=lows[i]
        if any(math.isnan(x) for x in (o,c,h,l)) or h<=l: continue
        bull+=c>o; bear+=c<o
        pl=min(lows[i-20:i])
        if l<pl and c>pl: ssl.append(i)
        if c>o:
            for lb in BOS_LBS:
                if c>max(highs[i-lb:i]): bos[lb].append(i)
    return {'symbol':s,'ok':True,'bars':n,'ssl_n':len(ssl),'bullish_n':int(bull),'bearish_n':int(bear),**{f'bos{lb}_n':len(v) for lb,v in bos.items()}},(bars,ssl,bos,dates,opens,closes)
def main():
    OUT.mkdir(parents=True,exist_ok=True); paths=sorted(KDIR.glob('*_daily_750.json')); stock_count=len(paths)
    prim=[]; spec=defaultdict(blank); timeline=defaultdict(blank); raw=blank(); attr=defaultdict(int); seen_raw_global=set()
    for pi,p in enumerate(paths,1):
        st,data=scan(p); prim.append(st)
        if not st.get('ok'): continue
        bars,ssl,bos,dates,opens,closes=data; s=st['symbol']; seen_spec=set(); seen_tl=set()
        for lb,events in bos.items():
            attr[(lb,'bos')]+=len(events)
            for ei in events:
                # last SSL before event
                last_ssl=None
                for j in ssl:
                    if j<ei: last_ssl=j
                    else: break
                ssl_age=None if last_ssl is None else ei-last_ssl
                # last bearish demand within 20
                di=None
                for k in range(ei-1,max(ei-21,-1),-1):
                    if closes[k]<opens[k]: di=k; break
                if di is None: continue
                dist=ei-di; zl=f(bars[di].get('l')); zh=max(opens[di],closes[di])
                if math.isnan(zl) or math.isnan(zh) or zl<=0 or zh<=zl: continue
                attr[(lb,'demand20')]+=1
                first={}
                for m in MODES:
                    for ri in range(ei+1,min(ei+max(WAITS),len(bars)-2)+1):
                        if okmode(m,bars[ri],zl,zh): first[m]=ri; break
                if not first: continue
                attr[(lb,'retest20')]+=1
                for m,ri in first.items():
                    delay=ri-ei; entry_i=ri+1
                    if entry_i>=len(bars): continue
                    entry=f(bars[entry_i].get('o')); sl=zl*0.99; risk=(entry/sl-1)*100
                    if not (0.8<=risk<=12): continue
                    rep=replay(bars,entry_i,entry,sl)
                    if rep is None: continue
                    pnl,year,reason,t1=rep
                    if year not in YEARS: continue
                    rk=(s,entry_i)
                    if rk not in seen_raw_global: seen_raw_global.add(rk); add(raw,pnl,year,t1,reason)
                    for dlb in DEMAND_LBS:
                        if dist>dlb: continue
                        for win in SSL_WINS:
                            if win and (ssl_age is None or ssl_age>win): continue
                            rel='NO_SSL_REQ' if win==0 else ('SSL_BEFORE_DEMAND' if last_ssl<di else ('SSL_ON_DEMAND' if last_ssl==di else 'SSL_AFTER_DEMAND_BEFORE_BOS'))
                            for wait in WAITS:
                                if delay>wait: continue
                                key=(lb,dlb,win,m,wait); sk=(key,entry_i)
                                if sk in seen_spec: continue
                                seen_spec.add(sk); add(spec[key],pnl,year,t1,reason)
                                for tk in [('rel',rel),('mode',m),('rel_mode',rel,m),('delay_mode',delay,m),('sslwin_mode',win,m)]:
                                    tlk=(tk,entry_i)
                                    if tlk not in seen_tl: seen_tl.add(tlk); add(timeline[tk],pnl,year,t1,reason)
        if pi%500==0: print(f'scanned {pi}/{stock_count} raw={raw["n"]}',flush=True)
    keys=sorted({k for r in prim for k in r.keys()}); prim_path=OUT/'v278_per_stock_primitive_counts.csv'
    with prim_path.open('w',newline='') as fh: w=csv.DictWriter(fh,fieldnames=keys); w.writeheader(); w.writerows(prim)
    ok=[r for r in prim if r.get('ok')]
    def desc(col):
        vals=sorted(float(r.get(col,0) or 0) for r in ok); n=len(vals)
        def q(p): return vals[min(n-1,int((n-1)*p))]
        return {'count':n,'mean':round(sum(vals)/max(n,1),4),'min':vals[0] if n else 0,'25%':q(.25) if n else 0,'50%':q(.5) if n else 0,'75%':q(.75) if n else 0,'90%':q(.9) if n else 0,'95%':q(.95) if n else 0,'max':vals[-1] if n else 0}
    primitive={'stocks':len(ok),'ssl_total':int(sum(r.get('ssl_n',0) or 0 for r in ok)),'ssl_per_stock':desc('ssl_n')}
    for lb in BOS_LBS: primitive[f'bos{lb}_total']=int(sum(r.get(f'bos{lb}_n',0) or 0 for r in ok)); primitive[f'bos{lb}_per_stock']=desc(f'bos{lb}_n')
    rows=[]
    for key,a in spec.items():
        m=met(a,stock_count)
        if m['n']>=100:
            lb,dlb,win,mode,wait=key; rows.append({'bos_lb':lb,'demand_lb':dlb,'ssl_win':win,'mode':mode,'wait':wait,**m})
    rows=sorted(rows,key=lambda r:(r['wr'],r['avg'],r['n']),reverse=True); pd.DataFrame(rows).to_csv(OUT/'v278_parameter_surface.csv',index=False)
    tl=[]
    for key,a in timeline.items():
        m=met(a,stock_count)
        if m['n']>=100: tl.append({'surface':str(key[0]),'key':'|'.join(map(str,key[1:])),**m})
    tl=sorted(tl,key=lambda r:(r['wr'],r['avg'],r['n']),reverse=True); pd.DataFrame(tl).to_csv(OUT/'v278_timeline_surface.csv',index=False)
    attrition={f'bos{lb}':{'bos':attr[(lb,'bos')],'demand20':attr[(lb,'demand20')],'retest20':attr[(lb,'retest20')],'demand20_pct':round(attr[(lb,'demand20')]/max(attr[(lb,'bos')],1)*100,4),'retest20_pct':round(attr[(lb,'retest20')]/max(attr[(lb,'bos')],1)*100,4)} for lb in BOS_LBS}
    summary={'version':'V278_SEQUENCE_COMBO_ATTRITION_ULTRAFAST_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'out_dir':str(OUT),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'inputs':{'kline_files':stock_count,'years':sorted(YEARS),'specs':len(spec)},'primitive_summary':primitive,'sequence_attrition':attrition,'raw_unique_opportunities_any_spec':met(raw,stock_count),'top_quality_surfaces':rows[:30],'largest_surfaces':sorted(rows,key=lambda r:(r['n'],r['wr'],r['avg']),reverse=True)[:30],'top_timeline_surfaces':tl[:30],'artifacts':{'per_stock_primitive_counts':str(prim_path),'parameter_surface':str(OUT/'v278_parameter_surface.csv'),'timeline_surface':str(OUT/'v278_timeline_surface.csv')},'decision':'NO_PRODUCTION_WRITE__COMBO_TIME_ORDER_ATTRITION_DIAGNOSIS_ONLY'}
    (OUT/'v278_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)); LATEST.write_text(json.dumps(summary,ensure_ascii=False,indent=2)); print(json.dumps(summary,ensure_ascii=False,indent=2)[:14000])
if __name__=='__main__': main()
