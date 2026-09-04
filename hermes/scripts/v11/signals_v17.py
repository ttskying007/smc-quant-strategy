#!/usr/bin/env python3
"""
V17 SMC信号检测引擎 — Pine Script精确对齐

逐行对齐三段Pine参考:
- SMC 2026: OB(swing-backward+displacement), CHOCH/BOS(state machine), FVG(pure gap), EQH/EQL
- LuxAlgo SMC: swing structure, internal structure, order blocks
- Waves Ultimate: pivothigh/pivotlow with right confirmation

V17关键修复 (vs V16):
1. 对称摆动确认: Pine ta.pivothigh(N,N) → left=right (之前不对称 right=2)
2. OB: 去掉多余impulse_check, 对齐Pine扫描范围, 加强度过滤
3. FVG: 加强度过滤 min_strength≥3.0
4. CHOCH/BOS: 去掉0.2% break_pct阈值(Pine无此限制), 对称摆动
5. EQL: 对称摆动 + consecutive优先 + ATR50回退
6. MSS: 对称内部摆动(left=3,right=3) + 15bar间距 + 0.3%穿透
7. Sweep: 对称摆动 + 合理穿透阈值 + 修正方向标注
8. BPR: top-5最强 + min宽度过滤
"""

import math, logging
from typing import List, Dict, Optional
from dataclasses import dataclass, field

log = logging.getLogger('smc_v17.signals')


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
        d = {
            'type': self.type, 'idx': self.idx, 'direction': self.direction,
            'price': round(self.price, 4), 'upper': round(self.upper, 4),
            'lower': round(self.lower, 4), 'strength': round(self.strength, 2),
            'confidence': round(self.confidence, 3), 'timeframe': self.timeframe,
            'confirmed_at': self.confirmed_at, 'volume_ratio': round(self.volume_ratio, 2),
            'grade': self.grade, 'trend_aligned': self.trend_aligned,
            'metadata': self.metadata,
        }
        return d


# ═══════════════════════════════════════════════════════════════════════
# 0. ATR / Adaptive Thresholds
# ═══════════════════════════════════════════════════════════════════════

def calc_adaptive_thresholds(ohlcv: List[Dict]) -> Dict:
    if not ohlcv or len(ohlcv) < 20:
        return {'atr_pct': 2.0, 'vol_median': 1000, 'avg_volume': 1000,
                'fvg_min_width': 0.001, 'atr_value': 0.01,
                'atr_200': 0.01, 'atr_50': 0.01, 'atr_14': 0.01}
    closes = [b['c'] for b in ohlcv if b.get('c', 0) > 0]
    vols = [b.get('v', b.get('vol', 0)) for b in ohlcv]
    avg_close = sum(closes) / len(closes) if closes else 100

    def _calc_atr(length):
        n = min(length, len(ohlcv))
        trs = []
        for i in range(max(1, len(ohlcv) - n), len(ohlcv)):
            h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        return sum(trs) / len(trs) if trs else 1

    atr14 = _calc_atr(14)
    atr50 = _calc_atr(50)
    atr200 = _calc_atr(200)

    atr_pct = atr14 / avg_close * 100 if avg_close > 0 else 2.0
    vol_median = sorted(vols)[len(vols)//2] if vols else 1000

    return {
        'atr_pct': max(0.3, min(10.0, atr_pct)),
        'atr_value': atr14,
        'atr_14': atr14,
        'atr_50': atr50,
        'atr_200': atr200,
        'vol_median': vol_median,
        'avg_volume': sum(vols) / len(vols) if vols else 1000,
        'fvg_min_width': atr14 * 0.5,
        'avg_close': avg_close,
    }


# ═══════════════════════════════════════════════════════════════════════
# 1. 摆动点检测 — Pine pivothigh/pivotlow 对称确认
# ═══════════════════════════════════════════════════════════════════════

def detect_consensus_swings(ohlcv, lookbacks=[5,8,10,12,15,20], min_confirmations=4):
    """
    多 lookback 共识摆动 — 只在 ≥min_confirmations 个 lookback 都检测到的才是真正结构点。
    过滤掉仅在单一 lookback 出现的数学 pivot（非真实 HH/HL/LL/LH）。
    """
    from collections import Counter
    
    all_highs = Counter()
    all_lows = Counter()
    swing_data = {}  # bar_idx -> swing dict (from the longest lookback)
    
    for lb in lookbacks:
        s = detect_swings_v17(ohlcv, left=lb, right=lb, atr_filter=False)
        for h in s['highs']:
            all_highs[h['bar_idx']] += 1
            if h['bar_idx'] not in swing_data or lb > swing_data[h['bar_idx']].get('_lb', 0):
                h['_lb'] = lb
                swing_data[h['bar_idx']] = h
        for l in s['lows']:
            all_lows[l['bar_idx']] += 1
            if l['bar_idx'] not in swing_data or lb > swing_data[l['bar_idx']].get('_lb', 0):
                l['_lb'] = lb
                swing_data[l['bar_idx']] = l
    
    highs = [swing_data[bar] for bar, cnt in all_highs.items() if cnt >= min_confirmations]
    lows = [swing_data[bar] for bar, cnt in all_lows.items() if cnt >= min_confirmations]
    
    highs.sort(key=lambda x: x['bar_idx'])
    lows.sort(key=lambda x: x['bar_idx'])
    
    swing_idxs = set()
    for h in highs: swing_idxs.add(h['idx'])
    for l in lows: swing_idxs.add(l['idx'])
    
    return {'highs': highs, 'lows': lows, 'swing_idxs': swing_idxs}


def detect_swings_v17(ohlcv: List[Dict], left: int = 5, right: int = 5,
                       atr_filter: bool = True, min_amp_atr: float = 0.3) -> Dict:
    """
    
    Pine语义:
    - ta.pivothigh(high, 5, 5): 在bar_index处非na，实际摆动点在bar_index-5
    - 需要5根右侧K线确认（全部high < pivot_high）
    
    V17: left=right 对称。摆动在 idx=i+right 处确认.
    bar_idx = i (实际摆动K线), confirmed_at = i+right
    """
    n = len(ohlcv)
    if n < left + right + 3:
        return {'highs': [], 'lows': [], 'swing_idxs': set()}

    atr_val = 0.0
    if atr_filter and n >= 15:
        trs = []
        for i in range(1, min(15, n)):
            h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr_val = sum(trs) / len(trs) if trs else 0

    raw_highs, raw_lows = [], []

    for i in range(left, n - right):
        bar = ohlcv[i]
        # Check pivot high: bar[i] is highest in [i-left, i+right]
        is_high = True
        for j in range(i - left, i + right + 1):
            if j == i or j < 0 or j >= n:
                continue
            if ohlcv[j]['h'] > bar['h']:
                is_high = False
                break
        if is_high:
            raw_highs.append({
                'idx': i + right,  # confirmed_at
                'bar_idx': i,       # actual pivot bar
                'price': bar['h']
            })

        # Check pivot low
        is_low = True
        for j in range(i - left, i + right + 1):
            if j == i or j < 0 or j >= n:
                continue
            if ohlcv[j]['l'] < bar['l']:
                is_low = False
                break
        if is_low:
            raw_lows.append({
                'idx': i + right,
                'bar_idx': i,
                'price': bar['l']
            })

    highs = _merge_consecutive(raw_highs, ohlcv, is_high=True)
    lows = _merge_consecutive(raw_lows, ohlcv, is_high=False)

    if atr_filter and atr_val > 0:
        min_amp = atr_val * min_amp_atr
        highs = _filter_tiny(highs, min_amp, ohlcv, is_high=True)
        lows = _filter_tiny(lows, min_amp, ohlcv, is_high=False)

    swing_idxs = set()
    for h in highs: swing_idxs.add(h['idx'])
    for lw in lows: swing_idxs.add(lw['idx'])

    return {'highs': highs, 'lows': lows, 'swing_idxs': swing_idxs}


def _merge_consecutive(swings, ohlcv, is_high):
    """合并3根K线内的同向摆动，取更极值"""
    if len(swings) < 2: return swings
    result = [swings[0]]
    for s in swings[1:]:
        last = result[-1]
        if s['bar_idx'] - last['bar_idx'] <= 3:
            if is_high:
                if s['price'] > last['price']: result[-1] = s
            else:
                if s['price'] < last['price']: result[-1] = s
        else:
            result.append(s)
    return result


def _filter_tiny(swings, min_amp, ohlcv, is_high):
    """过滤幅度过小的连续摆动（基于前一个摆动的幅度）"""
    if len(swings) < 2: return swings
    result = [swings[0]]
    for s in swings[1:]:
        prev = result[-1]
        amp = abs(s['price'] - prev['price'])
        if amp >= min_amp or s['bar_idx'] - prev['bar_idx'] > 30:
            result.append(s)
    return result


# ═══════════════════════════════════════════════════════════════════════
# 2. FVG — Pine exact + strength filter
# ═══════════════════════════════════════════════════════════════════════

def _calc_fvg_strength(gap_size, atr_val):
    """Pine SMC 2026: calculate_fvg_strength"""
    if atr_val <= 0: return 3.0
    gap_ratio = gap_size / atr_val
    if gap_ratio >= 1.5: return 8.0
    elif gap_ratio >= 1.0: return 6.0
    elif gap_ratio >= 0.75: return 4.5
    elif gap_ratio >= 0.5: return 3.0
    else: return 1.5


def detect_fvg_v17(ohlcv, adaptive=None, tf='daily',
                    min_strength=3.0, fvg_atr_mult=0.5):
    if adaptive is None: adaptive = calc_adaptive_thresholds(ohlcv)
    n = len(ohlcv)
    signals = []
    atr_val = adaptive.get('atr_value', 0.01)
    min_gap = atr_val * fvg_atr_mult

    for i in range(2, n):
        b0, b1, b2 = ohlcv[i], ohlcv[i-1], ohlcv[i-2]

        # Bullish FVG: low > high[2]
        if b0['l'] > b2['h']:
            gap = b0['l'] - b2['h']
            if gap >= min_gap:
                strength = _calc_fvg_strength(gap, atr_val)
                if strength < min_strength: continue

                all_bull = (b0['c'] > b0['o'] and b1['c'] > b1['o'] and b2['c'] > b2['o'])
                sig = Signal(type='FVG_Bull', idx=i-1, direction='bull',
                    price=(b2['h']+b0['l'])/2, upper=b0['l'], lower=b2['h'],
                    timeframe=tf, confirmed_at=i,
                    strength=strength,
                    confidence=min(0.9, 0.4 + gap/atr_val*0.15),
                    grade=3 if all_bull else 2,
                    trend_aligned=_check_trend(ohlcv, i, 'bull'),
                    metadata={'gap': round(gap, 4), 'all_same_dir': all_bull,
                              'strength_rating': round(strength, 1)})
                signals.append(sig)

        # Bearish FVG: high < low[2]
        if b0['h'] < b2['l']:
            gap = b2['l'] - b0['h']
            if gap >= min_gap:
                strength = _calc_fvg_strength(gap, atr_val)
                if strength < min_strength: continue

                all_bear = (b0['c'] < b0['o'] and b1['c'] < b1['o'] and b2['c'] < b2['o'])
                sig = Signal(type='FVG_Bear', idx=i-1, direction='bear',
                    price=(b2['l']+b0['h'])/2, upper=b2['l'], lower=b0['h'],
                    timeframe=tf, confirmed_at=i,
                    strength=strength,
                    confidence=min(0.9, 0.4 + gap/atr_val*0.15),
                    grade=3 if all_bear else 2,
                    trend_aligned=_check_trend(ohlcv, i, 'bear'),
                    metadata={'gap': round(gap, 4), 'all_same_dir': all_bear,
                              'strength_rating': round(strength, 1)})
                signals.append(sig)

    # Merge overlapping FVGs (same direction, within 3 bars)
    if signals:
        signals.sort(key=lambda s: s.idx)
        merged = [signals[0]]
        for s in signals[1:]:
            last = merged[-1]
            if abs(s.idx - last.idx) <= 3 and s.direction == last.direction:
                if s.strength > last.strength: merged[-1] = s
            else:
                merged.append(s)
        signals = merged

    return [s.to_dict() for s in signals]


def _check_trend(ohlcv, idx, direction, lookback=10):
    if idx < lookback: return False
    recent = ohlcv[max(0, idx-lookback):idx+1]
    if len(recent) < 5: return False
    avg_first = sum(b['c'] for b in recent[:3]) / 3
    avg_last = sum(b['c'] for b in recent[-3:]) / 3
    trend = (avg_last - avg_first) / avg_first * 100
    return trend > 0.3 if direction == 'bull' else trend < -0.3


# ═══════════════════════════════════════════════════════════════════════
# 3. OB — Pine exact: swing-backward, no impulse check, strength filter
# ═══════════════════════════════════════════════════════════════════════

def _calc_ob_strength(displacement, zone_height, atr_val):
    """Pine SMC 2026 strength rating — simplified (no session/age scoring)"""
    if atr_val <= 0: return 3.0
    # Displacement score
    disp_ratio = displacement / atr_val
    if disp_ratio >= 3.0: disp_score = 3.0
    elif disp_ratio >= 2.0: disp_score = 2.5
    elif disp_ratio >= 1.5: disp_score = 2.0
    elif disp_ratio >= 1.0: disp_score = 1.5
    else: disp_score = 1.0

    # Zone score
    zone_ratio = zone_height / atr_val
    if 0.5 <= zone_ratio <= 2.0: zone_score = 3.0
    elif 0.3 <= zone_ratio <= 3.0: zone_score = 2.0
    else: zone_score = 1.0

    # Base session score (no session info in daily data → use 1.5)
    sess_score = 1.5

    total = disp_score + sess_score + zone_score + 1.0  # +1.0 base
    return min(max(total, 0.0), 10.0)


def detect_ob_v17(ohlcv, swings=None, displacement_mult=1.5,
                   ob_swing_length=7, ob_lookback=10,
                   adaptive=None, tf='daily', min_strength=3.0):
    """
    SMC OB detection — finds the LAST opposite candle before a swing.
    
    Key principle: the OB is the candle CLOSEST to the swing in the opposite direction.
    Displacement is used for quality/strength scoring, NOT for hard filtering.
    
    1. Scan from swing-1 backward
    2. Stop at the FIRST matching candle (closest to swing)
    3. Use displacement ratio for strength rating only
    4. Filter by min_strength
    """
    if adaptive is None: adaptive = calc_adaptive_thresholds(ohlcv)
    if swings is None:
        swings = detect_swings_v17(ohlcv, left=ob_swing_length, right=ob_swing_length)

    n = len(ohlcv)
    signals = []
    vol_median = adaptive['vol_median']
    atr_val = adaptive.get('atr_value', 0.01)
    swing_highs = swings.get('highs', [])
    swing_lows = swings.get('lows', [])
    used_idx = set()

    # Bullish OB: scan backward from swing LOW
    for sl in swing_lows:
        sl_bar = sl['bar_idx']  # actual pivot bar (= bar_index - ob_swing_length in Pine)
        sl_price = sl['price']
        # Pine: for i = ob_swing_length+1 to ob_swing_length+ob_lookback
        # = close[8] to close[17] from bar_index
        # Relative to swing bar (bar_index-7): swing-1 to swing-10
        start_back = 1  # swing - 1
        end_back = ob_lookback  # swing - ob_lookback

        if sl_bar < end_back + 1: continue

        for back_offset in range(start_back, end_back + 1):
            back = sl_bar - back_offset
            if back < 2: break
            bar = ohlcv[back]
            if bar['c'] < bar['o']:  # bearish candle → bull OB
                if back in used_idx: break
                used_idx.add(back)
                
                rng = bar['h'] - bar['l']
                if rng <= 0: rng = 0.01
                # Standard SMC: OB is ABOVE the swing
                disp = bar['l'] - sl_price
                disp_ratio = disp / rng
                
                strength = _calc_ob_strength(disp, rng, atr_val)
                # Also factor in proximity: closer to swing = higher quality
                proximity_bonus = max(0, (ob_lookback - back_offset) / ob_lookback)  # 0-1
                strength += proximity_bonus * 1.5
                
                if strength < min_strength: break
                
                sig = Signal(type='OB_Bull', idx=back, direction='bull',
                    price=bar['l'], upper=bar['h'], lower=bar['l'],
                    timeframe=tf, confirmed_at=sl['idx'],
                    strength=strength,
                    confidence=min(0.9, 0.5 + disp/max(rng*3, 0.0001)),
                    volume_ratio=round(bar.get('v',0)/vol_median,2) if vol_median>0 else 1,
                    metadata={'method': 'first_match',
                        'swing_idx': sl['idx'], 'swing_bar': sl_bar,
                        'swing_price': round(sl_price, 4),
                        'displacement_ratio': round(disp_ratio, 2),
                        'strength_rating': round(strength, 1),
                        'bars_before_swing': back_offset,
                        'at_structure': True})
                signals.append(sig)
                break

    # Bearish OB: scan backward from swing HIGH
    for sh in swing_highs:
        sh_bar = sh['bar_idx']
        sh_price = sh['price']
        # Pine-correct: scan swing-1 to swing-ob_lookback
        start_back = 1
        end_back = ob_lookback

        if sh_bar < end_back + 1: continue

        for back_offset in range(start_back, end_back + 1):
            back = sh_bar - back_offset
            if back < 2: break
            bar = ohlcv[back]
            if bar['c'] > bar['o']:  # bullish candle → bear OB
                if back in used_idx: break
                used_idx.add(back)
                
                rng = bar['h'] - bar['l']
                if rng <= 0: rng = 0.01
                # Standard SMC: OB is BELOW the swing
                disp = sh_price - bar['h']
                disp_ratio = disp / rng
                
                strength = _calc_ob_strength(disp, rng, atr_val)
                proximity_bonus = max(0, (ob_lookback - back_offset) / ob_lookback)
                strength += proximity_bonus * 1.5
                
                if strength < min_strength: break
                
                sig = Signal(type='OB_Bear', idx=back, direction='bear',
                    price=bar['h'], upper=bar['h'], lower=bar['l'],
                    timeframe=tf, confirmed_at=sh['idx'],
                    strength=strength,
                    confidence=min(0.9, 0.5 + disp/max(rng*3, 0.0001)),
                    volume_ratio=round(bar.get('v',0)/vol_median,2) if vol_median>0 else 1,
                    metadata={'method': 'first_match',
                        'swing_idx': sh['idx'], 'swing_bar': sh_bar,
                        'swing_price': round(sh_price, 4),
                        'displacement_ratio': round(disp_ratio, 2),
                        'strength_rating': round(strength, 1),
                        'bars_before_swing': back_offset,
                        'at_structure': True})
                signals.append(sig)
                break

    signals.sort(key=lambda s: s.idx)
    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 4. CHOCH/BOS — Pine state machine with symmetric swings
# ═══════════════════════════════════════════════════════════════════════

def detect_structure_v17(ohlcv, swings=None, tf='daily',
                          swing_length=5, structure_spacing=12):
    """
    Simplified structure detection for zigzag swings.
    Zigzag swings have idx=bar_idx (no confirmation delay).
    """
    if swings is None:
        swings = detect_swings_v17(ohlcv, left=swing_length, right=swing_length)

    n = len(ohlcv)
    swing_highs = swings.get('highs', [])
    swing_lows = swings.get('lows', [])

    if not swing_highs and not swing_lows:
        return {'CHOCH_Bull':[],'CHOCH_Bear':[],'BOS_Bull':[],'BOS_Bear':[],'all':[]}

    # Build lookup by bar_idx (zigzag: idx==bar_idx)
    sh_by_bar = {h['bar_idx']: h for h in swing_highs}
    sl_by_bar = {l['bar_idx']: l for l in swing_lows}

    choch_signals, bos_signals = [], []
    last_swing_high = None
    last_swing_low = None
    last_swing_high_bar = 0
    last_swing_low_bar = 0
    last_label_bar = -999

    # Initialize trend from zigzag: newest swing direction
    if swing_highs and swing_lows:
        sh_newest = max(h['bar_idx'] for h in swing_highs)
        sl_newest = max(l['bar_idx'] for l in swing_lows)
        swing_trend = 1 if sh_newest > sl_newest else -1
    else:
        swing_trend = 0

    for i in range(n):
        bar = ohlcv[i]

        # Update last swing when we encounter a zigzag swing bar
        if i in sh_by_bar:
            last_swing_high = sh_by_bar[i]['price']
        if i in sl_by_bar:
            last_swing_low = sl_by_bar[i]['price']

        if last_swing_high is None or last_swing_low is None:
            continue
        if i - last_label_bar < structure_spacing:
            continue

        # Bullish break: close > newest swing high
        if bar['c'] > last_swing_high and last_swing_high > 0:
            break_pct = (bar['c'] - last_swing_high) / last_swing_high * 100
            if break_pct < 0.15: continue

            if swing_trend == -1:
                tag = 'CHOCH_Bull'; strength = 5.0 + min(3.0, break_pct)
            else:
                tag = 'BOS_Bull'; strength = 3.0 + min(2.0, break_pct)

            sig = Signal(type=tag, idx=i, direction='bull',
                price=bar['c'], upper=bar['h'], lower=last_swing_high,
                strength=strength, confidence=min(0.8, 0.3+break_pct*0.05),
                timeframe=tf, confirmed_at=i+1,
                metadata={'break_level':round(last_swing_high,4),
                    'break_pct':round(break_pct,2),
                    'prior_trend':'bear' if swing_trend==-1 else 'bull'})
            (choch_signals if 'CHOCH' in tag else bos_signals).append(sig)
            swing_trend = 1
            last_label_bar = i

        # Bearish break
        elif bar['c'] < last_swing_low and last_swing_low > 0:
            break_pct = (last_swing_low - bar['c']) / last_swing_low * 100
            if break_pct < 0.15: continue

            if swing_trend == 1:
                tag = 'CHOCH_Bear'; strength = 5.0 + min(3.0, break_pct)
            else:
                tag = 'BOS_Bear'; strength = 3.0 + min(2.0, break_pct)

            sig = Signal(type=tag, idx=i, direction='bear',
                price=bar['c'], upper=last_swing_low, lower=bar['l'],
                strength=strength, confidence=min(0.8, 0.3+break_pct*0.05),
                timeframe=tf, confirmed_at=i+1,
                metadata={'break_level':round(last_swing_low,4),
                    'break_pct':round(break_pct,2),
                    'prior_trend':'bull' if swing_trend==1 else 'bear'})
            (choch_signals if 'CHOCH' in tag else bos_signals).append(sig)
            swing_trend = -1
            last_label_bar = i

    all_struct = sorted(choch_signals + bos_signals, key=lambda s: s.idx)
    return {
        'CHOCH_Bull': [s.to_dict() for s in choch_signals if s.direction=='bull'],
        'CHOCH_Bear': [s.to_dict() for s in choch_signals if s.direction=='bear'],
        'BOS_Bull': [s.to_dict() for s in bos_signals if s.direction=='bull'],
        'BOS_Bear': [s.to_dict() for s in bos_signals if s.direction=='bear'],
        'all': [s.to_dict() for s in all_struct],
    }


# ═══════════════════════════════════════════════════════════════════════
# 5. MSS — Internal structure with symmetric swings
# ═══════════════════════════════════════════════════════════════════════

def detect_mss_v17(ohlcv, swings=None, tf='daily',
                    min_spacing=25, min_break_pct=0.5):
    if swings is None:
        swings = detect_swings_v17(ohlcv, left=3, right=3)

    n = len(ohlcv)
    signals = []
    internal_highs = swings.get('highs', [])
    internal_lows = swings.get('lows', [])

    if len(internal_highs) < 1 or len(internal_lows) < 1: return []

    hs_by_confirmed = {h['idx']: h for h in internal_highs}
    ls_by_confirmed = {lw['idx']: lw for lw in internal_lows}

    last_int_high, last_int_low = None, None
    last_label_bar = -999

    for i in range(n):
        bar = ohlcv[i]
        if i in hs_by_confirmed: last_int_high = hs_by_confirmed[i]['price']
        if i in ls_by_confirmed: last_int_low = ls_by_confirmed[i]['price']

        if last_int_high is None or last_int_low is None: continue
        if i - last_label_bar < min_spacing: continue

        if bar['c'] > last_int_high and last_int_high > 0:
            break_pct = (bar['c'] - last_int_high) / last_int_high * 100
            if break_pct < min_break_pct: continue
            sig = Signal(type='MSS_Bull', idx=i, direction='bull',
                price=bar['c'], upper=bar['h'], lower=last_int_high,
                strength=min(3.5, 1.0+break_pct),
                confidence=min(0.45, 0.2+break_pct/10),
                timeframe=tf, confirmed_at=i+1,
                metadata={'break_level':round(last_int_high,4),
                    'break_pct':round(break_pct,2), 'structure':'internal'})
            signals.append(sig)
            last_label_bar = i

        elif bar['c'] < last_int_low and last_int_low > 0:
            break_pct = (last_int_low - bar['c']) / last_int_low * 100
            if break_pct < min_break_pct: continue
            sig = Signal(type='MSS_Bear', idx=i, direction='bear',
                price=bar['c'], upper=last_int_low, lower=bar['l'],
                strength=min(3.5, 1.0+break_pct),
                confidence=min(0.45, 0.2+break_pct/10),
                timeframe=tf, confirmed_at=i+1,
                metadata={'break_level':round(last_int_low,4),
                    'break_pct':round(break_pct,2), 'structure':'internal'})
            signals.append(sig)
            last_label_bar = i

    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 6. Sweep — Liquidity sweep with symmetric swings + better naming
# ═══════════════════════════════════════════════════════════════════════

def detect_sweep_v17(ohlcv, swings=None, tf='daily'):
    """
    ICT liquidity sweep:
    - SSL sweep (price below swing low, close back above) → Bullish
    - BSL sweep (price above swing high, close back below) → Bearish
    Uses zigzag bar_idx (actual extreme bar, not delayed confirmation idx).
    """
    if swings is None:
        swings = detect_swings_v17(ohlcv, left=5, right=5)

    n = len(ohlcv)
    signals = []
    swing_highs = swings.get('highs', [])
    swing_lows = swings.get('lows', [])

    if not swing_highs and not swing_lows: return []

    adapt = calc_adaptive_thresholds(ohlcv)
    atr_val = adapt['atr_value']
    avg_price = adapt.get('avg_close', ohlcv[-1]['c'])
    min_penetration = max(atr_val * 0.15, avg_price * 0.001)  # relaxed
    min_wick_ratio = 0.3  # relaxed: smaller wicks count

    hs_by_bar, ls_by_bar = {}, {}
    for h in swing_highs:
        hs_by_bar.setdefault(h['bar_idx'], []).append(h)
    for lw in swing_lows:
        ls_by_bar.setdefault(lw['bar_idx'], []).append(lw)

    last_highs, last_lows = [], []

    for i in range(n):
        bar = ohlcv[i]
        for h in hs_by_bar.get(i, []): last_highs.append((i, h['price']))
        for lw in ls_by_bar.get(i, []): last_lows.append((i, lw['price']))

        # Keep only recent swings (30 bars)
        last_highs = [(idx, p) for idx, p in last_highs if i - idx <= 30]
        last_lows = [(idx, p) for idx, p in last_lows if i - idx <= 30]

        body = abs(bar['c'] - bar['o'])
        upper_wick = bar['h'] - max(bar['c'], bar['o'])
        lower_wick = min(bar['c'], bar['o']) - bar['l']

        # BSL Sweep → Bearish: price breaks above swing high then closes back below
        if len(last_highs) >= 1:
            for sh_idx, sh_price in last_highs:
                penetration = bar['h'] - sh_price
                if penetration > min_penetration and bar['c'] < sh_price:
                    sig = Signal(type='Sweep_BSL', idx=i, direction='bear',
                        price=bar['c'], upper=bar['h'], lower=min(bar['c'], bar['o']),
                        strength=4.0, confidence=0.55, timeframe=tf, confirmed_at=i,
                        metadata={'swept_level': round(sh_price, 4),
                            'swept_bar': sh_idx,
                            'penetration': round(penetration, 4),
                            'liquidity_type': 'BSL'})
                    signals.append(sig)
                    break

        # SSL Sweep → Bullish: price breaks below swing low then closes back above
        if len(last_lows) >= 1:
            for sl_idx, sl_price in last_lows:
                penetration = sl_price - bar['l']
                if penetration > min_penetration and bar['c'] > sl_price:
                    sig = Signal(type='Sweep_SSL', idx=i, direction='bull',
                        price=bar['c'], upper=max(bar['c'], bar['o']), lower=bar['l'],
                        strength=4.0, confidence=0.55, timeframe=tf, confirmed_at=i,
                        metadata={'swept_level': round(sl_price, 4),
                            'swept_bar': sl_idx,
                            'penetration': round(penetration, 4),
                            'liquidity_type': 'SSL'})
                    signals.append(sig)
                    break

    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 7. EQL/EQH — Pine exact: consecutive pivot comparison
# ═══════════════════════════════════════════════════════════════════════

def detect_eql_v17(ohlcv, swings=None, tolerance_pct=None,
                    atr_val=None, tf='daily'):
    """
    Pine SMC 2026 EQH/EQL exact:
    - Pivot: ta.pivothigh(eqhl_pivot_length, eqhl_pivot_length) = left=4, right=4
    - threshold = ATR200 * 0.1
    - Compare each new pivot with previousHigh
    - If max(ph, previousHigh) < min(ph, previousHigh) + threshold → EQH
    - Fallback: ATR50 * 0.15 for 300-bar limited data
    """
    if swings is None:
        swings = detect_swings_v17(ohlcv, left=4, right=4)
    adapt = calc_adaptive_thresholds(ohlcv)
    if atr_val is None: atr_val = adapt.get('atr_200', 0.01)
    if tolerance_pct is None: tolerance_pct = 0.1

    threshold = atr_val * tolerance_pct  # Pine exact
    signals = []
    swing_highs = swings.get('highs', [])
    swing_lows = swings.get('lows', [])
    seen = set()

    # Mode 1: consecutive pivots (Pine exact — compare with previous)
    previousHigh = None
    for sh in swing_highs:
        if previousHigh is not None:
            max_h = max(sh['price'], previousHigh)
            min_h = min(sh['price'], previousHigh)
            if max_h < min_h + threshold:
                level = max_h  # use the higher one for EQH
                key = ('EQH', round(level, 1))
                if key not in seen:
                    seen.add(key)
                    sig = Signal(type='EQH', idx=sh['idx'], direction='bear',
                        price=round(level, 2),
                        upper=round(level*1.005, 2), lower=round(level*0.995, 2),
                        strength=3.0, confidence=0.50, timeframe=tf, confirmed_at=sh['idx'],
                        metadata={'level': round(level, 4),
                            'threshold': round(threshold, 4),
                            'mode': 'consecutive',
                            'diff': round(abs(sh['price']-previousHigh), 4)})
                    signals.append(sig)
        previousHigh = sh['price']

    previousLow = None
    for sl in swing_lows:
        if previousLow is not None:
            max_l = max(sl['price'], previousLow)
            min_l = min(sl['price'], previousLow)
            if min_l > max_l - threshold:
                level = min_l
                key = ('EQL', round(level, 1))
                if key not in seen:
                    seen.add(key)
                    sig = Signal(type='EQL', idx=sl['idx'], direction='bull',
                        price=round(level, 2),
                        upper=round(level*1.005, 2), lower=round(level*0.995, 2),
                        strength=3.0, confidence=0.50, timeframe=tf, confirmed_at=sl['idx'],
                        metadata={'level': round(level, 4),
                            'threshold': round(threshold, 4),
                            'mode': 'consecutive',
                            'diff': round(abs(sl['price']-previousLow), 4)})
                    signals.append(sig)
        previousLow = sl['price']

    # Mode 2: relaxed with ATR50*0.15 for 300-bar data
    if not signals:
        atr50 = adapt.get('atr_50', atr_val)
        alt_threshold = atr50 * 0.15  # relaxed
        # nearby non-consecutive (up to 5 apart)
        for name, pivots, is_high in [('EQH', swing_highs, True), ('EQL', swing_lows, False)]:
            for i in range(len(pivots)):
                for j in range(i+1, min(i+6, len(pivots))):
                    pi, pj = pivots[i], pivots[j]
                    if abs(pj['price'] - pi['price']) < alt_threshold:
                        level = max(pj['price'], pi['price']) if is_high else min(pj['price'], pi['price'])
                        key = (name, round(level, 1))
                        if key not in seen:
                            seen.add(key)
                            typ = 'EQH' if is_high else 'EQL'
                            direc = 'bear' if is_high else 'bull'
                            sig = Signal(type=typ, idx=pj['idx'], direction=direc,
                                price=round(level, 2),
                                upper=round(level*1.005, 2) if not is_high else round(level, 2),
                                lower=round(level, 2) if not is_high else round(level*0.995, 2),
                                strength=2.5, confidence=0.35, timeframe=tf, confirmed_at=pj['idx'],
                                metadata={'level': round(level, 4),
                                    'threshold': round(alt_threshold, 4),
                                    'mode': 'nearby', 'gap': j-i})
                            signals.append(sig)

    # Mode 3: wide nearby with ATR50*0.30 for very sparse pivots
    if not signals and len(swing_highs) + len(swing_lows) > 4:
        atr50 = adapt.get('atr_50', atr_val)
        wide_threshold = atr50 * 0.30
        for name, pivots, is_high in [('EQH', swing_highs, True), ('EQL', swing_lows, False)]:
            for i in range(len(pivots)):
                for j in range(i+1, min(i+11, len(pivots))):  # up to 10 apart
                    pi, pj = pivots[i], pivots[j]
                    if abs(pj['price'] - pi['price']) < wide_threshold:
                        level = max(pj['price'], pi['price']) if is_high else min(pj['price'], pi['price'])
                        key = (name, round(level, 1))
                        if key not in seen:
                            seen.add(key)
                            typ = 'EQH' if is_high else 'EQL'
                            direc = 'bear' if is_high else 'bull'
                            sig = Signal(type=typ, idx=pj['idx'], direction=direc,
                                price=round(level, 2),
                                upper=round(level*1.005, 2) if not is_high else round(level, 2),
                                lower=round(level, 2) if not is_high else round(level*0.995, 2),
                                strength=2.0, confidence=0.3, timeframe=tf, confirmed_at=pj['idx'],
                                metadata={'level': round(level, 4),
                                    'threshold': round(wide_threshold, 4),
                                    'mode': 'wide', 'gap': j-i})
                            signals.append(sig)

    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 8. BPR — Top-N strongest overlaps
# ═══════════════════════════════════════════════════════════════════════

def detect_bpr_v17(ohlcv, fvg_signals=None, ob_signals=None, tf='daily'):
    adapt = calc_adaptive_thresholds(ohlcv)
    atr_val = adapt['atr_value']
    min_zone_width = atr_val * 0.3

    bull_zones, bear_zones = [], []
    for lst in (fvg_signals or []):
        up = lst.get('upper', 0)
        lo = lst.get('lower', 0)
        if up <= 0 or lo <= 0: continue
        entry = {'up': up, 'lo': lo, 'idx': lst.get('idx', 0),
                 'strength': lst.get('strength', 2), 'source': 'FVG'}
        if 'Bull' in lst.get('type', ''): bull_zones.append(entry)
        elif 'Bear' in lst.get('type', ''): bear_zones.append(entry)

    for lst in (ob_signals or []):
        up = lst.get('upper', 0)
        lo = lst.get('lower', 0)
        if up <= 0 or lo <= 0: continue
        entry = {'up': up, 'lo': lo, 'idx': lst.get('idx', 0),
                 'strength': lst.get('strength', 2), 'source': 'OB'}
        if 'Bull' in lst.get('type', ''): bull_zones.append(entry)
        elif 'Bear' in lst.get('type', ''): bear_zones.append(entry)

    if len(bull_zones) < 1 or len(bear_zones) < 1: return []

    overlaps = []
    seen = set()

    for bz in bull_zones:
        for brz in bear_zones:
            if bz['up'] > brz['lo'] and bz['lo'] < brz['up']:
                oh = min(bz['up'], brz['up'])
                ol = max(bz['lo'], brz['lo'])
                if oh - ol < min_zone_width: continue
                if oh <= ol: continue
                key = (round(oh, 2), round(ol, 2))
                if key in seen: continue
                seen.add(key)
                total_str = bz.get('strength', 2) + brz.get('strength', 2)
                overlaps.append({
                    'idx': max(bz['idx'], brz['idx']),
                    'oh': oh, 'ol': ol,
                    'strength': total_str,
                })

    overlaps.sort(key=lambda x: -x['strength'])
    signals = []
    for ov in overlaps[:5]:
        sig = Signal(type='BPR', idx=ov['idx'], direction='neutral',
            price=(ov['oh']+ov['ol'])/2, upper=ov['oh'], lower=ov['ol'],
            strength=min(8.0, ov['strength']),
            confidence=min(0.7, 0.3+(ov['oh']-ov['ol'])/max(ov['oh'],0.01)*5),
            timeframe=tf, confirmed_at=ov['idx'],
            metadata={'overlap_high':round(ov['oh'],4),'overlap_low':round(ov['ol'],4),
                'sources':'fvg+ob'})
        signals.append(sig)

    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 9. IFVG
# ═══════════════════════════════════════════════════════════════════════

def detect_ifvg_v17(ohlcv, adaptive=None, tf='daily'):
    if adaptive is None: adaptive = calc_adaptive_thresholds(ohlcv)
    n = len(ohlcv)
    signals = []
    atr_val = adaptive.get('atr_value', 0.01)

    for i in range(1, n - 2):
        c1, c2 = ohlcv[i], ohlcv[i + 1]
        if c1['h'] < c2['l']:
            gap = c2['l'] - c1['h']
            if gap >= atr_val * 0.3:
                sig = Signal(type='IFVG_Bull', idx=i, direction='bull',
                    price=((c1['h']+c1['l'])/2+(c2['h']+c2['l'])/2)/2,
                    upper=c2['l'], lower=c1['h'],
                    strength=2.0, confidence=0.3, timeframe=tf, confirmed_at=i+1,
                    metadata={'gap': round(gap, 4)})
                signals.append(sig)
        elif c1['l'] > c2['h']:
            gap = c1['l'] - c2['h']
            if gap >= atr_val * 0.3:
                sig = Signal(type='IFVG_Bear', idx=i, direction='bear',
                    price=((c1['h']+c1['l'])/2+(c2['h']+c2['l'])/2)/2,
                    upper=c1['l'], lower=c2['h'],
                    strength=2.0, confidence=0.3, timeframe=tf, confirmed_at=i+1,
                    metadata={'gap': round(gap, 4)})
                signals.append(sig)
    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 10. 统一入口
# ═══════════════════════════════════════════════════════════════════════

def detect_all_signals_v17(ohlcv, params=None, adaptive=None, tf='daily'):
    if params is None: params = {}
    if adaptive is None: adaptive = calc_adaptive_thresholds(ohlcv)

    swing_length = params.get('swing_length', 5)
    structure_swing_length = params.get('structure_swing_length', 10)  # longer for major structure
    ob_swing_length = params.get('ob_swing_length', 7)
    ob_displacement_mult = params.get('ob_displacement_mult', 1.5)
    ob_lookback = params.get('ob_lookback', 10)
    min_strength = params.get('min_strength', 3.0)
    fvg_atr_mult = params.get('fvg_atr_mult', 0.5)
    structure_spacing = params.get('structure_spacing', 15)  # allow more frequent breaks
    eqhl_pivot_length = params.get('eqhl_pivot_length', 4)
    eqhl_threshold = params.get('eqhl_threshold', 0.1)

    # Structure swings: zigzag reversal-based (true HH/HL/LL/LH from price reversals)
    from zigzag_swings import detect_zigzag_swings
    structure_swings = detect_zigzag_swings(ohlcv, reversal_pct=1.5)
    swings = detect_swings_v17(ohlcv, left=swing_length, right=swing_length)  # for Sweep reference
    internal_swings = detect_swings_v17(ohlcv, left=3, right=3)
    eql_swings = detect_swings_v17(ohlcv, left=eqhl_pivot_length, right=eqhl_pivot_length)

    # 1. FVG
    fvg_signals = detect_fvg_v17(ohlcv, adaptive=adaptive, tf=tf,
                                  min_strength=min_strength, fvg_atr_mult=fvg_atr_mult)

    # 2. OB (uses consensus swings for structure-quality OB positioning)
    ob_signals = detect_ob_v17(ohlcv, swings=structure_swings,
        displacement_mult=ob_displacement_mult,
        ob_swing_length=ob_swing_length,
        ob_lookback=ob_lookback,
        adaptive=adaptive, tf=tf, min_strength=min_strength)

    # 3. Structure CHOCH/BOS (uses LONGER structure_swings for major structure only)
    structure = detect_structure_v17(ohlcv, swings=structure_swings, tf=tf,
                                      swing_length=structure_swing_length,
                                      structure_spacing=structure_spacing)

    # 4. MSS
    mss_signals = detect_mss_v17(ohlcv, swings=internal_swings, tf=tf)

    # 5. Sweep (uses all swing levels — liquidity sweeps can happen at any swing)
    sweep_signals = detect_sweep_v17(ohlcv, swings=swings, tf=tf)

    # 6. EQL
    eql_signals = detect_eql_v17(ohlcv, swings=eql_swings,
        tolerance_pct=eqhl_threshold,
        atr_val=adaptive.get('atr_200'),
        tf=tf)

    # 7. BPR
    bpr_signals = detect_bpr_v17(ohlcv, fvg_signals=fvg_signals,
        ob_signals=ob_signals, tf=tf)

    # 8. IFVG
    ifvg_signals = detect_ifvg_v17(ohlcv, adaptive=adaptive, tf=tf)

    # Combine
    choch_signals = (structure.get('CHOCH_Bull', []) + structure.get('CHOCH_Bear', []))
    bos_signals = (structure.get('BOS_Bull', []) + structure.get('BOS_Bear', []))

    all_signals = (fvg_signals + ob_signals + sweep_signals +
                   choch_signals + bos_signals +
                   mss_signals + eql_signals + bpr_signals + ifvg_signals)
    all_signals.sort(key=lambda s: s.get('idx', 0))

    stats = {
        'total': len(all_signals),
        'fvg': len(fvg_signals), 'ob': len(ob_signals),
        'sweep': len(sweep_signals), 'choch': len(choch_signals),
        'bos': len(bos_signals), 'mss': len(mss_signals),
        'eql': len(eql_signals), 'bpr': len(bpr_signals), 'ifvg': len(ifvg_signals),
        'bull': sum(1 for s in all_signals if s.get('direction')=='bull'),
        'bear': sum(1 for s in all_signals if s.get('direction')=='bear'),
        'neutral': sum(1 for s in all_signals if s.get('direction')=='neutral'),
    }

    for i, sig in enumerate(all_signals): sig['seq'] = i

    return {
        'fvg': fvg_signals, 'ob': ob_signals, 'sweep': sweep_signals,
        'choch': choch_signals, 'bos': bos_signals,
        'mss': mss_signals, 'eql': eql_signals, 'bpr': bpr_signals,
        'ifvg': ifvg_signals, 'all': all_signals,
        'adaptive': adaptive,
        'swings': {'highs': [s['bar_idx'] for s in swings['highs']],
                    'lows': [s['bar_idx'] for s in swings['lows']]},
        'stats': stats,
    }
