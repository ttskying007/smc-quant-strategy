#!/usr/bin/env python3
"""
V22 SMC信号引擎 — 全面诊断修复 + 缺失信号实现

V21→V22 修复:
1. OB(LuxAlgo): 从break bar向后搜索(非swing→break), 取最近反向K线
2. OB(SMC2026): 重新启用, 从swing bar向后搜索
3. 新信号: IFVG(逆FVG), Breaker(失败OB反转), LV(流动性空洞), RB(拒绝块), OTE(最优入场), PO3
4. CHOCH/BOS: 确保不引用未来swing
5. Sweep: 放宽至ATR*0.05 + 30bar窗口
6. EQL: 修复配对逻辑
"""
import math, logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

log = logging.getLogger('smc_v22')

@dataclass
class Signal:
    type: str; idx: int; direction: str; price: float
    upper: float = 0.0; lower: float = 0.0
    strength: float = 0.0; confidence: float = 0.0
    timeframe: str = 'daily'; confirmed_at: int = 0
    volume_ratio: float = 1.0; grade: int = 1
    trend_aligned: bool = False
    metadata: Dict = field(default_factory=dict)
    def to_dict(self) -> Dict:
        return {'type':self.type,'idx':self.idx,'direction':self.direction,
                'price':round(self.price,4),'upper':round(self.upper,4),
                'lower':round(self.lower,4),'strength':round(self.strength,2),
                'confidence':round(self.confidence,3),'timeframe':self.timeframe,
                'confirmed_at':self.confirmed_at,'volume_ratio':round(self.volume_ratio,2),
                'grade':self.grade,'trend_aligned':self.trend_aligned,'metadata':self.metadata}

class SwingPoint:
    def __init__(self, bar_idx, price, ptype, label=''):
        self.bar_idx = bar_idx; self.price = price
        self.type = ptype; self.label = label; self.crossed = False

def _calc_atr(ohlcv, length=14):
    n = min(length, len(ohlcv))
    trs = []
    for i in range(max(1,len(ohlcv)-n), len(ohlcv)):
        h,l,pc = ohlcv[i]['h'],ohlcv[i]['l'],ohlcv[i-1]['c']
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs)/len(trs) if trs else 1.0

# ═══ LEG SWINGS (V20 LuxAlgo leg) ═══
def detect_leg_swings(ohlcv, leg_size=20) -> Tuple[List[SwingPoint], Dict]:
    n = len(ohlcv)
    if n < leg_size * 2: return [], {'highs': [], 'lows': []}
    leg = 0; prev_leg = 0; swings = []
    last_high = None; last_low = None
    for i in range(leg_size, n):
        pivot_bar = i - leg_size
        pivot_high = ohlcv[pivot_bar]['h']; pivot_low = ohlcv[pivot_bar]['l']
        recent_highs = [ohlcv[j]['h'] for j in range(pivot_bar+1, i+1)]
        recent_lows = [ohlcv[j]['l'] for j in range(pivot_bar+1, i+1)]
        if pivot_high > max(recent_highs): leg = -1
        elif pivot_low < min(recent_lows): leg = 1
        if leg != 0 and leg != prev_leg:
            if leg == -1:
                price = pivot_high
                label = 'HH' if (last_high and price > last_high.price) else ('LH' if last_high else 'HH')
                sp = SwingPoint(pivot_bar, price, 'H', label)
                sp.last_price = last_high.price if last_high else None
                last_high = sp; swings.append(sp)
            else:
                price = pivot_low
                label = 'LL' if (last_low and price < last_low.price) else ('HL' if last_low else 'LL')
                sp = SwingPoint(pivot_bar, price, 'L', label)
                sp.last_price = last_low.price if last_low else None
                last_low = sp; swings.append(sp)
        prev_leg = leg
    highs = [{'bar_idx':s.bar_idx,'price':s.price,'label':s.label} for s in swings if s.type=='H']
    lows = [{'bar_idx':s.bar_idx,'price':s.price,'label':s.label} for s in swings if s.type=='L']
    return swings, {'highs':highs, 'lows':lows}

# ═══ 1. CHOCH/BOS ═══
def detect_choch_bos(ohlcv, swings, atr_val):
    n = len(ohlcv); signals = []; fired_swings = set(); min_pen = atr_val * 0.2
    for i in range(5, n):
        close = ohlcv[i]['c']; prev_close = ohlcv[i-1]['c']
        for sh in swings:
            if sh.type != 'H' or sh.bar_idx >= i or sh.bar_idx in fired_swings or not sh.label: continue
            penetration = close - sh.price
            if prev_close <= sh.price and penetration >= min_pen:
                tag = 'CHOCH_Bull' if sh.label == 'LH' else 'BOS_Bull'
                signals.append(Signal(tag, i, 'bull', price=round(close,2), upper=close,
                    strength=round(penetration/atr_val,1) if atr_val>0 else 7.0,
                    confidence=0.85 if 'CHOCH' in tag else 0.7,
                    metadata={'swing_bar':sh.bar_idx,'swing_price':sh.price,'swing_label':sh.label}))
                fired_swings.add(sh.bar_idx)
        for sl in swings:
            if sl.type != 'L' or sl.bar_idx >= i or sl.bar_idx in fired_swings or not sl.label: continue
            penetration = sl.price - close
            if prev_close >= sl.price and penetration >= min_pen:
                tag = 'CHOCH_Bear' if sl.label == 'HL' else 'BOS_Bear'
                signals.append(Signal(tag, i, 'bear', price=round(close,2), lower=close,
                    strength=round(penetration/atr_val,1) if atr_val>0 else 7.0,
                    confidence=0.85 if 'CHOCH' in tag else 0.7,
                    metadata={'swing_bar':sl.bar_idx,'swing_price':sl.price,'swing_label':sl.label}))
                fired_swings.add(sl.bar_idx)
    # 同方向3bar去重
    signals.sort(key=lambda s:s.idx)
    deduped=[]; lb=-999; lp=0
    for s in signals:
        is_bull='Bull' in s.type; pen=s.metadata.get('penetration',0) or (abs(s.price-s.metadata.get('swing_price',0)))
        if s.idx-lb<=3 and is_bull==(lb_bull if 'lb_bull' in dir() else None):
            if pen>lp: deduped.pop(); deduped.append(s); lp=pen
        else: deduped.append(s); lp=pen
        lb=s.idx; lb_bull=is_bull
    return deduped

# ═══ 2. OB (LuxAlgo: 从break bar向后搜索) ═══
def detect_ob_luxalgo(ohlcv, swings, choch_bos):
    n=len(ohlcv); signals=[]
    atr=_calc_atr(ohlcv,200)
    for cbs in choch_bos:
        break_bar=cbs.idx; is_bull='Bull' in cbs.type
        sw_bar=cbs.metadata.get('swing_bar',break_bar)
        # OB必须在摆动点5bar以内
        if break_bar - sw_bar > 8: continue
        found=None
        for j in range(break_bar-1, max(0,break_bar-5), -1):  # 最多往回5bar
            b=ohlcv[j]
            if is_bull and b['c']>b['o']:
                if b['l'] - ohlcv[sw_bar]['l'] > atr*0.3 if sw_bar<n else True:
                    found=(j,b['h'],b['l'],b['c']); break
            elif not is_bull and b['c']<b['o']:
                if ohlcv[sw_bar]['h'] - b['h'] > atr*0.3 if sw_bar<n else True:
                    found=(j,b['h'],b['l'],b['c']); break
        if found:
            j,h,l,c=found
            tag='OB_Bull' if is_bull else 'OB_Bear'
            signals.append(Signal(tag,j,'bull' if is_bull else 'bear',
                upper=h,lower=l,price=c,strength=7.0,confidence=0.75,
                metadata={'break_bar':break_bar,'swing_bar':sw_bar}))
    return signals

# ═══ 3. OB (SMC2026: 从swing往回找) ═══
def detect_ob_smc2026(ohlcv, swings):
    n=len(ohlcv); signals=[]
    atr=_calc_atr(ohlcv,200)
    for sw in swings:
        if sw.bar_idx<2: continue
        found=None
        for j in range(sw.bar_idx-1, max(0,sw.bar_idx-5), -1):  # 最多往回5bar
            b=ohlcv[j]
            if sw.type=='H' and b['c']<b['o']:
                displacement=sw.price-b['h']
                if displacement>atr*0.5:  # Pine: displacement > ATR*1.3, 我们用0.5适配A股
                    found=(j,b['c'],b['h'],b['l'],round(displacement,2)); break
            elif sw.type=='L' and b['c']>b['o']:
                displacement=b['l']-sw.price
                if displacement>atr*0.5:
                    found=(j,b['c'],b['h'],b['l'],round(displacement,2)); break
        if found:
            j,c,h,l,disp=found
            tag='OB_Bear' if sw.type=='H' else 'OB_Bull'
            signals.append(Signal(tag,j,'bear' if sw.type=='H' else 'bull',
                upper=h,lower=l,price=c,strength=min(10.0,disp/atr*3),confidence=0.80,
                metadata={'swing_bar':sw.bar_idx}))
    return signals

# ═══ 4. FVG ═══
def detect_fvg(ohlcv, atr_mult=0.3, min_strength=1.5):
    n=len(ohlcv)
    if n<3: return []
    atr=_calc_atr(ohlcv,14); min_gap=atr*atr_mult; signals=[]
    for i in range(2,n):
        if ohlcv[i]['l']>ohlcv[i-2]['h']:
            gap=ohlcv[i]['l']-ohlcv[i-2]['h']
            if gap>=min_gap:
                strength=min(10.0,gap/atr*3)
                if strength>=min_strength:
                    signals.append(Signal('FVG_Bull',i-1,'bull',
                        price=ohlcv[i-2]['h'],upper=ohlcv[i]['l'],lower=ohlcv[i-2]['h'],
                        strength=round(strength,1),confidence=0.75,confirmed_at=i))
        if ohlcv[i]['h']<ohlcv[i-2]['l']:
            gap=ohlcv[i-2]['l']-ohlcv[i]['h']
            if gap>=min_gap:
                strength=min(10.0,gap/atr*3)
                if strength>=min_strength:
                    signals.append(Signal('FVG_Bear',i-1,'bear',
                        price=ohlcv[i-2]['l'],upper=ohlcv[i-2]['l'],lower=ohlcv[i]['h'],
                        strength=round(strength,1),confidence=0.75,confirmed_at=i))
    return signals

# ═══ 5. IFVG — Inverse FVG (FVG被回补后反转) ═══
def detect_ifvg(ohlcv, fvg_signals):
    """IFVG: FVG zone gets filled by price, then acts as opposite zone"""
    n=len(ohlcv); signals=[]
    for fvg in fvg_signals:
        fvg_high=fvg.upper; fvg_low=fvg.lower; fvg_bar=fvg.idx
        for j in range(fvg_bar+1, min(n,fvg_bar+60)):
            c=ohlcv[j]['c']
            if fvg_low<c<fvg_high:  # FVG filled
                tag='IFVG_Bull' if fvg.type=='FVG_Bear' else 'IFVG_Bear'
                signals.append(Signal(tag,j,'bull' if 'Bull' in tag else 'bear',
                    upper=fvg_high,lower=fvg_low,price=(fvg_high+fvg_low)/2,
                    strength=3.0,confidence=0.5,metadata={'fvg_bar':fvg_bar}))
                break
    return signals

# ═══ 6. Sweep ═══
def detect_sweep(ohlcv, swings, atr_val):
    n=len(ohlcv); signals=[]; min_pen=atr_val*0.05
    swing_highs=[(s.bar_idx,s.price) for s in swings if s.type=='H']
    swing_lows=[(s.bar_idx,s.price) for s in swings if s.type=='L']
    last_bsl=-999; last_ssl=-999
    for i in range(5,n):
        bar=ohlcv[i]
        if i-last_bsl>=3:
            best=None; best_depth=0
            for sh_idx,sh_price in swing_highs:
                if sh_idx>=i-30 and sh_idx<i:
                    if bar['h']>sh_price+min_pen and bar['c']<sh_price:
                        depth=bar['h']-sh_price
                        if depth>best_depth: best_depth=depth; best=(sh_idx,sh_price)
            if best:
                signals.append(Signal('Sweep_BSL',i,'bear',price=best[1],
                    strength=round(best_depth/atr_val,1) if atr_val>0 else 6.0,confidence=0.7,
                    metadata={'swept_level':best[1],'level_bar':best[0]})); last_bsl=i
        if i-last_ssl>=3:
            best=None; best_depth=0
            for sl_idx,sl_price in swing_lows:
                if sl_idx>=i-30 and sl_idx<i:
                    if bar['l']<sl_price-min_pen and bar['c']>sl_price:
                        depth=sl_price-bar['l']
                        if depth>best_depth: best_depth=depth; best=(sl_idx,sl_price)
            if best:
                signals.append(Signal('Sweep_SSL',i,'bull',price=best[1],
                    strength=round(best_depth/atr_val,1) if atr_val>0 else 6.0,confidence=0.7,
                    metadata={'swept_level':best[1],'level_bar':best[0]})); last_ssl=i
    return signals

# ═══ 7. MSS ═══
def detect_mss(ohlcv, swings, atr_val):
    n=len(ohlcv); signals=[]; last_mss=-999; min_pen=atr_val*0.4
    highs=[(s.bar_idx,s.price) for s in swings if s.type=='H']
    lows=[(s.bar_idx,s.price) for s in swings if s.type=='L']
    for i in range(5,n):
        if i-last_mss<8: continue
        close=ohlcv[i]['c']; prev_close=ohlcv[i-1]['c']
        for sh_idx,sh_price in highs:
            if sh_idx<i-3 and sh_idx>=i-50:
                if prev_close<=sh_price and close>sh_price+min_pen:
                    signals.append(Signal('MSS_Bull',i,'bull',price=round(close,2),
                        strength=round((close-sh_price)/atr_val,1) if atr_val>0 else 4.0,confidence=0.7,
                        metadata={'pivot_bar':sh_idx,'pivot_price':sh_price})); last_mss=i; break
        for sl_idx,sl_price in lows:
            if sl_idx<i-3 and sl_idx>=i-50:
                if prev_close>=sl_price and close<sl_price-min_pen:
                    signals.append(Signal('MSS_Bear',i,'bear',price=round(close,2),
                        strength=round((sl_price-close)/atr_val,1) if atr_val>0 else 4.0,confidence=0.7,
                        metadata={'pivot_bar':sl_idx,'pivot_price':sl_price})); last_mss=i; break
    return signals

# ═══ 8. EQL/EQH ═══
def detect_eql(ohlcv, swings, atr_val=None, avg_price=None):
    if avg_price is None: avg_price=sum(b['c'] for b in ohlcv[-100:])/min(100,len(ohlcv)) if len(ohlcv)>=20 else 100
    if atr_val is None: atr_val=_calc_atr(ohlcv,200)
    threshold=max(avg_price*0.003,atr_val*0.5); signals=[]
    highs=[s for s in swings if s.type=='H']; lows=[s for s in swings if s.type=='L']
    matched_h=set()
    for i in range(len(highs)):
        if highs[i].bar_idx in matched_h: continue
        best_j=None; best_dist=999
        for j in range(len(highs)):
            if i==j: continue
            a,b=highs[i],highs[j]
            if abs(a.bar_idx-b.bar_idx)<5: continue
            if abs(a.price-b.price)<=threshold:
                dist=abs(a.bar_idx-b.bar_idx)
                if dist<best_dist: best_dist=dist; best_j=j
        if best_j is not None:
            a,b=highs[i],highs[best_j]; use=b if b.bar_idx>a.bar_idx else a
            signals.append(Signal('EQL_High',use.bar_idx,'neutral',price=use.price,
                upper=max(a.price,b.price),lower=min(a.price,b.price),strength=3.0,confidence=0.5))
            matched_h.add(a.bar_idx); matched_h.add(b.bar_idx)
    matched_l=set()
    for i in range(len(lows)):
        if lows[i].bar_idx in matched_l: continue
        best_j=None; best_dist=999
        for j in range(len(lows)):
            if i==j: continue
            a,b=lows[i],lows[j]
            if abs(a.bar_idx-b.bar_idx)<5: continue
            if abs(a.price-b.price)<=threshold:
                dist=abs(a.bar_idx-b.bar_idx)
                if dist<best_dist: best_dist=dist; best_j=j
        if best_j is not None:
            a,b=lows[i],lows[best_j]; use=b if b.bar_idx>a.bar_idx else a
            signals.append(Signal('EQL_Low',use.bar_idx,'neutral',price=use.price,
                upper=max(a.price,b.price),lower=min(a.price,b.price),strength=3.0,confidence=0.5))
            matched_l.add(a.bar_idx); matched_l.add(b.bar_idx)
    return signals

# ═══ 9. BPR (Breaker Range: bull+bear zone overlap) ═══
def detect_bpr(fvg_signals, ob_signals):
    signals=[]; bull_zones=[(s.lower,s.upper,s.idx) for s in fvg_signals+ob_signals if s.direction=='bull']
    bear_zones=[(s.lower,s.upper,s.idx) for s in fvg_signals+ob_signals if s.direction=='bear']
    added=set(); all_bpr=[]
    for bl,bu,bidx in bull_zones:
        for rl,ru,ridx in bear_zones:
            ol=max(bl,rl); oh=min(bu,ru)
            key=(round(ol,2),round(oh,2))
            if ol<oh and key not in added:
                added.add(key); all_bpr.append((max(bidx,ridx),ol,oh,(ol+oh)/2))
    all_bpr.sort(key=lambda x:-x[0])
    for bidx,ol,oh,mid in all_bpr[:10]:
        signals.append(Signal('BPR',bidx,'neutral',price=mid,upper=oh,lower=ol,strength=5.0,confidence=0.65))
    return signals

# ═══ 10. BREAKER BLOCK (失败的OB变成反向) ═══
def detect_breaker(ohlcv, ob_signals):
    """Breaker Block: OB被突破后变成反向支撑/阻力"""
    n=len(ohlcv); signals=[]
    for ob in ob_signals:
        if ob.lower>=ob.upper: continue
        for j in range(ob.idx+1, min(n,ob.idx+30)):
            c=ohlcv[j]['c']
            if ob.type=='OB_Bull' and c<ob.lower:  # 看涨OB被下破→ 变看跌Breaker
                signals.append(Signal('BreakerBlock_Bear',j,'bear',
                    upper=ob.upper,lower=ob.lower,price=c,strength=4.0,confidence=0.6,
                    metadata={'ob_bar':ob.idx})); break
            elif ob.type=='OB_Bear' and c>ob.upper:  # 看跌OB被上破→ 变看涨Breaker
                signals.append(Signal('BreakerBlock_Bull',j,'bull',
                    upper=ob.upper,lower=ob.lower,price=c,strength=4.0,confidence=0.6,
                    metadata={'ob_bar':ob.idx})); break
    return signals

# ═══ 11. LIQUIDITY VOID (价格跳过区域) ═══
def detect_liquidity_void(ohlcv, atr_val):
    """LV: 连续K线之间价格跳空，没有交易发生的区域"""
    n=len(ohlcv); signals=[]; min_gap=atr_val*0.2
    for i in range(1,n):
        b0,b1=ohlcv[i-1],ohlcv[i]
        if b1['l']>b0['h']+min_gap:  # 向上跳空
            signals.append(Signal('LiquidityVoid',i,'bull',
                price=(b0['h']+b1['l'])/2,upper=b1['l'],lower=b0['h'],
                strength=round((b1['l']-b0['h'])/atr_val,2) if atr_val>0 else 3.0,confidence=0.45))
        elif b1['h']<b0['l']-min_gap:  # 向下跳空
            signals.append(Signal('LiquidityVoid',i,'bear',
                price=(b0['l']+b1['h'])/2,upper=b0['l'],lower=b1['h'],
                strength=round((b0['l']-b1['h'])/atr_val,2) if atr_val>0 else 3.0,confidence=0.45))
    return signals

# ═══ 12. REJECTION BLOCK (价格拒绝某个水平) ═══
def detect_rejection(ohlcv, swings, atr_val):
    """RB: 价格快速接近摆动点后强烈反转"""
    n=len(ohlcv); signals=[]; min_reject=atr_val*0.5
    for sw in swings:
        for j in range(sw.bar_idx+1, min(n,sw.bar_idx+10)):
            b=ohlcv[j]
            if sw.type=='H':
                # 接近前高高点后大幅回落 → Rejection at Resistance
                approach=b['h']-sw.price
                rejection=b['h']-b['c']
                if approach>=-min_reject*0.3 and rejection>min_reject:
                    signals.append(Signal('Rejection_Resistance',j,'bear',
                        price=sw.price,upper=b['h'],lower=b['c'],
                        strength=round(rejection/atr_val,2) if atr_val>0 else 3.0,confidence=0.5,
                        metadata={'swing_bar':sw.bar_idx})); break
            else:
                # 接近前低低点后大幅反弹 → Rejection at Support
                approach=sw.price-b['l']
                rejection=b['c']-b['l']
                if approach>=-min_reject*0.3 and rejection>min_reject:
                    signals.append(Signal('Rejection_Support',j,'bull',
                        price=sw.price,upper=b['c'],lower=b['l'],
                        strength=round(rejection/atr_val,2) if atr_val>0 else 3.0,confidence=0.5,
                        metadata={'swing_bar':sw.bar_idx})); break
    return signals

# ═══ 13. OTE (Optimal Trade Entry: Fib回撤区) ═══
def detect_ote(ohlcv, swings, atr_val):
    """OTE: 最近摆动leg的61.8%-79%回撤区域"""
    n=len(ohlcv); signals=[]
    hs=[s for s in swings if s.type=='H']; ls=[s for s in swings if s.type=='L']
    all_swings=sorted(hs+ls, key=lambda s:s.bar_idx)
    if len(all_swings)<2: return []
    for i in range(1,len(all_swings)):
        a,b=all_swings[i-1],all_swings[i]
        diff=b.price-a.price
        if abs(diff)<atr_val*0.3: continue  # too small
        # Fib levels
        ote_low=a.price+diff*0.618 if a.type=='L' else b.price-diff*0.618
        ote_high=a.price+diff*0.79 if a.type=='L' else b.price-diff*0.79
        if ote_low>ote_high: ote_low,ote_high=ote_high,ote_low
        dir='bull' if a.type=='L' else 'bear'
        signals.append(Signal('OTE_'+('Bull' if dir=='bull' else 'Bear'),b.bar_idx,dir,
            price=(ote_low+ote_high)/2,upper=ote_high,lower=ote_low,
            strength=3.0,confidence=0.4,metadata={'swing_a':a.bar_idx,'swing_b':b.bar_idx}))
    return signals

# ═══ 14. PO3 (Power of Three: Accum/Manip/Dist) ═══
def detect_po3(ohlcv, atr_val):
    """PO3: 日内/区间 Accumulation→Manipulation→Distribution 模式"""
    n=len(ohlcv); signals=[]; window=5
    for i in range(window*2,n-window):
        # Accumulation: 窄幅整理
        acc_high=max(b['h'] for b in ohlcv[i-window:i]); acc_low=min(b['l'] for b in ohlcv[i-window:i])
        acc_range=acc_high-acc_low
        if acc_range>atr_val*2: continue  # not narrow enough
        # Manipulation: 突破accumulation区间
        next_high=max(b['h'] for b in ohlcv[i:i+window])
        next_low=min(b['l'] for b in ohlcv[i:i+window])
        if next_high>acc_high+atr_val*0.2:  # 向上突破
            signals.append(Signal('PO3_Acc',i-window,'bull',upper=acc_high,lower=acc_low,price=(acc_high+acc_low)/2,strength=2.0,confidence=0.35))
            signals.append(Signal('PO3_Man',i,'bull',upper=next_high,lower=acc_high,price=next_high,strength=2.0,confidence=0.35))
            signals.append(Signal('PO3_DIS',i+window,'bull',upper=next_high,lower=acc_high,price=next_high,strength=2.0,confidence=0.35))
        elif next_low<acc_low-atr_val*0.2:  # 向下突破
            signals.append(Signal('PO3_Acc',i-window,'bear',upper=acc_high,lower=acc_low,price=(acc_high+acc_low)/2,strength=2.0,confidence=0.35))
            signals.append(Signal('PO3_Man',i,'bear',upper=acc_low,lower=next_low,price=next_low,strength=2.0,confidence=0.35))
            signals.append(Signal('PO3_DIS',i+window,'bear',upper=acc_low,lower=next_low,price=next_low,strength=2.0,confidence=0.35))
    return signals

# ═══ 15. Pinbar ═══
def detect_pinbars(ohlcv):
    results=[]
    for i in range(20,len(ohlcv)):
        b=ohlcv[i]; o,h,l,c=b['o'],b['h'],b['l'],b['c']
        if h==l: continue
        range_hl=h-l
        if range_hl==0: continue
        body_abs=abs(c-o); lower_wick=min(o,c)-l; upper_wick=h-max(o,c)
        if lower_wick>body_abs*2.5 and lower_wick>range_hl*0.6 and upper_wick<range_hl*0.15:
            if c>(h-range_hl*0.3):
                results.append(Signal('Pinbar_Bull',i,'bull',lower=l,upper=h,price=c,strength=lower_wick/range_hl,confidence=0.55))
        elif upper_wick>body_abs*2.5 and upper_wick>range_hl*0.6 and lower_wick<range_hl*0.15:
            if c<(l+range_hl*0.3):
                results.append(Signal('Pinbar_Bear',i,'bear',lower=l,upper=h,price=c,strength=upper_wick/range_hl,confidence=0.55))
    return results

# ═══ SMC SETUPS ═══
def detect_smc_setups(signals, ohlcv):
    n=len(ohlcv); sigs=sorted(signals,key=lambda s:s.idx)
    sweeps_ssl=[s for s in sigs if s.type=='Sweep_SSL']
    sweeps_bsl=[s for s in sigs if s.type=='Sweep_BSL']
    choch_bull=[s for s in sigs if s.type=='CHOCH_Bull']
    choch_bear=[s for s in sigs if s.type=='CHOCH_Bear']
    demand=[s for s in sigs if s.type in('OB_Bull','FVG_Bull')]
    supply=[s for s in sigs if s.type in('OB_Bear','FVG_Bear')]
    setups=[]; atr=_calc_atr(ohlcv,14); seen=set()
    for sw in sweeps_ssl:
        sweep_bar=sw.idx; sweep_price=sw.price
        next_choch=None
        for ch in choch_bull:
            if ch.idx>sweep_bar and ch.idx<=sweep_bar+30: next_choch=ch; break
        if not next_choch: continue
        choch_bar=next_choch.idx
        demand_zones=[]
        for dz in demand:
            if dz.idx>=sweep_bar-20 and dz.idx<sweep_bar:
                if dz.lower<=sweep_price+atr*1.5: demand_zones.append(dz)
        if not demand_zones: continue
        for dz in demand_zones:
            key=(dz.idx,dz.type)
            if key in seen: continue; seen.add(key)
            setups.append({'direction':'long','demand_bar':dz.idx,'sweep_bar':sweep_bar,
                'sweep_price':sweep_price,'choch_bar':choch_bar,'entry_bar':dz.idx,
                'entry_type':dz.type,'entry_price':dz.price,'zone_lower':dz.lower,'zone_upper':dz.upper,
                'strength':(sw.strength+next_choch.strength+dz.strength)/3})
    return setups

# ═══════════════════════ MAIN ═══════════════════════
def detect_all_signals_v22(ohlcv: List[Dict], params: Dict = None) -> tuple:
    if params is None: params={}
    leg_size=params.get('leg_size',20)
    atr=_calc_atr(ohlcv,200)

    swings, swings_dict=detect_leg_swings(ohlcv,leg_size=leg_size)
    choch_bos=detect_choch_bos(ohlcv,swings,atr)
    ob_lux=detect_ob_luxalgo(ohlcv,swings,choch_bos)
    ob_smc=detect_ob_smc2026(ohlcv,swings)
    fvg=detect_fvg(ohlcv)
    ifvg=detect_ifvg(ohlcv,fvg)
    sweep=detect_sweep(ohlcv,swings,atr)
    mss=detect_mss(ohlcv,swings,atr)
    avg_price=sum(b['c'] for b in ohlcv[-100:])/min(100,len(ohlcv)) if len(ohlcv)>=20 else 100
    eql=detect_eql(ohlcv,swings,atr,avg_price)
    # Merge OB: LuxAlgo + SMC2026, dedup by bar
    ob_all=[]
    ob_seen=set()
    for s in sorted(ob_lux+ob_smc,key=lambda s:s.idx):
        if s.idx not in ob_seen: ob_all.append(s); ob_seen.add(s.idx)
    bpr=detect_bpr(fvg,ob_all)
    breaker=detect_breaker(ohlcv,ob_all)
    lv=detect_liquidity_void(ohlcv,atr)
    rb=detect_rejection(ohlcv,swings,atr)
    ote=detect_ote(ohlcv,swings,atr)
    po3=detect_po3(ohlcv,atr)
    pinbar=detect_pinbars(ohlcv)

    # Limit PO3 to top-5 most significant
    po3.sort(key=lambda s: -s.strength)
    all_sigs = fvg+ifvg+ob_all+choch_bos+sweep+mss+eql+bpr+breaker+lv+rb+ote+po3[:5]+pinbar
    all_sigs.sort(key=lambda s:s.idx)

    from collections import Counter
    type_counts=Counter(s.type for s in all_sigs)
    return all_sigs, {
        'total_signals':len(all_sigs),'type_counts':dict(type_counts),
        'swing_highs':len(swings_dict['highs']),'swing_lows':len(swings_dict['lows']),
        'swings':[{'bar':s.bar_idx,'price':round(s.price,2),'type':s.type,'label':s.label} for s in swings],
    }, swings, swings_dict

# Backward compat
detect_all_signals_v21=detect_all_signals_v22
detect_all_signals_v20=detect_all_signals_v22

if __name__=='__main__':
    import json,sys
    from pathlib import Path
    fp=Path('/root/.hermes/kline_cache/600519_SH_daily_300.json')
    if not fp.exists(): fp=Path('/root/.hermes/kline_cache/600519.SH_daily_300.json')
    if not fp.exists(): print("No data"); sys.exit(1)
    ohlcv=json.loads(fp.read_bytes())
    for b in ohlcv:
        if 't' not in b and 'date' in b: b['t']=str(b['date'])
        for k in ('o','h','l','c'): b[k]=float(b[k]) if k in b else 0
    sigs,stats,_,_=detect_all_signals_v22(ohlcv)
    print(f"V22: {stats['total_signals']} signals, {stats['swing_highs']}H+{stats['swing_lows']}L swings")
    for t,c in sorted(stats['type_counts'].items(),key=lambda x:-x[1]):
        print(f"  {t:25s}: {c:4d}")
