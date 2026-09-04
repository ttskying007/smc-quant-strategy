#!/usr/bin/env python3
"""
V18 SMC信号检测引擎 — Pine SMC 2026 Exact Alignment

关键修复 (vs V17):
1. OB: pivothigh(7,7) 摆动 + displacement 硬过滤(1.0) + 从swing+1扫描
2. CHOCH/BOS: pivothigh(5,5), 20bar间距, 零break_pct
3. FVG: 纯gap low>high[2], 无3同向K线过滤
4. Sweep: 必须突破摆动点+反转, 穿透≥max(ATR×0.2, 0.2%)
5. MSS: crossover(close, prior_pivot), 25bar间距
6. EQL: 仅相邻pivot比较, ATR×0.1阈值
7. BPR: bull/bear zone重叠检测
"""
import math, logging
from typing import List, Dict, Optional
from dataclasses import dataclass, field

log = logging.getLogger('smc_v18.signals')

@dataclass
class Signal:
    type: str
    idx: int
    direction: str
    price: float
    upper: float = 0.0
    lower: float = 0.0
    strength: float = 0.0
    confidence: float = 0.0
    timeframe: str = 'daily'
    confirmed_at: int = 0
    volume_ratio: float = 1.0
    grade: int = 1
    trend_aligned: bool = False
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            'type': self.type, 'idx': self.idx, 'direction': self.direction,
            'price': round(self.price, 4), 'upper': round(self.upper, 4),
            'lower': round(self.lower, 4), 'strength': round(self.strength, 2),
            'confidence': round(self.confidence, 3), 'timeframe': self.timeframe,
            'confirmed_at': self.confirmed_at, 'volume_ratio': round(self.volume_ratio, 2),
            'grade': self.grade, 'trend_aligned': self.trend_aligned,
            'metadata': self.metadata,
        }

# ═════════════════════════════════════════════════════════════════
# 0. ATR / Adaptive Thresholds
# ═════════════════════════════════════════════════════════════════

def calc_atr(ohlcv, length=14):
    n = min(length, len(ohlcv))
    trs = []
    for i in range(max(1, len(ohlcv) - n), len(ohlcv)):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 1.0

def calc_adaptive_thresholds(ohlcv: List[Dict]) -> Dict:
    if not ohlcv or len(ohlcv) < 20:
        return {'atr_pct': 2.0, 'atr_value': 0.01, 'atr_14': 0.01, 'atr_50': 0.01}
    closes = [b['c'] for b in ohlcv if b.get('c', 0) > 0]
    avg_close = sum(closes) / len(closes) if closes else 100
    atr14 = calc_atr(ohlcv, 14)
    atr50 = calc_atr(ohlcv, 50)
    return {
        'atr_pct': (atr14 / avg_close) * 100,
        'atr_value': atr14,
        'atr_14': atr14,
        'atr_50': atr50,
        'avg_price': avg_close,
    }

# ═════════════════════════════════════════════════════════════════
# 1. PIVOT SWING DETECTION — Pine exact: pivothigh(high, left, left)
# ═════════════════════════════════════════════════════════════════

def detect_pivot_swings(ohlcv: List[Dict], left: int = 5) -> Dict:
    """
    Pine equivalent: ta.pivothigh(high, left, left), ta.pivotlow(low, left, left)
    Returns swing at bar_index (the actual bar where pivot occurs, no delay).
    Pine reports at bar_index - left (historical), but we use current bar for compatibility.
    """
    n = len(ohlcv)
    highs = []
    lows = []
    
    for i in range(left, n - left):
        h = ohlcv[i]['h']
        l = ohlcv[i]['l']
        
        # Pivot high
        is_ph = True
        for j in range(i - left, i + left + 1):
            if j == i: continue
            if ohlcv[j]['h'] >= h:
                is_ph = False
                break
        if is_ph:
            highs.append({'bar_idx': i, 'price': h, 'type': 'H'})
        
        # Pivot low
        is_pl = True
        for j in range(i - left, i + left + 1):
            if j == i: continue
            if ohlcv[j]['l'] <= l:
                is_pl = False
                break
        if is_pl:
            lows.append({'bar_idx': i, 'price': l, 'type': 'L'})
    
    return {'highs': highs, 'lows': lows}

# ═════════════════════════════════════════════════════════════════
# 2. OB DETECTION — Pine SMC 2026 exact
# ═════════════════════════════════════════════════════════════════

def detect_ob_v18(ohlcv: List[Dict], ob_swing_length=7, ob_lookback=10,
                  ob_displacement_mult=1.0, min_strength=3.0,
                  adaptive=None) -> List[Signal]:
    """
    Pine SMC 2026 OB detection:
    - Uses pivothigh(high, ob_swing_length, ob_swing_length) for structure swings
    - Scan from swing+1 backwards: for i = ob_swing_length+1 to ob_swing_length+ob_lookback
    - Find first bearish candle (close<open for Bull OB)
    - Displacement: disp = swing_low - hist_low (> rng * ob_displacement_mult) — HARD filter
    - A-share adaptation: ob_displacement_mult=1.0 (Pine default 1.5 is for forex)
    """
    n = len(ohlcv)
    if n < ob_swing_length * 2:
        return []
    
    swings = detect_pivot_swings(ohlcv, left=ob_swing_length)
    atr = adaptive.get('atr_value', 1.0) if adaptive else 1.0
    avg_price = adaptive.get('avg_price', 100) if adaptive else 100
    
    signals = []
    
    # Bullish OB: from a swing_low, find bearish candle before bullish impulse
    for sl in swings['lows']:
        sl_bar = sl['bar_idx']
        sl_price = sl['price']
        
        # Pine: for i = ob_swing_length + 1 to ob_swing_length + ob_lookback
        # In Pine, close[i] is historical offset from bar_index
        # At bar_index = sl_bar, close[ob_swing_length+1] = bar at sl_bar - (ob_swing_length+1)
        # This scans from right after the swing going backwards
        
        found = False
        ob_bar = -1
        ob_top = 0.0
        ob_bot = 0.0
        
        for i in range(ob_swing_length + 1, ob_swing_length + ob_lookback + 1):
            if found: break
            idx = sl_bar - i
            if idx < 0: break
            
            bar = ohlcv[idx]
            if bar['c'] < bar['o']:  # Bearish candle (close < open)
                # Displacement: swing_low - bar_low (Pine line 450)
                disp = sl_price - bar['l']
                rng = bar['h'] - bar['l']
                
                if rng > 0 and disp > (rng * ob_displacement_mult):
                    ob_top = bar['h']
                    ob_bot = bar['l']
                    ob_bar = idx
                    found = True
        
        if found:
            zone_height = ob_top - ob_bot
            displacement = avg_price - ob_bot  # for scoring
            strength = min(10.0, (displacement / atr) * 2 + (zone_height / atr) * 1.5)
            
            if strength >= min_strength:
                signals.append(Signal(
                    type='OB_Bull', idx=ob_bar, direction='bull',
                    price=ob_bot, upper=ob_top, lower=ob_bot,
                    strength=round(strength, 2), confidence=0.7,
                    confirmed_at=sl_bar,
                    metadata={'swing_bar': sl_bar, 'swing_price': sl_price,
                              'displacement': round(disp, 4), 'displacement_mult': ob_displacement_mult}
                ))
    
    # Bearish OB: from a swing_high, find bullish candle before bearish impulse
    for sh in swings['highs']:
        sh_bar = sh['bar_idx']
        sh_price = sh['price']
        
        found = False
        ob_bar = -1
        ob_top = 0.0
        ob_bot = 0.0
        
        for i in range(ob_swing_length + 1, ob_swing_length + ob_lookback + 1):
            if found: break
            idx = sh_bar - i
            if idx < 0: break
            
            bar = ohlcv[idx]
            if bar['c'] > bar['o']:  # Bullish candle
                # Displacement: bar_high - swing_high (Pine line 516)
                disp = bar['h'] - sh_price
                rng = bar['h'] - bar['l']
                
                if rng > 0 and disp > (rng * ob_displacement_mult):
                    ob_top = bar['h']
                    ob_bot = bar['l']
                    ob_bar = idx
                    found = True
        
        if found:
            zone_height = ob_top - ob_bot
            displacement = ob_top - avg_price
            strength = min(10.0, (displacement / atr) * 2 + (zone_height / atr) * 1.5)
            
            if strength >= min_strength:
                signals.append(Signal(
                    type='OB_Bear', idx=ob_bar, direction='bear',
                    price=ob_top, upper=ob_top, lower=ob_bot,
                    strength=round(strength, 2), confidence=0.7,
                    confirmed_at=sh_bar,
                    metadata={'swing_bar': sh_bar, 'swing_price': sh_price,
                              'displacement': round(disp, 4), 'displacement_mult': ob_displacement_mult}
                ))
    
    return signals

# ═════════════════════════════════════════════════════════════════
# 3. CHOCH/BOS DETECTION — Pine exact
# ═════════════════════════════════════════════════════════════════

def detect_structure_v18(ohlcv: List[Dict], swing_length=5, min_spacing=20,
                          show_bos=True, show_choch=True) -> List[Signal]:
    """
    Pine SMC 2026 structure detection:
    - pivothigh/lowl(swing_length, swing_length) for swings
    - Simple state machine: swing_trend tracks +1(bull), -1(bear), 0(neutral)
    - close > last_swing_high: if trend==-1 → CHOCH, if trend==1 → BOS
    - Minimum 20-bar spacing between labels
    - NO break_pct threshold (Pine uses zero)
    """
    n = len(ohlcv)
    if n < swing_length * 2:
        return []
    
    swings = detect_pivot_swings(ohlcv, left=swing_length)
    all_swings = sorted(swings['highs'] + swings['lows'], key=lambda x: x['bar_idx'])
    
    if len(all_swings) < 3:
        return []
    
    signals = []
    
    # State machine variables
    swing_trend = 0  # +1=bull, -1=bear, 0=neutral
    last_swing_high = None
    last_swing_low = None
    last_swing_high_idx = None
    last_swing_low_idx = None
    last_label_bar = -999
    last_labeled_high = None
    last_labeled_low = None
    
    for sw in all_swings:
        idx = sw['bar_idx']
        price = sw['price']
        
        if sw['type'] == 'H':
            last_swing_high = price
            last_swing_high_idx = idx
        else:
            last_swing_low = price
            last_swing_low_idx = idx
    
    # Second pass: check breaks
    for i in range(swing_length, n):
        bar = ohlcv[i]
        close = bar['c']
        
        # Check bullish break
        if (last_swing_high is not None and close > last_swing_high 
            and i > last_label_bar + min_spacing):
            # Anti-duplicate
            if last_labeled_high is None or abs(last_swing_high - last_labeled_high) > 0.001:
                if swing_trend == -1 and show_choch:
                    signals.append(Signal(
                        type='CHOCH_Bull', idx=i, direction='bull',
                        price=last_swing_high, upper=close, lower=last_swing_high,
                        strength=7.0, confidence=0.85,
                        metadata={'swing_bar': last_swing_high_idx, 'swing_price': last_swing_high,
                                  'trend_before': 'bear'}
                    ))
                elif swing_trend == 1 and show_bos:
                    signals.append(Signal(
                        type='BOS_Bull', idx=i, direction='bull',
                        price=last_swing_high, upper=close, lower=last_swing_high,
                        strength=5.0, confidence=0.7,
                        metadata={'swing_bar': last_swing_high_idx, 'swing_price': last_swing_high,
                                  'trend_before': 'bull'}
                    ))
                elif swing_trend == 0 and show_bos:
                    signals.append(Signal(
                        type='BOS_Bull', idx=i, direction='bull',
                        price=last_swing_high, upper=close, lower=last_swing_high,
                        strength=5.0, confidence=0.7,
                        metadata={'swing_bar': last_swing_high_idx, 'swing_price': last_swing_high,
                                  'trend_before': 'neutral'}
                    ))
                last_label_bar = i
                last_labeled_high = last_swing_high
                swing_trend = 1
        
        # Check bearish break (else-if in Pine - no double label on same bar)
        elif (last_swing_low is not None and close < last_swing_low
              and i > last_label_bar + min_spacing):
            if last_labeled_low is None or abs(last_swing_low - last_labeled_low) > 0.001:
                if swing_trend == 1 and show_choch:
                    signals.append(Signal(
                        type='CHOCH_Bear', idx=i, direction='bear',
                        price=last_swing_low, upper=last_swing_low, lower=close,
                        strength=7.0, confidence=0.85,
                        metadata={'swing_bar': last_swing_low_idx, 'swing_price': last_swing_low,
                                  'trend_before': 'bull'}
                    ))
                elif swing_trend == -1 and show_bos:
                    signals.append(Signal(
                        type='BOS_Bear', idx=i, direction='bear',
                        price=last_swing_low, upper=last_swing_low, lower=close,
                        strength=5.0, confidence=0.7,
                        metadata={'swing_bar': last_swing_low_idx, 'swing_price': last_swing_low,
                                  'trend_before': 'bear'}
                    ))
                elif swing_trend == 0 and show_bos:
                    signals.append(Signal(
                        type='BOS_Bear', idx=i, direction='bear',
                        price=last_swing_low, upper=last_swing_low, lower=close,
                        strength=5.0, confidence=0.7,
                        metadata={'swing_bar': last_swing_low_idx, 'swing_price': last_swing_low,
                                  'trend_before': 'neutral'}
                    ))
                last_label_bar = i
                last_labeled_low = last_swing_low
                swing_trend = -1
    
    return signals

# ═════════════════════════════════════════════════════════════════
# 4. FVG DETECTION — Pine exact: pure gap
# ═════════════════════════════════════════════════════════════════

def detect_fvg_v18(ohlcv: List[Dict], fvg_atr_mult=0.5, min_strength=3.0,
                    adaptive=None) -> List[Signal]:
    """
    Pine SMC 2026 FVG detection:
    - Bullish: low > high[2] (current low > high of 2 bars ago)
    - Bearish: high < low[2]
    - Gap >= ATR * 0.5
    - NO 3-candle color filter (Pine doesn't have it)
    """
    n = len(ohlcv)
    if n < 3:
        return []
    
    atr = adaptive.get('atr_value', 1.0) if adaptive else 1.0
    signals = []
    
    for i in range(2, n):
        # Bullish FVG: low > high[2]
        if ohlcv[i]['l'] > ohlcv[i-2]['h']:
            gap_top = ohlcv[i]['l']
            gap_bot = ohlcv[i-2]['h']
            gap_size = gap_top - gap_bot
            
            if gap_size >= atr * fvg_atr_mult:
                strength = min(10.0, gap_size / atr * 3)
                if strength >= min_strength:
                    signals.append(Signal(
                        type='FVG_Bull', idx=i-1, direction='bull',
                        price=gap_bot, upper=gap_top, lower=gap_bot,
                        strength=round(strength, 2), confidence=0.75,
                        confirmed_at=i,
                        metadata={'gap_size': round(gap_size, 4)}
                    ))
        
        # Bearish FVG: high < low[2]
        if ohlcv[i]['h'] < ohlcv[i-2]['l']:
            gap_top = ohlcv[i-2]['l']
            gap_bot = ohlcv[i]['h']
            gap_size = gap_top - gap_bot
            
            if gap_size >= atr * fvg_atr_mult:
                strength = min(10.0, gap_size / atr * 3)
                if strength >= min_strength:
                    signals.append(Signal(
                        type='FVG_Bear', idx=i-1, direction='bear',
                        price=gap_top, upper=gap_top, lower=gap_bot,
                        strength=round(strength, 2), confidence=0.75,
                        confirmed_at=i,
                        metadata={'gap_size': round(gap_size, 4)}
                    ))
    
    return signals

# ═════════════════════════════════════════════════════════════════
# 5. SWEEP DETECTION — Must break swing + reverse
# ═════════════════════════════════════════════════════════════════

def detect_sweep_v18(ohlcv: List[Dict], adaptive=None, min_penetration_pct=0.2) -> List[Signal]:
    """
    ICT Sweep: price pierces a prior swing point (high or low), then closes back inside.
    Key requirement: MUST break the swing price + then reverse.
    """
    n = len(ohlcv)
    if n < 10:
        return []
    
    atr = adaptive.get('atr_value', 1.0) if adaptive else 1.0
    avg_price = adaptive.get('avg_price', 100) if adaptive else 100
    
    # Get swing points from pivothigh/pivotlow(5,5)
    swings = detect_pivot_swings(ohlcv, left=5)
    all_highs = {s['bar_idx']: s['price'] for s in swings['highs']}
    all_lows = {s['bar_idx']: s['price'] for s in swings['lows']}
    
    min_pen = max(atr * 0.2, avg_price * 0.002)
    signals = []
    
    for i in range(5, n):
        bar = ohlcv[i]
        
        # Check prior swing highs (BSL sweep - bear trap)
        for sh_idx, sh_price in all_highs.items():
            if sh_idx >= i - 30 and sh_idx < i:  # within 30 bars
                if bar['h'] > sh_price + min_pen:  # pierced above
                    if bar['c'] < sh_price:  # reversed back below
                        signals.append(Signal(
                            type='Sweep_BSL', idx=i, direction='bear',
                            price=sh_price,
                            strength=6.0, confidence=0.7,
                            metadata={'swept_level': sh_price, 'level_bar': sh_idx,
                                      'penetration': round(bar['h'] - sh_price, 4)}
                        ))
                        break
        
        # Check prior swing lows (SSL sweep - bull trap)
        if not any(s.idx == i for s in signals):  # don't double count
            for sl_idx, sl_price in all_lows.items():
                if sl_idx >= i - 30 and sl_idx < i:
                    if bar['l'] < sl_price - min_pen:  # pierced below
                        if bar['c'] > sl_price:  # reversed back above
                            signals.append(Signal(
                                type='Sweep_SSL', idx=i, direction='bull',
                                price=sl_price,
                                strength=6.0, confidence=0.7,
                                metadata={'swept_level': sl_price, 'level_bar': sl_idx,
                                          'penetration': round(sl_price - bar['l'], 4)}
                            ))
                            break
    
    return signals

# ═════════════════════════════════════════════════════════════════
# 6. MSS DETECTION — crossover(close, prior pivot)
# ═════════════════════════════════════════════════════════════════

def detect_mss_v18(ohlcv: List[Dict], min_spacing=25) -> List[Signal]:
    """
    Pine SMC 2026 MSS: close crosses above prior pivot high (or below prior pivot low).
    Simple, clean detection.
    """
    n = len(ohlcv)
    if n < 10:
        return []
    
    swings = detect_pivot_swings(ohlcv, left=3)  # MSS uses smaller swing (3,3)
    signals = []
    last_mss_bar = -999
    
    for i in range(5, n):
        close = ohlcv[i]['c']
        prev_close = ohlcv[i-1]['c']
        
        if i - last_mss_bar < min_spacing:
            continue
        
        # Check crossover above prior pivot high
        for sh in swings['highs']:
            if sh['bar_idx'] < i - 3 and sh['bar_idx'] >= i - 30:
                if prev_close <= sh['price'] and close > sh['price']:
                    signals.append(Signal(
                        type='MSS_Bull', idx=i, direction='bull',
                        price=sh['price'],
                        strength=4.0, confidence=0.6,
                        metadata={'pivot_bar': sh['bar_idx'], 'pivot_price': sh['price']}
                    ))
                    last_mss_bar = i
                    break
        
        # Check crossunder below prior pivot low
        for sl in swings['lows']:
            if sl['bar_idx'] < i - 3 and sl['bar_idx'] >= i - 30:
                if prev_close >= sl['price'] and close < sl['price']:
                    signals.append(Signal(
                        type='MSS_Bear', idx=i, direction='bear',
                        price=sl['price'],
                        strength=4.0, confidence=0.6,
                        metadata={'pivot_bar': sl['bar_idx'], 'pivot_price': sl['price']}
                    ))
                    last_mss_bar = i
                    break
    
    return signals

# ═════════════════════════════════════════════════════════════════
# 7. EQL DETECTION — Adjacent pivot lows only
# ═════════════════════════════════════════════════════════════════

def detect_eql_v18(ohlcv: List[Dict], adaptive=None) -> List[Signal]:
    """
    Pine SMC 2026 EQH/EQL: compare only ADJACENT pivot points.
    Threshold = ATR * 0.1 (much stricter than brute force).
    """
    n = len(ohlcv)
    if n < 8:
        return []
    
    atr = adaptive.get('atr_value', 1.0) if adaptive else 1.0
    swings = detect_pivot_swings(ohlcv, left=4)
    threshold = atr * 0.1
    
    signals = []
    
    # EQL: compare adjacent pivot lows
    if len(swings['lows']) >= 2:
        for i in range(1, len(swings['lows'])):
            prev = swings['lows'][i-1]
            curr = swings['lows'][i]
            if abs(curr['price'] - prev['price']) <= threshold:
                signals.append(Signal(
                    type='EQL_Low', idx=curr['bar_idx'], direction='neutral',
                    price=curr['price'],
                    upper=max(curr['price'], prev['price']),
                    lower=min(curr['price'], prev['price']),
                    strength=3.0, confidence=0.5,
                    metadata={'prev_bar': prev['bar_idx'], 'prev_price': prev['price']}
                ))
    
    # EQH: compare adjacent pivot highs
    if len(swings['highs']) >= 2:
        for i in range(1, len(swings['highs'])):
            prev = swings['highs'][i-1]
            curr = swings['highs'][i]
            if abs(curr['price'] - prev['price']) <= threshold:
                signals.append(Signal(
                    type='EQL_High', idx=curr['bar_idx'], direction='neutral',
                    price=curr['price'],
                    upper=max(curr['price'], prev['price']),
                    lower=min(curr['price'], prev['price']),
                    strength=3.0, confidence=0.5,
                    metadata={'prev_bar': prev['bar_idx'], 'prev_price': prev['price']}
                ))
    
    return signals

# ═════════════════════════════════════════════════════════════════
# 8. BPR DETECTION — Multi-zone overlap
# ═════════════════════════════════════════════════════════════════

def detect_bpr_v18(fvg_signals: List[Signal], ob_signals: List[Signal]) -> List[Signal]:
    """
    BPR = Balanced Price Range = bull zone AND bear zone overlap.
    Only real BPR where both sides agree on a price level.
    """
    signals = []
    
    bull_zones = []
    bear_zones = []
    
    for s in fvg_signals + ob_signals:
        if s.direction == 'bull':
            bull_zones.append((s.lower, s.upper, s.idx, s.type))
        elif s.direction == 'bear':
            bear_zones.append((s.lower, s.upper, s.idx, s.type))
    
    for bl, bu, bidx, btype in bull_zones:
        for rl, ru, ridx, rtype in bear_zones:
            overlap_low = max(bl, rl)
            overlap_high = min(bu, ru)
            if overlap_low < overlap_high:
                signals.append(Signal(
                    type='BPR', idx=max(bidx, ridx), direction='neutral',
                    price=(overlap_low + overlap_high) / 2,
                    upper=overlap_high, lower=overlap_low,
                    strength=5.0, confidence=0.65,
                    metadata={'bull_source': btype, 'bear_source': rtype}
                ))
    
    return signals

# ═════════════════════════════════════════════════════════════════
# 9. MAIN DETECTION FUNCTION
# ═════════════════════════════════════════════════════════════════

def detect_all_signals_v18(ohlcv: List[Dict], params: Dict = None) -> tuple:
    """
    Main entry point for V18 signal detection.
    Returns (list_of_signals, dict_of_stats)
    """
    if params is None:
        params = {}
    
    adaptive = calc_adaptive_thresholds(ohlcv)
    
    ob_swing_length = params.get('ob_swing_length', 5)  # A-share: 5 (Pine default 7 for forex)
    ob_lookback = params.get('ob_lookback', 15)  # A-share: wider scan window
    ob_displacement_mult = params.get('ob_displacement_mult', 0.7)  # A-share: smaller displacements
    min_strength = params.get('min_strength', 2.5)  # A-share: relaxed
    swing_length = params.get('swing_length', 5)
    structure_spacing = params.get('structure_spacing', 15)  # A-share: 15 (Pine default 20 for forex)
    fvg_atr_mult = params.get('fvg_atr_mult', 0.5)
    mss_spacing = params.get('mss_spacing', 20)  # A-share: 20
    
    all_signals = []
    
    # 1. FVG
    fvg = detect_fvg_v18(ohlcv, fvg_atr_mult=fvg_atr_mult, min_strength=min_strength, adaptive=adaptive)
    all_signals.extend(fvg)
    
    # 2. OB
    ob = detect_ob_v18(ohlcv, ob_swing_length=ob_swing_length, ob_lookback=ob_lookback,
                       ob_displacement_mult=ob_displacement_mult, min_strength=min_strength,
                       adaptive=adaptive)
    all_signals.extend(ob)
    
    # 3. CHOCH/BOS
    structure = detect_structure_v18(ohlcv, swing_length=swing_length, min_spacing=structure_spacing)
    all_signals.extend(structure)
    
    # 4. Sweep
    sweep = detect_sweep_v18(ohlcv, adaptive=adaptive)
    all_signals.extend(sweep)
    
    # 5. MSS
    mss = detect_mss_v18(ohlcv, min_spacing=mss_spacing)
    all_signals.extend(mss)
    
    # 6. EQL
    eql = detect_eql_v18(ohlcv, adaptive=adaptive)
    all_signals.extend(eql)
    
    # 7. BPR (depends on FVG + OB)
    bpr = detect_bpr_v18(fvg, ob)
    all_signals.extend(bpr)
    
    # Sort by index
    all_signals.sort(key=lambda s: s.idx)
    
    # Stats
    type_counts = {}
    for s in all_signals:
        t = s.type
        type_counts[t] = type_counts.get(t, 0) + 1
    
    stats = {
        'total_signals': len(all_signals),
        'type_counts': type_counts,
        'params': params,
        'adaptive': {k: round(v, 4) if isinstance(v, float) else v for k, v in adaptive.items()}
    }
    
    return all_signals, stats

# ═════════════════════════════════════════════════════════════════
# 10. SELF-TEST
# ═════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys, json
    sys.path.insert(0, '/root/.hermes/scripts')
    from v11.klines_daily import get_daily_kline
    
    # Test on 600519.SH
    print("Testing V18 on 600519.SH...")
    bars = get_daily_kline('600519.SH')
    if not bars:
        print("ERROR: Cannot get kline data")
        sys.exit(1)
    
    signals, stats = detect_all_signals_v18(bars)
    
    print(f"\n=== V18 Signal Counts for 600519.SH ===")
    print(f"Total bars: {len(bars)}")
    print(f"ATR: {stats['adaptive']['atr_pct']:.2f}%")
    print()
    for sig_type, count in sorted(stats['type_counts'].items()):
        print(f"  {sig_type}: {count}")
    print(f"  TOTAL: {stats['total_signals']}")
    
    # Show sample indices
    print("\n=== Sample signal indices ===")
    shown = {}
    for s in signals[:20]:
        t = s.type
        if t not in shown:
            shown[t] = []
        if len(shown[t]) < 3:
            shown[t].append(s.idx)
    
    for t, indices in shown.items():
        print(f"  {t}: bars {indices}")
