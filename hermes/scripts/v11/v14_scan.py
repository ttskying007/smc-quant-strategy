#!/usr/bin/env python3
"""
V14: 全信号组合 + 入场精度优化 + SL上限控制 + 多周期
对比V13基线(OB_Bull alone, age≤120, 1399笔/97.3%/+11.31%/1.43x)

测试矩阵:
  信号组合: OB alone / OB+Sweep / OB+CHOCH / OB+Breaker / OB+Pinbar
  入场类型: zone_retrace(当前) / zone_bottom / pinbar_confirm
  SL: fixed_mult(当前) / capped(上限8%) / structural(前摆动点)
  TP: fixed_ATR(当前) / structural_target(前高/前低)
"""
import json, sys, math
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v22 import detect_all_signals_v22, _calc_atr

DAILY_DIR = Path('/root/.hermes/kline_cache')
OUT_DIR = Path('/root/.hermes/smc_opt_v14')
OUT_DIR.mkdir(exist_ok=True)

def calc_atr(daily, L=14):
    n=min(L,len(daily)); ts=[]
    for i in range(max(1,len(daily)-n),len(daily)):
        h,l,pc=daily[i]['h'],daily[i]['l'],daily[i-1]['c']
        ts.append(max(h-l,abs(h-pc),abs(l-pc)))
    return sum(ts)/len(ts) if ts else 1.0

def sim_exit(daily, eidx, ep, sl_price, tp_price=None, max_bars=30):
    """V14增强退出: 支持结构TP目标"""
    hs=[b['h'] for b in daily]; ls=[b['l'] for b in daily]; cs=[b['c'] for b in daily]
    n=len(daily); sc=sl_price; ext=ep; act=False
    atr=calc_atr(daily[:eidx+1],14); ap=atr/ep if ep>0 else 0.02
    
    # TP: 结构目标优先, 否则用ATR倍数
    if tp_price is None: tp_price=ep*(1+ap*2.0)
    tp2 = ep*(1+ap*4.0)
    
    ta=ap*1.5; td=ap*0.6  # V14: 更早激活trailing
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
    
    return {'pnl_pct':round(p*100,2), 'won':p*100>0, 'hold_bars':eb-eidx,
            'exit_price':round(ex,3), 'exit_bar':eb, 'exit_reason':er, 'tp1_hit':t1, 'tp2_hit':t2}

# ═══ 扫描配置 ═══
signal_combos = [
    ('OB_only',      ['OB_Bull'],                    []),
    ('OB+Sweep',     ['OB_Bull'],                    ['Sweep_SSL','Sweep_BSL']),
    ('OB+CHOCH',     ['OB_Bull'],                    ['CHOCH_Bull','CHOCH_Bear']),
    ('OB+Breaker',   ['OB_Bull','BreakerBlock_Bull'], []),
    ('OB+Pinbar',    ['OB_Bull'],                    ['Pinbar_Bull']),
]

sl_modes = [
    ('sl_fixed',    lambda cl,ep,ap: (cl*(1-ap*1.2), cl*(1-ap*1.2))),  # V13当前
    ('sl_capped',   lambda cl,ep,ap: (max(cl*(1-ap*1.2), ep*0.92), cl*(1-ap*1.2))),  # 上限min
]

tp_modes = [
    ('tp_atr',      None),   # 固定ATR倍数
    ('tp_swing',    'swing'), # 前摆动点目标
]

entry_modes = [
    ('zone_retrace',  'retrace'),
    ('zone_bottom',   'bottom'),
]

# ═══ 运行 ═══
files = sorted(DAILY_DIR.glob('*_daily_300.json'))
print(f"V14扫描: {len(files)} stocks, {len(signal_combos)}×{len(sl_modes)}×{len(tp_modes)}×{len(entry_modes)}={len(signal_combos)*len(sl_modes)*len(tp_modes)*len(entry_modes)} combos")

results = {}

for combo_name, valid_types, require_nearby in signal_combos:
    for sl_name, sl_fn in sl_modes:
        for tp_name, tp_mode in tp_modes:
            for entry_name, entry_mode in entry_modes:
                key = f"{combo_name}|{sl_name}|{tp_name}|{entry_name}"
                all_trades = []
                
                for fp in files:
                    fname = fp.name; parts = fname.replace('_daily_300.json','').split('_')
                    if len(parts) < 2: continue
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
                    sigs,_,swings,_=detect_all_signals_v22(daily); atr=_calc_atr(daily,200)
                    
                    # 信号索引
                    sig_by_type = defaultdict(list)
                    for s in sigs: sig_by_type[s.type].append(s)
                    
                    demand_zones=[s for s in sigs if any(s.type==vt for vt in valid_types) 
                                  and s.confidence>=0.7 and s.idx>=20 and s.idx<n-15]
                    
                    used=set()
                    for dz in demand_zones:
                        zl=dz.lower; zh=dz.upper; zb=dz.idx
                        if zl<=0 or zh<=zl or zb in used: continue
                        
                        # 反弹确认
                        rh=max(hs[zb:min(n,zb+20)])
                        if rh<zh+atr*0.3: continue
                        # Zone年龄
                        if n-1-zb>120: continue
                        # 击穿检查
                        br=False
                        for j in range(zb+5,n):
                            if cs[j]<zl*0.98: br=True; break
                        if br: continue
                        
                        # 关联信号检查
                        if require_nearby:
                            has_nearby=False
                            for rt in require_nearby:
                                for ns in sig_by_type.get(rt,[]):
                                    if abs(ns.idx-zb)<=20:
                                        has_nearby=True; break
                                if has_nearby: break
                            if not has_nearby: continue
                        
                        # 入场
                        eb=None; ep=None
                        if entry_mode=='retrace':
                            for w in range(1,15):
                                e=zb+w
                                if e>=n-15: break
                                if ls[e]<=zh:
                                    eb=e; ep=max(zl,ls[e]); break
                        elif entry_mode=='bottom':
                            # 等价格触及zone底部再入场(更精确)
                            for w in range(1,20):
                                e=zb+w
                                if e>=n-15: break
                                if ls[e]<=zl*1.02:  # 触及zone下沿
                                    # 确认: 收盘在zone内
                                    if cs[e]>=zl:
                                        eb=e; ep=max(zl,ls[e]); break
                        
                        if eb is None: continue
                        used.add(zb)
                        
                        # SL计算
                        ap=atr/ep if ep>0 else 0.02
                        sl_raw, sl_effective = sl_fn(zl, ep, ap)
                        sl=min(sl_raw, sl_effective)
                        sl_pct=(ep-sl)/ep*100
                        
                        # 结构TP目标: 前摆动高点
                        tp_price=None
                        if tp_mode=='swing':
                            swings_list=[sw for sw in swings if sw.type=='H' and sw.bar_idx<zb]
                            if swings_list:
                                prev_high=max(sw.price for sw in swings_list[-3:])
                                if prev_high>ep*1.02:
                                    tp_price=prev_high
                        
                        r=sim_exit(daily, eb, ep, sl, tp_price)
                        r['exit_date']=ds[r['exit_bar']] if r['exit_bar']<len(ds) else ''
                        
                        all_trades.append({
                            'symbol':fname.split('_')[0],
                            'entry_date':ds[eb] if eb<len(ds) else '',
                            'entry_idx':eb,'entry_price':round(ep,3),
                            'cost_line':round(zl,3),'sl_pct':round(sl_pct,2),
                            'pnl_pct':r['pnl_pct'],'won':r['won'],
                            'rr':round(r['pnl_pct']/sl_pct,2) if sl_pct>0 else 99,
                            'hold_bars':r['hold_bars'],'exit_reason':r['exit_reason'],
                            'tp1_hit':r['tp1_hit'],
                        })
                
                n_t=len(all_trades); won=sum(1 for t in all_trades if t['won'])
                wr=won/n_t*100 if n_t else 0
                ap=sum(t['pnl_pct'] for t in all_trades)/n_t if n_t else 0
                rr_avg=sum(t['rr'] for t in all_trades)/n_t if n_t else 0
                st=len(set(t['symbol'] for t in all_trades))
                results[key] = {'trades':n_t,'stocks':st,'wr':wr,'avg_pnl':ap,'rr':rr_avg}

# ═══ 输出 ═══
print(f"\n{'信号组合':<12s} {'SL':<10s} {'TP':<10s} {'入场':<12s} {'交易':>6s} {'股票':>5s} {'WR':>6s} {'均盈':>7s} {'RR':>6s} {'综合':>6s}")
print("-"*90)
for combo_name, _, _ in signal_combos:
    for sl_name, _ in sl_modes:
        for tp_name, _ in tp_modes:
            for entry_name, _ in entry_modes:
                key = f"{combo_name}|{sl_name}|{tp_name}|{entry_name}"
                r = results.get(key, {})
                n_t = r.get('trades',0); st = r.get('stocks',0)
                wr = r.get('wr',0); ap = r.get('avg_pnl',0); rr = r.get('rr',0)
                # 综合评分: WR×0.4 + 交易量×0.3 + RR×0.3 (均盈归一化)
                score = wr*0.4 + min(1,n_t/2000)*30 + rr*30
                marker = '⭐' if score>70 else ('✅' if score>60 else '')
                print(f"{combo_name:<12s} {sl_name:<10s} {tp_name:<10s} {entry_name:<12s} {n_t:6d} {st:5d} {wr:5.1f}% {ap:+6.2f}% {rr:5.2f}x {score:5.0f} {marker}")

# 保存完整结果
out_path = OUT_DIR / 'v14_scan_results.json'
out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
print(f"\nSaved: {out_path}")

# V13基线对比
print(f"\nV13基线: 1399笔 1083只 97.3% +11.31% 1.43x")
