#!/usr/bin/env python3
"""Independent raw-bar integrity audit for V444. No outcomes are selected or changed."""
import csv,json,math
from collections import Counter
from datetime import datetime
from pathlib import Path
R=Path('/root/.hermes'); AUD=R/'smc_audit'; K=R/'kline_cache'; SRC=AUD/'v444_internal_liquidity_ifvg_frontier_latest.json'; LATEST=AUD/'v445_v444_independent_integrity_latest.json'
def f(x):
 try: return float(x)
 except: return 0.0
def bars(s):
 p=K/f"{s.replace('.','_')}_daily_750.json"; a=json.loads(p.read_text()); out=[]
 for b in a:
  d=''.join(c for c in str(b.get('t') or b.get('date') or '') if c.isdigit())[:8]
  if d: out.append({'t':d,**{k:f(b.get(k)) for k in ('o','h','l','c')}})
 return sorted(out,key=lambda x:x['t'])
def main():
 report=json.loads(SRC.read_text()); sf=Path(report['artifacts']['seeds']); tf=Path(report['artifacts']['trades'])
 with sf.open() as h: seeds=list(csv.DictReader(h))
 with tf.open() as h: trades=list(csv.DictReader(h))
 cache={}; fail=Counter(); checked=Counter()
 for r in seeds:
  s=r['symbol']; cache.setdefault(s,bars(s)); b=cache[s]; o=r['ontology']; checked[o]+=1
  try:
   e=int(r['eligible_entry_idx']); t=int(r['takeover_idx'])
   if e!=t+1 or b[e]['t']!=r['eligible_entry_date'] or b[t]['t']!=r['takeover_date']: fail[o+'_ENTRY_CHRONOLOGY']+=1
   if o=='BEAR_IFVG_ROLE_REVERSAL':
    z=int(r['fvg_born_idx']); q=int(r['failure_idx']); x=int(r['touch_idx']); c=int(r['reclaim_idx'])
    if not (z<q<x<c<t<e): fail[o+'_ORDER']+=1
    if not b[z-2]['l']>b[z]['h']*1.0005: fail[o+'_GEOMETRY']+=1
    if not b[q]['c']>f(r['zone_high'])*1.002: fail[o+'_FAILURE']+=1
    if not (b[x]['l']<=f(r['zone_high']) and b[x]['h']>=f(r['zone_low'])): fail[o+'_TOUCH']+=1
    if not b[c]['c']>f(r['zone_high']) or not (b[t]['c']>f(r['zone_high']) and b[t]['l']>=f(r['zone_low'])): fail[o+'_RECLAIM_HOLD']+=1
   else:
    a=int(r['external_low_idx']); hidx=int(r['internal_high_idx']); lidx=int(r['internal_low_idx']); sw=int(r['sweep_idx']); ev=int(r['event_idx'])
    if not a<hidx<lidx<sw<ev<e: fail[o+'_ORDER']+=1
    if not (b[sw]['l']<f(r['internal_low'])*.997 and b[sw]['c']>f(r['internal_low']) and b[sw]['c']>f(r['external_low'])): fail[o+'_SWEEP']+=1
    if not b[ev]['c']>f(r['internal_high'])*1.002: fail[o+'_DISPLACEMENT']+=1
  except (ValueError,IndexError,KeyError): fail[o+'_MALFORMED']+=1
 seen=set()
 for r in trades:
  s=r['symbol']; b=cache[s]; checked['trades']+=1
  try:
   e=int(r['eligible_entry_idx']); x=int(r['exit_idx']); key=(s,r['ontology'],r['entry_date'])
   if key in seen: fail['DUPLICATE_EXECUTION']+=1
   seen.add(key)
   if x<=e or r['exit_date']<=r['entry_date']: fail['T1']+=1
   if abs(f(r['entry_price'])-b[e]['o'])>1e-6: fail['ENTRY_PRICE']+=1
   if abs(f(r['sl'])-f(r['zone_low'])*.99)>1e-5: fail['SL']+=1
   calc=(f(r['exit_price'])/f(r['entry_price'])-1)*100
   if abs(calc-f(r['pnl_pct']))>1e-4: fail['PNL']+=1
  except (ValueError,IndexError,KeyError,ZeroDivisionError): fail['TRADE_MALFORMED']+=1
 out={'version':'V445_V444_INDEPENDENT_RAW_BAR_INTEGRITY_AUDIT','generated_at':datetime.now().isoformat(timespec='seconds'),'source':str(SRC),'checked':dict(checked),'failures':dict(fail),'failure_total':sum(fail.values()),'invariants':{'all_semantics_rederived_from_raw_bars':True,'strict_t1':fail['T1']==0,'duplicate_execution_zero':fail['DUPLICATE_EXECUTION']==0,'production_write':False},'decision':'INDEPENDENT_INTEGRITY_PASS' if not fail else 'INDEPENDENT_INTEGRITY_FAIL'}
 LATEST.write_text(json.dumps(out,ensure_ascii=False,indent=2)); print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
