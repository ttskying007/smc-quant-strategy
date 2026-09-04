#!/usr/bin/env python3
"""V683: outcome-blind lifecycle-cancellation audit of frozen V678 ready chains.

This is not a replay and reads no price after next_h60_open_time.  It verifies
that every hard invalidation remains monitored from its creation through H4.
"""
from __future__ import annotations
import csv, importlib.util, json
from collections import Counter
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; DAILY=ROOT/'intraday_cache/sina_raw_daily_v379'; M60=ROOT/'intraday_cache/sina_m60_v1'
SRC=AUD/'v678_outcome_blind_wdh_state_machine_seeds_latest.json'; OUT=AUD/f'v683_wdh_lifecycle_cancellation_audit_no_write_{datetime.now():%Y%m%d_%H%M%S}'; LATEST=AUD/'v683_wdh_lifecycle_cancellation_audit_latest.json'
spec=importlib.util.spec_from_file_location('core',ROOT/'scripts/v25/v677_three_timeframe_semantic_source_audit.py');core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
def day(x):return ''.join(c for c in str(x) if c.isdigit())[:8]
def main():
 src=json.loads(SRC.read_text())
 if src.get('decision')!='V678_OUTCOME_BLIND_CHAIN_SEEDS_READY__INDEPENDENT_IDENTITY_ORACLE_REQUIRED':raise SystemExit('V678 source gate failed')
 with open(src['artifact'],newline='',encoding='utf-8') as h:seeds=[r for r in csv.DictReader(h) if r['terminal']=='SEED_READY']
 cache={}; counts=Counter(); violating=[]
 for n,r in enumerate(seeds,1):
  sym=r['symbol']; code,ex=sym.split('.')
  if sym not in cache:
   ds=core.daily_rows(DAILY/f'{code}_{ex}_raw_daily.json.gz'); hs,bad=core.m60_rows(M60/f'{code}_{ex}_m60_sina.json.gz',{x['t']:x['segment'] for x in ds}); cache[sym]=(ds,hs,core.weekly_rows(ds))
  ds,hs,ws=cache[sym]; entry=r['next_h60_open_time']; ed=day(entry); zl=float(r['daily_zone_low']); d1=float(r['daily_ssl_price']); wp=float(r['weekly_protected_low'])
  # All observations are strictly before the executable next-60m-open.
  d1_break=any(x['c']<d1 for x in ds if r['daily_ssl_time']<x['t']<ed)
  daily_poi_break=any(x['c']<zl for x in ds if r['daily_first_touch_time']<x['t']<ed)
  h_poi_break=any(x['c']<zl for x in hs if r['h60_first_touch_time']<x['t']<entry)
  weekly_break=any(x['c']<wp for x in ws if r['weekly_permission_time']<x['t']<ed)
  codes=[]
  if d1_break:codes.append('D1_LOW_REBREAK_AFTER_D2')
  if daily_poi_break:codes.append('DAILY_POI_CLOSE_PENETRATION_AFTER_D4')
  if h_poi_break:codes.append('H60_POI_CLOSE_PENETRATION_AFTER_H1')
  if weekly_break:codes.append('WEEKLY_PROTECTED_LOW_INVALIDATED')
  for c in codes:counts[c]+=1
  if codes and len(violating)<100:violating.append({'symbol':sym,'entry_time':entry,'daily_zone_low':zl,'daily_ssl_price':d1,'weekly_protected_low':wp,'violations':codes,'d4':r['daily_first_touch_time'],'h1':r['h60_first_touch_time'],'h4':r['h60_hold_time']})
  if n%250==0:print(f'V683 progress {n}/{len(seeds)} violations={sum(bool(x) for x in [codes])}',flush=True)
 invalid=sum(1 for r in seeds if False) # report below computes unique explicitly
 unique=0
 # re-evaluate booleans from retained only would truncate; exact unique set is stored during loop in a counter-free pass substitute.
 # Use identity samples saved in full-memory set, not outcomes.
 # (The count is reconstructed from identifiers emitted below.)
 # Audit needs exact number; repeat compact check now over source rows with cached bars.
 invalid_ids=[]
 for r in seeds:
  sym=r['symbol'];ds,hs,ws=cache[sym];entry=r['next_h60_open_time'];ed=day(entry);zl=float(r['daily_zone_low']);d1=float(r['daily_ssl_price']);wp=float(r['weekly_protected_low'])
  bad=(any(x['c']<d1 for x in ds if r['daily_ssl_time']<x['t']<ed) or any(x['c']<zl for x in ds if r['daily_first_touch_time']<x['t']<ed) or any(x['c']<zl for x in hs if r['h60_first_touch_time']<x['t']<entry) or any(x['c']<wp for x in ws if r['weekly_permission_time']<x['t']<ed))
  if bad:invalid_ids.append('|'.join([r['symbol'],r['weekly_permission_time'],r['daily_ssl_time'],r['daily_break_time'],r['daily_ob_time'],r['daily_first_touch_time'],r['h60_ssl_time'],r['h60_break_time'],r['h60_ob_time'],r['h60_hold_time']]))
 report={'version':'V683_WDH_LIFECYCLE_CANCELLATION_AUDIT_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'outcome_fields_read':False,'source_ready_count':len(seeds),'checks':'post-D2 D1 rebreak; post-D4 daily POI close; post-H1 60m POI close; post-W1 weekly protected-low close, each strictly before entry','violation_counts':dict(counts),'unique_violating_ready_chains':len(invalid_ids),'unique_violating_identity_samples':invalid_ids[:50],'examples':violating,'decision':'V683_LIFECYCLE_INVARIANT_FAIL__V678_V679_IDENTITIES_INVALID_FOR_REPLAY' if invalid_ids else 'V683_LIFECYCLE_INVARIANT_PASS__FROZEN_REPLAY_INTERPRETABLE'}
 OUT.mkdir(parents=True,exist_ok=False);text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v683_report.json').write_text(text,encoding='utf-8');LATEST.write_text(text,encoding='utf-8');print(text)
if __name__=='__main__':main()
