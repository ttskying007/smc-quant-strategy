#!/usr/bin/env python3
from __future__ import annotations

import csv, json, math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

SRC=Path('/root/.hermes/smc_opt_v86_production_gate/v86_trades.json')
D60=Path('/root/.hermes/kline_cache_60min')
DD=Path('/root/.hermes/kline_cache')
OUT=Path('/root/.hermes/smc_opt_v87_mtf_entry_rr_matrix'); OUT.mkdir(parents=True, exist_ok=True)

def f(x, default=0.0):
    try:
        if x is None or x=='': return default
        v=float(x)
        return v if math.isfinite(v) else default
    except Exception: return default

def d(b): return str(b.get('t') or b.get('date') or '')[:8].replace('-','')
def tstamp(b): return str(b.get('t') or b.get('date') or '')
def symkey(sym): return str(sym).replace('.','_')
def load_json(p): return json.loads(Path(p).read_text()) if Path(p).exists() else []
def kpath(sym,tf):
    base=symkey(sym)
    if tf=='60':
        p=D60/f'{base}_60min_500.json'
        return p if p.exists() else D60/f'{base}_60min_200.json'
    if tf=='weekly': return DD/f'{base}_weekly_200.json'
    return DD/f'{base}_daily_750.json'

def ma(vals,n): return sum(vals[-n:])/n if len(vals)>=n else None

def daily_state(bars:List[Dict[str,Any]])->str:
    if len(bars)<5: return 'UNKNOWN'
    cs=[f(b.get('c')) for b in bars if f(b.get('c'))]
    if len(cs)<5: return 'UNKNOWN'
    m5=ma(cs,5); m20=ma(cs,20) or m5
    ret5=(cs[-1]/cs[-5]-1)*100 if cs[-5] else 0
    ret20=(cs[-1]/cs[-20]-1)*100 if len(cs)>=20 and cs[-20] else ret5
    if cs[-1]>m5 and m5>=m20 and ret5>0: return 'BULL_CONTINUATION'
    if ret5>0 and ret20>-8: return 'RECOVERY'
    if cs[-1]<m5 and ret5<0: return 'BEAR_RISK'
    return 'MIXED'

def slice_until(bars,date):
    return [b for b in bars if d(b)<=str(date).replace('-','')]

def slice_after(bars,date,max_days=80):
    ds=str(date).replace('-','')
    out=[b for b in bars if d(b)>ds]
    return out[:max_days]

def find_m60_window_for_date(bars, entry_date, lookahead_days=1):
    ds=str(entry_date).replace('-','')
    days=[]; seen=set()
    for b in bars:
        bd=d(b)
        if bd>=ds and bd not in seen:
            seen.add(bd); days.append(bd)
        if len(days)>=lookahead_days+1: break
    allow=set(days)
    return [b for b in bars if d(b) in allow]

def compute_rr(entry, sl, tp):
    entry=f(entry); sl=f(sl); tp=f(tp)
    risk=entry-sl
    if entry<=0 or risk/entry<0.001 or tp<=entry: return 0
    return (tp-entry)/risk

def m60_state(bars):
    if not bars: return 'NO_M60'
    return daily_state(bars[-30:])

def _swing_low(bars):
    lows=[f(b.get('l')) for b in bars if f(b.get('l'))]
    return min(lows) if lows else 0

def m60_entry_plan(win, zone_low, zone_high, daily_entry, mode='m60_reclaim', sl_mode='m60_reclaim_low'):
    zl,zh,de=f(zone_low),f(zone_high),f(daily_entry)
    if mode=='daily_next_open':
        ep=de; et=tstamp(win[0]) if win else ''
    elif mode=='zone_limit':
        ep=zh; et='DAILY_ZONE_LIMIT'
    else:
        ep=0; et=''
        touched=False; touch_low=0
        for i,b in enumerate(win):
            lo,hi,cl=f(b.get('l')),f(b.get('h')),f(b.get('c'))
            if lo<=zh and hi>=zl:
                touched=True; touch_low=lo if not touch_low else min(touch_low,lo)
            if not touched: continue
            if mode=='m60_reclaim' and cl>zh:
                ep=cl; et=tstamp(b); break
            if mode=='m60_higher_low' and i>=1 and lo>touch_low and cl>f(win[i-1].get('c')):
                ep=cl; et=tstamp(b); break
            if mode=='m60_mss' and i>=2:
                prev_hi=max(f(x.get('h')) for x in win[max(0,i-3):i])
                if cl>prev_hi and cl>zh: ep=cl; et=tstamp(b); break
        if ep<=0:
            return {'entry_found':False,'entry_mode':mode,'reject':'NO_M60_CONFIRM'}
    prior_low=_swing_low(win) or zl
    if sl_mode=='daily_zone_buffer': sl=zl*0.985
    elif sl_mode=='m60_swing_low': sl=min(prior_low*0.995,zl*0.992)
    elif sl_mode=='m60_reclaim_low': sl=min(prior_low*0.995,zl*0.995)
    elif sl_mode=='hybrid_tight': sl=max(min(prior_low*0.995,zl*0.995), ep*0.975)
    else: sl=zl*0.985
    risk=(ep/sl-1)*100 if sl>0 else 999
    return {'entry_found': ep>sl>0, 'entry_mode':mode, 'entry_price':round(ep,4), 'entry_time':et, 'sl':round(sl,4), 'risk_pct_v87':round(risk,4), 'm60_entry_state':m60_state(win)}

def tp_plan(entry, sl, liq, mode):
    ep,sl,liq=f(entry),f(sl),f(liq)
    r=ep-sl
    if r<=0: return None
    if mode=='rr_1_2_3': return (ep+r, ep+2*r, ep+3*r)
    if mode=='rr_1_5_3': return (ep+r, ep+1.5*r, ep+3*r)
    if mode=='liq_then_2r_runner':
        tp1=max(liq, ep+r); return (tp1, max(liq,ep+2*r), max(liq,ep+3*r))
    if mode=='micro_0_8_1_5_3': return (ep+0.8*r, ep+1.5*r, ep+3*r)
    return (ep+r,ep+2*r,ep+3*r)

def simulate_exit_legs(daily, entry_price, sl, tp1, tp2, tp3, max_hold=40):
    ep,sl,tp1,tp2,tp3=map(f,[entry_price,sl,tp1,tp2,tp3])
    risk=ep-sl
    legs=[]; remaining=1.0; exit_price=ep; reason='TIME_STOP'; pnl=0.0
    mfe=-999; mae=999; trail=None
    weights=[('TP1_HIT',tp1,0.35),('TP2_HIT',tp2,0.35),('TP3_HIT',tp3,0.30)]
    hit=set()
    for i,b in enumerate(daily[:max_hold]):
        hi,lo,cl=f(b.get('h')),f(b.get('l')),f(b.get('c'))
        mfe=max(mfe,(hi/ep-1)*100); mae=min(mae,(lo/ep-1)*100)
        if lo<=sl and not legs:
            pnl=(sl/ep-1)*100; exit_price=sl; reason='SL_HIT'; remaining=0; break
        for name,tp,w in weights:
            if name not in hit and hi>=tp and remaining>0:
                take=min(w,remaining); legs.append({'reason':name,'price':round(tp,4),'weight':take,'date':d(b)})
                pnl += take*(tp/ep-1)*100; remaining-=take; hit.add(name)
                if name in {'TP2_HIT','TP3_HIT'}:
                    trail=max(trail or sl, ep+risk)
        if remaining<=0:
            exit_price=tp3; reason='TP3_HIT'; break
        if trail and lo<=trail:
            pnl += remaining*(trail/ep-1)*100; exit_price=trail; reason='RUNNER_TRAIL'; remaining=0; break
        exit_price=cl
    if remaining>0:
        last=daily[min(len(daily),max_hold)-1] if daily else {'c':ep,'t':''}
        exit_price=f(last.get('c'),ep); pnl += remaining*(exit_price/ep-1)*100; reason='TIME_STOP'
    return {'exit_price':round(exit_price,4),'pnl_pct':round(pnl,4),'exit_reason':reason,'exit_legs':legs,'mfe_pct':round(mfe if mfe!=-999 else 0,4),'mae_pct':round(mae if mae!=999 else 0,4),'mfe_r':round((mfe/100*ep)/risk,4) if risk>0 and mfe!=-999 else 0,'mae_r':round((mae/100*ep)/risk,4) if risk>0 and mae!=999 else 0}

def metrics(rows):
    if not rows: return {'n':0,'wr':0,'avg_pnl':0,'avg_rr':0,'low_rr_rate':0}
    n=len(rows); vals=[f(r.get('pnl_pct')) for r in rows]; rrs=[f(r.get('rr')) for r in rows]
    return {'n':n,'wr':round(sum(v>0 for v in vals)/n*100,2),'avg_pnl':round(sum(vals)/n,4),'cum':round(sum(vals),2),'avg_rr':round(sum(rrs)/n,4),'low_rr_rate':round(sum(x<1 for x in rrs)/n*100,2),'avg_mfe_r':round(sum(f(r.get('mfe_r')) for r in rows)/n,3)}

def bucket(rows,key):
    g=defaultdict(list)
    for r in rows: g[str(key(r))].append(r)
    return {k:metrics(v) for k,v in sorted(g.items())}

def main():
    base=load_json(SRC); daily_cache={}; m60_cache={}; weekly_cache={}; out=[]
    entry_modes=['daily_next_open','zone_limit','m60_reclaim','m60_higher_low','m60_mss']
    sl_modes=['daily_zone_buffer','m60_swing_low','m60_reclaim_low','hybrid_tight']
    tp_modes=['rr_1_2_3','rr_1_5_3','liq_then_2r_runner','micro_0_8_1_5_3']
    for r in base:
        sym=r['symbol']
        if sym not in daily_cache: daily_cache[sym]=load_json(kpath(sym,'daily'))
        if sym not in m60_cache: m60_cache[sym]=load_json(kpath(sym,'60'))
        if sym not in weekly_cache: weekly_cache[sym]=load_json(kpath(sym,'weekly'))
        db=daily_cache[sym]; mb=m60_cache[sym]; wb=weekly_cache[sym]
        entry_date=str(r.get('entry_date'))
        pre=slice_until(db, entry_date); post=slice_after(db, entry_date, 60)
        if not post: continue
        win=find_m60_window_for_date(mb, entry_date, 1)
        wstate=daily_state(slice_until(wb, entry_date)) if wb else 'NO_WEEKLY'
        dstate=daily_state(pre); mstate=m60_state(win)
        for em in entry_modes:
          for sm in sl_modes:
            plan=m60_entry_plan(win, r.get('zone_low'), r.get('zone_high'), r.get('entry_price'), em, sm)
            if not plan.get('entry_found'): continue
            for tm in tp_modes:
                tps=tp_plan(plan['entry_price'], plan['sl'], r.get('liquidity_target'), tm)
                if not tps: continue
                rr=compute_rr(plan['entry_price'], plan['sl'], tps[1])
                sim=simulate_exit_legs(post, plan['entry_price'], plan['sl'], *tps, max_hold=40)
                nr={k:r.get(k) for k in ['symbol','entry_date','market_state','v85_path','v85_market_substate','v85_zone_width_pct']}
                nr.update(plan); nr.update(sim)
                nr.update({'engine':'V87_MTF_ENTRY_RR_MATRIX','weekly_state':wstate,'daily_state':dstate,'m60_state':mstate,'mtf_score':sum(x in {'BULL_CONTINUATION','RECOVERY','MIXED'} for x in [wstate,dstate,mstate]),'sl_mode':sm,'tp_mode':tm,'tp1':round(tps[0],4),'tp2':round(tps[1],4),'tp3':round(tps[2],4),'rr':round(rr,4),'rr_realized':round(f(sim['pnl_pct'])/f(plan['risk_pct_v87'],1),4),'low_rr':rr<1,'t1_violation':False})
                out.append(nr)
    combo_report=bucket(out,lambda r:f"{r['entry_mode']}|{r['sl_mode']}|{r['tp_mode']}")
    best=[]
    for key in sorted(set(f"{r['entry_mode']}|{r['sl_mode']}|{r['tp_mode']}" for r in out)):
        rs=[r for r in out if f"{r['entry_mode']}|{r['sl_mode']}|{r['tp_mode']}"==key]
        yy=bucket(rs,lambda r:str(r['entry_date'])[:4])
        prod=len(rs)>=500 and all(yy.get(y,{}).get('n',0)>=50 and yy.get(y,{}).get('wr',0)>=65 for y in ['2023','2024','2025','2026'])
        mm=metrics(rs); mm.update({'combo':key,'production_like':prod,'year':yy})
        best.append(mm)
    best_by_avg=sorted([x for x in best if x['production_like']], key=lambda x:(x['avg_pnl'],x['wr']), reverse=True)[:12]
    best_by_wr=sorted([x for x in best if x['production_like']], key=lambda x:(x['wr'],x['avg_pnl']), reverse=True)[:12]
    field_keys=['weekly_state','daily_state','m60_state','entry_price','sl','tp1','tp2','tp3','rr','rr_realized','exit_legs','mfe_r','mae_r']
    report={'engine':'V87_MTF_ENTRY_RR_MATRIX','source':str(SRC),'base_rows':len(base),'matrix_rows':len(out),'overall':metrics(out),'by_entry_mode':bucket(out,lambda r:r['entry_mode']),'by_sl_mode':bucket(out,lambda r:r['sl_mode']),'by_tp_mode':bucket(out,lambda r:r['tp_mode']),'by_combo':combo_report,'best_production_like_by_avg':best_by_avg,'best_production_like_by_wr':best_by_wr,'by_year':bucket(out,lambda r:str(r['entry_date'])[:4]),'by_mtf_score':bucket(out,lambda r:r['mtf_score']),'field_audit':{k:sum(1 for r in out if r.get(k) in [None,''] or (k in ['entry_price','sl','tp1','tp2','tp3','rr'] and f(r.get(k))<=0)) for k in field_keys}}
    (OUT/'v87_matrix_rows.json').write_text(json.dumps(out,ensure_ascii=False))
    (OUT/'v87_matrix_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    with (OUT/'v87_matrix_rows.csv').open('w',newline='') as fp:
        fields=list(out[0].keys()) if out else []
        w=csv.DictWriter(fp,fieldnames=fields); w.writeheader(); w.writerows(out)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
