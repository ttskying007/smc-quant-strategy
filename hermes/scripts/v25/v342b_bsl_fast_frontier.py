#!/usr/bin/env python3
"""V342b no-write: fast BSL-room signal-layer frontier.

Optimized continuation of V342 after timeout. Two-stage: materialize pre-entry
BSL/local-structure features for seed rows, rank feature families by MFE/close20
quality, then executable replay only top families. No production writes.
"""
from __future__ import annotations
import itertools, json, math
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; KDIR=ROOT/'kline_cache'; V333=AUD/'v333_full_universe_rule_search_after_breadth_refresh_latest.json'
OUT=AUD/f"v342b_bsl_fast_frontier_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v342_bsl_room_signal_layer_latest.json'
WEAK={'C27医药制造业','C32有色金属冶炼和压延加工业'}
GATE={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'min_year_wr':91.0,'micro':1.0,'t1':0,'current_open':1}

def dn(x:Any)->str:
 s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def sf(x:Any,d=None):
 try:
  if x is None or x=='': return d
  v=float(x); return d if math.isnan(v) or math.isinf(v) else v
  return v
 except Exception: return d
def boolish(x:Any)->bool: return str(x).strip().lower() in {'true','1','yes'}
def load_json(p:Path,d):
 try: return json.loads(p.read_text())
 except Exception: return d
def bars(sym:str):
 arr=[]; p=KDIR/f"{sym.replace('.','_')}_daily_750.json"
 for b in load_json(p,[]):
  d=dn(b.get('t') or b.get('date')); o,h,l,c=sf(b.get('o')),sf(b.get('h')),sf(b.get('l')),sf(b.get('c'))
  if d and None not in (o,h,l,c): arr.append((d,float(o),float(h),float(l),float(c)))
 return sorted(arr)
def metrics(vals,yrs,reasons):
 s=pd.Series(vals); y=pd.Series(yrs); ok=s.notna(); s=s[ok].astype(float); y=y[ok]; rs=pd.Series(reasons)[ok]
 if len(s)==0: return {'n':0,'wr':0,'avg':0,'min_year_n':0,'year_counts':{},'year_wr':{},'min_year_wr':0,'micro':0,'t1':0,'exit_counts':{}}
 yc={str(k):int(v) for k,v in y[y>='2023'].value_counts().sort_index().to_dict().items()}; ywr={str(k):round(float((s[y==k]>0).mean()*100),2) for k in sorted(yc)}
 return {'n':int(len(s)),'wr':round(float((s>0).mean()*100),4),'avg':round(float(s.mean()),4),'min_year_n':int(min(yc.values()) if yc else 0),'year_counts':yc,'year_wr':ywr,'min_year_wr':round(float(min(ywr.values()) if ywr else 0),2),'micro':round(float(((s>0)&(s<1)).mean()*100),4),'t1':0,'exit_counts':{str(k):int(v) for k,v in rs.value_counts().to_dict().items()}}
def gate(m): return m['n']>=GATE['n'] and m['min_year_n']>=GATE['min_year_n'] and m['wr']>=GATE['wr'] and m['avg']>=GATE['avg'] and m['min_year_wr']>=GATE['min_year_wr'] and m['micro']<=GATE['micro']

def replay(path,ep,zl,slbuf,tp1,frac,tp2,mh):
 sl=zl*(1-slbuf)
 if sl>=ep: sl=ep*.985
 t1=ep*(1+tp1/100); t2=ep*(1+tp2/100); got=False; pnl1=0.0; rsl=sl
 for i,(_,_,h,l,c) in enumerate(path[:mh],1):
  if not got:
   if l<=sl: return (sl/ep-1)*100,'SL_BEFORE_TP1'
   if h>=t1:
    got=True; pnl1=tp1*(1-frac); rsl=ep
    if l<=rsl: return pnl1,'TP1_BE_SAME_BAR'
   elif i>=mh: return (c/ep-1)*100,'TIME_NO_TP1'
   continue
  if l<=rsl: return pnl1,'RUNNER_BE'
  if h>=t2: return pnl1+tp2*frac,'TP2_ABS'
  if i>=mh: return pnl1+(c/ep-1)*100*frac,'TIME_AFTER_TP1'
 return None,'OPEN'

def main():
 OUT.mkdir(parents=True,exist_ok=True); rep=load_json(V333,{}); df=pd.read_csv(rep['artifacts']['replayed_csv'],low_memory=False); df['entry_date']=df.entry_date.map(dn)
 n=lambda c: pd.to_numeric(df.get(c,pd.Series(index=df.index)),errors='coerce'); ss=lambda c: df.get(c,pd.Series('',index=df.index)).astype(str)
 weak=ss('v244_industry').isin(WEAK); add=n('v244_ind_strong1_pct').ge(31.1688)|n('v236_br_above_ma20').ge(46.8561); base=ss('v164_rule_pass').map(boolish)&((~weak)|add)
 seed=base&n('v132_bull_count_3').ge(3)&(ss('poi_source').isin(['DEMAND_OB','OB+FVG'])|ss('poi_source').eq('FVG_Demand'))
 sdf=df[seed.fillna(False)].copy(); sdf['_orig_idx']=sdf.index
 cache={}; feats=[]; paths={}
 for _, r in sdf.iterrows():
  sym=str(r.get('symbol')); ed=dn(r.get('entry_date')); ep=sf(r.get('entry_price')); zl=sf(r.get('zone_low')); ix=int(r.get('_orig_idx'))
  if sym not in cache: cache[sym]=bars(sym)
  b=cache[sym]; bi=next((i for i,x in enumerate(b) if x[0]==ed),None); path=[x for x in b if x[0]>ed][:40]
  paths[ix]={'ep':ep,'zl':zl,'path':path,'year':ed[:4],'actual':sf(r.get('v333_actual_bars_since_entry'))}
  f={'idx':ix,'has_bars':False}
  if bi is not None and ep and bi>=65:
   pre=b[:bi]; h20=max(x[2] for x in pre[-20:]); h60=max(x[2] for x in pre[-60:]); l20=min(x[3] for x in pre[-20:]); l60=min(x[3] for x in pre[-60:])
   tr=[]
   for k,x in enumerate(pre[-20:]):
    prev=pre[bi-20+k-1][4] if bi-20+k-1>=0 else x[4]
    tr.append(max(x[2]-x[3],abs(x[2]-prev),abs(x[3]-prev)))
   atr=sum(tr)/len(tr) if tr else 0
   f={'idx':ix,'has_bars':True,'bsl20':(h20/ep-1)*100,'bsl60':(h60/ep-1)*100,'pos20':(ep-l20)/(h20-l20)*100 if h20>l20 else None,'pos60':(ep-l60)/(h60-l60)*100 if h60>l60 else None,'atr20':atr/ep*100,'pre10ret':(pre[-1][4]/pre[-10][4]-1)*100 if pre[-10][4] else None,'ssl60':(ep/l60-1)*100 if l60 else None}
  feats.append(f)
 fdf=pd.DataFrame(feats).set_index('idx'); sdf=sdf.join(fdf,on='_orig_idx')
 # MFE shortlist, pre-entry predicates only.
 cand=[]; base_masks={
  'ALL':pd.Series(True,index=sdf.index),
  'OB':sdf.poi_source.astype(str).isin(['DEMAND_OB','OB+FVG']),
  'FVG':sdf.poi_source.astype(str).eq('FVG_Demand'),
 }
 nums={c:pd.to_numeric(sdf[c],errors='coerce') for c in ['bsl60','bsl20','pos60','pos20','atr20','pre10ret','ssl60','v85_zone_width_pct','risk_pct','v132_reclaim_bull_body_pct','v236_br_above_ma20'] if c in sdf.columns}
 for src,sm in base_masks.items():
  for room in [5,10,15,20,25,30]:
   m=sm&nums['bsl60'].ge(room); name=f'{src}_bsl60>={room}'; cand.append((name,m))
  for room,pos in itertools.product([10,15,20], [50,65,80]):
   m=sm&nums['bsl60'].ge(room)&nums['pos60'].le(pos); cand.append((f'{src}_bsl60>={room}_pos60<={pos}',m))
  for room,atr in itertools.product([10,15,20], [8,12,16]):
   m=sm&nums['bsl60'].ge(room)&nums['atr20'].le(atr); cand.append((f'{src}_bsl60>={room}_atr<={atr}',m))
  for room,zone in itertools.product([10,15,20], [1,1.5,2]):
   m=sm&nums['bsl60'].ge(room)&nums['v85_zone_width_pct'].ge(zone); cand.append((f'{src}_bsl60>={room}_zone>={zone}',m))
 # rank candidate families by executable-agnostic close20/MFE columns from existing replay if present
 fam=[]
 for name,m in cand:
  sub=sdf[m.fillna(False)]
  if len(sub)<120: continue
  yrs=sub.entry_date.astype(str).str[:4]; yc=yrs[yrs>='2023'].value_counts().to_dict(); minyn=min(yc.values()) if yc else 0
  pnl=pd.to_numeric(sub.get('pnl_pct'),errors='coerce')
  mfe_proxy=pd.to_numeric(sub.get('v333_actual_bars_since_entry'),errors='coerce')
  fam.append({'name':name,'n':int(len(sub)),'min_year_n':int(minyn),'pre_wr':round(float((pnl>0).mean()*100),4),'pre_avg':round(float(pnl.mean()),4)})
 fam=sorted(fam,key=lambda x:(x['pre_wr'],x['pre_avg'],x['n']),reverse=True)[:80]
 contracts=list(itertools.product([0,0.005,0.01],[4,5,6],[0.5,0.6,0.7],[20,30],[20,30]))
 results=[]
 for f in fam:
  name=f['name']; m=dict(cand)[name]; idx=[int(i) for i in sdf.loc[m.fillna(False),'_orig_idx'].tolist() if int(i) in paths]
  for sl,tp1,frac,tp2,mh in contracts:
   hist=[i for i in idx if paths[i]['actual'] is not None and paths[i]['actual']>=mh]
   if len(hist)<100: continue
   vals=[]; yrs=[]; reasons=[]
   for i in hist:
    x=paths[i]; v,rs=replay(x['path'],x['ep'],x['zl'],sl,tp1,frac,tp2,mh); vals.append(v); yrs.append(x['year']); reasons.append(rs)
   hm=metrics(vals,yrs,reasons)
   pg=gate(hm)
   score=(hm['wr']-90)*.45+hm['avg']*.9+hm['min_year_wr']*.03+min(hm['n'],570)/570-hm['micro']*.5
   results.append({'family':name,'sl_buf':sl,'tp1':tp1,'runner_frac':frac,'tp2':tp2,'max_hold':mh,'score':round(float(score),4),'hist':hm,'pass_gate':pg,'family_pre':f})
 results=sorted(results,key=lambda r:(r['pass_gate'],r['hist']['wr'],r['hist']['avg'],r['hist']['n']),reverse=True); passing=[r for r in results if r['pass_gate']]
 frontier=[]
 for need in [120,200,300,400,500,570,700,900]:
  cc=[r for r in results if r['hist']['n']>=need]
  if cc: frontier.append({'min_n':need,'best':cc[0]})
 pd.DataFrame([{**{k:r[k] for k in ['family','sl_buf','tp1','runner_frac','tp2','max_hold','score','pass_gate']},**{f'hist_{k}':v for k,v in r['hist'].items() if not isinstance(v,dict)}} for r in results[:2000]]).to_csv(OUT/'v342b_frontier_top2000.csv',index=False)
 report={'version':'V342B_BSL_FAST_FRONTIER_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source':rep['artifacts']['replayed_csv'],'gate':GATE,'seed_rows':int(len(sdf)),'family_shortlist':fam[:30],'rules_evaluated':len(results),'passing_rule_count':len(passing),'top_passing':passing[:20],'coverage_frontier':frontier,'top_rules':results[:50],'decision':'V342_BSL_ROOM_RECOVERS_PRODUCTION_GATE__SHADOW_ONLY_NO_WRITE' if passing else 'V342_BSL_ROOM_FAILS_PRODUCTION_GATE__NEED_SEQUENCE_REBUILD','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'rule_table':str(OUT/'v342b_frontier_top2000.csv')}}
 (OUT/'v342_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':report['decision'],'passing_rule_count':len(passing),'frontier':frontier,'top_rules':results[:8]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
