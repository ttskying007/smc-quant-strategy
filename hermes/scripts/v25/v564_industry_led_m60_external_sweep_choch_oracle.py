#!/usr/bin/env python3
"""V564 independent raw-bar oracle for frozen V563 identities; no outcome replay."""
from __future__ import annotations
import csv, json, math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

BASE=Path('/root/.hermes'); AUDIT=BASE/'smc_audit'; K60=BASE/'kline_cache_60min'; KDAY=BASE/'kline_cache'
MAP=AUDIT/'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
SEED_LATEST=AUDIT/'v563_industry_led_m60_external_sweep_choch_seed_latest.json'
LATEST=AUDIT/'v564_industry_led_m60_external_sweep_choch_oracle_latest.json'
TS=datetime.now().strftime('%Y%m%d_%H%M%S'); OUT=AUDIT/f'v564_industry_led_m60_external_sweep_choch_oracle_no_outcome_{TS}'

def f(x:Any,d=math.nan):
 try:return float(x)
 except:return d
def dn(x:Any)->str:
 s=''.join(c for c in str(x or '') if c.isdigit()); return s[:8] if len(s)>=8 else ''
def load(p:Path):
 try:
  x=json.loads(p.read_text());return x if isinstance(x,list) else []
 except:return []
def sym(p:Path):
 a=p.name.split('_');return f'{a[0]}.{a[1]}' if len(a)>=4 and len(a[0])==6 else ''
def dp(s:str):
 a,b=s.split('.');return KDAY/f'{a}_{b}_daily_750.json'

def activation(indmap):
 g=defaultdict(list);cal=set()
 for p in KDAY.glob('*_daily_750.json'):
  s=sym(p);ind=indmap.get(s)
  if not ind:continue
  prev=math.nan
  for b in sorted(load(p),key=lambda x:dn(x.get('t') or x.get('date'))):
   d=dn(b.get('t') or b.get('date'));c,h=f(b.get('c')),f(b.get('h'))
   if not d or c<=0:continue
   cal.add(d)
   if prev>0:g[d,ind].append(((c/prev-1)*100,(h/prev-1)*100 if h>0 else (c/prev-1)*100))
   prev=c
 active={}
 for k,v in g.items():
  if len(v)>=5:active[k]=(sum(x[1]>=9.5 for x in v)>=3 or sum(x[0]>=5 for x in v)/len(v)*100>=20)
 days=sorted(cal);prior={days[i]:days[i-1] for i in range(1,len(days))}
 return active,prior

def verify(r,active,prior):
 s=r['symbol'];a,b=s.split('.');bars=sorted(load(K60/f'{a}_{b}_60min_500.json'),key=lambda x:str(x.get('t') or ''))
 i=int(r['sweep_idx']);q=int(r['swing_high_idx']);z=int(r['choch_idx']);d=r['event_date']
 if not (0<=q<i<z<len(bars)):return 'ORDER'
 if not (dn(bars[i].get('t'))==dn(bars[z].get('t'))==d):return 'EVENT_DAY'
 # first three session bars boundary
 session=[j for j,x in enumerate(bars) if dn(x.get('t'))==d]
 if i not in session[:3] or z not in session[:3]:return 'SESSION_WINDOW'
 if not active.get((prior.get(d,''),r['industry']),False):return 'INDUSTRY_CONTEXT'
 lo,cl=f(bars[i].get('l')),f(bars[i].get('c'));ref=min(f(bars[j].get('l')) for j in range(i-8,i))
 if not(lo<ref and cl>ref):return 'SWEEP_RECLAIM'
 hs=[f(bars[j].get('h')) for j in range(q-2,q+3)]
 if q+2>=i or f(bars[q].get('h'))!=max(hs) or hs.count(f(bars[q].get('h')))!=1:return 'SWING_CONFIRM'
 if not f(bars[z].get('c'))>f(bars[q].get('h')):return 'CHOCH_BREAK'
 db=sorted(load(dp(s)),key=lambda x:dn(x.get('t') or x.get('date')));dates=[dn(x.get('t') or x.get('date')) for x in db]
 try:k=dates.index(d)
 except ValueError:return 'NO_DAILY_EVENT'
 if k+1>=len(dates) or dates[k+1]!=r['entry_date']:return 'ENTRY_DATE'
 return ''

def main():
 seed=json.loads(SEED_LATEST.read_text());rp=Path(seed['artifacts']['rows'])
 with rp.open() as h:rows=list(csv.DictReader(h))
 ind={str(x['symbol']):str(x['industry']) for x in json.loads(MAP.read_text()) if x.get('symbol') and x.get('industry')}
 act,prior=activation(ind);fails=defaultdict(int);valid=[]
 for r in rows:
  e=verify(r,act,prior)
  if e:fails[e]+=1
  else:valid.append(r)
 exp={(r['symbol'],r['event_date']) for r in rows};got={(r['symbol'],r['event_date']) for r in valid}
 years=defaultdict(int)
 for r in valid:years[r['event_date'][:4]]+=1
 OUT.mkdir(parents=True,exist_ok=True);outrows=OUT/'v564_oracle_rows.csv'
 with outrows.open('w',newline='') as h:
  w=csv.DictWriter(h,fieldnames=sorted(set().union(*(set(r) for r in valid))));w.writeheader();w.writerows(valid)
 report={'version':'V564_INDEPENDENT_RAW_BAR_ORACLE_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),'source_seed':str(rp),'expected_identities':len(exp),'oracle_identities':len(got),'missing':len(exp-got),'extra':len(got-exp),'identity_match':exp==got,'failure_counts':dict(fails),'year_counts':dict(sorted(years.items())),'invariants':{'no_outcome_fields_read':True,'production_write':False,'frontend_write':False,'watchlist_write':False},'artifacts':{'dir':str(OUT),'rows':str(outrows),'summary':str(OUT/'v564_report.json')}}
 (OUT/'v564_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({'status':'PASS' if report['identity_match'] else 'FAIL','latest':str(LATEST),'expected':len(exp),'oracle':len(got),'failures':dict(fails)},ensure_ascii=False))
if __name__=='__main__':main()
