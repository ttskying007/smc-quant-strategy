#!/usr/bin/env python3
"""V338 no-write: expansion-filter exit backtest.

V337 showed F1 has enough MFE but V335/V336 exits could not keep both WR and
Avg. This script tests broader non-outcome expansion filters (OR-unions of V337
pre-entry predicates) against executable T+1 exits. No production/frontend/write.
"""
from __future__ import annotations
import itertools, json, math, glob
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; KDIR=ROOT/'kline_cache'
OUT=AUD/f"v338_expansion_filter_exit_backtest_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v338_expansion_filter_exit_backtest_latest.json'
GATE={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'min_year_wr':91.0,'micro':1.0,'t1':0}

def dn(x:Any)->str:
 s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def sf(x:Any, default=None):
 try:
  if x is None or x=='': return default
  v=float(x); return default if math.isnan(v) or math.isinf(v) else v
 except Exception: return default
def latest_base()->Path:
 paths=[Path(p) for p in glob.glob(str(AUD/'v337_mfe_mae_ceiling_diagnosis_no_write_*'/'v337_base_with_mfe_mae.csv'))]
 if not paths: raise FileNotFoundError('missing V337 base csv')
 return max(paths,key=lambda p:p.stat().st_mtime)
def load_json(p:Path, default:Any)->Any:
 try: return json.loads(p.read_text())
 except Exception: return default

def load_bars(sym:str)->list[tuple[str,float,float,float,float]]:
 arr=[]; p=KDIR/f"{sym.replace('.','_')}_daily_750.json"
 for b in load_json(p,[]):
  d=dn(b.get('t') or b.get('date')); o,h,l,c=sf(b.get('o')),sf(b.get('h')),sf(b.get('l')),sf(b.get('c'))
  if d and None not in (o,h,l,c): arr.append((d,float(o),float(h),float(l),float(c)))
 return sorted(arr)

def metrics(vals:list[float|None], yrs:list[str])->dict[str,Any]:
 s=pd.Series(vals); y=pd.Series(yrs); ok=s.notna(); s=s[ok].astype(float); y=y[ok]
 if len(s)==0: return {'n':0,'wr':0,'avg':0,'micro':0,'min_year_n':0,'year_counts':{},'year_wr':{},'min_year_wr':0}
 yc={str(k):int(v) for k,v in y[y>='2023'].value_counts().sort_index().to_dict().items()}
 ywr={str(k):round(float((s[y==k]>0).mean()*100),2) for k in sorted(yc)}
 return {'n':int(len(s)),'wr':round(float((s>0).mean()*100),4),'avg':round(float(s.mean()),4),'micro':round(float(((s>0)&(s<1)).mean()*100),4),'min_year_n':int(min(yc.values()) if yc else 0),'year_counts':yc,'year_wr':ywr,'min_year_wr':round(float(min(ywr.values()) if ywr else 0),2)}
def gate(m:dict[str,Any])->bool:
 return m['n']>=GATE['n'] and m['min_year_n']>=GATE['min_year_n'] and m['wr']>=GATE['wr'] and m['avg']>=GATE['avg'] and m['min_year_wr']>=GATE['min_year_wr'] and m['micro']<=GATE['micro']

def main()->None:
 OUT.mkdir(parents=True,exist_ok=True); src=latest_base(); df=pd.read_csv(src,low_memory=False); df['entry_date']=df.entry_date.astype(str).str[:8]
 n=lambda c: pd.to_numeric(df.get(c,pd.Series(index=df.index)),errors='coerce'); ss=lambda c: df.get(c,pd.Series('',index=df.index)).astype(str)
 f1=n('v132_bull_count_3').ge(3)&n('v132_reclaim_bull_body_pct').le(60)&n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2)
 conds={
  'zone_ge_1.02':n('v85_zone_width_pct').ge(1.0204),'zone_ge_0.78':n('v85_zone_width_pct').ge(0.7823),
  'br_ge_76':n('v236_br_above_ma20').ge(76.3339),'br_ge_66':n('v236_br_above_ma20').ge(66.244),
  'risk_ge_3':n('risk_pct').ge(3.1189),'risk_ge_2':n('risk_pct').ge(1.9967),
  'body_le_34':n('v132_reclaim_bull_body_pct').le(34.5204),'takeover2':ss('v132_reclaim_class').eq('TRUE_TAKEOVER_2'),
  'bear_risk':ss('market_state').eq('BEAR_RISK'),'chase_ge_1.69':n('entry_chase_above_zone_pct').ge(1.6905),
  'reclaim_ge_1.29':n('reclaim_close_above_zone_pct').ge(1.291),
 }
 families={'F1_all':f1}
 items=list(conds.items())
 for k in [1,2,3]:
  for comb in itertools.combinations(items,k):
   m=pd.Series(False,index=df.index); names=[]
   for nm,c in comb: m|=c; names.append(nm)
   mask=f1&m
   yrs=df.loc[mask,'entry_date'].astype(str).str[:4]; yc=yrs[yrs>='2023'].value_counts().to_dict()
   if int(mask.sum())>=570 and yc and min(yc.values())>=70: families['F1__'+'__OR__'.join(names)]=mask
 cache={}
 paths={}
 for ix,r in df[f1].iterrows():
  sym=str(r.get('symbol') or ''); ed=dn(r.get('entry_date')); ep=sf(r.get('entry_price')); zl=sf(r.get('zone_low'))
  if not sym or not ep or not zl: continue
  if sym not in cache: cache[sym]=load_bars(sym)
  paths[ix]=(ep,zl,[b for b in cache[sym] if b[0]>ed][:30],ed[:4])
 def replay(ix:int,tp1_abs:float,tp1_frac:float,stop_mode:str,max_hold:int,trail:str)->float|None:
  ep,zl,path,_=paths[ix]; sl=zl*0.995
  if sl>=ep: sl=ep*0.985
  tp1=ep*(1+tp1_abs/100); got=False; pnl=0.0; peak=ep; rsl=sl
  for i,(_,_,h,l,c) in enumerate(path[:max_hold],1):
   if not got:
    if l<=sl: return (sl/ep-1)*100
    if h>=tp1:
     got=True; pnl=tp1_abs*tp1_frac; peak=max(peak,h); rsl=ep if stop_mode=='be' else ((ep+sl)/2 if stop_mode=='half_sl' else sl)
    elif i>=max_hold: return (c/ep-1)*100
    continue
   peak=max(peak,h)
   if trail=='peak20': rsl=max(rsl,peak*0.80)
   elif trail=='lock5_after15' and peak>=ep*1.15: rsl=max(rsl,ep*1.05)
   if l<=rsl: return pnl+(rsl/ep-1)*100*(1-tp1_frac)
   if i>=max_hold: return pnl+(c/ep-1)*100*(1-tp1_frac)
  return None
 results=[]; best_rows=[]
 contracts=list(itertools.product([4,6,8,10],[0.1,0.2,0.3],['sl','half_sl','be'],[20,30],['none','peak20','lock5_after15']))
 for fname,mask in families.items():
  idx=[int(i) for i in df.index[mask.fillna(False)] if int(i) in paths]
  if len(idx)<570: continue
  yrs=[paths[i][3] for i in idx]
  # MFE ceiling for the family, non-executable but useful diagnostic.
  mfe=pd.to_numeric(df.loc[idx,'mfe20_pct'],errors='coerce'); mae=pd.to_numeric(df.loc[idx,'mae20_pct'],errors='coerce'); close=pd.to_numeric(df.loc[idx,'close20_pct'],errors='coerce')
  ceiling={'mfe20_avg':round(float(mfe.mean()),4),'mfe10_rate':round(float((mfe>=10).mean()*100),4),'close20_wr':round(float((close>0).mean()*100),4),'close20_avg':round(float(close.mean()),4),'expansion_quality_rate':round(float(((mfe>=10)&(mae>-5)).mean()*100),4)}
  for tp1_abs,tp1_frac,stop_mode,max_hold,trail in contracts:
   vals=[replay(i,tp1_abs,tp1_frac,stop_mode,max_hold,trail) for i in idx]
   m=metrics(vals,yrs)
   score=(m['wr']-80)*0.5+m['avg']*0.8-m['micro']*0.25+m['min_year_wr']*0.03
   results.append({'family':fname,'tp1_abs':tp1_abs,'tp1_frac':tp1_frac,'stop_mode':stop_mode,'max_hold':max_hold,'trail':trail,'score':round(float(score),4),'hist':m,'ceiling':ceiling,'pass_gate':gate(m)})
 results=sorted(results,key=lambda r:(r['pass_gate'],r['hist']['wr'],r['hist']['avg'],r['hist']['n']),reverse=True); passing=[r for r in results if r['pass_gate']]
 pd.DataFrame([{**{k:r[k] for k in ['family','tp1_abs','tp1_frac','stop_mode','max_hold','trail','score','pass_gate']},**{f"hist_{k}":v for k,v in r['hist'].items() if not isinstance(v,dict)},**{f"ceil_{k}":v for k,v in r['ceiling'].items()}} for r in results[:800]]).to_csv(OUT/'v338_rule_table_top800.csv',index=False)
 report={'version':'V338_EXPANSION_FILTER_EXIT_BACKTEST_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source':str(src),'gate':GATE,'families_evaluated':len(families),'contracts_evaluated':len(results),'passing_rule_count':len(passing),'top_passing_rules':passing[:20],'top_rules':results[:40],'decision':'V338_EXPANSION_FILTER_EXIT_RECOVERS_GATE__SHADOW_ONLY_NO_WRITE' if passing else 'V338_NO_EXPANSION_FILTER_EXIT_RECOVERS_GATE__WR_AVG_TRADEOFF_CONFIRMED','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'rule_table':str(OUT/'v338_rule_table_top800.csv')}}
 (OUT/'v338_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':report['decision'],'passing_rule_count':len(passing),'top_rules':results[:10]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
