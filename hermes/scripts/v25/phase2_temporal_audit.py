#!/usr/bin/env python3
import json, sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime
sys.path[:0]=['/root/.hermes/scripts','/root/.hermes/scripts/v11']
from signals_v22 import detect_all_signals_v22
K=Path('/root/.hermes/kline_cache')
OUT=Path('/root/.hermes/smc_opt_v25/phase2_temporal_audit.json')
MAX_HOLD=60
N=int(sys.argv[1]) if len(sys.argv)>1 else 0

def f(x):
    try:return float(x or 0)
    except:return 0.0

def d(b):return str(b.get('t') or b.get('date') or '')[:8]
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

def sim(ks,eb,ep,sl,tp):
    if not(ep>sl>0 and tp>ep): return None
    for j in range(eb+1,min(len(ks),eb+MAX_HOLD+1)):
        if f(ks[j].get('l'))<=sl: return ('SL', (sl/ep-1)*100, j-eb)
        if f(ks[j].get('h'))>=tp: return ('TP', (tp/ep-1)*100, j-eb)
    if eb+MAX_HOLD<len(ks):
        px=f(ks[eb+MAX_HOLD].get('c')); return ('TIME',(px/ep-1)*100,MAX_HOLD)
    return None

def rec(symbol,ks,z,c,eb,mode):
    zl,zh=z['low'],z['high']; ep=f(ks[eb].get('c'))
    a=atr(ks,z['bar']); sl=min(zl-a*.5,zl*.995)
    risk=abs(zl-sl)/zl*100 if zl else 0
    if risk<.5: risk=1.5
    tp=zh*(1+risk*1.5/100)
    r=sim(ks,eb,ep,sl,tp)
    if not r: return None
    lo=f(ks[eb].get('l'))
    return {'symbol':symbol,'mode':mode,'zone_type':z['type'],'conf_type':c['type'],
      'zone_bar':z['bar'],'conf_bar':c['bar'],'entry_bar':eb,
      'entry_before_confirm':eb<=c['bar'],'entry_date':d(ks[eb]),'conf_date':d(ks[c['bar']]),
      'in_zone':ep<=zh and ep>=zl,'sl_pct':abs(ep-sl)/ep*100,
      'retrace_pct':max(0,min(100,(zh-lo)/max(zh-zl,1e-9)*100)),
      'pnl_pct':r[1],'exit':r[0],'hold':r[2]}

def replay(kf):
    sym=kf.stem.replace('_daily_750','').replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
    try: ks=json.loads(kf.read_text())
    except: return []
    if len(ks)<150: return []
    for b in ks:
        for k in ('o','h','l','c','v'):
            if k in b:b[k]=f(b[k])
    try:sigs,_,_,_=detect_all_signals_v22(ks)
    except Exception:return []
    confs=[{'type':stype(s),'bar':sbar(s)} for s in sigs if stype(s) in ('BOS_Bull','CHOCH_Bull')]
    zones=[]
    for s in sigs:
        typ=stype(s)
        if typ not in ('OB_Bull','FVG_Bull'): continue
        sb=sbar(s); zl=slow(s); zh=shigh(s)
        if sb>=30 and sb<len(ks)-65 and zh>zl>0: zones.append({'type':typ,'bar':sb,'low':zl,'high':zh})
    out=[]; seen=set()
    for z in zones:
        cs=[c for c in confs if z['bar']<c['bar']<=z['bar']+30]
        if not cs: continue
        c=cs[0]
        # old quality replay: can enter before confirmation
        for eb in range(z['bar']+3,min(z['bar']+31,len(ks)-65)):
            if f(ks[eb].get('l'))>z['high']: continue
            if f(ks[eb].get('l'))<z['low']*.95: break
            if f(ks[eb].get('h'))>=z['low']:
                t=rec(sym,ks,z,c,eb,'old_quality_temporal_leak');
                if t: out.append(t)
                break
        # strict replay: entry only after structure confirmation
        for eb in range(c['bar']+1,min(c['bar']+31,len(ks)-65)):
            if f(ks[eb].get('l'))>z['high']: continue
            if f(ks[eb].get('l'))<z['low']*.95: break
            if f(ks[eb].get('h'))>=z['low']:
                t=rec(sym,ks,z,c,eb,'strict_after_confirm');
                if t: out.append(t)
                break
    return out

def met(ts):
    if not ts:return {'n':0}
    return {'n':len(ts),'wr':round(sum(t['pnl_pct']>0 for t in ts)/len(ts)*100,2),
      'avg':round(sum(t['pnl_pct'] for t in ts)/len(ts),4),
      'sl_rate':round(sum(t['exit']=='SL' for t in ts)/len(ts)*100,2),
      'pre_conf_rate':round(sum(t['entry_before_confirm'] for t in ts)/len(ts)*100,2)}

def main():
    fs=sorted(K.glob('*_daily_750.json'))
    if N: fs=fs[:N]
    all=[]
    print('audit',len(fs),datetime.now().strftime('%H:%M:%S'),flush=True)
    for i,kf in enumerate(fs,1):
        all.extend(replay(kf))
        if i%1000==0: print(i,len(all),flush=True)
    prof={}
    for mode in ['old_quality_temporal_leak','strict_after_confirm']:
        g=[t for t in all if t['mode']==mode]
        prof[mode]=met(g)
        prof[mode+'_gate_inzone_sl1_retr60']=met([t for t in g if t['in_zone'] and t['sl_pct']>=1 and t['retrace_pct']<60])
        prof[mode+'_FVG_gate']=met([t for t in g if t['zone_type']=='FVG_Bull' and t['in_zone'] and t['sl_pct']>=1 and t['retrace_pct']<60])
        prof[mode+'_OB_gate']=met([t for t in g if t['zone_type']=='OB_Bull' and t['in_zone'] and t['sl_pct']>=1 and t['retrace_pct']<60])
    OUT.write_text(json.dumps({'generated_at':datetime.now().isoformat(timespec='seconds'),'n_stocks':len(fs),'profiles':prof,'samples':[t for t in all if t['entry_before_confirm']][:5]},ensure_ascii=False,indent=2))
    print(json.dumps(prof,ensure_ascii=False,indent=2))
    print('saved',OUT)
if __name__=='__main__': main()
