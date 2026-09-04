#!/usr/bin/env python3
"""Independent raw-data identity Oracle for V654; does not import V655 or read outcomes."""
from __future__ import annotations
import csv,gzip,json,math
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import quantiles
from typing import Any
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; MARGIN=ROOT/'pit_cache/v562_exchange_margin_raw'; DAILY=ROOT/'kline_cache'; META=AUD/'v655_two_sided_leverage_convergence_fvg_seed_latest.json'; LATEST=AUD/'v656_v654_independent_raw_oracle_latest.json'; OUT=AUD/f'v656_v654_independent_raw_oracle_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'; YEARS=('2023','2024','2025')
def n(x:Any)->float|None:
 try:
  v=float(x);return v if math.isfinite(v) and v>0 else None
 except (ValueError,TypeError):return None
def rows(ex,d):
 try:
  with gzip.open(MARGIN/ex/f'{d}.json.gz','rt',encoding='utf8') as h:x=json.load(h)
  return x.get('rows',[]) if x.get('date')==d and x.get('exchange')==ex else []
 except (OSError,ValueError):return []
def rebuild_events():
 out=[]
 for ex in ('SH','SZ'):
  fin0={};lend0={};on=defaultdict(bool)
  for p in sorted((MARGIN/ex).glob('20*.json.gz')):
   d=p.name[:8]
   if d[:4] not in YEARS:continue
   vals=[];a=[]
   for r in rows(ex,d):
    c=str(r.get('code','')).zfill(6);buy=n(r.get('financing_buy'));fin=n(r.get('financing_balance'));lend=n(r.get('lending_balance'))
    if c.isdigit() and buy and fin and lend and fin0.get(c,0)>0 and lend0.get(c,0)>0:
     z=buy/fin0[c];vals.append(z);a.append((c,z,fin,lend))
   cutoff=quantiles(vals,n=4,method='inclusive')[2] if len(vals)>3 else math.inf
   here=set()
   for c,z,fin,lend in a:
    state=z>=cutoff and fin>=fin0[c] and lend<lend0[c];here.add(c)
    if state and not on[c]:out.append((f'{c}.{ex}',d))
    on[c]=state
   known=set()
   for r in rows(ex,d):
    c=str(r.get('code','')).zfill(6);f=n(r.get('financing_balance'));l=n(r.get('lending_balance'))
    if c.isdigit() and f:fin0[c]=f;known.add(c)
    if c.isdigit() and l:lend0[c]=l;known.add(c)
   for c in list(on):
    if c not in known:on[c]=False
 return out
def bars(sym):
 try:q=json.loads((DAILY/f'{sym.replace(".","_")}_daily_750.json').read_text())
 except (OSError,ValueError):return []
 a=[]
 for r in q if isinstance(q,list) else []:
  d=str(r.get('t') or r.get('date') or '')[:8];z=[n(r.get(k)) for k in ('o','h','l','c')]
  if len(d)==8 and d.isdigit() and all(z):a.append((d,*z))
 return sorted(a)
def identity(sym,event,x):
 ds=[r[0] for r in x];start=bisect_right(ds,event)
 if start+26>=len(x):return None
 piv=[(i,i+3) for i in range(3,len(x)-3) if x[i][2]>max(v[2] for v in x[i-3:i]) and x[i][2]>=max(v[2] for v in x[i+1:i+4])]
 for j in range(start,min(start+15,len(x))):
  old=[p for p in piv if p[1]<j]
  if not old or j<2:continue
  p=old[-1]
  # tuple layout date,open,high,low,close
  if not(x[j][4]>x[p[0]][2] and x[j-2][2]<x[j][3]):continue
  lo,hi=x[j-2][2],x[j][3]
  r=next((k for k in range(j+1,min(j+11,len(x))) if x[k][3]<=hi and x[k][2]>=lo and x[k][4]>=hi),None)
  if r is not None and r+1<len(x):return (sym,event,x[p[0]][0],x[j][0],x[r][0],x[r+1][0])
 return None
def main():
 meta=json.loads(META.read_text()); assert meta['decision']=='V655_SUPPORT_PASS__INDEPENDENT_RAW_ORACLE_REQUIRED'
 with Path(meta['artifacts']['seeds']).open(newline='',encoding='utf8') as h:expected={(r['symbol'],r['event_date'],r['bsl_anchor_date'],r['bsl_break_fvg_date'],r['fvg_reclaim_date'],r['planned_entry_date']) for r in csv.DictReader(h)}
 grouped=defaultdict(list)
 for sym,d in rebuild_events():grouped[sym].append(d)
 candidates=[]
 for sym,dates in grouped.items():
  x=bars(sym)
  for d in dates:
   z=identity(sym,d,x)
   if z and z[-1][:4] in YEARS:candidates.append(z)
 # The preregistered identity canonicalizes duplicate symbol+entry observations
 # to the earliest external event, then earliest structural break.
 canonical={}
 for z in sorted(candidates,key=lambda q:(q[0],q[-1],q[1],q[3])):canonical.setdefault((z[0],z[-1]),z)
 actual=set(canonical.values())
 missing=expected-actual;extra=actual-expected;OUT.mkdir(parents=True,exist_ok=False)
 with (OUT/'v656_oracle_identities.csv').open('w',newline='',encoding='utf8') as h:
  w=csv.writer(h);w.writerow(['symbol','event_date','bsl_anchor_date','bsl_break_fvg_date','fvg_reclaim_date','planned_entry_date']);w.writerows(sorted(actual))
 rep={'version':'V656_V654_INDEPENDENT_RAW_ORACLE_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'input_contract':'Expected V655 identities plus official raw SSE/SZSE records and daily OHLCV only; no outcome/trade/PnL/exit/target/stop/replay file read.','independent_rebuild':'Separately rebuilds joint high-financing-plus-short-cover transitions, confirmed BSL acceptance, bullish FVG and FVG reclaim directly from raw inputs without importing V655.','expected_identities':len(expected),'oracle_identities':len(actual),'missing':len(missing),'extra':len(extra),'missing_sample':[list(x) for x in sorted(missing)[:10]],'extra_sample':[list(x) for x in sorted(extra)[:10]],'identity_match':expected==actual,'invariants':{'no_outcome_files_read':True,'writes_false':True},'decision':'V656_ORACLE_PASS__ONE_FROZEN_STRICT_T1_REPLAY_AUTHORIZED' if expected==actual else 'V656_ORACLE_FAIL__CLOSE_ONTOLOGY_NO_REPLAY','artifacts':{'out_dir':str(OUT),'identities':str(OUT/'v656_oracle_identities.csv'),'latest':str(LATEST)}}
 text=json.dumps(rep,ensure_ascii=False,indent=2);(OUT/'v656_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
