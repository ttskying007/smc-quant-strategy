#!/usr/bin/env python3
"""V344 no-write: robustness audit for V343.

Checks whether V343 survives duplicate-candidate removal and non-outcome
selection policies. This guards against counting multiple POIs on the same
symbol/date as independent trades. No production/frontend/watchlist writes.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; SRC=AUD/'v343_bsl_room_deep_runner_latest.json'
OUT=AUD/f"v344_v343_dedup_robustness_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v344_v343_dedup_robustness_latest.json'
GATE={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'min_year_wr':91.0,'micro':1.0,'t1':0,'current_open':1}

def dn(x:Any)->str:
 s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def sf(x:Any,d=None):
 try:
  if x is None or x=='': return d
  v=float(x); return d if pd.isna(v) else v
 except Exception: return d
def metrics(df:pd.DataFrame)->dict[str,Any]:
 closed=df[df.status.eq('CLOSED')].copy()
 if len(closed)==0: return {'n':0,'wr':0,'avg':0,'micro':0,'min_year_n':0,'year_counts':{},'year_wr':{},'min_year_wr':0,'t1':0,'exit_counts':{}}
 p=pd.to_numeric(closed.pnl_pct,errors='coerce'); yrs=closed.entry_date.astype(str).str[:4]
 yc={str(k):int(v) for k,v in yrs[yrs>='2023'].value_counts().sort_index().to_dict().items()}
 ywr={str(y):round(float((p[yrs==y]>0).mean()*100),2) for y in sorted(yc)}
 return {'n':int(len(closed)),'wr':round(float((p>0).mean()*100),4),'avg':round(float(p.mean()),4),'micro':round(float(((p>0)&(p<1)).mean()*100),4),'min_year_n':int(min(yc.values()) if yc else 0),'year_counts':yc,'year_wr':ywr,'min_year_wr':round(float(min(ywr.values()) if ywr else 0),2),'t1':int(closed.same_day_exit_violation.astype(str).str.lower().isin(['true','1']).sum()) if 'same_day_exit_violation' in closed else 0,'exit_counts':{str(k):int(v) for k,v in closed.exit_reason.value_counts().to_dict().items()}}
def gate(m:dict[str,Any], open_n:int=1)->bool:
 return m['n']>=GATE['n'] and m['min_year_n']>=GATE['min_year_n'] and m['wr']>=GATE['wr'] and m['avg']>=GATE['avg'] and m['min_year_wr']>=GATE['min_year_wr'] and m['micro']<=GATE['micro'] and m['t1']==0 and open_n>=GATE['current_open']
def choose(df:pd.DataFrame, policy:str)->pd.DataFrame:
 d=df.copy()
 poi_rank={'OB+FVG':0,'DEMAND_OB':1,'FVG_Demand':2}
 d['_poi_rank']=d.poi_source.map(poi_rank).fillna(9)
 if policy=='all_rows': return d
 if policy=='best_poi_then_bsl':
  d=d.sort_values(['symbol','entry_date','_poi_rank','bsl60_room_pct','risk_proxy'],ascending=[True,True,True,False,True])
 elif policy=='max_bsl':
  d=d.sort_values(['symbol','entry_date','bsl60_room_pct','risk_proxy'],ascending=[True,True,False,True])
 elif policy=='min_risk':
  d=d.sort_values(['symbol','entry_date','risk_proxy','bsl60_room_pct'],ascending=[True,True,True,False])
 elif policy=='prefer_ob':
  d=d.sort_values(['symbol','entry_date','_poi_rank','risk_proxy'],ascending=[True,True,True,True])
 return d.drop_duplicates(['symbol','entry_date'],keep='first')

def main():
 OUT.mkdir(parents=True,exist_ok=True); rep=json.loads(SRC.read_text()); allp=rep['artifacts']['all_rows_csv']; histp=rep['artifacts']['hist_csv']; curp=rep['artifacts']['current_csv']
 all_df=pd.read_csv(allp); hist=pd.read_csv(histp); cur=pd.read_csv(curp)
 for d in [all_df,hist,cur]:
  d['entry_date']=d.entry_date.map(dn); d['risk_proxy']=(pd.to_numeric(d.entry_price,errors='coerce')-pd.to_numeric(d.zone_low,errors='coerce'))/pd.to_numeric(d.entry_price,errors='coerce')*100
 policies=['all_rows','best_poi_then_bsl','max_bsl','min_risk','prefer_ob']
 results=[]
 for pol in policies:
  hd=choose(hist,pol); cd=choose(cur,pol)
  m=metrics(hd); cm=metrics(cd); open_n=int(cd.status.eq('OPEN_UNEXPIRED').sum()) if len(cd) else 0
  results.append({'policy':pol,'hist_rows':int(len(hd)),'current_rows':int(len(cd)),'current_open_rows':open_n,'metrics':m,'current_closed':cm,'pass_gate':gate(m,open_n)})
 # duplicate diagnostics on historical rows
 dup=hist.groupby(['symbol','entry_date']).size().reset_index(name='n').query('n>1')
 diag={'hist_duplicate_symbol_date_groups':int(len(dup)),'hist_duplicate_extra_rows':int((dup.n-1).sum()) if len(dup) else 0,'all_hist_rows':int(len(hist)),'unique_hist_symbol_dates':int(hist.drop_duplicates(['symbol','entry_date']).shape[0]),'current_duplicate_groups':int(cur.groupby(['symbol','entry_date']).size().reset_index(name='n').query('n>1').shape[0])}
 pd.DataFrame([{**{'policy':r['policy'],'hist_rows':r['hist_rows'],'current_rows':r['current_rows'],'current_open_rows':r['current_open_rows'],'pass_gate':r['pass_gate']},**{f"hist_{k}":v for k,v in r['metrics'].items() if not isinstance(v,dict)},**{f"cur_{k}":v for k,v in r['current_closed'].items() if not isinstance(v,dict)}} for r in results]).to_csv(OUT/'v344_dedup_policy_table.csv',index=False)
 for pol in policies:
  choose(hist,pol).to_csv(OUT/f'v344_hist_{pol}.csv',index=False)
 report={'version':'V344_V343_DEDUP_ROBUSTNESS_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source_report':str(SRC),'gate':GATE,'duplicate_diagnostics':diag,'policy_results':results,'passing_policies':[r for r in results if r['pass_gate']],'decision':'V344_V343_SURVIVES_DEDUP__READY_FOR_INTEGRATION_SHADOW' if any(r['pass_gate'] for r in results if r['policy']!='all_rows') else 'V344_V343_FAILS_DEDUP__DO_NOT_PROMOTE','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'policy_table':str(OUT/'v344_dedup_policy_table.csv')}}
 (OUT/'v344_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':report['decision'],'duplicate_diagnostics':diag,'policy_results':results},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
