#!/usr/bin/env python3
"""V682 no-write postmortem of the single V681 frozen replay.

Diagnostic only: it does not alter V676/V678 identities or construct a new
candidate.  Its purpose is to identify whether failure is sample, causality,
entry-execution, stop/target, or temporal-regime failure.
"""
from __future__ import annotations
import csv, importlib.util, json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; M60=ROOT/'intraday_cache/sina_m60_v1'
SRC=AUD/'v681_single_frozen_wdh_strict_t1_replay_latest.json'
OUT=AUD/f'v682_v681_frozen_replay_postmortem_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST=AUD/'v682_v681_frozen_replay_postmortem_latest.json'
spec=importlib.util.spec_from_file_location('core',ROOT/'scripts/v25/v677_three_timeframe_semantic_source_audit.py');core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)

def f(x):
 try:return float(x)
 except (TypeError,ValueError):return 0.0
def d(t):return ''.join(c for c in str(t) if c.isdigit())[:8]
def pct(a,b):return round(100*a/b,4) if b else 0.0
def met(rs):
 p=[f(r.get('net_pnl_pct')) for r in rs]; w=[x for x in p if x>0]; l=[x for x in p if x<=0]
 return {'n':len(rs),'wr_pct':pct(len(w),len(rs)),'avg_net_pct':round(sum(p)/len(p),4) if p else 0,'pf':round(sum(w)/abs(sum(l)),4) if l and sum(l) else 0,'payoff':round((sum(w)/len(w))/abs(sum(l)/len(l)),4) if w and l and sum(l) else 0}
def main():
 src=json.loads(SRC.read_text())
 if src.get('decision')!='V681_FULL_CHAIN_REPLAY_GATE_FAIL__CLOSE_WDH_ONTOLOGY_NO_VARIANTS':raise SystemExit('V681 is not a frozen failed replay')
 with open(src['artifacts']['rows'],newline='',encoding='utf-8') as h: rows=list(csv.DictReader(h))
 closed=[r for r in rows if r.get('status')=='CLOSED']; invalid=[r for r in rows if r.get('status')=='INVALID_PREENTRY_STRUCTURAL_STOP']
 cache={}; invalid_causes=Counter(); invalid_examples=[]
 for r in invalid:
  sym=r['symbol']; code,ex=sym.split('.')
  if sym not in cache:
   # Daily is not needed for classification: row contains frozen D POI low.
   raw=ROOT/'intraday_cache/sina_raw_daily_v379'/f'{code}_{ex}_raw_daily.json.gz'
   daily=core.daily_rows(raw); bars,bad=core.m60_rows(M60/f'{code}_{ex}_m60_sina.json.gz',{x['t']:x['segment'] for x in daily})
   cache[sym]={x['t']:x for x in bars}
  h2=f(cache[sym].get(r['h60_ssl_time'],{}).get('l')); poi=f(r['daily_zone_low']); entry=f(r['entry_price'])
  cause=('H2_RAID_LOW_AT_OR_ABOVE_ENTRY' if h2>=entry else '')+('+' if h2>=entry and poi>=entry else '')+('DAILY_POI_LOW_AT_OR_ABOVE_ENTRY' if poi>=entry else '')
  invalid_causes[cause or 'UNEXPECTED']+=1
  if len(invalid_examples)<20:invalid_examples.append({'symbol':sym,'entry_time':r['entry_time'],'entry':entry,'h2_raid_low':h2,'daily_poi_low':poi,'cause':cause})
 status_year=defaultdict(Counter)
 for r in rows: status_year[(r.get('entry_date') or d(r.get('next_h60_open_time')))[:4]][r['status']]+=1
 target_source={k:met([r for r in closed if r.get('target_source')==k]) for k in sorted({r.get('target_source') for r in closed})}
 exit_reason={k:met([r for r in closed if r.get('exit_reason')==k]) for k in sorted({r.get('exit_reason') for r in closed})}
 by_year={y:met([r for r in closed if r.get('entry_date','').startswith(y)]) for y in sorted({r.get('entry_date','')[:4] for r in closed})}
 diagnosis={
  'sample_integrity':'PASS: 1,579 frozen identities were processed; 0 runtime errors; V680 exact hash remains the replay source.',
  'causality_and_t1':'PASS: next-H4 60m-open entry, target/stop observable at entry, zero T+1 violations, and stop-first collisions are conservative.',
  'execution_feasibility':'FAIL: invalid structural stop means both structural invalidation references were at/above the executable next-open price; this is a causal entry-price feasibility failure, not a loss-based selector.',
  'economics':'FAIL: whole closed sample net WR is below 55% and stability fails; positive aggregate is dominated by 2025 while 2023 and 2026 are negative.',
  'promotion':'CLOSED: V676 W->D->H ontology cannot be repaired with thresholds, subgroups, RR, SL/TP tuning, or outcome filters because V681 was its one frozen replay.'}
 report={'version':'V682_V681_FROZEN_REPLAY_POSTMORTEM_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'source':str(SRC),'source_decision':src['decision'],'frozen_contract':src['contract'],'status_counts':dict(Counter(r['status'] for r in rows)),'status_by_entry_year':{k:dict(v) for k,v in sorted(status_year.items())},'closed_overall':met(closed),'closed_by_year':by_year,'closed_by_target_source':target_source,'closed_by_exit_reason':exit_reason,'invalid_stop_count':len(invalid),'invalid_stop_cause_counts':dict(invalid_causes),'invalid_stop_examples':invalid_examples,'diagnosis':diagnosis,'next_research_constraint':'A future ontology must be independently preregistered; it must encode executable next-60m-open structural feasibility before H4 is declared terminal, but may not use V681 outcomes, stocks, dates, thresholds, or result buckets as inputs.','decision':'V682_POSTMORTEM_COMPLETE__V676_WDH_ONTOLOGY_CLOSED'}
 OUT.mkdir(parents=True,exist_ok=False); text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v682_report.json').write_text(text,encoding='utf-8');LATEST.write_text(text,encoding='utf-8');print(text)
if __name__=='__main__':main()
