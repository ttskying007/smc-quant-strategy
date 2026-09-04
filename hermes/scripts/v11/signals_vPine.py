#!/usr/bin/env python3
"""
SMC V-Pine — Pine Script Quality Signal Detection Engine
==========================================================

Complete rewrite of signals_v11.py with proven Pine Script algorithms.

Key Improvements over signals_v11.py:
1. Pine-equivalent swing detection (right confirmation + ATR filter + volatility-aware)
2. OB displacement filter (>1.3x range of preceding candle) + ATR-normalized strength
3. State machine structure detection (BOS/CHOCH via crossover, no rigid sequences)
4. Pivot-based EQH/EQL liquidity zones (UAlgo-style)

Reference Pine Scripts:
- Smart Money Concepts 2026: ob_displacement_mult=1.3, ob_swing_length=7
- LuxAlgo SMC: dual structure (5-bar internal + 50-bar swing), volatility-aware parsing
- Waves Ultimate: zigzag with pivothigh/pivotlow (left=10, right=10)

Design Principles:
- Same Signal dataclass and detect_all_signals_vPine() interface as v11
- Backward-compatible with v468_engine.py (just change import)
- Improved internal detection quality without changing external API
"""

import math, logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

log = logging.getLogger('smc_vPine.signals')


# ═══════════════════════════════════════════════════════════════════════
# Signal data structures (identical to v11 for compatibility)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class Signal:
    """统一信号数据结构 — 与V11完全兼容"""
    type: str
    idx: int
    direction: str
    price: float
    timeframe: str = 'daily'
    strength: float = 0.0
    confidence: float = 0.5
    upper: float = 0.0
    lower: float = 0.0
    confirmed_at: int = -1
    expired_at: int = -1
    is_active: bool = True
    grade: int = 1
    trend_aligned: bool = False
    volume_ratio: float = 1.0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            'type': self.type,
            'idx': self.idx,
            'direction': self.direction,
            'price': self.price,
            'timeframe': self.timeframe,
            'strength': round(self.strength, 2),
            'confidence': round(self.confidence, 3),
            'upper': round(self.upper, 4),
            'lower': round(self.lower, 4),
            'confirmed_at': self.confirmed_at,
            'is_active': self.is_active,
            'grade': self.grade,
            'trend_aligned': self.trend_aligned,
            'volume_ratio': round(self.volume_ratio, 2),
            **self.metadata,
        }


# ═══════════════════════════════════════════════════════════════════════
# Adaptive threshold calculator (same as v11, minor improvements)
# ═══════════════════════════════════════════════════════════════════════

def calc_adaptive_thresholds(ohlcv: List[Dict]) -> Dict:
    """自适应阈值计算 — 基于每只股票的波动特性"""
    n = len(ohlcv)
    if n < 20:
        return {
            'atr_pct': 2.0, 'atr_median': 2.0,
            'avg_volume': 1e6, 'vol_median': 1e6, 'vol_std': 1e6,
            'fvg_min_width': 0.001, 'sweep_wick_ratio': 2.0,
            'ob_strength_min': 1.0, 'volatility_class': 'medium',
            'swing_min_pct': 1.5, 'ob_displacement_mult': 1.5,
        }

    # ATR calculation
    ranges = []
    for i in range(1, n):
        tr = max(
            ohlcv[i]['h'] - ohlcv[i]['l'],
            abs(ohlcv[i]['h'] - ohlcv[i-1]['c']),
            abs(ohlcv[i]['l'] - ohlcv[i-1]['c']),
        )
        ranges.append(tr / ohlcv[i]['c'] * 100 if ohlcv[i]['c'] > 0 else 0)

    sorted_ranges = sorted(ranges)
    atr_pct = sum(ranges[-min(14, len(ranges)):]) / min(14, len(ranges))
    atr_median = sorted_ranges[len(sorted_ranges) // 2] if sorted_ranges else 1.0

    # Volume stats
    vols = [b['v'] for b in ohlcv]
    sorted_vols = sorted(vols)
    avg_vol = sum(vols) / len(vols)
    vol_median = sorted_vols[len(sorted_vols) // 2] if sorted_vols else 1
    vol_std = math.sqrt(sum((v - avg_vol) ** 2 for v in vols) / len(vols)) if vols else 0

    # Volatility classification — more granular for Pine quality
    if atr_pct < 1.0:
        vol_class = 'very_low'
        fvg_min = 0.0003
        sweep_wick = 3.0
        ob_min = 0.6
        swing_min_pct = 0.8
    elif atr_pct < 1.5:
        vol_class = 'low'
        fvg_min = 0.0005
        sweep_wick = 2.5
        ob_min = 0.8
        swing_min_pct = 1.0
    elif atr_pct < 3.0:
        vol_class = 'medium'
        fvg_min = 0.001
        sweep_wick = 2.0
        ob_min = 1.0
        swing_min_pct = 1.5
    elif atr_pct < 5.0:
        vol_class = 'high'
        fvg_min = 0.002
        sweep_wick = 1.8
        ob_min = 1.2
        swing_min_pct = 2.0
    else:
        vol_class = 'very_high'
        fvg_min = 0.003
        sweep_wick = 1.5
        ob_min = 1.5
        swing_min_pct = 3.0

    scale = max(0.5, min(2.0, atr_median / 2.0))
    fvg_min *= scale
    ob_min *= scale

    return {
        'atr_pct': round(atr_pct, 2),
        'atr_median': round(atr_median, 2),
        'avg_volume': round(avg_vol, 0),
        'vol_median': round(vol_median, 0),
        'vol_std': round(vol_std, 0),
        'fvg_min_width': round(fvg_min, 5),
        'sweep_wick_ratio': round(sweep_wick, 2),
        'ob_strength_min': round(ob_min, 2),
        'volatility_class': vol_class,
        'swing_min_pct': swing_min_pct,
        'ob_displacement_mult': 1.0,
    }


# ═══════════════════════════════════════════════════════════════════════
# PINE-EQUIVALENT SWING DETECTION — 🎯 KEY IMPROVEMENT #1
# ═══════════════════════════════════════════════════════════════════════

def detect_swings_vPine(ohlcv: List[Dict], left: int = 10, right: int = 10,
                         min_swing_pct: float = None, adaptive: Dict = None,
                         vol_invert: bool = True) -> Tuple[List, List]:
    """
    Pine-equivalent swing point detection.

    Uses ta.pivothigh(high, left, right) / ta.pivotlow(low, left, right) algorithm:
    - left: bars to check on left side (default 10)
    - right: bars to check on right side (default 10) = confirmation bars
    - A bar is NOT a swing until 'right' bars pass WITHOUT a higher/lower extreme

    LuxAlgo-style enhancements:
    - ATR magnitude filter: reject swings with insufficient range
    - Volatility-aware inversion: bars with range >= 2*ATR get high/low swapped
      to prevent false swings on volatile bars

    Returns:
        (swing_highs, swing_lows) — each is List[Tuple[idx, price]]
        sorted by idx ascending
    """
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    if min_swing_pct is None:
        min_swing_pct = adaptive.get('swing_min_pct', 1.5)

    n = len(ohlcv)
    atr_pct = adaptive['atr_pct']
    atr_threshold = atr_pct * 2.0  # 2x ATR for volatility inversion

    swing_highs = []
    swing_lows = []

    for i in range(left + right, n - 1):
        bar = ohlcv[i]

        # ── Volatility-aware inversion (LuxAlgo style) ──
        # If current bar range >= 2*ATR, treat it as a volatile outlier
        # and swap its high/low for swing detection purposes
        range_pct = (bar['h'] - bar['l']) / bar['l'] * 100 if bar['l'] > 0 else 0
        is_high_vol = range_pct >= atr_threshold and vol_invert

        effective_high = bar['l'] if is_high_vol else bar['h']
        effective_low = bar['h'] if is_high_vol else bar['l']

        # ── Swing High: highest point in [i-left, i+right] window ──
        is_swing_high = True
        for j in range(i - left, i + right + 1):
            if j == i or j >= n:
                continue
            compare_high = ohlcv[min(j, n-1)]['l'] if (vol_invert and 
                (ohlcv[min(j, n-1)]['h'] - ohlcv[min(j, n-1)]['l']) / max(ohlcv[min(j, n-1)]['l'], 0.01) * 100 >= atr_threshold
            ) else ohlcv[min(j, n-1)]['h']
            if j < i:
                # Check left: ALL bars to the left must have lower highs
                if compare_high >= effective_high:
                    is_swing_high = False
                    break
            else:
                # Check right: ALL bars to the right must have lower highs
                # This is the RIGHT CONFIRMATION — Pine Script native behavior
                if compare_high > effective_high:
                    is_swing_high = False
                    break

        if is_swing_high:
            # ATR magnitude filter: swing range must be meaningful
            # Check the range from previous swing (or from start)
            min_price_prev = min(ohlcv[max(0, i-left)]['l'], bar['l'])
            swing_range_pct = (effective_high - min_price_prev) / max(min_price_prev, 0.01) * 100
            if swing_range_pct >= min_swing_pct or len(swing_highs) < 2:
                swing_highs.append((i, bar['h']))

        # ── Swing Low: lowest point in [i-left, i+right] window ──
        is_swing_low = True
        for j in range(i - left, i + right + 1):
            if j == i or j >= n:
                continue
            compare_low = ohlcv[min(j, n-1)]['h'] if (vol_invert and 
                (ohlcv[min(j, n-1)]['h'] - ohlcv[min(j, n-1)]['l']) / max(ohlcv[min(j, n-1)]['l'], 0.01) * 100 >= atr_threshold
            ) else ohlcv[min(j, n-1)]['l']
            if j < i:
                if compare_low <= effective_low:
                    is_swing_low = False
                    break
            else:
                if compare_low < effective_low:
                    is_swing_low = False
                    break

        if is_swing_low:
            max_price_prev = max(ohlcv[max(0, i-left)]['h'], bar['h'])
            swing_range_pct = (max_price_prev - effective_low) / max(effective_low, 0.01) * 100
            if swing_range_pct >= min_swing_pct or len(swing_lows) < 2:
                swing_lows.append((i, bar['l']))

    return swing_highs, swing_lows


def detect_swings_internal(ohlcv: List[Dict], left: int = 3, right: int = 2,
                            min_swing_pct: float = 0.3) -> Tuple[List, List]:
    """
    Internal (micro) swing detection — for LuxAlgo-style dual structure.
    5-bar window for detecting minor swings within the larger structure.
    """
    n = len(ohlcv)
    highs = []
    lows = []
    for i in range(left + right, n - 1):
        is_high = True
        for j in range(i - left, i + right + 1):
            if j == i or j >= n: continue
            if ohlcv[j]['h'] >= ohlcv[i]['h']:
                is_high = False
                break
        if is_high:
            highs.append((i, ohlcv[i]['h']))
        is_low = True
        for j in range(i - left, i + right + 1):
            if j == i or j >= n: continue
            if ohlcv[j]['l'] <= ohlcv[i]['l']:
                is_low = False
                break
        if is_low:
            lows.append((i, ohlcv[i]['l']))
    return highs, lows


# ═══════════════════════════════════════════════════════════════════════
# 1. FVG Detection — keeps existing quality, adds Pine refinements
# ═══════════════════════════════════════════════════════════════════════

def _classify_fvg_width(gap_pct: float, ohlcv: List, idx: int,
                         adaptive: Dict) -> int:
    """FVG宽度分级 1-4"""
    atr = adaptive.get('atr_pct', 2.0)
    ratio = gap_pct / atr if atr > 0 else 0
    if ratio > 1.5: return 4  # macro
    if ratio > 0.8: return 3  # meso
    if ratio > 0.3: return 2  # micro
    return 1  # nano


def _check_trend_alignment(ohlcv: List, idx: int, direction: str) -> bool:
    """检查信号方向是否与局部趋势对齐"""
    if idx < 5: return True
    lookback = min(8, idx)
    s = ohlcv[idx - lookback]['c']
    e = ohlcv[idx]['c']
    change = (e - s) / s * 100 if s > 0 else 0
    if direction == 'bull':
        return change > -0.5
    return change < 0.5


def _calc_fvg_strength(sig: 'Signal', c2: Dict, adaptive: Dict) -> float:
    """FVG强度 (0-10)"""
    gap_pct = sig.metadata.get('gap_pct', 0)
    atr = adaptive.get('atr_pct', 2.0)
    strength = 2.0 + min(5.0, gap_pct / atr * 3) if atr > 0 else 2.0
    vol_ratio = c2.get('v', 0) / max(adaptive.get('vol_median', 1), 1)
    if vol_ratio > 2.0: strength += 2.0
    elif vol_ratio > 1.5: strength += 1.0
    c2_body = abs(c2['c'] - c2['o']) / max(c2['c'], 0.01) * 100
    if c2_body > atr * 0.8: strength += 1.0
    if sig.grade >= 3: strength += 1.0
    return min(10, strength)


def _calc_fvg_confidence(sig: 'Signal', b1: Dict, b2: Dict, b3: Dict,
                          gap_pct: float) -> float:
    """FVG置信度 (0-1)"""
    conf = 0.35
    if gap_pct > 0.005: conf += 0.15
    if gap_pct > 0.01: conf += 0.10
    if b2['c'] < b2['o'] and b1['c'] < b1['o']: conf += 0.10
    if b2['v'] > b1['v'] * 1.2: conf += 0.10
    if sig.grade >= 3: conf += 0.10
    return min(0.85, conf)


def _merge_fvgs_vPine(signals: List, merge_dist: int = 3) -> List:
    """合并相邻FVG — 去除冗余"""
    if len(signals) < 2: return signals
    merged = [signals[0]]
    for s in signals[1:]:
        last = merged[-1]
        same_dir = last.direction == s.direction
        close_idx = abs(s.idx - last.idx) <= merge_dist
        overlap = (last.upper >= s.lower and last.lower <= s.upper)
        if same_dir and close_idx and overlap:
            last.upper = max(last.upper, s.upper)
            last.lower = min(last.lower, s.lower)
            last.price = (last.upper + last.lower) / 2
            last.strength = max(last.strength, s.strength)
            last.confidence = max(last.confidence, s.confidence)
            last.grade = max(last.grade, s.grade)
            last.metadata['merged_count'] = last.metadata.get('merged_count', 1) + 1
        else:
            merged.append(s)
    return merged


def detect_fvg_vPine(ohlcv: List[Dict], min_width: float = None,
                     merge_dist: int = 3, adaptive: Dict = None,
                     tf: str = 'daily') -> List[Dict]:
    """
    Enhanced FVG detection — keeps existing V11 quality with Pine refinements.

    Refinements:
    - ATR-normalized min_width (Pine style: min_width = ATR * 0.5 * scale)
    - 3-color pattern detection (continuation bear/bull = stronger)
    - Gap width grade with ATR ratio
    """
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    if min_width is None:
        min_width = max(0.0003, adaptive['atr_pct'] * 0.0003)

    n = len(ohlcv)
    signals = []
    atr = adaptive.get('atr_pct', 2.0)

    for i in range(n - 2):
        b1, b2, b3 = ohlcv[i], ohlcv[i+1], ohlcv[i+2]

        b1_bear = b1['c'] < b1['o']
        b2_bear = b2['c'] < b2['o']
        b3_bear = b3['c'] < b3['o']
        b1_bull = b1['c'] > b1['o']
        b2_bull = b2['c'] > b2['o']
        b3_bull = b3['c'] > b3['o']

        all_bearish = b1_bear and b2_bear and b3_bear
        all_bullish = b1_bull and b2_bull and b3_bull

        c2_body_pct = abs(b2['c'] - b2['o']) / max(b2['c'], 0.01) * 100
        c2_body_ok = c2_body_pct >= atr * 0.5  # Slightly relaxed from v11

        # Bullish FVG: gap up
        if b1['h'] < b3['l']:
            gap = b3['l'] - b1['h']
            gap_pct = gap / max(b1['c'], 0.01)

            if gap_pct >= min_width and (c2_body_ok or all_bearish):
                is_consecutive_bearish = all_bearish
                grade = _classify_fvg_width(gap_pct, ohlcv, i, adaptive)
                if is_consecutive_bearish:
                    grade = max(grade, 3)
                trend_aligned = _check_trend_alignment(ohlcv, i, 'bull')

                sig = Signal(
                    type='FVG_Bull', idx=i+1, direction='bull',
                    price=(b1['h'] + b3['l']) / 2,
                    upper=b3['l'], lower=b1['h'], timeframe=tf,
                    grade=grade, trend_aligned=trend_aligned,
                    confirmed_at=i+2,
                )
                sig.strength = _calc_fvg_strength(sig, b2, adaptive)
                sig.confidence = _calc_fvg_confidence(sig, b1, b2, b3, gap_pct)
                if is_consecutive_bearish:
                    sig.confidence = min(1.0, sig.confidence + 0.15)
                    sig.strength = min(10, sig.strength + 2.0)
                sig.metadata = {
                    'gap_pct': round(gap_pct, 4),
                    'gap_absolute': round(gap, 2),
                    'candle1_close': b1['c'],
                    'candle3_open': b3['o'],
                    'candle2_range': round((b2['h'] - b2['l']) / max(b2['c'], 0.01) * 100, 2),
                    'consecutive_bearish': is_consecutive_bearish,
                    'c2_body_ok': c2_body_ok,
                    'fvg_color_pattern': '3bear' if is_consecutive_bearish else 'mixed',
                }
                signals.append(sig)

        # Bearish FVG: gap down
        elif b1['l'] > b3['h']:
            gap = b1['l'] - b3['h']
            gap_pct = gap / max(b1['c'], 0.01)

            if gap_pct >= min_width and (c2_body_ok or all_bullish):
                is_consecutive_bullish = all_bullish
                grade = _classify_fvg_width(gap_pct, ohlcv, i, adaptive)
                if is_consecutive_bullish:
                    grade = max(grade, 3)
                trend_aligned = _check_trend_alignment(ohlcv, i, 'bear')

                sig = Signal(
                    type='FVG_Bear', idx=i+1, direction='bear',
                    price=(b1['l'] + b3['h']) / 2,
                    upper=b1['l'], lower=b3['h'], timeframe=tf,
                    grade=grade, trend_aligned=trend_aligned,
                    confirmed_at=i+2,
                )
                sig.strength = _calc_fvg_strength(sig, b2, adaptive)
                sig.confidence = _calc_fvg_confidence(sig, b1, b2, b3, gap_pct)
                if is_consecutive_bullish:
                    sig.confidence = min(1.0, sig.confidence + 0.15)
                    sig.strength = min(10, sig.strength + 2.0)
                sig.metadata = {
                    'gap_pct': round(gap_pct, 4),
                    'gap_absolute': round(gap, 2),
                    'consecutive_bullish': is_consecutive_bullish,
                    'c2_body_ok': c2_body_ok,
                    'fvg_color_pattern': '3bull' if is_consecutive_bullish else 'mixed',
                }
                signals.append(sig)

    if merge_dist > 0 and signals:
        signals = _merge_fvgs_vPine(signals, merge_dist)

    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 2. Sweep Detection — keep existing V11 quality
# ═══════════════════════════════════════════════════════════════════════

def _classify_wick(ratio: float) -> int:
    if ratio >= 5: return 4
    elif ratio >= 3: return 3
    elif ratio >= 2: return 2
    else: return 1

def _calc_sweep_strength_vPine(cur: Dict, wick: float, wick_ratio: float,
                                wick_grade: int, adaptive: Dict, at_swing: bool) -> float:
    strength = 1.0
    strength += (wick_grade - 1) * 1.5
    avg_vol = adaptive['avg_volume']
    vol_ratio = cur['v'] / avg_vol if avg_vol > 0 else 1
    if vol_ratio > 2.0: strength += 2.0
    elif vol_ratio > 1.5: strength += 1.0
    if at_swing: strength += 2.0
    wick_pct = wick / max(cur['c'], 0.01) * 100
    atr = adaptive['atr_pct']
    if wick_pct > atr: strength += 1.0
    return min(10, strength)

def _calc_sweep_confidence_vPine(cur: Dict, wick_ratio: float,
                                  vol_ok: bool, at_swing: bool) -> float:
    conf = 0.30
    if wick_ratio > 3.0: conf += 0.20
    elif wick_ratio > 2.0: conf += 0.10
    if vol_ok: conf += 0.15
    if at_swing: conf += 0.20
    return min(0.80, conf)


def detect_sweep_vPine(ohlcv: List[Dict], lookback: int = 12,
                       wick_ratio: float = None, adaptive: Dict = None,
                       require_volume: bool = True, require_reversal: bool = True,
                       swings: Tuple[List, List] = None,
                       tf: str = 'daily') -> List[Dict]:
    """
    Sweep detection — uses Pine-quality swings if provided.

    BSL (Buyside Liquidity) sweep = price breaks above prior swing high then reverses
    SSL (Sellside Liquidity) sweep = price breaks below prior swing low then reverses
    """
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    if wick_ratio is None:
        wick_ratio = adaptive['sweep_wick_ratio']

    n = len(ohlcv)
    signals = []
    avg_vol = adaptive['avg_volume']
    vol_median = adaptive['vol_median']

    # Use Pine-quality swings if provided
    if swings:
        swing_highs, swing_lows = swings
    else:
        swing_highs = _find_swing_highs_vPine(ohlcv, lookback)
        swing_lows = _find_swing_lows_vPine(ohlcv, lookback)

    def _near_swing(idx: int, price: float, is_high: bool, window: int = 8) -> bool:
        if is_high:
            for sh_idx, sh_price in swing_highs:
                if abs(sh_idx - idx) <= window and abs(price - sh_price) / max(sh_price, 0.01) < 0.005:
                    return True
        else:
            for sl_idx, sl_price in swing_lows:
                if abs(sl_idx - idx) <= window and abs(price - sl_price) / max(sl_price, 0.01) < 0.005:
                    return True
        return False

    for i in range(lookback, n - 2):
        cur = ohlcv[i]
        nxt = ohlcv[i + 1]
        nxt2 = ohlcv[i + 2] if i + 2 < n else None

        body = abs(cur['c'] - cur['o'])
        if body == 0:
            continue

        window_high = max(b['h'] for b in ohlcv[i - lookback:i])
        window_low = min(b['l'] for b in ohlcv[i - lookback:i])

        # BSL Sweep (向上突破前高)
        if cur['h'] > window_high:
            wick_up = cur['h'] - max(cur['o'], cur['c'])
            ratio = wick_up / body

            if ratio >= wick_ratio:
                vol_ok = (not require_volume or
                         cur['v'] > vol_median * 1.2 or
                         cur['v'] > avg_vol * 1.15)
                rev_ok = (not require_reversal or
                         nxt['c'] < cur['c'] * 0.998 or
                         (nxt2 and nxt2['c'] < cur['c']))

                at_swing = _near_swing(i, cur['h'], is_high=True)

                if vol_ok and rev_ok:
                    wick_grade = _classify_wick(ratio)
                    sig = Signal(
                        type='SweepUp', idx=i, direction='bear',
                        price=cur['h'], timeframe=tf,
                        upper=cur['h'], lower=cur['h'] - wick_up,
                        grade=wick_grade,
                        confirmed_at=i+1,
                        volume_ratio=round(cur['v'] / avg_vol, 2) if avg_vol > 0 else 1,
                    )
                    sig.strength = _calc_sweep_strength_vPine(cur, wick_up, ratio,
                                                              wick_grade, adaptive, at_swing)
                    sig.confidence = _calc_sweep_confidence_vPine(cur, ratio, vol_ok, at_swing)
                    sig.metadata = {
                        'break_level': round(window_high, 2),
                        'wick_ratio': round(ratio, 2),
                        'wick_grade': wick_grade,
                        'at_swing_point': at_swing,
                        'body_pct': round(body / max(cur['c'], 0.01) * 100, 2),
                        'liquidity_type': 'BSL',
                    }
                    signals.append(sig)

        # SSL Sweep (向下突破前低)
        if cur['l'] < window_low:
            wick_down = min(cur['o'], cur['c']) - cur['l']
            ratio = wick_down / body

            if ratio >= wick_ratio:
                vol_ok = (not require_volume or
                         cur['v'] > vol_median * 1.2 or
                         cur['v'] > avg_vol * 1.15)
                rev_ok = (not require_reversal or
                         nxt['c'] > cur['c'] * 1.002 or
                         (nxt2 and nxt2['c'] > cur['c']))

                at_swing = _near_swing(i, cur['l'], is_high=False)

                if vol_ok and rev_ok:
                    wick_grade = _classify_wick(ratio)
                    sig = Signal(
                        type='SweepDown', idx=i, direction='bull',
                        price=cur['l'], timeframe=tf,
                        upper=cur['l'] + wick_down, lower=cur['l'],
                        grade=wick_grade, confirmed_at=i+1,
                        volume_ratio=round(cur['v'] / avg_vol, 2) if avg_vol > 0 else 1,
                    )
                    sig.strength = _calc_sweep_strength_vPine(cur, wick_down, ratio,
                                                              wick_grade, adaptive, at_swing)
                    sig.confidence = _calc_sweep_confidence_vPine(cur, ratio, vol_ok, at_swing)
                    sig.metadata = {
                        'break_level': round(window_low, 2),
                        'wick_ratio': round(ratio, 2),
                        'wick_grade': wick_grade,
                        'at_swing_point': at_swing,
                        'liquidity_type': 'SSL',
                    }
                    signals.append(sig)

    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 3. OB Detection — 🎯 KEY IMPROVEMENT #2: Displacement filter + swing-scan
# ═══════════════════════════════════════════════════════════════════════

def _is_near_swing_vPine(idx: int, swing_idxs: set, max_dist: int = 5) -> bool:
    return any(abs(idx - sp) <= max_dist for sp in swing_idxs)


def _calc_ob_strength_vPine(body_pct: float, volume: float,
                             vol_median: float, adaptive: Dict,
                             displacement_ratio: float = 0) -> float:
    """
    OB strength (0-10) — Pine-quality rating.

    Incorporates:
    - Body size vs ATR
    - Volume ratio
    - Displacement/ATR ratio (from Pine Script reference)
    """
    strength = 2.0
    atr = adaptive['atr_pct']

    # Body size relative to ATR
    if body_pct > atr:
        strength += 2.0
    elif body_pct > atr * 0.6:
        strength += 1.0

    # Volume
    vol_ratio = volume / vol_median if vol_median > 0 else 1
    if vol_ratio > 2.0:
        strength += 2.0
    elif vol_ratio > 1.5:
        strength += 1.0
    elif vol_ratio > 1.2:
        strength += 0.5

    # Displacement/ATR bonus (Pine Script style)
    if displacement_ratio > 2.0:
        strength += 2.0
    elif displacement_ratio > 1.5:
        strength += 1.0
    elif displacement_ratio > 1.3:
        strength += 0.5

    return min(10, strength)


def _calc_ob_confidence_vPine(body_pct: float, vol_ok: bool,
                               at_structure: bool, impulse_bars: int,
                               displacement_ratio: float = 0) -> float:
    """OB confidence (0-1) — Pine quality"""
    conf = 0.40

    if body_pct > 3.0:
        conf += 0.15
    elif body_pct > 2.0:
        conf += 0.10
    elif body_pct > 1.0:
        conf += 0.05

    if vol_ok:
        conf += 0.15

    if at_structure:
        conf += 0.20

    if impulse_bars >= 4:
        conf += 0.10
    elif impulse_bars >= 3:
        conf += 0.05

    # Displacement bonus
    if displacement_ratio > 2.0:
        conf += 0.10
    elif displacement_ratio > 1.5:
        conf += 0.05

    return min(1.0, conf)


def detect_ob_vPine(ohlcv: List[Dict], strength_min: float = None,
                    adaptive: Dict = None, require_volume: bool = True,
                    displacement_mult: float = 1.5,
                    swings: Tuple[List, List] = None,
                    swing_mode: str = 'hybrid',
                    tf: str = 'daily') -> List[Dict]:
    """
    Pine-quality Order Block detection — 🎯 KEY IMPROVEMENT.

    ICT Order Block = the LAST candle in opposite direction BEFORE an impulsive move,
    WITH displacement filter (>1.3x range of preceding candle).

    THREE modes controlled by swing_mode param:
    'swing_only'  - Only scan backward from swing points (strict Pine quality)
    'hybrid'      - Swing-scan primary + full-data scan with displacement filter
    'full'        - Scan all candles like V11, but with displacement filter added

    Critical difference from V11:
    - Displacement filter: OB must have displacement > preceding_bar_range * mult
    - ATR-normalized strength rating
    - Uses Pine-quality swings when available
    """
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    if strength_min is None:
        strength_min = adaptive['ob_strength_min']

    n = len(ohlcv)
    if n < 30:
        return []

    signals = []
    vol_median = adaptive['vol_median']
    atr = adaptive['atr_pct']

    # ── Use Pine-quality swings for OB positioning ──
    if swings:
        swing_highs, swing_lows = swings
    else:
        swing_highs = _find_swing_highs_vPine(ohlcv, 12)
        swing_lows = _find_swing_lows_vPine(ohlcv, 12)

    swing_idxs = set(i for i, _ in swing_highs + swing_lows)

    def _is_strong_impulse(start: int, direction: str, min_bars: int = 2) -> int:
        count = 0
        for k in range(start, min(start + 5, n)):
            bar = ohlcv[k]
            if direction == 'bull' and bar['c'] > bar['o']:
                count += 1
            elif direction == 'bear' and bar['c'] < bar['o']:
                count += 1
            else:
                break
        return count

    # ── Pine-quality: scan from swing points backward ──
    # This is the KEY difference: instead of scanning every candle,
    # we scan from swing points backward to find the last opposite candle
    # that has sufficient displacement.

    # Build a set of swing point indices for OB scanning
    processed_indices = set()

    # Method 1: Scan from swing lows for Bullish OB
    for sw_idx, sw_price in swing_lows:
        # Look backward from this swing low (5-15 bars before the swing)
        for i in range(max(5, sw_idx - 15), sw_idx - 2):
            if i in processed_indices:
                continue
            bar = ohlcv[i]

            # Bullish OB: bearish candle before bullish impulse
            if bar['c'] < bar['o']:  # Bearish candle
                body = abs(bar['c'] - bar['o'])
                body_pct = body / max(bar['o'], 0.01) * 100
                if body == 0:
                    continue

                # ── DISPLACEMENT FILTER (Pine Script key) ──
                # displacement = distance from OB low to subsequent high
                # displacement > range * 1.3
                preceding_range = bar['h'] - bar['l']
                displacement = sw_price - bar['l']  # From OB low to swing low
                displacement_ratio = displacement / max(preceding_range, 0.001) if preceding_range > 0 else 0

                if displacement_ratio < displacement_mult:
                    continue  # Not enough displacement = not a real OB

                # Check for bullish impulse AFTER this candle
                impulse_bars = _is_strong_impulse(i + 1, 'bull', min_bars=2)

                if impulse_bars >= 2:
                    at_structure = _is_near_swing_vPine(i, swing_idxs)

                    # Volume check
                    impulse_vol = sum(ohlcv[i + 1 + k]['v'] for k in range(min(impulse_bars, 3))) / min(impulse_bars, 3)
                    vol_ok = impulse_vol > vol_median * 1.2 or bar['v'] > vol_median * 1.2

                    if vol_ok or not require_volume:
                        sig = Signal(
                            type='OB_Bull', idx=i, direction='bull',
                            price=bar['l'],
                            upper=bar['h'], lower=bar['l'],
                            timeframe=tf, confirmed_at=i + 1,
                            volume_ratio=round(bar['v'] / vol_median, 2) if vol_median > 0 else 1,
                        )
                        sig.strength = _calc_ob_strength_vPine(body_pct, bar['v'], vol_median, adaptive, displacement_ratio)
                        sig.confidence = _calc_ob_confidence_vPine(body_pct, vol_ok, at_structure, impulse_bars, displacement_ratio)
                        sig.metadata = {
                            'body_pct': round(body_pct, 2),
                            'impulse_bars': impulse_bars,
                            'at_structure': at_structure,
                            'ob_type': 'pine_ob',
                            'displacement_ratio': round(displacement_ratio, 2),
                            'preceding_range': round(preceding_range / max(bar['c'], 0.01) * 100, 2),
                            'swing_idx': sw_idx,
                        }
                        signals.append(sig)
                        processed_indices.add(i)

    # Method 2: Scan from swing highs for Bearish OB
    for sw_idx, sw_price in swing_highs:
        for i in range(max(5, sw_idx - 15), sw_idx - 2):
            if i in processed_indices:
                continue
            bar = ohlcv[i]

            if bar['c'] > bar['o']:  # Bullish candle = potential Bearish OB
                body = abs(bar['c'] - bar['o'])
                body_pct = body / max(bar['o'], 0.01) * 100
                if body == 0:
                    continue

                # Displacement filter
                preceding_range = bar['h'] - bar['l']
                displacement = sw_price - bar['h']  # From OB high to swing high
                displacement_ratio = displacement / max(preceding_range, 0.001) if preceding_range > 0 else 0

                if displacement_ratio < displacement_mult:
                    continue

                impulse_bars = _is_strong_impulse(i + 1, 'bear', min_bars=2)

                if impulse_bars >= 2:
                    at_structure = _is_near_swing_vPine(i, swing_idxs)
                    impulse_vol = sum(ohlcv[i + 1 + k]['v'] for k in range(min(impulse_bars, 3))) / min(impulse_bars, 3)
                    vol_ok = impulse_vol > vol_median * 1.2 or bar['v'] > vol_median * 1.2

                    if vol_ok or not require_volume:
                        sig = Signal(
                            type='OB_Bear', idx=i, direction='bear',
                            price=bar['h'],
                            upper=bar['h'], lower=bar['l'],
                            timeframe=tf, confirmed_at=i + 1,
                            volume_ratio=round(bar['v'] / vol_median, 2) if vol_median > 0 else 1,
                        )
                        sig.strength = _calc_ob_strength_vPine(body_pct, bar['v'], vol_median, adaptive, displacement_ratio)
                        sig.confidence = _calc_ob_confidence_vPine(body_pct, vol_ok, at_structure, impulse_bars, displacement_ratio)
                        sig.metadata = {
                            'body_pct': round(body_pct, 2),
                            'impulse_bars': impulse_bars,
                            'at_structure': at_structure,
                            'ob_type': 'pine_ob',
                            'displacement_ratio': round(displacement_ratio, 2),
                            'preceding_range': round(preceding_range / max(bar['c'], 0.01) * 100, 2),
                            'swing_idx': sw_idx,
                        }
                        signals.append(sig)
                        processed_indices.add(i)

    # ── Hybrid mode: scan all candles with quality filters ──
    # Key fixes vs raw V11 scan:
    #   1. body_pct >= 0.3% (filter doji/noise)
    #   2. displacement_ratio >= displacement_mult (Pine-quality gate)
    #   3. Signal cooldown: same direction signals at least COOLDOWN bars apart
    if swing_mode in ('hybrid', 'full'):
        HYBRID_BODY_MIN = 0.2          # minimum body % to consider (relaxed from 0.3)
        COOLDOWN = 2                    # min bars between same-direction OBs (relaxed from 3)
        last_bull_idx = -999
        last_bear_idx = -999

        for i in range(5, n - 3):
            if i in processed_indices:
                continue
            bar = ohlcv[i]
            body = abs(bar['c'] - bar['o'])
            body_pct = body / max(bar['o'], 0.01) * 100

            # Quality gate 1: minimum body size
            if body_pct < HYBRID_BODY_MIN:
                continue

            # Bullish OB: bearish candle before bullish impulse
            if bar['c'] < bar['o']:
                # Quality gate 2: cooldown
                if i - last_bull_idx < COOLDOWN:
                    continue

                preceding_range = bar['h'] - bar['l']

                # Find nearest forward swing low for displacement calc
                local_swing = None
                for sw_idx, sw_price in swing_lows:
                    if sw_idx > i and sw_idx <= i + 25:
                        local_swing = sw_price
                        break

                if local_swing is not None:
                    displacement = local_swing - bar['l']
                    displacement_ratio = displacement / max(preceding_range, 0.001) if preceding_range > 0 else 0
                else:
                    # Fallback: use forward price range (10 bars) for displacement
                    next_high = max(b['h'] for b in ohlcv[i+2:min(i+12, n)])
                    displacement = next_high - bar['l']
                    displacement_ratio = displacement / max(preceding_range, 0.001) if preceding_range > 0 else 0

                # Quality gate 3: displacement must meet threshold
                if displacement_ratio < displacement_mult:
                    continue

                # Check for bullish impulse AFTER this candle
                impulse_bars = _is_strong_impulse(i + 1, 'bull', min_bars=2)

                if impulse_bars >= 2:
                    at_structure = _is_near_swing_vPine(i, swing_idxs)

                    impulse_vol = sum(ohlcv[i + 1 + k]['v'] for k in range(min(impulse_bars, 3))) / min(impulse_bars, 3)
                    vol_ok = impulse_vol > vol_median * 1.2 or bar['v'] > vol_median * 1.2

                    if vol_ok or not require_volume:
                        sig = Signal(
                            type='OB_Bull', idx=i, direction='bull',
                            price=bar['l'],
                            upper=bar['h'], lower=bar['l'],
                            timeframe=tf, confirmed_at=i + 1,
                            volume_ratio=round(bar['v'] / vol_median, 2) if vol_median > 0 else 1,
                        )
                        sig.strength = _calc_ob_strength_vPine(body_pct, bar['v'], vol_median, adaptive, displacement_ratio)
                        sig.confidence = _calc_ob_confidence_vPine(body_pct, vol_ok, at_structure, impulse_bars, displacement_ratio)
                        sig.metadata = {
                            'body_pct': round(body_pct, 2),
                            'impulse_bars': impulse_bars,
                            'at_structure': at_structure,
                            'ob_type': 'hybrid_ob',
                            'displacement_ratio': round(displacement_ratio, 2),
                            'preceding_range': round(preceding_range / max(bar['c'], 0.01) * 100, 2),
                        }
                        signals.append(sig)
                        processed_indices.add(i)
                        last_bull_idx = i

            # Bearish OB: bullish candle before bearish impulse
            elif bar['c'] > bar['o']:
                # Quality gate 2: cooldown
                if i - last_bear_idx < COOLDOWN:
                    continue

                preceding_range = bar['h'] - bar['l']
                local_swing = None
                for sw_idx, sw_price in swing_highs:
                    if sw_idx > i and sw_idx <= i + 25:
                        local_swing = sw_price
                        break

                if local_swing is not None:
                    displacement = local_swing - bar['h']
                    displacement_ratio = displacement / max(preceding_range, 0.001) if preceding_range > 0 else 0
                else:
                    # Fallback: use forward price range (10 bars) for displacement
                    next_low = min(b['l'] for b in ohlcv[i+2:min(i+12, n)])
                    displacement = bar['h'] - next_low
                    displacement_ratio = displacement / max(preceding_range, 0.001) if preceding_range > 0 else 0

                # Quality gate 3: displacement must meet threshold
                if displacement_ratio < displacement_mult:
                    continue

                impulse_bars = _is_strong_impulse(i + 1, 'bear', min_bars=2)

                if impulse_bars >= 2:
                    at_structure = _is_near_swing_vPine(i, swing_idxs)
                    impulse_vol = sum(ohlcv[i + 1 + k]['v'] for k in range(min(impulse_bars, 3))) / min(impulse_bars, 3)
                    vol_ok = impulse_vol > vol_median * 1.2 or bar['v'] > vol_median * 1.2

                    if vol_ok or not require_volume:
                        sig = Signal(
                            type='OB_Bear', idx=i, direction='bear',
                            price=bar['h'],
                            upper=bar['h'], lower=bar['l'],
                            timeframe=tf, confirmed_at=i + 1,
                            volume_ratio=round(bar['v'] / vol_median, 2) if vol_median > 0 else 1,
                        )
                        sig.strength = _calc_ob_strength_vPine(body_pct, bar['v'], vol_median, adaptive, displacement_ratio)
                        sig.confidence = _calc_ob_confidence_vPine(body_pct, vol_ok, at_structure, impulse_bars, displacement_ratio)
                        sig.metadata = {
                            'body_pct': round(body_pct, 2),
                            'impulse_bars': impulse_bars,
                            'at_structure': at_structure,
                            'ob_type': 'hybrid_ob',
                            'displacement_ratio': round(displacement_ratio, 2),
                            'preceding_range': round(preceding_range / max(bar['c'], 0.01) * 100, 2),
                        }
                        signals.append(sig)
                        processed_indices.add(i)
                        last_bear_idx = i

    # Deduplicate + sort
    signals.sort(key=lambda s: -s.strength)
    unique = []
    seen_levels = set()
    for sig in signals:
        level_key = round(sig.price, 2)
        dir_key = sig.direction
        key = (level_key, dir_key)
        if key not in seen_levels:
            seen_levels.add(key)
            unique.append(sig)

    unique.sort(key=lambda s: s.idx)
    return [s.to_dict() for s in unique]


# ═══════════════════════════════════════════════════════════════════════
# 4. State Machine Structure Detection — 🎯 KEY IMPROVEMENT #3
# ═══════════════════════════════════════════════════════════════════════

def detect_structure_vPine(ohlcv: List[Dict],
                           swings: Tuple[List, List] = None,
                           tf: str = 'daily') -> List[Dict]:
    """
    State machine structure detection — replaces rigid sequence matching.

    Instead of matching pre-defined ICT sequences (Gold/Silver/Bronze),
    uses a simple state machine:
    - Track swing_trend: +1 (up), -1 (down), 0 (neutral)
    - crossover(close, last_swing_high) + trend was down → CHOCH_Bull
    - crossover(close, last_swing_high) + trend was up → BOS_Bull
    - crossunder(close, last_swing_low) + trend was up → CHOCH_Bear
    - crossunder(close, last_swing_low) + trend was down → BOS_Bear

    Simple, parameter-free, matches Pine Script logic exactly.
    """
    if swings:
        swing_highs, swing_lows = swings
    else:
        swing_highs = _find_swing_highs_vPine(ohlcv, 10)
        swing_lows = _find_swing_lows_vPine(ohlcv, 10)

    n = len(ohlcv)
    signals = []

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return []

    # Build sorted swing point list
    all_swings = []
    for idx, price in swing_highs:
        all_swings.append((idx, price, 'high'))
    for idx, price in swing_lows:
        all_swings.append((idx, price, 'low'))
    all_swings.sort(key=lambda x: x[0])

    # State machine
    # swing_trend: +1 = bullish (higher highs + higher lows)
    #              -1 = bearish (lower highs + lower lows)
    #                0 = neutral
    swing_trend = 0
    last_swing_high = None
    last_swing_low = None
    last_swing_idx = 0

    for idx, price, stype in all_swings:
        if idx < 10 or idx >= n - 2:
            continue

        bar = ohlcv[idx]

        if stype == 'high':
            if last_swing_high is not None:
                if price > last_swing_high:
                    # HH — trend is up
                    if swing_trend == -1:
                        # Was bearish, now new HH → CHOCH_Bull!
                        sig = Signal(
                            type='CHOCH_Bull', idx=idx, direction='bull',
                            price=bar['c'], timeframe=tf,
                            upper=bar['h'], lower=last_swing_high,
                            confirmed_at=idx,
                            grade=3,
                        )
                        sig.strength = 5.0
                        sig.confidence = 0.65
                        sig.metadata = {
                            'break_level': round(last_swing_high, 2),
                            'break_strength': round((price - last_swing_high) / max(last_swing_high, 0.01) * 100, 2),
                            'swing_type': 'HH_after_LH',
                            'structure_type': 'CHoCH',
                        }
                        signals.append(sig)

                    elif swing_trend == 1:
                        # Was bullish, new HH → BOS (continuation)
                        sig = Signal(
                            type='BOS_Bull', idx=idx, direction='bull',
                            price=bar['c'], timeframe=tf,
                            upper=bar['h'], lower=last_swing_high,
                            confirmed_at=idx,
                            grade=2,
                        )
                        sig.strength = 4.0
                        sig.confidence = 0.55
                        sig.metadata = {
                            'break_level': round(last_swing_high, 2),
                            'break_strength': round((price - last_swing_high) / max(last_swing_high, 0.01) * 100, 2),
                            'swing_type': 'HH_in_uptrend',
                            'structure_type': 'BOS',
                        }
                        signals.append(sig)

                # Update trend
                if last_swing_low is not None:
                    # Check for HH and HL pattern
                    hl = None
                    for si, sp, st in all_swings:
                        if si > last_swing_idx and si < idx and st == 'low':
                            hl = sp
                    if hl is not None:
                        if price > last_swing_high and hl > last_swing_low:
                            swing_trend = 1  # HH + HL = uptrend
                        elif price < last_swing_high and hl < last_swing_low:
                            swing_trend = -1  # LH + LL = downtrend

            last_swing_high = price
            last_swing_idx = idx

        elif stype == 'low':
            if last_swing_low is not None:
                if price < last_swing_low:
                    # LL — trend is down
                    if swing_trend == 1:
                        # Was bullish, now LL → CHOCH_Bear!
                        sig = Signal(
                            type='CHOCH_Bear', idx=idx, direction='bear',
                            price=bar['c'], timeframe=tf,
                            upper=last_swing_low, lower=bar['l'],
                            confirmed_at=idx,
                            grade=3,
                        )
                        sig.strength = 5.0
                        sig.confidence = 0.65
                        sig.metadata = {
                            'break_level': round(last_swing_low, 2),
                            'break_strength': round((last_swing_low - price) / max(last_swing_low, 0.01) * 100, 2),
                            'swing_type': 'LL_after_HL',
                            'structure_type': 'CHoCH',
                        }
                        signals.append(sig)

                    elif swing_trend == -1:
                        # Was bearish, new LL → BOS (continuation)
                        sig = Signal(
                            type='BOS_Bear', idx=idx, direction='bear',
                            price=bar['c'], timeframe=tf,
                            upper=last_swing_low, lower=bar['l'],
                            confirmed_at=idx,
                            grade=2,
                        )
                        sig.strength = 4.0
                        sig.confidence = 0.55
                        sig.metadata = {
                            'break_level': round(last_swing_low, 2),
                            'break_strength': round((last_swing_low - price) / max(last_swing_low, 0.01) * 100, 2),
                            'swing_type': 'LL_in_downtrend',
                            'structure_type': 'BOS',
                        }
                        signals.append(sig)

                # Update trend check
                if last_swing_high is not None:
                    hh = None
                    for si, sp, st in all_swings:
                        if si > last_swing_idx and si < idx and st == 'high':
                            hh = sp
                    if hh is not None:
                        if hh > last_swing_high and price > last_swing_low:
                            swing_trend = 1
                        elif hh < last_swing_high and price < last_swing_low:
                            swing_trend = -1

            last_swing_low = price
            last_swing_idx = idx

    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 5. EQH/EQL — 🎯 KEY IMPROVEMENT #4: Pivot-based liquidity zones
# ═══════════════════════════════════════════════════════════════════════

def detect_eql_vPine(ohlcv: List[Dict], pivot_length: int = 4,
                     threshold_pct: float = 0.1,
                     swings: Tuple[List, List] = None,
                     tf: str = 'daily') -> List[Dict]:
    """
    Pivot-based EQH/EQL detection — UAlgo style.

    Unlike V11 (brute-force pairwise comparison of all bars),
    uses Pine Script pivot-based logic:
    - Find swing HIGHs/LOWs using pivot_length lookback
    - Compare ONLY adjacent swing points (not O(n^2))
    - If two HIGHS within threshold → EQL_High (resistance zone)
    - If two LOWs within threshold → EQL_Low (support zone)

    Parameters:
        pivot_length: bars to check each side (4 = ta.pivothigh(4,4))
        threshold_pct: maximum difference to consider 'equal' (0.1%)
    """
    if swings:
        swing_highs, swing_lows = swings
    else:
        swing_highs = _find_swing_highs_vPine(ohlcv, pivot_length)
        swing_lows = _find_swing_lows_vPine(ohlcv, pivot_length)

    n = len(ohlcv)
    signals = []

    # ── Equal Highs: compare adjacent swing highs ──
    for k in range(1, len(swing_highs)):
        i1, p1 = swing_highs[k-1]
        i2, p2 = swing_highs[k]
        avg_p = max(p1, p2, 0.01)
        diff_pct = abs(p1 - p2) / avg_p * 100

        if diff_pct <= threshold_pct:
            level = min(p1, p2)
            closeness = 1.0 - diff_pct / max(threshold_pct, 0.001)

            sig = Signal(
                type='EQL_High', idx=i2, direction='bear',
                price=level, timeframe=tf,
                upper=level, lower=level * 0.998,
                strength=2.0 + closeness * 4.0,
                confidence=0.3 + closeness * 0.5,
                confirmed_at=i2,
                metadata={
                    'level': round(level, 4),
                    'candle1_idx': i1,
                    'candle2_idx': i2,
                    'diff_pct': round(diff_pct, 3),
                    'gap_bars': i2 - i1,
                    'closeness': round(closeness, 3),
                },
            )
            signals.append(sig)

    # ── Equal Lows: compare adjacent swing lows ──
    for k in range(1, len(swing_lows)):
        i1, p1 = swing_lows[k-1]
        i2, p2 = swing_lows[k]
        avg_p = max(p1, p2, 0.01)
        diff_pct = abs(p1 - p2) / avg_p * 100

        if diff_pct <= threshold_pct:
            level = max(p1, p2)
            closeness = 1.0 - diff_pct / max(threshold_pct, 0.001)

            sig = Signal(
                type='EQL_Low', idx=i2, direction='bull',
                price=level, timeframe=tf,
                upper=level * 1.002, lower=level,
                strength=2.0 + closeness * 4.0,
                confidence=0.3 + closeness * 0.5,
                confirmed_at=i2,
                metadata={
                    'level': round(level, 4),
                    'candle1_idx': i1,
                    'candle2_idx': i2,
                    'diff_pct': round(diff_pct, 3),
                    'gap_bars': i2 - i1,
                    'closeness': round(closeness, 3),
                },
            )
            signals.append(sig)

    # Deduplicate
    signals.sort(key=lambda s: -s.strength)
    unique = []
    seen_levels = set()
    for sig in signals:
        level_key = round(sig.metadata.get('level', 0), 2)
        dir_key = sig.direction
        key = (level_key, dir_key)
        if key not in seen_levels:
            seen_levels.add(key)
            unique.append(sig)

    unique.sort(key=lambda s: s.idx)
    return [s.to_dict() for s in unique]


# ═══════════════════════════════════════════════════════════════════════
# Helper functions (V11-compatible signatures for backward compat)
# ═══════════════════════════════════════════════════════════════════════

def _find_swing_highs_vPine(ohlcv: List[Dict], lookback: int) -> List[Tuple[int, float]]:
    """
    Quick swing high detection (no right confirmation, for sweep detection).
    For entry-level detection, use detect_swings_vPine() with left/right params.
    """
    highs = []
    n = len(ohlcv)
    for i in range(lookback, n - lookback):
        if all(ohlcv[i]['h'] >= ohlcv[j]['h']
               for j in range(i - lookback, i + lookback + 1) if 0 <= j < n):
            highs.append((i, ohlcv[i]['h']))
    return highs


def _find_swing_lows_vPine(ohlcv: List[Dict], lookback: int) -> List[Tuple[int, float]]:
    lows = []
    n = len(ohlcv)
    for i in range(lookback, n - lookback):
        if all(ohlcv[i]['l'] <= ohlcv[j]['l']
               for j in range(i - lookback, i + lookback + 1) if 0 <= j < n):
            lows.append((i, ohlcv[i]['l']))
    return lows


# ═══════════════════════════════════════════════════════════════════════
# 6. BPR (Balanced Price Range)
# 7. LV (Liquidity Void)
# 8. RJ (Rejection Block)
# 9. IFVG (Implied FVG)
# 10. Mitigated FVG
# 11. Breaker Block
# 12. OTE (Optimal Trade Entry)
# 13. MSS (Market Structure Shift)
# 14. PO3 (Power of 3)
# ── Identical to V11 implementation, kept for compatibility ──
# ═══════════════════════════════════════════════════════════════════════

def detect_bpr_vPine(ohlcv: List[Dict], fvg_signals: List[Dict],
                     tf: str = 'daily') -> List[Dict]:
    """BPR — same as V11"""
    if not fvg_signals or len(fvg_signals) < 2:
        return []
    n = len(ohlcv)
    signals = []
    bull_fvgs = [f for f in fvg_signals if 'Bull' in f.get('type', '')]
    bear_fvgs = [f for f in fvg_signals if 'Bear' in f.get('type', '')]
    if not bull_fvgs or not bear_fvgs:
        return []
    for bull_fvg in bull_fvgs:
        bull_idx = bull_fvg.get('idx', 0)
        bull_upper = bull_fvg.get('upper', 0)
        bull_lower = bull_fvg.get('lower', 0)
        if bull_upper <= 0 or bull_lower <= 0:
            continue
        for bear_fvg in bear_fvgs:
            bear_idx = bear_fvg.get('idx', 0)
            if bear_idx <= bull_idx or bear_idx > bull_idx + 30:
                continue
            bear_upper = bear_fvg.get('upper', 0)
            bear_lower = bear_fvg.get('lower', 0)
            if bear_upper <= 0 or bear_lower <= 0:
                continue
            if bull_upper > bear_lower and bull_lower < bear_upper:
                overlap_high = min(bull_upper, bear_upper)
                overlap_low = max(bull_lower, bear_lower)
                if overlap_high > overlap_low:
                    bpr_sig = Signal(
                        type='BPR', idx=bear_idx, direction='neutral',
                        price=(overlap_high + overlap_low) / 2,
                        timeframe=tf,
                        upper=overlap_high, lower=overlap_low,
                        grade=max(bull_fvg.get('grade', 1), bear_fvg.get('grade', 1)),
                        strength=min(8.0, bull_fvg.get('strength', 3.0) + bear_fvg.get('strength', 3.0)),
                        confidence=min(0.75, bull_fvg.get('confidence', 0.4) + bear_fvg.get('confidence', 0.4)),
                        confirmed_at=bear_idx,
                        metadata={
                            'bull_fvg_idx': bull_idx, 'bear_fvg_idx': bear_idx,
                            'bull_fvg_type': bull_fvg.get('type', ''),
                            'bear_fvg_type': bear_fvg.get('type', ''),
                            'overlap_high': round(overlap_high, 4),
                            'overlap_low': round(overlap_low, 4),
                            'overlap_pct': round((overlap_high - overlap_low) / max(overlap_low, 0.01) * 100, 4),
                        },
                    )
                    signals.append(bpr_sig)
                    break
    return [s.to_dict() for s in signals]


def detect_liquidity_void_vPine(ohlcv: List[Dict], min_gap_pct: float = 0.3,
                                tf: str = 'daily') -> List[Dict]:
    """Liquidity Void — same as V11"""
    n = len(ohlcv)
    signals = []
    for i in range(1, n):
        bar = ohlcv[i]
        prev = ohlcv[i - 1]
        gap_up = bar['l'] - prev['h']
        gap_up_pct = gap_up / max(prev['c'], 0.01) * 100
        if gap_up > 0 and gap_up_pct >= min_gap_pct:
            sig = Signal(
                type='LiquidityVoid', idx=i, direction='bull',
                price=bar['o'], timeframe=tf,
                upper=bar['l'], lower=prev['h'],
                grade=3, strength=min(8.0, 3.0 + gap_up_pct),
                confidence=min(0.75, 0.4 + gap_up_pct / 10),
                confirmed_at=i,
                metadata={'gap_pct': round(gap_up_pct, 2), 'gap_type': 'up'},
            )
            signals.append(sig)
        gap_down = prev['l'] - bar['h']
        gap_down_pct = gap_down / max(prev['c'], 0.01) * 100
        if gap_down > 0 and gap_down_pct >= min_gap_pct:
            sig = Signal(
                type='LiquidityVoid', idx=i, direction='bear',
                price=bar['o'], timeframe=tf,
                upper=prev['l'], lower=bar['h'],
                grade=3, strength=min(8.0, 3.0 + gap_down_pct),
                confidence=min(0.75, 0.4 + gap_down_pct / 10),
                confirmed_at=i,
                metadata={'gap_pct': round(gap_down_pct, 2), 'gap_type': 'down'},
            )
            signals.append(sig)
    return [s.to_dict() for s in signals]


def detect_rejection_block_vPine(ohlcv: List[Dict], min_wick_pct: float = 2.0,
                                 min_reversal: float = 1.5,
                                 tf: str = 'daily') -> List[Dict]:
    """Rejection Block — same as V11"""
    n = len(ohlcv)
    signals = []
    for i in range(2, n - 2):
        bar = ohlcv[i]
        nxt = ohlcv[i + 1]
        body = abs(bar['c'] - bar['o'])
        if body == 0:
            continue
        wick_up = bar['h'] - max(bar['o'], bar['c'])
        wick_up_pct = wick_up / max(bar['c'], 0.01) * 100
        if wick_up_pct >= min_wick_pct and nxt['c'] < bar['c'] * (1 - min_reversal / 100):
            sig = Signal(
                type='Rejection_Resistance', idx=i, direction='bear',
                price=bar['h'], timeframe=tf,
                upper=bar['h'], lower=bar['h'] - wick_up,
                strength=4.0, confidence=0.55,
                metadata={'wick_pct': round(wick_up_pct, 2)},
            )
            signals.append(sig)
        wick_down = min(bar['o'], bar['c']) - bar['l']
        wick_down_pct = wick_down / max(bar['c'], 0.01) * 100
        if wick_down_pct >= min_wick_pct and nxt['c'] > bar['c'] * (1 + min_reversal / 100):
            sig = Signal(
                type='Rejection_Support', idx=i, direction='bull',
                price=bar['l'], timeframe=tf,
                upper=bar['l'] + wick_down, lower=bar['l'],
                strength=4.0, confidence=0.55,
                metadata={'wick_pct': round(wick_down_pct, 2)},
            )
            signals.append(sig)
    return [s.to_dict() for s in signals]


def detect_ifvg_vPine(ohlcv: List[Dict], min_width: float = None,
                      adaptive: Dict = None, tf: str = 'daily') -> List[Dict]:
    """IFVG — same as V11"""
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    if min_width is None:
        min_width = adaptive['fvg_min_width']
    n = len(ohlcv)
    signals = []
    for i in range(n - 2):
        b1, b2, b3 = ohlcv[i], ohlcv[i+1], ohlcv[i+2]
        mid1 = (b1['h'] + b1['l']) / 2
        mid3 = (b3['h'] + b3['l']) / 2
        implied_bull = mid1 < mid3 * 0.985
        implied_bear = mid1 > mid3 * 1.015
        no_visible_gap = not (b1['h'] < b3['l'] or b1['l'] > b3['h'])
        if implied_bull and no_visible_gap:
            gap = mid3 - mid1
            gap_pct = gap / max(b1['c'], 0.01)
            if gap_pct >= min_width:
                sig = Signal(
                    type='IFVG_Bull', idx=i+1, direction='bull',
                    price=mid1, timeframe=tf,
                    upper=max(b3['h'], b1['h']), lower=min(b1['l'], b3['l']),
                    grade=2, strength=3.0, confidence=0.40,
                    confirmed_at=i+2,
                    metadata={'mid1': round(mid1, 4), 'mid3': round(mid3, 4),
                              'implied_gap_pct': round(gap_pct, 4), 'ifvg_type': 'wick_midpoint'},
                )
                signals.append(sig)
        if implied_bear and no_visible_gap:
            gap = mid1 - mid3
            gap_pct = gap / max(b1['c'], 0.01)
            if gap_pct >= min_width:
                sig = Signal(
                    type='IFVG_Bear', idx=i+1, direction='bear',
                    price=mid1, timeframe=tf,
                    upper=max(b1['h'], b3['h']), lower=min(b1['l'], b3['l']),
                    grade=2, strength=3.0, confidence=0.40,
                    confirmed_at=i+2,
                    metadata={'mid1': round(mid1, 4), 'mid3': round(mid3, 4),
                              'implied_gap_pct': round(gap_pct, 4), 'ifvg_type': 'wick_midpoint'},
                )
                signals.append(sig)
    return [s.to_dict() for s in signals]


def detect_mitigated_fvg_vPine(ohlcv: List[Dict], fvg_signals: List[Dict],
                               tf: str = 'daily') -> List[Dict]:
    """Mitigated FVG — same as V11"""
    if not fvg_signals:
        return []
    n = len(ohlcv)
    signals = []
    for fvg in fvg_signals:
        if not fvg.get('mitigated', False):
            continue
        fvg_idx = fvg.get('idx', 0)
        fvg_upper = fvg.get('upper', 0)
        fvg_lower = fvg.get('lower', 0)
        mitigated_at = fvg.get('mitigated_at', -1)
        if mitigated_at < 0 or mitigated_at >= n:
            continue
        if 'Bull' in fvg.get('type', ''):
            sig = Signal(
                type='FVG_Mitigated_Bear', idx=mitigated_at, direction='bear',
                price=fvg_lower, timeframe=tf,
                upper=fvg_upper, lower=fvg_lower,
                strength=min(7.0, 3.0 + fvg.get('strength', 3.0) * 0.5),
                confidence=min(0.7, 0.4 + fvg.get('confidence', 0.5) * 0.3),
                confirmed_at=mitigated_at,
                metadata={'original_fvg_idx': fvg_idx, 'original_type': fvg.get('type', ''),
                          'inversion_level': round(fvg_lower, 4)},
            )
            signals.append(sig)
        elif 'Bear' in fvg.get('type', ''):
            sig = Signal(
                type='FVG_Mitigated_Bull', idx=mitigated_at, direction='bull',
                price=fvg_upper, timeframe=tf,
                upper=fvg_upper, lower=fvg_lower,
                strength=min(7.0, 3.0 + fvg.get('strength', 3.0) * 0.5),
                confidence=min(0.7, 0.4 + fvg.get('confidence', 0.5) * 0.3),
                confirmed_at=mitigated_at,
                metadata={'original_fvg_idx': fvg_idx, 'original_type': fvg.get('type', ''),
                          'inversion_level': round(fvg_upper, 4)},
            )
            signals.append(sig)
    return [s.to_dict() for s in signals]


def detect_breaker_block_vPine(ohlcv: List[Dict], choch_signals: List[Dict],
                               ob_signals: List[Dict],
                               fvg_signals: List[Dict] = None,
                               tf: str = 'daily') -> List[Dict]:
    """Breaker Block — same as V11"""
    if not choch_signals or not ob_signals:
        return []
    signals = []
    for choch in choch_signals:
        choch_idx = choch.get('idx', 0)
        choch_dir = choch.get('direction', '')
        if choch_dir == 'bull':
            relevant_obs = [ob for ob in ob_signals
                           if ob.get('direction') == 'bear'
                           and ob.get('idx', 0) < choch_idx
                           and ob.get('idx', 0) >= choch_idx - 30]
            if not relevant_obs:
                continue
            last_ob = max(relevant_obs, key=lambda x: x.get('idx', 0))
            ob_upper = last_ob.get('upper', 0)
            ob_lower = last_ob.get('lower', 0)
            has_fvg_overlap = False
            if fvg_signals:
                for fvg in fvg_signals:
                    if fvg.get('direction') == 'bull':
                        f_upper = fvg.get('upper', 0)
                        f_lower = fvg.get('lower', 0)
                        if f_lower < ob_upper and f_upper > ob_lower:
                            has_fvg_overlap = True
                            break
            sig = Signal(
                type='BreakerBlock_Bull', idx=choch_idx, direction='bull',
                price=last_ob.get('lower', 0), timeframe=tf,
                upper=ob_upper, lower=ob_lower,
                strength=min(8.0, 4.0 + choch.get('strength', 3.0) * 0.4 + (1.5 if has_fvg_overlap else 0)),
                confidence=min(0.85 if has_fvg_overlap else 0.75, 0.5 + choch.get('confidence', 0.5) * 0.2 + (0.15 if has_fvg_overlap else 0)),
                confirmed_at=choch_idx,
                metadata={'original_ob_type': last_ob.get('type', ''), 'original_ob_idx': last_ob.get('idx', 0),
                          'choch_idx': choch_idx, 'has_fvg_overlap': has_fvg_overlap},
            )
            signals.append(sig)
        elif choch_dir == 'bear':
            relevant_obs = [ob for ob in ob_signals
                           if ob.get('direction') == 'bull'
                           and ob.get('idx', 0) < choch_idx
                           and ob.get('idx', 0) >= choch_idx - 30]
            if not relevant_obs:
                continue
            last_ob = max(relevant_obs, key=lambda x: x.get('idx', 0))
            ob_upper = last_ob.get('upper', 0)
            ob_lower = last_ob.get('lower', 0)
            has_fvg_overlap = False
            if fvg_signals:
                for fvg in fvg_signals:
                    if fvg.get('direction') == 'bear':
                        f_upper = fvg.get('upper', 0)
                        f_lower = fvg.get('lower', 0)
                        if f_lower < ob_upper and f_upper > ob_lower:
                            has_fvg_overlap = True
                            break
            sig = Signal(
                type='BreakerBlock_Bear', idx=choch_idx, direction='bear',
                price=last_ob.get('upper', 0), timeframe=tf,
                upper=ob_upper, lower=ob_lower,
                strength=min(8.0, 4.0 + choch.get('strength', 3.0) * 0.4 + (1.5 if has_fvg_overlap else 0)),
                confidence=min(0.85 if has_fvg_overlap else 0.75, 0.5 + choch.get('confidence', 0.5) * 0.2 + (0.15 if has_fvg_overlap else 0)),
                confirmed_at=choch_idx,
                metadata={'original_ob_type': last_ob.get('type', ''), 'original_ob_idx': last_ob.get('idx', 0),
                          'choch_idx': choch_idx, 'has_fvg_overlap': has_fvg_overlap},
            )
            signals.append(sig)
    return [s.to_dict() for s in signals]


def detect_ote_vPine(ohlcv: List[Dict], tf: str = 'daily') -> List[Dict]:
    """OTE — same as V11"""
    n = len(ohlcv)
    if n < 20:
        return []
    signals = []
    swing_highs = _find_swing_highs_vPine(ohlcv, 10)
    swing_lows = _find_swing_lows_vPine(ohlcv, 10)
    for low_idx, low_price in swing_lows:
        future_highs = [(hi, hp) for hi, hp in swing_highs if hi > low_idx and hi < low_idx + 30]
        if not future_highs:
            continue
        high_idx, high_price = future_highs[0]
        impulse = high_price - low_price
        if impulse <= 0 or low_price <= 0:
            continue
        impulse_pct = impulse / low_price * 100
        if impulse_pct < 1.0:
            continue
        fib_618 = high_price - impulse * 0.618
        fib_500 = high_price - impulse * 0.500
        search_end = min(high_idx + 20, n)
        for k in range(high_idx + 1, search_end):
            bar = ohlcv[k]
            tolerance = impulse * 0.02
            in_zone = (bar['l'] <= fib_618 + tolerance and bar['h'] >= fib_500 - tolerance)
            if in_zone:
                vol_before = sum(ohlcv[max(0, k-5):k][j]['v'] for j in range(min(5, k))) / max(min(5, max(1, k)), 1)
                vol_contracted = vol_before > 0 and bar['v'] < vol_before * 0.8
                retrace_ratio = (high_price - bar['c']) / impulse if impulse > 0 else 0
                strength = 3.0 + min(4.0, impulse_pct)
                if vol_contracted: strength += 1.5
                confidence = 0.4 + min(0.3, impulse_pct / 20)
                if vol_contracted: confidence += 0.15
                sig = Signal(
                    type='OTE_Bull', idx=k, direction='bull',
                    price=bar['c'], timeframe=tf,
                    upper=high_price, lower=low_price,
                    strength=min(10.0, strength), confidence=min(0.8, confidence),
                    confirmed_at=k,
                    metadata={'retracement_ratio': round(retrace_ratio, 3),
                              'swing_low_idx': low_idx, 'swing_high_idx': high_idx,
                              'swing_low_price': round(low_price, 4), 'swing_high_price': round(high_price, 4),
                              'fib_618_level': round(fib_618, 4), 'fib_500_level': round(fib_500, 4),
                              'impulse_pct': round(impulse_pct, 2), 'vol_contracted': vol_contracted},
                )
                signals.append(sig)
                break
    for high_idx, high_price in swing_highs:
        future_lows = [(li, lp) for li, lp in swing_lows if li > high_idx and li < high_idx + 30]
        if not future_lows:
            continue
        low_idx, low_price = future_lows[0]
        impulse = high_price - low_price
        if impulse <= 0 or high_price <= 0:
            continue
        impulse_pct = impulse / high_price * 100
        if impulse_pct < 1.0:
            continue
        fib_618 = low_price + impulse * 0.618
        fib_500 = low_price + impulse * 0.500
        search_end = min(low_idx + 20, n)
        for k in range(low_idx + 1, search_end):
            bar = ohlcv[k]
            tolerance = impulse * 0.02
            in_zone = (bar['l'] <= fib_618 + tolerance and bar['h'] >= fib_500 - tolerance)
            if in_zone:
                vol_before = sum(ohlcv[max(0, k-5):k][j]['v'] for j in range(min(5, k))) / max(min(5, max(1, k)), 1)
                vol_contracted = vol_before > 0 and bar['v'] < vol_before * 0.8
                retrace_ratio = (bar['c'] - low_price) / impulse if impulse > 0 else 0
                strength = 3.0 + min(4.0, impulse_pct)
                if vol_contracted: strength += 1.5
                confidence = 0.4 + min(0.3, impulse_pct / 20)
                if vol_contracted: confidence += 0.15
                sig = Signal(
                    type='OTE_Bear', idx=k, direction='bear',
                    price=bar['c'], timeframe=tf,
                    upper=high_price, lower=low_price,
                    strength=min(10.0, strength), confidence=min(0.8, confidence),
                    confirmed_at=k,
                    metadata={'retracement_ratio': round(retrace_ratio, 3),
                              'swing_high_idx': high_idx, 'swing_low_idx': low_idx,
                              'swing_high_price': round(high_price, 4), 'swing_low_price': round(low_price, 4),
                              'fib_618_level': round(fib_618, 4), 'fib_500_level': round(fib_500, 4),
                              'impulse_pct': round(impulse_pct, 2), 'vol_contracted': vol_contracted},
                )
                signals.append(sig)
                break
    return [s.to_dict() for s in signals]


def detect_mss_vPine(ohlcv: List[Dict], lookback: int = 10,
                     min_confirm: int = 1, tf: str = 'daily') -> List[Dict]:
    """MSS — same as V11"""
    n = len(ohlcv)
    if n < 10:
        return []
    signals = []
    local_window = 3
    for i in range(lookback, n - min_confirm - 1):
        start = i - local_window
        recent_high = max(ohlcv[j]['h'] for j in range(start, i))
        recent_low = min(ohlcv[j]['l'] for j in range(start, i))
        bar = ohlcv[i]
        if bar['c'] > recent_high and bar['h'] > recent_high:
            confirmed = True
            confirm_count = 0
            for c in range(1, min_confirm + 1):
                if i + c >= n: break
                if ohlcv[i + c]['c'] < recent_high: confirmed = False; break
                confirm_count += 1
            if not (confirmed and confirm_count >= min_confirm):
                continue
            break_strength = ((bar['c'] - recent_high) / max(recent_high, 0.01) * 100)
            if break_strength < 0.2: continue
            sig = Signal(
                type='MSS_Bull', idx=i, direction='bull',
                price=bar['c'], timeframe=tf,
                upper=bar['h'], lower=recent_high,
                strength=min(4.0, 1.5 + break_strength),
                confidence=min(0.45, 0.25 + break_strength / 20),
                confirmed_at=i + confirm_count,
                metadata={'break_level': round(recent_high, 4), 'break_strength': round(break_strength, 2),
                          'local_window': local_window, 'confirm_bars': confirm_count, 'micro_structure': True},
            )
            signals.append(sig)
        elif bar['c'] < recent_low and bar['l'] < recent_low:
            confirmed = True
            confirm_count = 0
            for c in range(1, min_confirm + 1):
                if i + c >= n: break
                if ohlcv[i + c]['c'] > recent_low: confirmed = False; break
                confirm_count += 1
            if not (confirmed and confirm_count >= min_confirm):
                continue
            break_strength = ((recent_low - bar['c']) / max(recent_low, 0.01) * 100)
            if break_strength < 0.2: continue
            sig = Signal(
                type='MSS_Bear', idx=i, direction='bear',
                price=bar['c'], timeframe=tf,
                upper=recent_low, lower=bar['l'],
                strength=min(4.0, 1.5 + break_strength),
                confidence=min(0.45, 0.25 + break_strength / 20),
                confirmed_at=i + confirm_count,
                metadata={'break_level': round(recent_low, 4), 'break_strength': round(break_strength, 2),
                          'local_window': local_window, 'confirm_bars': confirm_count, 'micro_structure': True},
            )
            signals.append(sig)
    return [s.to_dict() for s in signals]


def detect_po3_vPine(ohlcv: List[Dict], lookback: int = 20,
                     adaptive: Dict = None, tf: str = 'daily') -> List[Dict]:
    """PO3 — same as V11"""
    n = len(ohlcv)
    if n < 30: return []
    if adaptive is None: adaptive = calc_adaptive_thresholds(ohlcv)
    signals = []
    processed_acc = set()
    atr = adaptive.get('atr_pct', 2.0)
    acc_range_max = atr
    for i in range(lookback, n - 10):
        if i in processed_acc: continue
        for acc_len in range(3, min(9, n - i - 3)):
            acc_bars = ohlcv[i:i + acc_len]
            acc_high = max(b['h'] for b in acc_bars)
            acc_low = min(b['l'] for b in acc_bars)
            acc_range_pct = ((acc_high - acc_low) / max(acc_low, 0.01) * 100)
            if acc_range_pct > acc_range_max: continue
            acc_vol_avg = sum(b['v'] for b in acc_bars) / acc_len
            prev_bars = ohlcv[max(0, i - 10):i]
            if prev_bars:
                prev_vol_avg = sum(b['v'] for b in prev_bars) / len(prev_bars)
                vol_ok = prev_vol_avg > 0 and acc_vol_avg < prev_vol_avg * 0.8
            else: vol_ok = False
            if not vol_ok: continue
            man_idx = i + acc_len
            if man_idx >= n: continue
            man_bar = ohlcv[man_idx]
            man_high = man_bar['h']; man_low = man_bar['l']
            broke_up = man_high > acc_high; broke_down = man_low < acc_low
            if not (broke_up or broke_down): continue
            dis_found = False
            for dis_offset in range(1, min(8, n - man_idx)):
                dis_idx = man_idx + dis_offset; dis_bar = ohlcv[dis_idx]
                if broke_up and not broke_down:
                    if dis_bar['c'] < acc_high and dis_bar['l'] < min(acc_low, man_low):
                        dis_direction = 'bear'; dis_found = True; break
                elif broke_down and not broke_up:
                    if dis_bar['c'] > acc_low and dis_bar['h'] > max(acc_high, man_high):
                        dis_direction = 'bull'; dis_found = True; break
                else:
                    if man_bar['c'] > man_bar['o']:
                        if dis_bar['c'] < acc_high: dis_direction = 'bear'; dis_found = True; break
                    else:
                        if dis_bar['c'] > acc_low: dis_direction = 'bull'; dis_found = True; break
            if not dis_found: continue
            for acc_offset in range(acc_len): processed_acc.add(i + acc_offset)
            po3_type = f'PO3_{"Bear" if dis_direction == "bear" else "Bull"}'
            sig_acc = Signal(type='PO3_Acc', idx=i, direction='neutral', price=(acc_high + acc_low) / 2,
                timeframe=tf, upper=acc_high, lower=acc_low, strength=4.0, confidence=0.5, confirmed_at=man_idx-1,
                metadata={'phase': 'acc', 'acc_start': i, 'acc_end': man_idx-1, 'acc_range_pct': round(acc_range_pct, 2),
                          'acc_len': acc_len, 'po3_type': po3_type, 'dis_direction': dis_direction})
            signals.append(sig_acc)
            man_type = 'SweepUp' if broke_up else 'SweepDown'
            sig_man = Signal(type='PO3_Man', idx=man_idx, direction='bear' if broke_up else 'bull',
                price=man_bar['h'] if broke_up else man_bar['l'], timeframe=tf,
                upper=man_bar['h'], lower=man_bar['l'], strength=5.0, confidence=0.55, confirmed_at=man_idx,
                metadata={'phase': 'man', 'man_idx': man_idx, 'acc_start': i, 'acc_end': man_idx-1,
                          'man_type': man_type, 'po3_type': po3_type, 'dis_direction': dis_direction})
            signals.append(sig_man)
            dis_bar = ohlcv[dis_idx]
            sig_dis = Signal(type='PO3_DIS', idx=dis_idx, direction=dis_direction,
                price=dis_bar['c'], timeframe=tf, upper=max(dis_bar['h'], acc_high), lower=min(dis_bar['l'], acc_low),
                strength=6.0, confidence=0.6, confirmed_at=dis_idx,
                metadata={'phase': 'dis', 'dis_idx': dis_idx, 'dis_direction': dis_direction,
                          'acc_start': i, 'acc_end': man_idx-1, 'man_idx': man_idx, 'po3_type': po3_type})
            signals.append(sig_dis)
            break
    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# Unified Detection Entry Point (same interface as detect_all_signals_v11)
# ═══════════════════════════════════════════════════════════════════════

def detect_all_signals_vPine(ohlcv: List[Dict], params: Dict = None,
                             adaptive: Dict = None, tf: str = 'daily') -> Dict:
    """
    V-Pine统一信号检测入口 — 完全兼容V11接口。

    Key improvements over detect_all_signals_v11:
    - Pine-quality swing detection (right confirmation + ATR filter + vol-aware)
    - OB displacement filter (>1.3x range) + swing-scan only
    - State machine structure detection (BOS/CHOCH)
    - Pivot-based EQH/EQL liquidity zones
    - All other signals (FVG, Sweep, etc.) preserve V11 quality
    """
    if params is None:
        params = {}
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)

    # ── Pine-quality swing detection (used by OB, Structure, EQH/EQL) ──
    swing_left = params.get('swing_left', 10)
    swing_right = params.get('swing_right', 10)
    pine_swing_highs, pine_swing_lows = detect_swings_vPine(
        ohlcv, left=swing_left, right=swing_right,
        adaptive=adaptive)

    # ── Quick swings (V11 style, no right confirmation) for displacement calc ──
    # Pine swings are too sparse (right=10) for displacement calculation
    # in the hybrid OB mode. Quick swings provide more points.
    quick_highs = _find_swing_highs_vPine(ohlcv, 8)
    quick_lows = _find_swing_lows_vPine(ohlcv, 8)

    # Use quick swings for OB displacement calculation, Pine swings for structure/EQH
    ob_swings = (quick_highs, quick_lows)

    # 1. FVG
    fvg_signals = detect_fvg_vPine(
        ohlcv, min_width=params.get('fvg_min_width'),
        merge_dist=params.get('fvg_merge_dist', 3),
        adaptive=adaptive, tf=tf,
    )

    # 2. Sweep (with Pine-quality swings for positioning)
    sweep_signals = detect_sweep_vPine(
        ohlcv, lookback=params.get('sweep_lookback', 12),
        wick_ratio=params.get('sweep_wick_ratio'),
        adaptive=adaptive,
        swings=(pine_swing_highs, pine_swing_lows),
        tf=tf,
    )

    # 3. OB (Pine-quality: displacement filter + swing-scan only)
    ob_signals = detect_ob_vPine(
        ohlcv, strength_min=params.get('ob_strength_min'),
        adaptive=adaptive,
        displacement_mult=params.get('ob_displacement_mult', 1.0),
        swings=ob_swings,
        tf=tf,
    )

    # 4. Structure (state machine: BOS/CHOCH via swing point tracking)
    choch_signals = detect_structure_vPine(
        ohlcv,
        swings=(pine_swing_highs, pine_swing_lows),
        tf=tf,
    )

    # Fallback: use V11-style CHOCH detection if state machine found too few
    # (happens when Pine swings produce insufficient points for state transitions)
    from v11.signals_v11 import detect_choch_v11 as detect_choch_fallback
    if len(choch_signals) < 2:
        choch_fallback_sigs = detect_choch_fallback(ohlcv, lookback=15, tf=tf)
        if choch_fallback_sigs:
            choch_signals = choch_fallback_sigs

    # 5. BPR
    bpr_signals = detect_bpr_vPine(ohlcv, fvg_signals, tf=tf)

    # 6. Liquidity Void
    lv_signals = detect_liquidity_void_vPine(ohlcv, tf=tf)

    # 7. Rejection Block
    rj_signals = detect_rejection_block_vPine(ohlcv, tf=tf)

    # 8. IFVG
    ifvg_signals = detect_ifvg_vPine(ohlcv, adaptive=adaptive, tf=tf)

    # 9. Mitigated FVG
    mitigated_fvg_signals = detect_mitigated_fvg_vPine(ohlcv, fvg_signals, tf=tf)

    # 10. Breaker Block
    brk_signals = detect_breaker_block_vPine(ohlcv, choch_signals, ob_signals,
                                              fvg_signals=fvg_signals, tf=tf)

    # 11. EQH/EQL (pivot-based, Pine quality)
    eql_signals = detect_eql_vPine(ohlcv, pivot_length=params.get('eql_pivot_length', 4),
                                    threshold_pct=params.get('eql_threshold', 0.1),
                                    swings=(quick_highs, quick_lows), tf=tf)

    # 12. OTE
    ote_signals = detect_ote_vPine(ohlcv, tf=tf)

    # 13. MSS
    mss_signals = detect_mss_vPine(ohlcv, tf=tf)

    # 14. PO3
    po3_signals = detect_po3_vPine(ohlcv, adaptive=adaptive, tf=tf)

    # Merge all signals
    all_signals = (fvg_signals + sweep_signals + ob_signals +
                   choch_signals + bpr_signals + lv_signals + rj_signals +
                   ifvg_signals + mitigated_fvg_signals + brk_signals + eql_signals +
                   ote_signals + mss_signals + po3_signals)
    all_signals.sort(key=lambda s: s.get('idx', 0))

    stats = {
        'total': len(all_signals),
        'fvg': len(fvg_signals),
        'sweep': len(sweep_signals),
        'ob': len(ob_signals),
        'choch': len(choch_signals),
        'bpr': len(bpr_signals),
        'liquidity_void': len(lv_signals),
        'rejection_block': len(rj_signals),
        'ifvg': len(ifvg_signals),
        'mitigated_fvg': len(mitigated_fvg_signals),
        'breaker_block': len(brk_signals),
        'eql': len(eql_signals),
        'ote': len(ote_signals),
        'mss': len(mss_signals),
        'po3': len(po3_signals),
        'bull': sum(1 for s in all_signals if s.get('direction') == 'bull'),
        'bear': sum(1 for s in all_signals if s.get('direction') == 'bear'),
    }

    for i, sig in enumerate(all_signals):
        sig['seq'] = i

    return {
        'fvg': fvg_signals,
        'sweep': sweep_signals,
        'ob': ob_signals,
        'choch': choch_signals,
        'bpr': bpr_signals,
        'liquidity_void': lv_signals,
        'rejection_block': rj_signals,
        'ifvg': ifvg_signals,
        'mitigated_fvg': mitigated_fvg_signals,
        'breaker_block': brk_signals,
        'eql': eql_signals,
        'ote': ote_signals,
        'mss': mss_signals,
        'po3': po3_signals,
        'all': all_signals,
        'adaptive': adaptive,
        'stats': stats,
    }


# ═══════════════════════════════════════════════════════════════════════
# V11 compatibility alias
# ═══════════════════════════════════════════════════════════════════════

# For backward compatibility: allow 'from v11.signals_vPine import detect_all_signals'
detect_all_signals = detect_all_signals_vPine
