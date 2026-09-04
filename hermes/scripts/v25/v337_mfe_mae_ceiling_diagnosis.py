#!/usr/bin/env python3
"""V337 no-write: MFE/MAE ceiling diagnosis for V336 failure.

V336 showed TP1+runner keeps WR high but avg remains far below production target.
V337 measures whether the candidate family actually contains enough forward
range (MFE) to support 7.6% average, and mines non-outcome pre-entry predicates
that separate expansion-capable rows from quick-TP-only rows.

No production/frontend/watchlist writes.
"""
from __future__ import annotations
import itertools, json, math
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; KDIR=ROOT/'kline_cache'; V333=AUD/'v333_full_universe_rule_search_after_breadth_refresh_latest.json'
OUT=AUD/f"v337_mfe_mae_ceiling_diagnosis_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v337_mfe_mae_ceiling_diagnosis_latest.json'
WEAK={'C27医药制造业','C32有色金属冶炼和压延加工业'}; MAX_HOLD=20

def dn(x:Any)->str:
 s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def sf(x:Any, default=None):
 try:
  if x is None or x=='': return default
  v=float(x); return default if math.isnan(v) or math.isinf(v) else v
 except Exception: return default
def boolish(x:Any)->bool: return str(x).strip().lower() in {'true','1','yes'}
def load_json(p:Path, default:Any)->Any:
 try: return json.loads(p.read_text())
 except Exception: return default

def bars(sym:str)->list[dict[str,Any]]:
 arr=[]; p=KDIR/f"{sym.replace('.','_')}_daily_750.json"
 for b in load_json(p,[]):
  d=dn(b.get('t') or b.get('date')); o,h,l,c=sf(b.get('o')),sf(b.get('h')),sf(b.get('l')),sf(b.get('c'))
  if d and None not in (o,h,l,c): arr.append({'date':d,'o':float(o),'h':float(h),'l':float(l),'c':float(c)})
 return sorted(arr,key=lambda x:x['date'])

def mfe_mae(r:dict[str,Any], cache:dict[str,list[dict[str,Any]]], max_hold:int=MAX_HOLD)->dict[str,Any]:
 sym,ed=str(r.get('symbol') or ''),dn(r.get('entry_date')); ep=sf(r.get('entry_price'))
 if sym not in cache: cache[sym]=bars(sym)
 path=[b for b in cache[sym] if b['date']>ed][:max_hold]
 if not path or not ep: return {'mfe20_pct':None,'mae20_pct':None,'close20_pct':None,'path_bars20':len(path),'mfe10_hit':False,'mfe15_hit':False,'mae5_breach':False}
 mx=max(b['h'] for b in path); mn=min(b['l'] for b in path); lc=path[-1]['c']
 mfe=(mx/ep-1)*100; mae=(mn/ep-1)*100; close=(lc/ep-1)*100
 return {'mfe20_pct':mfe,'mae20_pct':mae,'close20_pct':close,'path_bars20':len(path),'mfe8_hit':mfe>=8,'mfe10_hit':mfe>=10,'mfe15_hit':mfe>=15,'mae5_breach':mae<=-5,'mae8_breach':mae<=-8}

def summary(df:pd.DataFrame)->dict[str,Any]:
 if len(df)==0: return {'n':0}
 mfe=pd.to_numeric(df.mfe20_pct,errors='coerce'); mae=pd.to_numeric(df.mae20_pct,errors='coerce'); close=pd.to_numeric(df.close20_pct,errors='coerce')
 yrs=df.entry_date.astype(str).str[:4]; yc={str(k):int(v) for k,v in yrs[yrs>='2023'].value_counts().sort_index().to_dict().items()}
 return {'n':int(len(df)),'min_year_n':min(yc.values()) if yc else 0,'year_counts':yc,'mfe20_avg':round(float(mfe.mean()),4),'mfe20_median':round(float(mfe.median()),4),'mfe8_rate':round(float((mfe>=8).mean()*100),4),'mfe10_rate':round(float((mfe>=10).mean()*100),4),'mfe15_rate':round(float((mfe>=15).mean()*100),4),'mae20_avg':round(float(mae.mean()),4),'mae5_breach_rate':round(float((mae<=-5).mean()*100),4),'mae8_breach_rate':round(float((mae<=-8).mean()*100),4),'close20_avg':round(float(close.mean()),4),'expansion_quality_rate':round(float(((mfe>=10)&(mae>-5)).mean()*100),4)}

def main():
 OUT.mkdir(parents=True,exist_ok=True); rep=load_json(V333,{}); df=pd.read_csv(rep['artifacts']['replayed_csv'],low_memory=False); df['entry_date']=df.entry_date.map(dn)
 actual=pd.to_numeric(df.v333_actual_bars_since_entry,errors='coerce'); hist=actual.ge(MAX_HOLD)
 weak=df.v244_industry.astype(str).isin(WEAK); add=pd.to_numeric(df.v244_ind_strong1_pct,errors='coerce').ge(31.1688)|pd.to_numeric(df.v236_br_above_ma20,errors='coerce').ge(46.8561); base=df.v164_rule_pass.map(boolish)&((~weak)|add)
 n=lambda c: pd.to_numeric(df.get(c,pd.Series(index=df.index)),errors='coerce'); ss=lambda c: df.get(c,pd.Series('',index=df.index)).astype(str)
 families={
  'base_v164_industry':base,
  'F1_bull3_body60_pull2':base&n('v132_bull_count_3').ge(3)&n('v132_reclaim_bull_body_pct').le(60)&n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2),
  'F4_bull3_body60_pull2_chase3':base&n('v132_bull_count_3').ge(3)&n('v132_reclaim_bull_body_pct').le(60)&n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2)&n('entry_chase_above_zone_pct').le(3),
  'F6_bull3_body60_pull2_reclaim_le2':base&n('v132_bull_count_3').ge(3)&n('v132_reclaim_bull_body_pct').le(60)&n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2)&n('reclaim_close_above_zone_pct').le(2),
  'F2_bull3_zone2_ob':base&n('v132_bull_count_3').ge(3)&n('v85_zone_width_pct').ge(2)&ss('poi_source').isin(['DEMAND_OB','OB+FVG']),
 }
 cache={}; enrich=[]
 # Only historical rows are used for outcome diagnosis; current rows remain for later shadow only.
 target_mask=hist & base
 for r in df[target_mask].to_dict('records'):
  rr=dict(r); rr.update(mfe_mae(rr,cache)); enrich.append(rr)
 edf=pd.DataFrame(enrich); edf.to_csv(OUT/'v337_base_with_mfe_mae.csv',index=False)
 family_reports={}
 for name,mask in families.items():
  keys=set(zip(df[hist&mask.fillna(False)].symbol.astype(str), df[hist&mask.fillna(False)].entry_date.astype(str), df[hist&mask.fillna(False)].poi_source.astype(str)))
  sub=edf[[ (str(r.symbol),str(r.entry_date),str(r.poi_source)) in keys for _,r in edf.iterrows() ]].copy()
  family_reports[name]=summary(sub)
 # Mine predicates over F1/F4 universe. Quality target: MFE>=10 and MAE>-5.
 mine_mask=(hist & families['F1_bull3_body60_pull2'].fillna(False)); mine_keys=set(zip(df[mine_mask].symbol.astype(str),df[mine_mask].entry_date.astype(str),df[mine_mask].poi_source.astype(str)))
 mine=edf[[ (str(r.symbol),str(r.entry_date),str(r.poi_source)) in mine_keys for _,r in edf.iterrows() ]].copy()
 preds=[]
 num_cols=[c for c in ['risk_pct','entry_chase_above_zone_pct','v85_zone_width_pct','v132_reclaim_bull_body_pct','v132_reclaim_close_pos_pct','v132_post_zone_pullback_depth_pct_1','v132_post_zone_pullback_depth_pct_2','v132_post_zone_pullback_depth_pct_3','v132_bull_count_3','v236_all_strong1_pct','v236_br_above_ma20','v244_ind_up1_pct','v244_ind_strong1_pct','v244_ind_mean_ret1','source_gap_atr','source_mid_body_atr','reclaim_close_above_zone_pct','touch_to_reclaim_bars'] if c in mine.columns]
 for c in num_cols:
  s=pd.to_numeric(mine[c],errors='coerce'); vals=s.dropna()
  if len(vals)<200: continue
  for q in sorted(set(round(float(x),4) for x in vals.quantile([.15,.25,.35,.5,.65,.75,.85]).dropna())):
   for name,mask in [(f'{c}<={q}',s.le(q)),(f'{c}>={q}',s.ge(q))]:
    cnt=int(mask.sum())
    if 120<=cnt<=len(mine)*0.95: preds.append((name,mask.fillna(False)))
 for c in ['market_state','poi_source','event_type','v132_reclaim_class']:
  if c in mine.columns:
   for val,cnt in mine[c].astype(str).value_counts().items():
    if 120<=cnt<=len(mine)*0.95: preds.append((f'{c}=={val}',mine[c].astype(str).eq(str(val))))
 results=[]
 for k in [1,2,3]:
  for comb in itertools.combinations(preds,k):
   mask=pd.Series(True,index=mine.index); names=[]
   for name,p in comb: mask &= p; names.append(name)
   sub=mine[mask]
   if len(sub)<120: continue
   sm=summary(sub); score=sm['expansion_quality_rate']*0.55+sm['mfe10_rate']*0.25-sm['mae5_breach_rate']*0.2+min(sm['n'],600)/600
   results.append({'rule':' & '.join(names),'score':round(float(score),4),'summary':sm})
 results=sorted(results,key=lambda r:(r['summary']['expansion_quality_rate'],r['summary']['mfe20_avg'],r['summary']['n']),reverse=True)
 pd.DataFrame([{**{'rule':r['rule'],'score':r['score']},**r['summary']} for r in results[:300]]).to_csv(OUT/'v337_mfe_predicate_table_top300.csv',index=False)
 report={'version':'V337_MFE_MAE_CEILING_DIAGNOSIS_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source':rep['artifacts']['replayed_csv'],'family_reports':family_reports,'top_mfe_predicates':results[:30],'decision':'V337_DIAGNOSIS_DONE__NEXT_BUILD_EXPANSION_FILTER_BACKTEST' if results else 'V337_NO_MFE_PREDICATES_FOUND__SIGNAL_CEILING_CONFIRMED','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'base_mfe_mae':str(OUT/'v337_base_with_mfe_mae.csv'),'predicate_table':str(OUT/'v337_mfe_predicate_table_top300.csv')}}
 (OUT/'v337_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':report['decision'],'family_reports':family_reports,'top_mfe_predicates':results[:10]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
