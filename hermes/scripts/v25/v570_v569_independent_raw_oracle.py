#!/usr/bin/env python3
"""Independent raw-data Oracle for V569; no outcome/replay files are opened."""
from __future__ import annotations

import csv
import gzip
import json
import math
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import quantiles
from typing import Any

ROOT=Path('/root/.hermes'); AUDIT=ROOT/'smc_audit'; MARGIN=ROOT/'pit_cache/v562_exchange_margin_raw'; DAILY=ROOT/'kline_cache'
SEED_LATEST=AUDIT/'v569_margin_commitment_smc_response_seed_latest.json'; LATEST=AUDIT/'v570_v569_independent_raw_oracle_latest.json'
OUT=AUDIT/f'v570_v569_independent_raw_oracle_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'; YEARS=('2023','2024','2025')

def n(x:Any)->float|None:
 try:
  v=float(x);return v if math.isfinite(v) and v>0 else None
 except (TypeError,ValueError):return None

def doc(ex:str,date:str)->list[dict[str,Any]]:
 try:
  with gzip.open(MARGIN/ex/f'{date}.json.gz','rt',encoding='utf8') as h:x=json.load(h)
  return x['rows'] if x.get('exchange')==ex and x.get('date')==date and isinstance(x.get('rows'),list) else []
 except (OSError,ValueError):return []

def margin_events()->dict[str,set[str]]:
 """Reconstruct eligible external events independently from provider records."""
 out=defaultdict(set)
 for ex in ('SH','SZ'):
  prior={}; state=defaultdict(bool)
  for p in sorted((MARGIN/ex).glob('20*.json.gz')):
   d=p.stem.split('.')[0]
   if d[:4] not in YEARS:continue
   rows=doc(ex,d); parsed=[];vals=[]
   for r in rows:
    code=str(r.get('code') or '').zfill(6); buy,bal=n(r.get('financing_buy')),n(r.get('financing_balance'))
    if code.isdigit() and buy is not None and bal is not None and prior.get(code,0)>0:
     z=buy/prior[code];parsed.append((code,z,bal));vals.append(z)
   q=quantiles(vals,n=4,method='inclusive')[2] if len(vals)>=4 else math.inf
   seen=set()
   for code,z,bal in parsed:
    high=z>=q and bal>=prior[code]
    if high and not state[code]:out[f'{code}.{ex}'].add(d)
    state[code]=high;seen.add(code)
   for r in rows:
    code=str(r.get('code') or '').zfill(6);bal=n(r.get('financing_balance'))
    if code.isdigit() and bal is not None:prior[code]=bal;seen.add(code)
   for code in list(state):
    if code not in seen:state[code]=False
 return out

def bars(sym:str)->list[dict[str,Any]]:
 try:x=json.loads((DAILY/f'{sym.replace(".","_")}_daily_750.json').read_text())
 except (OSError,ValueError):return []
 out=[]
 for r in x if isinstance(x,list) else []:
  d=str(r.get('t') or r.get('date') or '')[:8];vs=[n(r.get(k)) for k in ('o','h','l','c')]
  if len(d)==8 and d.isdigit() and all(v is not None for v in vs):out.append({'d':d,'o':vs[0],'h':vs[1],'l':vs[2],'c':vs[3]})
 return sorted(out,key=lambda x:x['d'])

def piv(xs):
 lo=[];hi=[]
 for i in range(3,len(xs)-3):
  if xs[i]['l']<min(x['l'] for x in xs[i-3:i]) and xs[i]['l']<=min(x['l'] for x in xs[i+1:i+4]):lo.append((i,i+3))
  if xs[i]['h']>max(x['h'] for x in xs[i-3:i]) and xs[i]['h']>=max(x['h'] for x in xs[i+1:i+4]):hi.append((i,i+3))
 return lo,hi

def identity_for(sym:str,mdate:str,xs,lo,hi)->tuple[str,str]|None:
 dates=[x['d'] for x in xs];start=bisect_right(dates,mdate)
 if start+34>=len(xs):return None
 for si in range(start,min(start+15,len(xs)-1)):
  ks=[p for p in lo if p[1]<si]
  if not ks:continue
  ssl=ks[-1]
  if not(xs[si]['l']<xs[ssl[0]]['l'] and xs[si]['c']>xs[ssl[0]]['l']):continue
  hs=[p for p in hi if p[1]<si];lh=None
  for j in range(len(hs)-1,0,-1):
   if xs[hs[j][0]]['h']<xs[hs[j-1][0]]['h']:lh=hs[j][0];break
  if lh is None:continue
  ch=next((i for i in range(si+1,min(si+9,len(xs))) if xs[i]['c']>xs[lh]['h']),None)
  if ch is None:continue
  bears=[i for i in range(si,ch+1) if xs[i]['c']<xs[i]['o']]
  if not bears:continue
  pi=bears[-1]; zl,zh=xs[pi]['l'],xs[pi]['o']
  rc=next((i for i in range(ch+1,min(ch+11,len(xs))) if xs[i]['l']<=zh and xs[i]['h']>=zl and xs[i]['c']>=zh),None)
  if rc is not None and rc+1<len(xs):return (sym,xs[rc+1]['d'])
 return None

def main():
 meta=json.loads(SEED_LATEST.read_text());seedp=Path(meta['artifacts']['seeds'])
 with seedp.open(newline='',encoding='utf8') as h:expected=list(csv.DictReader(h))
 expected_ids={(r['symbol'],r['planned_entry_date']) for r in expected};src=margin_events();actual=set(); failures=defaultdict(int)
 for k,(sym,dates) in enumerate(sorted(src.items()),1):
  xs=bars(sym);lo,hi=piv(xs)
  for d in sorted(dates):
   ident=identity_for(sym,d,xs,lo,hi)
   if ident and ident[1][:4] in YEARS:actual.add(ident)
  if k%500==0:print(json.dumps({'symbols':k,'oracle_identities':len(actual)},ensure_ascii=False),flush=True)
 missing=expected_ids-actual;extra=actual-expected_ids
 OUT.mkdir(parents=True,exist_ok=False)
 rows=OUT/'v570_oracle_identities.csv'
 with rows.open('w',newline='',encoding='utf8') as h:
  w=csv.DictWriter(h,fieldnames=['symbol','planned_entry_date']);w.writeheader();w.writerows([{'symbol':s,'planned_entry_date':d} for s,d in sorted(actual)])
 rep={'version':'V570_V569_INDEPENDENT_RAW_ORACLE_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),'input_contract':'V569 expected identities, official raw SSE/SZSE margin records, and daily OHLCV only; no outcome/trade/replay file read.','independent_rebuild':'Rebuilds the source-only cross-sectional q75 margin impulse transition and the full daily confirmed SSL->LH CHOCH->demand POI reclaim lifecycle without importing V569 code.','expected_identities':len(expected_ids),'oracle_identities':len(actual),'missing':len(missing),'extra':len(extra),'missing_sample':[{'symbol':s,'planned_entry_date':d} for s,d in sorted(missing)[:20]],'extra_sample':[{'symbol':s,'planned_entry_date':d} for s,d in sorted(extra)[:20]],'identity_match':expected_ids==actual,'invariants':{'no_outcome_files_read':True,'production_write':False,'frontend_write':False,'watchlist_write':False},'decision':'V570_ORACLE_PASS__ONE_FROZEN_STRICT_T1_REPLAY_AUTHORIZED' if expected_ids==actual else 'V570_ORACLE_FAIL__NO_REPLAY_ALLOWED','artifacts':{'out_dir':str(OUT),'oracle_identities':str(rows),'latest':str(LATEST)}}
 text=json.dumps(rep,ensure_ascii=False,indent=2);(OUT/'v570_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
