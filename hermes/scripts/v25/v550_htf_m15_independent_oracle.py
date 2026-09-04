#!/usr/bin/env python3
"""Independent identity Oracle for frozen V548 HTF->m15 seeds; no outcomes."""
from __future__ import annotations
import csv, gzip, json, math
from bisect import bisect_right
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

ROOT=Path('/root/.hermes'); RAW=ROOT/'intraday_cache/raw_multitf_v536/source_raw/sina'; AUDIT=ROOT/'smc_audit'
V548=AUDIT/'v548_htf_trend_m15_entry_seed_gate_latest.json'
OUT=AUDIT/f'v550_htf_m15_independent_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST=AUDIT/'v550_htf_m15_independent_oracle_latest.json'
L=R=3; LB=20; SWEEP=.003; Q=.80; BOS=12; RETEST=20; DR=DV=1.20; FVG=.50; RV=1.0
ID=('symbol','weekly_trend_confirm_date','weekly_latest_hl_date','weekly_structure_high_date','daily_trend_confirm_date','daily_latest_hl_date','daily_structure_high_date','m15_ssl_pivot_time','m15_sweep_time','m15_bos_time','m15_fvg_time','m15_reclaim_time','entry_time')

def f(x:Any)->float|None:
 try:
  y=float(x); return y if y>0 and math.isfinite(y) else None
 except (TypeError,ValueError): return None

def bars(path:Path, m15:bool)->list[dict]:
 try:
  with gzip.open(path,'rt',encoding='utf-8') as h: raw=json.load(h)
 except (OSError,ValueError): return []
 out=[]
 for x in raw if isinstance(raw,list) else []:
  t=str(x.get('t') or ''); d=str(x.get('d') or t[:8])[:8]; z=[f(x.get(k)) for k in ('o','h','l','c','v')]
  if len(d)==8 and (len(t)==14 if m15 else True) and all(v is not None for v in z): out.append({'t':t if m15 else d,'d':d,'o':z[0],'h':z[1],'l':z[2],'c':z[3],'v':z[4]})
 return sorted(out,key=lambda x:x['t'])

def pivot(rows:list[dict])->tuple[list[tuple[int,int,float]],list[tuple[int,int,float]]]:
 lo=[]; hi=[]
 for i in range(L,len(rows)-R):
  left,right=rows[i-L:i],rows[i+1:i+R+1]
  if rows[i]['l']<min(x['l'] for x in left) and rows[i]['l']<=min(x['l'] for x in right): lo.append((i,i+R,rows[i]['l']))
  if rows[i]['h']>max(x['h'] for x in left) and rows[i]['h']>=max(x['h'] for x in right): hi.append((i,i+R,rows[i]['h']))
 return lo,hi

def completed_weekly(daily:list[dict])->list[dict]:
 groups=[]; key=None
 for x in daily:
  k=datetime.strptime(x['d'],'%Y%m%d').date().isocalendar()[:2]
  if k!=key: groups.append([]); key=k
  groups[-1].append(x)
 return [{'d':g[-1]['d'],'o':g[0]['o'],'h':max(x['h'] for x in g),'l':min(x['l'] for x in g),'c':g[-1]['c'],'v':sum(x['v'] for x in g)} for g in groups[:-1] if g]

def uptrend(rows:list[dict], lo:list, hi:list, before:str)->dict|None:
 dates=[x['d'] for x in rows]; end=bisect_right(dates,before)-1
 if end>=0 and rows[end]['d']>=before: end-=1
 lc=bisect_right([x[1] for x in lo],end); hc=bisect_right([x[1] for x in hi],end)
 if end<2*R+8 or lc<2 or hc<1: return None
 a,b=lo[lc-2],lo[lc-1]; highs=hi[:hc]; sh=next((x for x in reversed(highs) if x[0]>b[0]),highs[-1])
 if not(b[2]>a[2] and rows[end]['c']>sh[2]): return None
 return {'confirm':rows[end]['d'],'hl':rows[b[0]]['d'],'sh':rows[sh[0]]['d']}

def base(rows:list[dict],i:int):
 if i<LB:return None
 p=rows[i-LB:i]; ranges=[x['h']-x['l'] for x in p]; vols=sorted(x['v'] for x in p)
 return median(ranges),vols[math.ceil(Q*len(vols))-1],median(vols)

def derive(path:Path)->tuple[list[dict],str|None]:
 symbol=path.name.removesuffix('_m15.json.gz').replace('_','.')
 m=bars(path,True); d=bars(RAW/'daily'/path.name.replace('_m15.json.gz','_daily.json.gz'),False); w=completed_weekly(d)
 if len(m)<100 or len(d)<40 or len(w)<12:return [],'short'
 ml,mh=pivot(m); wl,wh=pivot(w); dl,dh=pivot(d); lo={x[0] for x in ml}; hi={x[0] for x in mh}
 lastlo=lasthi=None; states=[]; out=[]; emitted=-1
 for i,x in enumerate(m):
  eligible=i-R-1
  if eligible in lo:lastlo,lasthi=eligible,None
  if eligible in hi and lastlo is not None and eligible>lastlo and m[eligible]['h']>m[lastlo]['l']:lasthi=eligible
  nextstates=[]
  for s in states:
   if s['stage']=='B':
    if i-s['sweep']<=BOS:
     q=base(m,i)
     if q and x['c']>s['ref'] and x['c']-x['o']>=q[0]*DR and x['v']>=q[2]*DV:s.update(stage='F',bos=i)
     nextstates.append(s)
   elif s['stage']=='F':
    if i-s['bos']<=RETEST:
     q=base(m,i)
     if q and i>=2 and x['l']-m[i-2]['h']>=q[0]*FVG and x['v']>=q[2]*DV:s.update(stage='T',fvg=i,gl=m[i-2]['h'],gh=x['l'])
     nextstates.append(s)
   elif i-s['fvg']<=RETEST:
    q=base(m,i); touch=i>s['fvg'] and x['l']<=s['gh'] and x['h']>=s['gl']
    if q and touch and x['c']>=s['gh'] and x['v']<=q[2]*RV:
     ei=i+1
     if ei<len(m) and ei>emitted:
      e=m[ei]; wt=uptrend(w,wl,wh,e['d']); dt=uptrend(d,dl,dh,e['d'])
      if wt and dt:
       out.append({'symbol':symbol,'weekly_trend_confirm_date':wt['confirm'],'weekly_latest_hl_date':wt['hl'],'weekly_structure_high_date':wt['sh'],'daily_trend_confirm_date':dt['confirm'],'daily_latest_hl_date':dt['hl'],'daily_structure_high_date':dt['sh'],'m15_ssl_pivot_time':m[s['pivot']]['t'],'m15_sweep_time':m[s['sweep']]['t'],'m15_bos_time':m[s['bos']]['t'],'m15_fvg_time':m[s['fvg']]['t'],'m15_reclaim_time':x['t'],'entry_time':e['t']}); emitted=ei
    else: nextstates.append(s)
  states=nextstates
  q=base(m,i)
  if q and lastlo is not None and lasthi is not None and x['l']<=m[lastlo]['l']*(1-SWEEP) and x['c']>m[lastlo]['l'] and x['v']>=q[1]: states.append({'stage':'B','pivot':lastlo,'sweep':i,'ref':m[lasthi]['h']})
 return out,None

def tup(r):return tuple(str(r[k]) for k in ID)
def main():
 frozen=json.loads(V548.read_text()); seed=Path(frozen['artifacts']['seeds'])
 with seed.open(newline='',encoding='utf-8') as h: expected={tup(x) for x in csv.DictReader(h)}
 OUT.mkdir(parents=True,exist_ok=False); got=[]; short=Counter(); ps=sorted((RAW/'m15').glob('*_m15.json.gz'))
 with ProcessPoolExecutor(max_workers=8) as pool:
  for rs,reason in pool.map(derive,ps,chunksize=16): got.extend(rs); short.update([reason] if reason else [])
 actual={tup(x) for x in got if x['entry_time'][:4] in {'2025','2026'}}; missing=expected-actual; extra=actual-expected
 p=OUT/'v550_oracle_identities.csv'
 with p.open('w',newline='',encoding='utf-8') as h:
  z=csv.DictWriter(h,fieldnames=ID);z.writeheader();z.writerows(got)
 report={'version':'V550_HTF_M15_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'scope':'SINA_PARTIAL_2025_04_TO_2026_07__EXPLORATORY_ONLY','frozen_seed_source':str(seed),'identity_fields':ID,'files_scanned':len(ps),'short_files':dict(short),'expected_identities':len(expected),'oracle_identities':len(actual),'missing_identities':len(missing),'extra_identities':len(extra),'identity_match':not missing and not extra,'samples':{'missing':[dict(zip(ID,x)) for x in sorted(missing)[:5]],'extra':[dict(zip(ID,x)) for x in sorted(extra)[:5]]},'decision':'V550_ORACLE_PASS__EXPLORATORY_FROZEN_T1_REPLAY_AUTHORIZED' if not missing and not extra else 'V550_ORACLE_MISMATCH__NO_REPLAY','artifacts':{'dir':str(OUT),'identities':str(p)}}
 text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v550_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
