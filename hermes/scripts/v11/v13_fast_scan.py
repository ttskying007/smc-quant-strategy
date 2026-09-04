#!/usr/bin/env python3
"""V13快速扫描: 单次信号检测 + 多过滤器并行应用"""
import json, sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v22 import detect_all_signals_v22, _calc_atr

def calc_atr(daily, L=14):
    n=min(L,len(daily)); ts=[]
    for i in range(max(1,len(daily)-n),len(daily)):
        h,l,pc=daily[i]['h'],daily[i]['l'],daily[i-1]['c']
        ts.append(max(h-l,abs(h-pc),abs(l-pc)))
    return sum(ts)/len(ts) if ts else 1.0

def sim_exit(daily, eidx, ep, sl_price):
    hs=[b['h'] for b in daily]; ls=[b['l'] for b in daily]; cs=[b['c'] for b in daily]
    n=len(daily); sc=sl_price; ext=ep; act=False
    t1=False; t2=False; eb=None; ex=None
    atr=calc_atr(daily[:eidx+1],14); ap=atr/ep if ep>0 else 0.02
    tp1=ep*(1+ap*2.0); tp2=ep*(1+ap*4.0)
    ta=ap*3.0; td=ap*0.8
    for j in range(eidx+1,min(n,eidx+40)):
        if hs[j]>ext: ext=hs[j]
        g=(ext-ep)/ep
        if not act and g>=ta: act=True
        if act: sc=max(sc,ext*(1-td))
        if not t1 and hs[j]>=tp1: t1=True
        if not t2 and hs[j]>=tp2: t2=True
        if ls[j]<=sc: eb=j; ex=max(sc,ls[j]); break
        if j==eidx+30: eb=j; ex=cs[j]; break
    if eb is None: eb=min(eidx+39,n-1); ex=cs[eb]
    p=0
    if t1: p+=0.5*(tp1-ep)/ep
    else: p+=0.5*(cs[eb]-ep)/ep
    if t2: p+=0.3*(tp2-ep)/ep
    else: p+=0.3*(cs[eb]-ep)/ep
    p+=0.2*(ex-ep)/ep
    return p*100

daily_dir = Path('/root/.hermes/kline_cache')
files = sorted(daily_dir.glob('*_daily_300.json'))
print(f"全量扫描: {len(files)}只...")

# 预检测所有信号(一次性)
all_zones = []  # [(symbol, dz_low, dz_high, dz_bar, rally_high, breached, choch_bar, entry_price, entry_bar)]
skipped=0
for fi, fp in enumerate(files):
    fname=fp.name; parts=fname.replace('_daily_300.json','').split('_')
    if len(parts)<2: continue
    symbol='.'.join(parts)
    if (fi+1)%1000==0: print(f"  检测: {fi+1}/{len(files)}")
    try:
        daily=json.loads(fp.read_bytes())
        for b in daily:
            if 't' not in b and 'date' in b: b['t']=str(b['date'])
            for k in ('o','h','l','c','v'): b[k]=float(b[k]) if k in b else 0
    except: skipped+=1; continue
    n=len(daily)
    if n<60: skipped+=1; continue
    cs=[b['c'] for b in daily]; hs=[b['h'] for b in daily]; ls=[b['l'] for b in daily]
    sigs,_,_,_=detect_all_signals_v22(daily); atr=_calc_atr(daily,200)
    choch_bulls=[s for s in sigs if s.type=='CHOCH_Bull']
    
    dzs=[s for s in sigs if s.type=='OB_Bull' and s.confidence>=0.7 and s.idx>=20 and s.idx<n-15]
    for dz in dzs:
        zl=dz.lower; zh=dz.upper; zb=dz.idx
        if zl<=0 or zh<=zl: continue
        rh=max(hs[zb:min(n,zb+20)])
        if rh<zh+atr*0.3: continue  # 无反弹确认
        zone_age=n-1-zb
        if zone_age>200: continue  # 最大200bar
        
        # 击穿检查
        breached=False; breach_bar=-1
        for j in range(zb+5,n):
            if cs[j]<zl*0.98: breached=True; breach_bar=j; break
        
        # CHOCH(最近)
        choch_after=[s for s in choch_bulls if zb<=s.idx<=zb+50]
        ch_bar=choch_after[0].idx if choch_after else -1
        
        # 入场机会
        eb=None; ep=None
        for w in range(1,15):
            e=zb+w
            if e>=n-15: break
            if ls[e]<=zh: eb=e; ep=max(zl,ls[e]); break
        if eb is None: continue
        
        sl_price=zl*(1-(atr/ep if ep>0 else 0.02)*1.2)
        all_zones.append({
            'symbol':symbol,'zl':zl,'zh':zh,'zb':zb,
            'zone_age':zone_age,'breached':breached,'breach_bar':breach_bar,
            'ch_bar':ch_bar,'eb':eb,'ep':ep,'sl':sl_price,
            'atr':atr
        })

print(f"\n预检测完成: {len(all_zones)} zones from {len(files)} stocks (skip {skipped})")

# ═══ 多参数应用 ═══
age_limits=[40,60,80,100,120,200]
choch_required=[True,False]

for age in age_limits:
    for need_ch in choch_required:
        trades=[]
        seen=set()
        for z in all_zones:
            if z['zone_age']>age: continue
            if z['breached']: continue
            if need_ch and z['ch_bar']<0: continue
            key=(z['symbol'],z['zb'])
            if key in seen: continue
            seen.add(key)
            
            # 回测结果
            pnl=0  # placeholder - actual backtest would need daily data
            won=pnl>0
            trades.append({'pnl':pnl,'won':won,'symbol':z['symbol']})
        
        n=len(trades)
        if n==0: print(f"age≤{age:3d} ch={need_ch}: 0 trades"); continue
        won_cnt=sum(1 for t in trades if t['won'])
        wr=won_cnt/n*100 if n else 0
        st=len(set(t['symbol'] for t in trades))
        
        marker=' ← 最优' if (wr>=85 and n>=2000) else ''
        print(f"age≤{age:3d} ch={need_ch}: {n:6d}笔 {st:5d}只 WR≈? (需实测PnL){marker}")

print(f"\n需要实测PnL才能得到准确WR。推荐先测 age≤100 ch=False (去掉CHOCH) 组合")
