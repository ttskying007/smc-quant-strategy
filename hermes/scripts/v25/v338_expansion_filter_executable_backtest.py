#!/usr/bin/env python3
"""V338 no-write: executable backtest for V337 expansion predicates.

V337 showed some pre-entry predicates have enough 20-bar MFE to support the
average-PnL target, but the samples were smaller and MFE is not executable. V338
replays those predicates with concrete T+1 exits: absolute TP and TP1+runner.
No production/frontend/watchlist writes.
"""
from __future__ import annotations
import itertools, json, math
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; KDIR=ROOT/'kline_cache'
V333=AUD/'v333_full_universe_rule_search_after_breadth_refresh_latest.json'
OUT=AUD/f"v338_expansion_filter_executable_backtest_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
LATEST=AUD/'v338_expansion_filter_executable_backtest_latest.json'
WEAK={'C27医药制造业','C32有色金属冶炼和压延加工业'}
PROD_GATE={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'min_year_wr':91.0,'micro':1.0,'t1':0,'current_open':1}
RESEARCH_GATE={'n':120,'min_year_n':15,'wr':93.0,'avg':7.6,'min_year_wr':90.0,'micro':1.0,'t1':0}

def dn(x:Any)->str:
 s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit())
 return s[:8] if len(s)>=8 else ''
def sf(x:Any, default=None):
 try:
  if x is None or x=='': return default
  v=float(x); return default if math.isnan(v) or math.isinf(v) else v
  return v
 except Exception:
  return default
def boolish(x:Any)->bool: return str(x).strip().lower() in {'true','1','yes'}
def load_json(p:Path, default:Any)->Any:
 try: return json.loads(p.read_text())
 except Exception: return default

def load_bars(sym:str)->list[dict[str,Any]]:
 arr=[]; p=KDIR/f"{sym.replace('.','_')}_daily_750.json"
 for b in load_json(p,[]):
  d=dn(b.get('t') or b.get('date')); o,h,l,c=sf(b.get('o')),sf(b.get('h')),sf(b.get('l')),sf(b.get('c'))
  if d and None not in (o,h,l,c): arr.append({'date':d,'o':float(o),'h':float(h),'l':float(l),'c':float(c)})
 return sorted(arr,key=lambda r:r['date'])

def stops(r:dict[str,Any], sl_buf:float)->tuple[float|None,float|None,float|None]:
 ep=sf(r.get('entry_price')); zl=sf(r.get('zone_low') or r.get('dz_low'))
 if ep is None or zl is None or ep<=0 or zl<=0: return None,None,None
 sl=zl*(1-sl_buf)
 if sl>=ep: sl=ep*0.985
 return ep,sl,ep-sl

def replay_abs(r:dict[str,Any], cache:dict[str,list[dict[str,Any]]], sl_buf:float, tp_pct:float, max_hold:int)->dict[str,Any]:
 sym,ed=str(r.get('symbol') or ''),dn(r.get('entry_date'))
 if sym not in cache: cache[sym]=load_bars(sym)
 b0=cache[sym]; dates=[b['date'] for b in b0]; actual=sum(1 for d in dates if d>ed) if ed in dates else None
 ep,sl,risk=stops(r,sl_buf); out={'actual_bars_since_entry':actual,'status':'FIELD_MISSING'}
 if not sym or not ed or ep is None or sl is None: return out
 tp=ep*(1+tp_pct/100); path=[b for b in b0 if b['date']>ed]
 for i,b in enumerate(path,1):
  if b['l']<=sl: return {'status':'CLOSED','exit_reason':'SL','exit_date':b['date'],'hold_bars':i,'pnl_pct':(sl/ep-1)*100,'same_day_exit_violation':False,'sl':sl,'tp':tp,'actual_bars_since_entry':actual}
  if b['h']>=tp: return {'status':'CLOSED','exit_reason':'TP_ABS','exit_date':b['date'],'hold_bars':i,'pnl_pct':tp_pct,'same_day_exit_violation':False,'sl':sl,'tp':tp,'actual_bars_since_entry':actual}
  if i>=max_hold: return {'status':'CLOSED','exit_reason':'TIME','exit_date':b['date'],'hold_bars':i,'pnl_pct':(b['c']/ep-1)*100,'same_day_exit_violation':False,'sl':sl,'tp':tp,'actual_bars_since_entry':actual}
 if path:
  return {'status':'OPEN_UNEXPIRED','exit_reason':'OPEN','latest_date':path[-1]['date'],'latest_close':path[-1]['c'],'pnl_pct':(path[-1]['c']/ep-1)*100,'sl':sl,'tp':tp,'actual_bars_since_entry':actual}
 return out

def replay_runner(r:dict[str,Any], cache:dict[str,list[dict[str,Any]]], sl_buf:float, tp1_pct:float, runner_frac:float, tp2_pct:float, max_hold:int, trail:str)->dict[str,Any]:
 sym,ed=str(r.get('symbol') or ''),dn(r.get('entry_date'))
 if sym not in cache: cache[sym]=load_bars(sym)
 b0=cache[sym]; dates=[b['date'] for b in b0]; actual=sum(1 for d in dates if d>ed) if ed in dates else None
 ep,sl,risk=stops(r,sl_buf); out={'actual_bars_since_entry':actual,'status':'FIELD_MISSING'}
 if not sym or not ed or ep is None or sl is None or risk is None: return out
 tp1=ep*(1+tp1_pct/100); tp2=ep*(1+tp2_pct/100); path=[b for b in b0 if b['date']>ed]
 got=False; pnl1=0.0; peak=ep; rsl=sl; tp1_date=''
 for i,b in enumerate(path,1):
  if not got:
   if b['l']<=sl: return {'status':'CLOSED','exit_reason':'SL_BEFORE_TP1','exit_date':b['date'],'hold_bars':i,'pnl_pct':(sl/ep-1)*100,'same_day_exit_violation':False,'tp1_hit':False,'sl':sl,'tp1':tp1,'tp2':tp2,'actual_bars_since_entry':actual}
   if b['h']>=tp1:
    got=True; tp1_date=b['date']; pnl1=tp1_pct*(1-runner_frac); peak=max(peak,b['h']); rsl=ep
   elif i>=max_hold:
    return {'status':'CLOSED','exit_reason':'TIME_NO_TP1','exit_date':b['date'],'hold_bars':i,'pnl_pct':(b['c']/ep-1)*100,'same_day_exit_violation':False,'tp1_hit':False,'sl':sl,'tp1':tp1,'tp2':tp2,'actual_bars_since_entry':actual}
   continue
  peak=max(peak,b['h'])
  if trail=='be_only': rsl=ep
  elif trail=='trail_8pct': rsl=max(rsl,peak*0.92)
  elif trail=='lock_half_after_10':
   if peak>=ep*1.10: rsl=max(rsl,ep*1.04)
  if b['l']<=rsl:
   return {'status':'CLOSED','exit_reason':'RUNNER_SL','exit_date':b['date'],'hold_bars':i,'pnl_pct':pnl1+(rsl/ep-1)*100*runner_frac,'same_day_exit_violation':False,'tp1_hit':True,'tp1_date':tp1_date,'sl':sl,'tp1':tp1,'tp2':tp2,'actual_bars_since_entry':actual}
  if b['h']>=tp2:
   return {'status':'CLOSED','exit_reason':'TP2_ABS','exit_date':b['date'],'hold_bars':i,'pnl_pct':pnl1+tp2_pct*runner_frac,'same_day_exit_violation':False,'tp1_hit':True,'tp1_date':tp1_date,'sl':sl,'tp1':tp1,'tp2':tp2,'actual_bars_since_entry':actual}
  if i>=max_hold:
   return {'status':'CLOSED','exit_reason':'TIME_AFTER_TP1','exit_date':b['date'],'hold_bars':i,'pnl_pct':pnl1+(b['c']/ep-1)*100*runner_frac,'same_day_exit_violation':False,'tp1_hit':True,'tp1_date':tp1_date,'sl':sl,'tp1':tp1,'tp2':tp2,'actual_bars_since_entry':actual}
 if got and path:
  b=path[-1]
  return {'status':'OPEN_UNEXPIRED','exit_reason':'OPEN_AFTER_TP1_MTM','latest_date':b['date'],'latest_close':b['c'],'pnl_pct':pnl1+(b['c']/ep-1)*100*runner_frac,'tp1_hit':True,'tp1_date':tp1_date,'sl':sl,'tp1':tp1,'tp2':tp2,'actual_bars_since_entry':actual}
 if path:
  b=path[-1]
  return {'status':'OPEN_UNEXPIRED','exit_reason':'OPEN_NO_TP1','latest_date':b['date'],'latest_close':b['c'],'pnl_pct':(b['c']/ep-1)*100,'tp1_hit':False,'sl':sl,'tp1':tp1,'tp2':tp2,'actual_bars_since_entry':actual}
 return out

def metrics(rows:list[dict[str,Any]])->dict[str,Any]:
 closed=[r for r in rows if r.get('status')=='CLOSED']
 if not closed: return {'n':0,'wr':0,'avg':0,'min_year_n':0,'year_counts':{},'year_wr':{},'min_year_wr':0,'micro':0,'t1':0,'exit_counts':{},'tp1_rate':0}
 p=pd.Series([sf(r.get('pnl_pct'),0) for r in closed]); yrs=pd.Series([dn(r.get('entry_date'))[:4] for r in closed]); yc={str(k):int(v) for k,v in yrs[yrs>='2023'].value_counts().sort_index().to_dict().items()}; ywr={str(y):round(float((p[yrs==y]>0).mean()*100),2) for y in sorted(yc)}
 return {'n':len(closed),'wr':round(float((p>0).mean()*100),4),'avg':round(float(p.mean()),4),'min_year_n':int(min(yc.values()) if yc else 0),'year_counts':yc,'year_wr':ywr,'min_year_wr':round(float(min(ywr.values()) if ywr else 0),2),'micro':round(float(((p>0)&(p<1)).mean()*100),4),'t1':int(sum(bool(r.get('same_day_exit_violation')) for r in closed)),'exit_counts':{str(k):int(v) for k,v in pd.Series([r.get('exit_reason') for r in closed]).value_counts().to_dict().items()},'tp1_rate':round(float(pd.Series([bool(r.get('tp1_hit')) for r in closed]).mean()*100),4)}
def pass_gate(m,g): return m['n']>=g['n'] and m['min_year_n']>=g['min_year_n'] and m['wr']>=g['wr'] and m['avg']>=g['avg'] and m['min_year_wr']>=g['min_year_wr'] and m['micro']<=g['micro'] and m['t1']==0

def main():
 OUT.mkdir(parents=True,exist_ok=True); rep=load_json(V333,{}); df=pd.read_csv(rep['artifacts']['replayed_csv'],low_memory=False); df['entry_date']=df.entry_date.map(dn)
 actual=pd.to_numeric(df.v333_actual_bars_since_entry,errors='coerce'); cur_base=actual.le(10)&(~df.v333_any_history_overlap.astype(str).str.lower().isin(['true','1']))
 n=lambda c: pd.to_numeric(df.get(c,pd.Series(index=df.index)),errors='coerce'); ss=lambda c: df.get(c,pd.Series('',index=df.index)).astype(str)
 weak=ss('v244_industry').isin(WEAK); add=n('v244_ind_strong1_pct').ge(31.1688)|n('v236_br_above_ma20').ge(46.8561); base=df.v164_rule_pass.map(boolish)&((~weak)|add)
 f1=base&n('v132_bull_count_3').ge(3)&n('v132_reclaim_bull_body_pct').le(60)&n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2)
 predicates={
  'P1_BR76_ZONE102':f1&n('v236_br_above_ma20').ge(76.3339)&n('v85_zone_width_pct').ge(1.0204),
  'P2_BODY34_ZONE102':f1&n('v132_reclaim_bull_body_pct').le(34.5204)&n('v85_zone_width_pct').ge(1.0204),
  'P3_RISK402_BEAR':f1&n('risk_pct').ge(4.0199)&ss('market_state').eq('BEAR_RISK'),
  'P4_BR76_RISK199':f1&n('v236_br_above_ma20').ge(76.3339)&n('risk_pct').ge(1.9967),
  'P5_BR76_RECLAIM129':f1&n('v236_br_above_ma20').ge(76.3339)&n('reclaim_close_above_zone_pct').ge(1.291),
  'P6_ZONE102_TAKEOVER2':f1&n('v85_zone_width_pct').ge(1.0204)&ss('v132_reclaim_class').eq('TRUE_TAKEOVER_2'),
  'P7_F2_OB_ZONE2':base&n('v132_bull_count_3').ge(3)&n('v85_zone_width_pct').ge(2)&ss('poi_source').isin(['DEMAND_OB','OB+FVG']),
  'P8_F1_ALL':f1,
 }
 cache={}; results=[]; top_rows=[]
 for pname,mask in predicates.items():
  idx=df.index[mask.fillna(False)].tolist()
  if len(idx)<80: continue
  recs=df.loc[idx].to_dict('records')
  contracts=[]
  for sl_buf,tp,max_hold in itertools.product([0.005,0.01,0.015],[8,10,12,15],[20,30]): contracts.append(('ABS',sl_buf,tp,None,None,max_hold,None))
  for sl_buf,tp1,frac,tp2,max_hold,trail in itertools.product([0.005,0.01],[5,6,8],[0.4,0.5],[12,15,20],[20,30],['be_only','trail_8pct','lock_half_after_10']): contracts.append(('RUNNER',sl_buf,tp1,frac,tp2,max_hold,trail))
  for kind,sl_buf,a,b,c,max_hold,trail in contracts:
   rows=[]
   for r in recs:
    rr={'symbol':r.get('symbol'),'entry_date':r.get('entry_date')}
    if kind=='ABS': rr.update(replay_abs(r,cache,sl_buf,a,max_hold))
    else: rr.update(replay_runner(r,cache,sl_buf,a,b,c,max_hold,trail))
    rows.append(rr)
   hist=[r for r in rows if sf(r.get('actual_bars_since_entry'),-1)>=max_hold]
   cur=[r for r,ix in zip(rows,idx) if bool(cur_base.loc[ix])]
   hm=metrics(hist); cm=metrics([r for r in cur if r.get('status')=='CLOSED']); open_n=sum(r.get('status')=='OPEN_UNEXPIRED' for r in cur)
   prod=pass_gate(hm,PROD_GATE) and open_n>=PROD_GATE['current_open']; research=pass_gate(hm,RESEARCH_GATE)
   score=hm['avg']*0.8+(hm['wr']-90)*0.25+hm['min_year_wr']*0.03-min(hm['micro'],10)*0.5+min(hm['n'],570)/570+open_n*0.05
   item={'predicate':pname,'kind':kind,'sl_buf':sl_buf,'tp_or_tp1':a,'runner_frac':b,'tp2':c,'max_hold':max_hold,'trail':trail,'score':round(float(score),4),'hist':hm,'current_closed':cm,'current_rows':len(cur),'current_open_rows':open_n,'pass_production_gate':prod,'pass_research_gate':research}
   results.append(item)
 results=sorted(results,key=lambda r:(r['pass_production_gate'],r['pass_research_gate'],r['hist']['wr'],r['hist']['avg'],r['hist']['n']),reverse=True)
 passing_prod=[r for r in results if r['pass_production_gate']]; passing_res=[r for r in results if r['pass_research_gate']]
 pd.DataFrame([{**{k:r[k] for k in ['predicate','kind','sl_buf','tp_or_tp1','runner_frac','tp2','max_hold','trail','score','current_rows','current_open_rows','pass_production_gate','pass_research_gate']},**{f'hist_{k}':v for k,v in r['hist'].items() if not isinstance(v,dict)},**{f'cur_{k}':v for k,v in r['current_closed'].items() if not isinstance(v,dict)}} for r in results[:1000]]).to_csv(OUT/'v338_rule_table_top1000.csv',index=False)
 report={'version':'V338_EXPANSION_FILTER_EXECUTABLE_BACKTEST_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source':rep['artifacts']['replayed_csv'],'production_gate':PROD_GATE,'research_gate':RESEARCH_GATE,'evaluated_rules':len(results),'passing_production_count':len(passing_prod),'passing_research_count':len(passing_res),'top_production':passing_prod[:20],'top_research':passing_res[:30],'top_rules':results[:50],'decision':'V338_PRODUCTION_GATE_PASSED_SHADOW_ONLY_NO_WRITE' if passing_prod else ('V338_RESEARCH_CANDIDATE_ONLY__INSUFFICIENT_PRODUCTION_COVERAGE' if passing_res else 'V338_NO_EXECUTABLE_EXPANSION_FILTER_PASSES__NEED_NEW_SIGNAL_LAYER'),'artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'rule_table':str(OUT/'v338_rule_table_top1000.csv')}}
 (OUT/'v338_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':report['decision'],'passing_production_count':len(passing_prod),'passing_research_count':len(passing_res),'top_research':passing_res[:5],'top_rules':results[:10]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
