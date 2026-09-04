#!/usr/bin/env python3
"""V533 pre-outcome gate: selling climax -> automatic rally -> secondary test -> SOS.

A new Wyckoff accumulation ontology, not a spring/test variant:
- selling climax is a high-effort bearish wide-range bar;
- automatic rally proves immediate demand response;
- secondary test holds the climax low on lower effort;
- SOS breaks the rally high, then only next open is eligible.
"""
from __future__ import annotations
import csv,json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
ROOT=Path('/root/.hermes');KDIR=ROOT/'kline_cache';AUD=ROOT/'smc_audit'
OUT=AUD/f'v533_selling_climax_ar_st_sos_seed_gate_no_write_{datetime.now():%Y%m%d_%H%M%S}';LATEST=AUD/'v533_selling_climax_ar_st_sos_seed_gate_latest.json'
VL=20;RANK=.80;AR_WIN=5;ST_WIN=10;SOS_WIN=5;ST_VOL=.60;YEARS=('2023','2024','2025','2026');MIN=300;YMIN=40
GATE={'gross_wr_pct_min':55.0,'avg_net_pnl_pct_min':.5,'pf_min':1.15,'payoff_min':.7,'each_year_avg_net_pnl_pct_min':0.0,'t1_violations':0}
def n(x:Any)->float|None:
 try:x=float(x);return x if x>0 else None
 except(ValueError,TypeError):return None
def d(x:Any)->str:
 x=''.join(c for c in str(x or '') if c.isdigit());return x[:8] if len(x)>=8 else ''
def load(p:Path)->list[dict[str,Any]]:
 try:r=json.loads(p.read_text())
 except Exception:return []
 o=[]
 for x in r if isinstance(r,list) else []:
  date=d(x.get('t') or x.get('date'));v=[n(x.get(k)) for k in ('o','h','l','c','v')]
  if date and all(z is not None for z in v):o.append(dict(zip(('t','o','h','l','c','v'),(date,*v))))
 return sorted(o,key=lambda x:x['t'])
def vrank(b:list[dict[str,Any]],i:int)->float:
 p=[b[j]['v'] for j in range(i-VL,i)];return sum(x<=b[i]['v'] for x in p)/len(p) if len(p)==VL else 0
def scan(sym:str,b:list[dict[str,Any]])->list[dict[str,Any]]:
 out=[]
 for sc in range(VL,len(b)-AR_WIN-ST_WIN-SOS_WIN-1):
  bar=b[sc];prior=[b[j]['h']-b[j]['l'] for j in range(sc-VL,sc)]
  # Climax: down bar, high relative effort, and spread at least its prior median.
  if not(bar['c']<bar['o'] and vrank(b,sc)>=RANK and (bar['h']-bar['l'])>=sorted(prior)[len(prior)//2]):continue
  ar=next((j for j in range(sc+1,sc+AR_WIN+1) if b[j]['c']>bar['h']),None)
  if ar is None:continue
  st=next((j for j in range(ar+1,ar+ST_WIN+1) if b[j]['l']>=bar['l'] and b[j]['c']>bar['l'] and b[j]['v']<=bar['v']*ST_VOL),None)
  if st is None:continue
  sos=next((j for j in range(st+1,st+SOS_WIN+1) if b[j]['c']>b[ar]['h']),None)
  if sos is None:continue
  e=sos+1
  out.append({'symbol':sym,'ontology':'WYCKOFF_SELLING_CLIMAX_AUTOMATIC_RALLY_SECONDARY_TEST_SOS','climax_idx':sc,'climax_date':bar['t'],'climax_low':round(bar['l'],6),'climax_high':round(bar['h'],6),'climax_volume':round(bar['v'],6),'prior20_volume_rank':round(vrank(b,sc),6),'ar_idx':ar,'ar_date':b[ar]['t'],'ar_high':round(b[ar]['h'],6),'ar_close':round(b[ar]['c'],6),'st_idx':st,'st_date':b[st]['t'],'st_low':round(b[st]['l'],6),'st_high':round(b[st]['h'],6),'st_volume':round(b[st]['v'],6),'st_to_climax_volume_ratio':round(b[st]['v']/bar['v'],6),'sos_idx':sos,'sos_date':b[sos]['t'],'sos_close':round(b[sos]['c'],6),'entry_eligible_idx':e,'entry_eligible_date':b[e]['t'],'causal_trace':'high_effort_selling_climax -> automatic_rally_close_above_climax_high -> low_effort_secondary_test_holds_climax_low -> SOS_close_above_AR_high -> following_open_eligible'})
 return out
def main()->None:
 OUT.mkdir(parents=True,exist_ok=True);seeds=[];files=sorted(KDIR.glob('*_daily_750.json'));valid=0
 for i,p in enumerate(files,1):
  b=load(p)
  if len(b)<80:continue
  valid+=1
  try:code,ex=p.name.removesuffix('_daily_750.json').rsplit('_',1)
  except ValueError:continue
  seeds+=scan(f'{code}.{ex}',b)
  if i%1000==0:print(f'progress {i}/{len(files)} seeds={len(seeds)}',flush=True)
 seeds.sort(key=lambda x:(x['entry_eligible_date'],x['symbol'],x['climax_idx']));year=Counter(x['entry_eligible_date'][:4] for x in seeds);bad={'pnl','exit','mfe','mae','tp','sl','entry_price'}
 checks={'n>=300':len(seeds)>=MIN,'each_year_n>=40':all(year[y]>=YMIN for y in YEARS),'no_outcome_fields':all(not any(k in bad for k in x) for x in seeds),'strict_chronology':all(x['climax_idx']<x['ar_idx']<x['st_idx']<x['sos_idx']<x['entry_eligible_idx'] for x in seeds)}
 cp=OUT/'v533_outcome_blind_seeds.csv';fields=list(seeds[0]) if seeds else ['symbol','ontology']
 with cp.open('w',newline='',encoding='utf8')as h:w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(seeds)
 report={'version':'V533_SELLING_CLIMAX_AR_ST_SOS_SEED_GATE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'outcomes_opened':False,'distinctness':'Starts from a high-effort selling climax and automatic rally, rather than a confirmed swing breach, a post-spring low-volume test, an SOS backup, or a failed supply OB.','frozen_contract':'high-volume wide-spread bearish climax -> 1..5-bar automatic-rally close above climax high -> 1..10-bar low-volume secondary test holds climax low -> 1..5-bar SOS close above AR high -> following open eligible','constants':{'volume_lookback':VL,'climax_rank_min':RANK,'ar_lookahead':AR_WIN,'st_lookahead':ST_WIN,'sos_lookahead':SOS_WIN,'st_volume_max_of_climax':ST_VOL},'support_gate':{'total_min':MIN,'year_min':YMIN,'years':YEARS},'promotion_gate_if_replay':GATE,'files_seen':len(files),'files_valid':valid,'seed_count':len(seeds),'yearly_seed_count':{y:year[y] for y in YEARS},'support_checks':checks,'support_gate_pass':all(checks.values()),'decision':'V533_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED' if all(checks.values()) else 'V533_SUPPORT_FAIL__CLOSE_ONTOLOGY_WITHOUT_OUTCOMES__NO_RELAXATION','artifacts':{'out_dir':str(OUT),'seeds':str(cp),'latest':str(LATEST)}}
 text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v533_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
