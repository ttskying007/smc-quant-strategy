#!/usr/bin/env python3
"""V14快速版: 每只股票仅检测1次信号, 然后应用40组过滤"""
import json, sys, math
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v22 import detect_all_signals_v22, _calc_atr

DAILY_DIR = Path('/root/.hermes/kline_cache')

def calc_atr(daily, L=14):
    n=min(L,len(daily)); ts=[]
    for i in range(max(1,len(daily)-n),len(daily)):
        h,l,pc=daily[i]['h'],daily[i]['l'],daily[i-1]['c']
        ts.append(max(h-l,abs(h-pc),abs(l-pc)))
    return sum(ts)/len(ts) if ts else 1.0

def sim_exit(daily, eidx, ep, sl_price, tp_price=None, max_bars=30):
    hs=[b['h'] for b in daily]; ls=[b['l'] for b in daily]; cs=[b['c'] for b in daily]
    n=len(daily); sc=sl_price; ext=ep; act=False
    atr=calc_atr(daily[:eidx+1],14); ap=atr/ep if ep>0 else 0.02
    if tp_price is None: tp_price=ep*(1+ap*2.0)
    tp2=ep*(1+ap*4.0); ta=ap*1.5; td=ap*0.6
    t1=False; t2=False; eb=None; ex=None; er='timeout'
    for j in range(eidx+1, min(n, eidx+max_bars)):
        if hs[j]>ext: ext=hs[j]
        g=(ext-ep)/ep
        if not act and g>=ta: act=True
        if act: sc=max(sc, ext*(1-td))
        if not t1 and hs[j]>=tp_price: t1=True
        if not t2 and hs[j]>=tp2: t2=True
        if ls[j]<=sc: eb=j; ex=max(sc,ls[j]); er='SL_hit'; break
        if j==eidx+max_bars-5: eb=j; ex=cs[j]; er='time_stop'; break
    if eb is None: eb=min(eidx+max_bars-1,n-1); ex=cs[eb]; er='timeout'
    p=0
    if t1: p+=0.5*(tp_price-ep)/ep
    else: p+=0.5*(cs[eb]-ep)/ep
    if t2: p+=0.3*(tp2-ep)/ep
    else: p+=0.3*(cs[eb]-ep)/ep
    p+=0.2*(ex-ep)/ep
    return p*100

# ═══ 阶段1: 预检测所有股票信号 ═══
files = sorted(DAILY_DIR.glob('*_daily_300.json'))
print(f"Phase 1: 信号检测 {len(files)} stocks...")
stock_data = []  # [{symbol, daily, closes, highs, lows, dates, sigs, atr, swings}]
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
    except: continue
    n=len(daily)
    if n<60: continue
    cs=[b['c'] for b in daily]; hs=[b['h'] for b in daily]; ls=[b['l'] for b in daily]
    ds=[str(b.get('t',''))[:10] for b in daily]
    sigs,_,swings,_=detect_all_signals_v22(daily)
    atr=_calc_atr(daily,200)
    # 预索引信号
    sig_by_type=defaultdict(list)
    for s in sigs: sig_by_type[s.type].append(s)
    stock_data.append({'symbol':symbol,'daily':daily,'cs':cs,'hs':hs,'ls':ls,'ds':ds,
                       'sigs':sigs,'sig_by_type':sig_by_type,'atr':atr,'swings':swings})

print(f"  {len(stock_data)} stocks ready")

# ═══ 阶段2: 应用40组过滤 ═══
combos = [
    ('OB_only',    ['OB_Bull'],                    []),
    ('OB+Sweep',   ['OB_Bull'],                    ['Sweep_SSL','Sweep_BSL']),
    ('OB+CHOCH',   ['OB_Bull'],                    ['CHOCH_Bull']),
    ('OB+Breaker', ['OB_Bull','BreakerBlock_Bull'], []),
    ('OB+Pinbar',  ['OB_Bull'],                    ['Pinbar_Bull']),
]
sl_modes = [
    ('sl_fixed',  'fixed'),   # cost_line*(1-atr_pct*1.2)
    ('sl_capped', 'capped'),  # max(cost_line_sl, entry*0.92)
]
tp_modes = [
    ('tp_atr',   'atr'),
    ('tp_swing', 'swing'),
]
entry_modes = [
    ('zone_retrace', 'retrace'),
    ('zone_bottom',  'bottom'),
]

results = {}
for combo_name, valid_types, require_nearby in combos:
    for sl_name, sl_mode in sl_modes:
        for tp_name, tp_mode in tp_modes:
            for entry_name, entry_mode in entry_modes:
                key = f"{combo_name}|{sl_name}|{tp_name}|{entry_name}"
                all_trades = []
                
                for sd in stock_data:
                    daily=sd['daily']; cs=sd['cs']; hs=sd['hs']; ls=sd['ls']; ds=sd['ds']
                    sig_by_type=sd['sig_by_type']; atr=sd['atr']; swings=sd['swings']
                    n=len(daily)
                    
                    dzs=[s for s in sd['sigs'] if any(s.type==vt for vt in valid_types) 
                         and s.confidence>=0.7 and s.idx>=20 and s.idx<n-15]
                    used=set()
                    
                    for dz in dzs:
                        zl=dz.lower; zh=dz.upper; zb=dz.idx
                        if zl<=0 or zh<=zl or zb in used: continue
                        rh=max(hs[zb:min(n,zb+20)])
                        if rh<zh+atr*0.3: continue
                        if n-1-zb>120: continue
                        br=False
                        for j in range(zb+5,n):
                            if cs[j]<zl*0.98: br=True; break
                        if br: continue
                        
                        if require_nearby:
                            has_nearby=False
                            for rt in require_nearby:
                                for ns in sig_by_type.get(rt,[]):
                                    if abs(ns.idx-zb)<=20: has_nearby=True; break
                                if has_nearby: break
                            if not has_nearby: continue
                        
                        eb=None; ep=None
                        if entry_mode=='retrace':
                            for w in range(1,15):
                                e=zb+w
                                if e>=n-15: break
                                if ls[e]<=zh: eb=e; ep=max(zl,ls[e]); break
                        else:  # bottom
                            for w in range(1,20):
                                e=zb+w
                                if e>=n-15: break
                                if ls[e]<=zl*1.02 and cs[e]>=zl: eb=e; ep=max(zl,ls[e]); break
                        
                        if eb is None: continue
                        used.add(zb)
                        
                        ap=atr/ep if ep>0 else 0.02
                        fixed_sl=zl*(1-ap*1.2)
                        if sl_mode=='capped':
                            sl=min(fixed_sl, ep*0.92)
                        else:
                            sl=fixed_sl
                        sl_pct=(ep-sl)/ep*100 if ep>0 else 5
                        
                        tp_price=None
                        if tp_mode=='swing':
                            sh_list=[sw for sw in swings if sw.type=='H' and sw.bar_idx<zb]
                            if len(sh_list)>=2:
                                prev_high=max(sw.price for sw in sh_list[-3:])
                                if prev_high>ep*1.02: tp_price=prev_high
                        
                        pnl=sim_exit(daily, eb, ep, sl, tp_price)
                        rr=pnl/sl_pct if sl_pct>0 else 99
                        
                        all_trades.append({
                            'pnl_pct':round(pnl,2),'won':pnl>0,
                            'rr':round(rr,2),'sl_pct':round(sl_pct,2),
                            'symbol':sd['symbol']
                        })
                
                n_t=len(all_trades); won=sum(1 for t in all_trades if t['won'])
                wr=won/n_t*100 if n_t else 0
                ap=sum(t['pnl_pct'] for t in all_trades)/n_t if n_t else 0
                rr=sum(t['rr'] for t in all_trades)/n_t if n_t else 0
                st=len(set(t['symbol'] for t in all_trades))
                results[key]={'trades':n_t,'stocks':st,'wr':wr,'avg_pnl':ap,'rr':rr}

# ═══ 输出 ═══
print(f"\n{'信号组合':<12s} {'SL':<10s} {'TP':<10s} {'入场':<12s} {'交易':>6s} {'股票':>5s} {'WR':>6s} {'均盈':>7s} {'RR':>6s}")
print("-"*90)
best_key=None; best_score=0
for combo_name, _, _ in combos:
    for sl_name, _ in sl_modes:
        for tp_name, _ in tp_modes:
            for entry_name, _ in entry_modes:
                key=f"{combo_name}|{sl_name}|{tp_name}|{entry_name}"
                r=results.get(key,{})
                n_t=r.get('trades',0); st=r.get('stocks',0)
                wr=r.get('wr',0); ap=r.get('avg_pnl',0); rr=r.get('rr',0)
                # 综合: WR×RR×log(交易量) 最大
                score=wr*rr*math.log(max(n_t,10))
                marker='⭐⭐⭐' if score>best_score*0.95 else ('⭐⭐' if score>best_score*0.85 else '')
                if score>best_score: best_score=score; best_key=key
                print(f"{combo_name:<12s} {sl_name:<10s} {tp_name:<10s} {entry_name:<12s} {n_t:6d} {st:5d} {wr:5.1f}% {ap:+6.2f}% {rr:5.2f}x {marker}")

print(f"\nV13基线: age≤120 无CHOCH  1399笔 1083只 97.3% +11.31% 1.43x")
print(f"V14最优: {best_key}  score={best_score:.0f}")

Path('/root/.hermes/smc_opt_v14/v14_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
