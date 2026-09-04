#!/usr/bin/env python3
"""V337b no-write: finalize MFE/MAE diagnosis from materialized V337 base CSV.

The first V337 run completed expensive MFE/MAE materialization but timed out in
an overly broad predicate-combination search. V337b reuses that materialized
CSV and performs bounded singles+pairs mining only.
"""
from __future__ import annotations
import itertools, json, math, glob
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; OUT=AUD/f"v337b_mfe_mae_ceiling_diagnosis_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v337_mfe_mae_ceiling_diagnosis_latest.json'

def latest_base()->Path:
 paths=[Path(p) for p in glob.glob(str(AUD/'v337_mfe_mae_ceiling_diagnosis_no_write_*'/'v337_base_with_mfe_mae.csv'))]
 if not paths: raise FileNotFoundError('missing v337_base_with_mfe_mae.csv')
 return max(paths,key=lambda p:p.stat().st_mtime)
def sf(x:Any, default=None):
 try:
  v=float(x); return default if math.isnan(v) or math.isinf(v) else v
 except Exception: return default
def summary(df:pd.DataFrame)->dict[str,Any]:
 if len(df)==0: return {'n':0}
 mfe=pd.to_numeric(df.mfe20_pct,errors='coerce'); mae=pd.to_numeric(df.mae20_pct,errors='coerce'); close=pd.to_numeric(df.close20_pct,errors='coerce'); yrs=df.entry_date.astype(str).str[:4]; yc={str(k):int(v) for k,v in yrs[yrs>='2023'].value_counts().sort_index().to_dict().items()}
 return {'n':int(len(df)),'min_year_n':min(yc.values()) if yc else 0,'year_counts':yc,'mfe20_avg':round(float(mfe.mean()),4),'mfe20_median':round(float(mfe.median()),4),'mfe8_rate':round(float((mfe>=8).mean()*100),4),'mfe10_rate':round(float((mfe>=10).mean()*100),4),'mfe15_rate':round(float((mfe>=15).mean()*100),4),'mae20_avg':round(float(mae.mean()),4),'mae5_breach_rate':round(float((mae<=-5).mean()*100),4),'mae8_breach_rate':round(float((mae<=-8).mean()*100),4),'close20_avg':round(float(close.mean()),4),'expansion_quality_rate':round(float(((mfe>=10)&(mae>-5)).mean()*100),4)}
def main():
 OUT.mkdir(parents=True,exist_ok=True); src=latest_base(); df=pd.read_csv(src,low_memory=False); df['entry_date']=df.entry_date.astype(str).str[:8]
 # Reconstruct family subsets inside the materialized base universe.
 n=lambda c: pd.to_numeric(df.get(c,pd.Series(index=df.index)),errors='coerce'); ss=lambda c: df.get(c,pd.Series('',index=df.index)).astype(str)
 families={
  'base_v164_industry':pd.Series(True,index=df.index),
  'F1_bull3_body60_pull2':n('v132_bull_count_3').ge(3)&n('v132_reclaim_bull_body_pct').le(60)&n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2),
  'F4_bull3_body60_pull2_chase3':n('v132_bull_count_3').ge(3)&n('v132_reclaim_bull_body_pct').le(60)&n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2)&n('entry_chase_above_zone_pct').le(3),
  'F6_bull3_body60_pull2_reclaim_le2':n('v132_bull_count_3').ge(3)&n('v132_reclaim_bull_body_pct').le(60)&n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2)&n('reclaim_close_above_zone_pct').le(2),
  'F2_bull3_zone2_ob':n('v132_bull_count_3').ge(3)&n('v85_zone_width_pct').ge(2)&ss('poi_source').isin(['DEMAND_OB','OB+FVG']),
 }
 family_reports={k:summary(df[m.fillna(False)]) for k,m in families.items()}
 mine=df[families['F1_bull3_body60_pull2'].fillna(False)].copy()
 preds=[]
 num_cols=[c for c in ['risk_pct','entry_chase_above_zone_pct','v85_zone_width_pct','v132_reclaim_bull_body_pct','v132_reclaim_close_pos_pct','v132_post_zone_pullback_depth_pct_1','v132_post_zone_pullback_depth_pct_2','v132_post_zone_pullback_depth_pct_3','v132_bull_count_3','v236_all_strong1_pct','v236_br_above_ma20','v244_ind_up1_pct','v244_ind_strong1_pct','v244_ind_mean_ret1','source_gap_atr','source_mid_body_atr','reclaim_close_above_zone_pct','touch_to_reclaim_bars'] if c in mine.columns]
 for c in num_cols:
  s=pd.to_numeric(mine[c],errors='coerce'); vals=s.dropna()
  if len(vals)<200: continue
  for q in sorted(set(round(float(x),4) for x in vals.quantile([.2,.35,.5,.65,.8]).dropna())):
   for name,mask in [(f'{c}<={q}',s.le(q)),(f'{c}>={q}',s.ge(q))]:
    cnt=int(mask.sum())
    if 150<=cnt<=len(mine)*0.9: preds.append((name,mask.fillna(False)))
 for c in ['market_state','poi_source','event_type','v132_reclaim_class']:
  if c in mine.columns:
   for val,cnt in mine[c].astype(str).value_counts().items():
    if 150<=cnt<=len(mine)*0.9: preds.append((f'{c}=={val}',mine[c].astype(str).eq(str(val))))
 # rank singles, keep top 40, then pairs only.
 singles=[]
 for name,mask in preds:
  sub=mine[mask]
  if len(sub)<150: continue
  sm=summary(sub); score=sm['expansion_quality_rate']*0.55+sm['mfe10_rate']*0.25-sm['mae5_breach_rate']*0.2+min(sm['n'],600)/600
  singles.append((score,name,mask,sm))
 singles=sorted(singles,key=lambda x:x[0],reverse=True)[:40]
 results=[{'rule':name,'score':round(float(score),4),'summary':sm} for score,name,mask,sm in singles]
 for (s1,n1,m1,_),(s2,n2,m2,_) in itertools.combinations(singles,2):
  mask=m1&m2; sub=mine[mask]
  if len(sub)<120: continue
  sm=summary(sub); score=sm['expansion_quality_rate']*0.55+sm['mfe10_rate']*0.25-sm['mae5_breach_rate']*0.2+min(sm['n'],600)/600
  results.append({'rule':n1+' & '+n2,'score':round(float(score),4),'summary':sm})
 results=sorted(results,key=lambda r:(r['summary']['expansion_quality_rate'],r['summary']['mfe20_avg'],r['summary']['n']),reverse=True)
 pd.DataFrame([{**{'rule':r['rule'],'score':r['score']},**r['summary']} for r in results[:300]]).to_csv(OUT/'v337_mfe_predicate_table_top300.csv',index=False)
 report={'version':'V337B_MFE_MAE_CEILING_DIAGNOSIS_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source':str(src),'family_reports':family_reports,'top_mfe_predicates':results[:30],'decision':'V337_DIAGNOSIS_DONE__NEXT_BUILD_EXPANSION_FILTER_BACKTEST','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'base_mfe_mae':str(src),'predicate_table':str(OUT/'v337_mfe_predicate_table_top300.csv')}}
 (OUT/'v337_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':report['decision'],'family_reports':family_reports,'top_mfe_predicates':results[:10]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
