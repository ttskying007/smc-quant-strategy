#!/usr/bin/env python3
"""V565 single frozen strict-T+1 replay for V563/V564 identities.

Execution was fixed before this script opens raw forward bars: D+1 daily open;
stop 0.5% below the intraday raid low; nearest visible, unconsumed confirmed
3L/3R daily swing high with planned RR >=1.5; exits begin no earlier than the
next trading date, conservative stop-first, 20 daily sessions, 0.20% fee.
"""
from __future__ import annotations
import csv,gzip,json,math
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; RAW=ROOT/'intraday_cache/raw_multitf_v536/source_raw/sina/daily'
V563=AUD/'v563_industry_bos_opening_liquidity_seed_latest.json';V564=AUD/'v564_v563_independent_raw_oracle_latest.json';OUT=AUD/f'v565_v563_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}';LATEST=AUD/'v565_v563_frozen_t1_replay_latest.json';FEE=.002;HOLD=20;RR=1.5

def n(x):
 try:
  y=float(x);return y if math.isfinite(y) and y>0 else None
 except (TypeError,ValueError):return None
def bars(sym):
 try:
  with gzip.open(RAW/f'{sym.replace(".","_")}_daily.json.gz','rt') as h:raw=json.load(h)
 except (OSError,ValueError):return []
 out=[]
 for x in raw if isinstance(raw,list) else []:
  vs=[n(x.get(k)) for k in ('o','h','l','c')];d=str(x.get('t') or '')[:8]
  if len(d)==8 and all(v is not None for v in vs):out.append({'d':d,'o':vs[0],'h':vs[1],'l':vs[2],'c':vs[3]})
 return sorted(out,key=lambda x:x['d'])
def high(x,i):return i>=3 and i+3<len(x) and x[i]['h']>max(z['h'] for z in x[i-3:i]) and x[i]['h']>=max(z['h'] for z in x[i+1:i+4])
def target(x,ei,entry,stop):
 need=entry+(entry-stop)*RR;found=[]
 for i in range(3,ei-3):
  if high(x,i) and x[i]['h']>=need and not any(z['h']>=x[i]['h'] for z in x[i+1:ei]):found.append(x[i]['h'])
 return min(found,default=None)
def metric(rows):
 if not rows:return {'n':0}
 p=[r['net_pct'] for r in rows];w=[v for v in p if v>0];loss=[v for v in p if v<=0]
 return {'n':len(rows),'wr_pct':round(100*len(w)/len(rows),4),'avg_net_pct':round(sum(p)/len(rows),4),'profit_factor':round(sum(w)/abs(sum(loss)),4) if loss and sum(loss) else None,'payoff':round((sum(w)/len(w))/abs(sum(loss)/len(loss)),4) if w and loss else None,'exit_counts':dict(Counter(r['exit_reason'] for r in rows))}
def main():
 assert json.loads(V564.read_text())['identity_match'] is True
 source=json.loads(V563.read_text())
 with Path(source['artifacts']['seeds']).open(newline='') as h:seeds=list(csv.DictReader(h))
 groups=defaultdict(list)
 for r in seeds:groups[r['symbol']].append(r)
 OUT.mkdir(parents=True,exist_ok=False);trades=[];missing=[];no_target=[];viol=[]
 for sym,items in groups.items():
  xs=bars(sym);pos={b['d']:i for i,b in enumerate(xs)}
  for r in items:
   ei=pos.get(r['eligible_entry_date'])
   if ei is None or ei+1>=len(xs):missing.append({'symbol':sym,'event_date':r['event_date'],'reason':'MISSING_ENTRY_OR_FORWARD'});continue
   entry=xs[ei]['o'];stop=float(r['m15_opening_raid_low'])*.995;tar=target(xs,ei,entry,stop);base={'symbol':sym,'event_date':r['event_date'],'entry_date':r['eligible_entry_date'],'entry':round(entry,6),'stop':round(stop,6)}
   if stop>=entry or tar is None:no_target.append({**base,'reason':'INVALID_STOP_OR_NO_UNCONSUMED_PREENTRY_TARGET_RR_1_5'});continue
   last=min(len(xs)-1,ei+HOLD);xi=last;price=xs[last]['c'];reason='TIME20'
   for j in range(ei+1,last+1):
    if xs[j]['l']<=stop:xi=j;price=stop;reason='SL';break
    if xs[j]['h']>=tar:xi=j;price=tar;reason='TP_UNCONSUMED_STRUCTURAL';break
   if xs[xi]['d']<=xs[ei]['d']:viol.append({**base,'exit_date':xs[xi]['d']});continue
   trades.append({**base,'target':round(tar,6),'planned_rr':round((tar-entry)/(entry-stop),4),'exit_date':xs[xi]['d'],'exit_price':round(price,6),'exit_reason':reason,'hold_bars':xi-ei,'net_pct':round((price/entry-1-FEE)*100,4),'year':r['eligible_entry_date'][:4]})
 for name,data in [('v565_frozen_trades.csv',trades),('v565_no_target.csv',no_target),('v565_missing.csv',missing)]:
  with (OUT/name).open('w',newline='',encoding='utf-8') as h:
   w=csv.DictWriter(h,fieldnames=list(data[0]) if data else ['symbol']);w.writeheader();w.writerows(data)
 yearly={y:metric([r for r in trades if r['year']==y]) for y in ('2025','2026')};allm=metric(trades)
 checks={'n>=1000':allm['n']>=1000,'each_year_n>=300':all(yearly[y]['n']>=300 for y in yearly),'wr>=55':allm['wr_pct']>=55,'avg_net>=0.5':allm['avg_net_pct']>=.5,'pf>=1.15':(allm['profit_factor'] or 0)>=1.15,'payoff>=0.7':(allm['payoff'] or 0)>=.7,'each_year_avg_net>0':all(yearly[y].get('avg_net_pct',0)>0 for y in yearly),'t1_violations==0':not viol}
 report={'version':'V565_V563_FROZEN_STRICT_T1_REPLAY','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'seed_count':len(seeds),'execution_contract':'D+1 daily open; stop=opening M15 raid low*0.995; nearest unconsumed pre-entry confirmed 3L/3R daily high with planned RR>=1.5; stop-first; exits earliest D+2; hold=20; fee=0.20%; no selector/bucket search','coverage':{'executed':len(trades),'no_target_or_invalid_stop':len(no_target),'missing_source':len(missing)},'overall':allm,'yearly':yearly,'t1_violations':len(viol),'promotion_checks':checks,'promotion_gate_pass':all(checks.values()),'invariants':{'v564_identity_match':True,'all_exits_after_entry':not viol,'all_targets_unconsumed_at_entry':True,'no_parameter_or_bucket_search':True},'decision':'FROZEN_REPLAY_COMPLETE__RESEARCH_ONLY__NO_PRODUCTION_WRITE','artifacts':{'out_dir':str(OUT),'trades':str(OUT/'v565_frozen_trades.csv'),'latest':str(LATEST)}}
 text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v565_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
