#!/usr/bin/env python3
import json, sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime
sys.path[:0]=['/root/.hermes/scripts','/root/.hermes/scripts/v11']
from signals_v22 import detect_all_signals_v22
K=Path('/root/.hermes/kline_cache')
OUT=Path('/root/.hermes/smc_opt_v25/phase2_strict_exit_audit.json')
MAX_HOLD=60
N=int(sys.argv[1]) if len(sys.argv)>1 else 0

def f(x):
    try:return float(x or 0)
    except:return 0.0

def sbar(s):return int(getattr(s,'idx',getattr(s,'bar',0)) or 0)
def stype(s):return getattr(s,'type','')
def slow(s):
    m=getattr(s,'metadata',{}) or getattr(s,'meta',{}) or {}
    return f(m.get('ob_low') or getattr(s,'lower',0) or getattr(s,'price',0))
def shigh(s):
    m=getattr(s,'metadata',{}) or getattr(s,'meta',{}) or {}
    return f(m.get('ob_high') or getattr(s,'upper',0) or getattr(s,'price',0))
def atr(ks,idx,n=14):
    vals=[]
    for i in range(max(1,idx-n+1),idx+1):
        h,l,pc=f(ks[i].get('h')),f(ks[i].get('l')),f(ks[i-1].get('c'))
        vals.append(max(h-l,abs(h-pc),abs(l-pc)))
    return sum(vals)/len(vals) if vals else 0

def state(ks,idx):
    ep=f(ks[idx].get('c')); a=atr(ks,idx); ap=a/ep*100 if ep else 0
    if ap>5:return 'HIGH_VOL'
    if ap<1.5:return 'LOW_VOL'
    return 'NORMAL'

def sim_modes(ks,eb,ep,sl,tp1):
    if not(ep>sl>0 and tp1>ep): return []
    out=[]; hit1=False; stop=sl; tp1_bar=None
    # fixed TP/SL
    fixed=None
    for j in range(eb+1,min(len(ks),eb+MAX_HOLD+1)):
        lo,hi=f(ks[j].get('l')),f(ks[j].get('h'))
        if lo<=sl: fixed=('fixed_SL',(sl/ep-1)*100,j-eb); break
        if hi>=tp1: fixed=('fixed_TP',(tp1/ep-1)*100,j-eb); break
    if fixed: out.append(('fixed',)+fixed)
    # V66-like: partial at TP1 then after 2R lock 4R/trail target approximation
    r=ep-sl; target=ep+r*4.0
    for j in range(eb+1,min(len(ks),eb+MAX_HOLD+1)):
        lo,hi,cl=f(ks[j].get('l')),f(ks[j].get('h')),f(ks[j].get('c'))
        if not hit1:
            if lo<=sl: out.append(('v66_like','SL',(sl/ep-1)*100,j-eb)); break
            if hi>=tp1: hit1=True; tp1_bar=j; stop=max(stop,ep)  # BE after TP1
        else:
            if hi>=target:
                pnl=(0.4*((tp1/ep-1)*100)+0.6*((target/ep-1)*100)); out.append(('v66_like','STRUCT_CONFIRM_BREAK',pnl,j-eb)); break
            if lo<=stop:
                pnl=(0.4*((tp1/ep-1)*100)+0.6*((stop/ep-1)*100)); out.append(('v66_like','BE_STOP',pnl,j-eb)); break
    else:
        if eb+MAX_HOLD<len(ks):
            px=f(ks[eb+MAX_HOLD].get('c'))
            if hit1: pnl=0.4*((tp1/ep-1)*100)+0.6*((px/ep-1)*100)
            else: pnl=(px/ep-1)*100
            out.append(('v66_like','TIME',pnl,MAX_HOLD))
    return out

def replay(kf):
    sym=kf.stem.replace('_daily_750','').replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
    try:ks=json.loads(kf.read_text())
    except:return []
    if len(ks)<150:return []
    for b in ks:
        for k in ('o','h','l','c','v'):
            if k in b:b[k]=f(b[k])
    try:sigs,_,_,_=detect_all_signals_v22(ks)
    except:return []
    confs=[{'type':stype(s),'bar':sbar(s)} for s in sigs if stype(s) in ('BOS_Bull','CHOCH_Bull')]
    zones=[]
    for s in sigs:
        if stype(s) not in ('OB_Bull','FVG_Bull'):continue
        sb=sbar(s); zl=slow(s); zh=shigh(s)
        if sb>=30 and sb<len(ks)-65 and zh>zl>0:zones.append({'type':stype(s),'bar':sb,'low':zl,'high':zh})
    out=[]
    for z in zones:
        cs=[c for c in confs if z['bar']<c['bar']<=z['bar']+30]
        if not cs:continue
        c=cs[0]
        for eb in range(c['bar']+1,min(c['bar']+31,len(ks)-65)):
            lo,hi,ep=f(ks[eb].get('l')),f(ks[eb].get('h')),f(ks[eb].get('c'))
            if lo>z['high']:continue
            if lo<z['low']*.95:break
            if hi>=z['low']:
                a=atr(ks,eb); sl=min(z['low']-a*.5,z['low']*.995)
                risk=abs(ep-sl)/ep*100 if ep else 999
                retr=max(0,min(100,(z['high']-lo)/max(z['high']-z['low'],1e-9)*100))
                if not(ep<=z['high'] and ep>=z['low'] and risk>=1 and retr<60):break
                tp1=ep+(ep-sl)*1.5
                for mode,ex,pnl,hold in sim_modes(ks,eb,ep,sl,tp1):
                    out.append({'symbol':sym,'mode':mode,'zone_type':z['type'],'conf_type':c['type'],'market_state':state(ks,eb),'pnl_pct':pnl,'exit':ex,'hold':hold})
                break
    return out

def met(ts):
    if not ts:return {'n':0}
    return {'n':len(ts),'wr':round(sum(t['pnl_pct']>0 for t in ts)/len(ts)*100,2),'avg':round(sum(t['pnl_pct'] for t in ts)/len(ts),4),'sl_rate':round(sum('SL' in t['exit'] for t in ts)/len(ts)*100,2)}

def main():
    fs=sorted(K.glob('*_daily_750.json'))
    if N:fs=fs[:N]
    all=[]
    print('strict exit audit',len(fs),flush=True)
    for i,kf in enumerate(fs,1):
        all.extend(replay(kf))
        if i%1000==0:print(i,len(all),flush=True)
    prof={}
    for m in sorted(set(t['mode'] for t in all)):
        g=[t for t in all if t['mode']==m]; prof[m]=met(g)
        for z in ['FVG_Bull','OB_Bull']:
            prof[m+'_'+z]=met([t for t in g if t['zone_type']==z])
    OUT.write_text(json.dumps({'generated_at':datetime.now().isoformat(timespec='seconds'),'n_stocks':len(fs),'profiles':prof},ensure_ascii=False,indent=2))
    print(json.dumps(prof,ensure_ascii=False,indent=2));print('saved',OUT)
if __name__=='__main__':main()
