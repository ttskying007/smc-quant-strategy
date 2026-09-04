#!/usr/bin/env python3
"""V334 no-write: numeric threshold frontier over V333 replayed universe.

V333 hand predicate search found no production-passing full-universe route. V334
mines numeric pre-entry fields with quantile thresholds and pairs/triples to test
whether the failure is merely coarse thresholds or a true signal-family ceiling.

Uses V333 replayed full universe; no production/frontend/watchlist writes.
"""
from __future__ import annotations
import itertools, json, math
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; V333=AUD/'v333_full_universe_rule_search_after_breadth_refresh_latest.json'
OUT=AUD/f"v334_numeric_threshold_frontier_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v334_numeric_threshold_frontier_latest.json'
GATE={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'min_year_wr':91.0,'micro':1.0,'t1':0,'current_open':1}
MAX_HOLD=10
WEAK={'C27医药制造业','C32有色金属冶炼和压延加工业'}

def dn(x:Any)->str:
 s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def boolish(x:Any)->bool: return str(x).strip().lower() in {'true','1','yes'}
def metrics(df:pd.DataFrame)->dict[str,Any]:
 closed=df[df.replay_status.astype(str).eq('CLOSED')].copy()
 if len(closed)==0: return {'n':0,'wr':0,'avg':0,'min_year_n':0,'year_wr':{},'min_year_wr':0,'micro':0,'t1':0,'exit_counts':{}}
 p=pd.to_numeric(closed.pnl_pct,errors='coerce'); yrs=closed.entry_date.astype(str).str[:4]; yc=yrs.value_counts().sort_index().to_dict(); ywr={str(y):round(float((p[yrs==y]>0).mean()*100),2) for y in sorted(yc)}
 return {'n':int(len(closed)),'wr':round(float((p>0).mean()*100),4),'avg':round(float(p.mean()),4),'min_year_n':int(min(yc.values()) if yc else 0),'year_counts':{str(k):int(v) for k,v in yc.items()},'year_wr':ywr,'min_year_wr':round(float(min(ywr.values()) if ywr else 0),2),'micro':round(float(((p>0)&(p<1)).mean()*100),4),'t1':int(closed.get('same_day_exit_violation',pd.Series(False,index=closed.index)).astype(str).str.lower().isin(['true','1']).sum()),'exit_counts':{str(k):int(v) for k,v in closed.exit_reason.astype(str).value_counts().to_dict().items()}}
def gate(m): return m['n']>=GATE['n'] and m['min_year_n']>=GATE['min_year_n'] and m['wr']>=GATE['wr'] and m['avg']>=GATE['avg'] and m['min_year_wr']>=GATE['min_year_wr'] and m['micro']<=GATE['micro'] and m['t1']==0

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 rep=json.loads(V333.read_text()); df=pd.read_csv(rep['artifacts']['replayed_csv'],low_memory=False); df['entry_date']=df.entry_date.map(dn)
 actual=pd.to_numeric(df.v333_actual_bars_since_entry,errors='coerce')
 hist_base=actual.ge(MAX_HOLD); cur_base=actual.le(MAX_HOLD)&(~df.v333_any_history_overlap.astype(str).str.lower().isin(['true','1']))
 weak=df.v244_industry.astype(str).isin(WEAK); add=pd.to_numeric(df.v244_ind_strong1_pct,errors='coerce').ge(31.1688)|pd.to_numeric(df.v236_br_above_ma20,errors='coerce').ge(46.8561)
 base=df.v164_rule_pass.map(boolish)&((~weak)|add)
 # Base families: broad high-n candidates from V333 plus variants. All are pre-entry fields.
 families={
  'base_v164_industry':base,
  'base_bull3':base & pd.to_numeric(df.v132_bull_count_3,errors='coerce').ge(3),
  'base_bull3_body60_pull2':base & pd.to_numeric(df.v132_bull_count_3,errors='coerce').ge(3)&pd.to_numeric(df.v132_reclaim_bull_body_pct,errors='coerce').le(60)&pd.to_numeric(df.v132_post_zone_pullback_depth_pct_3,errors='coerce').fillna(999).le(2),
  'base_bull3_zone2':base & pd.to_numeric(df.v132_bull_count_3,errors='coerce').ge(3)&pd.to_numeric(df.v85_zone_width_pct,errors='coerce').ge(2),
 }
 num_cols=[c for c in ['risk_pct','entry_chase_above_zone_pct','v85_zone_width_pct','v132_reclaim_bull_body_pct','v132_reclaim_close_pos_pct','v132_reclaim_bull_body_atr','v132_post_zone_pullback_depth_pct_1','v132_post_zone_pullback_depth_pct_2','v132_post_zone_pullback_depth_pct_3','v132_bull_count_3','v236_all_strong1_pct','v236_br_above_ma20','v244_ind_up1_pct','v244_ind_strong1_pct','v244_ind_mean_ret1','source_gap_atr','source_mid_body_atr','reclaim_close_above_zone_pct','touch_to_reclaim_bars'] if c in df.columns]
 preds=[]
 for c in num_cols:
  s=pd.to_numeric(df[c],errors='coerce')
  vals=s[hist_base & base & s.notna()]
  if len(vals)<200: continue
  qs=sorted(set(round(float(x),4) for x in vals.quantile([.1,.2,.3,.4,.5,.6,.7,.8,.9]).dropna()))
  for q in qs:
   le=s.le(q); ge=s.ge(q)
   # keep predicates neither tiny nor universal on base historical rows
   for op,mask in [(f'{c}<={q}',le),(f'{c}>={q}',ge)]:
    cnt=int((mask & hist_base & base).sum())
    if 250<=cnt<=6000: preds.append((op,mask.fillna(False)))
 cats=[]
 for c in ['market_state','poi_source','event_type','v132_reclaim_class']:
  if c in df.columns:
   for val,cnt in df.loc[hist_base & base,c].astype(str).value_counts().items():
    if 250<=cnt<=6000: cats.append((f'{c}=={val}',df[c].astype(str).eq(str(val))))
 preds.extend(cats)
 # de-duplicate equivalent names
 seen=set(); uniq=[]
 for name,mask in preds:
  if name not in seen:
   seen.add(name); uniq.append((name,mask))
 preds=uniq
 results=[]
 for fam_name,fam_mask in families.items():
  fam_mask=fam_mask.fillna(False)
  # evaluate base + singles, then only top singleton predicates for pairs/triples.
  # This avoids O(P^3) blow-up while still testing the strongest numeric frontiers.
  viable=[]
  for name,mask in preds:
   m=fam_mask&mask
   if int((m&hist_base).sum())>=250:
    h=df[m&hist_base]; hm=metrics(h)
    # prioritize predicates that improve WR/avg without collapsing sample size
    s=(hm['wr']-88)*min(hm['n'],1200)/1200 + hm['avg']*.35 + hm['min_year_wr']*.02 - hm['micro']*.5
    viable.append((float(s),name,mask))
  viable=sorted(viable, key=lambda x:x[0], reverse=True)[:36]
  viable=[(name,mask) for _,name,mask in viable]
  for k in [0,1,2,3]:
   iterable=[()] if k==0 else itertools.combinations(viable,k)
   for comb in iterable:
    mask=fam_mask.copy(); names=[]
    for name,p in comb:
     mask &= p; names.append(name)
    h=df[mask&hist_base]; cur=df[mask&cur_base]
    hm=metrics(h); open_n=int((cur.replay_status.astype(str)=='OPEN_UNEXPIRED').sum()) if len(cur) else 0; cm=metrics(cur[cur.replay_status.astype(str).eq('CLOSED')])
    if hm['n']<250: continue
    score=(hm['wr']-90)*min(hm['n'],1000)/1000+hm['avg']*.45+hm['min_year_wr']*.03-open_n*.0-hm['micro']*.5
    results.append({'family':fam_name,'rule':fam_name+(' & '+ ' & '.join(names) if names else ''),'score':round(float(score),4),'hist':hm,'current_rows':int(len(cur)),'current_open_rows':open_n,'current_closed':cm,'pass_gate':gate(hm) and open_n>=GATE['current_open']})
 results=sorted(results,key=lambda r:(r['pass_gate'],r['hist']['wr'],r['hist']['avg'],r['hist']['n'],r['current_open_rows']),reverse=True)
 passing=[r for r in results if r['pass_gate']]
 top=passing[0] if passing else results[0]
 # materialize top rows
 mask=families[top['family']].copy().fillna(False)
 parts=top['rule'].split(' & ')[1:]
 predmap={name:mask0 for name,mask0 in preds}
 for part in parts:
  if part in predmap: mask &= predmap[part]
 df[mask&hist_base].to_csv(OUT/'v334_top_historical_rows.csv',index=False); df[mask&cur_base].to_csv(OUT/'v334_top_current_rows.csv',index=False)
 pd.DataFrame([{**{'family':r['family'],'rule':r['rule'],'score':r['score'],'current_rows':r['current_rows'],'current_open_rows':r['current_open_rows'],'pass_gate':r['pass_gate']},**{f"hist_{k}":v for k,v in r['hist'].items() if not isinstance(v,dict)},**{f"cur_closed_{k}":v for k,v in r['current_closed'].items() if not isinstance(v,dict)}} for r in results[:500]]).to_csv(OUT/'v334_rule_table_top500.csv',index=False)
 report={'version':'V334_NUMERIC_THRESHOLD_FRONTIER_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source':rep['artifacts']['replayed_csv'],'gate':GATE,'predicate_count':len(preds),'evaluated_rules':len(results),'passing_rule_count':len(passing),'top_passing_rules':passing[:20],'top_rules':results[:40],'decision':'V334_PASSING_FULL_UNIVERSE_RULE_FOUND__SHADOW_ONLY_NO_WRITE' if passing else 'V334_NO_NUMERIC_THRESHOLD_RULE_PASSES__SIGNAL_FAMILY_CEILING_CONFIRMED','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'top_hist':str(OUT/'v334_top_historical_rows.csv'),'top_current':str(OUT/'v334_top_current_rows.csv'),'rule_table':str(OUT/'v334_rule_table_top500.csv')}}
 (OUT/'v334_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':report['decision'],'predicate_count':len(preds),'evaluated_rules':len(results),'passing_rule_count':len(passing),'top_passing':passing[:5],'top_rules':results[:10]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
