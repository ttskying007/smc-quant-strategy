#!/usr/bin/env python3
"""V694 outcome-blind, source-isolated short-covering -> bearish SMC seeds."""
from __future__ import annotations
import csv, gzip, json, math
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; MARGIN=ROOT/'pit_cache'/'v562_exchange_margin_raw'; DAILY=ROOT/'kline_cache'
PRE=AUD/'v694_short_covering_smc_reversal_preregistration.json'; LATEST=AUD/'v694_short_covering_smc_reversal_seed_latest.json'; YEARS=('2023','2024','2025')
SUPPORT={'raw_events_min':30000,'canonical_seeds_min':3000,'each_year_seeds_min':800,'unique_symbols_min':500}
def pos(x:Any)->float|None:
 try:
  v=float(x); return v if math.isfinite(v) and v>0 else None
 except (TypeError,ValueError): return None
def raw(ex:str,d:str)->list[dict[str,Any]]:
 try:
  with gzip.open(MARGIN/ex/f'{d}.json.gz','rt',encoding='utf-8') as f: z=json.load(f)
  return z['rows'] if z.get('exchange')==ex and z.get('date')==d and isinstance(z.get('rows'),list) else []
 except (OSError,ValueError,KeyError): return []
def events():
 out=[]; per=Counter(); days=0
 for ex in ('SH','SZ'):
  previous={}
  for p in sorted((MARGIN/ex).glob('20*.json.gz')):
   d=p.name.split('.')[0]
   if d[:4] not in YEARS: continue
   rows=raw(ex,d)
   if not rows: continue
   days+=1
   for r in rows:
    code=str(r.get('code') or '').zfill(6); bal=pos(r.get('lending_balance')); prior=previous.get(code)
    sell=float(r.get('lending_sell') or 0)
    if code.isdigit() and prior is not None and bal is not None and bal<prior and sell==0:
     out.append({'symbol':f'{code}.{ex}','lending_event_date':d,'margin_exchange':ex,'prior_lending_balance':round(prior,6),'lending_balance':round(bal,6),'lending_balance_change':round(bal-prior,6),'lending_sell':0.0,'external_commitment':'LENDING_INVENTORY_CONTRACTION_NO_NEW_SHORT_SELL'})
     per[d[:4]]+=1
    if code.isdigit() and bal is not None: previous[code]=bal
 return out,days,dict(sorted(per.items()))
def daily(s:str):
 try: a=json.loads((DAILY/f'{s.replace(".","_")}_daily_750.json').read_text())
 except (OSError,ValueError): return []
 o=[]
 for x in a if isinstance(a,list) else []:
  d=str(x.get('t') or x.get('date') or '')[:8]
  try: q=[float(x[k]) for k in ('o','h','l','c')]
  except (KeyError,TypeError,ValueError): continue
  if len(d)==8 and d.isdigit() and all(math.isfinite(v) and v>0 for v in q): o.append({'d':d,'o':q[0],'h':q[1],'l':q[2],'c':q[3]})
 return sorted(o,key=lambda z:z['d'])
def pivots(r):
 lo=[]; hi=[]
 for i in range(3,len(r)-3):
  if r[i]['l']<min(z['l'] for z in r[i-3:i]) and r[i]['l']<=min(z['l'] for z in r[i+1:i+4]): lo.append((i,i+3))
  if r[i]['h']>max(z['h'] for z in r[i-3:i]) and r[i]['h']>=max(z['h'] for z in r[i+1:i+4]): hi.append((i,i+3))
 return lo,hi
def chain(e,r,lo,hi):
 ds=[x['d'] for x in r]; start=bisect_right(ds,e['lending_event_date'])
 if start>=len(r): return 'NO_NEXT_RESPONSE_SESSION',None
 if start+34>=len(r): return 'RIGHT_EDGE_UNOBSERVED',None
 for sw in range(start,min(start+15,len(r)-1)):
  known=[x for x in hi if x[1]<sw]
  if not known: continue
  ah,cf=known[-1]; bar=r[sw]
  if not(bar['h']>r[ah]['h'] and bar['c']<r[ah]['h']): continue
  knownlo=[x for x in lo if x[1]<sw]; hl=None
  for j in range(len(knownlo)-1,0,-1):
   cand,prior=knownlo[j][0],knownlo[j-1][0]
   if r[cand]['l']>r[prior]['l']: hl=cand; break
  if hl is None: continue
  br=next((i for i in range(sw+1,min(sw+9,len(r))) if r[i]['c']<r[hl]['l']),None)
  if br is None: continue
  bulls=[i for i in range(sw,br+1) if r[i]['c']>r[i]['o']]
  if not bulls: continue
  poi=bulls[-1]; zl,zh=r[poi]['o'],r[poi]['h']
  rec=next((i for i in range(br+1,min(br+11,len(r))) if r[i]['h']>=zl and r[i]['l']<=zh and r[i]['c']<=zl),None)
  if rec is None: continue
  en=rec+1
  if en>=len(r): return 'ENTRY_UNOBSERVED',None
  z={**e,'response_start_date':r[start]['d'],'bsl_anchor_date':r[ah]['d'],'bsl_anchor_confirm_date':r[cf]['d'],'sweep_date':r[sw]['d'],'hl_anchor_date':r[hl]['d'],'choch_date':r[br]['d'],'poi_date':r[poi]['d'],'zone_low':round(zl,6),'zone_high':round(zh,6),'reclaim_date':r[rec]['d'],'planned_entry_date':r[en]['d'],'causal_path':'PIT_LENDING_CONTRACTION>CONFIRMED_BSL_SWEEP_REJECTION>CONFIRMED_HL_CHOCH>SUPPLY_POI_REJECTION>NEXT_OPEN_SHORT'}
  return 'SEED',z
 return 'NO_COMPLETED_SMC_RESPONSE',None
def main():
 pre=json.loads(PRE.read_text()); assert pre['decision']=='PREREGISTRATION_COMPLETE__OUTCOME_BLIND_GENERATOR_AUTHORIZED'
 outdir=AUD/f'v694_short_covering_smc_reversal_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'; outdir.mkdir(exist_ok=False)
 ev,days,ey=events(); grp=defaultdict(list)
 for e in ev: grp[e['symbol']].append(e)
 allrows=[]
 for s,es in sorted(grp.items()):
  r=daily(s); lo,hi=pivots(r)
  for e in es:
   status,seed=chain(e,r,lo,hi); allrows.append({**e,'seed_status':status,**(seed or {})})
 c=[x for x in allrows if x['seed_status']=='SEED' and x['planned_entry_date'][:4] in YEARS]; canonical={}
 for x in sorted(c,key=lambda z:(z['symbol'],z['planned_entry_date'],z['lending_event_date'],z['sweep_date'])): canonical.setdefault((x['symbol'],x['planned_entry_date']),x)
 seeds=sorted(canonical.values(),key=lambda z:(z['planned_entry_date'],z['symbol'])); fields=sorted({k for z in allrows+seeds for k in z})
 for name,rows in [('v694_all_lending_events.csv',allrows),('v694_outcome_blind_seeds.csv',seeds)]:
  with (outdir/name).open('w',newline='',encoding='utf-8') as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
 sy={y:sum(x['planned_entry_date'].startswith(y) for x in seeds) for y in YEARS}; uniq=len({x['symbol'] for x in seeds})
 inv={'no_outcome_or_trade_files_read':True,'all_margin_features_before_response':all(x['lending_event_date']<x['response_start_date'] for x in seeds),'all_bsl_anchors_confirmed_before_sweep':all(x['bsl_anchor_confirm_date']<x['sweep_date'] for x in seeds),'all_causal_nodes_before_entry':all(x['lending_event_date']<x['sweep_date']<x['choch_date']<x['reclaim_date']<x['planned_entry_date'] for x in seeds),'one_seed_per_symbol_entry_date':len(seeds)==len({(x['symbol'],x['planned_entry_date']) for x in seeds}),'raw_events_capacity':len(ev)>=SUPPORT['raw_events_min'],'canonical_seed_capacity':len(seeds)>=SUPPORT['canonical_seeds_min'],'each_year_seed_capacity':all(sy[y]>=SUPPORT['each_year_seeds_min'] for y in YEARS),'unique_symbol_capacity':uniq>=SUPPORT['unique_symbols_min']}
 ok=all(inv[k] for k in ('raw_events_capacity','canonical_seed_capacity','each_year_seed_capacity','unique_symbol_capacity'))
 rep={'version':'V694_SHORT_COVERING_SMC_REVERSAL_SEED_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'input_contract':'Official SSE/SZSE raw margin records and daily OHLCV only through planned entry; no outcome/trade/PnL/exit files read.','source_days_read':days,'raw_lending_contraction_count':len(ev),'lending_event_years':ey,'status_counts':dict(Counter(x['seed_status'] for x in allrows)),'canonical_seed_count':len(seeds),'canonical_seed_years':sy,'unique_symbols':uniq,'invariants':inv,'support_gate':SUPPORT,'decision':'V694_SUPPORT_PASS__INDEPENDENT_RAW_ORACLE_REQUIRED' if ok else 'V694_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_ONTOLOGY','artifacts':{'out_dir':str(outdir),'all_events':str(outdir/'v694_all_lending_events.csv'),'seeds':str(outdir/'v694_outcome_blind_seeds.csv'),'latest':str(LATEST)}}
 text=json.dumps(rep,ensure_ascii=False,indent=2); (outdir/'v694_report.json').write_text(text); LATEST.write_text(text); print(text)
if __name__=='__main__': main()
