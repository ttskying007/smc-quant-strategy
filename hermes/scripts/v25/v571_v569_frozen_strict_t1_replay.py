#!/usr/bin/env python3
"""One frozen strict-T+1 replay for V569 after the V570 identity Oracle pass."""
from __future__ import annotations
import csv, json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

ROOT=Path('/root/.hermes'); AUDIT=ROOT/'smc_audit'; DAILY=ROOT/'kline_cache'
SEED=AUDIT/'v569_margin_commitment_smc_response_seed_latest.json'; ORACLE=AUDIT/'v570_v569_independent_raw_oracle_latest.json'
LATEST=AUDIT/'v571_v569_frozen_strict_t1_replay_latest.json'; OUT=AUDIT/f'v571_v569_frozen_strict_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
YEARS=('2023','2024','2025'); FEE=0.20; HOLD=20
GATE={'n_min':1000,'year_n_min':300,'wr_pct_min':55.0,'avg_net_pct_min':0.5,'pf_min':1.15,'payoff_min':0.7,'each_year_avg_net_positive':True,'t1_violations':0}

def n(x:Any)->float|None:
 try:
  v=float(x);return v if math.isfinite(v) and v>0 else None
 except (TypeError,ValueError):return None

def bars(sym:str)->list[dict[str,Any]]:
 try:x=json.loads((DAILY/f'{sym.replace(".","_")}_daily_750.json').read_text())
 except (OSError,ValueError):return []
 out=[]
 for r in x if isinstance(x,list) else []:
  d=str(r.get('t') or r.get('date') or '')[:8];vs=[n(r.get(k)) for k in ('o','h','l','c')]
  if len(d)==8 and d.isdigit() and all(v is not None for v in vs):out.append({'d':d,'o':vs[0],'h':vs[1],'l':vs[2],'c':vs[3]})
 return sorted(out,key=lambda x:x['d'])

def highs(xs):
 out=[]
 for i in range(3,len(xs)-3):
  if xs[i]['h']>max(x['h'] for x in xs[i-3:i]) and xs[i]['h']>=max(x['h'] for x in xs[i+1:i+4]):out.append((i,i+3,xs[i]['h']))
 return out

def target(xs,signal_i,entry,stop):
 floor=entry+(entry-stop)*1.5;c=[]
 for i,confirm,price in highs(xs):
  if confirm>signal_i or price<floor:continue
  if any(x['h']>=price for x in xs[confirm+1:signal_i+1]):continue
  c.append(price)
 return min(c) if c else None

def exit_trade(xs,entry_i,entry,stop,tp):
 last=min(entry_i+HOLD,len(xs)-1)
 for i in range(entry_i+1,last+1):
  b=xs[i]
  if b['o']<=stop:return i,b['d'],b['o'],'SL_GAP_T1'
  if b['o']>=tp:return i,b['d'],b['o'],'TP_GAP_T1'
  if b['l']<=stop and b['h']>=tp:return i,b['d'],stop,'SL_TP_COLLISION_CONSERVATIVE_T1'
  if b['l']<=stop:return i,b['d'],stop,'SL_T1'
  if b['h']>=tp:return i,b['d'],tp,'TP_STRUCTURAL_T1'
 b=xs[last];return last,b['d'],b['c'],'TIME20'

def metrics(rows):
 if not rows:return {'n':0,'wr_pct':0.0,'avg_net_pct':0.0,'profit_factor':0.0,'payoff':0.0}
 p=[r['net_pnl_pct'] for r in rows];w=[x for x in p if x>0];loss=[x for x in p if x<=0]
 return {'n':len(p),'wr_pct':round(len(w)*100/len(p),4),'avg_net_pct':round(mean(p),4),'profit_factor':round(sum(w)/abs(sum(loss)),4) if loss else None,'payoff':round(mean(w)/abs(mean(loss)),4) if w and loss else None,'total_net_pct':round(sum(p),4),'avg_win_pct':round(mean(w),4) if w else None,'avg_loss_pct':round(mean(loss),4) if loss else None}

def main():
 oracle=json.loads(ORACLE.read_text())
 if oracle['decision']!='V570_ORACLE_PASS__ONE_FROZEN_STRICT_T1_REPLAY_AUTHORIZED':raise RuntimeError('V570 oracle must pass before replay')
 meta=json.loads(SEED.read_text())
 with Path(meta['artifacts']['seeds']).open(newline='',encoding='utf8') as h:seeds=list(csv.DictReader(h))
 by=defaultdict(list)
 for s in seeds:by[s['symbol']].append(s)
 OUT.mkdir(parents=True,exist_ok=False);trades=[];skip=Counter();t1=0
 for count,(sym,items) in enumerate(sorted(by.items()),1):
  xs=bars(sym);idx={x['d']:i for i,x in enumerate(xs)};busy=-1
  for s in sorted(items,key=lambda r:(r['planned_entry_date'],r['margin_date'])):
   si=idx.get(s['reclaim_date']);ei=idx.get(s['planned_entry_date'])
   if si is None or ei is None or ei!=si+1:skip['NO_EXACT_RECLAIM_NEXT_OPEN']+=1;continue
   if ei<=busy:skip['SERIAL_SYMBOL_POSITION_OPEN']+=1;continue
   if ei+1>=len(xs):skip['NO_T1_FORWARD_BAR']+=1;continue
   entry=xs[ei]['o'];stop=float(s['zone_low'])*.99
   if not(0<stop<entry):skip['INVALID_STRUCTURAL_STOP']+=1;continue
   tp=target(xs,si,entry,stop)
   if tp is None:skip['NO_UNCONSUMED_PREENTRY_TARGET_RR_1P5']+=1;continue
   xi,xd,xp,reason=exit_trade(xs,ei,entry,stop,tp)
   if xi<=ei:raise RuntimeError('T1 violation')
   busy=xi;net=(xp/entry-1)*100-FEE
   trades.append({'symbol':sym,'margin_date':s['margin_date'],'signal_date':s['reclaim_date'],'entry_date':xs[ei]['d'],'entry_price':round(entry,8),'stop_price':round(stop,8),'target_price':round(tp,8),'planned_rr':round((tp-entry)/(entry-stop),6),'exit_date':xd,'exit_price':round(xp,8),'exit_reason':reason,'hold_bars':xi-ei,'net_pnl_pct':round(net,6),'execution_contract':'MARGIN_M_PRIOR_TO_RESPONSE__RECLAIM_D_PLUS_1_OPEN__STRUCTURE_SL_TP__STRICT_T1__TIME20__FEE0P2'})
  if count%1000==0:print(json.dumps({'symbols':count,'trades':len(trades)}),flush=True)
 overall=metrics(trades);yearly={y:metrics([r for r in trades if r['entry_date'].startswith(y)]) for y in YEARS};exits=Counter(r['exit_reason'] for r in trades)
 checks={'n>=1000':overall['n']>=GATE['n_min'],'each_year_n>=300':all(yearly[y]['n']>=GATE['year_n_min'] for y in YEARS),'wr>=55':overall['wr_pct']>=GATE['wr_pct_min'],'avg_net>=0.5':overall['avg_net_pct']>=GATE['avg_net_pct_min'],'pf>=1.15':overall['profit_factor'] is not None and overall['profit_factor']>=GATE['pf_min'],'payoff>=0.7':overall['payoff'] is not None and overall['payoff']>=GATE['payoff_min'],'each_year_avg_net>0':all(yearly[y]['avg_net_pct']>0 for y in YEARS),'t1_violations==0':t1==0}
 out=OUT/'v571_frozen_t1_trades.csv'
 with out.open('w',newline='',encoding='utf8') as h:
  w=csv.DictWriter(h,fieldnames=list(trades[0]) if trades else ['symbol']);w.writeheader();w.writerows(trades)
 rep={'version':'V571_V569_ONE_FROZEN_STRICT_T1_REPLAY','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'input_contract':'V569 outcome-blind margin+SMC seeds after V570 independent raw Oracle identity equality.','frozen_execution_contract':'entry=first daily open after reclaim; stop=demand POI low*0.99; target=nearest pre-entry right-confirmed unconsumed daily swing high with RR>=1.5; exits start entry+1 only; gap-aware stop-first collision; time20; fee0.20%; serial symbol positions.','seed_count':len(seeds),'closed_trade_count':len(trades),'skip_counts':dict(skip),'overall':overall,'yearly':yearly,'exit_reason_counts':dict(exits),'promotion_gate':GATE,'promotion_checks':checks,'invariants':{'oracle_identity_pass':True,'all_targets_preentry':all(r['planned_rr']>=1.5 for r in trades),'t1_violations':t1,'all_writes_false':True,'search_count':1},'decision':'V571_RESEARCH_GATE_PASS__INDEPENDENT_METRIC_AUDIT_REQUIRED' if all(checks.values()) else 'V571_FROZEN_REPLAY_GATE_FAIL__CLOSE_V569_ONTOLOGY_NO_VARIANTS','artifacts':{'out_dir':str(OUT),'trades':str(out),'latest':str(LATEST),'v569':str(SEED),'v570':str(ORACLE)}}
 text=json.dumps(rep,ensure_ascii=False,indent=2);(OUT/'v571_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
