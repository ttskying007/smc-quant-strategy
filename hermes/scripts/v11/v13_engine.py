#!/usr/bin/env python3
"""
V13修正版: 纯SMC Zone入场 — 击穿后的反转=PO3有效信号

Zone有效性逻辑:
  ❌ Zone从未反弹确认 → 无效(不是真正的需求区)
  ❌ Zone击穿后无CHOCH反转 → 无效(趋势延续下跌)
  ✅ Zone击穿 + CHOCH_Bull反转 → PO3有效 (流动性清扫后反转)
  ✅ Zone未击穿 + 回撤到zone内 → 标准入场

入场条件:
  1. Zone反弹确认 (rally > zone_high + ATR*0.3)
  2. Zone形成后有CHOCH_Bull反转 (证明趋势改变)
  3. 当前价格在zone区间内或略下方(回撤机会)
  4. Zone不过于陈旧(<80bar)
"""
import json, sys, math, csv
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v22 import detect_all_signals_v22, _calc_atr

DAILY_DIR = Path('/root/.hermes/kline_cache')
OUT_DIR = Path('/root/.hermes/smc_opt_v13')
OUT_DIR.mkdir(exist_ok=True)

# ═══ 可配置参数 ═══
V13_MAX_AGE = 120       # zone最大年龄(bar)
V13_REQUIRE_CHOCH = False  # 是否要求CHOCH_Bull
V13_ALLOW_PO3 = False   # 是否允许击穿后PO3入场

def calc_atr(daily, length=14):
    n = min(length, len(daily))
    trs = []
    for i in range(max(1, len(daily)-n), len(daily)):
        h,l,pc = daily[i]['h'],daily[i]['l'],daily[i-1]['c']
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs)/len(trs) if trs else 1.0

def calc_sltp(daily, entry_idx, entry_price, cost_line):
    atr = calc_atr(daily[:entry_idx+1], 14)
    atr_pct = atr/entry_price if entry_price>0 else 0.02
    sl = cost_line * (1 - atr_pct * 1.2)
    sl_pct = (entry_price - sl) / entry_price * 100
    tp1 = entry_price * (1 + atr_pct * 2.0)
    tp2 = entry_price * (1 + atr_pct * 4.0)
    trail_act = atr_pct * 3.0; trail_dist = atr_pct * 0.8
    return {'sl':round(sl,3), 'sl_pct':round(sl_pct,2), 'tp1':round(tp1,3), 'tp2':round(tp2,3),
            'tp_pct':round(atr_pct*200,1), 'trail_act':trail_act, 'trail_dist':trail_dist}

def simulate_exit(daily, entry_idx, entry_price, sltp):
    highs=[b['h'] for b in daily]; lows=[b['l'] for b in daily]; closes=[b['c'] for b in daily]
    n=len(daily); sl=sltp['sl']; tp1=sltp['tp1']; tp2=sltp['tp2']
    trail_act=sltp['trail_act']; trail_dist=sltp['trail_dist']
    extreme=entry_price; sl_current=sl; trail_active=False
    tp1_hit=False; tp2_hit=False; exit_bar=None; exit_price=None; exit_reason='timeout'
    for j in range(entry_idx+1, min(n, entry_idx+40)):
        if highs[j]>extreme: extreme=highs[j]
        gain=(extreme-entry_price)/entry_price
        if not trail_active and gain>=trail_act: trail_active=True
        if trail_active: sl_current=max(sl_current, extreme*(1-trail_dist))
        if not tp1_hit and highs[j]>=tp1: tp1_hit=True
        if not tp2_hit and highs[j]>=tp2: tp2_hit=True
        if lows[j]<=sl_current: exit_bar=j; exit_price=max(sl_current,lows[j]); exit_reason='SL_hit'; break
        if j==entry_idx+30: exit_bar=j; exit_price=closes[j]; exit_reason='time_stop'; break
    if exit_bar is None: exit_bar=min(entry_idx+39,n-1); exit_price=closes[exit_bar]; exit_reason='timeout'
    pnl=0
    if tp1_hit: pnl+=0.5*(tp1-entry_price)/entry_price
    else: pnl+=0.5*(closes[exit_bar]-entry_price)/entry_price
    if tp2_hit: pnl+=0.3*(tp2-entry_price)/entry_price
    else: pnl+=0.3*(closes[exit_bar]-entry_price)/entry_price
    pnl+=0.2*(exit_price-entry_price)/entry_price
    return {'pnl_pct':round(pnl*100,2), 'won':pnl*100>0, 'hold_bars':exit_bar-entry_idx,
            'exit_price':round(exit_price,3), 'exit_bar':exit_bar, 'exit_reason':exit_reason,
            'tp1_hit':tp1_hit, 'tp2_hit':tp2_hit}

def classify_zone(zone_bar, zone_low, zone_high, daily, sigs, atr):
    """分类Zone有效性: 未击穿 / PO3反转(击穿后CHOCH) / 击穿无效"""
    n=len(daily); closes=[b['c'] for b in daily]
    
    # 找击穿点: 收盘跌破zone下沿2%
    breach_bar = -1
    for j in range(zone_bar+5, n):
        if closes[j] < zone_low * 0.98:
            breach_bar = j; break
    
    if breach_bar < 0:
        return 'unbreached', -1  # 从未击穿
    
    # 击穿后找CHOCH_Bull反转
    choch_after_breach = [s for s in sigs if s.type=='CHOCH_Bull' 
                          and breach_bar < s.idx <= breach_bar+30]
    
    if choch_after_breach:
        return 'po3', choch_after_breach[0].idx  # PO3: 击穿后反转
    else:
        return 'breached_invalid', breach_bar  # 击穿无反转=无效

def backtest_stock_v13(symbol, daily):
    if len(daily)<60: return []
    n=len(daily); closes=[b['c'] for b in daily]; highs=[b['h'] for b in daily]
    lows=[b['l'] for b in daily]; dates=[str(b.get('t',''))[:10] for b in daily]
    atr=calc_atr(daily, 200)
    
    sigs, _, _, _ = detect_all_signals_v22(daily)
    
    demand_zones = [s for s in sigs if s.type=='OB_Bull' and s.confidence>=0.7 
                    and s.idx>=20 and s.idx<n-15]
    
    trades=[]; used_zones=set()
    
    for dz in demand_zones:
        dz_low=dz.lower; dz_high=dz.upper; dz_bar=dz.idx
        if dz_low<=0 or dz_high<=dz_low: continue
        if dz_bar in used_zones: continue
        
        # 1. Zone反弹确认
        rally_high=max(highs[dz_bar:min(n, dz_bar+20)])
        if rally_high < dz_high + atr*0.3: continue
        
        # 2. Zone年龄限制 (可配置)
        zone_age = n-1-dz_bar
        if zone_age > V13_MAX_AGE: continue
        
        # 3. 击穿检查: 如果击穿,必须后面有CHOCH反转(PO3)
        breached=False; breach_bar=-1
        for j in range(dz_bar+5, n):
            if closes[j] < dz_low*0.98:
                breached=True; breach_bar=j; break
        
        if breached:
            # PO3: 击穿后必须有CHOCH_Bull反转
            if not V13_ALLOW_PO3: continue
            choch_after_breach = [s for s in sigs if s.type=='CHOCH_Bull' 
                                  and breach_bar < s.idx <= breach_bar+30]
            if not choch_after_breach: continue
        
        # 4. CHOCH要求 (可配置)
        if V13_REQUIRE_CHOCH:
            choch_after = [s for s in sigs if s.type=='CHOCH_Bull' and dz_bar <= s.idx <= dz_bar+50]
            if not choch_after: continue
        
        # 5. 入场
        entry_bar=None; entry_price=None
        for w in range(1, 15):
            eb=dz_bar+w
            if eb>=n-15: break
            if lows[eb] <= dz_high:
                entry_bar=eb; entry_price=max(dz_low, lows[eb]); break
        
        if entry_bar is None: continue
        used_zones.add(dz_bar)
        
        sltp=calc_sltp(daily, entry_bar, entry_price, dz_low)
        result=simulate_exit(daily, entry_bar, entry_price, sltp)
        result['exit_date']=dates[result['exit_bar']] if result['exit_bar']<len(dates) else ''
        
        zone_type = 'po3' if breached else 'unbreached'
        
        trades.append({
            'symbol':symbol,
            'entry_date':dates[entry_bar] if entry_bar<len(dates) else '',
            'signal_type':'OB_Bull',
            'entry_idx':entry_bar,
            'entry_price':round(entry_price,3),
            'cost_line':round(dz_low,3),
            'zone_type':zone_type,
            'zone_bar':dz_bar,
            'zone_age':entry_bar-dz_bar,
            'sl_price':sltp['sl'],
            'sl_pct':sltp['sl_pct'],
            'tp_pct':sltp['tp_pct'],
            'exit_date':result['exit_date'],
            'exit_bar':result['exit_bar'],
            'exit_price':result['exit_price'],
            'exit_reason':result['exit_reason'],
            'pnl_pct':result['pnl_pct'],
            'won':result['won'],
            'rr':round(result['pnl_pct']/sltp['sl_pct'],2) if sltp['sl_pct']>0 else 99,
            'hold_bars':result['hold_bars'],
            'tp1_hit':result['tp1_hit'],
            'tp2_hit':result['tp2_hit'],
        })
    return trades

def run_full(limit=None):
    daily_files=sorted(DAILY_DIR.glob('*_daily_300.json'))
    if limit: daily_files=daily_files[:limit]
    all_trades=[]
    for fi,fp in enumerate(daily_files):
        fname=fp.name; parts=fname.replace('_daily_300.json','').split('_')
        if len(parts)>=2: symbol='.'.join(parts)
        else: continue
        try:
            daily=json.loads(fp.read_bytes())
            for b in daily:
                if 't' not in b and 'date' in b: b['t']=str(b['date'])
                for k in ('o','h','l','c','v'): b[k]=float(b[k]) if k in b else 0
        except: continue
        trades=backtest_stock_v13(symbol, daily)
        all_trades.extend(trades)
        if (fi+1)%500==0: print(f"  [{fi+1}/{len(daily_files)}] {symbol} -> {len(trades)} trades")
    
    n=len(all_trades); won=sum(1 for t in all_trades if t['won'])
    print(f"\nV13完成: {n} trades, {len(set(t['symbol'] for t in all_trades))} stocks")
    print(f"  WR={won/n*100:.1f}% Avg PnL={sum(t['pnl_pct'] for t in all_trades)/n:+.2f}%")
    
    # 按zone类型分组
    for zt in ['unbreached','po3']:
        ct=[t for t in all_trades if t['zone_type']==zt]
        if not ct: continue
        cw=sum(1 for t in ct if t['won'])
        ca=sum(t['pnl_pct'] for t in ct)/len(ct)
        print(f"  {zt:15s}: {len(ct):5d} WR={cw/len(ct)*100:.1f}% avg={ca:+.2f}%")
    
    out_json=OUT_DIR/'v13_complete.json'
    out_json.write_text(json.dumps(all_trades, ensure_ascii=False, indent=2))
    
    csv_path=OUT_DIR/'v13_trade_log.csv'
    if all_trades:
        with open(csv_path,'w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f, fieldnames=list(all_trades[0].keys()), extrasaction='ignore')
            w.writeheader(); w.writerows(all_trades)
    return all_trades

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--limit',type=int,default=0)
    args=ap.parse_args()
    run_full(limit=args.limit or None)
