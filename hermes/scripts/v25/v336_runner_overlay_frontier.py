#!/usr/bin/env python3
"""V336 no-write: TP1+runner overlay frontier.

V335 proved fixed single-target exits cannot satisfy both WR and Avg. The next
different direction is a two-leg SMC execution: lock TP1 quickly, then let a
runner seek the real liquidity expansion with BE/structural protection. This
explicitly tests whether the avg-PnL gap is an exit architecture issue rather
than a signal-entry issue.

Rules are pre-entry only; no production/frontend/watchlist writes.
"""
from __future__ import annotations

import itertools, json, math
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; KDIR=ROOT/'kline_cache'; V333=AUD/'v333_full_universe_rule_search_after_breadth_refresh_latest.json'
OUT=AUD/f"v336_runner_overlay_frontier_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v336_runner_overlay_frontier_latest.json'
GATE={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'min_year_wr':91.0,'micro':1.0,'t1':0,'current_open':1}
WEAK={'C27医药制造业','C32有色金属冶炼和压延加工业'}; MAX_ACTIONABLE=10

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
 out=[]; p=KDIR/f"{sym.replace('.','_')}_daily_750.json"
 for b in load_json(p,[]):
  d=dn(b.get('t') or b.get('date')); o,h,l,c=sf(b.get('o')),sf(b.get('h')),sf(b.get('l')),sf(b.get('c'))
  if d and None not in (o,h,l,c): out.append({'date':d,'o':float(o),'h':float(h),'l':float(l),'c':float(c)})
 return sorted(out,key=lambda r:r['date'])

def replay_runner(r:dict[str,Any], cache:dict[str,list[dict[str,Any]]], sl_buf:float, tp1_r:float, runner_frac:float, tp2_r:float, max_hold:int, trail_mode:str)->dict[str,Any]:
 sym,ed=str(r.get('symbol') or ''),dn(r.get('entry_date')); ep,zl=sf(r.get('entry_price')),sf(r.get('zone_low') or r.get('dz_low'))
 if sym not in cache: cache[sym]=bars(sym)
 b0=cache[sym]; dates=[b['date'] for b in b0]; actual=sum(1 for d in dates if d>ed) if ed in dates else None
 out={'actual_bars_since_entry':actual,'status':'FIELD_MISSING'}
 if not sym or not ed or ep is None or zl is None or ep<=0 or zl<=0: return out
 sl0=zl*(1-sl_buf)
 if sl0>=ep: sl0=ep*0.985
 risk=ep-sl0; tp1=ep+risk*tp1_r; tp2=ep+risk*tp2_r; path=[b for b in b0 if b['date']>ed]
 got_tp1=False; pnl1=0.0; runner_sl=sl0; peak=ep; tp1_date=''; exit_reason='OPEN'; exit_date=''; runner_px=None
 for i,b in enumerate(path,1):
  # T+1 path only because path excludes entry date.
  if not got_tp1:
   # conservative: if SL and TP1 same day before tp1 state, count SL for whole position.
   if b['l']<=sl0:
    pnl=(sl0/ep-1)*100; return {'status':'CLOSED','exit_reason':'SL_BEFORE_TP1','exit_date':b['date'],'hold_bars':i,'pnl_pct':pnl,'same_day_exit_violation':False,'tp1_hit':False,'tp1_date':'','runner_exit_price':sl0,'sl':sl0,'tp1':tp1,'tp2':tp2,'actual_bars_since_entry':actual}
   if b['h']>=tp1:
    got_tp1=True; tp1_date=b['date']; pnl1=(tp1/ep-1)*100*(1-runner_frac); runner_sl=ep  # BE after TP1
    peak=max(peak,b['h'])
   elif i>=max_hold:
    pnl=(b['c']/ep-1)*100; return {'status':'CLOSED','exit_reason':'TIME_NO_TP1','exit_date':b['date'],'hold_bars':i,'pnl_pct':pnl,'same_day_exit_violation':False,'tp1_hit':False,'tp1_date':'','runner_exit_price':b['c'],'sl':sl0,'tp1':tp1,'tp2':tp2,'actual_bars_since_entry':actual}
   continue
  # runner leg after tp1; same bar after TP1 uses conservative low check only after TP1 state.
  peak=max(peak,b['h'])
  if trail_mode=='be_only':
   runner_sl=ep
  elif trail_mode=='half_r_after_2r':
   if peak>=ep+2*risk: runner_sl=max(runner_sl, ep+0.5*risk)
  elif trail_mode=='one_r_after_3r':
   if peak>=ep+3*risk: runner_sl=max(runner_sl, ep+1.0*risk)
  elif trail_mode=='close_trail_8pct':
   runner_sl=max(runner_sl, peak*0.92)
  if b['l']<=runner_sl:
   runner_px=runner_sl; exit_reason='RUNNER_SL'; exit_date=b['date']; break
  if b['h']>=tp2:
   runner_px=tp2; exit_reason='TP2'; exit_date=b['date']; break
  if i>=max_hold:
   runner_px=b['c']; exit_reason='TIME_AFTER_TP1'; exit_date=b['date']; break
 if got_tp1 and runner_px is not None:
  pnl=pnl1 + (runner_px/ep-1)*100*runner_frac
  return {'status':'CLOSED','exit_reason':exit_reason,'exit_date':exit_date,'hold_bars':i,'pnl_pct':pnl,'same_day_exit_violation':False,'tp1_hit':True,'tp1_date':tp1_date,'runner_exit_price':runner_px,'sl':sl0,'tp1':tp1,'tp2':tp2,'actual_bars_since_entry':actual}
 if got_tp1 and path:
  latest=path[-1]
  pnl=pnl1 + (latest['c']/ep-1)*100*runner_frac
  return {'status':'OPEN_UNEXPIRED','exit_reason':'OPEN_AFTER_TP1_MTM','latest_date':latest['date'],'latest_close':latest['c'],'pnl_pct':pnl,'tp1_hit':True,'tp1_date':tp1_date,'runner_exit_price':latest['c'],'sl':sl0,'tp1':tp1,'tp2':tp2,'actual_bars_since_entry':actual}
 if path:
  latest=path[-1]
  return {'status':'OPEN_UNEXPIRED','exit_reason':'OPEN_NO_TP1','latest_date':latest['date'],'latest_close':latest['c'],'pnl_pct':(latest['c']/ep-1)*100,'tp1_hit':False,'tp1_date':'','runner_exit_price':latest['c'],'sl':sl0,'tp1':tp1,'tp2':tp2,'actual_bars_since_entry':actual}
 return out

def metrics(rows:list[dict[str,Any]])->dict[str,Any]:
 closed=[r for r in rows if r.get('status')=='CLOSED']
 if not closed: return {'n':0,'wr':0,'avg':0,'min_year_n':0,'year_counts':{},'year_wr':{},'min_year_wr':0,'micro':0,'t1':0,'exit_counts':{},'tp1_rate':0}
 p=pd.Series([sf(r.get('pnl_pct'),0) for r in closed]); yrs=pd.Series([dn(r.get('entry_date'))[:4] for r in closed]); yc={k:v for k,v in yrs.value_counts().sort_index().to_dict().items() if str(k)>='2023'}; ywr={str(y):round(float((p[yrs==y]>0).mean()*100),2) for y in sorted(yc)}
 return {'n':len(closed),'wr':round(float((p>0).mean()*100),4),'avg':round(float(p.mean()),4),'min_year_n':int(min(yc.values()) if yc else 0),'year_counts':{str(k):int(v) for k,v in yc.items()},'year_wr':ywr,'min_year_wr':round(float(min(ywr.values()) if ywr else 0),2),'micro':round(float(((p>0)&(p<1)).mean()*100),4),'t1':int(sum(bool(r.get('same_day_exit_violation')) for r in closed)),'exit_counts':{str(k):int(v) for k,v in pd.Series([r.get('exit_reason') for r in closed]).value_counts().to_dict().items()},'tp1_rate':round(float(pd.Series([bool(r.get('tp1_hit')) for r in closed]).mean()*100),4)}
def gate(m): return m['n']>=GATE['n'] and m['min_year_n']>=GATE['min_year_n'] and m['wr']>=GATE['wr'] and m['avg']>=GATE['avg'] and m['min_year_wr']>=GATE['min_year_wr'] and m['micro']<=GATE['micro'] and m['t1']==0

def main():
 OUT.mkdir(parents=True,exist_ok=True); rep=load_json(V333,{}); df=pd.read_csv(rep['artifacts']['replayed_csv'],low_memory=False); df['entry_date']=df.entry_date.map(dn)
 actual=pd.to_numeric(df.v333_actual_bars_since_entry,errors='coerce'); hist_base=actual.ge(MAX_ACTIONABLE); cur_base=actual.le(MAX_ACTIONABLE)&(~df.v333_any_history_overlap.astype(str).str.lower().isin(['true','1']))
 weak=df.v244_industry.astype(str).isin(WEAK); add=pd.to_numeric(df.v244_ind_strong1_pct,errors='coerce').ge(31.1688)|pd.to_numeric(df.v236_br_above_ma20,errors='coerce').ge(46.8561); base=df.v164_rule_pass.map(boolish)&((~weak)|add)
 n=lambda c: pd.to_numeric(df.get(c,pd.Series(index=df.index)),errors='coerce'); ss=lambda c: df.get(c,pd.Series('',index=df.index)).astype(str)
 families={
  'F1_bull3_body60_pull2':base&n('v132_bull_count_3').ge(3)&n('v132_reclaim_bull_body_pct').le(60)&n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2),
  'F4_bull3_body60_pull2_chase3':base&n('v132_bull_count_3').ge(3)&n('v132_reclaim_bull_body_pct').le(60)&n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2)&n('entry_chase_above_zone_pct').le(3),
  'F6_bull3_body60_pull2_reclaim_le2':base&n('v132_bull_count_3').ge(3)&n('v132_reclaim_bull_body_pct').le(60)&n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2)&n('reclaim_close_above_zone_pct').le(2),
  'F2_bull3_zone2_ob':base&n('v132_bull_count_3').ge(3)&n('v85_zone_width_pct').ge(2)&ss('poi_source').isin(['DEMAND_OB','OB+FVG']),
 }
 # Focused grid after V335: high-WR contracts need avg expansion, so test only
 # fast TP1 + meaningful runner variants. Wider exhaustive grids timed out and
 # mostly repeat dominated low-R outcomes.
 grid=list(itertools.product([0.005,0.01],[1.0,1.2],[0.3,0.5],[3,4,5],[20,30],['be_only','half_r_after_2r','close_trail_8pct']))
 cache={}; results=[]
 for fname,mask in families.items():
  idx=df.index[mask.fillna(False)].tolist(); recs=df.loc[idx].to_dict('records')
  if len(idx)<250: continue
  for sl_buf,tp1_r,runner_frac,tp2_r,max_hold,trail in grid:
   rep_rows=[]
   for r in recs:
    rr={'symbol':r.get('symbol'),'entry_date':r.get('entry_date')}; rr.update(replay_runner(r,cache,sl_buf,tp1_r,runner_frac,tp2_r,max_hold,trail)); rep_rows.append(rr)
   hist=[r for r,ix in zip(rep_rows,idx) if bool(hist_base.loc[ix])]; cur=[r for r,ix in zip(rep_rows,idx) if bool(cur_base.loc[ix])]
   hm=metrics(hist); cm=metrics([r for r in cur if r.get('status')=='CLOSED']); open_n=sum(r.get('status')=='OPEN_UNEXPIRED' for r in cur)
   score=(hm['wr']-90)*min(hm['n'],1200)/1200+hm['avg']*.7+hm['min_year_wr']*.03-hm['micro']*.4+open_n*.05
   results.append({'family':fname,'sl_buf':sl_buf,'tp1_r':tp1_r,'runner_frac':runner_frac,'tp2_r':tp2_r,'max_hold':max_hold,'trail':trail,'score':round(float(score),4),'hist':hm,'current_closed':cm,'current_rows':len(cur),'current_open_rows':open_n,'pass_gate':gate(hm) and open_n>=GATE['current_open']})
 results=sorted(results,key=lambda r:(r['pass_gate'],r['hist']['wr'],r['hist']['avg'],r['hist']['n'],r['current_open_rows']),reverse=True); passing=[r for r in results if r['pass_gate']]
 pd.DataFrame([{**{k:r[k] for k in ['family','sl_buf','tp1_r','runner_frac','tp2_r','max_hold','trail','score','current_rows','current_open_rows','pass_gate']},**{f"hist_{k}":v for k,v in r['hist'].items() if not isinstance(v,dict)},**{f"cur_{k}":v for k,v in r['current_closed'].items() if not isinstance(v,dict)}} for r in results[:800]]).to_csv(OUT/'v336_runner_rule_table_top800.csv',index=False)
 report={'version':'V336_RUNNER_OVERLAY_FRONTIER_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source':rep['artifacts']['replayed_csv'],'gate':GATE,'evaluated_rules':len(results),'passing_rule_count':len(passing),'top_passing_rules':passing[:20],'top_rules':results[:40],'decision':'V336_RUNNER_OVERLAY_RECOVERS_GATE__SHADOW_ONLY_NO_WRITE' if passing else 'V336_NO_RUNNER_OVERLAY_RECOVERS_GATE__ENTRY_SIGNAL_FAMILY_CEILING_CONFIRMED','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'rule_table':str(OUT/'v336_runner_rule_table_top800.csv')}}
 (OUT/'v336_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':report['decision'],'passing_rule_count':len(passing),'top_passing':passing[:5],'top_rules':results[:10]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
