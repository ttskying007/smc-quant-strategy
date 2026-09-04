#!/usr/bin/env python3
"""V339 no-write: coverage-quality frontier around V338 research candidate.

V338 found executable 96.85% WR / 8.11% avg only at n=127. V339 broadens the
same semantic family (F1 + takeover/zone/breadth/body/risk variants) to find the
largest executable frontier and prove whether production coverage can be
recovered without changing the signal layer.
"""
from __future__ import annotations
import itertools, json, math
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; KDIR=ROOT/'kline_cache'; V333=AUD/'v333_full_universe_rule_search_after_breadth_refresh_latest.json'
OUT=AUD/f"v339_coverage_quality_frontier_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v339_coverage_quality_frontier_latest.json'
WEAK={'C27医药制造业','C32有色金属冶炼和压延加工业'}
GATE={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'min_year_wr':91.0,'micro':1.0,'t1':0,'current_open':1}

def dn(x:Any)->str:
 s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def sf(x:Any, default=None):
 try:
  if x is None or x=='': return default
  v=float(x); return default if math.isnan(v) or math.isinf(v) else v
  return v
 except Exception: return default
def boolish(x): return str(x).strip().lower() in {'true','1','yes'}
def load_json(p:Path, default):
 try: return json.loads(p.read_text())
 except Exception: return default
def bars(sym):
 out=[]; p=KDIR/f"{sym.replace('.','_')}_daily_750.json"
 for b in load_json(p,[]):
  d=dn(b.get('t') or b.get('date')); o,h,l,c=sf(b.get('o')),sf(b.get('h')),sf(b.get('l')),sf(b.get('c'))
  if d and None not in (o,h,l,c): out.append({'date':d,'o':float(o),'h':float(h),'l':float(l),'c':float(c)})
 return sorted(out,key=lambda x:x['date'])
def replay(r,cache,sl_buf,tp1,frac,tp2,max_hold,trail):
 sym,ed=str(r.get('symbol') or ''),dn(r.get('entry_date'))
 if sym not in cache: cache[sym]=bars(sym)
 b0=cache[sym]; dates=[b['date'] for b in b0]; actual=sum(1 for d in dates if d>ed) if ed in dates else None
 ep,zl=sf(r.get('entry_price')),sf(r.get('zone_low') or r.get('dz_low'))
 if not sym or not ed or ep is None or zl is None or ep<=0 or zl<=0: return {'status':'FIELD_MISSING','actual_bars_since_entry':actual}
 sl=zl*(1-sl_buf)
 if sl>=ep: sl=ep*0.985
 t1=ep*(1+tp1/100); t2=ep*(1+tp2/100); path=[b for b in b0 if b['date']>ed]
 got=False; pnl1=0.0; peak=ep; rsl=sl
 for i,b in enumerate(path,1):
  if not got:
   if b['l']<=sl: return {'status':'CLOSED','exit_reason':'SL_BEFORE_TP1','exit_date':b['date'],'hold_bars':i,'pnl_pct':(sl/ep-1)*100,'tp1_hit':False,'same_day_exit_violation':False,'actual_bars_since_entry':actual}
   if b['h']>=t1:
    got=True; pnl1=tp1*(1-frac); peak=max(peak,b['h']); rsl=ep
   elif i>=max_hold:
    return {'status':'CLOSED','exit_reason':'TIME_NO_TP1','exit_date':b['date'],'hold_bars':i,'pnl_pct':(b['c']/ep-1)*100,'tp1_hit':False,'same_day_exit_violation':False,'actual_bars_since_entry':actual}
   continue
  peak=max(peak,b['h'])
  if trail=='be_only': rsl=ep
  elif trail=='lock_half_after_10' and peak>=ep*1.10: rsl=max(rsl,ep*1.04)
  if b['l']<=rsl: return {'status':'CLOSED','exit_reason':'RUNNER_SL','exit_date':b['date'],'hold_bars':i,'pnl_pct':pnl1+(rsl/ep-1)*100*frac,'tp1_hit':True,'same_day_exit_violation':False,'actual_bars_since_entry':actual}
  if b['h']>=t2: return {'status':'CLOSED','exit_reason':'TP2_ABS','exit_date':b['date'],'hold_bars':i,'pnl_pct':pnl1+tp2*frac,'tp1_hit':True,'same_day_exit_violation':False,'actual_bars_since_entry':actual}
  if i>=max_hold: return {'status':'CLOSED','exit_reason':'TIME_AFTER_TP1','exit_date':b['date'],'hold_bars':i,'pnl_pct':pnl1+(b['c']/ep-1)*100*frac,'tp1_hit':True,'same_day_exit_violation':False,'actual_bars_since_entry':actual}
 if path:
  b=path[-1]; return {'status':'OPEN_UNEXPIRED','exit_reason':'OPEN_AFTER_TP1_MTM' if got else 'OPEN_NO_TP1','pnl_pct':(pnl1+(b['c']/ep-1)*100*frac) if got else (b['c']/ep-1)*100,'tp1_hit':got,'actual_bars_since_entry':actual}
 return {'status':'FIELD_MISSING','actual_bars_since_entry':actual}
def metrics(rows):
 closed=[r for r in rows if r.get('status')=='CLOSED']
 if not closed: return {'n':0,'wr':0,'avg':0,'min_year_n':0,'year_counts':{},'year_wr':{},'min_year_wr':0,'micro':0,'t1':0,'exit_counts':{},'tp1_rate':0}
 p=pd.Series([sf(r.get('pnl_pct'),0) for r in closed]); yrs=pd.Series([dn(r.get('entry_date'))[:4] for r in closed]); yc={str(k):int(v) for k,v in yrs[yrs>='2023'].value_counts().sort_index().to_dict().items()}; ywr={str(y):round(float((p[yrs==y]>0).mean()*100),2) for y in sorted(yc)}
 return {'n':len(closed),'wr':round(float((p>0).mean()*100),4),'avg':round(float(p.mean()),4),'min_year_n':int(min(yc.values()) if yc else 0),'year_counts':yc,'year_wr':ywr,'min_year_wr':round(float(min(ywr.values()) if ywr else 0),2),'micro':round(float(((p>0)&(p<1)).mean()*100),4),'t1':int(sum(bool(r.get('same_day_exit_violation')) for r in closed)),'exit_counts':{str(k):int(v) for k,v in pd.Series([r.get('exit_reason') for r in closed]).value_counts().to_dict().items()},'tp1_rate':round(float(pd.Series([bool(r.get('tp1_hit')) for r in closed]).mean()*100),4)}
def ok(m): return m['n']>=GATE['n'] and m['min_year_n']>=GATE['min_year_n'] and m['wr']>=GATE['wr'] and m['avg']>=GATE['avg'] and m['min_year_wr']>=GATE['min_year_wr'] and m['micro']<=GATE['micro'] and m['t1']==0

def main():
 OUT.mkdir(parents=True,exist_ok=True); rep=load_json(V333,{}); df=pd.read_csv(rep['artifacts']['replayed_csv'],low_memory=False); df['entry_date']=df.entry_date.map(dn)
 actual=pd.to_numeric(df.v333_actual_bars_since_entry,errors='coerce'); cur_base=actual.le(10)&(~df.v333_any_history_overlap.astype(str).str.lower().isin(['true','1']))
 n=lambda c: pd.to_numeric(df.get(c,pd.Series(index=df.index)),errors='coerce'); ss=lambda c: df.get(c,pd.Series('',index=df.index)).astype(str)
 weak=ss('v244_industry').isin(WEAK); add=n('v244_ind_strong1_pct').ge(31.1688)|n('v236_br_above_ma20').ge(46.8561); base=df.v164_rule_pass.map(boolish)&((~weak)|add)
 f1=base&n('v132_bull_count_3').ge(3)&n('v132_reclaim_bull_body_pct').le(60)&n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2)
 masks=[]
 for zone in [0,0.5,0.8,1.0,1.25,1.5,2.0]:
  for br in [None,40,55,66,76]:
   for body in [None,35,45,60]:
    for takeover in [False,True]:
     m=f1.copy(); name=[]
     if zone>0: m&=n('v85_zone_width_pct').ge(zone); name.append(f'zone>={zone}')
     if br is not None: m&=n('v236_br_above_ma20').ge(br); name.append(f'br>={br}')
     if body is not None: m&=n('v132_reclaim_bull_body_pct').le(body); name.append(f'body<={body}')
     if takeover: m&=ss('v132_reclaim_class').eq('TRUE_TAKEOVER_2'); name.append('takeover2')
     masks.append(('F1_'+('&'.join(name) if name else 'all'),m))
 # Add OB branch because it was the only wider high-quality branch in V338.
 for zone in [1.0,1.5,2.0]:
  masks.append((f'OB_zone>={zone}',base&n('v132_bull_count_3').ge(3)&n('v85_zone_width_pct').ge(zone)&ss('poi_source').isin(['DEMAND_OB','OB+FVG'])))
 contracts=list(itertools.product([0.005,0.01],[5,6],[0.4,0.5],[15,20],[20,30],['be_only','lock_half_after_10']))
 cache={}; results=[]
 for name,mask in masks:
  idx=df.index[mask.fillna(False)].tolist()
  if len(idx)<100: continue
  recs=df.loc[idx].to_dict('records')
  for sl,tp1,frac,tp2,mh,trail in contracts:
   rows=[]
   for r in recs:
    rr={'symbol':r.get('symbol'),'entry_date':r.get('entry_date')}; rr.update(replay(r,cache,sl,tp1,frac,tp2,mh,trail)); rows.append(rr)
   hist=[r for r in rows if sf(r.get('actual_bars_since_entry'),-1)>=mh]
   cur=[r for r,ix in zip(rows,idx) if bool(cur_base.loc[ix])]
   hm=metrics(hist); cm=metrics([r for r in cur if r.get('status')=='CLOSED']); open_n=sum(r.get('status')=='OPEN_UNEXPIRED' for r in cur)
   pass_gate=ok(hm) and open_n>=GATE['current_open']
   score=(hm['wr']-90)*0.4+hm['avg']*0.8+min(hm['n'],570)/570+hm['min_year_wr']*0.03-hm['micro']*0.5+open_n*0.05
   results.append({'rule':name,'sl_buf':sl,'tp1':tp1,'runner_frac':frac,'tp2':tp2,'max_hold':mh,'trail':trail,'score':round(float(score),4),'hist':hm,'current_closed':cm,'current_rows':len(cur),'current_open_rows':open_n,'pass_gate':pass_gate})
 results=sorted(results,key=lambda r:(r['pass_gate'],r['hist']['wr'],r['hist']['avg'],r['hist']['n']),reverse=True); passing=[r for r in results if r['pass_gate']]
 pd.DataFrame([{**{k:r[k] for k in ['rule','sl_buf','tp1','runner_frac','tp2','max_hold','trail','score','current_rows','current_open_rows','pass_gate']},**{f'hist_{k}':v for k,v in r['hist'].items() if not isinstance(v,dict)},**{f'cur_{k}':v for k,v in r['current_closed'].items() if not isinstance(v,dict)}} for r in results[:2000]]).to_csv(OUT/'v339_frontier_top2000.csv',index=False)
 # coverage frontier: best rows for minimum n buckets.
 frontier=[]
 for need in [120,200,300,400,500,570,700,900]:
  cand=[r for r in results if r['hist']['n']>=need]
  if cand: frontier.append({'min_n':need,'best_by_wr_avg':cand[0]})
 report={'version':'V339_COVERAGE_QUALITY_FRONTIER_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source':rep['artifacts']['replayed_csv'],'gate':GATE,'evaluated_rules':len(results),'passing_rule_count':len(passing),'top_passing':passing[:20],'coverage_frontier':frontier,'top_rules':results[:60],'decision':'V339_PRODUCTION_GATE_PASSED_SHADOW_ONLY_NO_WRITE' if passing else 'V339_NO_COVERAGE_EXPANSION_RECOVERS_PRODUCTION_GATE__NEW_SIGNAL_LAYER_REQUIRED','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'frontier_table':str(OUT/'v339_frontier_top2000.csv')}}
 (OUT/'v339_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':report['decision'],'passing_rule_count':len(passing),'coverage_frontier':frontier,'top_rules':results[:10]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
