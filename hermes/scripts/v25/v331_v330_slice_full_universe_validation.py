#!/usr/bin/env python3
"""V331 no-write: full-universe validation for V330 shadow slices.

V330 found promising slices inside the already-selected V246 historical set. That
is insufficient: this script validates the same rules against the full V164 dry-run
universe with T+1 executable replay, so a slice cannot be promoted merely because
it fits the historical selected population.

No production/frontend/watchlist writes.
"""
from __future__ import annotations

import importlib.util, json, math
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; SRC=AUD/'v164_corrected_scanner_dry_run_20260622/v164_dryrun_rows.json'
OUT=AUD/f"v331_v330_slice_full_universe_validation_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v331_v330_slice_full_universe_validation_latest.json'
GATE={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'min_year_wr':91.0,'micro':1.0,'t1':0}
MAX_HOLD=10

def load_mod(path,name):
 spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(mod); return mod
v326=load_mod('/root/.hermes/scripts/v25/v326_v246_lineage_current_supply_audit.py','v326_for_v331')
v328=load_mod('/root/.hermes/scripts/v25/v328_current_supply_gap_and_relaxed_gate_audit.py','v328_for_v331')

def dn(x:Any)->str:
 s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def sf(x:Any, default=None):
 try:
  if x is None or x=='': return default
  v=float(x); return default if math.isnan(v) or math.isinf(v) else v
 except Exception: return default
def boolish(x:Any)->bool: return str(x).strip().lower() in {'true','1','yes'}

def metrics(rows:list[dict[str,Any]])->dict[str,Any]:
 closed=[r for r in rows if r.get('replay_status')=='CLOSED']
 if not closed: return {'n':0,'wr':0,'avg':0,'min_year_n':0,'year_counts':{},'year_wr':{},'min_year_wr':0,'micro':0,'t1':0,'exit_counts':{}}
 p=pd.Series([sf(r.get('pnl_pct'),0) for r in closed]); yrs=pd.Series([dn(r.get('entry_date'))[:4] for r in closed]); yc=yrs.value_counts().sort_index().to_dict(); ywr={str(y):round(float((p[yrs==y]>0).mean()*100),2) for y in sorted(yc)}
 return {'n':len(closed),'wr':round(float((p>0).mean()*100),4),'avg':round(float(p.mean()),4),'min_year_n':int(min(yc.values()) if yc else 0),'year_counts':{str(k):int(v) for k,v in yc.items()},'year_wr':ywr,'min_year_wr':round(float(min(ywr.values()) if ywr else 0),2),'micro':round(float(((p>0)&(p<1)).mean()*100),4),'t1':int(sum(bool(r.get('same_day_exit_violation')) for r in closed)),'exit_counts':{str(k):int(v) for k,v in pd.Series([r.get('exit_reason') for r in closed]).value_counts().to_dict().items()}}

def pass_gate(m): return m['n']>=GATE['n'] and m['min_year_n']>=GATE['min_year_n'] and m['wr']>=GATE['wr'] and m['avg']>=GATE['avg'] and m['min_year_wr']>=GATE['min_year_wr'] and m['micro']<=GATE['micro'] and m['t1']==0

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 rows=json.loads(SRC.read_text())
 all_strong,strong_dates=v326.build_all_market_strong1(); br,br_dates=v326.load_breadth_above_ma20(); sym_ind,ind_feats,ind_dates=v326.build_industry_features(); hist=v326.load_history()
 enriched=[]
 for r0 in rows:
  r=dict(r0); ed=dn(r.get('entry_date')); sym=str(r.get('symbol') or ''); r['entry_date']=ed
  ps=v326.previous(strong_dates,ed); pb=v326.previous(br_dates,ed); ind=sym_ind.get(sym,'UNKNOWN'); pi=v326.previous(ind_dates,ed)
  r['v236_all_strong1_pct']=all_strong.get(ps); r['v236_br_above_ma20']=br.get(pb); r['v244_industry']=ind; r.update(ind_feats.get((pi,ind),{}))
  r['v331_actual_bars_since_entry']=v328.actual_bars_since(sym,ed); r['v331_any_history_overlap']=any((sym,ed) in s for s in hist.values())
  enriched.append(r)
 def base(r): return boolish(r.get('v164_rule_pass')) and v326.industry_addback_pass(r)
 rules:dict[str,Callable[[dict[str,Any]],bool]]={
  'v330_bull3_ge_3': lambda r: base(r) and sf(r.get('v132_bull_count_3'),-1)>=3,
  'v330_bull3_ge_3_strong1_le_25': lambda r: base(r) and sf(r.get('v132_bull_count_3'),-1)>=3 and sf(r.get('v236_all_strong1_pct'),999)<=25,
  'v330_ob_or_obfvg_bull3_strong1_le_25': lambda r: base(r) and str(r.get('poi_source')) in {'DEMAND_OB','OB+FVG'} and sf(r.get('v132_bull_count_3'),-1)>=3 and sf(r.get('v236_all_strong1_pct'),999)<=25,
  'v330_bull3_chase_le_3': lambda r: base(r) and sf(r.get('v132_bull_count_3'),-1)>=3 and sf(r.get('entry_chase_above_zone_pct'),999)<=3,
  'v330_bull3_risk_2_6': lambda r: base(r) and sf(r.get('v132_bull_count_3'),-1)>=3 and 2<=sf(r.get('risk_pct'),999)<=6,
 }
 reports={}; samples=[]
 for name,fn in rules.items():
  picked=[]; seen=set()
  for r in enriched:
   if not fn(r): continue
   k=(str(r.get('symbol')),dn(r.get('entry_date')),str(r.get('poi_source')))
   if k in seen: continue
   seen.add(k); rr=dict(r); rr.update(v328.replay(rr)); picked.append(rr)
  hist_closed=[r for r in picked if r.get('v331_actual_bars_since_entry') is not None and r.get('v331_actual_bars_since_entry')>=MAX_HOLD]
  current=[r for r in picked if r.get('v331_actual_bars_since_entry') is not None and r.get('v331_actual_bars_since_entry')<=MAX_HOLD and not r.get('v331_any_history_overlap')]
  m=metrics(hist_closed); cm=metrics([r for r in current if r.get('replay_status')=='CLOSED'])
  open_current=[r for r in current if r.get('replay_status')!='CLOSED']
  reports[name]={'total_rows':len(picked),'historical_closed_rows':len(hist_closed),'historical_metrics':m,'production_gate_pass':pass_gate(m),'current_nonhistory_actionable10_rows':len(current),'current_closed_metrics':cm,'current_open_rows':len(open_current),'current_open_slim':[{k:r.get(k) for k in ['symbol','entry_date','poi_source','entry_price','zone_low','risk_pct','entry_chase_above_zone_pct','v132_bull_count_3','v236_all_strong1_pct','latest_date','latest_close']} for r in open_current[:30]]}
  for r in open_current[:30]: samples.append({'rule':name,**{k:r.get(k) for k in ['symbol','entry_date','poi_source','entry_price','zone_low','risk_pct','entry_chase_above_zone_pct','v132_bull_count_3','v236_all_strong1_pct','latest_date','latest_close']}})
 pd.DataFrame(samples).to_csv(OUT/'v331_current_open_samples.csv',index=False)
 decision='V331_NO_V330_SLICE_PASSES_FULL_UNIVERSE_PRODUCTION_GATE__KEEP_SHADOW_ONLY'
 if any(v['production_gate_pass'] and v['current_open_rows']>0 for v in reports.values()): decision='V331_FULL_UNIVERSE_PASSING_SLICE_FOUND__READY_FOR_ENDPOINT_SHADOW_NOT_PRODUCTION_WRITE'
 report={'version':'V331_V330_SLICE_FULL_UNIVERSE_VALIDATION_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'gate':GATE,'reports':reports,'decision':decision,'artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'current_open_samples':str(OUT/'v331_current_open_samples.csv')}}
 (OUT/'v331_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':decision,'reports':reports},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
