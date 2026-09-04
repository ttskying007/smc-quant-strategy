#!/usr/bin/env python3
"""V340 no-write: broader exit expansion for the only production-coverage branch.

V339's closest production-coverage branch was OB_zone>=1.5: n=606, WR=95.38,
avg=6.52, min-year WR=90.14. V340 keeps that high-coverage signal fixed and
only broadens executable TP1+runner contracts to test whether exit architecture
can recover avg/min-year without changing signal generation.
"""
from __future__ import annotations
import importlib.util, itertools, json
from datetime import datetime
from pathlib import Path
import pandas as pd
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; V333=AUD/'v333_full_universe_rule_search_after_breadth_refresh_latest.json'
OUT=AUD/f"v340_ob_broad_exit_expansion_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v340_ob_broad_exit_expansion_latest.json'
spec=importlib.util.spec_from_file_location('v339','/root/.hermes/scripts/v25/v339_coverage_quality_frontier.py'); v339=importlib.util.module_from_spec(spec); spec.loader.exec_module(v339)

def main():
 OUT.mkdir(parents=True,exist_ok=True); rep=v339.load_json(V333,{}); df=pd.read_csv(rep['artifacts']['replayed_csv'],low_memory=False); df['entry_date']=df.entry_date.map(v339.dn)
 actual=pd.to_numeric(df.v333_actual_bars_since_entry,errors='coerce'); cur_base=actual.le(10)&(~df.v333_any_history_overlap.astype(str).str.lower().isin(['true','1']))
 n=lambda c: pd.to_numeric(df.get(c,pd.Series(index=df.index)),errors='coerce'); ss=lambda c: df.get(c,pd.Series('',index=df.index)).astype(str)
 weak=ss('v244_industry').isin(v339.WEAK); add=n('v244_ind_strong1_pct').ge(31.1688)|n('v236_br_above_ma20').ge(46.8561); base=df.v164_rule_pass.map(v339.boolish)&((~weak)|add)
 branches={
  'OB_zone>=1.0':base&n('v132_bull_count_3').ge(3)&n('v85_zone_width_pct').ge(1.0)&ss('poi_source').isin(['DEMAND_OB','OB+FVG']),
  'OB_zone>=1.25':base&n('v132_bull_count_3').ge(3)&n('v85_zone_width_pct').ge(1.25)&ss('poi_source').isin(['DEMAND_OB','OB+FVG']),
  'OB_zone>=1.5':base&n('v132_bull_count_3').ge(3)&n('v85_zone_width_pct').ge(1.5)&ss('poi_source').isin(['DEMAND_OB','OB+FVG']),
  'OB_zone>=2.0':base&n('v132_bull_count_3').ge(3)&n('v85_zone_width_pct').ge(2.0)&ss('poi_source').isin(['DEMAND_OB','OB+FVG']),
 }
 # Monkey-patch v339 replay only supports frac but no trail_8; keep supported trails.
 contracts=list(itertools.product([0.0,0.005,0.01,0.015],[4,5,6,8,10],[0.5,0.6,0.7,0.8],[15,20,25,30],[20,30,40],['be_only','lock_half_after_10']))
 cache={}; results=[]
 for bname,mask in branches.items():
  idx=df.index[mask.fillna(False)].tolist(); recs=df.loc[idx].to_dict('records')
  if len(idx)<150: continue
  for sl,tp1,frac,tp2,mh,trail in contracts:
   rows=[]
   for r in recs:
    rr={'symbol':r.get('symbol'),'entry_date':r.get('entry_date')}; rr.update(v339.replay(r,cache,sl,tp1,frac,tp2,mh,trail)); rows.append(rr)
   hist=[r for r in rows if v339.sf(r.get('actual_bars_since_entry'),-1)>=mh]
   cur=[r for r,ix in zip(rows,idx) if bool(cur_base.loc[ix])]
   hm=v339.metrics(hist); cm=v339.metrics([r for r in cur if r.get('status')=='CLOSED']); open_n=sum(r.get('status')=='OPEN_UNEXPIRED' for r in cur)
   pass_gate=v339.ok(hm) and open_n>=v339.GATE['current_open']
   score=(hm['avg']*0.9+(hm['wr']-90)*0.45+hm['min_year_wr']*0.03+min(hm['n'],570)/570-hm['micro']*0.5+open_n*0.05)
   results.append({'branch':bname,'sl_buf':sl,'tp1':tp1,'runner_frac':frac,'tp2':tp2,'max_hold':mh,'trail':trail,'score':round(float(score),4),'hist':hm,'current_closed':cm,'current_rows':len(cur),'current_open_rows':open_n,'pass_gate':pass_gate})
 results=sorted(results,key=lambda r:(r['pass_gate'],r['hist']['wr'],r['hist']['avg'],r['hist']['n']),reverse=True); passing=[r for r in results if r['pass_gate']]
 pd.DataFrame([{**{k:r[k] for k in ['branch','sl_buf','tp1','runner_frac','tp2','max_hold','trail','score','current_rows','current_open_rows','pass_gate']},**{f'hist_{k}':v for k,v in r['hist'].items() if not isinstance(v,dict)},**{f'cur_{k}':v for k,v in r['current_closed'].items() if not isinstance(v,dict)}} for r in results[:2000]]).to_csv(OUT/'v340_ob_exit_top2000.csv',index=False)
 frontier=[]
 for need in [570,700,900,1200]:
  cand=[r for r in results if r['hist']['n']>=need]
  if cand: frontier.append({'min_n':need,'best':cand[0]})
 report={'version':'V340_OB_BROAD_EXIT_EXPANSION_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source':rep['artifacts']['replayed_csv'],'gate':v339.GATE,'evaluated_rules':len(results),'passing_rule_count':len(passing),'top_passing':passing[:20],'coverage_frontier':frontier,'top_rules':results[:50],'decision':'V340_PRODUCTION_GATE_PASSED_SHADOW_ONLY_NO_WRITE' if passing else 'V340_OB_EXIT_EXPANSION_FAILS__AVG_OR_YEAR_CEILING_CONFIRMED','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'rule_table':str(OUT/'v340_ob_exit_top2000.csv')}}
 (OUT/'v340_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':report['decision'],'passing_rule_count':len(passing),'coverage_frontier':frontier,'top_rules':results[:8]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
