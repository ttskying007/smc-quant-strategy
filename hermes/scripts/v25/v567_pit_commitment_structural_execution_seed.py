#!/usr/bin/env python3
"""V567 outcome-blind seeds for V566 PIT commitment -> structural execution.

Only announcement metadata and daily bars up to planned entry are read. No trade
or result data is opened. The source event is the signal; daily SMC anchors are
an executable pre-entry risk/target contract, not an outcome filter.
"""
from __future__ import annotations
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; CACHE=ROOT/'kline_cache'
PRE=AUD/'v566_pit_commitment_structural_execution_preregistration_latest.json'
META=AUD/'v563_pit_event_archive_full_coverage_no_outcome_20260724_124935'/'v563_event_metadata.jsonl'
OUT=AUD/f'v567_pit_commitment_structural_execution_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST=AUD/'v567_pit_commitment_structural_execution_seed_latest.json'
BUYBACK_EXCLUDE=re.compile(r'进展|实施结果|完成|期限届满|注销|减少注册资本|补偿股份|业绩承诺|终止|调整')
INCREASE_EXCLUDE=re.compile(r'减持|进展|完成|结果|实施|时间过半|解除|质押|权益变动|被动')
ACTOR=re.compile(r'控股股东|实际控制人|董事|监事|高级管理人员|持股5%以上|股东')

def num(x):
 try:return float(x)
 except (TypeError,ValueError):return None

def family(r):
 t=str(r.get('title') or '')
 if r.get('kind')=='BUYBACK' and '回购' in t and re.search(r'方案|预案|董事会|股东大会',t) and not BUYBACK_EXCLUDE.search(t):return 'BUYBACK_INIT'
 if r.get('kind')=='HOLDER_INCREASE' and '增持' in t and re.search(r'计划|拟',t) and ACTOR.search(t) and not INCREASE_EXCLUDE.search(t):return 'INSIDER_INCREASE_INIT'
 return None

def events():
 seen=set();out=[]
 for line in META.open(encoding='utf8'):
  r=json.loads(line);fam=family(r)
  pub=str(r.get('publication_time') or '')[:10].replace('-','')
  key=(fam,str(r.get('symbol') or ''),str(r.get('announcement_id') or ''))
  if not fam or len(pub)!=8 or not pub.isdigit() or key in seen:continue
  seen.add(key);out.append({'family':fam,'symbol':key[1],'announcement_id':key[2],'publication_date':pub,'event_year':pub[:4],'title':str(r['title'])})
 return sorted(out,key=lambda r:(r['symbol'],r['publication_date'],r['announcement_id']))

def bars(sym):
 try:raw=json.loads((CACHE/f"{sym.replace('.', '_')}_daily_750.json").read_text())
 except (OSError,ValueError):return []
 out=[]
 for x in raw if isinstance(raw,list) else []:
  d=str(x.get('t') or x.get('date') or '')[:8];o,h,l,c=(num(x.get(k)) for k in ('o','h','l','c'))
  if len(d)==8 and d.isdigit() and all(v is not None and v>0 for v in (o,h,l,c)):out.append({'d':d,'o':o,'h':h,'l':l,'c':c})
 return sorted(out,key=lambda r:r['d'])

def plow(xs,i):return i>=3 and i+3<len(xs) and xs[i]['l']<min(x['l'] for x in xs[i-3:i]) and xs[i]['l']<=min(x['l'] for x in xs[i+1:i+4])
def phigh(xs,i):return i>=3 and i+3<len(xs) and xs[i]['h']>max(x['h'] for x in xs[i-3:i]) and xs[i]['h']>=max(x['h'] for x in xs[i+1:i+4])

def anchor_seed(ev,xs):
 # Strictly next available local session after public timestamp, including after-hours publication.
 ei=next((i for i,x in enumerate(xs) if x['d']>ev['publication_date']),None)
 if ei is None:return 'NO_NEXT_SESSION_IN_CACHE',None
 entry=xs[ei]['o']
 # All pivots must have their 3 right bars completed before decision/entry index.
 lows=[i for i in range(3,ei-3) if plow(xs,i) and xs[i]['l']<entry]
 if not lows:return 'NO_CONFIRMED_STRUCTURAL_STOP',None
 si=lows[-1];stop=xs[si]['l']*.99
 if not stop<entry:return 'INVALID_STOP_AT_ENTRY',None
 highs=[]
 for i in range(3,ei-3):
  if phigh(xs,i) and xs[i]['h']>entry and not any(x['h']>=xs[i]['h'] for x in xs[i+1:ei]): highs.append(i)
 if not highs:return 'NO_UNCONSUMED_STRUCTURAL_TARGET',None
 ti=min(highs,key=lambda i:xs[i]['h']);target=xs[ti]['h'];rr=(target-entry)/(entry-stop)
 if rr<1.5:return 'PLANNED_RR_LT_1_5',None
 return 'SEED',{**ev,'eligible_date':xs[ei]['d'],'planned_entry_date':xs[ei]['d'],'entry_open':round(entry,6),'stop_anchor_date':xs[si]['d'],'structural_stop':round(stop,6),'target_anchor_date':xs[ti]['d'],'structural_target':round(target,6),'planned_rr':round(rr,6)}

def main():
 pre=json.loads(PRE.read_text());assert pre['decision']=='PREREGISTRATION_COMPLETE__OUTCOME_BLIND_SEED_GENERATION_AUTHORIZED'
 assert not any(pre[k] for k in ('production_write','frontend_write','watchlist_write'))
 OUT.mkdir(parents=True,exist_ok=False);all_events=events();groups=defaultdict(list)
 for e in all_events:groups[e['symbol']].append(e)
 rows=[]
 for n,(sym,items) in enumerate(sorted(groups.items()),1):
  xs=bars(sym)
  for e in items:
   status,seed=anchor_seed(e,xs);row={**e,'seed_status':status}
   if seed:row.update(seed)
   rows.append(row)
  if n%500==0:print(json.dumps({'symbols':n,'events':len(rows)},ensure_ascii=False),flush=True)
 # One position identity per symbol/open. Preserve earliest public event deterministically.
 candidates=[r for r in rows if r['seed_status']=='SEED'];canonical={}
 for r in sorted(candidates,key=lambda x:(x['symbol'],x['planned_entry_date'],x['publication_date'],x['announcement_id'])):canonical.setdefault((r['symbol'],r['planned_entry_date']),r)
 seeds=sorted(canonical.values(),key=lambda r:(r['planned_entry_date'],r['symbol'],r['announcement_id']))
 fields=sorted({k for r in rows for k in r}|{k for r in seeds for k in r})
 for name,data in [('v567_all_events.csv',rows),('v567_outcome_blind_seeds.csv',seeds)]:
  with (OUT/name).open('w',newline='',encoding='utf8') as f:
   w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(data)
 years=['2024','2025']
 report={'version':'V567_PIT_COMMITMENT_STRUCTURAL_EXECUTION_SEED_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'input_contract':'V566 event taxonomy plus local daily_750 OHLCV only through next-session planned entry; no outcome/trade/PnL/exit data is opened.','events_selected':len(all_events),'event_years':dict(Counter(r['event_year'] for r in all_events)),'status_counts':dict(Counter(r['seed_status'] for r in rows)),'raw_seed_count':len(candidates),'canonical_seed_count':len(seeds),'seed_years':{y:sum(r['planned_entry_date'][:4]==y for r in seeds) for y in sorted({r['planned_entry_date'][:4] for r in seeds})},'complete_evaluation_seed_years':{y:sum(r['planned_entry_date'][:4]==y for r in seeds) for y in years},'invariants':{'no_outcome_or_trade_files_read':True,'all_entries_after_publication':all(r['planned_entry_date']>r['publication_date'] for r in seeds),'all_stop_anchor_confirmed_before_entry':all(r['stop_anchor_date']<r['planned_entry_date'] for r in seeds),'all_target_anchor_confirmed_before_entry':all(r['target_anchor_date']<r['planned_entry_date'] for r in seeds),'all_planned_rr_ge_1_5':all(float(r['planned_rr'])>=1.5 for r in seeds),'one_seed_per_symbol_entry_date':len(seeds)==len({(r['symbol'],r['planned_entry_date']) for r in seeds})},'decision':'OUTCOME_BLIND_SEED_COMPLETE__INDEPENDENT_ORACLE_REQUIRED_BEFORE_REPLAY','artifacts':{'out_dir':str(OUT),'all_events':str(OUT/'v567_all_events.csv'),'seeds':str(OUT/'v567_outcome_blind_seeds.csv'),'latest':str(LATEST)}}
 text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v567_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
