#!/usr/bin/env python3
"""V559 one frozen strict-T+1 replay for independently verified V557 seeds.
Entry=next daily open; SL=demand low*0.99; TP=nearest unconsumed, pre-entry,
3L/3R daily swing high with RR>=1.5.  No selector/search/production writes.
"""
from __future__ import annotations
import csv,gzip,json,math
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
ROOT=Path('/root/.hermes');RAW=ROOT/'intraday_cache/raw_multitf_v536/source_raw/sina/daily';AUD=ROOT/'smc_audit';V557=AUD/'v557_daily_demand_confirmed_m15_choch_seed_latest.json';V558=AUD/'v558_v557_independent_raw_oracle_latest.json';OUT=AUD/f'v559_confirmed_m15_choch_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}';LATEST=AUD/'v559_confirmed_m15_choch_frozen_t1_replay_latest.json';FEE=.002;HOLD=20;RR=1.5
def n(x:Any)->float|None:
 try:x=float(x);return x if math.isfinite(x) and x>0 else None
 except (TypeError,ValueError):return None
def load(sym):
 try:
  with gzip.open(RAW/f'{sym.replace(".","_")}_daily.json.gz','rt',encoding='utf-8') as f:raw=json.load(f)
 except (OSError,ValueError):return []
 out=[]
 for x in raw if isinstance(raw,list) else []:
  z=[n(x.get(k)) for k in ('o','h','l','c')];d=str(x.get('d') or x.get('t') or '')[:8]
  if len(d)==8 and all(v is not None for v in z):out.append({'d':d,'o':z[0],'h':z[1],'l':z[2],'c':z[3]})
 return sorted(out,key=lambda x:x['d'])
def peak(xs,i):return i>=3 and i+3<len(xs) and xs[i]['h']>max(x['h'] for x in xs[i-3:i]) and xs[i]['h']>=max(x['h'] for x in xs[i+1:i+4])
def target(xs,ei,entry,stop):
 need=entry+(entry-stop)*RR; options=[]
 for i in range(3,ei-3):
  if peak(xs,i) and xs[i]['h']>=need and not any(x['h']>=xs[i]['h'] for x in xs[i+1:ei]):options.append(xs[i]['h'])
 return min(options,default=None)
def metrics(rows):
 if not rows:return {'n':0}
 p=[r['net_pct'] for r in rows];w=[x for x in p if x>0];l=[x for x in p if x<=0]
 return {'n':len(rows),'wr_pct':round(100*len(w)/len(rows),4),'avg_net_pct':round(sum(p)/len(rows),4),'profit_factor':round(sum(w)/abs(sum(l)),4) if l and sum(l) else None,'payoff':round((sum(w)/len(w))/abs(sum(l)/len(l)),4) if w and l else None,'exit_counts':dict(Counter(r['exit_reason'] for r in rows))}
def main():
 assert json.loads(V558.read_text())['identity_match'] is True
 source=json.loads(V557.read_text())
 with Path(source['artifacts']['confirmed_seeds']).open(newline='',encoding='utf-8') as f: seeds=list(csv.DictReader(f))
 groups=defaultdict(list)
 for r in seeds:groups[r['symbol']].append(r)
 OUT.mkdir(parents=True,exist_ok=False);trades=[];no_target=[];missing=[];viol=[]
 for sym,items in sorted(groups.items()):
  xs=load(sym); dates={x['d']:i for i,x in enumerate(xs)}
  for r in items:
   ei=dates.get(r['planned_entry_date'])
   if ei is None or ei+1>=len(xs):missing.append({**r,'reason':'MISSING_ENTRY_OR_FUTURE'});continue
   entry=xs[ei]['o'];stop=float(r['structural_stop']);tar=target(xs,ei,entry,stop);base={'symbol':sym,'event_date':r['event_date'],'reclaim_date':r['reclaim_date'],'entry_date':r['planned_entry_date'],'entry':round(entry,6),'stop':round(stop,6)}
   if tar is None:no_target.append({**base,'reason':'NO_UNCONSUMED_PREENTRY_TARGET_RR_1_5'});continue
   last=min(len(xs)-1,ei+HOLD);exit_i=last;price=xs[last]['c'];why='TIME20'
   for j in range(ei+1,last+1):
    if xs[j]['l']<=stop:exit_i=j;price=stop;why='SL';break
    if xs[j]['h']>=tar:exit_i=j;price=tar;why='TP_UNCONSUMED_STRUCTURAL';break
   if xs[exit_i]['d']<=xs[ei]['d']:viol.append({**base,'exit_date':xs[exit_i]['d']});continue
   trades.append({**base,'target':round(tar,6),'planned_rr':round((tar-entry)/(entry-stop),4),'exit_date':xs[exit_i]['d'],'exit_price':round(price,6),'exit_reason':why,'hold_bars':exit_i-ei,'net_pct':round((price/entry-1-FEE)*100,4),'year':r['planned_entry_date'][:4]})
 for name,rows in [('v559_frozen_trades.csv',trades),('v559_no_unconsumed_target.csv',no_target),('v559_missing.csv',missing)]:
  with (OUT/name).open('w',newline='',encoding='utf-8') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['symbol']);w.writeheader();w.writerows(rows)
 report={'version':'V559_CONFIRMED_M15_CHOCH_FROZEN_T1_REPLAY','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'seed_count':len(seeds),'execution_contract':'next daily open; stop=demand low*0.99; nearest unconsumed pre-entry 3L/3R high with RR>=1.5; stop-first; earliest exit next trading day; hold=20; fee=0.20%','coverage':{'executed':len(trades),'no_unconsumed_target':len(no_target),'missing_source':len(missing)},'overall':metrics(trades),'yearly':{y:metrics([r for r in trades if r['year']==y]) for y in sorted({r['year'] for r in trades})},'t1_violations':len(viol),'invariants':{'v558_identity_match':True,'all_exits_after_entry':not viol,'all_targets_unconsumed_at_entry':True,'no_parameter_or_bucket_search':True},'production_gate_pass':False,'decision':'FROZEN_REPLAY_COMPLETE__RESEARCH_RESULT_ONLY__NO_PRODUCTION_AUTHORIZATION','artifacts':{'out_dir':str(OUT),'trades':str(OUT/'v559_frozen_trades.csv'),'latest':str(LATEST)}}
 text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
