#!/usr/bin/env python3
"""V555 one frozen strict-T+1 diagnostic replay for V554-verified identities.

Separates causal signal confirmation from pre-entry structural target-space and
execution. No filtering, threshold search, production/frontend/watchlist writes.
"""
from __future__ import annotations
import csv,gzip,json,math
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
ROOT=Path('/root/.hermes'); RAW=ROOT/'intraday_cache/raw_multitf_v536/source_raw/sina/daily'; AUD=ROOT/'smc_audit'
V553=AUD/'v553_daily_candidate_mtf_lineage_latest.json'; V554=AUD/'v554_daily_m15_takeover_independent_oracle_latest.json'; OUT=AUD/f'v555_daily_m15_takeover_frozen_t1_diagnostic_no_write_{datetime.now():%Y%m%d_%H%M%S}'; LATEST=AUD/'v555_daily_m15_takeover_frozen_t1_diagnostic_latest.json'
FEE=.002; HOLD=20; RR=1.5

def n(x:Any)->float|None:
 try:x=float(x);return x if math.isfinite(x) and x>0 else None
 except (TypeError,ValueError):return None

def bars(sym:str)->list[dict]:
 p=RAW/f'{sym.replace(".","_")}_daily.json.gz'
 try:
  with gzip.open(p,'rt',encoding='utf-8') as f:r=json.load(f)
 except (OSError,ValueError):return []
 out=[]
 for x in r if isinstance(r,list) else []:
  z=[n(x.get(k)) for k in ('o','h','l','c')];d=str(x.get('d') or x.get('t') or '')[:8]
  if len(d)==8 and all(v is not None for v in z):out.append({'d':d,'o':z[0],'h':z[1],'l':z[2],'c':z[3]})
 return sorted(out,key=lambda x:x['d'])

def target(xs:list[dict],ei:int,entry:float,stop:float)->float|None:
 # A swing high is known only after its 3 right-side bars and must be visible pre-entry.
 highs=[]
 for i in range(3,ei-3):
  h=xs[i]['h']
  if h>max(x['h'] for x in xs[i-3:i]) and h>=max(x['h'] for x in xs[i+1:i+4]):highs.append(h)
 need=entry+(entry-stop)*RR
 return min((h for h in highs if h>=need),default=None)

def metric(rows:list[dict])->dict:
 if not rows:return {'n':0}
 pnl=[r['net_pct'] for r in rows];wins=[x for x in pnl if x>0];loss=[x for x in pnl if x<=0]
 return {'n':len(rows),'wr_pct':round(100*len(wins)/len(rows),4),'avg_net_pct':round(sum(pnl)/len(rows),4),'profit_factor':round(sum(wins)/abs(sum(loss)),4) if loss and sum(loss) else None,'payoff':round((sum(wins)/len(wins))/abs(sum(loss)/len(loss)),4) if wins and loss else None,'exit_counts':dict(Counter(r['exit_reason'] for r in rows))}

def main():
 assert json.loads(V554.read_text())['identity_match'] is True
 v=json.loads(V553.read_text()); candidates=[]
 with Path(v['artifacts']['candidate_lineage_csv']).open(newline='',encoding='utf-8') as f:
  for r in csv.DictReader(f):
   if r.get('m15_confirmation_label')=='M15_TAKEOVER_CONFIRMED':candidates.append(r)
 OUT.mkdir(parents=True,exist_ok=False); cache={}; executed=[]; no_target=[]; missed=[]; violations=[]
 for r in candidates:
  sym=r['symbol']; xs=cache.setdefault(sym,bars(sym)); date=r['planned_entry_date']; ei=next((i for i,x in enumerate(xs) if x['d']==date),None)
  if ei is None or ei+1>=len(xs):missed.append({'symbol':sym,'planned_entry_date':date,'reason':'MISSING_ENTRY_OR_FUTURE'});continue
  entry=xs[ei]['o']; stop=float(r['structural_stop']); tar=target(xs,ei,entry,stop)
  base={'symbol':sym,'event_date':r['event_date'],'reclaim_date':r['reclaim_date'],'entry_date':date,'entry':round(entry,6),'stop':round(stop,6)}
  if tar is None:
   no_target.append({**base,'reason':'NO_PREENTRY_CONFIRMED_TARGET_RR_1_5'});continue
  last=min(len(xs)-1,ei+HOLD); xp=xs[last]['c'];xi=last;reason='TIME20'
  for j in range(ei+1,last+1):
   if xs[j]['l']<=stop:xp=stop;xi=j;reason='SL';break
   if xs[j]['h']>=tar:xp=tar;xi=j;reason='TP_STRUCTURAL';break
  if xs[xi]['d']<=xs[ei]['d']:violations.append({**base,'exit_date':xs[xi]['d']});continue
  net=(xp/entry-1-FEE)*100
  executed.append({**base,'target':round(tar,6),'planned_rr':round((tar-entry)/(entry-stop),4),'exit_date':xs[xi]['d'],'exit_price':round(xp,6),'exit_reason':reason,'hold_bars':xi-ei,'net_pct':round(net,4),'year':date[:4]})
 years={y:metric([r for r in executed if r['year']==y]) for y in sorted({r['year'] for r in executed})}
 report={'version':'V555_DAILY_M15_TAKEOVER_FROZEN_T1_DIAGNOSTIC','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'input_identities':len(candidates),'frozen_execution':'next daily open; stop=daily demand low*0.99; nearest pre-entry 3L/3R confirmed swing high with RR>=1.5; earliest exit next trading date only; stop-first; 20 sessions; fee=0.20%','signal_vs_execution':{'m15_confirmed':len(candidates),'no_preentry_structural_target_rr_1_5':len(no_target),'executed':len(executed),'missing_source_rows':len(missed)},'overall':metric(executed),'yearly':years,'t1_violations':len(violations),'invariants':{'v554_identity_match':True,'all_exits_after_entry':not violations,'no_parameter_or_bucket_search':True},'decision':'V555_FROZEN_DIAGNOSTIC_COMPLETE__NO_PRODUCTION_AUTHORIZATION','artifacts':{'out_dir':str(OUT),'trades':str(OUT/'v555_frozen_rows.csv'),'no_target':str(OUT/'v555_signal_confirmed_no_target.csv'),'latest':str(LATEST)}}
 for name,rows in [('v555_frozen_rows.csv',executed),('v555_signal_confirmed_no_target.csv',no_target),('v555_missing.csv',missed)]:
  with (OUT/name).open('w',newline='',encoding='utf-8') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['symbol']);w.writeheader();w.writerows(rows)
 text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v555_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
