#!/usr/bin/env python3
"""V321 no-write raw SSL sweep -> reclaim generator.

New raw daily supply direction distinct from V320 breakout/retest and V185/V167
filters. Looks for sell-side liquidity sweep below a prior N-day low, rapid reclaim
back above that liquidity level, and T+1 long entry.
"""
from __future__ import annotations
import json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median
ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'; TS=datetime.now().strftime('%Y%m%d_%H%M%S')
OUT=AUD/f'v321_raw_ssl_sweep_reclaim_no_write_{TS}'; LATEST=AUD/'v321_raw_ssl_sweep_reclaim_latest.json'
V185=ROOT/'smc_opt_v185_combined_production_candidate/v185_trades.json'
GATE={'n_min':300,'min_year_n_min':40,'wr_min':87.0,'avg_min':6.8,'year_wr_min':84.0,'micro_max':1.0}
PARAMS=[]
for lookback in (10,20,30,60):
 for pierce in (0.3,0.8,1.2):
  for reclaim_days in (1,2,3):
   for close_pos in (0.55,0.65,0.75):
    PARAMS.append({'lookback':lookback,'pierce':pierce,'reclaim_days':reclaim_days,'close_pos':close_pos})
EXITS=[{'rr':1.2,'hold':10},{'rr':1.5,'hold':10},{'rr':1.5,'hold':15},{'rr':1.8,'hold':15},{'rr':2.0,'hold':20}]
def f(x,d=None):
 try:
  if x in (None,''): return d
  v=float(x); return d if math.isnan(v) or math.isinf(v) else v
 except Exception: return d
def dkey(v):
 s=''.join(ch for ch in str(v or '') if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def pct(a,b): return None if a is None or b in (None,0) else (a/b-1)*100
def load_bars(p):
 try: data=json.load(open(p))
 except Exception: return []
 if isinstance(data,dict):
  for k in ('data','bars','klines'):
   if isinstance(data.get(k),list): data=data[k]; break
 out=[]
 for b in data if isinstance(data,list) else []:
  o,h,l,c=f(b.get('o')),f(b.get('h')),f(b.get('l')),f(b.get('c')); t=dkey(b.get('t') or b.get('date') or b.get('day'))
  if t and None not in (o,h,l,c): out.append({'t':t,'o':o,'h':h,'l':l,'c':c,'v':f(b.get('v'),0)})
 return sorted(out,key=lambda x:x['t'])
def sym_from(p):
 s=p.name.replace('_daily_750.json','').replace('_daily_300.json',''); a=s.split('_'); return f'{a[0]}.{a[1]}' if len(a)>=2 else s
def finish(sym,eb,xb,entry,sl,tp,pnl,reason,price,hold,best,worst,risk,meta,rr,max_hold):
 return {'symbol':sym,'entry_date':eb['t'],'exit_date':xb['t'],'entry_price':round(entry,4),'exit_price':round(price,4),'sl':round(sl,4),'tp':round(tp,4),'rr':rr,'max_hold':max_hold,'hold_bars':hold,'pnl_pct':round(pnl,4),'exit_reason':reason,'same_day_exit_violation':eb['t']==xb['t'],'mfe_pct':round(pct(best,entry),4),'mae_pct':round(pct(worst,entry),4),'mfe_r':round((best-entry)/risk,4),'mae_r':round((worst-entry)/risk,4),**meta}
def simulate(sym,bars,ei,entry,sl,rr,hold,meta):
 if ei>=len(bars)-1 or entry<=0 or sl<=0 or sl>=entry: return None
 risk=entry-sl; tp=entry+risk*rr; best=-1e18; worst=1e18
 for k in range(ei+1,min(len(bars),ei+1+hold)):
  b=bars[k]; best=max(best,b['h']); worst=min(worst,b['l'])
  if b['o']<=sl: return finish(sym,bars[ei],b,entry,sl,tp,pct(b['o'],entry),'GAP_SL',b['o'],k-ei,best,worst,risk,meta,rr,hold)
  if b['l']<=sl: return finish(sym,bars[ei],b,entry,sl,tp,pct(sl,entry),'SL',sl,k-ei,best,worst,risk,meta,rr,hold)
  if b['h']>=tp: return finish(sym,bars[ei],b,entry,sl,tp,pct(tp,entry),'TP',tp,k-ei,best,worst,risk,meta,rr,hold)
 k=min(len(bars)-1,ei+hold); b=bars[k]; best=max(best,b['h']); worst=min(worst,b['l'])
 return finish(sym,bars[ei],b,entry,sl,tp,pct(b['c'],entry),'TIME',b['c'],k-ei,best,worst,risk,meta,rr,hold)
def gen(sym,bars,p):
 out=[]; L=p['lookback']; last=-999
 for i in range(L+1,len(bars)-25):
  prior=bars[i-L:i]; ssl=min(b['l'] for b in prior); b=bars[i]
  if b['l']>ssl*(1-p['pierce']/100): continue
  # avoid pure crash: close must recover into upper half of sweep bar or within reclaim window
  for r in range(i,min(len(bars)-2,i+p['reclaim_days'])):
   rb=bars[r]; pos=(rb['c']-rb['l'])/(rb['h']-rb['l']+1e-9)
   if rb['c']>=ssl and pos>=p['close_pos'] and rb['c']>rb['o']:
    ei=r+1
    if ei<=last+5: break
    entry=bars[ei]['o']; sl=min(b['l'],rb['l'])*0.995; risk=pct(entry,sl)
    if risk is None or risk<2 or risk>9: continue
    # target room: avoid immediate overhead from prior 20d high below 1R
    hi20=max(x['h'] for x in bars[max(0,ei-20):ei]); room=pct(hi20,entry) or 0
    meta={'event_type':'RAW_SSL_SWEEP_RECLAIM','sweep_date':b['t'],'reclaim_date':rb['t'],'lookback':L,'pierce_pct':round(pct(ssl,b['l']) or 0,4),'ssl_level':round(ssl,4),'close_pos':round(pos,4),'risk_pct':round(risk,4),'prior20_room_pct':round(room,4),'raw_generator':'V321'}
    out.append((ei,entry,sl,meta)); last=ei; break
 return out
def metrics(rows):
 n=len(rows)
 if not n: return {'n':0}
 vals=[r['pnl_pct'] for r in rows]; yrs=defaultdict(list)
 for r,p in zip(rows,vals): yrs[r['entry_date'][:4]].append(p)
 yc={y:len(v) for y,v in sorted(yrs.items())}; yw={y:round(sum(x>=0.8 for x in v)/len(v)*100,4) for y,v in sorted(yrs.items())}
 m={'n':n,'wr':round(sum(x>=0.8 for x in vals)/n*100,4),'gross_wr':round(sum(x>0 for x in vals)/n*100,4),'avg':round(mean(vals),4),'median':round(median(vals),4),'loss_pct':round(sum(x<0 for x in vals)/n*100,4),'micro_profit_pct':round(sum(0<x<0.8 for x in vals)/n*100,4),'min_year_n':min(yc.values()) if yc else 0,'year_counts':yc,'year_wr':yw,'all_year_wr_min':round(min(yw.values()),4) if yw else 0,'same_day_exit_violations':sum(r['same_day_exit_violation'] for r in rows),'exit_counts':dict(Counter(r['exit_reason'] for r in rows))}
 m['gate_status']='PRODUCTION_PASS' if (m['n']>=GATE['n_min'] and m['min_year_n']>=GATE['min_year_n_min'] and m['wr']>=GATE['wr_min'] and m['avg']>=GATE['avg_min'] and m['all_year_wr_min']>=GATE['year_wr_min'] and m['micro_profit_pct']<=GATE['micro_max'] and m['same_day_exit_violations']==0) else 'FAIL'
 return m
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 v185=set()
 if V185.exists(): v185={(r.get('symbol'),dkey(r.get('entry_date'))) for r in json.load(open(V185))}
 files=sorted(KDIR.glob('*_daily_750.json')) or sorted(KDIR.glob('*_daily_300.json'))
 series=[(sym_from(p),load_bars(p)) for p in files]; series=[x for x in series if len(x[1])>=260]
 results=[]; rows_by={}
 for p in PARAMS:
  sig_by=[]
  for sym,bars in series:
   sigs=gen(sym,bars,p)
   if sigs: sig_by.append((sym,bars,sigs))
  for ex in EXITS:
   rows=[]
   for sym,bars,sigs in sig_by:
    for ei,entry,sl,meta in sigs:
     tr=simulate(sym,bars,ei,entry,sl,ex['rr'],ex['hold'],meta)
     if tr: rows.append(tr)
   if len(rows)<80: continue
   key=f"L{p['lookback']}_P{p['pierce']}_D{p['reclaim_days']}_C{p['close_pos']}_RR{ex['rr']}_H{ex['hold']}"
   m=metrics(rows); m['config']=key; m['param']=p; m['exit']=ex; m['overlap_v185']=sum((r['symbol'],r['entry_date']) in v185 for r in rows); m['non_overlap_pct']=round((1-m['overlap_v185']/len(rows))*100,2)
   results.append(m); rows_by[key]=rows
 ranked=sorted(results,key=lambda x:(x['gate_status']=='PRODUCTION_PASS',x['wr'],x['avg'],x['all_year_wr_min'],x['n']),reverse=True)
 best=ranked[0] if ranked else {}; best_rows=rows_by.get(best.get('config',''),[]); passes=[r for r in ranked if r['gate_status']=='PRODUCTION_PASS']
 report={'version':'V321_RAW_SSL_SWEEP_RECLAIM_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'gate':GATE,'scanned_files':len(files),'usable_symbols':len(series),'param_count':len(PARAMS),'exit_count':len(EXITS),'results_count':len(results),'production_pass_count':len(passes),'production_pass_top10':passes[:10],'frontier_top30':ranked[:30],'best':best,'decision':'V321_PRODUCTION_PASS__REQUIRES_CURRENT_SCANNER_DRYRUN' if passes else 'V321_NO_PRODUCTION_PASS__RAW_SSL_SWEEP_RECLAIM_CLOSED','artifacts':{'report':str(OUT/'v321_report.json'),'all_results':str(OUT/'v321_all_results.json'),'best_rows':str(OUT/'v321_best_rows.json'),'latest':str(LATEST)}}
 json.dump(report,open(OUT/'v321_report.json','w'),ensure_ascii=False,indent=2); json.dump(ranked,open(OUT/'v321_all_results.json','w'),ensure_ascii=False,indent=2); json.dump(best_rows,open(OUT/'v321_best_rows.json','w'),ensure_ascii=False,indent=2); json.dump(report,open(LATEST,'w'),ensure_ascii=False,indent=2)
 print(json.dumps({'latest':str(LATEST),'usable_symbols':len(series),'results_count':len(results),'production_pass_count':len(passes),'decision':report['decision'],'best':best},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
