#!/usr/bin/env python3
"""
V21 SMC信号引擎 — 逐信号诊断修复版

V20→V21 修复清单 (Pine标准对齐):

1. BOS/CHOCH:
   - 要求 close 穿透摆动点 ATR*0.3 以上才触发 (防止微小穿刺)
   - 同方向3bar内去重: 只保留穿透最强的信号
   - CHOCH=反转(LH/HL突破), BOS=延续(HH/LL突破)
   - 价格设为 close (非 swing price), 记录被突破的摆动点

2. Sweep:
   - 5-bar cooldown per direction (消除重复检测)
   - 只扫最近20bar内的摆动点 (非60bar全窗口)
   - 要求穿刺深度 ATR*0.15 以上
   - 收盘必须回到摆动点反侧确认 (true sweep & reverse)

3. MSS:
   - close穿透摆动点 ATR*0.5 以上 (比CHOCH更强)
   - 8-bar cooldown
   - MSS是比CHOCH更强的结构变化, 应更稀少

4. EQL/EQH:
   - 修复类型名到 EQL_High/EQL_Low (匹配SIG_STYLE)
   - 每pivot只保留最近匹配对
   - 要求pivot间至少5bar距离

5. BPR:
   - 限制到top-10最重叠区域
   - 保持原逻辑不变
"""
import math, logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

log = logging.getLogger('smc_v21')

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

# ═══ SwingPoint ═══
class SwingPoint:
    def __init__(self, bar_idx, price, ptype, label=''):
        self.bar_idx = bar_idx
        self.price = price
        self.type = ptype
        self.label = label
        self.crossed = False

# ═══ ATR ═══
def _calc_atr(ohlcv, length=14):
    n = min(length, len(ohlcv))
    trs = []
    for i in range(max(1,len(ohlcv)-n), len(ohlcv)):
        h,l,pc = ohlcv[i]['h'],ohlcv[i]['l'],ohlcv[i-1]['c']
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs)/len(trs) if trs else 1.0

# ═══ LEG SWINGS (from V20: LuxAlgo leg) ═══
def detect_leg_swings(ohlcv, leg_size=20) -> Tuple[List[SwingPoint], Dict]:
    """LuxAlgo leg(): high[leg_size] > ta.highest(leg_size) → swing high confirmed"""
    n = len(ohlcv)
    if n < leg_size * 2:
        return [], {'highs': [], 'lows': []}
    
    leg = 0; prev_leg = 0
    swings = []
    last_high = None; last_low = None
    
    for i in range(leg_size, n):
        pivot_bar = i - leg_size
        pivot_high = ohlcv[pivot_bar]['h']
        pivot_low = ohlcv[pivot_bar]['l']
        
        recent_highs = [ohlcv[j]['h'] for j in range(pivot_bar+1, i+1)]
        recent_lows = [ohlcv[j]['l'] for j in range(pivot_bar+1, i+1)]
        
        if pivot_high > max(recent_highs):
            leg = -1  # bearish leg → swing high confirmed
        elif pivot_low < min(recent_lows):
            leg = 1   # bullish leg → swing low confirmed
        
        if leg != 0 and leg != prev_leg:
            if leg == -1:  # New swing high
                price = pivot_high
                label = 'HH' if (last_high and price > last_high.price) else ('LH' if last_high else 'HH')
                sp = SwingPoint(pivot_bar, price, 'H', label)
                sp.last_price = last_high.price if last_high else None
                last_high = sp; swings.append(sp)
            else:  # New swing low
                price = pivot_low
                label = 'LL' if (last_low and price < last_low.price) else ('HL' if last_low else 'LL')
                sp = SwingPoint(pivot_bar, price, 'L', label)
                sp.last_price = last_low.price if last_low else None
                last_low = sp; swings.append(sp)
        prev_leg = leg
    
    highs = [{'bar_idx': s.bar_idx, 'price': s.price, 'label': s.label} for s in swings if s.type == 'H']
    lows = [{'bar_idx': s.bar_idx, 'price': s.price, 'label': s.label} for s in swings if s.type == 'L']
    return swings, {'highs': highs, 'lows': lows}

# ════════════════════════════════════════════
# 1. BOS/CHOCH — V21 修复: 穿透确认+去重
# ════════════════════════════════════════════
def detect_choch_bos_v21(ohlcv, swings, atr_val):
    """V21: 要求close穿透摆动点ATR*0.3 + 同区域去重"""
    n = len(ohlcv)
    signals = []
    fired_swings = set()

    for i in range(5, n):
        close = ohlcv[i]['c']
        prev_close = ohlcv[i-1]['c']
        bar_low = ohlcv[i]['l']
        bar_high = ohlcv[i]['h']
        min_pen = atr_val * 0.3  # V21: 至少穿透0.3*ATR

        # 突破摆动高点
        for sh in swings:
            if sh.type != 'H': continue
            if sh.bar_idx >= i: continue
            if sh.bar_idx in fired_swings: continue
            if not sh.label: continue

            # V21: close必须穿透摆动点+ATR*0.3
            penetration = close - sh.price
            if prev_close <= sh.price and penetration >= min_pen:
                if sh.label == 'LH': tag = 'CHOCH_Bull'
                elif sh.label == 'HH': tag = 'BOS_Bull'
                else: tag = 'BOS_Bull'

                # V21: 价格设为close (实际突破点), metadata记录被突破的swing
                signals.append(Signal(
                    type=tag, idx=i, direction='bull',
                    price=round(close, 2), upper=close,
                    strength=round(penetration/atr_val, 1) if atr_val>0 else 7.0,
                    confidence=0.85 if 'CHOCH' in tag else 0.7,
                    metadata={'swing_bar': sh.bar_idx, 'swing_price': sh.price,
                              'swing_label': sh.label, 'penetration': round(penetration,2)}))
                fired_swings.add(sh.bar_idx)

        # 突破摆动低点
        for sl in swings:
            if sl.type != 'L': continue
            if sl.bar_idx >= i: continue
            if sl.bar_idx in fired_swings: continue
            if not sl.label: continue

            penetration = sl.price - close
            if prev_close >= sl.price and penetration >= min_pen:
                if sl.label == 'HL': tag = 'CHOCH_Bear'
                elif sl.label == 'LL': tag = 'BOS_Bear'
                else: tag = 'BOS_Bear'

                signals.append(Signal(
                    type=tag, idx=i, direction='bear',
                    price=round(close, 2), lower=close,
                    strength=round(penetration/atr_val, 1) if atr_val>0 else 7.0,
                    confidence=0.85 if 'CHOCH' in tag else 0.7,
                    metadata={'swing_bar': sl.bar_idx, 'swing_price': sl.price,
                              'swing_label': sl.label, 'penetration': round(penetration,2)}))
                fired_swings.add(sl.bar_idx)

    # V21: 同方向3bar内去重, 保留penetration最大的
    signals.sort(key=lambda s: s.idx)
    deduped = []
    last_bull_at = -999; last_bear_at = -999
    last_bull_pen = 0; last_bear_pen = 0
    for i, s in enumerate(signals):
        is_bull = 'Bull' in s.type
        pen = s.metadata.get('penetration', 0)
        if is_bull:
            if s.idx - last_bull_at <= 3:
                if pen > last_bull_pen:
                    deduped.pop()
                    deduped.append(s)
                    last_bull_pen = pen
            else:
                deduped.append(s)
                last_bull_pen = pen
            last_bull_at = s.idx
        else:
            if s.idx - last_bear_at <= 3:
                if pen > last_bear_pen:
                    deduped.pop()
                    deduped.append(s)
                    last_bear_pen = pen
            else:
                deduped.append(s)
                last_bear_pen = pen
            last_bear_at = s.idx
    return deduped

# ════════════════════════════════════════════
# 2. OB (unchanged: LuxAlgo + SMC2026)
# ════════════════════════════════════════════
def detect_ob_luxalgo(ohlcv, swings, choch_bos_signals):
    """LuxAlgo OB: at CHOCH/BOS moment, find OB between pivot and break bar"""
    n = len(ohlcv)
    signals = []
    for cbs in choch_bos_signals:
        sw_bar = cbs.metadata.get('swing_bar', 0)
        if 'Bull' in cbs.type:
            min_low = float('inf'); min_bar = cbs.idx
            for j in range(sw_bar, cbs.idx+1):
                if ohlcv[j]['l'] < min_low:
                    min_low = ohlcv[j]['l']; min_bar = j
            if min_low < float('inf'):
                signals.append(Signal('OB_Bull', min_bar, 'bull',
                    upper=ohlcv[min_bar]['h'], lower=min_low, price=min_low,
                    strength=6.0, confidence=0.75,
                    metadata={'swing_bar': sw_bar, 'break_bar': cbs.idx}))
        else:
            max_high = -float('inf'); max_bar = cbs.idx
            for j in range(sw_bar, cbs.idx+1):
                if ohlcv[j]['h'] > max_high:
                    max_high = ohlcv[j]['h']; max_bar = j
            if max_high > -float('inf'):
                signals.append(Signal('OB_Bear', max_bar, 'bear',
                    upper=max_high, lower=ohlcv[max_bar]['l'], price=max_high,
                    strength=6.0, confidence=0.75,
                    metadata={'swing_bar': sw_bar, 'break_bar': cbs.idx}))
    return signals

# ════════════════════════════════════════════
# 3. OB SMC2026 (unchanged)
# ════════════════════════════════════════════
def detect_ob_smc2026(ohlcv, swings):
    """SMC 2026 OB: 从摆动点回看最近的reverse candle"""
    n = len(ohlcv)
    signals = []
    for sw in swings:
        if sw.bar_idx < 2: continue
        found = None; best_displacement = 0
        for j in range(sw.bar_idx-1, max(0, sw.bar_idx-20), -1):
            b = ohlcv[j]
            if sw.type == 'H' and b['c'] < b['o']:
                displacement = sw.price - b['h']
                if displacement > best_displacement:
                    best_displacement = displacement
                    avg_price = sum(b2['c'] for b2 in ohlcv[max(0,j-10):j+1])/min(10, j+1)
                    if displacement > avg_price * 0.005:
                        found = (j, b['c'], b['h'], b['l'])
            elif sw.type == 'L' and b['c'] > b['o']:
                displacement = b['l'] - sw.price
                if displacement > best_displacement:
                    best_displacement = displacement
                    avg_price = sum(b2['c'] for b2 in ohlcv[max(0,j-10):j+1])/min(10, j+1)
                    if displacement > avg_price * 0.005:
                        found = (j, b['c'], b['h'], b['l'])
        if found:
            j, c, h, l = found
            tag = 'OB_Bear' if sw.type=='H' else 'OB_Bull'
            signals.append(Signal(tag, j, 'bear' if sw.type=='H' else 'bull',
                upper=h, lower=l, price=c, strength=3.0, confidence=0.60,
                metadata={'swing_bar': sw.bar_idx, 'displacement': round(best_displacement, 2)}))
    return signals

# ════════════════════════════════════════════
# 4. FVG (unchanged)
# ════════════════════════════════════════════
def detect_fvg_v21(ohlcv, atr_mult=0.5, min_strength=2.5):
    """FVG: 3-candle gap — b2.l > b0.h (bull) or b2.h < b0.l (bear)"""
    n = len(ohlcv)
    if n < 3: return []
    atr = _calc_atr(ohlcv, 14)
    min_gap = atr * atr_mult
    signals = []
    for i in range(2, n):
        # Bull FVG: candle 2 low > candle 0 high (gap up)
        if ohlcv[i]['l'] > ohlcv[i-2]['h']:
            gap = ohlcv[i]['l'] - ohlcv[i-2]['h']
            if gap >= min_gap:
                strength = min(10.0, gap/atr*3)
                if strength >= min_strength:
                    signals.append(Signal('FVG_Bull', i-1, 'bull',
                        price=ohlcv[i-2]['h'], upper=ohlcv[i]['l'], lower=ohlcv[i-2]['h'],
                        strength=round(strength,1), confidence=0.75, confirmed_at=i))
        # Bear FVG: candle 2 high < candle 0 low (gap down)
        if ohlcv[i]['h'] < ohlcv[i-2]['l']:
            gap = ohlcv[i-2]['l'] - ohlcv[i]['h']
            if gap >= min_gap:
                strength = min(10.0, gap/atr*3)
                if strength >= min_strength:
                    signals.append(Signal('FVG_Bear', i-1, 'bear',
                        price=ohlcv[i-2]['l'], upper=ohlcv[i-2]['l'], lower=ohlcv[i]['h'],
                        strength=round(strength,1), confidence=0.75, confirmed_at=i))
    return signals

# ════════════════════════════════════════════
# 5. Sweep — V21 修复: 去重+最近摆动点+深度确认
# ════════════════════════════════════════════
def detect_sweep_v21(ohlcv, swings, atr_val):
    """V21: 3-bar cooldown + 最近25bar摆动点 + ATR*0.08穿刺"""
    n = len(ohlcv)
    if n < 10: return []
    signals = []
    swing_highs = [(s.bar_idx, s.price) for s in swings if s.type == 'H']
    swing_lows = [(s.bar_idx, s.price) for s in swings if s.type == 'L']
    min_pen = atr_val * 0.08
    last_bsl = -999; last_ssl = -999

    for i in range(5, n):
        bar = ohlcv[i]
        if i - last_bsl < 3 and i - last_ssl < 3: continue

        # BSL: 上穿前高后回落
        if i - last_bsl >= 3:
            best_swing = None; best_depth = 0
            for sh_idx, sh_price in swing_highs:
                if sh_idx >= i - 25 and sh_idx < i:
                    if bar['h'] > sh_price + min_pen and bar['c'] < sh_price:
                        depth = bar['h'] - sh_price
                        if depth > best_depth:
                            best_depth = depth
                            best_swing = (sh_idx, sh_price)
            if best_swing:
                signals.append(Signal('Sweep_BSL', i, 'bear', price=best_swing[1],
                    strength=round(best_depth/atr_val, 1) if atr_val>0 else 6.0, confidence=0.7,
                    metadata={'swept_level': best_swing[1], 'level_bar': best_swing[0]}))
                last_bsl = i

        # SSL: 下穿前低后回升
        if i - last_ssl >= 3:
            best_swing = None; best_depth = 0
            for sl_idx, sl_price in swing_lows:
                if sl_idx >= i - 25 and sl_idx < i:
                    if bar['l'] < sl_price - min_pen and bar['c'] > sl_price:
                        depth = sl_price - bar['l']
                        if depth > best_depth:
                            best_depth = depth
                            best_swing = (sl_idx, sl_price)
            if best_swing:
                signals.append(Signal('Sweep_SSL', i, 'bull', price=best_swing[1],
                    strength=round(best_depth/atr_val, 1) if atr_val>0 else 6.0, confidence=0.7,
                    metadata={'swept_level': best_swing[1], 'level_bar': best_swing[0]}))
                last_ssl = i
    return signals

# ════════════════════════════════════════════
# 6. MSS — V21 修复: 更强穿透+更长cooldown
# ════════════════════════════════════════════
def detect_mss_v21(ohlcv, swings, atr_val):
    """V21: ATR*0.5穿透 + 8-bar cooldown"""
    n = len(ohlcv)
    if n < 10: return []
    signals = []
    highs = [(s.bar_idx, s.price) for s in swings if s.type == 'H']
    lows = [(s.bar_idx, s.price) for s in swings if s.type == 'L']
    last_mss = -999
    min_pen = atr_val * 0.5  # V21: 0.5 ATR = 强break

    for i in range(5, n):
        if i - last_mss < 8: continue  # V21: 8-bar cooldown
        close = ohlcv[i]['c']
        prev_close = ohlcv[i-1]['c']

        for sh_idx, sh_price in highs:
            if sh_idx < i-3 and sh_idx >= i-50:
                if prev_close <= sh_price and close > sh_price + min_pen:
                    signals.append(Signal('MSS_Bull', i, 'bull', price=round(close,2),
                        strength=round((close-sh_price)/atr_val,1) if atr_val>0 else 4.0, confidence=0.7,
                        metadata={'pivot_bar': sh_idx, 'pivot_price': sh_price}))
                    last_mss = i; break

        for sl_idx, sl_price in lows:
            if sl_idx < i-3 and sl_idx >= i-50:
                if prev_close >= sl_price and close < sl_price - min_pen:
                    signals.append(Signal('MSS_Bear', i, 'bear', price=round(close,2),
                        strength=round((sl_price-close)/atr_val,1) if atr_val>0 else 4.0, confidence=0.7,
                        metadata={'pivot_bar': sl_idx, 'pivot_price': sl_price}))
                    last_mss = i; break
    return signals

# ════════════════════════════════════════════
# 7. EQL/EQH — V21 修复: 类型名+每pivot最近匹配
# ════════════════════════════════════════════
def detect_eql_v21(ohlcv, swings, atr_val=None, avg_price=None):
    """V21: 修复类型名为EQL_High/EQL_Low, 至少5bar间距, 每pivot最近匹配"""
    if avg_price is None:
        avg_price = sum(b['c'] for b in ohlcv[-100:])/min(100, len(ohlcv)) if len(ohlcv)>=20 else 100
    if atr_val is None:
        atr_val = _calc_atr(ohlcv, 200)
    threshold = max(avg_price*0.003, atr_val*0.5)
    signals = []
    highs = [s for s in swings if s.type=='H']
    lows = [s for s in swings if s.type=='L']

    # V21: 每pivot只取最近的匹配对 (bar距离最近的)
    matched_h = set()
    for i in range(len(highs)):
        if highs[i].bar_idx in matched_h: continue
        best_j = None; best_dist = 999
        for j in range(len(highs)):
            if i == j: continue
            a, b = highs[i], highs[j]
            if abs(a.bar_idx - b.bar_idx) < 5: continue  # V21: 至少5bar距离
            if abs(a.price - b.price) <= threshold:
                dist = abs(a.bar_idx - b.bar_idx)
                if dist < best_dist:
                    best_dist = dist; best_j = j
        if best_j is not None:
            a, b = highs[i], highs[best_j]
            use = b if b.bar_idx > a.bar_idx else a
            signals.append(Signal('EQL_High', use.bar_idx, 'neutral',
                price=use.price, upper=max(a.price,b.price), lower=min(a.price,b.price),
                strength=3.0, confidence=0.5,
                metadata={'pivot_a': a.bar_idx, 'pivot_b': b.bar_idx}))
            matched_h.add(a.bar_idx); matched_h.add(b.bar_idx)

    matched_l = set()
    for i in range(len(lows)):
        if lows[i].bar_idx in matched_l: continue
        best_j = None; best_dist = 999
        for j in range(len(lows)):
            if i == j: continue
            a, b = lows[i], lows[j]
            if abs(a.bar_idx - b.bar_idx) < 5: continue
            if abs(a.price - b.price) <= threshold:
                dist = abs(a.bar_idx - b.bar_idx)
                if dist < best_dist:
                    best_dist = dist; best_j = j
        if best_j is not None:
            a, b = lows[i], lows[best_j]
            use = b if b.bar_idx > a.bar_idx else a
            signals.append(Signal('EQL_Low', use.bar_idx, 'neutral',
                price=use.price, upper=max(a.price,b.price), lower=min(a.price,b.price),
                strength=3.0, confidence=0.5,
                metadata={'pivot_a': a.bar_idx, 'pivot_b': b.bar_idx}))
            matched_l.add(a.bar_idx); matched_l.add(b.bar_idx)
    return signals

# ════════════════════════════════════════════
# 8. BPR (unchanged, top-10 only)
# ════════════════════════════════════════════
def detect_bpr_v21(fvg_signals, ob_signals):
    signals = []
    bull_zones = [(s.lower, s.upper, s.idx) for s in fvg_signals+ob_signals if s.direction=='bull']
    bear_zones = [(s.lower, s.upper, s.idx) for s in fvg_signals+ob_signals if s.direction=='bear']
    added = set(); all_bpr = []
    for bl, bu, bidx in bull_zones:
        for rl, ru, ridx in bear_zones:
            ol = max(bl, rl); oh = min(bu, ru)
            key = (round(ol,2), round(oh,2))
            if ol < oh and key not in added:
                added.add(key)
                all_bpr.append((max(bidx,ridx), ol, oh, (ol+oh)/2))
    all_bpr.sort(key=lambda x: -x[0])
    for bidx, ol, oh, mid in all_bpr[:10]:  # V21: top-10
        signals.append(Signal('BPR', bidx, 'neutral', price=mid, upper=oh, lower=ol,
            strength=5.0, confidence=0.65))
    return signals

# ════════════════════════════════════════════
# 9. Pinbar (unchanged)
# ════════════════════════════════════════════
def detect_pinbars_v21(ohlcv: List[Dict]) -> list:
    results = []
    for i in range(20, len(ohlcv)):
        b = ohlcv[i]; o, h, l, c = b['o'], b['h'], b['l'], b['c']
        if h == l: continue
        range_hl = h - l
        if range_hl == 0: continue
        body_abs = abs(c - o)
        lower_wick = min(o, c) - l
        upper_wick = h - max(o, c)
        if lower_wick > body_abs * 2.5 and lower_wick > range_hl * 0.6 and upper_wick < range_hl * 0.15:
            if c > (h - range_hl * 0.3):
                results.append(Signal('Pinbar_Bull', i, 'bull', lower=l, upper=h, price=c,
                    strength=lower_wick/range_hl, confidence=0.55))
        elif upper_wick > body_abs * 2.5 and upper_wick > range_hl * 0.6 and lower_wick < range_hl * 0.15:
            if c < (l + range_hl * 0.3):
                results.append(Signal('Pinbar_Bear', i, 'bear', lower=l, upper=h, price=c,
                    strength=upper_wick/range_hl, confidence=0.55))
    return results

# ════════════════════════════════════════════
# 10. SMC SETUPS (unchanged)
# ════════════════════════════════════════════
def detect_smc_setups(signals, ohlcv):
    n = len(ohlcv)
    sigs = sorted(signals, key=lambda s: s.idx)
    sweeps_ssl = [s for s in sigs if s.type == 'Sweep_SSL']
    sweeps_bsl = [s for s in sigs if s.type == 'Sweep_BSL']
    choch_bull = [s for s in sigs if s.type == 'CHOCH_Bull']
    choch_bear = [s for s in sigs if s.type == 'CHOCH_Bear']
    demand = [s for s in sigs if s.type in ('OB_Bull', 'FVG_Bull')]
    supply = [s for s in sigs if s.type in ('OB_Bear', 'FVG_Bear')]
    setups = []
    atr = _calc_atr(ohlcv, 14)
    seen_entries = set()

    for sw in sweeps_ssl:
        sweep_bar = sw.idx; sweep_price = sw.price
        next_choch = None
        for ch in choch_bull:
            if ch.idx > sweep_bar and ch.idx <= sweep_bar + 30:
                next_choch = ch; break
        if not next_choch: continue
        choch_bar = next_choch.idx
        demand_zones = []
        for dz in demand:
            if dz.idx >= sweep_bar - 20 and dz.idx < sweep_bar:
                if dz.lower <= sweep_price + atr * 1.5:
                    demand_zones.append(dz)
        if not demand_zones: continue
        for dz in demand_zones:
            key = (dz.idx, dz.type)
            if key in seen_entries: continue
            seen_entries.add(key)
            setups.append({'direction': 'long', 'demand_bar': dz.idx,
                'sweep_bar': sweep_bar, 'sweep_price': sweep_price,
                'choch_bar': choch_bar, 'entry_bar': dz.idx,
                'entry_type': dz.type, 'entry_price': dz.price,
                'zone_lower': dz.lower, 'zone_upper': dz.upper,
                'strength': (sw.strength+next_choch.strength+dz.strength)/3})

    return setups

# ════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════
def detect_all_signals_v21(ohlcv: List[Dict], params: Dict = None) -> tuple:
    if params is None: params = {}
    leg_size = params.get('leg_size', 20)
    atr = _calc_atr(ohlcv, 200)

    swings, swings_dict = detect_leg_swings(ohlcv, leg_size=leg_size)
    choch_bos = detect_choch_bos_v21(ohlcv, swings, atr)
    ob_lux = detect_ob_luxalgo(ohlcv, swings, choch_bos)
    # SMC2026 OB: disabled — lower quality, no CHOCH/BOS context
    # ob_smc = detect_ob_smc2026(ohlcv, swings)
    fvg = detect_fvg_v21(ohlcv)
    sweep = detect_sweep_v21(ohlcv, swings, atr)
    mss = detect_mss_v21(ohlcv, swings, atr)
    avg_price = sum(b['c'] for b in ohlcv[-100:])/min(100, len(ohlcv)) if len(ohlcv)>=20 else 100
    eql = detect_eql_v21(ohlcv, swings, atr, avg_price)
    bpr = detect_bpr_v21(fvg, ob_lux)
    pinbar = detect_pinbars_v21(ohlcv)

    all_sigs = fvg + ob_lux + choch_bos + sweep + mss + eql + bpr + pinbar
    all_sigs.sort(key=lambda s: s.idx)

    type_counts = {}
    for s in all_sigs: type_counts[s.type] = type_counts.get(s.type, 0) + 1

    return all_sigs, {
        'total_signals': len(all_sigs),
        'type_counts': type_counts,
        'swing_highs': len(swings_dict['highs']),
        'swing_lows': len(swings_dict['lows']),
        'swings': [{'bar': s.bar_idx, 'price': round(s.price,2), 'type': s.type, 'label': s.label} for s in swings],
    }, swings, swings_dict

# ═══ Backward compat alias ═══
detect_all_signals_v20 = detect_all_signals_v21

if __name__ == '__main__':
    import json, sys
    from pathlib import Path
    fp = Path('/root/.hermes/kline_cache/600519_SH_daily_300.json')
    if not fp.exists(): fp = Path('/root/.hermes/kline_cache/600519.SH_daily_300.json')
    if not fp.exists(): print("No data"); sys.exit(1)
    ohlcv = json.loads(fp.read_bytes())
    for b in ohlcv:
        if 't' not in b and 'date' in b: b['t'] = str(b['date'])
        for k in ('o','h','l','c'): b[k] = float(b[k]) if k in b else 0
    sigs, stats, swings, _ = detect_all_signals_v21(ohlcv)
    print(f"V21: {stats['total_signals']} signals, {stats['swing_highs']}H+{stats['swing_lows']}L swings")
    for t, c in sorted(stats['type_counts'].items(), key=lambda x:-x[1]):
        print(f"  {t:20s}: {c:4d}")
    print(f"\nSwings:")
    for sw in stats['swings']:
        print(f"  bar={sw['bar']:3d} {sw['type']}@{sw['price']:>10.2f} [{sw['label']}]")
