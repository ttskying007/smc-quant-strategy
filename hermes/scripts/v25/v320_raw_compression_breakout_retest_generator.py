#!/usr/bin/env python3
"""V320 no-write: raw daily K-line supply generator.

New information content after V315-V319 closure. This does NOT filter V185/V167
rows. It scans raw daily K-line cache for a structural story:

  accumulation/compression -> displacement breakout -> demand retest -> reclaim entry

Then replays T+1 exits. Writes audit artifacts only.
"""
from __future__ import annotations

import json, math, glob
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median

ROOT = Path('/root/.hermes')
KDIR = ROOT / 'kline_cache'
AUD = ROOT / 'smc_audit'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUD / f'v320_raw_compression_breakout_retest_no_write_{TS}'
LATEST = AUD / 'v320_raw_compression_breakout_retest_latest.json'
V185 = ROOT / 'smc_opt_v185_combined_production_candidate' / 'v185_trades.json'

GATE = {'n_min':300,'min_year_n_min':40,'wr_min':87.0,'avg_min':6.8,'year_wr_min':84.0,'micro_max':1.0}
PARAMS=[]
for lookback in (15,20,30):
  for max_range in (10,12,15,18):
    for break_buf in (0.5,1.0,1.5):
      for retest_wait in (3,5,8):
        for retest_tol in (0.5,1.0,1.5):
          PARAMS.append({'lookback':lookback,'max_range':max_range,'break_buf':break_buf,'retest_wait':retest_wait,'retest_tol':retest_tol})
EXITS=[]
for rr in (1.2,1.5,1.8,2.0):
  for hold in (8,10,15,20):
    EXITS.append({'rr':rr,'hold':hold})

def f(x, default=None):
  try:
    if x in (None,''): return default
    v=float(x)
    return default if math.isnan(v) or math.isinf(v) else v
  except Exception: return default

def dkey(v):
  s=''.join(ch for ch in str(v or '') if ch.isdigit())
  return s[:8] if len(s)>=8 else ''

def pct(a,b): return None if a is None or b in (None,0) else (a/b-1)*100

def load_bars(p:Path):
  try: data=json.load(open(p))
  except Exception: return []
  if isinstance(data,dict):
    for k in ('data','bars','klines'):
      if isinstance(data.get(k),list): data=data[k]; break
  out=[]
  for b in data if isinstance(data,list) else []:
    o,h,l,c=f(b.get('o')),f(b.get('h')),f(b.get('l')),f(b.get('c'))
    t=dkey(b.get('t') or b.get('date') or b.get('day'))
    v=f(b.get('v'),0)
    if t and None not in (o,h,l,c): out.append({'t':t,'o':o,'h':h,'l':l,'c':c,'v':v})
  return sorted(out,key=lambda x:x['t'])

def symbol_from_path(p:Path):
  stem=p.name.replace('_daily_750.json','').replace('_daily_300.json','')
  parts=stem.split('_')
  if len(parts)>=2: return f'{parts[0]}.{parts[1]}'
  return stem

def simulate(sym,bars,entry_i,entry,sl,rr,hold,meta):
  if entry_i>=len(bars) or entry<=0 or sl<=0 or sl>=entry: return None
  risk=entry-sl; tp=entry+risk*rr
  # A-share T+1: exits start next trading day after entry date.
  best=-1e18; worst=1e18
  for k in range(entry_i+1, min(len(bars), entry_i+1+hold)):
    b=bars[k]; best=max(best,b['h']); worst=min(worst,b['l'])
    if b['o']<=sl:
      pnl=pct(b['o'],entry); reason='GAP_SL'; price=b['o']
      return finish(sym,bars[entry_i],b,entry,sl,tp,pnl,reason,price,k-entry_i,best,worst,risk,meta,rr,hold)
    if b['l']<=sl:
      pnl=pct(sl,entry); reason='SL'; price=sl
      return finish(sym,bars[entry_i],b,entry,sl,tp,pnl,reason,price,k-entry_i,best,worst,risk,meta,rr,hold)
    if b['h']>=tp:
      pnl=pct(tp,entry); reason='TP'; price=tp
      return finish(sym,bars[entry_i],b,entry,sl,tp,pnl,reason,price,k-entry_i,best,worst,risk,meta,rr,hold)
  k=min(len(bars)-1, entry_i+hold)
  if k<=entry_i: return None
  b=bars[k]; best=max(best,b['h']); worst=min(worst,b['l'])
  pnl=pct(b['c'],entry); return finish(sym,bars[entry_i],b,entry,sl,tp,pnl,'TIME',b['c'],k-entry_i,best,worst,risk,meta,rr,hold)

def finish(sym,eb,xb,entry,sl,tp,pnl,reason,price,hold,best,worst,risk,meta,rr,max_hold):
  return {
    'symbol':sym,'entry_date':eb['t'],'exit_date':xb['t'],'entry_price':round(entry,4),'exit_price':round(price,4),
    'sl':round(sl,4),'tp':round(tp,4),'rr':rr,'max_hold':max_hold,'hold_bars':hold,
    'pnl_pct':round(pnl,4),'exit_reason':reason,'same_day_exit_violation':eb['t']==xb['t'],
    'mfe_pct':round(pct(best,entry),4),'mae_pct':round(pct(worst,entry),4),'mfe_r':round((best-entry)/risk,4),'mae_r':round((worst-entry)/risk,4),
    **meta
  }

def gen_signals(sym,bars,param):
  L=param['lookback']; out=[]; last_entry=-999
  # i is breakout bar after compression window [i-L, i)
  for i in range(L+1, len(bars)-12):
    win=bars[i-L:i]
    hi=max(b['h'] for b in win); lo=min(b['l'] for b in win)
    rng=pct(hi,lo)
    if rng is None or rng>param['max_range']: continue
    b=bars[i]
    body=pct(abs(b['c']-b['o']), b['o']) or 0
    if b['c'] <= hi*(1+param['break_buf']/100): continue
    # displacement: close near top and bullish body
    if b['c']<=b['o'] or body<1.0: continue
    if (b['c']-b['l'])/(b['h']-b['l']+1e-9) < 0.65: continue
    # demand zone: last down/small candle in compression, or compression high/low shelf
    dz_low=lo; dz_high=hi
    for j in range(i-1, max(i-L,0), -1):
      if bars[j]['c'] <= bars[j]['o']:
        dz_low=min(bars[j]['o'],bars[j]['c'],bars[j]['l']); dz_high=max(bars[j]['o'],bars[j]['c'])
        break
    for r in range(i+1, min(len(bars)-2, i+1+param['retest_wait'])):
      rb=bars[r]
      # Retest old range high/demand zone, then close back above old range high.
      touched = rb['l'] <= hi*(1+param['retest_tol']/100)
      reclaimed = rb['c'] >= hi and rb['c'] > rb['o']
      if not (touched and reclaimed): continue
      entry_i=r+1
      if entry_i<=last_entry+5: break
      if entry_i>=len(bars): break
      entry=bars[entry_i]['o']
      sl=min(dz_low, rb['l'])*0.995
      risk_pct=pct(entry,sl)
      if risk_pct is None or risk_pct<2.0 or risk_pct>9.0: continue
      meta={'event_type':'RAW_COMPRESSION_BREAKOUT_RETEST_RECLAIM','breakout_date':b['t'],'retest_date':rb['t'],'lookback':L,'compression_range_pct':round(rng,4),'break_buf':param['break_buf'],'retest_wait':param['retest_wait'],'retest_tol':param['retest_tol'],'risk_pct':round(risk_pct,4),'zone_low':round(dz_low,4),'zone_high':round(dz_high,4),'prior_range_high':round(hi,4),'raw_generator':'V320'}
      out.append((entry_i,entry,sl,meta)); last_entry=entry_i; break
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
  v185_keys=set()
  if V185.exists():
    v185_keys={(r.get('symbol'),dkey(r.get('entry_date'))) for r in json.load(open(V185))}
  files=sorted(KDIR.glob('*_daily_750.json'))
  if not files: files=sorted(KDIR.glob('*_daily_300.json'))
  # Preload bars once.
  series=[]
  for p in files:
    bars=load_bars(p)
    if len(bars)>=260: series.append((symbol_from_path(p),bars))
  results=[]; rows_by_key={}; candidate_counts=[]
  for pi,param in enumerate(PARAMS):
    base=[]
    for sym,bars in series:
      sigs=gen_signals(sym,bars,param)
      candidate_counts.append(len(sigs))
      for entry_i,entry,sl,meta in sigs:
        for ex in EXITS:
          tr=simulate(sym,bars,entry_i,entry,sl,ex['rr'],ex['hold'],meta)
          if tr: base.append(tr)
    for ex in EXITS:
      erows=[r for r in base if r['rr']==ex['rr'] and r['max_hold']==ex['hold']]
      if len(erows)<80: continue
      key=f"L{param['lookback']}_R{param['max_range']}_B{param['break_buf']}_W{param['retest_wait']}_T{param['retest_tol']}_RR{ex['rr']}_H{ex['hold']}"
      m=metrics(erows); m['config']=key; m['param']=param; m['exit']=ex; m['overlap_v185']=sum((r['symbol'],r['entry_date']) in v185_keys for r in erows); m['non_overlap_pct']=round((1-m['overlap_v185']/len(erows))*100,2) if erows else 0
      results.append(m); rows_by_key[key]=erows
  ranked=sorted(results,key=lambda x:(x['gate_status']=='PRODUCTION_PASS',x['wr'],x['avg'],x['all_year_wr_min'],x['n']),reverse=True)
  best=ranked[0] if ranked else {}
  best_rows=rows_by_key.get(best.get('config',''),[])
  pass_rows=[r for r in ranked if r['gate_status']=='PRODUCTION_PASS']
  report={'version':'V320_RAW_COMPRESSION_BREAKOUT_RETEST_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'gate':GATE,'scanned_files':len(files),'usable_symbols':len(series),'param_count':len(PARAMS),'exit_count':len(EXITS),'results_count':len(results),'production_pass_count':len(pass_rows),'production_pass_top10':pass_rows[:10],'frontier_top30':ranked[:30],'best':best,'decision':'V320_PRODUCTION_PASS__REQUIRES_CURRENT_SCANNER_DRYRUN' if pass_rows else 'V320_NO_PRODUCTION_PASS__RAW_COMPRESSION_BREAKOUT_RETEST_CLOSED','artifacts':{'report':str(OUT/'v320_report.json'),'all_results':str(OUT/'v320_all_results.json'),'best_rows':str(OUT/'v320_best_rows.json'),'latest':str(LATEST)}}
  json.dump(report,open(OUT/'v320_report.json','w'),ensure_ascii=False,indent=2)
  json.dump(ranked,open(OUT/'v320_all_results.json','w'),ensure_ascii=False,indent=2)
  json.dump(best_rows,open(OUT/'v320_best_rows.json','w'),ensure_ascii=False,indent=2)
  json.dump(report,open(LATEST,'w'),ensure_ascii=False,indent=2)
  print(json.dumps({'latest':str(LATEST),'usable_symbols':len(series),'param_count':len(PARAMS),'exit_count':len(EXITS),'results_count':len(results),'production_pass_count':len(pass_rows),'decision':report['decision'],'best':best},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
