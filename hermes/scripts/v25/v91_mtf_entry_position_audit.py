#!/usr/bin/env python3
from __future__ import annotations
import json,math
from pathlib import Path
from collections import defaultdict,Counter
SRC=Path('/root/.hermes/smc_opt_v85_mixed_accumulation_generator/v85_candidates.json')
KD=Path('/root/.hermes/kline_cache'); K60=Path('/root/.hermes/kline_cache_60min')
OUT=Path('/root/.hermes/smc_opt_v91_mtf_entry_position_audit'); OUT.mkdir(parents=True,exist_ok=True)

def F(x,d=0.0):
    try:
        if x in (None,'',[],{}): return d
        v=float(x); return v if math.isfinite(v) else d
    except Exception: return d

def D(x):
    s=''.join(c for c in str(x or '') if c.isdigit()); return s[:8]
def bd(b): return D(b.get('t') or b.get('date'))
def load(p):
    return json.loads(Path(p).read_text()) if Path(p).exists() else []
def sp(sym): return str(sym).replace('.','_')
def kpath(sym,tf='d'):
    return (K60/f'{sp(sym)}_60min_500.json') if tf=='60' else KD/f'{sp(sym)}_daily_750.json'
def idx_by_date(ks,date):
    dd=D(date)
    for i,b in enumerate(ks):
        if bd(b)==dd: return i
    return None
def ma(a,n): return sum(a[-n:])/n if len(a)>=n else None
def state(bars):
    cs=[F(b.get('c')) for b in bars if F(b.get('c'))>0]
    if len(cs)<5: return 'UNKNOWN'
    m5=ma(cs,5); m20=ma(cs,20) or m5; r5=(cs[-1]/cs[-5]-1)*100 if cs[-5] else 0; r20=(cs[-1]/cs[-20]-1)*100 if len(cs)>=20 and cs[-20] else r5
    if cs[-1]>m5 and m5>=m20 and r5>0: return 'BULL_CONTINUATION'
    if r5>0 and r20>-8: return 'RECOVERY'
    if cs[-1]<m5 and r5<0: return 'BEAR_RISK'
    return 'MIXED'
def known_bsl(ks,ei,ep,look=60):
    hs=[]
    for i in range(max(0,ei-look),ei):
        h=F(ks[i].get('h'))
        if h>ep: hs.append((h,i))
    if not hs: return 0,-1
    h,i=min(hs,key=lambda x:(x[0]-ep,ei-x[1])); return h,i
def v86_gate(r):
    risk=F(r.get('risk_pct')) or ((F(r.get('entry_price'))/F(r.get('zone_low'))-1)*100 if F(r.get('zone_low')) else 999)
    return 1.0<F(r.get('v85_zone_width_pct'),999)<=1.6 and 1.0<risk<=1.5 and F(r.get('hold_bars'),999)<=2 and r.get('v83_takeover_type')=='HOLD_ABOVE_POI'
def gate_reason(r):
    rs=[]; risk=F(r.get('risk_pct')) or ((F(r.get('entry_price'))/F(r.get('zone_low'))-1)*100 if F(r.get('zone_low')) else 999)
    if not (1.0<F(r.get('v85_zone_width_pct'),999)<=1.6): rs.append('ZONE_WIDTH')
    if not (1.0<risk<=1.5): rs.append('RISK')
    if not (F(r.get('hold_bars'),999)<=2): rs.append('HOLD_LAG')
    if r.get('v83_takeover_type')!='HOLD_ABOVE_POI': rs.append('NO_HOLD_ABOVE_POI')
    return '+'.join(rs) or 'PASS'
def entry_plans(r,ks,m60):
    zl,zh,ep0=F(r.get('zone_low')),F(r.get('zone_high')),F(r.get('entry_price')); ei=int(F(r.get('entry_idx'),-1)); out=[]
    if ei<1 or ei>=len(ks) or not (zl and zh and ep0): return out
    out.append(('orig_v85_entry',ei,ep0,'daily'))
    for name,px in [('zone_high_limit',zh),('zone_mid_limit',(zl+zh)/2),('zone_low_limit',zl)]:
        fill=None
        for j in range(max(1,int(F(r.get('touch_idx'),ei))),min(len(ks),ei+6)):
            if F(ks[j].get('l'))<=px<=F(ks[j].get('h')): fill=j; break
        if fill and bd(ks[fill])!=bd(ks[max(0,int(F(r.get('event_idx'),fill-1)))]): out.append((name,fill,px,'daily'))
    # 60min confirmation only when cache covers entry date; no historical fill if absent
    if m60:
        ed=bd(ks[ei]); win=[b for b in m60 if bd(b) in {ed, bd(ks[min(len(ks)-1,ei+1)])}]
        touch=False; low=0
        for b in win:
            lo,hi,cl=F(b.get('l')),F(b.get('h')),F(b.get('c'))
            if lo<=zh and hi>=zl: touch=True; low=lo if not low else min(low,lo)
            if touch and cl>zh:
                out.append(('m60_reclaim_close',ei,cl,'m60')); break
        if touch:
            for b in win:
                lo,cl=F(b.get('l')),F(b.get('c'))
                if low and lo>low and cl>zh: out.append(('m60_higher_low_reclaim',ei,cl,'m60')); break
    return out
def sim(ks,start,ep,zl,zh,mode='micro',maxhold=40):
    if start+1>=len(ks): return None
    # T+1: exit scan starts next daily bar
    sl=max(zl*0.995, ep*0.975); risk=ep-sl
    if not(ep>sl>0) or risk/ep<0.003: return None
    bsl,_=known_bsl(ks,start,ep); rr1=1.5
    if bsl>ep: rr1=max(1.2,min(3.0,(bsl-ep)/risk))
    if mode=='micro': tps=[ep+0.8*risk,ep+1.5*risk,ep+3*risk]
    elif mode=='liq': tps=[max(ep+risk,bsl),max(ep+2*risk,bsl),max(ep+3*risk,bsl)]
    else: tps=[ep+risk,ep+1.5*risk,ep+3*risk]
    rem=1; pnl=0; legs=[]; hit=set(); trail=None; mfe=-999; mae=999; exi=start; reason='TIME_STOP'; exp=ep
    for i in range(start+1,min(len(ks),start+maxhold+1)):
        b=ks[i]; hi,lo,cl=F(b.get('h')),F(b.get('l')),F(b.get('c')); mfe=max(mfe,(hi/ep-1)*100); mae=min(mae,(lo/ep-1)*100)
        if lo<=sl and not legs: exp=sl; reason='SL_HIT'; exi=i; pnl=(sl/ep-1)*100; rem=0; break
        for nm,tp,w in [('TP1',tps[0],.35),('TP2',tps[1],.35),('TP3',tps[2],.30)]:
            if nm not in hit and hi>=tp and rem>0:
                take=min(w,rem); pnl+=take*(tp/ep-1)*100; rem-=take; hit.add(nm); legs.append(nm)
                if nm in ('TP2','TP3'): trail=max(trail or sl, ep+risk)
        if rem<=0: reason='TP3_HIT'; exp=tps[2]; exi=i; break
        if trail and lo<=trail: pnl+=rem*(trail/ep-1)*100; reason='RUNNER_TRAIL'; exp=trail; exi=i; rem=0; break
        exp=cl; exi=i
    if rem>0: pnl+=rem*(exp/ep-1)*100
    return dict(pnl_pct=round(pnl,4),exit_reason=reason,exit_date=bd(ks[exi]),exit_idx=exi,sl=round(sl,4),tp1=round(tps[0],4),tp2=round(tps[1],4),tp3=round(tps[2],4),rr=round((tps[1]-ep)/risk,4),mfe_r=round((mfe/100*ep)/risk,4),mae_r=round((mae/100*ep)/risk,4),legs=legs)
def met(rows):
    n=len(rows)
    if not n: return dict(n=0,wr=0,avg=0,sl=0,tp=0,rr=0,mfe=0)
    return dict(n=n,wr=round(sum(F(r.get('pnl_pct'))>0 for r in rows)/n*100,2),avg=round(sum(F(r.get('pnl_pct')) for r in rows)/n,4),sl=round(sum(r.get('exit_reason')=='SL_HIT' for r in rows)/n*100,2),tp=round(sum('TP' in str(r.get('exit_reason')) or r.get('exit_reason')=='RUNNER_TRAIL' for r in rows)/n*100,2),rr=round(sum(F(r.get('rr')) for r in rows)/n,3),mfe=round(sum(F(r.get('mfe_r')) for r in rows)/n,3))
def bucket(rows,key,minn=1):
    g=defaultdict(list)
    for r in rows: g[str(key(r))].append(r)
    return {k:met(v) for k,v in sorted(g.items(),key=lambda kv:-len(kv[1])) if len(v)>=minn}

def main():
    src=load(SRC); dc={}; mc={}; rows=[]; cov=Counter(); rej=Counter()
    for n,r in enumerate(src):
        sym=r.get('symbol'); ks=dc.get(sym)
        if ks is None: ks=dc[sym]=load(kpath(sym,'d'))
        if not ks: continue
        m60=mc.get(sym)
        if m60 is None: m60=mc[sym]=load(kpath(sym,'60'))
        ei=int(F(r.get('entry_idx'),-1)); zl,zh=F(r.get('zone_low')),F(r.get('zone_high'))
        if ei<1 or ei>=len(ks) or not(zl and zh): continue
        gr=gate_reason(r); rej[gr]+=1
        pre=ks[max(0,ei-80):ei+1]
        dstate=state(pre); y=D(r.get('entry_date'))[:4]
        for en,ej,ep,srcmode in entry_plans(r,ks,m60):
            cov[srcmode]+=1
            for tp_mode in ['micro','liq']:
                s=sim(ks,ej,F(ep),zl,zh,tp_mode)
                if not s: continue
                rec=dict(symbol=sym,year=y,gate=gr,gate_pass=(gr=='PASS'),market_state=r.get('market_state'),v85_path=r.get('v85_path'),substate=r.get('v85_market_substate'),entry_mode=en,entry_src=srcmode,tp_mode=tp_mode,daily_state=dstate,entry_date=bd(ks[ej]),orig_entry_date=r.get('entry_date'),entry_price=round(F(ep),4),zone_pos=round((F(ep)-zl)/(zh-zl),4) if zh>zl else 9,zone_width=F(r.get('v85_zone_width_pct')),risk_signal=F(r.get('risk_pct')),hold_bars=F(r.get('hold_bars')),t1_violation=(bd(ks[ej])==s['exit_date']))
                rec.update(s); rows.append(rec)
    pass_rows=[r for r in rows if r['gate_pass']]
    filtered=[r for r in rows if not r['gate_pass']]
    combos=bucket(rows,lambda r:f"{r['gate']}|{r['entry_mode']}|{r['tp_mode']}",50)
    prod=[]
    for k,m in combos.items():
        rs=[r for r in rows if f"{r['gate']}|{r['entry_mode']}|{r['tp_mode']}"==k]
        byy=bucket(rs,lambda r:r['year'],1); ok=m['n']>=500 and m['wr']>=88 and m['sl']<=12 and all(byy.get(y,{}).get('n',0)>=30 for y in ['2023','2024','2025','2026'])
        if ok: prod.append(dict(combo=k,**m,year=byy))
    prod=sorted(prod,key=lambda x:(x['wr'],-x['sl'],x['avg']),reverse=True)[:30]
    loss=[r for r in rows if r['exit_reason']=='SL_HIT']
    report=dict(engine='V91_MTF_ENTRY_POSITION_AUDIT',source=str(SRC),source_rows=len(src),matrix_rows=len(rows),coverage=dict(cov),reject_source=dict(rej),overall=met(rows),gate_pass=met(pass_rows),filtered=met(filtered),by_entry_mode=bucket(rows,lambda r:r['entry_mode'],50),by_tp_mode=bucket(rows,lambda r:r['tp_mode'],50),by_gate=bucket(rows,lambda r:r['gate'],50),by_market=bucket(rows,lambda r:r['market_state'],50),by_daily_state=bucket(rows,lambda r:r['daily_state'],50),best_production_like=prod,sl_by_gate_entry=bucket(loss,lambda r:f"{r['gate']}|{r['entry_mode']}|{r['market_state']}",10),t1_violations=sum(r['t1_violation'] for r in rows))
    (OUT/'v91_mtf_entry_position_rows.json').write_text(json.dumps(rows,ensure_ascii=False))
    (OUT/'v91_mtf_entry_position_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2)[:12000])
if __name__=='__main__': main()
