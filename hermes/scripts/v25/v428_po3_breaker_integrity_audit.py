#!/usr/bin/env python3
"""V428 independent no-outcome raw-bar audit for V427 R5 PO3 lifecycle."""
from __future__ import annotations
import csv, importlib.util, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); KDIR,AUD=ROOT/'kline_cache',ROOT/'smc_audit'; SOURCE=AUD/'v427_po3_breaker_latest.json'; OUT=AUD/f'v428_po3_breaker_integrity_no_write_{datetime.now():%Y%m%d_%H%M%S}'; LATEST=AUD/'v428_po3_breaker_integrity_latest.json'
spec=importlib.util.spec_from_file_location('v27',ROOT/'scripts/v25/smc_core_v27.py');v27=importlib.util.module_from_spec(spec);spec.loader.exec_module(v27)
def f(x):
 try: x=float(x);return x if math.isfinite(x) else 0.0
 except (TypeError,ValueError): return 0.0
def day(b):return ''.join(c for c in str(b.get('t') or b.get('date') or '') if c.isdigit())[:8]
def load(s):
 try: raw=json.loads((KDIR/f'{s.replace(".","_")}_daily_750.json').read_text())
 except Exception:return []
 return sorted([b for b in raw if day(b) and all(f(b.get(k))>0 for k in ('o','h','l','c'))],key=day)
def lifecycle(ks,start,lo,hi):
 t=r=None
 for i in range(start+1,min(len(ks),start+31)):
  b=ks[i]
  if f(b['c'])<lo:return 'CANCEL_ZONE_INVALIDATED',t,r,i
  if t is None:
   if f(b['l'])<=hi:t=i
  elif r is None:
   if f(b['c'])>hi:r=i
  elif f(b['c'])>hi and f(b['l'])>=lo:return 'TAKEOVER_CONFIRMED',t,r,i
 seen=start+30<len(ks)
 if t is None:return ('EXPIRE_NO_TOUCH_30B' if seen else 'WAIT_TOUCH_UNOBSERVED'),None,None,None
 if r is None:return ('EXPIRE_NO_RECLAIM_30B' if seen else 'WAIT_RECLAIM_UNOBSERVED'),t,None,None
 return ('EXPIRE_NO_HOLD_30B' if seen else 'WAIT_HOLD_UNOBSERVED'),t,r,None
def main():
 OUT.mkdir(parents=True,exist_ok=True);src=json.loads(SOURCE.read_text());rows=list(csv.DictReader(open(src['artifacts']['rows'])));bad=Counter();ok=0;cache={}
 forbidden=[c for c in rows[0] if c!='outcome_fields_present' and any(x in c.lower() for x in ('entry','exit','pnl','profit','win','loss','mae','mfe','tp','sl'))]
 event_dups=Counter((r['symbol'],r['event_idx'],r['poi_idx']) for r in rows); exec_dups=Counter((r['symbol'],r['takeover_idx']) for r in rows if r['lifecycle_state']=='TAKEOVER_CONFIRMED')
 for r in rows:
  s=r['symbol'];cache.setdefault(s,load(s));ks=cache[s]
  try:a0,a1,sw,ev,poi=[int(r[k]) for k in ('accum_start_idx','accum_end_idx','sweep_idx','event_idx','poi_idx')]
  except:bad['INDEX_PARSE']+=1;continue
  if not(a0==max(0,sw-30) and a1==sw and a0<sw<=poi<ev):bad['ORDER']+=1;continue
  hi=max(f(b['h']) for b in ks[a0:sw]);lo=min(f(b['l']) for b in ks[a0:sw])
  if abs(hi-f(r['accum_high']))>1e-6 or abs(lo-f(r['accum_low']))>1e-6 or hi/lo-1>.075:bad['ACCUM_GEOMETRY']+=1;continue
  swings=v27.confirmed_swings(ks); sweeps=v27.sweep_signals(ks,swings);events=v27.structure_signals(ks,swings)
  if not any(x['index']==sw and x.get('direction')=='bull' for x in sweeps):bad['SSL_NOT_REDERIVED']+=1;continue
  if not any(x['index']==ev and x.get('direction')=='bull' for x in events):bad['DISTRIBUTION_NOT_REDERIVED']+=1;continue
  b=ks[poi];zl,zh=f(r['zone_low']),f(r['zone_high'])
  if not(f(b['c'])<f(b['o']) and abs(zl-f(b['l']))<1e-6 and abs(zh-f(b['h']))<1e-6) or any(f(x['c'])<zl or f(x['l'])<=zh for x in ks[poi+1:ev]):bad['BREAKER_NOT_FRESH']+=1;continue
  state,touch,reclaim,take=lifecycle(ks,ev,zl,zh); got=(r['lifecycle_state'],r['touch_idx'],r['reclaim_idx'],r['takeover_idx']);need=(state,'' if touch is None else str(touch),'' if reclaim is None else str(reclaim),'' if take is None else str(take))
  if got!=need:bad['LIFECYCLE']+=1;continue
  ok+=1
 passed=ok==len(rows) and not bad and not forbidden and all(n==1 for n in event_dups.values()) and all(n==1 for n in exec_dups.values())
 out={'version':'V428_PO3_BREAKER_INTEGRITY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'scope':'Independent raw-bar R5 PO3 semantic, chronology, freshness, lifecycle, and execution-identity audit; no outcomes.','input_rows':len(rows),'raw_rederived_rows':ok,'forbidden_input_fields':forbidden,'duplicate_event_poi_rows':sum(n-1 for n in event_dups.values() if n>1),'duplicate_execution_rows':sum(n-1 for n in exec_dups.values() if n>1),'failures':dict(bad),'pass':passed,'decision':'INTEGRITY_PASS__R5_ELIGIBLE_FOR_ONE_FROZEN_T1_MARK_REPLAY' if passed else 'INTEGRITY_FAIL__NO_REPLAY_ALLOWED','artifacts':{'out_dir':str(OUT),'latest':str(LATEST)}}
 text=json.dumps(out,ensure_ascii=False,indent=2);(OUT/'v428_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
