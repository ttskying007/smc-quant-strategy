#!/usr/bin/env python3
"""V343 no-write: dynamic BSL target exits.

After V342 showed BSL-room filters improve quality but fixed TP2 still misses the
production avg target, V343 changes direction: runner TP2 is the pre-entry
liquidity target itself (prior BSL room), not a fixed percent. No writes.
"""
from __future__ import annotations
import itertools,json,math,glob
from datetime import datetime
from pathlib import Path
import pandas as pd
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; KDIR=ROOT/'kline_cache'
FEAT='/root/.hermes/smc_audit/v342_fast_bsl_room_signal_layer_no_write_20260709_231700/v342_bsl_features.csv'
OUT=AUD/f"v343_dynamic_bsl_target_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v343_dynamic_bsl_target_latest.json'
GATE={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'min_year_wr':91.0,'micro':1.0,'t1':0,'current_open':1}
def dn(x):
 s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def sf(x,d=None):
 try:
  if x is None or x=='': return d
  v=float(x); return d if math.isnan(v) or math.isinf(v) else v
  return v
 except Exception: return d
def load_json(p,default):
 try: return json.loads(Path(p).read_text())
 except Exception: return default
def bars(sym):
 arr=[]; p=KDIR/f"{sym.replace('.','_')}_daily_750.json"
 for b in load_json(p,[]):
  d=dn(b.get('t') or b.get('date')); o,h,l,c=sf(b.get('o')),sf(b.get('h')),sf(b.get('l')),sf(b.get('c'))
  if d and None not in (o,h,l,c): arr.append((d,float(o),float(h),float(l),float(c)))
 return sorted(arr)
def metrics(vals,yrs,reasons):
 s=pd.Series(vals); y=pd.Series(yrs); rr=pd.Series(reasons); ok=s.notna(); s=s[ok].astype(float); y=y[ok]; rr=rr[ok]
 if len(s)==0: return {'n':0,'wr':0,'avg':0,'min_year_n':0,'year_counts':{},'year_wr':{},'min_year_wr':0,'micro':0,'t1':0,'exit_counts':{}}
 yc={str(k):int(v) for k,v in y[y>='2023'].value_counts().sort_index().to_dict().items()}; ywr={str(k):round(float((s[y==k]>0).mean()*100),2) for k in sorted(yc)}
 return {'n':int(len(s)),'wr':round(float((s>0).mean()*100),4),'avg':round(float(s.mean()),4),'min_year_n':int(min(yc.values()) if yc else 0),'year_counts':yc,'year_wr':ywr,'min_year_wr':round(float(min(ywr.values()) if ywr else 0),2),'micro':round(float(((s>0)&(s<1)).mean()*100),4),'t1':0,'exit_counts':{str(k):int(v) for k,v in rr.value_counts().to_dict().items()}}
def gate(m): return m['n']>=GATE['n'] and m['min_year_n']>=GATE['min_year_n'] and m['wr']>=GATE['wr'] and m['avg']>=GATE['avg'] and m['min_year_wr']>=GATE['min_year_wr'] and m['micro']<=GATE['micro']
def main():
 OUT.mkdir(parents=True,exist_ok=True); f=pd.read_csv(FEAT); cache={}; paths={}
 for r in f.itertuples():
  sym=str(r.symbol); ed=dn(r.entry_date); ep=sf(r.ep); zl=sf(r.zl)
  if sym not in cache: cache[sym]=bars(sym)
  fut=[x for x in cache[sym] if x[0]>ed][:40]
  paths[int(r.ix)]={'path':fut,'year':str(r.year),'actual':sf(r.actual),'cur':bool(r.cur),'ep':ep,'zl':zl,'bsl20':sf(r.bsl20),'bsl60':sf(r.bsl60)}
 families={}
 for src in ['ALL','OB','FVG']:
  sm=pd.Series(True,index=f.index)
  if src=='OB': sm=f.poi_source.isin(['DEMAND_OB','OB+FVG'])
  if src=='FVG': sm=f.poi_source.eq('FVG_Demand')
  for room in [0,5,10,15,20,25,30]:
   for pos in [None,50,65]:
    m=sm&f.bsl60.ge(room); name=f'{src}_bsl60>={room}'
    if pos is not None: m&=f.pos60.le(pos); name+=f'_pos60<={pos}'
    if int(m.sum())>=100: families[name]=m
 contracts=list(itertools.product([0,0.005],[4,5,6],[0.5,0.6,0.7],['bsl20','bsl60'],[0.8,0.9,1.0],[20,30]))
 def replay(i,slbuf,tp1,frac,target,fac,mh):
  x=paths[i]; ep=x['ep']; zl=x['zl']; path=x['path'][:mh]; sl=zl*(1-slbuf)
  if sl>=ep: sl=ep*.985
  t1=ep*(1+tp1/100); room=max(0.0,x[target] or 0.0)*fac; t2=ep*(1+room/100); got=False; pnl1=0.0; rsl=sl
  for k,(_,_,h,l,c) in enumerate(path,1):
   if not got:
    if l<=sl: return (sl/ep-1)*100,'SL_BEFORE_TP1'
    if h>=t1:
     got=True; pnl1=tp1*(1-frac); rsl=ep
     if l<=rsl: return pnl1,'TP1_BE_SAME_BAR'
    elif k>=mh: return (c/ep-1)*100,'TIME_NO_TP1'
    continue
   if l<=rsl: return pnl1,'RUNNER_BE'
   if h>=t2: return pnl1+room*frac,'BSL_TARGET'
   if k>=mh: return pnl1+(c/ep-1)*100*frac,'TIME_AFTER_TP1'
  return None,'OPEN'
 results=[]
 for fname,mask in families.items():
  idx=[int(f.loc[j,'ix']) for j in f.index[mask]]
  for sl,tp1,frac,target,fac,mh in contracts:
   hist=[i for i in idx if paths[i]['actual'] is not None and paths[i]['actual']>=mh]
   if len(hist)<100: continue
   vals=[]; yrs=[]; reasons=[]
   for i in hist:
    v,rs=replay(i,sl,tp1,frac,target,fac,mh); vals.append(v); yrs.append(paths[i]['year']); reasons.append(rs)
   hm=metrics(vals,yrs,reasons)
   cur=[i for i in idx if paths[i]['cur']]
   cvals=[]; cyrs=[]; creasons=[]; open_n=0
   for i in cur:
    v,rs=replay(i,sl,tp1,frac,target,fac,mh); open_n += 1 if v is None else 0; cvals.append(v); cyrs.append(paths[i]['year']); creasons.append(rs)
   cm=metrics(cvals,cyrs,creasons); pg=gate(hm) and open_n>=GATE['current_open']
   score=(hm['wr']-90)*.45+hm['avg']*.9+hm['min_year_wr']*.03+min(hm['n'],570)/570-hm['micro']*.5+open_n*.05
   results.append({'family':fname,'sl_buf':sl,'tp1':tp1,'runner_frac':frac,'target':target,'target_factor':fac,'max_hold':mh,'score':round(float(score),4),'hist':hm,'current_closed':cm,'current_rows':len(cur),'current_open_rows':open_n,'pass_gate':pg})
 results=sorted(results,key=lambda r:(r['pass_gate'],r['hist']['wr'],r['hist']['avg'],r['hist']['n']),reverse=True); passing=[r for r in results if r['pass_gate']]
 frontier=[]
 for need in [120,200,300,400,500,570,700,900,1200]:
  cand=[r for r in results if r['hist']['n']>=need]
  if cand: frontier.append({'min_n':need,'best':cand[0]})
 pd.DataFrame([{**{k:r[k] for k in ['family','sl_buf','tp1','runner_frac','target','target_factor','max_hold','score','current_rows','current_open_rows','pass_gate']},**{f'hist_{k}':v for k,v in r['hist'].items() if not isinstance(v,dict)},**{f'cur_{k}':v for k,v in r['current_closed'].items() if not isinstance(v,dict)}} for r in results[:1500]]).to_csv(OUT/'v343_dynamic_bsl_top1500.csv',index=False)
 report={'version':'V343_DYNAMIC_BSL_TARGET_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source_features':FEAT,'gate':GATE,'families_evaluated':len(families),'rules_evaluated':len(results),'passing_rule_count':len(passing),'top_passing':passing[:20],'coverage_frontier':frontier,'top_rules':results[:50],'decision':'V343_DYNAMIC_BSL_TARGET_RECOVERS_GATE__SHADOW_ONLY_NO_WRITE' if passing else 'V343_DYNAMIC_BSL_TARGET_FAILS__TRUE_SEQUENCE_REBUILD_REQUIRED','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'rule_table':str(OUT/'v343_dynamic_bsl_top1500.csv')}}
 (OUT/'v343_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':report['decision'],'passing_rule_count':len(passing),'frontier':frontier,'top_rules':results[:8]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
