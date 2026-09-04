#!/usr/bin/env python3
"""Fast V69 high-WR probe.

Purpose: test if 90% WR is reachable under strict non-leaky L→D with tiny TP / wide SL.
Creates full-market report and best-trade artifact only if a candidate exists.
"""
import json, importlib.util
from pathlib import Path
from collections import defaultdict
from datetime import datetime

BASE = Path('/root/.hermes/scripts/v25/phase2_strict_ld_backtest.py')
spec = importlib.util.spec_from_file_location('ld', BASE)
ld = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ld)
KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v69_high_wr_probe')
OUT.mkdir(parents=True, exist_ok=True)

def f(x):
    try: return float(x or 0)
    except Exception: return 0.0

def d(ks,i): return ld.d(ks[i]) if 0 <= i < len(ks) else ''

def swing_low(ks, upto, lookback=30):
    vals=[]
    for i in range(max(3,upto-lookback), max(3,upto-3)+1):
        if i+3 < len(ks) and ld.is_swing_low(ks,i,3,3): vals.append((i,f(ks[i].get('l'))))
    return vals[-1] if vals else (None,0.0)

def first_fill(ks,start,end,price):
    for i in range(start, min(end, len(ks)-62)):
        lo,hi,cl=f(ks[i].get('l')),f(ks[i].get('h')),f(ks[i].get('c'))
        if lo <= price <= hi: return i
        if cl < price*0.97: return None
    return None

def sim(ks, entry_idx, ep, sl, tp, max_hold):
    if not (ep>sl>0 and tp>ep): return None
    for j in range(entry_idx+1, min(len(ks), entry_idx+max_hold+1)):
        lo,hi=f(ks[j].get('l')),f(ks[j].get('h'))
        if lo <= sl: return j,'SL', (sl/ep-1)*100
        if hi >= tp: return j,'TP', (tp/ep-1)*100
    if entry_idx+max_hold < len(ks):
        px=f(ks[entry_idx+max_hold].get('c')); return entry_idx+max_hold,'TIME',(px/ep-1)*100
    return None

def add_metric(m, pnl, reason):
    m['n']+=1; m['wins'] += pnl>0; m['sum'] += pnl
    m['tp'] += reason=='TP'; m['sl'] += reason=='SL'; m['time'] += reason=='TIME'

CONFIGS=[]
for entry_model in ('ZONE_HIGH_20','ZONE_MID','ZONE_LOW_35'):
  for sl_model in ('STRUCT_ATR','LIQ_WIDE'):
    for sl_atr in (0.5,0.8,1.2,1.8,2.5):
      for tp_rr in (0.03,0.05,0.08,0.10,0.12,0.15,0.20,0.25,0.30):
        for max_hold in (3,5,10,20,40,60):
          CONFIGS.append((entry_model,sl_model,sl_atr,tp_rr,max_hold))
FILTERS=[]
for risk_lo,risk_hi in ((1,4),(2,6),(3,8),(4,10),(5,12),(6,15),(1,15)):
  for retr_lo,retr_hi in ((30,60),(40,70),(50,80),(60,90),(30,90)):
    for disp_lo in (0,0.8,1.2,1.8,2.5):
      for pierce_lo in (0,0.5,1.0,1.5):
        FILTERS.append((risk_lo,risk_hi,retr_lo,retr_hi,disp_lo,pierce_lo))

metrics=defaultdict(lambda:{'n':0,'wins':0,'sum':0.0,'tp':0,'sl':0,'time':0})
# keep candidate keys that may pass high WR after initial aggregate; no rows stored in first pass
files=sorted(KLINE_DIR.glob('*_daily_750.json'))
print('V69 high-WR fast probe',len(files),'stocks',datetime.now().strftime('%H:%M:%S'),flush=True)
base_count=0
for idx,kf in enumerate(files,1):
    sym=kf.stem.replace('_daily_750','')
    symbol=sym.replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
    try: ks=json.loads(kf.read_text())
    except Exception: continue
    if len(ks)<180: continue
    for b in ks:
        for k in ('o','h','l','c','v'):
            if k in b: b[k]=f(b[k])
    for L in ld.find_ssl_sweeps(ks):
        D=ld.find_displacement_after(ks,L['bar'])
        if not D: continue
        for poi in ld.demand_pois(ks,L['bar'],D['bar']):
            if poi.get('type')!='FVG_Demand': continue
            zl,zh=f(poi.get('low')),f(poi.get('high'))
            if not (zl>0 and zh>zl): continue
            start=max(D['bar']+1, poi.get('bar',D['bar'])+1)
            atr=ld.atr(ks,D['bar'])
            for entry_model, ep in (('ZONE_HIGH_20',zl+(zh-zl)*0.80),('ZONE_MID',(zl+zh)/2),('ZONE_LOW_35',zl+(zh-zl)*0.35)):
                fill=first_fill(ks,start,D['bar']+20,ep)
                if fill is None: continue
                base_count += 1
                atr2=ld.atr(ks,fill)
                sw_i,sw=swing_low(ks,fill,30)
                anchor=min([x for x in (sw,L.get('liq_price'),zl) if x and x>0])
                retr=max(0,min(100,(zh-f(ks[fill].get('l')))/max(zh-zl,1e-9)*100))
                disp=f(D.get('disp_atr')); pierce=f(L.get('pierce_atr'))
                for sl_model in ('STRUCT_ATR','LIQ_WIDE'):
                  for sl_atr in (0.5,0.8,1.2,1.8,2.5):
                    sl=(anchor-atr2*sl_atr) if sl_model=='STRUCT_ATR' else (min(anchor,L.get('liq_price') or anchor)-atr2*sl_atr)
                    if not (sl>0 and ep>sl): continue
                    risk=(ep/sl-1)*100
                    if risk<1 or risk>=15: continue
                    for tp_rr in (0.03,0.05,0.08,0.10,0.12,0.15,0.20,0.25,0.30):
                      tp=ep+(ep-sl)*tp_rr
                      # simulate once for all max_hold; shorter maxhold may TIME before hit
                      for max_hold in (3,5,10,20,40,60):
                        res=sim(ks,fill,ep,sl,tp,max_hold)
                        if not res: continue
                        _,reason,pnl=res
                        for flt in FILTERS:
                            risk_lo,risk_hi,retr_lo,retr_hi,disp_lo,pierce_lo=flt
                            if risk_lo<=risk<risk_hi and retr_lo<=retr<retr_hi and disp>=disp_lo and pierce>=pierce_lo:
                                key=(entry_model,sl_model,sl_atr,tp_rr,max_hold,flt)
                                add_metric(metrics[key],pnl,reason)
    if idx%500==0: print(idx,'base',base_count,'keys',len(metrics),flush=True)

leader=[]
for key,m in metrics.items():
    n=m['n']
    if n<30: continue
    wr=m['wins']/n*100; avg=m['sum']/n
    if wr>=88 or (n>=100 and wr>=85) or (n>=300 and wr>=80):
        leader.append({'key':key,'n':n,'wr':round(wr,2),'avg_pnl':round(avg,4),'tp_rate':round(m['tp']/n*100,2),'sl_rate':round(m['sl']/n*100,2),'time_rate':round(m['time']/n*100,2)})
leader.sort(key=lambda x:(x['wr'],min(x['n'],500),x['avg_pnl']), reverse=True)
report={'generated_at':datetime.now().isoformat(timespec='seconds'),'stocks':len(files),'base_entries':base_count,'searched_keys':len(metrics),'passed_90_count':sum(1 for x in leader if x['wr']>=90),'leaderboard':leader[:100]}
(OUT/'v69_high_wr_probe_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str))
print(json.dumps(report,ensure_ascii=False,indent=2,default=str)[:20000])
print('Saved',OUT)
