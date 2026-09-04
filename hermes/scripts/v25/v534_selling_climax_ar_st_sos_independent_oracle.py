#!/usr/bin/env python3
"""Independent raw-bar Oracle for V533; it does not import the seed generator."""
from __future__ import annotations
import csv,json
from datetime import datetime
from pathlib import Path
from typing import Any
ROOT=Path('/root/.hermes');KDIR=ROOT/'kline_cache';AUD=ROOT/'smc_audit';V533=AUD/'v533_selling_climax_ar_st_sos_seed_gate_latest.json';OUT=AUD/f'v534_selling_climax_ar_st_sos_independent_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}';LATEST=AUD/'v534_selling_climax_ar_st_sos_independent_oracle_latest.json'
VL=20;R=.80;AW=5;TW=10;SW=5;V=.60
def n(x:Any)->float|None:
 try:x=float(x);return x if x>0 else None
 except(ValueError,TypeError):return None
def d(x:Any)->str:
 x=''.join(c for c in str(x or '') if c.isdigit());return x[:8] if len(x)>=8 else ''
def load(p:Path)->list[dict[str,Any]]:
 try:raw=json.loads(p.read_text())
 except Exception:return []
 o=[]
 for x in raw if isinstance(raw,list) else []:
  t=d(x.get('t') or x.get('date'));q=[n(x.get(k)) for k in ('o','h','l','c','v')]
  if t and all(z is not None for z in q):o.append(dict(zip(('t','o','h','l','c','v'),(t,*q))))
 return sorted(o,key=lambda x:x['t'])
def rank(b:list[dict[str,Any]],i:int)->float:
 p=[b[j]['v'] for j in range(i-VL,i)];return sum(x<=b[i]['v'] for x in p)/len(p) if len(p)==VL else 0
def rows(sym:str,b:list[dict[str,Any]])->set[tuple[str,...]]:
 out=set()
 for sc in range(VL,len(b)-AW-TW-SW-1):
  x=b[sc];spread=sorted(b[j]['h']-b[j]['l'] for j in range(sc-VL,sc))[VL//2]
  if not(x['c']<x['o'] and rank(b,sc)>=R and x['h']-x['l']>=spread):continue
  ar=next((j for j in range(sc+1,sc+AW+1) if b[j]['c']>x['h']),None)
  if ar is None:continue
  st=next((j for j in range(ar+1,ar+TW+1) if b[j]['l']>=x['l'] and b[j]['c']>x['l'] and b[j]['v']<=x['v']*V),None)
  if st is None:continue
  sos=next((j for j in range(st+1,st+SW+1) if b[j]['c']>b[ar]['h']),None)
  if sos is not None:out.add((sym,x['t'],b[ar]['t'],b[st]['t'],b[sos]['t'],b[sos+1]['t']))
 return out
def main()->None:
 source=json.loads(V533.read_text())
 if not source.get('support_gate_pass') or source.get('outcomes_opened'):raise RuntimeError('invalid pre-outcome source')
 with Path(source['artifacts']['seeds']).open(newline='',encoding='utf8')as h:s=list(csv.DictReader(h))
 expected={(x['symbol'],x['climax_date'],x['ar_date'],x['st_date'],x['sos_date'],x['entry_eligible_date']) for x in s};actual=set()
 for p in sorted(KDIR.glob('*_daily_750.json')):
  try:code,ex=p.name.removesuffix('_daily_750.json').rsplit('_',1)
  except ValueError:continue
  actual|=rows(f'{code}.{ex}',load(p))
 missing=sorted(expected-actual);extra=sorted(actual-expected);OUT.mkdir(parents=True,exist_ok=True)
 report={'version':'V534_SELLING_CLIMAX_AR_ST_SOS_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'outcomes_opened':False,'generator_seed_count':len(expected),'oracle_seed_count':len(actual),'missing_count':len(missing),'extra_count':len(extra),'oracle_pass':not missing and not extra,'sample_missing':missing[:10],'sample_extra':extra[:10],'decision':'V534_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED' if not missing and not extra else 'V534_ORACLE_FAIL__CLOSE_ONTOLOGY','artifacts':{'out_dir':str(OUT),'v533':str(V533)}}
 text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v534_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
