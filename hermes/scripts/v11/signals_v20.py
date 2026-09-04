#!/usr/bin/env python3
"""
V20 SMC信号引擎 — 全面诊断修复版

V19→V20 修复清单:
1. OB(SMC): strength阈值 2.0→1.0, displacement 0.6→0.25 (A股适用)
2. CHOCH/BOS: 去掉crossed标志, 每次检查最近未穿越摆动点
3. Sweep: min_pen降低, 窗口扩大到60根
4. EQL/EQH: 比较所有同类型pivot (非仅相邻), ATR自适应阈值
5. MSS: cooldown 12→5 bars
6. 序列窗口: ATR%自适应缩放
7. 函数重命名: detect_all_signals_v20
"""
import math, logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

log = logging.getLogger('smc_v19')

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

# ════════════════════════════════════════════
# 0. UTILITY: ATR calculation
# ════════════════════════════════════════════

def _calc_atr(ohlcv, length=14):
    n = min(length, len(ohlcv))
    trs = []
    for i in range(max(1,len(ohlcv)-n), len(ohlcv)):
        h,l,pc = ohlcv[i]['h'],ohlcv[i]['l'],ohlcv[i-1]['c']
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs)/len(trs) if trs else 1.0

# ════════════════════════════════════════════
# 1. LUXALGO LEG DETECTION — TRUE SWING POINTS
# ════════════════════════════════════════════

class SwingPoint:
    def __init__(self, bar_idx, price, ptype, label=''):
        self.bar_idx = bar_idx
        self.price = price
        self.type = ptype  # 'H' or 'L'
        self.label = label  # 'HH','HL','LH','LL'
        self.crossed = False

def detect_leg_swings(ohlcv, leg_size=20) -> Tuple[List[SwingPoint], Dict]:
    """
    LuxAlgo leg(): high[leg_size] > ta.highest(leg_size) → new bearish leg (swing high)
                   low[leg_size] < ta.lowest(leg_size) → new bullish leg (swing low)
    
    Returns list of confirmed SwingPoint objects with HH/HL/LL/LH labels.
    """
    n = len(ohlcv)
    if n < leg_size * 2:
        return [], {'highs': [], 'lows': []}
    
    # Track leg state
    leg = 0  # 0=neutral, 1=bullish leg, -1=bearish leg
    prev_leg = 0
    swings = []
    last_high = None
    last_low = None
    
    for i in range(leg_size, n):
        bar = ohlcv[i]
        # LuxAlgo: high[size] > ta.highest(size)
        # high[leg_size] = bar at i-leg_size
        # ta.highest(leg_size) = max of last leg_size bars (i-leg_size+1 to i)
        pivot_bar = i - leg_size
        pivot_high = ohlcv[pivot_bar]['h']
        pivot_low = ohlcv[pivot_bar]['l']
        
        recent_highs = [ohlcv[j]['h'] for j in range(pivot_bar+1, i+1)]
        recent_lows = [ohlcv[j]['l'] for j in range(pivot_bar+1, i+1)]
        
        if pivot_high > max(recent_highs):
            leg = -1  # bearish leg → swing high confirmed
        elif pivot_low < min(recent_lows):
            leg = 1   # bullish leg → swing low confirmed
        
        # New leg detected   
        if leg != 0 and leg != prev_leg:
            if leg == -1:  # New swing high at pivot_bar
                price = ohlcv[pivot_bar]['h']
                label = ''
                if last_high is not None:
                    label = 'HH' if price > last_high.price else 'LH'
                else:
                    label = 'HH'
                sp = SwingPoint(pivot_bar, price, 'H', label)
                sp.last_price = last_high.price if last_high else None
                last_high = sp
                swings.append(sp)
            else:  # New swing low
                price = ohlcv[pivot_bar]['l']
                label = ''
                if last_low is not None:
                    label = 'LL' if price < last_low.price else 'HL'
                else:
                    label = 'LL'
                sp = SwingPoint(pivot_bar, price, 'L', label)
                sp.last_price = last_low.price if last_low else None
                last_low = sp
                swings.append(sp)
        
        prev_leg = leg
    
    highs = [{'bar_idx': s.bar_idx, 'price': s.price, 'label': s.label} for s in swings if s.type == 'H']
    lows = [{'bar_idx': s.bar_idx, 'price': s.price, 'label': s.label} for s in swings if s.type == 'L']
    
    return swings, {'highs': highs, 'lows': lows}

# ════════════════════════════════════════════
# 2. CHOCH/BOS — LuxAlgo crossover/crossunder
# ════════════════════════════════════════════

def detect_choch_bos_v20(ohlcv, swings):
    """
    V20.1 CHOCH/BOS — 基于摆动点标签判断结构变化.

    SMC理论核心:
    - 上穿 LH (Lower High) → CHOCH_Bull (下降趋势反转)
    - 上穿 HH (Higher High) → BOS_Bull (上升趋势延续)
    - 下穿 HL (Higher Low) → CHOCH_Bear (上升趋势反转)
    - 下穿 LL (Lower Low) → BOS_Bear (下降趋势延续)

    去掉了 crossed/last_cross 等状态追踪, 纯基于标签的静态判断.
    每个摆动点只触发一次 (同bar+同swing去重).
    """
    n = len(ohlcv)
    signals = []
    # Track fired: per-swing + per-bar dedup
    fired_swings = set()
    
    for i in range(1, n):
        close = ohlcv[i]['c']
        prev_close = ohlcv[i-1]['c']
        bar_has_high_signal = False  # one high-triggered signal per bar
        bar_has_low_signal = False   # one low-triggered signal per bar
        
        # Check ALL past swing highs (not just the most recent)
        for sh in swings:
            if sh.type != 'H': continue
            if sh.bar_idx >= i: continue  # future swing
            if sh.bar_idx in fired_swings: continue
            if not sh.label: continue  # must have label
            if bar_has_high_signal: continue  # one per bar
            
            if prev_close <= sh.price and close > sh.price:
                # 根据标签判断 CHOCH 还是 BOS
                if sh.label == 'LH':
                    tag = 'CHOCH_Bull'
                elif sh.label == 'HH':
                    tag = 'BOS_Bull'
                else:
                    tag = 'BOS_Bull'  # fallback
                
                signals.append(Signal(
                    type=tag, idx=i, direction='bull',
                    price=sh.price, upper=close,
                    strength=7.0 if 'CHOCH' in tag else 5.0,
                    confidence=0.85 if 'CHOCH' in tag else 0.7,
                    metadata={'swing_bar': sh.bar_idx, 'swing_price': sh.price,
                              'swing_label': sh.label}
                ))
                fired_swings.add(sh.bar_idx)
                bar_has_high_signal = True
        
        # Check ALL past swing lows
        for sl in swings:
            if sl.type != 'L': continue
            if sl.bar_idx >= i: continue
            if sl.bar_idx in fired_swings: continue
            if not sl.label: continue
            if bar_has_low_signal: continue  # one per bar
            
            if prev_close >= sl.price and close < sl.price:
                if sl.label == 'HL':
                    tag = 'CHOCH_Bear'
                elif sl.label == 'LL':
                    tag = 'BOS_Bear'
                else:
                    tag = 'BOS_Bear'  # fallback
                
                signals.append(Signal(
                    type=tag, idx=i, direction='bear',
                    price=sl.price, lower=close,
                    strength=7.0 if 'CHOCH' in tag else 5.0,
                    confidence=0.85 if 'CHOCH' in tag else 0.7,
                    metadata={'swing_bar': sl.bar_idx, 'swing_price': sl.price,
                              'swing_label': sl.label}
                ))
                fired_swings.add(sl.bar_idx)
                bar_has_low_signal = True
    
    return signals

# ════════════════════════════════════════════
# 3. OB — LuxAlgo: store at CHOCH/BOS moment
# ════════════════════════════════════════════

def detect_ob_luxalgo(ohlcv, swings, choch_bos_signals):
    """
    LuxAlgo storeOrdeBlock():
    - On CHOCH/BOS bullish: find MIN low between pivot.barIndex and current bar_index
    - On CHOCH/BOS bearish: find MAX high between pivot.barIndex and current bar_index
    - That bar is the Order Block
    
    Also locate OBs at swing points (SMC 2026 approach for standalone detection).
    """
    signals = []
    
    for cs in choch_bos_signals:
        meta = cs.metadata
        pivot_bar = meta.get('swing_bar', cs.idx - 10)
        current_bar = cs.idx
        
        if 'Bull' in cs.type:
            # Bullish CHOCH/BOS: find lowest low between pivot and current bar
            best_bar = pivot_bar
            best_low = float('inf')
            for i in range(pivot_bar, min(current_bar + 1, len(ohlcv))):
                if ohlcv[i]['l'] < best_low:
                    best_low = ohlcv[i]['l']
                    best_bar = i
            if best_bar < len(ohlcv) and best_low < float('inf'):
                bar = ohlcv[best_bar]
                signals.append(Signal(
                    type='OB_Bull', idx=best_bar, direction='bull',
                    price=best_low, upper=bar['h'], lower=bar['l'],
                    strength=6.0, confidence=0.75,
                    confirmed_at=cs.idx,
                    metadata={'pivot_bar': pivot_bar, 'choch_bar': current_bar,
                              'method': 'luxalgo'}
                ))
        else:
            # Bearish CHOCH/BOS: find highest high between pivot and current bar
            best_bar = pivot_bar
            best_high = -float('inf')
            for i in range(pivot_bar, min(current_bar + 1, len(ohlcv))):
                if ohlcv[i]['h'] > best_high:
                    best_high = ohlcv[i]['h']
                    best_bar = i
            if best_bar < len(ohlcv):
                bar = ohlcv[best_bar]
                signals.append(Signal(
                    type='OB_Bear', idx=best_bar, direction='bear',
                    price=best_high, upper=bar['h'], lower=bar['l'],
                    strength=6.0, confidence=0.75,
                    confirmed_at=cs.idx,
                    metadata={'pivot_bar': pivot_bar, 'choch_bar': current_bar,
                              'method': 'luxalgo'}
                ))
    
    # Also do SMC 2026 standalone OB for swing points (without CHOCH/BOS)
    smc_obs = detect_ob_smc2026(ohlcv, swings)
    # Merge, dedup by bar index
    used_idx = set()
    for s in signals:
        used_idx.add((s.type, s.idx))
    for s in smc_obs:
        if (s.type, s.idx) not in used_idx:
            signals.append(s)
    
    return signals

def detect_ob_smc2026(ohlcv, swings):
    """SMC 2026 OB: from swing, scan backward for first opposite candle with displacement."""
    signals = []
    atr = _calc_atr(ohlcv, 14)
    avg_price = sum(b['c'] for b in ohlcv[-50:]) / 50 if len(ohlcv) >= 50 else 100
    
    for sp in swings:
        if sp.type == 'L':  # Swing low → Bullish OB
            sl_bar = sp.bar_idx
            sl_price = sp.price
            found = False
            for i in range(7, 18):
                idx = sl_bar - i
                if idx < 0: break
                bar = ohlcv[idx]
                if bar['c'] < bar['o']:  # Bearish candle before bullish impulse
                    disp = sl_price - bar['l']
                    rng = bar['h'] - bar['l']
                    if rng > 0 and disp > rng * 0.25:  # A-share adapted: 0.6→0.25
                        strength = min(10.0, disp/atr*2 + rng/atr*1.5)
                        if strength >= 1.0:  # A-share adapted: 2.0→1.0
                            signals.append(Signal(
                                type='OB_Bull', idx=idx, direction='bull',
                                price=bar['l'], upper=bar['h'], lower=bar['l'],
                                strength=round(strength,1), confidence=0.7,
                                confirmed_at=sl_bar,
                                metadata={'swing_bar': sl_bar, 'swing_price': sl_price,
                                          'swing_label': sp.label, 'displacement': round(disp,4)}
                            ))
                            found = True
                            break
        elif sp.type == 'H':  # Swing high → Bearish OB
            sh_bar = sp.bar_idx
            sh_price = sp.price
            found = False
            for i in range(7, 18):
                idx = sh_bar - i
                if idx < 0: break
                bar = ohlcv[idx]
                if bar['c'] > bar['o']:  # Bullish candle before bearish impulse
                    disp = bar['h'] - sh_price
                    rng = bar['h'] - bar['l']
                    if rng > 0 and disp > rng * 0.25:  # 0.6→0.25
                        strength = min(10.0, disp/atr*2 + rng/atr*1.5)
                        if strength >= 1.0:  # 2.0→1.0
                            signals.append(Signal(
                                type='OB_Bear', idx=idx, direction='bear',
                                price=bar['h'], upper=bar['h'], lower=bar['l'],
                                strength=round(strength,1), confidence=0.7,
                                confirmed_at=sh_bar,
                                metadata={'swing_bar': sh_bar, 'swing_price': sh_price,
                                          'swing_label': sp.label, 'displacement': round(disp,4)}
                            ))
                            found = True
                            break
    return signals

# ════════════════════════════════════════════
# 4. FVG — SMC 2026 pure gap
# ════════════════════════════════════════════

def detect_fvg_v19(ohlcv, atr_mult=0.5, min_strength=2.5):
    n = len(ohlcv)
    if n < 3: return []
    atr = _calc_atr(ohlcv, 14)
    signals = []
    for i in range(2, n):
        if ohlcv[i]['l'] > ohlcv[i-2]['h']:
            gap_top, gap_bot = ohlcv[i]['l'], ohlcv[i-2]['h']
            gap = gap_top - gap_bot
            if gap >= atr * atr_mult:
                strength = min(10.0, gap/atr*3)
                if strength >= min_strength:
                    signals.append(Signal(type='FVG_Bull', idx=i-1, direction='bull',
                        price=gap_bot, upper=gap_top, lower=gap_bot,
                        strength=round(strength,2), confidence=0.75, confirmed_at=i,
                        metadata={'gap_size': round(gap,4)}))
        if ohlcv[i]['h'] < ohlcv[i-2]['l']:
            gap_top, gap_bot = ohlcv[i-2]['l'], ohlcv[i]['h']
            gap = gap_top - gap_bot
            if gap >= atr * atr_mult:
                strength = min(10.0, gap/atr*3)
                if strength >= min_strength:
                    signals.append(Signal(type='FVG_Bear', idx=i-1, direction='bear',
                        price=gap_top, upper=gap_top, lower=gap_bot,
                        strength=round(strength,2), confidence=0.75, confirmed_at=i,
                        metadata={'gap_size': round(gap,4)}))
    return signals

# ════════════════════════════════════════════
# 5. SWEEP — ICT: break swing + reverse
# ════════════════════════════════════════════

def detect_sweep_v20(ohlcv, swings):
    """V20 Sweep: 放宽穿刺阈值, 扩大摆动点窗口到60根, 增加独立穿刺计数."""
    n = len(ohlcv)
    if n < 10: return []
    avg_price = sum(b['c'] for b in ohlcv[-50:])/50 if len(ohlcv)>=50 else 100
    atr = _calc_atr(ohlcv, 14)
    
    signals = []
    swing_highs = [(s.bar_idx, s.price) for s in swings if s.type == 'H']
    swing_lows = [(s.bar_idx, s.price) for s in swings if s.type == 'L']
    
    for i in range(5, n):
        bar = ohlcv[i]
        min_pen = max(atr*0.08, avg_price*0.0005)  # V20: 降低阈值
        
        # BSL sweep: pierces prior high then closes below (window 60→)
        for sh_idx, sh_price in swing_highs:
            if sh_idx >= i-60 and sh_idx < i and bar['h'] > sh_price + min_pen:
                if bar['c'] < sh_price:
                    signals.append(Signal(type='Sweep_BSL', idx=i, direction='bear',
                        price=sh_price, strength=6.0, confidence=0.7,
                        metadata={'swept_level': sh_price, 'level_bar': sh_idx}))
                    break
        
        # SSL sweep: pierces prior low then closes above
        for sl_idx, sl_price in swing_lows:
            if sl_idx >= i-60 and sl_idx < i and bar['l'] < sl_price - min_pen:
                if bar['c'] > sl_price:
                    signals.append(Signal(type='Sweep_SSL', idx=i, direction='bull',
                        price=sl_price, strength=6.0, confidence=0.7,
                        metadata={'swept_level': sl_price, 'level_bar': sl_idx}))
                    break
    return signals

# ════════════════════════════════════════════
# 6. MSS — LuxAlgo internal structure
# ════════════════════════════════════════════

def detect_mss_v20(ohlcv, swings):
    """V20 MSS: cooldown 5 bars (was 12), wider window 50 bars (was 40)."""
    n = len(ohlcv)
    if n < 10: return []
    
    signals = []
    highs = [(s.bar_idx, s.price) for s in swings if s.type == 'H']
    lows = [(s.bar_idx, s.price) for s in swings if s.type == 'L']
    last_mss = -999
    
    for i in range(5, n):
        if i - last_mss < 5: continue  # V20: 5 bars cooldown
        close = ohlcv[i]['c']
        prev_close = ohlcv[i-1]['c']
        
        for sh_idx, sh_price in highs:
            if sh_idx < i-3 and sh_idx >= i-50:  # V20: 50 bar window
                if prev_close <= sh_price and close > sh_price:
                    signals.append(Signal(type='MSS_Bull', idx=i, direction='bull',
                        price=sh_price, strength=4.0, confidence=0.6,
                        metadata={'pivot_bar': sh_idx, 'pivot_price': sh_price}))
                    last_mss = i
                    break
        
        for sl_idx, sl_price in lows:
            if sl_idx < i-3 and sl_idx >= i-50:
                if prev_close >= sl_price and close < sl_price:
                    signals.append(Signal(type='MSS_Bear', idx=i, direction='bear',
                        price=sl_price, strength=4.0, confidence=0.6,
                        metadata={'pivot_bar': sl_idx, 'pivot_price': sl_price}))
                    last_mss = i
                    break
    return signals

# ════════════════════════════════════════════
# 7. EQL/EQH — LuxAlgo adjacent pivot comparison
# ════════════════════════════════════════════

def detect_eql_v20(ohlcv, swings, atr_val=None, avg_price=None):
    """V20 EQL/EQH: 比较所有同类型pivot(非仅相邻), ATR自适应阈值."""
    if avg_price is None:
        avg_price = sum(b['c'] for b in ohlcv[-100:]) / min(100, len(ohlcv)) if len(ohlcv) >= 20 else 100
    if atr_val is None:
        atr_val = _calc_atr(ohlcv, 200)
    
    # V20: ATR自适应 — 高波动股用宽阈值, 低波动用窄阈值
    atr_pct = atr_val / avg_price if avg_price > 0 else 0.02
    threshold = max(avg_price * 0.003, atr_val * 0.5)  # 至少0.3%或0.5xATR
    
    signals = []
    highs = [s for s in swings if s.type == 'H']
    lows = [s for s in swings if s.type == 'L']
    
    # 比较所有high对 (非仅相邻)
    for i in range(len(highs)):
        for j in range(i+1, len(highs)):
            a, b = highs[i], highs[j]
            if abs(a.price - b.price) <= threshold:
                # 取后发生的bar
                use = b if b.bar_idx > a.bar_idx else a
                signals.append(Signal(type='EQH', idx=use.bar_idx, direction='neutral',
                    price=use.price, upper=max(a.price,b.price),
                    lower=min(a.price,b.price), strength=3.0, confidence=0.5,
                    metadata={'pivot_a': a.bar_idx, 'pivot_b': b.bar_idx, 'gap': abs(a.price-b.price)}))
    
    for i in range(len(lows)):
        for j in range(i+1, len(lows)):
            a, b = lows[i], lows[j]
            if abs(a.price - b.price) <= threshold:
                use = b if b.bar_idx > a.bar_idx else a
                signals.append(Signal(type='EQL', idx=use.bar_idx, direction='neutral',
                    price=use.price, upper=max(a.price,b.price),
                    lower=min(a.price,b.price), strength=3.0, confidence=0.5,
                    metadata={'pivot_a': a.bar_idx, 'pivot_b': b.bar_idx, 'gap': abs(a.price-b.price)}))
    return signals

# ════════════════════════════════════════════
# 8. BPR — Multi-zone overlap
# ════════════════════════════════════════════

def detect_bpr_v19(fvg_signals, ob_signals):
    signals = []
    bull_zones = [(s.lower, s.upper, s.idx) for s in fvg_signals+ob_signals if s.direction=='bull']
    bear_zones = [(s.lower, s.upper, s.idx) for s in fvg_signals+ob_signals if s.direction=='bear']
    
    added = set()
    all_bpr = []
    for bl, bu, bidx in bull_zones:
        for rl, ru, ridx in bear_zones:
            ol = max(bl, rl); oh = min(bu, ru)
            key = (round(ol,2), round(oh,2))
            if ol < oh and key not in added:
                added.add(key)
                all_bpr.append((max(bidx,ridx), ol, oh, (ol+oh)/2))
    
    # Limit to top-15 most recent (highest bar index) BPRs
    all_bpr.sort(key=lambda x: -x[0])
    for bidx, ol, oh, mid in all_bpr[:15]:
        signals.append(Signal(type='BPR', idx=bidx, direction='neutral',
            price=mid, upper=oh, lower=ol, strength=5.0, confidence=0.65))
    return signals

# ════════════════════════════════════════════
# 8b. PINBAR DETECTION (V20.1: SMC-standard, entry confirmation only)
# ════════════════════════════════════════════

def detect_pinbars_v20(ohlcv: List[Dict]) -> list:
    """SMC Pinbar: entry confirmation at PD Arrays (OB/FVG), NOT standalone signal.
    
    Pinbar is used to confirm entries at existing PD Array zones — it is NOT
    a standalone signal type. The caller should only trigger on pinbars that 
    appear near (within ~3 bars of) a known OB or FVG zone.
    
    Criteria:
    - Bull (Hammer): long lower wick > body*2.5, wick > range*0.6, 
      tiny upper wick < range*0.15, close in top 30% of range
    - Bear (Shooting Star): long upper wick > body*2.5, wick > range*0.6,
      tiny lower wick < range*0.15, close in bottom 30% of range
    """
    results = []
    for i in range(20, len(ohlcv)):
        b = ohlcv[i]; o, h, l, c = b['o'], b['h'], b['l'], b['c']
        if h == l: continue
        range_hl = h - l
        if range_hl == 0: continue
        
        body_abs = abs(c - o)
        lower_wick = min(o, c) - l
        upper_wick = h - max(o, c)
        
        # Bullish Hammer
        if lower_wick > body_abs * 2.5 and lower_wick > range_hl * 0.6 and upper_wick < range_hl * 0.15:
            if c > (h - range_hl * 0.3):
                results.append(Signal('Pinbar_Bull', i, 'bull', lower=l, upper=h, price=c,
                                      strength=lower_wick/range_hl, confidence=0.55))
        # Bearish Shooting Star
        elif upper_wick > body_abs * 2.5 and upper_wick > range_hl * 0.6 and lower_wick < range_hl * 0.15:
            if c < (l + range_hl * 0.3):
                results.append(Signal('Pinbar_Bear', i, 'bear', lower=l, upper=h, price=c,
                                      strength=upper_wick/range_hl, confidence=0.55))
    return results

# ════════════════════════════════════════════
# 9. MAIN DETECTION
# ════════════════════════════════════════════

def detect_all_signals_v20(ohlcv: List[Dict], params: Dict = None) -> tuple:
    """V20: 全面修复版信号引擎."""
    if params is None: params = {}
    
    leg_size = params.get('leg_size', 20)
    fvg_atr_mult = params.get('fvg_atr_mult', 0.5)
    min_strength = params.get('min_strength', 2.5)
    
    # 1. Swing points
    swings, swings_dict = detect_leg_swings(ohlcv, leg_size=leg_size)
    
    # 2. CHOCH/BOS (V20.1: 基于标签 LH→CHOCH_Bull, HL→CHOCH_Bear)
    choch_bos = detect_choch_bos_v20(ohlcv, swings)
    
    # 3. OB (LuxAlgo + SMC 2026)  — uses V20 choch_bos
    ob = detect_ob_luxalgo(ohlcv, swings, choch_bos)
    
    # 4. FVG
    fvg = detect_fvg_v19(ohlcv, atr_mult=fvg_atr_mult, min_strength=min_strength)
    
    # 5. Sweep (V20: relaxed)
    sweep = detect_sweep_v20(ohlcv, swings)
    
    # 6. MSS (V20: 5-bar cooldown)
    mss = detect_mss_v20(ohlcv, swings)
    
    # 7. EQL/EQH (V20: all-pivot + ATR-adaptive)
    atr_val = _calc_atr(ohlcv, 200)
    avg_price = sum(b['c'] for b in ohlcv[-100:]) / min(100, len(ohlcv))
    eql = detect_eql_v20(ohlcv, swings, atr_val=atr_val, avg_price=avg_price)
    
    # 8. BPR
    bpr = detect_bpr_v19(fvg, ob)
    
    # 8b. Pinbar (entry confirmation at PD Arrays, NOT standalone)
    pinbar = detect_pinbars_v20(ohlcv)
    
    all_sigs = fvg + ob + choch_bos + sweep + mss + eql + bpr + pinbar
    all_sigs.sort(key=lambda s: s.idx)
    
    type_counts = {}
    for s in all_sigs:
        type_counts[s.type] = type_counts.get(s.type, 0) + 1
    
    stats = {
        'total_signals': len(all_sigs),
        'type_counts': type_counts,
        'swing_highs': len(swings_dict['highs']),
        'swing_lows': len(swings_dict['lows']),
        'swings': [
            {'bar': s.bar_idx, 'price': round(s.price,2), 'type': s.type, 'label': s.label}
            for s in swings
        ],
        'params': params,
    }
    
    return all_sigs, stats, swings, swings_dict

# ════════════════════════════════════════════
# 10. SELF-TEST
# ════════════════════════════════════════════

if __name__ == '__main__':
    import json, sys
    sys.path.insert(0, '/root/.hermes/scripts')
    from pathlib import Path
    
    fpath = Path('/root/.hermes/kline_cache/600519_SH_daily_300.json')
    if not fpath.exists():
        print("No data"); sys.exit(1)
    
    ohlcv = json.loads(fpath.read_bytes())
    signals, stats, swings, _ = detect_all_signals_v19(ohlcv)
    
    print(f"=== V19: 600519.SH ({len(ohlcv)} bars) ===")
    print(f"Swing points: {stats['swing_highs']}H + {stats['swing_lows']}L = {stats['swing_highs']+stats['swing_lows']}")
    print(f"\nSwing labels:")
    for s in stats['swings']:
        print(f"  bar={s['bar']:3d} {s['type']}@{s['price']:>8.2f} [{s['label']}]")
    
    print(f"\nSignal counts:")
    for t, c in sorted(stats['type_counts'].items()):
        print(f"  {t}: {c}")
    print(f"  TOTAL: {stats['total_signals']}")
    
    # Sample signals
    print(f"\nSample signal indices:")
    shown = {}
    for s in signals:
        if s.type not in shown: shown[s.type] = []
        if len(shown[s.type]) < 3: shown[s.type].append(f"bar={s.idx} price={s.price:.2f}")
    for t, items in sorted(shown.items()):
        print(f"  {t}: {', '.join(items)}")


# ════════════════════════════════════════════
# 11. SIGNAL SEQUENCE DETECTION (V20: ATR自适应)
# ════════════════════════════════════════════

# Base patterns with window multipliers (scaled by ATR%)
# High ATR% (volatile stocks) → shorter windows
# Low ATR% (quiet stocks) → longer windows
_SEQUENCE_BASE = [
    # name, types, base_windows, atr_scale (higher=more sensitive to ATR)
    ('Sweep→CHOCH→FVG→OB', ['Sweep_SSL','CHOCH_Bull','FVG_Bull','OB_Bull'],  [3,4,4],  1.2),
    ('CHOCH→FVG→OB',       ['CHOCH_Bull','FVG_Bull','OB_Bull'],               [4,3],    1.0),
    ('Sweep→CHOCH→FVG',    ['Sweep_SSL','CHOCH_Bull','FVG_Bull'],             [3,4],    1.2),
    ('Sweep→FVG→OB',       ['Sweep_SSL','FVG_Bull','OB_Bull'],                [5,4],    1.0),
    ('Sweep→CHOCH→FVG→OB', ['Sweep_BSL','CHOCH_Bear','FVG_Bear','OB_Bear'],   [3,4,4],  1.2),
    ('CHOCH→FVG→OB',       ['CHOCH_Bear','FVG_Bear','OB_Bear'],               [4,3],    1.0),
    ('Sweep→CHOCH→FVG',    ['Sweep_BSL','CHOCH_Bear','FVG_Bear'],             [3,4],    1.2),
    ('Sweep→FVG→OB',       ['Sweep_BSL','FVG_Bear','OB_Bear'],                [5,4],    1.0),
    ('BOS→FVG',            ['BOS_Bull','FVG_Bull'],                           [3],      0.8),
    ('BOS→FVG',            ['BOS_Bear','FVG_Bear'],                           [3],      0.8),
    ('MSS→CHOCH',           ['MSS_Bull','CHOCH_Bull'],                        [3],      0.8),
    ('MSS→CHOCH',           ['MSS_Bear','CHOCH_Bear'],                        [3],      0.8),
    ('FVG+OB',              ['FVG_Bull','OB_Bull'],                           [2],      0.5),
    ('FVG+OB',              ['FVG_Bear','OB_Bear'],                           [2],      0.5),
    ('Sweep→FVG',           ['Sweep_SSL','FVG_Bull'],                         [5],      1.2),
    ('Sweep→FVG',           ['Sweep_BSL','FVG_Bear'],                         [5],      1.2),
    # V20新增: 更长链条和更多组合
    ('MSS→FVG→OB',          ['MSS_Bull','FVG_Bull','OB_Bull'],                [4,3],    0.8),
    ('MSS→FVG→OB',          ['MSS_Bear','FVG_Bear','OB_Bear'],                [4,3],    0.8),
    ('BOS→FVG→OB',          ['BOS_Bull','FVG_Bull','OB_Bull'],                [3,3],    0.8),
    ('BOS→FVG→OB',          ['BOS_Bear','FVG_Bear','OB_Bear'],                [3,3],    0.8),
    ('CHOCH→OB',            ['CHOCH_Bull','OB_Bull'],                         [4],      0.8),
    ('CHOCH→OB',            ['CHOCH_Bear','OB_Bear'],                         [4],      0.8),
]

def _build_sequences(atr_pct):
    """Build adapted sequence patterns based on ATR%."""
    # atr_pct = ATR / avg_price (e.g., 0.02 = 2%)
    # scale: atr_pct 1% → window×1.5, atr_pct 3% → window×0.7
    scale = max(0.5, min(2.0, 1.5 / max(atr_pct, 0.005)))
    patterns = []
    for name, types, base_win, atr_scale in _SEQUENCE_BASE:
        adj_scale = scale * atr_scale
        windows = [max(1, int(w * adj_scale)) for w in base_win]
        patterns.append({'name': name, 'types': types, 'bars': windows})
    return patterns

def detect_signal_sequences(signals, atr_pct=0.02):
    """Find SMC signal sequences in chronological order.
    
    Args:
        signals: list of Signal objects
        atr_pct: ATR as percentage of price (用于自适应窗口缩放)
    """
    sequences = []
    sigs = sorted(signals, key=lambda s: s.idx)
    patterns = _build_sequences(atr_pct)
    for pat in patterns:
        types = pat['types']
        windows = pat['bars']
        # Sliding window through all signals
        for i in range(len(sigs) - len(types) + 1):
            match = True
            bars = [sigs[i].idx]
            for j in range(len(types)):
                s = sigs[i+j]
                if s.type != types[j]:
                    match = False
                    break
                if j > 0 and s.idx - sigs[i+j-1].idx > windows[j-1]:
                    match = False
                    break
                bars.append(s.idx)
            if match:
                sequences.append({
                    'pattern': pat['name'],
                    'direction': 'bull' if 'Bull' in types[0] or 'SSL' in types[0] else 'bear',
                    'start_bar': sigs[i].idx,
                    'end_bar': sigs[i+len(types)-1].idx,
                    'signals': [{'type': sigs[i+k].type, 'bar': sigs[i+k].idx, 'price': round(sigs[i+k].price, 2)} for k in range(len(types))],
                    'has_entry': types[-1] in ('FVG_Bull','OB_Bull','FVG_Bear','OB_Bear')
                })
                break  # One match per pattern per start position
    
    return sequences

# ════════════════════════════════════════════
# 12. SMC SETUP DETECTION — 流动性→结构→POI
# ════════════════════════════════════════════

def detect_smc_setups(signals, ohlcv):
    """
    V20.2: 完整SMC入场Setup检测 — 时间顺序的流动性→结构→POI流程.
    
    Long Setup:
      SSL Sweep → CHOCH_Bull → Demand Zone (OB_Bull/FVG_Bull) → Entry at POI
    
    Short Setup:
      BSL Sweep → CHOCH_Bear → Supply Zone (OB_Bear/FVG_Bear) → Entry at POI
    
    返回: list of {entry_bar, entry_type, demand_zone, sweep_bar, choch_bar, ...}
    """
    n = len(ohlcv)
    sigs = sorted(signals, key=lambda s: s.idx)
    
    # Index by type
    sweeps_ssl = [s for s in sigs if s.type == 'Sweep_SSL']
    sweeps_bsl = [s for s in sigs if s.type == 'Sweep_BSL']
    choch_bull = [s for s in sigs if s.type == 'CHOCH_Bull']
    choch_bear = [s for s in sigs if s.type == 'CHOCH_Bear']
    demand = [s for s in sigs if s.type in ('OB_Bull', 'FVG_Bull')]
    supply = [s for s in sigs if s.type in ('OB_Bear', 'FVG_Bear')]
    
    setups = []
    atr = _calc_atr(ohlcv, 14)
    avg_price = sum(b['c'] for b in ohlcv[-50:]) / min(50, len(ohlcv)) if n >= 20 else 100
    
    # ── Long Setups: Demand Zone → SSL Sweep → CHOCH_Bull → POI Entry ──
    # Order: demand zone forms → price sweeps below it → CHOCH → retrace to demand = entry
    seen_entries = set()
    
    for sw in sweeps_ssl:
        sweep_bar = sw.idx
        sweep_price = sw.price
        
        # Find next CHOCH_Bull within 30 bars after sweep
        next_choch = None
        for ch in choch_bull:
            if ch.idx > sweep_bar and ch.idx <= sweep_bar + 30:
                next_choch = ch
                break
        if not next_choch:
            continue
        
        choch_bar = next_choch.idx
        
        # Demand zone: OB_Bull or FVG_Bull that formed BEFORE the sweep
        # (within 20 bars prior) — this is the zone that got swept through
        demand_zones = []
        for dz in demand:
            if dz.idx >= sweep_bar - 20 and dz.idx < sweep_bar:
                # Zone lower should be near or below the swept price
                if dz.lower <= sweep_price + atr * 1.5:
                    demand_zones.append(dz)
        
        if not demand_zones:
            continue
        
        # Entry: the demand zone itself IS the POI
        # After CHOCH, price should retrace to demand zone — we enter at demand zone
        for dz in demand_zones:
            key = (dz.idx, dz.type)
            if key in seen_entries: continue
            seen_entries.add(key)
            
            setups.append({
                'direction': 'long',
                'demand_bar': dz.idx,
                'sweep_bar': sweep_bar,
                'sweep_price': sweep_price,
                'choch_bar': choch_bar,
                'entry_bar': dz.idx,  # enter at demand zone (same bar, or next)
                'entry_type': dz.type,
                'entry_price': dz.price,
                'zone_lower': dz.lower,
                'zone_upper': dz.upper,
                'strength': (sw.strength + next_choch.strength + dz.strength) / 3,
            })
    
    # ── Short Setups: Supply Zone → BSL Sweep → CHOCH_Bear → POI Entry ──
    for sw in sweeps_bsl:
        sweep_bar = sw.idx
        sweep_price = sw.price
        
        next_choch = None
        for ch in choch_bear:
            if ch.idx > sweep_bar and ch.idx <= sweep_bar + 30:
                next_choch = ch
                break
        if not next_choch:
            continue
        
        choch_bar = next_choch.idx
        
        # Supply zone formed BEFORE the sweep
        supply_zones = []
        for sz in supply:
            if sz.idx >= sweep_bar - 20 and sz.idx < sweep_bar:
                if sz.upper >= sweep_price - atr * 1.5:
                    supply_zones.append(sz)
        
        if not supply_zones:
            continue
        
        for sz in supply_zones:
            key = (sz.idx, sz.type)
            if key in seen_entries: continue
            seen_entries.add(key)
            
            setups.append({
                'direction': 'short',
                'supply_bar': sz.idx,
                'sweep_bar': sweep_bar,
                'sweep_price': sweep_price,
                'choch_bar': choch_bar,
                'entry_bar': sz.idx,
                'entry_type': sz.type,
                'entry_price': sz.price,
                'zone_lower': sz.lower,
                'zone_upper': sz.upper,
                'strength': (sw.strength + next_choch.strength + sz.strength) / 3,
            })
    
    # Sort by entry bar
    setups.sort(key=lambda x: x['entry_bar'])
    return setups
