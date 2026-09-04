#!/usr/bin/env python3
"""V381 no-write true MTF replay: raw-daily fresh POI -> 60m touch/reclaim/hold.
Daily POIs come only from V380 raw-60m-aggregated daily bars; 60m execution uses
same Sina source. Entries are next 60m open after reclaim+hold; exits are T+1.
"""
from __future__ import annotations
import csv,gzip,json,math
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); RAW=ROOT/'intraday_cache/sina_raw_daily_v379'; M60=ROOT/'intraday_cache/sina_m60_v1'; AUD=ROOT/'smc_audit'
V380=AUD/'v380_raw_daily_independent_semantic_oracle_latest.json'; OUT=AUD/f'v381_true_mtf_raw_daily_poi_m60_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'; LATEST=AUD/'v381_true_mtf_raw_daily_poi_m60_replay_latest.json'; SLOTS={'10:30:00','11:30:00','14:00:00','15:00:00'}
def f(x): return float(x)
def m60(sym):
 p=M60/f"{sym.replace('.','_')}_m60_sina.json.gz"
 with gzip.open(p,'rt') as h:x=json.load(h)
 by=defaultdict(list)
 for z in x:
  t=str(z.get('day','')); d=t[:10].replace('-','')
  if '20230101'<=d<='20260710':
   try:by[d].append({'t':t,'d':d,'o':f(z['open']),'h':f(z['high']),'l':f(z['low']),'c':f(z['close'])})
   except:pass
 return [b for d in sorted(by) if len(by[d])==4 and {q['t'][-8:] for q in by[d]}==SLOTS for b in sorted(by[d],key=lambda q:q['t'])]
def daily(sym):
 with gzip.open(RAW/f"{sym.replace('.','_')}_raw_daily.json.gz",'rt') as h:return json.load(h)
def pivots(b):
 out=[]
 for i in range(3,len(b)-3):
  if b[i]['h']==max(x['h'] for x in b[i-3:i+4]) and sum(x['h']==b[i]['h'] for x in b[i-3:i+4])==1:out.append((i,b[i]['h'],i+3))
 return out
def candidate(seed,ib,db,highs):
 # Daily event is known at its 15:00 close: only later dates may touch the POI.
 ev=str(seed['event_date']); zl,zh=f(seed['zone_low']),f(seed['zone_high']); seg=int(seed['segment_id']); start=next((i for i,b in enumerate(ib) if b['d']>ev and b['d'] in db and db[b['d']]==seg),None)
 if start is None:return None,'NO_POST_EVENT_M60'
 touch=reclaim=hold=None
 for i in range(start,len(ib)):
  b=ib[i]
  if db.get(b['d'])!=seg: break
  if b['c']<zl:return None,'INVALID_BEFORE_ENTRY'
  if touch is None:
   if b['l']<=zh:touch=i
  elif reclaim is None:
   if i>touch and b['c']>zh:reclaim=i
  elif i>reclaim and b['c']>zh and b['l']>=zl:
   hold=i;break
 if hold is None:return None,'NO_COMPLETE_60M_REACTION'
 ei=hold+1
 if ei>=len(ib) or db.get(ib[ei]['d'])!=seg:return None,'NO_NEXT_OPEN'
 ep=ib[ei]['o']; sl=zl*.997; targets=[p for _,p,ci in highs if ci<len(db) and db.get(db_dates[ci],'')==seg and db_dates[ci]<ib[ei]['d'] and p>ep]
 if not targets:return None,'NO_KNOWN_STRUCTURAL_TARGET'
 tp=min(targets); risk=(ep-sl)/ep*100; rr=(tp-ep)/(ep-sl)
 if not 1.5<=risk<=10:return None,'RISK_BAND'
 if not 1.5<=rr<=5:return None,'RR_BAND'
 return {'symbol':seed['symbol'],'daily_event_type':seed['event_type'],'daily_event_date':ev,'daily_ob_date':seed['ob_date'],'daily_segment_id':seg,'zone_low':zl,'zone_high':zh,'touch_time':ib[touch]['t'],'reclaim_time':ib[reclaim]['t'],'hold_time':ib[hold]['t'],'entry_time':ib[ei]['t'],'entry_date':ib[ei]['d'],'entry_i':ei,'entry_price':ep,'sl':sl,'tp':tp,'risk_pct':risk,'rr':rr},'CANDIDATE'
def exitrow(r,ib):
 ed=r['entry_date']; ei=r['entry_i']
 later=[i for i in range(ei+1,min(len(ib),ei+41)) if ib[i]['d']!=ed]
 if not later:return None
 for i in later:
  b=ib[i]
  if b['l']<=r['sl']: price,why=r['sl'],'SL_HIT';break
  if b['h']>=r['tp']: price,why=r['tp'],'TP_HIT';break
 else:i=later[-1];price,why=ib[i]['c'],'TIME_10_SESSIONS'
 r={k:v for k,v in r.items() if k!='entry_i'};r.update(exit_time=ib[i]['t'],exit_date=ib[i]['d'],exit_price=price,exit_reason=why,pnl_pct=(price/r['entry_price']-1)*100,hold_bars=i-ei,t1_violation=(ib[i]['d']==ed));return r
def metrics(x):
 ys=defaultdict(list)
 for r in x:ys[r['entry_date'][:4]].append(r)
 yc={k:len(v) for k,v in ys.items()}; yw={k:round(sum(r['pnl_pct']>0 for r in v)/len(v)*100,2) for k,v in ys.items()}
 return {'n':len(x),'symbols':len({r['symbol'] for r in x}),'wr':round(sum(r['pnl_pct']>0 for r in x)/len(x)*100,4) if x else 0,'avg_pnl':round(sum(r['pnl_pct'] for r in x)/len(x),4) if x else 0,'micro_pct':round(sum(0<r['pnl_pct']<1 for r in x)/len(x)*100,4) if x else 0,'sl_pct':round(sum(r['exit_reason']=='SL_HIT' for r in x)/len(x)*100,4) if x else 0,'t1_violations':sum(r['t1_violation'] for r in x),'year_counts':yc,'year_wr':yw,'min_year_n':min(yc.values()) if yc else 0,'min_year_wr':min(yw.values()) if yw else 0}
def main():
 global db_dates
 v=json.load(open(V380));
 if v['decision']!='SEMANTIC_DIFFERENTIAL_PASS__MTF_REPLAY_ALLOWED':raise RuntimeError('V380 semantic differential failed')
 OUT.mkdir(parents=True,exist_ok=True)
 with open(v['artifacts']['seeds'],newline='') as h:seeds=list(csv.DictReader(h))
 by=defaultdict(list)
 for s in seeds:by[s['symbol']].append(s)
 stages=Counter(); candidates=[]
 for n,(sym,ss) in enumerate(sorted(by.items()),1):
  try:ib=m60(sym); rb=daily(sym)
  except Exception:stages['LOAD_FAILURE']+=len(ss);continue
  db={str(x['t']):int(x['segment_id']) for x in rb};db_dates=[str(x['t']) for x in rb]; hs=pivots(rb)
  for s in ss:
   r,why=candidate(s,ib,db,hs);stages[why]+=1
   if r:candidates.append(r)
  if n%500==0:print(json.dumps({'symbols':n,'candidates':len(candidates)}),flush=True)
 newest={}
 for r in candidates:
  old=newest.get((r['symbol'],r['entry_time']))
  if old is None or r['daily_event_date']>old['daily_event_date']:newest[(r['symbol'],r['entry_time'])]=r
 executed=[]
 for sym in set(r['symbol'] for r in newest.values()):
  until=''
  ib=m60(sym)
  for r in sorted((z for z in newest.values() if z['symbol']==sym),key=lambda z:z['entry_time']):
   if until and r['entry_time']<=until:stages['BLOCKED_OVERLAP']+=1;continue
   q=exitrow(r,ib)
   if q:executed.append(q);until=q['exit_time']
 stages['EXECUTED']=len(executed);m=metrics(executed)
 fields=list(executed[0]) if executed else ['symbol']
 with (OUT/'v381_trades.csv').open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(executed)
 checks={'n>=300':m['n']>=300,'min_year_n>=40':m['min_year_n']>=40,'wr>=87':m['wr']>=87,'avg>=6.8':m['avg_pnl']>=6.8,'year_wr>=84':m['min_year_wr']>=84,'micro<=1':m['micro_pct']<=1,'t1==0':m['t1_violations']==0};passed=all(checks.values())
 report={'version':'V381_TRUE_MTF_RAW_DAILY_POI_M60_T1_REPLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'contract':'V380 semantic-valid raw-daily bull BOS/CHOCH demand OB, fresh from daily event close; first later 60m touch -> reclaim -> hold -> next 60m open; daily known swing-high target; risk 1.5-10%, RR 1.5-5; 60m T+1 exits with SL-first same-bar rule; serial per-symbol execution','stages':dict(stages),'metrics':m,'production_gate':checks,'decision':'RESEARCH_CANDIDATE_ONLY__INDEPENDENT_TRADE_ORACLE_REQUIRED' if passed else 'NO_PRODUCTION_PASS__TRUE_MTF_BRANCH_CLOSED','artifacts':{'trades':str(OUT/'v381_trades.csv'),'latest':str(LATEST)}}
 text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v381_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
