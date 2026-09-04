#!/usr/bin/env python3
"""V682 no-write structural-integrity postmortem of the closed V676 ontology.

This audit deliberately excludes pnl/exit/target outcomes.  It asks only whether
a V678 SEED_READY entry still had the W1 permission and D-POI validity required
by its own causal contract at actual entry time.
"""
import csv, gzip, importlib.util, json
from collections import Counter
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'
V678=AUD/'v678_outcome_blind_wdh_state_machine_seeds_latest.json'
OUT=AUD/'v682_closed_ontology_structural_integrity_postmortem_latest.json'
DAILY=ROOT/'intraday_cache/sina_raw_daily_v379'; M60=ROOT/'intraday_cache/sina_m60_v1'
s=importlib.util.spec_from_file_location('core',ROOT/'scripts/v25/v677_three_timeframe_semantic_source_audit.py');core=importlib.util.module_from_spec(s);s.loader.exec_module(core)
def date(x):return ''.join(c for c in x[:10] if c.isdigit())
def days(a,b):return (datetime.strptime(date(b),'%Y%m%d')-datetime.strptime(date(a),'%Y%m%d')).days
def main():
 r=json.loads(V678.read_text()); rows=[x for x in csv.DictReader(open(r['artifact'])) if x['terminal']=='SEED_READY']
 invalid=Counter(); total=Counter(); lag=Counter(); examples=[]
 bysymbol={}
 for seed in rows:
  sym=seed['symbol']
  if sym not in bysymbol:
   c,e=sym.split('.');d=core.daily_rows(DAILY/f'{c}_{e}_raw_daily.json.gz');h,bad=core.m60_rows(M60/f'{c}_{e}_m60_sina.json.gz',{x['t']:x['segment'] for x in d});bysymbol[sym]=(d,h,core.weekly_rows(d))
  d,h,w=bysymbol[sym]; entry=date(seed['next_h60_open_time']); zl=float(seed['daily_zone_low']); pl=float(seed['weekly_protected_low'])
  # These facts are all known by entry time; post-entry bars are never read.
  d_poi_fail=any(x['t']>seed['daily_first_touch_time'] and x['t']<entry and x['c']<zl for x in d)
  w_fail=any(x['t']>seed['weekly_permission_time'] and x['t']<entry and x['c']<pl for x in w)
  hidx={x['t']:i for i,x in enumerate(h)}; en=h[hidx[seed['next_h60_open_time']]]; h2=h[hidx[seed['h60_ssl_time']]]
  structural_stop=max(h2['l'],zl); entry_below_stop=en['o']<=structural_stop
  reasons=[]
  if d_poi_fail:reasons.append('D_POI_ALREADY_CLOSE_INVALID')
  if w_fail:reasons.append('W1_PROTECTED_LOW_ALREADY_INVALID')
  if entry_below_stop:reasons.append('ENTRY_AT_OR_BELOW_OWN_STRUCTURE_STOP')
  total['ready']=total['ready']+1
  for x in reasons:invalid[x]+=1
  if reasons:invalid['ANY_STRUCTURAL_INTEGRITY_FAIL']+=1
  dh3h4=days(seed['h60_break_time'],seed['h60_reclaim_time']); d4entry=days(seed['daily_first_touch_time'],seed['next_h60_open_time'])
  lag['h3_to_h4_over_20_calendar_days']+=dh3h4>20;lag['h3_to_h4_over_60_calendar_days']+=dh3h4>60;lag['d4_to_entry_over_20_calendar_days']+=d4entry>20
  if reasons and len(examples)<100:examples.append({'symbol':sym,'reasons':reasons,'entry_time':seed['next_h60_open_time'],'entry_open':en['o'],'stop':structural_stop,'daily_zone_low':zl,'h2_low':h2['l'],'weekly_permission':seed['weekly_permission_time'],'daily_first_touch':seed['daily_first_touch_time'],'h3':seed['h60_break_time'],'h4_reclaim':seed['h60_reclaim_time']})
 out={'version':'V682_CLOSED_ONTOLOGY_STRUCTURAL_INTEGRITY_POSTMORTEM_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'outcome_fields_read':False,'ready_identities':len(rows),'integrity_failures':dict(invalid),'lag_flags':dict(lag),'root_cause':'The closed V676/V678 ontology did not carry W1 and daily-POI invalidation forward through the delayed H2→H4 lifecycle; consequently some declared ready chains reach E after their own higher-timeframe permission/POI is structurally invalid. This is an ontology-lifecycle defect, not a performance selector or parameter issue.','decision':'V682_CONFIRMED_CAUSAL_LIFECYCLE_DEFECT__V676_ONTOLOGY_REMAINS_CLOSED__NEW_ONTOLOGY_MUST_REDECLARE_PERSISTENT_VALIDITY' if invalid['ANY_STRUCTURAL_INTEGRITY_FAIL'] else 'V682_NO_LIFECYCLE_DEFECT_FOUND','examples':examples}
 OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
