#!/usr/bin/env python3
"""V558 independent raw-bar oracle for V557 M15 confirmed-LH CHOCH identities."""
from __future__ import annotations
import csv,gzip,json,math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
ROOT=Path('/root/.hermes'); RAW=ROOT/'intraday_cache/raw_multitf_v536/source_raw/sina/m15'; AUD=ROOT/'smc_audit'
V553=AUD/'v553_daily_candidate_mtf_lineage_latest.json'; V557=AUD/'v557_daily_demand_confirmed_m15_choch_seed_latest.json'; OUT=AUD/f'v558_v557_independent_raw_oracle_no_outcome_{datetime.now():%Y%m%d_%H%M%S}';LATEST=AUD/'v558_v557_independent_raw_oracle_latest.json'
def n(x:Any)->float|None:
 try:x=float(x);return x if math.isfinite(x) and x>0 else None
 except (TypeError,ValueError):return None
def load(sym):
 try:
  with gzip.open(RAW/f'{sym.replace(".","_")}_m15.json.gz','rt',encoding='utf-8') as f:raw=json.load(f)
 except (OSError,ValueError):return [],{}
 xs=[]; days=defaultdict(list)
 for x in raw if isinstance(raw,list) else []:
  t=str(x.get('t') or '');v=[n(x.get(k)) for k in ('o','h','l','c')]
  if len(t)==14 and all(q is not None for q in v):days[t[:8]].append(len(xs));xs.append((t,*v))
 return xs,days
def peak(xs,i):
 h=xs[i][2]
 return h>max(xs[j][2] for j in range(i-3,i)) and h>=max(xs[j][2] for j in range(i+1,i+4))
def accept(xs,ix,c):
 session=ix.get(c['reclaim_date'],[]); low=float(c['zone_low']);high=float(c['zone_high'])
 touch=next((i for i in session if xs[i][3]<=high and xs[i][2]>=low),None)
 if touch is None:return None
 reclaim=next((i for i in session if i>=touch and xs[i][4]>=high),None)
 if reclaim is None:return None
 highs=[i for i in range(3,touch-3) if peak(xs,i)]
 anchor=next((highs[k] for k in range(len(highs)-1,0,-1) if xs[highs[k]][2]<xs[highs[k-1]][2]),None)
 if anchor is None:return None
 hit=next((i for i in session if i>reclaim and xs[i][4]>xs[anchor][2]*1.001),None)
 if hit is not None and not any(xs[i][4]<low for i in session if i>=hit):return (c['symbol'],c['event_date'],c['reclaim_date'],c['planned_entry_date'])
 return None
def main():
 source=json.loads(V553.read_text()); verified=json.loads(V557.read_text())
 with Path(source['artifacts']['candidate_lineage_csv']).open(newline='',encoding='utf-8') as f: rows=list(csv.DictReader(f))
 groups=defaultdict(list)
 for r in rows:groups[r['symbol']].append(r)
 got=set()
 for no,(sym,items) in enumerate(sorted(groups.items()),1):
  xs,ix=load(sym)
  for r in items:
   z=accept(xs,ix,r)
   if z:got.add(z)
  if no%500==0:print(json.dumps({'symbols':no,'oracle':len(got)}),flush=True)
 with Path(verified['artifacts']['confirmed_seeds']).open(newline='',encoding='utf-8') as f: expected={(r['symbol'],r['event_date'],r['reclaim_date'],r['planned_entry_date']) for r in csv.DictReader(f)}
 missing=sorted(expected-got);extra=sorted(got-expected);OUT.mkdir(parents=True,exist_ok=False)
 for name,values in [('missing.csv',missing),('extra.csv',extra)]:
  with (OUT/name).open('w',newline='',encoding='utf-8') as f:
   w=csv.writer(f);w.writerow(['symbol','event_date','reclaim_date','planned_entry_date']);w.writerows(values)
 report={'version':'V558_V557_INDEPENDENT_RAW_ORACLE_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'oracle_contract':'Independently reloads raw M15, evaluates touch/reclaim and a 3L/3R lower-high break before next-day entry; outcome files are never opened.','v557_expected_identities':len(expected),'oracle_identities':len(got),'missing':len(missing),'extra':len(extra),'identity_match':not missing and not extra,'invariants':{'no_outcome_files_read':True,'oracle_does_not_import_v557_logic':True},'decision':'IDENTITY_PASS__FROZEN_T1_REPLAY_ALLOWED' if not missing and not extra else 'IDENTITY_FAIL__REPLAY_BLOCKED','artifacts':{'out_dir':str(OUT),'latest':str(LATEST)}}
 text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
