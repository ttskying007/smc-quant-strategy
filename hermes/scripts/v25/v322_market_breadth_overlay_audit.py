#!/usr/bin/env python3
"""V322 no-write: market breadth environment overlay for V185.

New information source after V320/V321 raw supply failure: full-market breadth
known before entry. Tests whether V185 weak years/losses are market-regime driven.
No production/frontend/watchlist writes.
"""
from __future__ import annotations
import json, math
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path
from statistics import mean, median
ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'; TS=datetime.now().strftime('%Y%m%d_%H%M%S')
OUT=AUD/f'v322_market_breadth_overlay_no_write_{TS}'; LATEST=AUD/'v322_market_breadth_overlay_latest.json'; V185=ROOT/'smc_opt_v185_combined_production_candidate/v185_trades.json'
GATE={'n_min':300,'min_year_n_min':40,'wr_min':87.0,'avg_min':6.8,'year_wr_min':84.0,'micro_max':1.0}
def f(x,d=None):
 try:
  if x in (None,''): return d
  v=float(x); return d if math.isnan(v) or math.isinf(v) else v
 except Exception: return d
def dkey(v):
 s=''.join(ch for ch in str(v or '') if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def load_bars(p):
 try: data=json.load(open(p))
 except Exception: return []
 if isinstance(data,dict):
  for k in ('data','bars','klines'):
   if isinstance(data.get(k),list): data=data[k]; break
 out=[]
 for b in data if isinstance(data,list) else []:
  t=dkey(b.get('t') or b.get('date') or b.get('day')); c=f(b.get('c')); o=f(b.get('o'))
  if t and c and o: out.append((t,o,c))
 return sorted(out)
def metrics(rows):
 n=len(rows)
 if not n: return {'n':0}
 vals=[f(r.get('pnl_pct'),0) for r in rows]; yrs=defaultdict(list)
 for r,p in zip(rows,vals): yrs[dkey(r.get('entry_date'))[:4]].append(p)
 yc={y:len(v) for y,v in sorted(yrs.items())}; yw={y:round(sum(x>=0.8 for x in v)/len(v)*100,4) for y,v in sorted(yrs.items())}
 m={'n':n,'wr':round(sum(x>=0.8 for x in vals)/n*100,4),'gross_wr':round(sum(x>0 for x in vals)/n*100,4),'avg':round(mean(vals),4),'median':round(median(vals),4),'loss_pct':round(sum(x<0 for x in vals)/n*100,4),'micro_profit_pct':round(sum(0<x<0.8 for x in vals)/n*100,4),'min_year_n':min(yc.values()) if yc else 0,'year_counts':yc,'year_wr':yw,'all_year_wr_min':round(min(yw.values()),4) if yw else 0,'same_day_exit_violations':sum(dkey(r.get('entry_date'))==dkey(r.get('exit_date')) for r in rows),'exit_counts':dict(Counter(str(r.get('exit_reason') or '') for r in rows))}
 m['gate_status']='PRODUCTION_PASS' if (m['same_day_exit_violations']==0 and m['n']>=GATE['n_min'] and m['min_year_n']>=GATE['min_year_n_min'] and m['wr']>=GATE['wr_min'] and m['avg']>=GATE['avg_min'] and m['all_year_wr_min']>=GATE['year_wr_min'] and m['micro_profit_pct']<=GATE['micro_max']) else 'FAIL'
 return m
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 # Build daily breadth from all local bars: advancer ratio and 5d market momentum.
 daily=defaultdict(lambda: {'n':0,'adv':0,'ret_sum':0.0})
 for p in sorted(KDIR.glob('*_daily_750.json')):
  bars=load_bars(p)
  for i,(t,o,c) in enumerate(bars):
   if i==0: continue
   pc=bars[i-1][2]
   if pc<=0: continue
   ret=(c/pc-1)*100
   d=daily[t]; d['n']+=1; d['adv']+= 1 if ret>0 else 0; d['ret_sum']+=ret
 dates=sorted(daily)
 breadth={}
 for idx,t in enumerate(dates):
  d=daily[t]; adv=d['adv']/d['n']*100 if d['n'] else 0; avg=d['ret_sum']/d['n'] if d['n'] else 0
  prev=dates[max(0,idx-5):idx]
  avg5=mean([daily[x]['ret_sum']/daily[x]['n'] for x in prev if daily[x]['n']]) if prev else 0
  adv5=mean([daily[x]['adv']/daily[x]['n']*100 for x in prev if daily[x]['n']]) if prev else adv
  breadth[t]={'market_adv_pct':round(adv,4),'market_avg_ret_pct':round(avg,4),'market_adv5_pct':round(adv5,4),'market_avg5_ret_pct':round(avg5,4),'market_n':d['n']}
 rows=json.load(open(V185))
 # use previous available trading day breadth before entry.
 bdates=sorted(breadth)
 def prev_breadth(ed):
  cand=[x for x in bdates if x<ed]
  return breadth[cand[-1]] if cand else {}
 enriched=[]
 for r in rows:
  x=dict(r); x['_breadth']=prev_breadth(dkey(r.get('entry_date'))); enriched.append(x)
 feats=['market_adv_pct','market_avg_ret_pct','market_adv5_pct','market_avg5_ret_pct']
 candidates=[]
 for feat in feats:
  vals=sorted(x['_breadth'].get(feat) for x in enriched if isinstance(x['_breadth'].get(feat),(int,float)))
  for q in (0.15,0.2,0.25,0.3,0.35,0.4,0.45,0.5,0.55,0.6,0.65,0.7,0.75,0.8,0.85):
   th=vals[int((len(vals)-1)*q)]
   for op in ('<=','>='):
    sel=[x for x in enriched if x['_breadth'].get(feat) is not None and ((x['_breadth'][feat]<=th) if op=='<=' else (x['_breadth'][feat]>=th))]
    if len(sel)<120: continue
    m=metrics(sel); m['rule']=f'{feat}{op}{round(th,6)}'; candidates.append(m)
 # pairs from top singles
 parsed=[]
 for c in sorted(candidates,key=lambda z:(z['wr'],z['avg'],z['n']),reverse=True)[:40]:
  rule=c['rule'];
  if '<=' in rule: a,b=rule.split('<='); parsed.append((a,'<=',float(b)))
  else: a,b=rule.split('>='); parsed.append((a,'>=',float(b)))
 seen=set(); pairs=[]
 for i in range(len(parsed)):
  for j in range(i+1,len(parsed)):
   if parsed[i][0]==parsed[j][0]: continue
   key=tuple(sorted([parsed[i],parsed[j]]))
   if key in seen: continue
   seen.add(key)
   conds=[parsed[i],parsed[j]]; sel=[]
   for x in enriched:
    ok=True
    for a,op,th in conds:
     v=x['_breadth'].get(a)
     if v is None or (op=='<=' and not v<=th) or (op=='>=' and not v>=th): ok=False; break
    if ok: sel.append(x)
   if len(sel)<120: continue
   m=metrics(sel); m['rule']=' AND '.join(f'{a}{op}{round(th,6)}' for a,op,th in conds); pairs.append(m)
 allc=candidates+pairs; ranked=sorted(allc,key=lambda z:(z['gate_status']=='PRODUCTION_PASS',z['wr'],z['avg'],z['all_year_wr_min'],z['n']),reverse=True); passes=[x for x in ranked if x['gate_status']=='PRODUCTION_PASS']
 base=metrics(rows); best=ranked[0] if ranked else {}
 report={'version':'V322_MARKET_BREADTH_OVERLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'gate':GATE,'daily_breadth_dates':len(breadth),'baseline_v185':base,'coverage':{'rows':len(rows),'features':feats,'single_rules':len(candidates),'pair_rules':len(pairs)},'production_pass_count':len(passes),'production_pass_top10':passes[:10],'frontier_top30':ranked[:30],'best':best,'decision':'V322_PRODUCTION_PASS__REQUIRES_CURRENT_SCANNER_BREADTH_DRYRUN' if passes else 'V322_NO_PRODUCTION_PASS__MARKET_BREADTH_OVERLAY_CLOSED','artifacts':{'report':str(OUT/'v322_report.json'),'all_results':str(OUT/'v322_all_results.json'),'latest':str(LATEST)}}
 json.dump(report,open(OUT/'v322_report.json','w'),ensure_ascii=False,indent=2); json.dump(ranked,open(OUT/'v322_all_results.json','w'),ensure_ascii=False,indent=2); json.dump(report,open(LATEST,'w'),ensure_ascii=False,indent=2)
 print(json.dumps({'latest':str(LATEST),'daily_breadth_dates':len(breadth),'coverage':report['coverage'],'production_pass_count':len(passes),'decision':report['decision'],'best':best},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
