#!/usr/bin/env python3
"""V566 outcome-blind raw generator: industry activation -> same-session M60 micro BOS."""
from __future__ import annotations
import csv,json,math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any
BASE=Path('/root/.hermes');AUDIT=BASE/'smc_audit';K60=BASE/'kline_cache_60min';KDAY=BASE/'kline_cache'
MAP=AUDIT/'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json';PREREG=AUDIT/'v566_industry_activation_m60_micro_continuation_preregistration.json';LATEST=AUDIT/'v566_industry_activation_m60_micro_continuation_seed_latest.json';TS=datetime.now().strftime('%Y%m%d_%H%M%S');OUT=AUDIT/f'v566_industry_activation_m60_micro_continuation_seed_no_outcome_{TS}'
def f(x:Any,d=math.nan):
 try:return float(x)
 except:return d
def dn(x:Any):
 s=''.join(c for c in str(x or '') if c.isdigit());return s[:8] if len(s)>=8 else ''
def load(p):
 try:
  x=json.loads(p.read_text());return x if isinstance(x,list) else []
 except:return []
def sym(p):
 a=p.name.split('_');return f'{a[0]}.{a[1]}' if len(a)>=4 and len(a[0])==6 else ''
def dp(s):
 a,b=s.split('.');return KDAY/f'{a}_{b}_daily_750.json'
def daily_context(ind):
 g=defaultdict(list);cal=set()
 for p in KDAY.glob('*_daily_750.json'):
  s=sym(p);z=ind.get(s)
  if not z:continue
  prev=math.nan
  for b in sorted(load(p),key=lambda x:dn(x.get('t') or x.get('date'))):
   d=dn(b.get('t') or b.get('date'));c,h=f(b.get('c')),f(b.get('h'))
   if not d or c<=0:continue
   cal.add(d)
   if prev>0:g[d,z].append(((c/prev-1)*100,(h/prev-1)*100 if h>0 else (c/prev-1)*100))
   prev=c
 days=sorted(cal);prevmap={days[i]:days[i-1] for i in range(1,len(days))};active={}
 for k,v in g.items():
  if len(v)>=5:active[k]=(sum(y>=9.5 for _,y in v)>=3 or sum(x>=5 for x,_ in v)*100/len(v)>=20)
 return active,prevmap
def main():
 ind={str(x['symbol']):str(x['industry']) for x in json.loads(MAP.read_text()) if x.get('symbol') and x.get('industry')}
 active,prevmap=daily_context(ind);first=defaultdict(list);stockbars={}
 for p in K60.glob('*_60min_500.json'):
  s=sym(p);z=ind.get(s)
  if not z:continue
  by=defaultdict(list)
  for b in sorted(load(p),key=lambda x:str(x.get('t') or '')):
   d=dn(b.get('t'))
   if d:by[d].append(b)
  for d,bs in by.items():
   bs=sorted(bs,key=lambda x:str(x.get('t') or ''))
   if len(bs)<2:continue
   b1,b2=bs[0],bs[1];o,c=f(b1.get('o')),f(b1.get('c'))
   if o>0 and c>0:
    ret=(c/o-1)*100;first[d,z].append((s,ret,b1,b2));stockbars[s,d]=(b1,b2)
 # Establish industry leadership entirely from first 60m bars.
 leader={}
 for d in {k[0] for k in first}:
  vals=[]
  for (dd,z),rs in first.items():
   if dd!=d or len(rs)<5:continue
   r=[x[1] for x in rs];vals.append((z,median(r),sum(x>=0 for x in r)*100/len(r),len(r)))
  vals.sort(key=lambda x:x[1],reverse=True);n=len(vals)
  for rank,(z,ret,up,cnt) in enumerate(vals,1):leader[d,z]=(rank/n*100<=33.333333 and up>=60,rank,n,ret,up,cnt)
 rows=[]
 for (s,d),(b1,b2) in stockbars.items():
  z=ind[s];prior=prevmap.get(d,'');state=leader.get((d,z))
  if not prior or not active.get((prior,z),False) or not state or not state[0]:continue
  o1,c1,l1,h1,v1=f(b1.get('o')),f(b1.get('c')),f(b1.get('l')),f(b1.get('h')),f(b1.get('v'))
  c2,l2,v2=f(b2.get('c')),f(b2.get('l')),f(b2.get('v'))
  if not(o1>0 and c1>=o1 and l2>=l1 and v2>=v1 and c2>h1):continue
  daily=sorted(load(dp(s)),key=lambda x:dn(x.get('t') or x.get('date')));ds=[dn(x.get('t') or x.get('date')) for x in daily]
  if d not in ds:continue
  rows.append({'symbol':s,'industry':z,'prior_industry_date':prior,'event_date':d,'entry_date':d,'first60_time':str(b1.get('t')),'second60_time':str(b2.get('t')),'first_open':round(o1,6),'first_low':round(l1,6),'first_high':round(h1,6),'first_close':round(c1,6),'second_close':round(c2,6),'first_volume':round(v1,6),'second_volume':round(v2,6),'industry_rank':state[1],'eligible_industries':state[2],'industry_first60_median_ret':round(state[3],6),'industry_first60_up_pct':round(state[4],6),'industry_member_count':state[5],'entry_pre_fee':round(c2,6),'stop_pre_entry':round(l1*.99,6),'semantic_path':'PRIOR_INDUSTRY_ACTIVATION->FIRST60_INDUSTRY_LEADER->STOCK_FIRST60_HOLD->SECOND60_MICRO_BOS->SAME_SESSION_ENTRY'})
 rows.sort(key=lambda x:(x['event_date'],x['symbol']));ids={(x['symbol'],x['event_date']) for x in rows};assert len(ids)==len(rows)
 forbid={'pnl','exit','reason','hold','mfe','mae','won'};assert not(set().union(*(set(x) for x in rows))&forbid)
 yr=defaultdict(int)
 for r in rows:yr[r['event_date'][:4]]+=1
 OUT.mkdir(parents=True,exist_ok=True);rp=OUT/'v566_seed_rows.csv'
 with rp.open('w',newline='') as h:
  w=csv.DictWriter(h,fieldnames=sorted(set().union(*(set(x) for x in rows))));w.writeheader();w.writerows(rows)
 report={'version':'V566_INDUSTRY_ACTIVATION_M60_MICRO_CONTINUATION_SEED_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),'preregistration':str(PREREG),'support':{'seeds':len(rows),'year_counts':dict(sorted(yr.items())),'unique_symbol_event_identities':len(ids)},'invariants':{'no_outcome_fields_read':True,'duplicate_identity_count':0,'production_write':False,'frontend_write':False,'watchlist_write':False},'artifacts':{'dir':str(OUT),'rows':str(rp),'summary':str(OUT/'v566_report.json')}}
 (OUT/'v566_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({'status':'PASS','latest':str(LATEST),'support':report['support'],'invariants':report['invariants']},ensure_ascii=False))
if __name__=='__main__':main()
