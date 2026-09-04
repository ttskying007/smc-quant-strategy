#!/usr/bin/env python3
"""V345 no-write: cost/slippage robustness for V344 dedup-passed V343.

Applies deterministic per-trade cost haircuts to deduplicated V343 rows to test
whether the pass is fragile. No production/frontend/watchlist writes.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; V344=AUD/'v344_v343_dedup_robustness_latest.json'
OUT=AUD/f"v345_v343_cost_stress_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v345_v343_cost_stress_latest.json'
GATE={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'min_year_wr':91.0,'micro':1.0,'t1':0,'current_open':1}

def metrics(df:pd.DataFrame,cost:float)->dict[str,Any]:
 d=df[df.status.eq('CLOSED')].copy(); p=pd.to_numeric(d.pnl_pct,errors='coerce')-cost; yrs=d.entry_date.astype(str).str[:4]
 yc={str(k):int(v) for k,v in yrs[yrs>='2023'].value_counts().sort_index().to_dict().items()}; ywr={str(y):round(float((p[yrs==y]>0).mean()*100),2) for y in sorted(yc)}
 return {'n':int(len(d)),'wr':round(float((p>0).mean()*100),4),'avg':round(float(p.mean()),4),'micro':round(float(((p>0)&(p<1)).mean()*100),4),'min_year_n':int(min(yc.values()) if yc else 0),'year_counts':yc,'year_wr':ywr,'min_year_wr':round(float(min(ywr.values()) if ywr else 0),2),'t1':0,'exit_counts':{str(k):int(v) for k,v in d.exit_reason.value_counts().to_dict().items()}}
def gate(m:dict[str,Any],open_n:int)->bool:
 return m['n']>=GATE['n'] and m['min_year_n']>=GATE['min_year_n'] and m['wr']>=GATE['wr'] and m['avg']>=GATE['avg'] and m['min_year_wr']>=GATE['min_year_wr'] and m['micro']<=GATE['micro'] and m['t1']==0 and open_n>=GATE['current_open']
def main():
 OUT.mkdir(parents=True,exist_ok=True); rep=json.loads(V344.read_text()); src_dir=Path(rep['artifacts']['out_dir'])
 policies=['best_poi_then_bsl','max_bsl','min_risk','prefer_ob']; costs=[0,0.1,0.2,0.3,0.5,1.0]
 results=[]
 for pol in policies:
  hist=pd.read_csv(src_dir/f'v344_hist_{pol}.csv'); open_n=next(r['current_open_rows'] for r in rep['policy_results'] if r['policy']==pol)
  for cost in costs:
   m=metrics(hist,cost); results.append({'policy':pol,'cost_pct':cost,'open_n':open_n,'metrics':m,'pass_gate':gate(m,open_n)})
 table=pd.DataFrame([{**{'policy':r['policy'],'cost_pct':r['cost_pct'],'open_n':r['open_n'],'pass_gate':r['pass_gate']},**{f'hist_{k}':v for k,v in r['metrics'].items() if not isinstance(v,dict)}} for r in results])
 table.to_csv(OUT/'v345_cost_stress_table.csv',index=False)
 report={'version':'V345_V343_COST_STRESS_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source_report':str(V344),'gate':GATE,'costs_tested_pct':costs,'results':results,'max_cost_all_dedup_policies_pass':max([c for c in costs if all(r['pass_gate'] for r in results if r['cost_pct']==c)] or [-1]),'decision':'V345_COST_STRESS_PASS_ROBUST' if any(r['cost_pct']>=0.2 and r['pass_gate'] for r in results) else 'V345_COST_STRESS_FRAGILE','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'table':str(OUT/'v345_cost_stress_table.csv')}}
 (OUT/'v345_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':report['decision'],'max_cost_all_dedup_policies_pass':report['max_cost_all_dedup_policies_pass'],'results':results},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
