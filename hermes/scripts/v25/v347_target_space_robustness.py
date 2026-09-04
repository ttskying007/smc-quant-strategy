#!/usr/bin/env python3
"""V347 no-write: test whether pre-entry target-space/context gates rescue V343.

Uses only pre-entry fields (BSL room, range position, reclaim body, breadth, POI)
and dynamic prior-BSL exits. Adds quarter and PnL-concentration robustness gates.
No production/frontend/watchlist writes.
"""
from __future__ import annotations
import itertools, json, math
from datetime import datetime
from pathlib import Path
import pandas as pd

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; KDIR=ROOT/'kline_cache'
FEAT=Path('/root/.hermes/smc_audit/v342_fast_bsl_room_signal_layer_no_write_20260709_231700/v342_bsl_features.csv')
OUT=AUD/f"v347_target_space_robustness_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
LATEST=AUD/'v347_target_space_robustness_latest.json'
GATE={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'min_year_wr':91.0,'micro':1.0,'top5_pnl_share':35.0,'weak_quarters':0,'t1':0}

def dn(x):
 s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def sf(x,d=None):
 try:
  v=float(x); return d if math.isnan(v) or math.isinf(v) else v
 except Exception: return d
def load_json(p,d):
 try:return json.loads(Path(p).read_text())
 except Exception:return d
def bars(sym):
 out=[]
 for b in load_json(KDIR/f"{sym.replace('.','_')}_daily_750.json",[]):
  d=dn(b.get('t') or b.get('date')); o,h,l,c=sf(b.get('o')),sf(b.get('h')),sf(b.get('l')),sf(b.get('c'))
  if d and None not in (o,h,l,c):out.append((d,o,h,l,c))
 return sorted(out)
def replay(x,target,fac,hold):
 ep=x['ep']; sl=x['zl']*.99
 if sl>=ep:sl=ep*.985
 tp1=ep*1.04; room=max(4.1,x[target]*fac); tp2=ep*(1+room/100); got=False
 for k,(_,_,h,l,c) in enumerate(x['path'][:hold],1):
  if not got:
   if l<=sl:return (sl/ep-1)*100,'SL'
   if h>=tp1:
    got=True
    if l<=ep:return 1.2,'SAME'
   elif k>=hold:return (c/ep-1)*100,'TIME0'
   continue
  if l<=ep:return 1.2,'BE'
  if h>=tp2:return 1.2+room*.7,'BSL_TARGET'
  if k>=hold:return 1.2+(c/ep-1)*70,'TIME'
 return None,'OPEN'
def metrics(data):
 if not data:return None
 p=[x[0] for x in data]; ys={}; qs={}; ex={}
 for v,y,q,r in data:
  ys.setdefault(y,[]).append(v); qs.setdefault(q,[]).append(v); ex[r]=ex.get(r,0)+1
 yc={y:len(a) for y,a in ys.items() if y>='2023'}; ywr={y:sum(v>0 for v in a)/len(a)*100 for y,a in ys.items() if y>='2023'}
 weak=[]
 for q,a in qs.items():
  if len(a)>=10:
   wr=sum(v>0 for v in a)/len(a)*100; avg=sum(a)/len(a)
   if wr<91 or avg<3:weak.append({'quarter':q,'n':len(a),'wr':round(wr,2),'avg':round(avg,4)})
 sp=sorted(p); q95=sp[int(.95*(len(sp)-1))]; total=sum(p); top5=sum(v for v in p if v>=q95)/total*100 if total>0 else 999
 return {'n':len(p),'wr':sum(v>0 for v in p)/len(p)*100,'avg':sum(p)/len(p),'micro':sum(0<v<1 for v in p)/len(p)*100,'min_year_n':min(yc.values()) if yc else 0,'min_year_wr':min(ywr.values()) if ywr else 0,'weak_quarter_count':len(weak),'weak_quarters':weak,'top5_pnl_share':top5,'target_hit_rate':ex.get('BSL_TARGET',0)/len(p)*100,'exit_counts':ex}
def passed(m):
 return m['n']>=570 and m['min_year_n']>=70 and m['wr']>=93 and m['avg']>=7.6 and m['min_year_wr']>=91 and m['micro']<=1 and m['top5_pnl_share']<=35 and m['weak_quarter_count']==0

def main():
 OUT.mkdir(parents=True,exist_ok=True); f=pd.read_csv(FEAT); cache={}; paths={}
 for r in f.itertuples():
  sym=str(r.symbol); ed=dn(r.entry_date)
  if sym not in cache:cache[sym]=bars(sym)
  paths[int(r.ix)]={'path':[x for x in cache[sym] if x[0]>ed][:50],'year':str(r.year),'quarter':pd.Period(pd.to_datetime(ed,format='%Y%m%d'),freq='Q').strftime('%YQ%q'),'actual':sf(r.actual),'ep':sf(r.ep),'zl':sf(r.zl),'bsl20':sf(r.bsl20,0),'bsl60':sf(r.bsl60,0)}
 families=[]
 for src,room,pos,body,br in itertools.product(['ALL','OB','FVG'],[10,20,30],[40,50,65],[0,45,55],[0,30,45]):
  m=pd.Series(True,index=f.index)
  if src=='OB':m&=f.poi_source.isin(['DEMAND_OB','OB+FVG'])
  if src=='FVG':m&=f.poi_source.eq('FVG_Demand')
  m&=f.bsl60.ge(room)&f.pos60.le(pos)&f.body.ge(body)&f.br.ge(br)
  if int(m.sum())>=100:families.append((f'{src}_r{room}_p{pos}_body{body}_br{br}',m))
 results=[]
 for name,mask in families:
  ids=[int(v) for v in f.loc[mask,'ix']]
  for target,fac,hold in itertools.product(['bsl20','bsl60'],[.7,.9,1.0],[20,30,50]):
   data=[]
   for i in ids:
    x=paths[i]
    if x['actual'] is None or x['actual']<hold:continue
    v,reason=replay(x,target,fac,hold)
    if v is not None:data.append((v,x['year'],x['quarter'],reason))
   m=metrics(data)
   if not m:continue
   rec={'family':name,'target':target,'target_factor':fac,'max_hold':hold,'pass_all':passed(m),**{k:(round(v,4) if isinstance(v,float) else v) for k,v in m.items()}}
   rec['score']=sum([m['n']>=570,m['min_year_n']>=70,m['wr']>=93,m['avg']>=7.6,m['min_year_wr']>=91,m['micro']<=1,m['top5_pnl_share']<=35,m['weak_quarter_count']==0])
   results.append(rec)
 results.sort(key=lambda r:(r['pass_all'],r['score'],r['avg'],r['wr'],r['n']),reverse=True); passing=[r for r in results if r['pass_all']]
 flat=[]
 for r in results[:500]:flat.append({k:v for k,v in r.items() if k not in {'weak_quarters','exit_counts'}})
 pd.DataFrame(flat).to_csv(OUT/'v347_target_space_frontier_top500.csv',index=False)
 report={'version':'V347_TARGET_SPACE_ROBUSTNESS_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source_features':str(FEAT),'gate':GATE,'families_evaluated':len(families),'rules_evaluated':len(results),'passing_rule_count':len(passing),'top_passing':passing[:20],'top_rules':results[:20],'decision':'V347_TARGET_SPACE_PASS__SHADOW_ONLY' if passing else 'V347_TARGET_SPACE_FAIL__PRE_ENTRY_ROOM_CONTEXT_EXHAUSTED','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'frontier':str(OUT/'v347_target_space_frontier_top500.csv')}}
 (OUT/'v347_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps({'decision':report['decision'],'families':len(families),'rules':len(results),'passing':len(passing),'top_rules':results[:5],'artifacts':report['artifacts']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
