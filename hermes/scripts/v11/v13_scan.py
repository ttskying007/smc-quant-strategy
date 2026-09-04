#!/usr/bin/env python3
"""V13多参数扫描: zone年龄+CHOCH要求 对WR/交易量的影响"""
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

def calc_sltp(daily, eidx, ep, cl):
    atr=calc_atr(daily[:eidx+1],14); ap=atr/ep if ep>0 else 0.02
    sl=cl*(1-ap*1.2); slp=(ep-sl)/ep*100
    tp1=ep*(1+ap*2.0); tp2=ep*(1+ap*4.0)
    return {'sl':round(sl,3),'sl_pct':round(slp,2),'tp1':round(tp1,3),'tp2':round(tp2,3),
            'tp_pct':round(ap*200,1),'trail_act':ap*3.0,'trail_dist':ap*0.8}

def sim_exit(daily, eidx, ep, sltp):
    hs=[b['h'] for b in daily]; ls=[b['l'] for b in daily]; cs=[b['c'] for b in daily]
    n=len(daily); sl=sltp['sl']; tp1=sltp['tp1']; tp2=sltp['tp2']
    ta=sltp['trail_act']; td=sltp['trail_dist']
    ext=ep; sc=sl; act=False; t1=False; t2=False; eb=None; ex=None; er='timeout'
    for j in range(eidx+1,min(n,eidx+40)):
        if hs[j]>ext: ext=hs[j]
        g=(ext-ep)/ep
        if not act and g>=ta: act=True
        if act: sc=max(sc,ext*(1-td))
        if not t1 and hs[j]>=tp1: t1=True
        if not t2 and hs[j]>=tp2: t2=True
        if ls[j]<=sc: eb=j; ex=max(sc,ls[j]); er='SL_hit'; break
        if j==eidx+30: eb=j; ex=cs[j]; er='time_stop'; break
    if eb is None: eb=min(eidx+39,n-1); ex=cs[eb]; er='timeout'
    p=0
    if t1: p+=0.5*(tp1-ep)/ep
    else: p+=0.5*(cs[eb]-ep)/ep
    if t2: p+=0.3*(tp2-ep)/ep
    else: p+=0.3*(cs[eb]-ep)/ep
    p+=0.2*(ex-ep)/ep
    return {'pnl_pct':round(p*100,2),'won':p*100>0,'hold_bars':eb-eidx,
            'exit_price':round(ex,3),'exit_bar':eb,'exit_reason':er,'tp1_hit':t1,'tp2_hit':t2}

def scan_params(daily_files, age_limits, require_choch):
    """扫描不同zone年龄限制+CHOCH要求的回测结果"""
    results = {}
    for age_limit in age_limits:
        for need_ch in require_choch:
            key = f"age{age_limit}_ch{need_ch}"
            all_trades = []
            for fp in daily_files:
                fname = fp.name; parts = fname.replace('_daily_300.json','').split('_')
                if len(parts) < 2: continue
                symbol = '.'.join(parts)
                try:
                    daily = json.loads(fp.read_bytes())
                    for b in daily:
                        if 't' not in b and 'date' in b: b['t']=str(b['date'])
                        for k in ('o','h','l','c','v'): b[k]=float(b[k]) if k in b else 0
                except: continue
                
                n=len(daily)
                if n<60: continue
                cs=[b['c'] for b in daily]; hs=[b['h'] for b in daily]; ls=[b['l'] for b in daily]
                ds=[str(b.get('t',''))[:10] for b in daily]
                sigs,_,_,_=detect_all_signals_v22(daily); atr=_calc_atr(daily,200)
                
                dzs=[s for s in sigs if s.type=='OB_Bull' and s.confidence>=0.7 and s.idx>=20 and s.idx<n-15]
                used=set()
                
                for dz in dzs:
                    zl=dz.lower; zh=dz.upper; zb=dz.idx
                    if zl<=0 or zh<=zl or zb in used: continue
                    rh=max(hs[zb:min(n,zb+20)])
                    if rh<zh+atr*0.3: continue
                    if n-1-zb>age_limit: continue
                    # 击穿检查
                    br=False
                    for j in range(zb+5,n):
                        if cs[j]<zl*0.98: br=True; break
                    if br: continue
                    # CHOCH检查(可选)
                    if need_ch:
                        ch=[s for s in sigs if s.type=='CHOCH_Bull' and zb<=s.idx<=zb+50]
                        if not ch: continue
                    # 入场
                    eb=None; ep=None
                    for w in range(1,15):
                        e=zb+w
                        if e>=n-15: break
                        if ls[e]<=zh:
                            eb=e; ep=max(zl,ls[e]); break
                    if eb is None: continue
                    used.add(zb)
                    sltp=calc_sltp(daily,eb,ep,zl)
                    r=sim_exit(daily,eb,ep,sltp)
                    r['exit_date']=ds[r['exit_bar']] if r['exit_bar']<len(ds) else ''
                    all_trades.append({'symbol':symbol,'entry_date':ds[eb] if eb<len(ds) else '',
                        'entry_idx':eb,'entry_price':round(ep,3),'cost_line':round(zl,3),
                        'zone_bar':zb,'zone_age':eb-zb,'sl_pct':sltp['sl_pct'],
                        'pnl_pct':r['pnl_pct'],'won':r['won'],'rr':round(r['pnl_pct']/sltp['sl_pct'],2) if sltp['sl_pct']>0 else 99,
                        'hold_bars':r['hold_bars'],'exit_reason':r['exit_reason']})
            
            n=len(all_trades); won=sum(1 for t in all_trades if t['won'])
            wr=won/n*100 if n else 0; ap=sum(t['pnl_pct'] for t in all_trades)/n if n else 0
            rr_avg=sum(t['rr'] for t in all_trades)/n if n else 0
            st=len(set(t['symbol'] for t in all_trades))
            results[key] = {'trades':n,'stocks':st,'wr':wr,'avg_pnl':ap,'rr':rr_avg}
    return results

# ═══ 运行扫描 ═══
daily_dir = Path('/root/.hermes/kline_cache')
files = sorted(daily_dir.glob('*_daily_300.json'))  # 全量4905只

print("多参数扫描: zone年龄 × CHOCH要求")
print("="*60)
age_limits = [40, 60, 80, 100, 120, 200]
require_choch = [True, False]

results = scan_params(files, age_limits, require_choch)

print(f"{'配置':<20s} {'交易':>6s} {'股票':>5s} {'WR':>6s} {'均盈':>7s} {'RR':>6s}")
print("-"*55)
for age in age_limits:
    for ch in [False, True]:
        key = f"age{age}_ch{ch}"
        r = results.get(key, {})
        n = r.get('trades',0); st = r.get('stocks',0)
        wr = r.get('wr',0); ap = r.get('avg_pnl',0); rr = r.get('rr',0)
        ch_label = '需CHOCH' if ch else '无CHOCH'
        marker = ' ← 最优平衡?' if (wr>=90 and n>=3000) else ''
        print(f"age≤{age:3d} {ch_label:6s}: {n:6d} {st:5d} {wr:5.1f}% {ap:+6.2f}% {rr:5.2f}x{marker}")
