#!/usr/bin/env python3
"""V342 no-write: BSL room signal-layer test.

V338-V340 proved TP/runner exits cannot recover production avg at coverage. V342
adds a true SMC signal-layer predicate: pre-entry upside liquidity room (nearest
prior buy-side liquidity / prior highs) and local structure context, then replays
T+1 executable exits. No production/frontend/watchlist writes.
"""
from __future__ import annotations
import itertools, json, math
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; KDIR=ROOT/'kline_cache'; V333=AUD/'v333_full_universe_rule_search_after_breadth_refresh_latest.json'
OUT=AUD/f"v342_bsl_room_signal_layer_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v342_bsl_room_signal_layer_latest.json'
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

def add_bsl_features(df:pd.DataFrame)->pd.DataFrame:
 cache={}; feats=[]
 for r in df.itertuples():
  sym=str(r.symbol); ed=dn(r.entry_date); ep=sf(r.entry_price)
  if sym not in cache: cache[sym]=bars(sym)
  b=cache[sym]; idx=next((i for i,x in enumerate(b) if x['date']==ed),None)
  f={'v342_has_bars':False}
  if idx is not None and ep and idx>=65:
   pre=b[:idx]; w20=pre[-20:]; w60=pre[-60:]; w10=pre[-10:]
   h20=max(x['h'] for x in w20); h60=max(x['h'] for x in w60); l20=min(x['l'] for x in w20); l60=min(x['l'] for x in w60)
   tr=[]
   for j,x in enumerate(w20):
    pc=pre[idx-20+j-1]['c'] if idx-20+j-1>=0 else x['c']
    tr.append(max(x['h']-x['l'],abs(x['h']-pc),abs(x['l']-pc)))
   atr=sum(tr)/len(tr) if tr else 0
   f={
    'v342_has_bars':True,
    'v342_bsl20_room_pct':(h20/ep-1)*100,
    'v342_bsl60_room_pct':(h60/ep-1)*100,
    'v342_ssl20_gap_pct':(ep/l20-1)*100,
    'v342_ssl60_gap_pct':(ep/l60-1)*100,
    'v342_atr20_pct':atr/ep*100 if ep else None,
    'v342_pre10_ret_pct':(pre[-1]['c']/w10[0]['c']-1)*100 if w10 and w10[0]['c'] else None,
    'v342_pos20_pct':(ep-l20)/(h20-l20)*100 if h20>l20 else None,
    'v342_pos60_pct':(ep-l60)/(h60-l60)*100 if h60>l60 else None,
   }
  feats.append(f)
 return pd.concat([df.reset_index(drop=True),pd.DataFrame(feats)],axis=1)

def replay(r:dict[str,Any], cache:dict[str,list[dict[str,Any]]], slbuf:float,tp1:float,frac:float,tp2:float,mh:int)->dict[str,Any]:
 sym,ed=str(r.get('symbol') or ''),dn(r.get('entry_date'))
 if sym not in cache: cache[sym]=bars(sym)
 b0=cache[sym]; dates=[x['date'] for x in b0]; actual=sum(1 for d in dates if d>ed) if ed in dates else None
 ep,zl=sf(r.get('entry_price')),sf(r.get('zone_low'))
 if not sym or not ed or ep is None or zl is None or ep<=0 or zl<=0: return {'status':'FIELD_MISSING','actual_bars_since_entry':actual}
 sl=zl*(1-slbuf)
 if sl>=ep: sl=ep*0.985
 t1=ep*(1+tp1/100); t2=ep*(1+tp2/100); path=[x for x in b0 if x['date']>ed]
 got=False; pnl1=0.0; rsl=sl
 for i,b in enumerate(path,1):
  if not got:
   if b['l']<=sl: return {'status':'CLOSED','exit_reason':'SL_BEFORE_TP1','pnl_pct':(sl/ep-1)*100,'hold_bars':i,'same_day_exit_violation':False,'actual_bars_since_entry':actual,'tp1_hit':False}
   if b['h']>=t1:
    got=True; pnl1=tp1*(1-frac); rsl=ep
    if b['l']<=rsl: return {'status':'CLOSED','exit_reason':'TP1_RUNNER_BE_SAME_BAR','pnl_pct':pnl1,'hold_bars':i,'same_day_exit_violation':False,'actual_bars_since_entry':actual,'tp1_hit':True}
   elif i>=mh: return {'status':'CLOSED','exit_reason':'TIME_NO_TP1','pnl_pct':(b['c']/ep-1)*100,'hold_bars':i,'same_day_exit_violation':False,'actual_bars_since_entry':actual,'tp1_hit':False}
   continue
  if b['l']<=rsl: return {'status':'CLOSED','exit_reason':'RUNNER_BE','pnl_pct':pnl1,'hold_bars':i,'same_day_exit_violation':False,'actual_bars_since_entry':actual,'tp1_hit':True}
  if b['h']>=t2: return {'status':'CLOSED','exit_reason':'TP2_ABS','pnl_pct':pnl1+tp2*frac,'hold_bars':i,'same_day_exit_violation':False,'actual_bars_since_entry':actual,'tp1_hit':True}
  if i>=mh: return {'status':'CLOSED','exit_reason':'TIME_AFTER_TP1','pnl_pct':pnl1+(b['c']/ep-1)*100*frac,'hold_bars':i,'same_day_exit_violation':False,'actual_bars_since_entry':actual,'tp1_hit':True}
 if path: return {'status':'OPEN_UNEXPIRED','exit_reason':'OPEN','pnl_pct':None,'actual_bars_since_entry':actual,'tp1_hit':got}
 return {'status':'FIELD_MISSING','actual_bars_since_entry':actual}

def metrics(rows:list[dict[str,Any]])->dict[str,Any]:
 closed=[r for r in rows if r.get('status')=='CLOSED']
 if not closed: return {'n':0,'wr':0,'avg':0,'min_year_n':0,'year_counts':{},'year_wr':{},'min_year_wr':0,'micro':0,'t1':0,'exit_counts':{},'tp1_rate':0}
 p=pd.Series([sf(r.get('pnl_pct'),0) for r in closed]); yrs=pd.Series([dn(r.get('entry_date'))[:4] for r in closed]); yc={str(k):int(v) for k,v in yrs[yrs>='2023'].value_counts().sort_index().to_dict().items()}; ywr={str(y):round(float((p[yrs==y]>0).mean()*100),2) for y in sorted(yc)}
 return {'n':len(closed),'wr':round(float((p>0).mean()*100),4),'avg':round(float(p.mean()),4),'min_year_n':int(min(yc.values()) if yc else 0),'year_counts':yc,'year_wr':ywr,'min_year_wr':round(float(min(ywr.values()) if ywr else 0),2),'micro':round(float(((p>0)&(p<1)).mean()*100),4),'t1':0,'exit_counts':{str(k):int(v) for k,v in pd.Series([r.get('exit_reason') for r in closed]).value_counts().to_dict().items()},'tp1_rate':round(float(pd.Series([bool(r.get('tp1_hit')) for r in closed]).mean()*100),4)}
def gate(m:dict[str,Any])->bool:
 return m['n']>=GATE['n'] and m['min_year_n']>=GATE['min_year_n'] and m['wr']>=GATE['wr'] and m['avg']>=GATE['avg'] and m['min_year_wr']>=GATE['min_year_wr'] and m['micro']<=GATE['micro'] and m['t1']==0

def main():
 OUT.mkdir(parents=True,exist_ok=True); rep=load_json(V333,{}); df=pd.read_csv(rep['artifacts']['replayed_csv'],low_memory=False); df['entry_date']=df.entry_date.map(dn)
 n=lambda c: pd.to_numeric(df.get(c,pd.Series(index=df.index)),errors='coerce'); ss=lambda c: df.get(c,pd.Series('',index=df.index)).astype(str)
 weak=ss('v244_industry').isin(WEAK); add=n('v244_ind_strong1_pct').ge(31.1688)|n('v236_br_above_ma20').ge(46.8561); base=ss('v164_rule_pass').map(boolish)&((~weak)|add)
 seed=base&n('v132_bull_count_3').ge(3)&(ss('poi_source').isin(['DEMAND_OB','OB+FVG'])|ss('poi_source').eq('FVG_Demand'))
 edf=add_bsl_features(df[seed.fillna(False)].copy())
 actual=pd.to_numeric(edf.v333_actual_bars_since_entry,errors='coerce'); cur_base=actual.le(10)&(~edf.v333_any_history_overlap.astype(str).str.lower().isin(['true','1']))
 n2=lambda c: pd.to_numeric(edf.get(c,pd.Series(index=edf.index)),errors='coerce'); ss2=lambda c: edf.get(c,pd.Series('',index=edf.index)).astype(str)
 families={}
 for src in ['ALL','OB','FVG']:
  srcmask=pd.Series(True,index=edf.index)
  if src=='OB': srcmask=ss2('poi_source').isin(['DEMAND_OB','OB+FVG'])
  if src=='FVG': srcmask=ss2('poi_source').eq('FVG_Demand')
  for room in [5,10,15,20,25,30]:
   for pos60 in [None,50,65,80]:
    for atrmax in [None,8,12,16]:
     m=srcmask&n2('v342_has_bars').eq(1)&n2('v342_bsl60_room_pct').ge(room)
     name=f'{src}_bsl60>={room}'
     if pos60 is not None: m&=n2('v342_pos60_pct').le(pos60); name+=f'_pos60<={pos60}'
     if atrmax is not None: m&=n2('v342_atr20_pct').le(atrmax); name+=f'_atr<={atrmax}'
     if int(m.sum())>=120: families[name]=m
 contracts=list(itertools.product([0,0.005,0.01],[4,5,6],[0.5,0.6,0.7],[20,25,30],[20,30]))
 cache={}; results=[]
 for fname,mask in families.items():
  idx=edf.index[mask.fillna(False)].tolist(); recs=edf.loc[idx].to_dict('records')
  for sl,tp1,frac,tp2,mh in contracts:
   rows=[]
   for r in recs:
    rr={'symbol':r.get('symbol'),'entry_date':r.get('entry_date')}; rr.update(replay(r,cache,sl,tp1,frac,tp2,mh)); rows.append(rr)
   hist=[r for r in rows if sf(r.get('actual_bars_since_entry'),-1)>=mh]
   cur=[r for r,ix in zip(rows,idx) if bool(cur_base.loc[ix])]
   hm=metrics(hist); cm=metrics([r for r in cur if r.get('status')=='CLOSED']); open_n=sum(r.get('status')=='OPEN_UNEXPIRED' for r in cur)
   pg=gate(hm) and open_n>=GATE['current_open']
   score=(hm['wr']-90)*.45+hm['avg']*.9+hm['min_year_wr']*.03+min(hm['n'],570)/570-hm['micro']*.5+open_n*.05
   results.append({'family':fname,'sl_buf':sl,'tp1':tp1,'runner_frac':frac,'tp2':tp2,'max_hold':mh,'score':round(float(score),4),'hist':hm,'current_closed':cm,'current_rows':len(cur),'current_open_rows':open_n,'pass_gate':pg})
 results=sorted(results,key=lambda r:(r['pass_gate'],r['hist']['wr'],r['hist']['avg'],r['hist']['n']),reverse=True); passing=[r for r in results if r['pass_gate']]
 frontier=[]
 for need in [120,200,300,400,500,570,700,900]:
  cand=[r for r in results if r['hist']['n']>=need]
  if cand: frontier.append({'min_n':need,'best':cand[0]})
 pd.DataFrame([{**{k:r[k] for k in ['family','sl_buf','tp1','runner_frac','tp2','max_hold','score','current_rows','current_open_rows','pass_gate']},**{f'hist_{k}':v for k,v in r['hist'].items() if not isinstance(v,dict)},**{f'cur_{k}':v for k,v in r['current_closed'].items() if not isinstance(v,dict)}} for r in results[:2000]]).to_csv(OUT/'v342_bsl_frontier_top2000.csv',index=False)
 report={'version':'V342_BSL_ROOM_SIGNAL_LAYER_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source':rep['artifacts']['replayed_csv'],'gate':GATE,'seed_rows':int(len(edf)),'families_evaluated':len(families),'rules_evaluated':len(results),'passing_rule_count':len(passing),'top_passing':passing[:20],'coverage_frontier':frontier,'top_rules':results[:50],'decision':'V342_BSL_ROOM_RECOVERS_PRODUCTION_GATE__SHADOW_ONLY_NO_WRITE' if passing else 'V342_BSL_ROOM_FAILS_PRODUCTION_GATE__NEED_SEQUENCE_REBUILD','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'rule_table':str(OUT/'v342_bsl_frontier_top2000.csv')}}
 (OUT/'v342_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':report['decision'],'passing_rule_count':len(passing),'frontier':frontier,'top_rules':results[:10]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
