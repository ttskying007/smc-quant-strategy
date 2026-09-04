#!/usr/bin/env python3
"""V339 no-write: conservative same-bar audit for V338 pass.

Audits the executable rule with same-bar TP1/BE ambiguity handled pessimistically:
if a bar hits TP1 and also trades down through runner stop, the runner exits the
same bar at that stop. No production/frontend/watchlist writes.
"""
from __future__ import annotations
import json, math, glob
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; KDIR=ROOT/'kline_cache'
OUT=AUD/f"v339_conservative_samebar_audit_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v339_conservative_samebar_audit_latest.json'
GATE={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'min_year_wr':91.0,'micro':1.0,'t1':0}
RULE={'family':'F1_zone_ge_1.0204','tp1_abs':5.0,'tp1_frac':0.2,'runner_stop':'BE','max_hold':20,'trail':'none','same_bar_policy':'conservative_tp1_then_runner_stop_if_low_crosses_be'}

def dn(x:Any)->str:
 s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def sf(x:Any, default=None):
 try:
  if x is None or x=='': return default
  v=float(x); return default if math.isnan(v) or math.isinf(v) else v
 except Exception: return default
def load_json(p:Path, default:Any)->Any:
 try: return json.loads(p.read_text())
 except Exception: return default
def latest_base()->Path:
 paths=[Path(p) for p in glob.glob(str(AUD/'v337_mfe_mae_ceiling_diagnosis_no_write_*'/'v337_base_with_mfe_mae.csv'))]
 if not paths: raise FileNotFoundError('missing V337 base csv')
 return max(paths,key=lambda p:p.stat().st_mtime)
def bars(sym:str)->list[tuple[str,float,float,float,float]]:
 arr=[]; p=KDIR/f"{sym.replace('.','_')}_daily_750.json"
 for b in load_json(p,[]):
  d=dn(b.get('t') or b.get('date')); o,h,l,c=sf(b.get('o')),sf(b.get('h')),sf(b.get('l')),sf(b.get('c'))
  if d and None not in (o,h,l,c): arr.append((d,float(o),float(h),float(l),float(c)))
 return sorted(arr)
def metrics(rows:list[dict[str,Any]])->dict[str,Any]:
 closed=[r for r in rows if r.get('status')=='CLOSED']
 p=pd.Series([sf(r.get('pnl_pct'),0) for r in closed]); yrs=pd.Series([dn(r.get('entry_date'))[:4] for r in closed])
 yc={str(k):int(v) for k,v in yrs[yrs>='2023'].value_counts().sort_index().to_dict().items()}
 ywr={str(y):round(float((p[yrs==y]>0).mean()*100),2) for y in sorted(yc)}
 return {'n':len(closed),'wr':round(float((p>0).mean()*100),4),'avg':round(float(p.mean()),4),'micro':round(float(((p>0)&(p<1)).mean()*100),4),'min_year_n':int(min(yc.values()) if yc else 0),'year_counts':yc,'year_wr':ywr,'min_year_wr':round(float(min(ywr.values()) if ywr else 0),2),'t1':int(sum(bool(r.get('same_day_exit_violation')) for r in closed)),'exit_counts':{str(k):int(v) for k,v in pd.Series([r.get('exit_reason') for r in closed]).value_counts().to_dict().items()}}
def gate(m:dict[str,Any])->bool:
 return m['n']>=GATE['n'] and m['min_year_n']>=GATE['min_year_n'] and m['wr']>=GATE['wr'] and m['avg']>=GATE['avg'] and m['min_year_wr']>=GATE['min_year_wr'] and m['micro']<=GATE['micro'] and m['t1']==0

def replay(r:Any, b:list[tuple[str,float,float,float,float]])->dict[str,Any]:
 sym=str(r.symbol); ed=dn(r.entry_date); ep=sf(r.entry_price); zl=sf(r.zone_low)
 out={'symbol':sym,'entry_date':ed,'entry_price':ep,'zone_low':zl,'zone_high':sf(getattr(r,'zone_high',None)),'market_state':str(getattr(r,'market_state','')),'risk_pct':sf(getattr(r,'risk_pct',None)),'v85_zone_width_pct':sf(getattr(r,'v85_zone_width_pct',None)),'same_day_exit_violation':False}
 if not ep or not zl: out.update({'status':'FIELD_MISSING'}); return out
 sl=zl*0.995
 if sl>=ep: sl=ep*0.985
 tp1=ep*1.05; runner_stop=ep; pnl_tp1=RULE['tp1_abs']*RULE['tp1_frac']; path=[x for x in b if x[0]>ed][:RULE['max_hold']]
 out.update({'sl':sl,'tp1':tp1,'runner_stop':runner_stop,'tp1_frac':RULE['tp1_frac']})
 got_tp1=False; tp1_date=''
 for hold,(d,o,h,l,c) in enumerate(path,1):
  if not got_tp1:
   if l<=sl:
    out.update({'status':'CLOSED','exit_reason':'SL_BEFORE_TP1','exit_date':d,'hold_bars':hold,'pnl_pct':(sl/ep-1)*100,'tp1_hit':False}); return out
   if h>=tp1:
    got_tp1=True; tp1_date=d
    if l<=runner_stop:
     out.update({'status':'CLOSED','exit_reason':'TP1_AND_RUNNER_BE_SAME_BAR','exit_date':d,'hold_bars':hold,'pnl_pct':pnl_tp1,'tp1_hit':True,'tp1_date':tp1_date}); return out
   elif hold>=RULE['max_hold']:
    out.update({'status':'CLOSED','exit_reason':'TIME_NO_TP1','exit_date':d,'hold_bars':hold,'pnl_pct':(c/ep-1)*100,'tp1_hit':False}); return out
   continue
  if l<=runner_stop:
   out.update({'status':'CLOSED','exit_reason':'RUNNER_BE','exit_date':d,'hold_bars':hold,'pnl_pct':pnl_tp1,'tp1_hit':True,'tp1_date':tp1_date}); return out
  if hold>=RULE['max_hold']:
   out.update({'status':'CLOSED','exit_reason':'TIME_AFTER_TP1','exit_date':d,'hold_bars':hold,'pnl_pct':pnl_tp1+(c/ep-1)*100*(1-RULE['tp1_frac']),'tp1_hit':True,'tp1_date':tp1_date}); return out
 out.update({'status':'OPEN_UNEXPIRED','exit_reason':'OPEN','pnl_pct':None,'tp1_hit':got_tp1,'tp1_date':tp1_date}); return out

def main()->None:
 OUT.mkdir(parents=True,exist_ok=True); src=latest_base(); df=pd.read_csv(src,low_memory=False); df['entry_date']=df.entry_date.astype(str).str[:8]
 n=lambda c: pd.to_numeric(df.get(c,pd.Series(index=df.index)),errors='coerce')
 mask=n('v132_bull_count_3').ge(3)&n('v132_reclaim_bull_body_pct').le(60)&n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2)&n('v85_zone_width_pct').ge(1.0204)
 cache={}; rows=[]
 for r in df[mask.fillna(False)].itertuples():
  sym=str(r.symbol)
  if sym not in cache: cache[sym]=bars(sym)
  rows.append(replay(r,cache[sym]))
 m=metrics(rows); passed=gate(m)
 pd.DataFrame(rows).to_csv(OUT/'v339_conservative_trades.csv',index=False)
 report={'version':'V339_CONSERVATIVE_SAMEBAR_AUDIT_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source':str(src),'gate':GATE,'rule':RULE,'metrics':m,'pass_gate':passed,'decision':'V339_CONSERVATIVE_PASS__READY_FOR_SHADOW_PROMOTION_REVIEW' if passed else 'V339_CONSERVATIVE_FAIL__V338_PASS_WAS_INTRABAR_OPTIMISTIC','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'trades_csv':str(OUT/'v339_conservative_trades.csv')}}
 (OUT/'v339_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':report['decision'],'metrics':m,'artifacts':report['artifacts']},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
