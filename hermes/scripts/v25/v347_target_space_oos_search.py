#!/usr/bin/env python3
"""V347 no-write: pre-entry structural target-space search with temporal OOS audit."""
from __future__ import annotations
import itertools, json, math
from datetime import datetime
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; KDIR=ROOT/'kline_cache'
FEATURES=AUD/'v342_fast_bsl_room_signal_layer_no_write_20260709_231700/v342_bsl_features.csv'
V333=AUD/'v333_full_universe_rule_search_after_breadth_refresh_latest.json'
OUT=AUD/f"v347_target_space_oos_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
LATEST=AUD/'v347_target_space_oos_latest.json'
GATE={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'min_year_wr':91.0,'micro':1.0,'top5_share':35.0,'weak_quarters':0}

def dn(x:Any)->str:
 s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def sf(x:Any,d=None):
 try:
  v=float(x); return d if math.isnan(v) or math.isinf(v) else v
 except Exception:return d
def load_json(p:Path,d):
 try:return json.loads(p.read_text())
 except Exception:return d
def json_text(value):
 return json.dumps(value,ensure_ascii=False,indent=2,default=lambda x:x.item() if hasattr(x,'item') else str(x))
def bars(sym:str):
 out=[]
 for b in load_json(KDIR/f"{sym.replace('.','_')}_daily_750.json",[]):
  d=dn(b.get('t') or b.get('date')); o,h,l,c=sf(b.get('o')),sf(b.get('h')),sf(b.get('l')),sf(b.get('c'))
  if d and None not in (o,h,l,c):out.append((d,o,h,l,c))
 return sorted(out)
def replay(ep,zl,path,target_pct,hold):
 sl=zl*.99
 if sl>=ep:sl=ep*.985
 t1=ep*1.04; t2=ep*(1+max(4.1,target_pct)/100); got=False; pnl1=0.0
 for i,(_,_,h,l,c) in enumerate(path[:hold],1):
  if not got:
   if l<=sl:return (sl/ep-1)*100,'SL'
   if h>=t1:
    got=True; pnl1=1.2
    if l<=ep:return pnl1,'SAME'
   elif i>=hold:return (c/ep-1)*100,'TIME0'
   continue
  if l<=ep:return pnl1,'BE'
  if h>=t2:return pnl1+max(4.1,target_pct)*.7,'STRUCT_TARGET'
  if i>=hold:return pnl1+(c/ep-1)*100*.7,'TIME'
 return np.nan,'OPEN'
def metrics(frame:pd.DataFrame)->dict:
 if frame.empty:return {'n':0,'wr':0,'avg':0,'micro':0,'min_year_n':0,'min_year_wr':0,'top5_share':999,'weak_quarter_count':99}
 p=frame.pnl.astype(float); ys=frame.groupby('year').pnl.agg(n='size',wr=lambda x:(x>0).mean()*100)
 qs=frame.groupby('quarter').pnl.agg(n='size',wr=lambda x:(x>0).mean()*100,avg='mean')
 weak=qs[(qs.n>=10)&((qs.wr<91)|(qs.avg<3))]
 q95=p.quantile(.95,interpolation='lower'); top5=p[p>=q95].sum()/p.sum()*100 if p.sum()>0 else 999
 return {'n':len(frame),'wr':(p>0).mean()*100,'avg':p.mean(),'micro':((p>0)&(p<1)).mean()*100,'min_year_n':int(ys.n.min()),'min_year_wr':ys.wr.min(),'top5_share':top5,'weak_quarter_count':len(weak),'weak_quarters':qs.reset_index().to_dict('records'),'target_hit_rate':frame.reason.eq('STRUCT_TARGET').mean()*100,'exit_counts':frame.reason.value_counts().to_dict()}
def hard_pass(m):
 return m['n']>=GATE['n'] and m['min_year_n']>=GATE['min_year_n'] and m['wr']>=GATE['wr'] and m['avg']>=GATE['avg'] and m['min_year_wr']>=GATE['min_year_wr'] and m['micro']<=GATE['micro'] and m['top5_share']<=GATE['top5_share'] and m['weak_quarter_count']==0

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 f=pd.read_csv(FEATURES,low_memory=False); src=pd.read_csv(load_json(V333,{})['artifacts']['replayed_csv'],usecols=['v333_any_history_overlap'],low_memory=False)
 f['overlap']=f['ix'].map(src.v333_any_history_overlap.astype(str).str.lower().isin(['true','1']).to_dict()).fillna(False)
 f['entry_date']=f.entry_date.astype(str).str[:8]; f['year']=f.entry_date.str[:4]; f['quarter']=pd.to_datetime(f.entry_date,format='%Y%m%d').dt.to_period('Q').astype(str)
 cache={}; paths={}
 for r in f.itertuples(index=False):
  if r.symbol not in cache:cache[r.symbol]=bars(r.symbol)
  paths[r.ix]=[x for x in cache[r.symbol] if x[0]>r.entry_date][:50]
 outcomes={}
 contracts=list(itertools.product([20,60],[.5,.7,.9,1.0],[20,30,50]))
 for tw,fac,hold in contracts:
  vals=[]; reasons=[]
  for r in f.itertuples(index=False):
   v,reason=replay(r.ep,r.zl,paths[r.ix],getattr(r,f'bsl{tw}')*fac,hold)
   vals.append(v); reasons.append(reason)
  outcomes[(tw,fac,hold)]=(np.array(vals,float),np.array(reasons,object))
 families=[]
 state_sets={'ALL':None,'NO_MIXED':{'BEAR_RISK','BULL_CONTINUATION','ACCUMULATION'},'BEAR_MIXED':{'BEAR_RISK','MIXED'},'BULL_ACC':{'BULL_CONTINUATION','ACCUMULATION'}}
 poi_sets={'ALL':None,'OB':{'DEMAND_OB','OB+FVG'},'FVG':{'FVG_Demand'}}
 for sname,states in state_sets.items():
  sm=np.ones(len(f),bool) if states is None else f.market_state.isin(states).to_numpy()
  for pname,pois in poi_sets.items():
   pm=np.ones(len(f),bool) if pois is None else f.poi_source.isin(pois).to_numpy()
   for room,pos,zmax,bmin,premax in itertools.product([5,10,15,20,25,30],[30,40,50,60],[3,5,8,99],[0,40,55],[0,5,99]):
    mask=sm&pm&(f.bsl60.to_numpy()>=room)&(f.pos60.to_numpy()<=pos)&(f.zone_width.to_numpy()<=zmax)&(f.body.to_numpy()>=bmin)&(f.pre10.to_numpy()<=premax)
    if mask.sum()>=570:families.append((f'{sname}_{pname}_room{room}_pos{pos}_z{zmax}_body{bmin}_pre{premax}',mask))
 results=[]
 for tw,fac,hold in contracts:
  vals,reasons=outcomes[(tw,fac,hold)]
  eligible=(f.actual.to_numpy()>=hold)&(~f.overlap.to_numpy())&np.isfinite(vals)
  for name,mask in families:
   use=eligible&mask
   if use.sum()<300:continue
   x=f.loc[use,['symbol','entry_date','year','quarter']].copy(); x['pnl']=vals[use]; x['reason']=reasons[use]
   train=metrics(x[x.year.isin(['2023','2024'])]); test=metrics(x[x.year.isin(['2025','2026'])]); full=metrics(x)
   discovery=train['n']>=140 and train['wr']>=91 and train['avg']>=3 and train['min_year_n']>=50
   score=sum([full['n']>=570,full['min_year_n']>=70,full['wr']>=93,full['avg']>=7.6,full['min_year_wr']>=91,full['micro']<=1,full['top5_share']<=35,full['weak_quarter_count']==0,test['wr']>=91,test['avg']>=3])
   results.append({'family':name,'target_window':tw,'target_factor':fac,'hold':hold,'discovery_pass':discovery,'full_pass':hard_pass(full),'score':score,'full':full,'train_2023_24':train,'oos_2025_26':test})
 results.sort(key=lambda r:(r['full_pass'],r['discovery_pass'],r['score'],r['oos_2025_26']['avg'],r['full']['avg']),reverse=True)
 passing=[r for r in results if r['full_pass'] and r['discovery_pass']]
 flat=[]
 for r in results[:500]:
  flat.append({'family':r['family'],'target_window':r['target_window'],'target_factor':r['target_factor'],'hold':r['hold'],'discovery_pass':r['discovery_pass'],'full_pass':r['full_pass'],'score':r['score'],**{f'full_{k}':v for k,v in r['full'].items() if not isinstance(v,(dict,list))},**{f'oos_{k}':v for k,v in r['oos_2025_26'].items() if not isinstance(v,(dict,list))}})
 pd.DataFrame(flat).to_csv(OUT/'v347_oos_frontier_top500.csv',index=False)
 report={'version':'V347_TARGET_SPACE_OOS_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'features':str(FEATURES),'contracts':len(contracts),'families':len(families),'rules_evaluated':len(results),'passing_rule_count':len(passing),'gate':GATE,'top_rules':results[:20],'decision':'V347_TARGET_SPACE_OOS_PASS__SHADOW_ONLY' if passing else 'V347_TARGET_SPACE_OOS_FAIL__SEQUENCE_REBUILD_REQUIRED','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'frontier':str(OUT/'v347_oos_frontier_top500.csv')}}
 (OUT/'v347_report.json').write_text(json_text(report),encoding='utf-8'); LATEST.write_text(json_text(report),encoding='utf-8')
 print(json_text({'decision':report['decision'],'contracts':len(contracts),'families':len(families),'rules':len(results),'pass':len(passing),'top':results[:3],'artifacts':report['artifacts']}))
if __name__=='__main__':main()
