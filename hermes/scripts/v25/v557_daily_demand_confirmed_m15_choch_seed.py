#!/usr/bin/env python3
"""V557 — correct V553's M15 'MSS' into a confirmed pre-touch CHOCH seed.

No outcome data is read.  The daily candidate contract is frozen from V553.
A valid lower-timeframe transition must break a 3L/3R swing high that was
confirmed before the daily-demand touch, and that high must be a lower high
than the immediately preceding confirmed swing high.
"""
from __future__ import annotations
import bisect,csv,gzip,json,math
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
ROOT=Path('/root/.hermes'); RAW=ROOT/'intraday_cache/raw_multitf_v536/source_raw/sina/m15'; AUD=ROOT/'smc_audit'
V553=AUD/'v553_daily_candidate_mtf_lineage_latest.json'; OUT=AUD/f'v557_daily_demand_confirmed_m15_choch_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'; LATEST=AUD/'v557_daily_demand_confirmed_m15_choch_seed_latest.json'

def num(x:Any)->float|None:
 try:
  x=float(x); return x if math.isfinite(x) and x>0 else None
 except (TypeError,ValueError): return None

def bars(sym:str)->list[dict]:
 try:
  with gzip.open(RAW/f'{sym.replace(".","_")}_m15.json.gz','rt',encoding='utf-8') as f:r=json.load(f)
 except (OSError,ValueError): return []
 o=[]
 for x in r if isinstance(r,list) else []:
  z=[num(x.get(k)) for k in ('o','h','l','c')];t=str(x.get('t') or '')
  if len(t)==14 and all(v is not None for v in z):o.append({'t':t,'d':t[:8],'o':z[0],'h':z[1],'l':z[2],'c':z[3]})
 return sorted(o,key=lambda x:x['t'])

def swing_high(xs:list[dict],i:int)->bool:
 return i>=3 and i+3<len(xs) and xs[i]['h']>max(x['h'] for x in xs[i-3:i]) and xs[i]['h']>=max(x['h'] for x in xs[i+1:i+4])

def index_symbol(sym:str)->dict:
 xs=bars(sym); by_day=defaultdict(list)
 for i,x in enumerate(xs): by_day[x['d']].append(i)
 return {'xs':xs,'by_day':by_day,'highs':[i for i in range(3,len(xs)-3) if swing_high(xs,i)]}

def classify(state:dict,c:dict)->tuple[str,dict]:
 xs=state['xs']; day=c['reclaim_date']; zl=float(c['zone_low']); zh=float(c['zone_high'])
 session=state['by_day'].get(day,[])
 if len(session)<4:return 'M15_MISSING_OR_SHORT_SESSION',{}
 touch=next((i for i in session if xs[i]['l']<=zh and xs[i]['h']>=zl),None)
 if touch is None:return 'M15_NO_ZONE_TOUCH',{}
 reclaim=next((i for i in session if i>=touch and xs[i]['c']>=zh),None)
 if reclaim is None:return 'M15_TOUCH_NO_RECLAIM',{'m15_touch_time':xs[touch]['t']}
 # The index list was computed once; anchor must be confirmed three bars before touch.
 stop=bisect.bisect_left(state['highs'],touch-3); hs=state['highs'][:stop]
 if len(hs)<2:return 'M15_NO_CONFIRMED_PRETOUCH_LOWER_HIGH',{'m15_touch_time':xs[touch]['t'],'m15_reclaim_time':xs[reclaim]['t']}
 anchor=next((hs[j] for j in range(len(hs)-1,0,-1) if xs[hs[j]]['h']<xs[hs[j-1]]['h']),None)
 if anchor is None:return 'M15_NO_CONFIRMED_PRETOUCH_LOWER_HIGH',{'m15_touch_time':xs[touch]['t'],'m15_reclaim_time':xs[reclaim]['t']}
 mss=next((i for i in session if i>reclaim and xs[i]['c']>xs[anchor]['h']*1.001),None)
 if mss is None:return 'M15_RECLAIM_NO_CONFIRMED_LH_CHOCH',{'m15_touch_time':xs[touch]['t'],'m15_reclaim_time':xs[reclaim]['t'],'m15_anchor_time':xs[anchor]['t'],'m15_anchor_high':round(xs[anchor]['h'],6)}
 if any(xs[i]['c']<zl for i in session if i>=mss):return 'M15_CHOCH_THEN_ZONE_FAIL',{'m15_touch_time':xs[touch]['t'],'m15_reclaim_time':xs[reclaim]['t'],'m15_anchor_time':xs[anchor]['t'],'m15_anchor_high':round(xs[anchor]['h'],6),'m15_choch_time':xs[mss]['t']}
 return 'M15_CONFIRMED_LH_CHOCH_TAKEOVER',{'m15_touch_time':xs[touch]['t'],'m15_reclaim_time':xs[reclaim]['t'],'m15_anchor_time':xs[anchor]['t'],'m15_anchor_high':round(xs[anchor]['h'],6),'m15_choch_time':xs[mss]['t']}

def main():
 v=json.loads(V553.read_text())
 with Path(v['artifacts']['candidate_lineage_csv']).open(newline='',encoding='utf-8') as f:src=list(csv.DictReader(f))
 OUT.mkdir(parents=True,exist_ok=False);rows=[]; grouped=defaultdict(list)
 for c in src: grouped[c['symbol']].append(c)
 for number,(sym,items) in enumerate(sorted(grouped.items()),1):
  state=index_symbol(sym)
  for c in items:
   label,e=classify(state,c); rows.append({**c,'v557_m15_label':label,**e})
  if number%500==0: print(json.dumps({'symbols':number,'rows':len(rows)},ensure_ascii=False),flush=True)
 rows.sort(key=lambda x:(x['planned_entry_date'],x['symbol'],x['event_date']))
 labels=Counter(x['v557_m15_label'] for x in rows); chosen=[x for x in rows if x['v557_m15_label']=='M15_CONFIRMED_LH_CHOCH_TAKEOVER']
 fields=sorted({key for row in rows for key in row})
 for name,data in [('v557_all_daily_candidates_m15_choch.csv',rows),('v557_confirmed_m15_choch_seeds.csv',chosen)]:
  with (OUT/name).open('w',newline='',encoding='utf-8') as f:
   w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(data)
 report={'version':'V557_DAILY_DEMAND_CONFIRMED_M15_CHOCH_SEED_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source_contract':'same V553 source-isolated Sina daily/m15 cache; 2025-2026 partial range','daily_contract':'unchanged V553 daily BOS -> bearish demand -> 7-session touch/reclaim -> following daily open','m15_contract':'same reclaim session: zone touch -> reclaim above zone high -> close breaks latest pre-touch confirmed 3L/3R lower high by 0.1% -> no later same-session close below zone low','causality':'The anchor swing uses three right-side M15 bars ending before the touch; all CHOCH evidence occurs before next-day entry. No outcome file is opened.','input_daily_candidates':len(rows),'label_counts':dict(labels),'confirmed_seed_count':len(chosen),'confirmed_seed_years':dict(Counter(x['planned_entry_date'][:4] for x in chosen)),'invariants':{'no_outcome_files_read':True,'all_anchor_confirmed_before_touch':all(x['m15_anchor_time'][:14] < x['m15_touch_time'][:14] for x in chosen),'all_choch_before_entry':all(x['m15_choch_time'][:8]<=x['reclaim_date']<x['planned_entry_date'] for x in chosen),'daily_contract_unchanged':True},'decision':'OUTCOME_BLIND_SEED_COMPLETE__REQUIRES_INDEPENDENT_ORACLE_BEFORE_ANY_REPLAY','artifacts':{'out_dir':str(OUT),'all_rows':str(OUT/'v557_all_daily_candidates_m15_choch.csv'),'confirmed_seeds':str(OUT/'v557_confirmed_m15_choch_seeds.csv'),'latest':str(LATEST)}}
 text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v557_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
