#!/usr/bin/env python3
"""V655 outcome-blind seed generator for V654 two-sided leverage convergence."""
from __future__ import annotations
import csv,gzip,json,math
from bisect import bisect_right
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
from statistics import quantiles
from typing import Any
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; MARGIN=ROOT/'pit_cache/v562_exchange_margin_raw'; DAILY=ROOT/'kline_cache'
PRE=AUD/'v654_two_sided_leverage_convergence_fvg_preregistration.json'; PIT=AUD/'v654_two_sided_leverage_source_pit_audit_latest.json'; LATEST=AUD/'v655_two_sided_leverage_convergence_fvg_seed_latest.json'; OUT=AUD/f'v655_two_sided_leverage_convergence_fvg_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'; YEARS=('2023','2024','2025'); SUPPORT={'canonical_seeds_min':1000,'each_year_seeds_min':300,'unique_symbols_min':500}
def pos(x:Any)->float|None:
 try:
  v=float(x);return v if math.isfinite(v) and v>0 else None
 except (ValueError,TypeError):return None
def raw(ex,d):
 try:
  with gzip.open(MARGIN/ex/f'{d}.json.gz','rt',encoding='utf8') as h:x=json.load(h)
  return x['rows'] if x.get('exchange')==ex and x.get('date')==d and isinstance(x.get('rows'),list) else []
 except (OSError,ValueError):return []
def events():
 out=[]; years=Counter(); source_days=0
 for ex in ('SH','SZ'):
  prior_fin={};prior_lend={}; prior_state=defaultdict(bool)
  for p in sorted((MARGIN/ex).glob('20*.json.gz')):
   d=p.stem.split('.')[0]
   if d[:4] not in YEARS:continue
   rows=raw(ex,d)
   if not rows:continue
   source_days+=1; vals=[]; parsed=[]; current=set()
   for r in rows:
    c=str(r.get('code') or '').zfill(6); buy,fin,lend=pos(r.get('financing_buy')),pos(r.get('financing_balance')),pos(r.get('lending_balance'))
    pf,pl=prior_fin.get(c),prior_lend.get(c)
    if c.isdigit() and buy is not None and fin is not None and lend is not None and pf and pl:
     z=buy/pf; vals.append(z); parsed.append((c,z,fin,lend,pf,pl))
   q=quantiles(vals,n=4,method='inclusive')[2] if len(vals)>=4 else math.inf
   for c,z,fin,lend,pf,pl in parsed:
    state=z>=q and fin>=pf and lend<pl;current.add(c)
    if state and not prior_state[c]:
     out.append({'symbol':f'{c}.{ex}','event_date':d,'event_exchange':ex,'financing_buy_intensity':round(z,10),'financing_intensity_q75':round(q,10),'financing_balance':round(fin,2),'prior_lending_balance':round(pl,2),'lending_balance':round(lend,2),'external_event':'HIGH_FINANCING_COMMITMENT_PLUS_SHORT_COVER_CONVERGENCE'});years[d[:4]]+=1
    prior_state[c]=state
   seen=set()
   for r in rows:
    c=str(r.get('code') or '').zfill(6);f,l=pos(r.get('financing_balance')),pos(r.get('lending_balance'))
    if c.isdigit() and f is not None:prior_fin[c]=f;seen.add(c)
    if c.isdigit() and l is not None:prior_lend[c]=l;seen.add(c)
   for c in list(prior_state):
    if c not in seen:prior_state[c]=False
 return sorted(out,key=lambda r:(r['symbol'],r['event_date'])),source_days,dict(years)
def bars(sym):
 try:x=json.loads((DAILY/f'{sym.replace(".","_")}_daily_750.json').read_text())
 except (OSError,ValueError):return []
 o=[]
 for r in x if isinstance(x,list) else []:
  d=str(r.get('t') or r.get('date') or '')[:8];v=[pos(r.get(k)) for k in ('o','h','l','c')]
  if len(d)==8 and d.isdigit() and all(v):o.append({'d':d,'o':v[0],'h':v[1],'l':v[2],'c':v[3]})
 return sorted(o,key=lambda r:r['d'])
def highs(xs):
 return [(i,i+3) for i in range(3,len(xs)-3) if xs[i]['h']>max(x['h'] for x in xs[i-3:i]) and xs[i]['h']>=max(x['h'] for x in xs[i+1:i+4])]
def chain(e,xs,hs):
 ds=[x['d'] for x in xs]; start=bisect_right(ds,e['event_date'])
 if start>=len(xs):return 'NO_RESPONSE_SESSION',None
 if start+26>=len(xs):return 'RIGHT_EDGE_UNOBSERVED',None
 for b in range(start,min(start+15,len(xs))):
  known=[p for p in hs if p[1]<b]
  if not known or b<2:continue
  anchor=known[-1]
  if not(xs[b]['c']>xs[anchor[0]]['h'] and xs[b-2]['h']<xs[b]['l']):continue
  low,high=xs[b-2]['h'],xs[b]['l']
  reclaim=next((i for i in range(b+1,min(b+11,len(xs))) if xs[i]['l']<=high and xs[i]['h']>=low and xs[i]['c']>=high),None)
  if reclaim is None:continue
  if reclaim+1>=len(xs):return 'ENTRY_UNOBSERVED',None
  return 'SEED',{**e,'response_start_date':xs[start]['d'],'bsl_anchor_date':xs[anchor[0]]['d'],'bsl_anchor_confirm_date':xs[anchor[1]]['d'],'bsl_break_fvg_date':xs[b]['d'],'fvg_lower':round(low,6),'fvg_upper':round(high,6),'fvg_reclaim_date':xs[reclaim]['d'],'planned_entry_date':xs[reclaim+1]['d'],'causal_path':'PIT_TWO_SIDED_LEVERAGE_CONVERGENCE>CONFIRMED_BSL_ACCEPTANCE>BULLISH_FVG_RECLAIM>NEXT_OPEN'}
 return 'NO_COMPLETED_FVG_RESPONSE',None
def main():
 assert json.loads(PRE.read_text())['decision'].startswith('PREREGISTRATION_COMPLETE')
 assert json.loads(PIT.read_text())['decision']=='V654_SOURCE_PIT_PASS__OUTCOME_BLIND_SEED_AUTHORIZED'
 OUT.mkdir(parents=True,exist_ok=False); ev,days,ey=events(); group=defaultdict(list)
 for e in ev:group[e['symbol']].append(e)
 allrows=[]
 for sym,items in sorted(group.items()):
  xs=bars(sym);hs=highs(xs)
  for e in items:
   status,seed=chain(e,xs,hs);r={**e,'seed_status':status}
   if seed:r.update(seed)
   allrows.append(r)
 candidates=[r for r in allrows if r['seed_status']=='SEED' and r['planned_entry_date'][:4] in YEARS];canon={}
 for r in sorted(candidates,key=lambda r:(r['symbol'],r['planned_entry_date'],r['event_date'],r['bsl_break_fvg_date'])):canon.setdefault((r['symbol'],r['planned_entry_date']),r)
 seeds=sorted(canon.values(),key=lambda r:(r['planned_entry_date'],r['symbol'])); fields=sorted(set().union(*(r.keys() for r in allrows)))
 for fn,rs in [('v655_all_events.csv',allrows),('v655_outcome_blind_seeds.csv',seeds)]:
  with (OUT/fn).open('w',newline='',encoding='utf8') as h:w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rs)
 sy={y:sum(r['planned_entry_date'].startswith(y) for r in seeds) for y in YEARS}; inv={'no_outcome_or_trade_files_read':True,'event_before_response':all(r['event_date']<r['response_start_date'] for r in seeds),'anchors_confirmed_before_break':all(r['bsl_anchor_confirm_date']<r['bsl_break_fvg_date'] for r in seeds),'all_nodes_before_entry':all(r['event_date']<r['bsl_break_fvg_date']<r['fvg_reclaim_date']<r['planned_entry_date'] for r in seeds),'one_seed_per_symbol_entry':len(seeds)==len(canon),'support_total':len(seeds)>=SUPPORT['canonical_seeds_min'],'support_years':all(sy[y]>=SUPPORT['each_year_seeds_min'] for y in YEARS),'support_symbols':len({r['symbol'] for r in seeds})>=SUPPORT['unique_symbols_min']}
 passed=all(inv[k] for k in ('support_total','support_years','support_symbols'))
 rep={'version':'V655_TWO_SIDED_LEVERAGE_CONVERGENCE_FVG_SEED_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'input_contract':'Official raw SSE/SZSE financing/lending fields and OHLCV only through planned entry; no outcome/trade/PnL/exit file read.','source_days_read':days,'raw_external_event_count':len(ev),'event_years':ey,'status_counts':dict(Counter(r['seed_status'] for r in allrows)),'canonical_seed_count':len(seeds),'canonical_seed_years':sy,'unique_symbols':len({r['symbol'] for r in seeds}),'support_gate':SUPPORT,'invariants':inv,'decision':'V655_SUPPORT_PASS__INDEPENDENT_RAW_ORACLE_REQUIRED' if passed else 'V655_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_ONTOLOGY','artifacts':{'out_dir':str(OUT),'seeds':str(OUT/'v655_outcome_blind_seeds.csv'),'all_events':str(OUT/'v655_all_events.csv'),'latest':str(LATEST)}}
 text=json.dumps(rep,ensure_ascii=False,indent=2);(OUT/'v655_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
