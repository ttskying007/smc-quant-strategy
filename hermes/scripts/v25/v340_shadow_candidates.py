#!/usr/bin/env python3
"""V340 no-write: current shadow candidates for V339 pass rule."""
from __future__ import annotations
import json, math
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; V333=AUD/'v333_full_universe_rule_search_after_breadth_refresh_latest.json'
OUT=AUD/f"v340_shadow_candidates_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v340_shadow_candidates_latest.json'
WEAK={'C27医药制造业','C32有色金属冶炼和压延加工业'}
RULE={'family':'F1_zone_ge_1.0204','tp1_abs':5.0,'tp1_frac':0.2,'runner_stop':'BE','max_hold':20,'same_bar_policy':'conservative','production_write':False}

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

def main()->None:
 OUT.mkdir(parents=True,exist_ok=True); rep=load_json(V333,{}); src=rep['artifacts']['replayed_csv']; df=pd.read_csv(src,low_memory=False); df['entry_date']=df.entry_date.map(dn)
 n=lambda c: pd.to_numeric(df.get(c,pd.Series(index=df.index)),errors='coerce')
 weak=df.v244_industry.astype(str).isin(WEAK); add=n('v244_ind_strong1_pct').ge(31.1688)|n('v236_br_above_ma20').ge(46.8561)
 base=df.v164_rule_pass.astype(str).str.lower().isin(['true','1'])&((~weak)|add)
 rule_mask=base&n('v132_bull_count_3').ge(3)&n('v132_reclaim_bull_body_pct').le(60)&n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2)&n('v85_zone_width_pct').ge(1.0204)
 actual=n('v333_actual_bars_since_entry'); current=actual.le(10)&(~df.v333_any_history_overlap.astype(str).str.lower().isin(['true','1']))
 rows=df[rule_mask&current].copy()
 rows['tp1_price']=pd.to_numeric(rows.entry_price,errors='coerce')*1.05
 rows['runner_stop_price']=pd.to_numeric(rows.entry_price,errors='coerce')
 rows['rule_family']=RULE['family']; rows['shadow_only']=True
 cols=[c for c in ['symbol','entry_date','entry_price','zone_low','zone_high','tp1_price','runner_stop_price','risk_pct','v85_zone_width_pct','market_state','poi_source','event_type','v132_bull_count_3','v132_reclaim_bull_body_pct','v132_post_zone_pullback_depth_pct_3','v244_industry','v244_ind_strong1_pct','v236_br_above_ma20','v333_actual_bars_since_entry','v333_any_history_overlap','rule_family','shadow_only'] if c in rows.columns]
 out=rows[cols].sort_values(['entry_date','symbol'],ascending=[False,True])
 # one preferred row per symbol for phone-readable action list: lower risk first, then latest entry.
 dedup=out.sort_values(['symbol','entry_date','risk_pct'],ascending=[True,False,True]).drop_duplicates('symbol',keep='first').sort_values(['entry_date','symbol'],ascending=[False,True])
 out.to_csv(OUT/'v340_shadow_candidates_all_rows.csv',index=False); dedup.to_csv(OUT/'v340_shadow_candidates_dedup.csv',index=False)
 report={'version':'V340_SHADOW_CANDIDATES_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source':src,'validated_rule_report':'/root/.hermes/smc_audit/v339_conservative_samebar_audit_latest.json','rule':RULE,'counts':{'all_current_rows':int(len(out)),'dedup_symbols':int(len(dedup)),'historical_rows_ge20':int((rule_mask&actual.ge(20)).sum())},'current_candidates':dedup.to_dict('records'),'artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'all_rows_csv':str(OUT/'v340_shadow_candidates_all_rows.csv'),'dedup_csv':str(OUT/'v340_shadow_candidates_dedup.csv')},'decision':'V340_SHADOW_CURRENT_LIST_READY__NO_PRODUCTION_WRITE'}
 (OUT/'v340_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':report['decision'],'counts':report['counts'],'current_candidates':report['current_candidates']},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
