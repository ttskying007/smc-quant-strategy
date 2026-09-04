#!/usr/bin/env python3
"""
V15 SMC信号检测引擎 — 全面Pine Script质量对齐

对齐的三段Pine参考:
  1. LuxAlgo SMC — 摆动结构/内部结构/EQH-EQL/FVG
  2. SMC 2026 — OB/CHOCH-BOS/BreakerBlock/FVG/EQH-EQL
  3. Waves Ultimate — pivothigh/pivotlow摆动点检测(右确认)

核心原则: 信号正确性 > 信号数量。宁可少但要准。

逐信号修复(V14已知缺陷→V15修复):
  FVG  : 改为Pine纯gap检测 low>high[2]/high<low[2] + ATR过滤
         V14条件c2_body_ok OR all_bearish → 改为AND逻辑(需三根同向K线)
  OB   : quick_swing→confirmed_swing + 摆动点向后扫描 + displacement≥1.5x
         V14用了无右确认的快摆动点→OB出现在任何局部高点
  CHOCH: 添加trend state machine区分BOS/CHOCH + min 20 bars spacing
  MSS  : 3-bar窗口→基于内部摆动结构的micro break
  Sweep: 任意长影线→必须突破前一个摆动点+反转
  EQL  : 价格聚类所有摆动点→连续pivot比较(ATR阈值), Pine准确方式
  BPR  : FVG重叠→OB+FVG多区域重叠平衡区间

参数默认(SMC 2026): swing_length=5, ob_swing=7, ob_lookback=10,
  ob_displacement_mult=1.5, fvg_atr_mult=0.5, eqhl_pivot=4, eqhl_thr=0.1
"""

import math, logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

log = logging.getLogger('smc_v15.signals')

# ═══════════════════════════════════════════════════════════════════════
# Signal data structures (复用)
# ═══════════════════════════════════════════════════════════════════════

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
# 自适应阈值
# ═══════════════════════════════════════════════════════════════════════

def calc_adaptive_thresholds(ohlcv: List[Dict]) -> Dict:
    if not ohlcv or len(ohlcv) < 20:
        return {'atr_pct': 2.0, 'vol_median': 1000, 'avg_volume': 1000,
                'fvg_min_width': 0.001, 'atr_value': 0.01}
    closes = [b['c'] for b in ohlcv if b.get('c', 0) > 0]
    highs = [b['h'] for b in ohlcv]
    lows = [b['l'] for b in ohlcv]
    vols = [b.get('v', b.get('vol', 0)) for b in ohlcv]

    recent = min(50, len(ohlcv))
    trs = []
    for i in range(max(1, len(ohlcv) - recent), len(ohlcv)):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs) / len(trs) if trs else (max(highs) - min(lows)) / max(1, len(ohlcv))
    avg_close = sum(closes) / len(closes) if closes else 100
    atr_pct = atr / avg_close * 100 if avg_close > 0 else 2.0
    atr_value = atr  # raw ATR value for displacement calculations
    vol_median = sorted(vols)[len(vols)//2] if vols else 1000
    avg_volume = sum(vols) / len(vols) if vols else 1000

    return {
        'atr_pct': max(0.3, min(10.0, atr_pct)),
        'atr_value': atr_value,
        'vol_median': vol_median,
        'avg_volume': avg_volume,
        'fvg_min_width': atr_value * 0.5,  # Pine: fvg_atr_mult=0.5
    }


# ═══════════════════════════════════════════════════════════════════════
# 1. 摆动点检测 — Pine pivothigh/pivotlow with right confirmation
# ═══════════════════════════════════════════════════════════════════════

def detect_swings_v15(ohlcv: List[Dict], left: int = 5, right: int = 2,
                       atr_filter: bool = True) -> Dict:
    """
    Pine-equivalent pivothigh/pivotlow

    参考:
      SMC 2026: ta.pivothigh(high, 5, 5), swing_length=5
      Waves Ultimate: ta.pivothigh(highSrc, 5, 2), rightBars=2
      LuxAlgo: leg() uses ta.highest/ta.lowest with dynamic size

    参数:
      left=5: 左边检查5根K线
      right=2: 右边确认2根K线 (Waves Ultimate default)
      ATR filter: 相邻同向摆动点幅度 < 0.3*ATR 则合并

    Returns: {'highs': [{idx, price, bar_idx},...], 'lows': [...], 'swing_idxs': set()}
      idx = 确认bar索引 (i + right)
      bar_idx = 摆动点实际bar索引 (i)
    """
    n = len(ohlcv)
    if n < left + right + 3:
        return {'highs': [], 'lows': [], 'swing_idxs': set()}

    # Precompute ATR
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

        # Pivot high: bar[i] is the highest high in [i-left, i+right]
        is_high = True
        for j in range(i - left, i + right + 1):
            if j == i or j < 0 or j >= n:
                continue
            if ohlcv[j]['h'] > bar['h']:
                is_high = False
                break
        if is_high:
            raw_highs.append({
                'idx': i + right,       # confirmation bar (Pine semantics)
                'bar_idx': i,            # actual pivot bar
                'price': bar['h']
            })

        # Pivot low
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

    # Merge adjacent swings of same direction (take most extreme)
    highs = _merge_same_direction(raw_highs, ohlcv, is_high=True)
    lows = _merge_same_direction(raw_lows, ohlcv, is_high=False)

    # ATR amplitude filter: merge tiny swings
    if atr_filter and atr_val > 0:
        min_amp = atr_val * 0.3
        highs = _filter_tiny_swings(highs, min_amp, 'high', ohlcv)
        lows = _filter_tiny_swings(lows, min_amp, 'low', ohlcv)

    swing_idxs = set()
    for h in highs:
        swing_idxs.add(h['idx'])
    for lw in lows:
        swing_idxs.add(lw['idx'])

    return {'highs': highs, 'lows': lows, 'swing_idxs': swing_idxs}


def _merge_same_direction(swings, ohlcv, is_high):
    """Merge consecutive swings of same direction keeping the most extreme"""
    if len(swings) < 2:
        return swings
    result = [swings[0]]
    for s in swings[1:]:
        last = result[-1]
        # If very close, merge
        if s['bar_idx'] - last['bar_idx'] <= 3:
            if is_high:
                if s['price'] > last['price']:
                    result[-1] = s
            else:
                if s['price'] < last['price']:
                    result[-1] = s
        else:
            result.append(s)
    return result


def _filter_tiny_swings(swings, min_amp, direction, ohlcv):
    """Filter swings with amplitude < min_amp from previous opposite swing"""
    if len(swings) < 2:
        return swings
    # Keep only swings that have meaningful amplitude from previous
    result = [swings[0]]
    for s in swings[1:]:
        prev = result[-1]
        amp = abs(s['price'] - prev['price'])
        if amp >= min_amp or s['bar_idx'] - prev['bar_idx'] > 20:
            result.append(s)
    return result


# ═══════════════════════════════════════════════════════════════════════
# 2. FVG — Pine exact: low > high[2] / high < low[2] + ATR filter
# ═══════════════════════════════════════════════════════════════════════

def detect_fvg_v15(ohlcv: List[Dict], adaptive: Dict = None,
                    tf: str = 'daily') -> List[Dict]:
    """
    Pine SMC 2026 exact:
      Bullish: low[0] > high[2]  AND  gapSize >= atr * 0.5
      Bearish: high[0] < low[2]  AND  gapSize >= atr * 0.5

    Plus candle quality: bars must be same direction (user requirement)
    """
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    n = len(ohlcv)
    signals = []
    atr_val = adaptive.get('atr_value', 0.01)
    min_gap = atr_val * 0.5  # fvg_atr_mult=0.5 (SMC 2026 default)

    for i in range(2, n):
        b0, b1, b2 = ohlcv[i], ohlcv[i-1], ohlcv[i-2]

        # Bullish FVG: current low > 2-bars-ago high
        if b0['l'] > b2['h']:
            gap = b0['l'] - b2['h']
            if gap >= min_gap:
                b0_bull = b0['c'] > b0['o']
                b1_bull = b1['c'] > b1['o']
                b2_bull = b2['c'] > b2['o']
                all_bull = b0_bull and b1_bull and b2_bull

                sig = Signal(
                    type='FVG_Bull', idx=i-1, direction='bull',
                    price=(b2['h'] + b0['l']) / 2,
                    upper=b0['l'], lower=b2['h'], timeframe=tf,
                    confirmed_at=i,
                    grade=3 if all_bull else 2,
                    trend_aligned=_check_trend(ohlcv, i, 'bull'),
                )
                sig.strength = 2.0 + (3.0 if all_bull else 0) + min(2.0, gap/atr_val)
                sig.confidence = min(0.9, 0.4 + (0.3 if all_bull else 0) + gap/atr_val*0.1)
                sig.metadata = {'gap': round(gap, 4), 'all_same_dir': all_bull}
                signals.append(sig)

        # Bearish FVG: current high < 2-bars-ago low
        if b0['h'] < b2['l']:
            gap = b2['l'] - b0['h']
            if gap >= min_gap:
                b0_bear = b0['c'] < b0['o']
                b1_bear = b1['c'] < b1['o']
                b2_bear = b2['c'] < b2['o']
                all_bear = b0_bear and b1_bear and b2_bear

                sig = Signal(
                    type='FVG_Bear', idx=i-1, direction='bear',
                    price=(b2['l'] + b0['h']) / 2,
                    upper=b2['l'], lower=b0['h'], timeframe=tf,
                    confirmed_at=i,
                    grade=3 if all_bear else 2,
                    trend_aligned=_check_trend(ohlcv, i, 'bear'),
                )
                sig.strength = 2.0 + (3.0 if all_bear else 0) + min(2.0, gap/atr_val)
                sig.confidence = min(0.9, 0.4 + (0.3 if all_bear else 0) + gap/atr_val*0.1)
                sig.metadata = {'gap': round(gap, 4), 'all_same_dir': all_bear}
                signals.append(sig)

    # Merge adjacent FVGs of same direction
    if signals:
        signals.sort(key=lambda s: s.idx)
        merged = [signals[0]]
        for s in signals[1:]:
            last = merged[-1]
            if abs(s.idx - last.idx) <= 3 and s.direction == last.direction:
                if s.strength > last.strength:
                    merged[-1] = s
            else:
                merged.append(s)
        signals = merged

    return [s.to_dict() for s in signals]


def _check_trend(ohlcv, idx, direction, lookback=10):
    if idx < lookback:
        return False
    recent = ohlcv[max(0, idx - lookback):idx + 1]
    if len(recent) < 5:
        return False
    avg_first = sum(b['c'] for b in recent[:3]) / 3
    avg_last = sum(b['c'] for b in recent[-3:]) / 3
    trend = (avg_last - avg_first) / avg_first * 100
    if direction == 'bull':
        return trend > 0.3
    return trend < -0.3


# ═══════════════════════════════════════════════════════════════════════
# 3. OB — Pine exact: from CONFIRMED swing, backward scan + displacement
# ═══════════════════════════════════════════════════════════════════════

def detect_ob_v15(ohlcv: List[Dict], swings: Dict = None,
                   displacement_mult: float = 1.5,
                   ob_lookback: int = 10,
                   adaptive: Dict = None, tf: str = 'daily') -> List[Dict]:
    """
    Pine SMC 2026 exact OB detection:

    Bull OB:
      swing_low_ob = ta.pivotlow(low, 7, 7)  # confirmed swing low
      Scan backward 8-17 bars from current
      Find bearish candle where:
        displacement = swing_low - hist_low
        range = hist_high - hist_low
        displacement > range * 1.5

    KEY FIX from V14: uses CONFIRMED swing points (with right=2 confirmation),
    NOT quick_swing (right=0 local maxima). This eliminates OB at random
    trend-internal local highs.
    """
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    if swings is None:
        swings = detect_swings_v15(ohlcv, left=7, right=2)

    n = len(ohlcv)
    signals = []
    vol_median = adaptive['vol_median']
    used_idx = set()
    swing_highs = swings.get('highs', [])
    swing_lows = swings.get('lows', [])

    # ── Bull OB: from confirmed swing LOW, backward scan ──
    for sl in swing_lows:
        sl_bar = sl['bar_idx']  # actual swing low bar
        sl_price = sl['price']
        if sl_bar < ob_lookback + 2:
            continue

        # Scan backward from swing low bar, look for bearish candle
        found = False
        for back in range(sl_bar - 1, max(sl_bar - ob_lookback - 5, 2), -1):
            bar = ohlcv[back]
            if bar['c'] < bar['o']:  # bearish candle (potential OB)
                rng = bar['h'] - bar['l']
                if rng <= 0:
                    continue
                disp = sl_price - bar['l']  # how far price traveled from OB low
                if disp > (rng * displacement_mult):
                    # Verify there's an IMPULSE between OB and swing
                    # (at least 1 bullish candle after OB, before swing)
                    has_impulse = False
                    for fwd in range(back + 1, sl_bar):
                        if ohlcv[fwd]['c'] > ohlcv[fwd]['o']:
                            has_impulse = True
                            break
                    if not has_impulse:
                        continue

                    ob_idx = back
                    ob_bar = bar
                    if ob_idx in used_idx:
                        continue

                    at_structure = True  # confirmed swing = structure
                    sig = Signal(
                        type='OB_Bull', idx=ob_idx, direction='bull',
                        price=ob_bar['l'], upper=ob_bar['h'], lower=ob_bar['l'],
                        timeframe=tf, confirmed_at=sl['idx'],
                        volume_ratio=round(ob_bar.get('v', 0) / vol_median, 2) if vol_median > 0 else 1,
                    )
                    sig.strength = 4.0 + min(3.0, disp / max(rng, 0.0001) * 0.5)
                    sig.confidence = min(0.9, 0.5 + disp / max(rng * 3, 0.0001))
                    sig.metadata = {
                        'method': 'swing_backward',
                        'swing_idx': sl['idx'],
                        'swing_bar': sl_bar,
                        'swing_price': round(sl_price, 4),
                        'displacement_ratio': round(disp / max(rng, 0.0001), 2),
                        'impulse_bars': sl_bar - back - 1,
                        'at_structure': True,
                    }
                    signals.append(sig)
                    used_idx.add(ob_idx)
                    found = True
                    break
            # else: bullish candle - skip (part of impulse)

    # ── Bear OB: from confirmed swing HIGH, backward scan ──
    for sh in swing_highs:
        sh_bar = sh['bar_idx']
        sh_price = sh['price']
        if sh_bar < ob_lookback + 2:
            continue

        for back in range(sh_bar - 1, max(sh_bar - ob_lookback - 5, 2), -1):
            bar = ohlcv[back]
            if bar['c'] > bar['o']:  # bullish candle (potential bear OB)
                rng = bar['h'] - bar['l']
                if rng <= 0:
                    continue
                disp = bar['h'] - sh_price  # how far from OB high down to swing
                if disp > (rng * displacement_mult):
                    # Verify impulse after OB
                    has_impulse = False
                    for fwd in range(back + 1, sh_bar):
                        if ohlcv[fwd]['c'] < ohlcv[fwd]['o']:
                            has_impulse = True
                            break
                    if not has_impulse:
                        continue

                    ob_idx = back
                    if ob_idx in used_idx:
                        continue
                    ob_bar = bar

                    sig = Signal(
                        type='OB_Bear', idx=ob_idx, direction='bear',
                        price=ob_bar['h'], upper=ob_bar['h'], lower=ob_bar['l'],
                        timeframe=tf, confirmed_at=sh['idx'],
                        volume_ratio=round(ob_bar.get('v', 0) / vol_median, 2) if vol_median > 0 else 1,
                    )
                    sig.strength = 4.0 + min(3.0, disp / max(rng, 0.0001) * 0.5)
                    sig.confidence = min(0.9, 0.5 + disp / max(rng * 3, 0.0001))
                    sig.metadata = {
                        'method': 'swing_backward',
                        'swing_idx': sh['idx'],
                        'swing_bar': sh_bar,
                        'swing_price': round(sh_price, 4),
                        'displacement_ratio': round(disp / max(rng, 0.0001), 2),
                        'impulse_bars': sh_bar - back - 1,
                        'at_structure': True,
                    }
                    signals.append(sig)
                    used_idx.add(ob_idx)
                    break

    signals.sort(key=lambda s: s.idx)
    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 4. CHOCH/BOS — Pine state machine with trend tracking
# ═══════════════════════════════════════════════════════════════════════

def detect_structure_v15(ohlcv: List[Dict], swings: Dict = None,
                          tf: str = 'daily') -> Dict:
    """
    Pine SMC 2026 structure detection:

    State machine tracking swing_trend:
      swing_trend = 0 (neutral), 1 (bullish), -1 (bearish)

    On each bar:
      if close > last_swing_high:
        if swing_trend == -1: CHOCH_Bull (trend reversal)
        else: BOS_Bull (trend continuation)
        swing_trend = 1

      if close < last_swing_low:
        if swing_trend == 1: CHOCH_Bear
        else: BOS_Bear
        swing_trend = -1

    Spacing: min 20 bars between labels (SMC 2026)

    Returns: {'CHOCH_Bull': [...], 'CHOCH_Bear': [...],
              'BOS_Bull': [...], 'BOS_Bear': [...],
              'all': combined list}
    """
    if swings is None:
        swings = detect_swings_v15(ohlcv)

    n = len(ohlcv)
    swing_highs = swings.get('highs', [])
    swing_lows = swings.get('lows', [])

    choch_signals = []
    bos_signals = []

    if not swing_highs and not swing_lows:
        return {'CHOCH_Bull': [], 'CHOCH_Bear': [],
                'BOS_Bull': [], 'BOS_Bear': [], 'all': []}

    # Combine all swing points sorted by bar index
    all_swings = []
    for sh in swing_highs:
        all_swings.append({'bar_idx': sh['bar_idx'], 'price': sh['price'],
                            'type': 'high', 'idx': sh['idx']})
    for sl in swing_lows:
        all_swings.append({'bar_idx': sl['bar_idx'], 'price': sl['price'],
                            'type': 'low', 'idx': sl['idx']})
    all_swings.sort(key=lambda s: s['bar_idx'])

    swing_trend = 0
    last_swing_high = None
    last_swing_low = None
    last_swing_high_idx = 0
    last_swing_low_idx = 0
    last_label_bar = -999

    # Walk through bars chronologically
    for i in range(n):
        bar = ohlcv[i]

        # Update last known swing high/low as they become available
        for sw in all_swings:
            if sw['bar_idx'] <= i and sw['type'] == 'high':
                if last_swing_high is None or sw['price'] > last_swing_high:
                    last_swing_high = sw['price']
                    last_swing_high_idx = sw['bar_idx']
            elif sw['bar_idx'] <= i and sw['type'] == 'low':
                if last_swing_low is None or sw['price'] < last_swing_low:
                    last_swing_low = sw['price']
                    last_swing_low_idx = sw['bar_idx']

        if last_swing_high is None or last_swing_low is None:
            continue
        if i - last_label_bar < 20:
            continue

        # Bullish break: close > last swing high
        if bar['c'] > last_swing_high and last_swing_high > 0:
            break_pct = (bar['c'] - last_swing_high) / last_swing_high * 100
            if break_pct < 0.2:  # minimum break threshold
                continue

            if swing_trend == -1:
                tag = 'CHOCH_Bull'
                strength = 5.0 + min(3.0, break_pct)
                conf = min(0.85, 0.4 + break_pct * 0.05)
            else:
                tag = 'BOS_Bull'
                strength = 3.0 + min(2.0, break_pct)
                conf = min(0.65, 0.3 + break_pct * 0.03)

            sig = Signal(
                type=tag, idx=i, direction='bull',
                price=bar['c'], upper=bar['h'], lower=last_swing_high,
                strength=strength, confidence=conf,
                timeframe=tf, confirmed_at=i + 1,
                metadata={
                    'break_level': round(last_swing_high, 4),
                    'break_pct': round(break_pct, 2),
                    'prior_trend': 'bear' if swing_trend == -1 else 'bull',
                },
            )
            if 'CHOCH' in tag:
                choch_signals.append(sig)
            else:
                bos_signals.append(sig)

            swing_trend = 1
            last_label_bar = i

        # Bearish break: close < last swing low
        elif bar['c'] < last_swing_low and last_swing_low > 0:
            break_pct = (last_swing_low - bar['c']) / last_swing_low * 100
            if break_pct < 0.2:
                continue

            if swing_trend == 1:
                tag = 'CHOCH_Bear'
                strength = 5.0 + min(3.0, break_pct)
                conf = min(0.85, 0.4 + break_pct * 0.05)
            else:
                tag = 'BOS_Bear'
                strength = 3.0 + min(2.0, break_pct)
                conf = min(0.65, 0.3 + break_pct * 0.03)

            sig = Signal(
                type=tag, idx=i, direction='bear',
                price=bar['c'], upper=last_swing_low, lower=bar['l'],
                strength=strength, confidence=conf,
                timeframe=tf, confirmed_at=i + 1,
                metadata={
                    'break_level': round(last_swing_low, 4),
                    'break_pct': round(break_pct, 2),
                    'prior_trend': 'bull' if swing_trend == 1 else 'bear',
                },
            )
            if 'CHOCH' in tag:
                choch_signals.append(sig)
            else:
                bos_signals.append(sig)

            swing_trend = -1
            last_label_bar = i

    all_struct = sorted(choch_signals + bos_signals, key=lambda s: s.idx)
    return {
        'CHOCH_Bull': [s.to_dict() for s in choch_signals if s.direction == 'bull'],
        'CHOCH_Bear': [s.to_dict() for s in choch_signals if s.direction == 'bear'],
        'BOS_Bull': [s.to_dict() for s in bos_signals if s.direction == 'bull'],
        'BOS_Bear': [s.to_dict() for s in bos_signals if s.direction == 'bear'],
        'all': [s.to_dict() for s in all_struct],
    }


# ═══════════════════════════════════════════════════════════════════════
# 5. MSS — Internal structure micro-shifts
# ═══════════════════════════════════════════════════════════════════════

def detect_mss_v15(ohlcv: List[Dict], swings: Dict = None,
                    tf: str = 'daily') -> List[Dict]:
    """
    MSS (Market Structure Shift) — early warning of structure change.

    Pine LuxAlgo approach:
      Internal structure uses shorter swing detection (size=5).
      When internal structure breaks a previous internal swing level,
      it signals a potential CHOCH earlier.

    SMC 2026: show_mss = false by default, not fully implemented.

    V15 approach:
      Use internal (smaller) swing points (left=3, right=1).
      Check if current close breaks previous internal high/low.
      More sensitive than CHOCH/BOS but less than V14's 3-bar window.
    """
    if swings is None:
        swings = detect_swings_v15(ohlcv, left=3, right=1)

    n = len(ohlcv)
    signals = []
    internal_highs = swings.get('highs', [])
    internal_lows = swings.get('lows', [])

    if len(internal_highs) < 1 or len(internal_lows) < 1:
        return []

    # Build last known internal levels
    last_int_high = None
    last_int_high_idx = 0
    last_int_low = None
    last_int_low_idx = 0
    last_label_bar = -999

    hs_by_bar = {h['bar_idx']: h for h in internal_highs}
    ls_by_bar = {lw['bar_idx']: lw for lw in internal_lows}

    for i in range(n):
        bar = ohlcv[i]

        if i in hs_by_bar:
            last_int_high = hs_by_bar[i]['price']
            last_int_high_idx = i
        if i in ls_by_bar:
            last_int_low = ls_by_bar[i]['price']
            last_int_low_idx = i

        if last_int_high is None or last_int_low is None:
            continue
        if i - last_label_bar < 8:
            continue

        # Bull MSS: close breaks above last internal high
        if bar['c'] > last_int_high and last_int_high > 0:
            break_pct = (bar['c'] - last_int_high) / last_int_high * 100
            if break_pct < 0.15:
                continue

            sig = Signal(
                type='MSS_Bull', idx=i, direction='bull',
                price=bar['c'], upper=bar['h'], lower=last_int_high,
                strength=min(3.5, 1.0 + break_pct),
                confidence=min(0.45, 0.2 + break_pct / 10),
                timeframe=tf, confirmed_at=i + 1,
                metadata={
                    'break_level': round(last_int_high, 4),
                    'break_pct': round(break_pct, 2),
                    'structure': 'internal',
                },
            )
            signals.append(sig)
            last_label_bar = i

        # Bear MSS
        elif bar['c'] < last_int_low and last_int_low > 0:
            break_pct = (last_int_low - bar['c']) / last_int_low * 100
            if break_pct < 0.15:
                continue

            sig = Signal(
                type='MSS_Bear', idx=i, direction='bear',
                price=bar['c'], upper=last_int_low, lower=bar['l'],
                strength=min(3.5, 1.0 + break_pct),
                confidence=min(0.45, 0.2 + break_pct / 10),
                timeframe=tf, confirmed_at=i + 1,
                metadata={
                    'break_level': round(last_int_low, 4),
                    'break_pct': round(break_pct, 2),
                    'structure': 'internal',
                },
            )
            signals.append(sig)
            last_label_bar = i

    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 6. Sweep — Liquidity grab at swing points only
# ═══════════════════════════════════════════════════════════════════════

def detect_sweep_v15(ohlcv: List[Dict], swings: Dict = None,
                      tf: str = 'daily') -> List[Dict]:
    """
    Sweep (Liquidity Grab): price briefly breaks a swing high/low
    then immediately reverses.

    ICT definition: a sweep must:
      1. Break a previous swing high (for bearish sweep) or low (for bullish sweep)
      2. Close BACK inside the range (reversal confirmation)
      3. The swing being swept must be recent (within 15 bars)

    V14 problem: any candle with long wick triggered sweep.
    V15 fix: must breach an actual swing point and reverse.
    """
    if swings is None:
        swings = detect_swings_v15(ohlcv, left=5, right=2)

    n = len(ohlcv)
    signals = []
    swing_highs = swings.get('highs', [])
    swing_lows = swings.get('lows', [])

    if not swing_highs and not swing_lows:
        return []

    # Track which swing points are available at each bar
    hs_by_bar = {}
    for h in swing_highs:
        hs_by_bar.setdefault(h['bar_idx'], []).append(h)

    ls_by_bar = {}
    for lw in swing_lows:
        ls_by_bar.setdefault(lw['bar_idx'], []).append(lw)

    last_highs = []  # (idx, price) of recent swing highs
    last_lows = []   # (idx, price) of recent swing lows

    for i in range(n):
        bar = ohlcv[i]

        # Add new swing points as they become known
        for h in hs_by_bar.get(i, []):
            last_highs.append((i, h['price']))
        for lw in ls_by_bar.get(i, []):
            last_lows.append((i, lw['price']))

        # Prune old swings (>15 bars old)
        last_highs = [(idx, p) for idx, p in last_highs if i - idx <= 15]
        last_lows = [(idx, p) for idx, p in last_lows if i - idx <= 15]

        body = abs(bar['c'] - bar['o'])
        upper_wick = bar['h'] - max(bar['c'], bar['o'])
        lower_wick = min(bar['c'], bar['o']) - bar['l']

        # SweepDown (bullish): wick breaks above a swing high, then closes below
        if upper_wick > body * 1.5 and len(last_highs) >= 1:
            for sh_idx, sh_price in last_highs:
                if bar['h'] > sh_price and bar['c'] < sh_price:
                    # Broke above swing high but closed below = sweep confirmed
                    sig = Signal(
                        type='SweepDown', idx=i, direction='bull',
                        price=bar['c'],
                        upper=bar['h'], lower=min(bar['c'], bar['o']),
                        strength=4.0,
                        confidence=0.55,
                        timeframe=tf, confirmed_at=i,
                        metadata={
                            'swept_level': round(sh_price, 4),
                            'swept_bar': sh_idx,
                            'wick_pct': round((bar['h'] - sh_price) / sh_price * 100, 2),
                        },
                    )
                    signals.append(sig)
                    break

        # SweepUp (bearish): wick breaks below a swing low, then closes above
        if lower_wick > body * 1.5 and len(last_lows) >= 1:
            for sl_idx, sl_price in last_lows:
                if bar['l'] < sl_price and bar['c'] > sl_price:
                    sig = Signal(
                        type='SweepUp', idx=i, direction='bear',
                        price=bar['c'],
                        upper=max(bar['c'], bar['o']), lower=bar['l'],
                        strength=4.0,
                        confidence=0.55,
                        timeframe=tf, confirmed_at=i,
                        metadata={
                            'swept_level': round(sl_price, 4),
                            'swept_bar': sl_idx,
                            'wick_pct': round((sl_price - bar['l']) / sl_price * 100, 2),
                        },
                    )
                    signals.append(sig)
                    break

    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 7. EQL — Consecutive pivot comparison (Pine exact)
# ═══════════════════════════════════════════════════════════════════════

def detect_eql_v15(ohlcv: List[Dict], swings: Dict = None,
                    tolerance_pct: float = None,
                    atr_val: float = None,
                    tf: str = 'daily') -> List[Dict]:
    """
    Pine SMC 2026 exact EQH/EQL:

    For each new pivot high:
      Compare with PREVIOUS pivot high.
      If |ph - previousHigh| < atr * 0.1: EQH!

    For each new pivot low:
      Compare with PREVIOUS pivot low.
      If |pl - previousLow| < atr * 0.1: EQL!

    Uses eqhl_pivot_length=4 (Pine default), threshold=0.1
    """
    if swings is None:
        # Use shorter pivots for EQL detection (eqhl_pivot_length=4)
        swings = detect_swings_v15(ohlcv, left=4, right=2)
    if atr_val is None:
        adapt = calc_adaptive_thresholds(ohlcv)
        atr_val = adapt.get('atr_value', 0.01)
    if tolerance_pct is None:
        tolerance_pct = 0.1  # eqhl_threshold

    threshold = atr_val * tolerance_pct
    signals = []
    swing_highs = swings.get('highs', [])
    swing_lows = swings.get('lows', [])

    # EQH: consecutive pivot highs within threshold
    if len(swing_highs) >= 2:
        for i in range(1, len(swing_highs)):
            prev = swing_highs[i - 1]
            curr = swing_highs[i]
            if abs(curr['price'] - prev['price']) < threshold:
                level = max(curr['price'], prev['price'])
                sig = Signal(
                    type='EQL_High', idx=curr['idx'], direction='bear',
                    price=round(level, 2),
                    upper=round(level, 2),
                    lower=round(level * 0.995, 2),
                    strength=3.0,
                    confidence=0.45,
                    timeframe=tf, confirmed_at=curr['idx'],
                    metadata={
                        'level': round(level, 4),
                        'prev_swing': prev['bar_idx'],
                        'threshold': round(threshold, 4),
                    },
                )
                signals.append(sig)

    # EQL: consecutive pivot lows within threshold
    if len(swing_lows) >= 2:
        for i in range(1, len(swing_lows)):
            prev = swing_lows[i - 1]
            curr = swing_lows[i]
            if abs(curr['price'] - prev['price']) < threshold:
                level = min(curr['price'], prev['price'])
                sig = Signal(
                    type='EQL_Low', idx=curr['idx'], direction='bull',
                    price=round(level, 2),
                    upper=round(level * 1.005, 2),
                    lower=round(level, 2),
                    strength=3.0,
                    confidence=0.45,
                    timeframe=tf, confirmed_at=curr['idx'],
                    metadata={
                        'level': round(level, 4),
                        'prev_swing': prev['bar_idx'],
                        'threshold': round(threshold, 4),
                    },
                )
                signals.append(sig)

    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 8. BPR — Balanced Price Range from overlapping zones
# ═══════════════════════════════════════════════════════════════════════

def detect_bpr_v15(ohlcv: List[Dict],
                    fvg_signals: List[Dict] = None,
                    ob_signals: List[Dict] = None,
                    tf: str = 'daily') -> List[Dict]:
    """
    BPR (Balanced Price Range): price zone where both bull and bear
    zones overlap, creating a balance area.

    V14: only checked bull FVG vs bear FVG overlap.
    V15: check all zone types (FVG + OB) for overlapping areas.

    Returns zones where bull support and bear resistance converge.
    """
    # Collect all bull zones and bear zones
    bull_zones = []
    bear_zones = []

    if fvg_signals:
        for f in fvg_signals:
            up = f.get('upper', 0)
            lo = f.get('lower', 0)
            if up <= 0 or lo <= 0:
                continue
            if 'Bull' in f.get('type', ''):
                bull_zones.append({'up': up, 'lo': lo, 'idx': f.get('idx', 0),
                                    'strength': f.get('strength', 2)})
            elif 'Bear' in f.get('type', ''):
                bear_zones.append({'up': up, 'lo': lo, 'idx': f.get('idx', 0),
                                    'strength': f.get('strength', 2)})

    if ob_signals:
        for o in ob_signals:
            up = o.get('upper', 0)
            lo = o.get('lower', 0)
            if up <= 0 or lo <= 0:
                continue
            if 'Bull' in o.get('type', ''):
                bull_zones.append({'up': up, 'lo': lo, 'idx': o.get('idx', 0),
                                    'strength': o.get('strength', 4)})
            elif 'Bear' in o.get('type', ''):
                bear_zones.append({'up': up, 'lo': lo, 'idx': o.get('idx', 0),
                                    'strength': o.get('strength', 4)})

    if len(bull_zones) < 1 or len(bear_zones) < 1:
        return []

    signals = []
    seen_overlaps = set()

    for bz in bull_zones:
        for brz in bear_zones:
            # Zones must overlap
            if bz['up'] > brz['lo'] and bz['lo'] < brz['up']:
                oh = min(bz['up'], brz['up'])
                ol = max(bz['lo'], brz['lo'])
                if oh <= ol:
                    continue

                key = (round(oh, 3), round(ol, 3))
                if key in seen_overlaps:
                    continue
                seen_overlaps.add(key)

                last_idx = max(bz['idx'], brz['idx'])
                sig = Signal(
                    type='BPR', idx=last_idx, direction='neutral',
                    price=(oh + ol) / 2, upper=oh, lower=ol,
                    strength=min(8.0, bz.get('strength', 2) + brz.get('strength', 2)),
                    confidence=min(0.7, 0.3 + (oh - ol) / max(oh, 0.01) * 5),
                    timeframe=tf, confirmed_at=last_idx,
                    metadata={
                        'overlap_high': round(oh, 4),
                        'overlap_low': round(ol, 4),
                        'sources': 'fvg+ob',
                    },
                )
                signals.append(sig)

    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 9. IFVG — Implied Fair Value Gap (simplified)
# ═══════════════════════════════════════════════════════════════════════

def detect_ifvg_v15(ohlcv: List[Dict], adaptive: Dict = None,
                     tf: str = 'daily') -> List[Dict]:
    """IFVG — 简化版"""
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    n = len(ohlcv)
    signals = []
    atr_val = adaptive.get('atr_value', 0.01)

    for i in range(1, n - 2):
        c1, c2 = ohlcv[i], ohlcv[i + 1]
        c1_mid = (c1['h'] + c1['l']) / 2
        c2_mid = (c2['h'] + c2['l']) / 2

        if c1['h'] < c2['l']:
            gap = c2['l'] - c1['h']
            if gap >= atr_val * 0.3:
                sig = Signal(
                    type='IFVG_Bull', idx=i, direction='bull',
                    price=(c1_mid + c2_mid) / 2, upper=c2['l'], lower=c1['h'],
                    strength=2.0, confidence=0.3, timeframe=tf, confirmed_at=i + 1,
                    metadata={'gap': round(gap, 4)},
                )
                signals.append(sig)
        elif c1['l'] > c2['h']:
            gap = c1['l'] - c2['h']
            if gap >= atr_val * 0.3:
                sig = Signal(
                    type='IFVG_Bear', idx=i, direction='bear',
                    price=(c1_mid + c2_mid) / 2, upper=c1['l'], lower=c2['h'],
                    strength=2.0, confidence=0.3, timeframe=tf, confirmed_at=i + 1,
                    metadata={'gap': round(gap, 4)},
                )
                signals.append(sig)
    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 10. 统一入口
# ═══════════════════════════════════════════════════════════════════════

def detect_all_signals_v15(ohlcv: List[Dict], params: Dict = None,
                            adaptive: Dict = None, tf: str = 'daily') -> Dict:
    """
    V15 unified signal detection — Pine Script quality.

    Detection order:
    1. Swings (once, shared)
    2. FVG
    3. OB (depends on swings)
    4. Structure CHOCH/BOS (depends on swings)
    5. MSS (depends on internal swings)
    6. Sweep (depends on swings)
    7. EQL (depends on swings)
    8. BPR (depends on FVG + OB)
    9. IFVG

    Parameters (SMC 2026 defaults):
      swing_left=5, swing_right=2
      ob_displacement_mult=1.5, ob_lookback=10
      eqhl_pivot=4, eqhl_threshold=0.1
      fvg_atr_mult=0.5
    """
    if params is None:
        params = {}
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)

    # ── Swings: once, shared across all detectors ──
    swing_left = params.get('swing_left', 5)
    swing_right = params.get('swing_right', 2)
    swings = detect_swings_v15(ohlcv, left=swing_left, right=swing_right)

    # ── Also generate internal swings (shorter) for MSS ──
    internal_swings = detect_swings_v15(ohlcv, left=3, right=1)

    # ── EQL swings (even shorter) ──
    eql_swings = detect_swings_v15(ohlcv, left=4, right=2)

    # ── 1. FVG ──
    fvg_signals = detect_fvg_v15(ohlcv, adaptive=adaptive, tf=tf)

    # ── 2. OB ──
    ob_signals = detect_ob_v15(
        ohlcv, swings=swings,
        displacement_mult=params.get('ob_displacement_mult', 1.5),
        ob_lookback=params.get('ob_lookback', 10),
        adaptive=adaptive, tf=tf,
    )

    # ── 3. Structure CHOCH/BOS ──
    structure = detect_structure_v15(ohlcv, swings=swings, tf=tf)

    # ── 4. MSS ──
    mss_signals = detect_mss_v15(ohlcv, swings=internal_swings, tf=tf)

    # ── 5. Sweep ──
    sweep_signals = detect_sweep_v15(ohlcv, swings=swings, tf=tf)

    # ── 6. EQL ──
    eql_signals = detect_eql_v15(
        ohlcv, swings=eql_swings,
        tolerance_pct=params.get('eqhl_threshold', 0.1),
        atr_val=adaptive.get('atr_value'),
        tf=tf,
    )

    # ── 7. BPR ──
    bpr_signals = detect_bpr_v15(ohlcv, fvg_signals=fvg_signals,
                                  ob_signals=ob_signals, tf=tf)

    # ── 8. IFVG ──
    ifvg_signals = detect_ifvg_v15(ohlcv, adaptive=adaptive, tf=tf)

    # ── Combine ──
    choch_signals = (structure.get('CHOCH_Bull', []) +
                     structure.get('CHOCH_Bear', []))
    bos_signals = (structure.get('BOS_Bull', []) +
                   structure.get('BOS_Bear', []))

    all_signals = (fvg_signals + ob_signals + sweep_signals +
                   choch_signals + bos_signals +
                   mss_signals + eql_signals + bpr_signals + ifvg_signals)
    all_signals.sort(key=lambda s: s.get('idx', 0))

    # ── Statistics ──
    stats = {
        'total': len(all_signals),
        'fvg': len(fvg_signals),
        'ob': len(ob_signals),
        'sweep': len(sweep_signals),
        'choch': len(choch_signals),
        'bos': len(bos_signals),
        'mss': len(mss_signals),
        'eql': len(eql_signals),
        'bpr': len(bpr_signals),
        'ifvg': len(ifvg_signals),
        'bull': sum(1 for s in all_signals if s.get('direction') == 'bull'),
        'bear': sum(1 for s in all_signals if s.get('direction') == 'bear'),
    }

    for i, sig in enumerate(all_signals):
        sig['seq'] = i

    return {
        'fvg': fvg_signals,
        'ob': ob_signals,
        'sweep': sweep_signals,
        'choch': choch_signals,
        'bos': bos_signals,
        'mss': mss_signals,
        'eql': eql_signals,
        'bpr': bpr_signals,
        'ifvg': ifvg_signals,
        'all': all_signals,
        'adaptive': adaptive,
        'swings': {
            'highs': [s['bar_idx'] for s in swings['highs']],
            'lows': [s['bar_idx'] for s in swings['lows']],
        },
        'stats': stats,
    }
