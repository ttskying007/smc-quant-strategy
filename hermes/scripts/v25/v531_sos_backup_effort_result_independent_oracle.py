#!/usr/bin/env python3
"""Independent raw-bar Oracle for V530; deliberately does not import its generator."""
from __future__ import annotations
import csv,json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT=Path('/root/.hermes');KDIR=ROOT/'kline_cache';AUD=ROOT/'smc_audit'
V530=AUD/'v530_sos_backup_effort_result_seed_gate_latest.json'
OUT=AUD/f'v531_sos_backup_effort_result_independent_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}';LATEST=AUD/'v531_sos_backup_effort_result_independent_oracle_latest.json'
L=R=3;VL=20;RANK=.80;BREAK=.003;THROUGH=.01;VR=.60;BW=5;RW=3

def n(x:Any)->float|None:
 try:x=float(x);return x if x>0 else None
 except (ValueError,TypeError):return None
def d(x:Any)->str:
 x=''.join(c for c in str(x or '') if c.isdigit());return x[:8] if len(x)>=8 else ''
def bars(p:Path)->list[dict[str,Any]]:
 try:raw=json.loads(p.read_text())
 except Exception:return []
 out=[]
 for x in raw if isinstance(raw,list) else []:
  date=d(x.get('t') or x.get('date') or x.get('day'));v=[n(x.get(k)) for k in ('o','h','l','c','v')]
  if date and all(z is not None for z in v):out.append(dict(zip(('t','o','h','l','c','v'),(date,*v))))
 return sorted(out,key=lambda x:x['t'])
def pivot_high(b:list[dict[str,Any]],i:int)->bool:
 return i>=L and i+R<len(b) and b[i]['h']>max(b[j]['h'] for j in range(i-L,i)) and b[i]['h']>=max(b[j]['h'] for j in range(i+1,i+R+1))
def volrank(b:list[dict[str,Any]],i:int)->float:
 p=[b[j]['v'] for j in range(i-VL,i)];return sum(x<=b[i]['v'] for x in p)/len(p) if len(p)==VL else 0
def identities(sym:str,b:list[dict[str,Any]])->set[tuple[str,...]]:
 out=set();end=len(b)-BW-RW-1
 for sos in range(max(VL,L+R+1),end):
  sh=sos-R-1
  if not pivot_high(b,sh):continue
  level=b[sh]['h']
  if not(b[sos]['c']>=level*(1+BREAK) and volrank(b,sos)>=RANK):continue
  backup=next((j for j in range(sos+1,sos+BW+1) if b[j]['l']<=level*(1+BREAK) and b[j]['c']>=level*(1-THROUGH) and b[j]['v']<=b[sos]['v']*VR),None)
  if backup is None:continue
  reaccept=next((j for j in range(backup+1,backup+RW+1) if b[j]['c']>b[backup]['h']),None)
  if reaccept is not None:out.add((sym,b[sh]['t'],b[sos]['t'],b[backup]['t'],b[reaccept]['t'],b[reaccept+1]['t']))
 return out
def main()->None:
 source=json.loads(V530.read_text())
 if not source.get('support_gate_pass') or source.get('outcomes_opened'):raise RuntimeError('invalid V530 pre-outcome gate')
 with Path(source['artifacts']['seeds']).open(newline='',encoding='utf8') as h:seeds=list(csv.DictReader(h))
 expected={(x['symbol'],x['swing_date'],x['sos_date'],x['backup_date'],x['reaccept_date'],x['entry_eligible_date']) for x in seeds}
 actual=set()
 for p in sorted(KDIR.glob('*_daily_750.json')):
  try:code,ex=p.name.removesuffix('_daily_750.json').rsplit('_',1)
  except ValueError:continue
  actual|=identities(f'{code}.{ex}',bars(p))
 missing=sorted(expected-actual);extra=sorted(actual-expected);OUT.mkdir(parents=True,exist_ok=True)
 report={'version':'V531_SOS_BACKUP_EFFORT_RESULT_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'outcomes_opened':False,'generator_seed_count':len(expected),'oracle_seed_count':len(actual),'missing_count':len(missing),'extra_count':len(extra),'oracle_pass':not missing and not extra,'sample_missing':missing[:10],'sample_extra':extra[:10],'decision':'V531_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED' if not missing and not extra else 'V531_ORACLE_FAIL__CLOSE_ONTOLOGY','artifacts':{'out_dir':str(OUT),'v530':str(V530)}}
 text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v531_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
