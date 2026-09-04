#!/usr/bin/env python3
"""V554 independent identity oracle for V553 daily->m15 takeover candidates.

Independently recomputes only identities using the frozen V553 causal contract.
It reads no return/outcome/exit artifacts and does not import V553 code.
"""
from __future__ import annotations
import csv, gzip, json, math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT=Path('/root/.hermes'); RAW=ROOT/'intraday_cache/raw_multitf_v536/source_raw/sina'; AUD=ROOT/'smc_audit'
V553=AUD/'v553_daily_candidate_mtf_lineage_latest.json'; OUT=AUD/f'v554_daily_m15_takeover_independent_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}'; LATEST=AUD/'v554_daily_m15_takeover_independent_oracle_latest.json'
YEARS={'2025','2026'}

def val(x:Any)->float|None:
 try:
  x=float(x); return x if math.isfinite(x) and x>0 else None
 except (TypeError,ValueError): return None

def rows(p:Path,minute:bool):
 try:
  with gzip.open(p,'rt',encoding='utf-8') as f: raw=json.load(f)
 except (OSError,ValueError): return []
 out=[]
 for x in raw if isinstance(raw,list) else []:
  t=str(x.get('t') or ''); d=str(x.get('d') or t[:8])[:8]; z=[val(x.get(k)) for k in ('o','h','l','c')]
  if len(d)==8 and (len(t)==14 if minute else True) and all(v is not None for v in z): out.append({'t':t if minute else d,'d':d,'o':z[0],'h':z[1],'l':z[2],'c':z[3]})
 return sorted(out,key=lambda x:x['t'])

def takeover(xs:list[dict],lo:float,hi:float)->bool:
 touch=None
 for i,x in enumerate(xs):
  if x['l']<=hi and x['h']>=lo: touch=i;break
 if touch is None:return False
 reclaim=next((i for i in range(touch,len(xs)) if xs[i]['c']>=hi),None)
 if reclaim is None:return False
 before=max(x['h'] for x in xs[:touch+1])
 mss=next((i for i in range(reclaim+1,len(xs)) if xs[i]['c']>before*1.001),None)
 return mss is not None and not any(x['c']<lo for x in xs[mss:])

def scan(p:Path)->set[tuple[str,str,str,str]]:
 sym=p.name.removesuffix('_daily.json.gz').replace('_','.')
 ds=rows(p,False); ms=rows(RAW/'m15'/p.name.replace('_daily.json.gz','_m15.json.gz'),True)
 by=defaultdict(list)
 for x in ms:by[x['d']].append(x)
 ans=set()
 for i in range(20,len(ds)-1):
  e=ds[i]
  if e['d'][:4] not in YEARS or not(e['c']>e['o'] and e['c']>max(x['h'] for x in ds[i-20:i])):continue
  zi=next((j for j in range(i-1,max(-1,i-9),-1) if ds[j]['c']<ds[j]['o']),None)
  if zi is None:continue
  lo=ds[zi]['l']; hi=max(ds[zi]['o'],ds[zi]['c']); ri=None
  for j in range(i+1,min(i+8,len(ds)-1)):
   x=ds[j]
   if x['l']<=hi*1.005 and x['c']>=hi and x['c']>x['o'] and (x['c']-x['l'])/max(x['h']-x['l'],1e-12)>=.55:ri=j;break
  if ri is None:continue
  ei=ri+1; risk=(ds[ei]['o']/(lo*.99)-1)*100
  if not .8<=risk<=12:continue
  if takeover(by.get(ds[ri]['d'],[]),lo,hi):ans.add((sym,e['d'],ds[ri]['d'],ds[ei]['d']))
 return ans

def source_ids(path:Path)->set[tuple[str,str,str,str]]:
 out=set()
 with path.open(newline='',encoding='utf-8') as f:
  for r in csv.DictReader(f):
   if r.get('m15_confirmation_label')=='M15_TAKEOVER_CONFIRMED':out.add((r['symbol'],r['event_date'],r['reclaim_date'],r['planned_entry_date']))
 return out

def main():
 OUT.mkdir(parents=True,exist_ok=False); v=json.loads(V553.read_text()); source=source_ids(Path(v['artifacts']['candidate_lineage_csv']))
 got=set()
 for n,p in enumerate(sorted((RAW/'daily').glob('*_daily.json.gz')),1):
  got|=scan(p)
  if n%500==0:print(json.dumps({'symbols':n,'oracle_identities':len(got)}),flush=True)
 missing=sorted(source-got); extra=sorted(got-source)
 report={'version':'V554_DAILY_M15_TAKEOVER_INDEPENDENT_ORACLE_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source_contract':'same Sina source-isolated daily/m15 cache, 2025-2026 only','identity':'symbol,event_date,reclaim_date,planned_entry_date','expected_v553_takeover_identities':len(source),'oracle_identities':len(got),'missing':len(missing),'extra':len(extra),'identity_match':not missing and not extra,'samples':{'missing':missing[:20],'extra':extra[:20]},'invariants':{'no_outcome_files_read':True,'oracle_does_not_import_v553':True},'decision':'V554_IDENTITY_PASS__FROZEN_T1_DIAGNOSTIC_REPLAY_ALLOWED' if not missing and not extra else 'V554_IDENTITY_FAIL__STOP'}
 text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v554_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
