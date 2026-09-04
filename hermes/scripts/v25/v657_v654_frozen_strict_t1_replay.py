#!/usr/bin/env python3
"""The sole frozen strict-T+1 replay for V654 after exact V656 Oracle equality."""
from __future__ import annotations
import csv,json,math
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any
ROOT=Path('/root/.hermes');AUD=ROOT/'smc_audit';DAILY=ROOT/'kline_cache';SEED=AUD/'v655_two_sided_leverage_convergence_fvg_seed_latest.json';ORACLE=AUD/'v656_v654_independent_raw_oracle_latest.json';LATEST=AUD/'v657_v654_frozen_strict_t1_replay_latest.json';OUT=AUD/f'v657_v654_frozen_strict_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}';YEARS=('2023','2024','2025');FEE=.20;HOLD=20;G={'n_min':1000,'year_n_min':300,'wr_pct_min':55.,'avg_net_pct_min':.5,'pf_min':1.15,'payoff_min':.7}
def n(x:Any)->float|None:
 try:
  v=float(x);return v if math.isfinite(v) and v>0 else None
 except (ValueError,TypeError):return None
def bars(sym):
 try:a=json.loads((DAILY/f'{sym.replace(".","_")}_daily_750.json').read_text())
 except (OSError,ValueError):return []
 z=[]
 for r in a if isinstance(a,list) else []:
  d=str(r.get('t') or r.get('date') or '')[:8];v=[n(r.get(k)) for k in ('o','h','l','c')]
  if len(d)==8 and d.isdigit() and all(v):z.append({'d':d,'o':v[0],'h':v[1],'l':v[2],'c':v[3]})
 return sorted(z,key=lambda r:r['d'])
def pivots(x):return [(i,i+3,x[i]['h']) for i in range(3,len(x)-3) if x[i]['h']>max(r['h'] for r in x[i-3:i]) and x[i]['h']>=max(r['h'] for r in x[i+1:i+4])]
def target(x,signal,entry,stop):
 floor=entry+(entry-stop)*1.5;c=[]
 for i,confirm,h in pivots(x):
  if confirm>signal or h<floor or any(r['h']>=h for r in x[confirm+1:signal+1]):continue
  c.append(h)
 return min(c) if c else None
def exit(x,e,entry,stop,tp):
 last=min(e+HOLD,len(x)-1)
 for i in range(e+1,last+1):
  b=x[i]
  if b['o']<=stop:return i,b['o'],'SL_GAP_T1'
  if b['o']>=tp:return i,b['o'],'TP_GAP_T1'
  if b['l']<=stop and b['h']>=tp:return i,stop,'SL_TP_COLLISION_CONSERVATIVE_T1'
  if b['l']<=stop:return i,stop,'SL_T1'
  if b['h']>=tp:return i,tp,'TP_STRUCTURAL_T1'
 return last,x[last]['c'],'TIME20'
def metrics(a):
 p=[r['net_pnl_pct'] for r in a];w=[v for v in p if v>0];l=[v for v in p if v<=0]
 return {'n':len(a),'wr_pct':round(100*len(w)/len(a),4) if a else 0.,'avg_net_pct':round(mean(p),4) if p else 0.,'profit_factor':round(sum(w)/abs(sum(l)),4) if w and l else None,'payoff':round(mean(w)/abs(mean(l)),4) if w and l else None}
def main():
 assert json.loads(ORACLE.read_text())['decision']=='V656_ORACLE_PASS__ONE_FROZEN_STRICT_T1_REPLAY_AUTHORIZED'
 meta=json.loads(SEED.read_text())
 with Path(meta['artifacts']['seeds']).open(newline='',encoding='utf8') as h:seeds=list(csv.DictReader(h))
 by=defaultdict(list)
 for s in seeds:by[s['symbol']].append(s)
 OUT.mkdir(parents=True,exist_ok=False);trades=[];skip=Counter();t1=0
 for sym,items in sorted(by.items()):
  x=bars(sym);idx={r['d']:i for i,r in enumerate(x)};busy=-1
  for s in sorted(items,key=lambda r:(r['planned_entry_date'],r['event_date'])):
   si=idx.get(s['fvg_reclaim_date']);ei=idx.get(s['planned_entry_date'])
   if si is None or ei!=si+1:skip['NO_EXACT_NEXT_OPEN']+=1;continue
   if ei<=busy:skip['SERIAL_SYMBOL_POSITION_OPEN']+=1;continue
   if ei+1>=len(x):skip['NO_T1_BAR']+=1;continue
   entry=x[ei]['o'];stop=float(s['fvg_lower'])*.99
   if not 0<stop<entry:skip['INVALID_FVG_STRUCTURAL_STOP']+=1;continue
   tp=target(x,si,entry,stop)
   if tp is None:skip['NO_UNCONSUMED_PREENTRY_TARGET_RR_1P5']+=1;continue
   xi,xp,reason=exit(x,ei,entry,stop,tp)
   if xi<=ei:raise RuntimeError('T1_VIOLATION')
   busy=xi;trades.append({'symbol':sym,'event_date':s['event_date'],'signal_date':s['fvg_reclaim_date'],'entry_date':x[ei]['d'],'entry_price':round(entry,8),'stop_price':round(stop,8),'target_price':round(tp,8),'planned_rr':round((tp-entry)/(entry-stop),6),'exit_date':x[xi]['d'],'exit_price':round(xp,8),'exit_reason':reason,'hold_bars':xi-ei,'net_pnl_pct':round((xp/entry-1)*100-FEE,6)})
 overall=metrics(trades);yearly={y:metrics([r for r in trades if r['entry_date'].startswith(y)]) for y in YEARS};checks={'n>=1000':overall['n']>=G['n_min'],'each_year_n>=300':all(yearly[y]['n']>=G['year_n_min'] for y in YEARS),'wr>=55':overall['wr_pct']>=G['wr_pct_min'],'avg_net>=0.5':overall['avg_net_pct']>=G['avg_net_pct_min'],'pf>=1.15':overall['profit_factor'] is not None and overall['profit_factor']>=G['pf_min'],'payoff>=0.7':overall['payoff'] is not None and overall['payoff']>=G['payoff_min'],'each_year_avg_net>0':all(yearly[y]['avg_net_pct']>0 for y in YEARS),'t1_violations==0':t1==0}
 with (OUT/'v657_frozen_t1_trades.csv').open('w',newline='',encoding='utf8') as h:w=csv.DictWriter(h,fieldnames=list(trades[0]) if trades else ['symbol']);w.writeheader();w.writerows(trades)
 rep={'version':'V657_V654_ONE_FROZEN_STRICT_T1_REPLAY','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'input_contract':'V655 outcome-blind seeds only after V656 exact raw Oracle equality.','frozen_execution_contract':'entry=next open after FVG reclaim; stop=FVG lower*0.99; target=nearest unconsumed pre-entry right-confirmed swing high with RR>=1.5; exits from entry+1 only; gap-aware conservative stop-first collision; fee0.20%; time20; serial symbols.','seed_count':len(seeds),'closed_trade_count':len(trades),'skip_counts':dict(skip),'overall':overall,'yearly':yearly,'exit_reason_counts':dict(Counter(r['exit_reason'] for r in trades)),'promotion_gate':G,'promotion_checks':checks,'invariants':{'oracle_identity_pass':True,'all_targets_preentry':all(r['planned_rr']>=1.5 for r in trades),'t1_violations':t1,'all_writes_false':True,'search_count':1},'decision':'V657_RESEARCH_GATE_PASS__INDEPENDENT_METRIC_AUDIT_REQUIRED' if all(checks.values()) else 'V657_FROZEN_REPLAY_GATE_FAIL__CLOSE_V654_ONTOLOGY_NO_VARIANTS','artifacts':{'out_dir':str(OUT),'trades':str(OUT/'v657_frozen_t1_trades.csv'),'latest':str(LATEST)}}
 text=json.dumps(rep,ensure_ascii=False,indent=2);(OUT/'v657_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
