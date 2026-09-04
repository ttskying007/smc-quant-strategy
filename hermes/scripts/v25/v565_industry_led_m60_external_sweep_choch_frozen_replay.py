#!/usr/bin/env python3
"""V565 single frozen strict-T+1 replay for V563/V564 identities."""
from __future__ import annotations
import csv,json,math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
BASE=Path('/root/.hermes'); AUDIT=BASE/'smc_audit'; KDAY=BASE/'kline_cache'
ORACLE=AUDIT/'v564_industry_led_m60_external_sweep_choch_oracle_latest.json'; LATEST=AUDIT/'v565_industry_led_m60_external_sweep_choch_frozen_t1_replay_latest.json'
TS=datetime.now().strftime('%Y%m%d_%H%M%S'); OUT=AUDIT/f'v565_industry_led_m60_external_sweep_choch_frozen_t1_replay_no_write_{TS}'
FEE=0.20; HOLD=20; RR_MIN=1.5

def f(x:Any,d=math.nan):
 try:return float(x)
 except:return d
def dn(x:Any):
 s=''.join(c for c in str(x or '') if c.isdigit());return s[:8] if len(s)>=8 else ''
def load(p):
 try:
  x=json.loads(p.read_text());return x if isinstance(x,list) else []
 except:return []
def dp(s):
 a,b=s.split('.');return KDAY/f'{a}_{b}_daily_750.json'
def swing_highs(bars,event_i):
 out=[]
 for i in range(3,event_i-3):
  h=f(bars[i].get('h'));w=[f(bars[j].get('h')) for j in range(i-3,i+4)]
  if h>0 and h==max(w) and w.count(h)==1:out.append(h)
 return out
def replay(r,cache):
 s=r['symbol'];bars=cache.setdefault(s,sorted(load(dp(s)),key=lambda x:dn(x.get('t') or x.get('date'))));dates=[dn(b.get('t') or b.get('date')) for b in bars]
 try:ei=dates.index(r['event_date']);xi=dates.index(r['entry_date'])
 except ValueError:return None,'DATE_MISSING'
 if xi<=ei or xi>=len(bars):return None,'T1_ENTRY'
 entry=f(bars[xi].get('o'));stop=f(r['stop_pre_entry'])
 if not(entry>stop>0):return None,'INVALID_STOP_OR_OPEN'
 targets=[h for h in swing_highs(bars,ei) if h>entry]
 if not targets:return None,'NO_PRE_EVENT_TARGET'
 target=min(targets);rr=(target-entry)/(entry-stop)
 if rr<RR_MIN:return None,'RR_LT_1_5'
 for j in range(xi+1,min(len(bars),xi+1+HOLD)):
  b=bars[j];o,h,l,c=f(b.get('o')),f(b.get('h')),f(b.get('l')),f(b.get('c'));d=dates[j]
  if o<=stop:exit_px=o;reason='GAP_SL'
  elif o>=target:exit_px=target;reason='TP_OPEN'
  elif l<=stop and h>=target:exit_px=stop;reason='SL_TP_COLLISION_STOP'
  elif l<=stop:exit_px=stop;reason='SL'
  elif h>=target:exit_px=target;reason='TP'
  elif j==min(len(bars),xi+1+HOLD)-1:exit_px=c;reason='TIME20'
  else:continue
  pnl=(exit_px/entry-1)*100-FEE
  return {'symbol':s,'event_date':r['event_date'],'entry_date':dates[xi],'entry':round(entry,6),'stop':round(stop,6),'target':round(target,6),'planned_rr':round(rr,6),'exit_date':d,'exit':round(exit_px,6),'reason':reason,'hold_bars':j-xi,'pnl_net_pct':round(pnl,6),'t1_violation':dates[xi]<=r['event_date'] or d<=dates[xi]},None
 return None,'NO_EXIT_BARS'
def metrics(rows):
 vals=[f(r['pnl_net_pct']) for r in rows];w=[x for x in vals if x>0];l=[x for x in vals if x<=0]
 by=defaultdict(list);mo=defaultdict(list);reasons=defaultdict(int)
 for r in rows:by[r['entry_date'][:4]].append(f(r['pnl_net_pct']));mo[r['entry_date'][:6]].append(f(r['pnl_net_pct']));reasons[r['reason']]+=1
 def st(x):
  a=[z for z in x if z>0];b=[z for z in x if z<=0]
  return {'n':len(x),'wr_pct':round(100*len(a)/len(x),4) if x else 0,'avg_net_pct':round(sum(x)/len(x),4) if x else 0,'profit_factor':round(sum(a)/abs(sum(b)),4) if b else None,'payoff':round((sum(a)/len(a))/abs(sum(b)/len(b)),4) if a and b else None}
 return {'n':len(rows),'symbols':len({r['symbol'] for r in rows}),'wr_pct':round(100*len(w)/len(vals),4) if vals else 0,'avg_net_pct':round(sum(vals)/len(vals),4) if vals else 0,'profit_factor':round(sum(w)/abs(sum(l)),4) if l else None,'payoff':round((sum(w)/len(w))/abs(sum(l)/len(l)),4) if w and l else None,'yearly':{k:st(v) for k,v in sorted(by.items())},'monthly':{k:st(v) for k,v in sorted(mo.items())},'exit_reasons':dict(sorted(reasons.items())),'t1_violations':sum(bool(r['t1_violation']) for r in rows)}
def main():
 x=json.loads(ORACLE.read_text());rp=Path(x['artifacts']['rows'])
 with rp.open() as h:seeds=list(csv.DictReader(h))
 cache={};trades=[];excluded=defaultdict(int)
 for r in seeds:
  t,e=replay(r,cache)
  if t:trades.append(t)
  else:excluded[e]+=1
 m=metrics(trades);years=defaultdict(int)
 for r in seeds:years[r['event_date'][:4]]+=1
 gate={'n':m['n']>=1000,'yearly_n':all(v.get('n',0)>=300 for v in m['yearly'].values()) and len(m['yearly'])>=2,'wr':m['wr_pct']>=55,'avg':m['avg_net_pct']>=0.5,'pf':(m['profit_factor'] or 0)>=1.15,'payoff':(m['payoff'] or 0)>=0.7,'every_year_avg':all(v['avg_net_pct']>0 for v in m['yearly'].values()),'t1':m['t1_violations']==0};gate['pass']=all(gate.values())
 OUT.mkdir(parents=True,exist_ok=True);tp=OUT/'v565_trades.csv'
 with tp.open('w',newline='') as h:
  w=csv.DictWriter(h,fieldnames=list(trades[0]) if trades else []);w.writeheader();w.writerows(trades)
 report={'version':'V565_FROZEN_STRICT_T1_REPLAY','generated_at':datetime.now().isoformat(timespec='seconds'),'source_oracle':str(rp),'contract':{'entry':'next daily open after event','exit_start':'entry+1 daily bar','stop':'pre-entry m60 sweep low*0.99','target':'nearest pre-event confirmed daily 3L/3R high above entry','rr_min':RR_MIN,'hold':HOLD,'fee_pct':FEE,'collision':'stop-first'},'seeds':len(seeds),'seed_year_counts':dict(sorted(years.items())),'executed':m,'excluded':dict(sorted(excluded.items())),'promotion_gate':gate,'writes':{'production':False,'frontend':False,'watchlist':False},'artifacts':{'dir':str(OUT),'trades':str(tp),'summary':str(OUT/'v565_report.json')}}
 (OUT/'v565_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({'status':'PASS','latest':str(LATEST),'seeds':len(seeds),'executed':m,'excluded':dict(excluded),'gate':gate},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
