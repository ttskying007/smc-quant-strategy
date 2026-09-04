#!/usr/bin/env python3
"""V343 no-write: formal production gate for BSL room + deep runner.

Formalizes the V342 continuation finding: F1/OB/FVG seed with pre-entry BSL60
room >=10% and position in lower half of 60-bar range, plus executable deep
runner contract. Uses conservative same-bar TP1->BE handling and strict T+1.
No production/frontend/watchlist writes.
"""
from __future__ import annotations
import json, math
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; KDIR=ROOT/'kline_cache'; V333=AUD/'v333_full_universe_rule_search_after_breadth_refresh_latest.json'
OUT=AUD/f"v343_bsl_room_deep_runner_formal_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v343_bsl_room_deep_runner_latest.json'
WEAK={'C27医药制造业','C32有色金属冶炼和压延加工业'}
GATE={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'min_year_wr':91.0,'micro':1.0,'t1':0,'current_open':1}
RULE={'name':'V343_BSL60_ROOM10_POS60_LOWER_HALF_DEEP_RUNNER','bsl60_room_min_pct':10.0,'pos60_max_pct':50.0,'tp1_pct':4.0,'runner_frac':0.7,'tp2_pct':60.0,'max_hold':50,'sl_buf':0.01,'runner_stop':'BE','same_bar_policy':'TP1 then runner BE if low crosses BE','seed':'v164 pass + industry gate + bull_count_3>=3 + POI in OB/FVG/FVG_Demand'}

def dn(x:Any)->str:
 s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def sf(x:Any,d=None):
 try:
  if x is None or x=='': return d
  v=float(x); return d if math.isnan(v) or math.isinf(v) else v
  return v
 except Exception: return d
def boolish(x): return str(x).strip().lower() in {'true','1','yes'}
def load_json(p:Path,d):
 try: return json.loads(p.read_text())
 except Exception: return d
def bars(sym:str):
 out=[]; p=KDIR/f"{sym.replace('.','_')}_daily_750.json"
 for b in load_json(p,[]):
  d=dn(b.get('t') or b.get('date')); o,h,l,c=sf(b.get('o')),sf(b.get('h')),sf(b.get('l')),sf(b.get('c'))
  if d and None not in (o,h,l,c): out.append((d,float(o),float(h),float(l),float(c)))
 return sorted(out)
def features(sym,ed,ep,cache):
 if sym not in cache: cache[sym]=bars(sym)
 b=cache[sym]; bi=next((i for i,x in enumerate(b) if x[0]==ed),None)
 if bi is None or ep is None or bi<65: return None,[x for x in b if x[0]>ed][:60]
 pre=b[:bi]; h60=max(x[2] for x in pre[-60:]); l60=min(x[3] for x in pre[-60:])
 return {'bsl60_room_pct':(h60/ep-1)*100,'pos60_pct':(ep-l60)/(h60-l60)*100 if h60>l60 else None,'prior60_high':h60,'prior60_low':l60},[x for x in b if x[0]>ed][:60]
def replay(path,ep,zl):
 sl=zl*(1-RULE['sl_buf'])
 if sl>=ep: sl=ep*.985
 t1=ep*(1+RULE['tp1_pct']/100); t2=ep*(1+RULE['tp2_pct']/100); got=False; pnl1=0.0; rsl=sl
 for i,(_,_,h,l,c) in enumerate(path[:RULE['max_hold']],1):
  if not got:
   if l<=sl: return (sl/ep-1)*100,'SL_BEFORE_TP1',i,False
   if h>=t1:
    got=True; pnl1=RULE['tp1_pct']*(1-RULE['runner_frac']); rsl=ep
    if l<=rsl: return pnl1,'TP1_BE_SAME_BAR',i,True
   elif i>=RULE['max_hold']: return (c/ep-1)*100,'TIME_NO_TP1',i,False
   continue
  if l<=rsl: return pnl1,'RUNNER_BE',i,True
  if h>=t2: return pnl1+RULE['tp2_pct']*RULE['runner_frac'],'TP2_ABS',i,True
  if i>=RULE['max_hold']: return pnl1+(c/ep-1)*100*RULE['runner_frac'],'TIME_AFTER_TP1',i,True
 return None,'OPEN',None,got
def calc_metrics(rows):
 closed=[r for r in rows if r['status']=='CLOSED']; p=pd.Series([r['pnl_pct'] for r in closed],dtype='float64'); y=pd.Series([r['entry_date'][:4] for r in closed])
 yc={str(k):int(v) for k,v in y[y>='2023'].value_counts().sort_index().to_dict().items()}; ywr={str(k):round(float((p[y==k]>0).mean()*100),2) for k in sorted(yc)}
 return {'n':len(closed),'wr':round(float((p>0).mean()*100),4),'avg':round(float(p.mean()),4),'micro':round(float(((p>0)&(p<1)).mean()*100),4),'min_year_n':int(min(yc.values()) if yc else 0),'year_counts':yc,'year_wr':ywr,'min_year_wr':round(float(min(ywr.values()) if ywr else 0),2),'t1':0,'exit_counts':{str(k):int(v) for k,v in pd.Series([r['exit_reason'] for r in closed]).value_counts().to_dict().items()},'tp1_rate':round(float(pd.Series([r['tp1_hit'] for r in closed]).mean()*100),4)}
def gate(m): return m['n']>=GATE['n'] and m['min_year_n']>=GATE['min_year_n'] and m['wr']>=GATE['wr'] and m['avg']>=GATE['avg'] and m['min_year_wr']>=GATE['min_year_wr'] and m['micro']<=GATE['micro'] and m['t1']==0

def main():
 OUT.mkdir(parents=True,exist_ok=True); rep=load_json(V333,{}); df=pd.read_csv(rep['artifacts']['replayed_csv'],low_memory=False); df['entry_date']=df.entry_date.map(dn)
 n=lambda c: pd.to_numeric(df.get(c,pd.Series(index=df.index)),errors='coerce'); ss=lambda c: df.get(c,pd.Series('',index=df.index)).astype(str)
 weak=ss('v244_industry').isin(WEAK); add=n('v244_ind_strong1_pct').ge(31.1688)|n('v236_br_above_ma20').ge(46.8561)
 seed=ss('v164_rule_pass').map(boolish)&((~weak)|add)&n('v132_bull_count_3').ge(3)&(ss('poi_source').isin(['DEMAND_OB','OB+FVG'])|ss('poi_source').eq('FVG_Demand'))
 curmask=n('v333_actual_bars_since_entry').le(10)&(~ss('v333_any_history_overlap').str.lower().isin(['true','1']))
 cache={}; rows=[]
 for r in df[seed.fillna(False)].itertuples():
  sym=str(r.symbol); ed=dn(r.entry_date); ep=sf(r.entry_price); zl=sf(r.zone_low); actual=sf(getattr(r,'v333_actual_bars_since_entry',None))
  feat,path=features(sym,ed,ep,cache)
  if not feat or feat['bsl60_room_pct']<RULE['bsl60_room_min_pct'] or feat['pos60_pct']>RULE['pos60_max_pct']: continue
  pnl,reason,hold,tp1_hit=replay(path,ep,zl)
  status='OPEN_UNEXPIRED' if pnl is None else 'CLOSED'
  row={'symbol':sym,'entry_date':ed,'entry_price':ep,'zone_low':zl,'zone_high':sf(getattr(r,'zone_high',None)),'poi_source':str(r.poi_source),'market_state':str(r.market_state),'event_type':str(r.event_type),'actual_bars_since_entry':actual,'is_current':bool(curmask.loc[r.Index]),**feat,'pnl_pct':pnl,'exit_reason':reason,'hold_bars':hold,'tp1_hit':tp1_hit,'status':status,'same_day_exit_violation':False}
  rows.append(row)
 hist=[r for r in rows if r['actual_bars_since_entry'] is not None and r['actual_bars_since_entry']>=RULE['max_hold']]
 cur=[r for r in rows if r['is_current']]
 metrics=calc_metrics(hist); current_closed=calc_metrics([r for r in cur if r['status']=='CLOSED']) if any(r['status']=='CLOSED' for r in cur) else {'n':0,'wr':0,'avg':0,'micro':0,'min_year_n':0,'year_counts':{},'year_wr':{},'min_year_wr':0,'t1':0,'exit_counts':{},'tp1_rate':0}
 open_n=sum(r['status']=='OPEN_UNEXPIRED' for r in cur); pass_gate=gate(metrics) and open_n>=GATE['current_open']
 pd.DataFrame(rows).to_csv(OUT/'v343_all_replayed_rows.csv',index=False); pd.DataFrame(hist).to_csv(OUT/'v343_hist_rows.csv',index=False); pd.DataFrame(cur).to_csv(OUT/'v343_current_shadow_rows.csv',index=False)
 report={'version':'V343_BSL_ROOM_DEEP_RUNNER_FORMAL_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source':rep['artifacts']['replayed_csv'],'gate':GATE,'rule':RULE,'row_counts':{'all_rule_rows':len(rows),'hist_eligible':len(hist),'current_rows':len(cur),'current_open_rows':open_n},'metrics':metrics,'current_closed':current_closed,'pass_gate':pass_gate,'decision':'V343_PRODUCTION_GATE_PASSED__SHADOW_ONLY_NO_WRITE' if pass_gate else 'V343_FAIL','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'all_rows_csv':str(OUT/'v343_all_replayed_rows.csv'),'hist_csv':str(OUT/'v343_hist_rows.csv'),'current_csv':str(OUT/'v343_current_shadow_rows.csv')}}
 (OUT/'v343_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':report['decision'],'pass_gate':pass_gate,'row_counts':report['row_counts'],'metrics':metrics,'current_closed':current_closed},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
