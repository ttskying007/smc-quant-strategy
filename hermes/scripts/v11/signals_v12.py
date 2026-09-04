#!/usr/bin/env python3
"""
SMC V12 — Corrected ICT Signal Detection Engine (v2)
====================================================

Core improvements over signals_v11.py:
...
"""

import math, logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field

log = logging.getLogger('smc_v12.signals')


@dataclass
class Signal:
    """Unified signal data class — 100% compatible with V11 engine API"""
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


def calc_adaptive_thresholds(ohlcv: List[Dict]) -> Dict:
    """Calculate volatility-adaptive thresholds from OHLCV data."""
    n = len(ohlcv)
    if n < 20:
        return {'atr_pct': 2.0, 'atr_median': 2.0, 'avg_volume': 0,
                'vol_median': 0, 'vol_std': 0, 'fvg_min_width': 0.001,
                'sweep_wick_ratio': 2.0, 'ob_strength_min': 1.0,
                'volatility_class': 'medium', 'swing_min_pct': 0.5}

    ranges = [abs(b['h'] - b['l']) / max(b['c'], 0.01) * 100 for b in ohlcv[-min(60, n):]]
    ranges.sort()
    atr_median = ranges[len(ranges) // 2] if ranges else 2.0
    atr_pct = max(atr_median, 0.3)

    vols = [b['v'] for b in ohlcv[-min(60, n):]]
    vols.sort()
    vol_median = vols[len(vols) // 2] if vols else 0
    avg_vol = sum(vols) / max(len(vols), 1) if vols else 0
    vol_std = (sum((v - avg_vol) ** 2 for v in vols) / max(len(vols), 1)) ** 0.5 if vols else 0

    if atr_pct <= 1.2:
        vol_class = 'low'
        fvg_min = 0.0008; sweep_wick = 2.2; ob_min = 0.8
    elif atr_pct <= 3.5:
        vol_class = 'medium'
        fvg_min = 0.001; sweep_wick = 2.0; ob_min = 1.0
    else:
        vol_class = 'high'
        fvg_min = 0.002; sweep_wick = 1.8; ob_min = 1.2

    scale = max(0.5, min(2.0, atr_median / 2.0))
    return {
        'atr_pct': round(atr_pct, 2),
        'atr_median': round(atr_median, 2),
        'avg_volume': round(avg_vol, 0),
        'vol_median': round(vol_median, 0),
        'vol_std': round(vol_std, 0),
        'fvg_min_width': round(fvg_min * scale, 5),
        'sweep_wick_ratio': sweep_wick,
        'ob_strength_min': round(ob_min * scale, 2),
        'volatility_class': vol_class,
        'swing_min_pct': round(max(0.3, atr_pct * 0.3), 2),
    }


# ═══════════════════════════════════════════════════════════════════════
# 1. PINE-QUALITY SWING DETECTION
# ═══════════════════════════════════════════════════════════════════════

def detect_swings_v12(ohlcv: List[Dict], left: int = 8, right: int = 3,
                      min_swing_pct: float = None, adaptive: Dict = None,
                      vol_invert: bool = True) -> Tuple[List, List]:
    """Pine-equivalent swing detection with RIGHT CONFIRMATION."""
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    if min_swing_pct is None:
        min_swing_pct = adaptive.get('swing_min_pct', 0.5)

    n = len(ohlcv)
    atr_pct = adaptive['atr_pct']
    atr_threshold = atr_pct * 2.0
    swing_highs, swing_lows = [], []

    for i in range(left + right, n - 1):
        bar = ohlcv[i]
        rng_pct = (bar['h'] - bar['l']) / max(bar['l'], 0.01) * 100
        hi_vol = rng_pct >= atr_threshold and vol_invert
        eh = bar['l'] if hi_vol else bar['h']
        el = bar['h'] if hi_vol else bar['l']

        is_high = True
        for j in range(i - left, i + right + 1):
            if j == i or j >= n: continue
            jb = ohlcv[j]; jv = (jb['h'] - jb['l']) / max(jb['l'], 0.01) * 100 >= atr_threshold
            jh = jb['l'] if (vol_invert and jv) else jb['h']
            if j < i and jh >= eh: is_high = False; break
            if j > i and jh > eh: is_high = False; break
        if is_high:
            mp = min(ohlcv[max(0,i-left)]['l'], bar['l'])
            sr = (eh - mp) / max(mp, 0.01) * 100
            if sr >= min_swing_pct or len(swing_highs) < 2:
                swing_highs.append((i, bar['h']))

        is_low = True
        for j in range(i - left, i + right + 1):
            if j == i or j >= n: continue
            jb = ohlcv[j]; jv = (jb['h'] - jb['l']) / max(jb['l'], 0.01) * 100 >= atr_threshold
            jl = jb['h'] if (vol_invert and jv) else jb['l']
            if j < i and jl <= el: is_low = False; break
            if j > i and jl < el: is_low = False; break
        if is_low:
            mp = max(ohlcv[max(0,i-left)]['h'], bar['h'])
            sr = (mp - el) / max(el, 0.01) * 100
            if sr >= min_swing_pct or len(swing_lows) < 2:
                swing_lows.append((i, bar['l']))

    return swing_highs, swing_lows


def detect_swings_v13_60min(ohlcv: List[Dict], left: int = 10, right: int = 2,
                            adaptive: Dict = None) -> Tuple[List, List]:
    """60min-optimized swing detection — right=2, ATR=1.0x.
    
    Pine Script reference (Waves Ultimate): pivotlookback with right_bars=2.
    For 60min data, right=2 finds more valid swing points than right=3.
    ATR inversion threshold reduced to 1.0x (from 2.0x in V12 daily) for 60min noise.
    """
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    n = len(ohlcv)
    atr_pct = adaptive['atr_pct']
    atr_threshold = atr_pct * 1.0  # 1x ATR for 60min (vs 2x daily)
    swing_highs, swing_lows = [], []

    for i in range(left + right, n - 1):
        bar = ohlcv[i]
        rng_pct = (bar['h'] - bar['l']) / max(bar['l'], 0.01) * 100
        hi_vol = rng_pct >= atr_threshold
        eh = bar['l'] if hi_vol else bar['h']
        el = bar['h'] if hi_vol else bar['l']

        # Swing high check
        is_high = True
        for j in range(i - left, i + right + 1):
            if j == i or j >= n: continue
            jb = ohlcv[j]; jv = (jb['h'] - jb['l']) / max(jb['l'], 0.01) * 100 >= atr_threshold
            jh = jb['l'] if jv else jb['h']
            if j < i and jh >= eh - 0.001: is_high = False; break
            if j > i and jh > eh - 0.001: is_high = False; break
        if is_high:
            swing_highs.append((i, bar['h']))

        # Swing low check
        is_low = True
        for j in range(i - left, i + right + 1):
            if j == i or j >= n: continue
            jb = ohlcv[j]; jv = (jb['h'] - jb['l']) / max(jb['l'], 0.01) * 100 >= atr_threshold
            jl = jb['h'] if jv else jb['l']
            if j < i and jl <= el + 0.001: is_low = False; break
            if j > i and jl < el + 0.001: is_low = False; break
        if is_low:
            swing_lows.append((i, bar['l']))

    return swing_highs, swing_lows


def _quick_sh(ohlcv, lb=8):
    n = len(ohlcv)
    return [(i, ohlcv[i]['h']) for i in range(lb, n-lb) if all(ohlcv[i]['h'] >= ohlcv[j]['h'] for j in range(i-lb, i+lb+1) if 0 <= j < n)]

def _quick_sl(ohlcv, lb=8):
    n = len(ohlcv)
    return [(i, ohlcv[i]['l']) for i in range(lb, n-lb) if all(ohlcv[i]['l'] <= ohlcv[j]['l'] for j in range(i-lb, i+lb+1) if 0 <= j < n)]


# ═══════════════════════════════════════════════════════════════════════
# 2. CORRECTED ICT ORDER BLOCK DETECTION
# ═══════════════════════════════════════════════════════════════════════
#
# V12 KEY FIX:
# V11 scans EVERY candle → produces OBs at wrong positions (2-5 bar offset)
# → causes 1-bar holds (entry at wrong location)
#
# V12: scan BACKWARD from SWING POINTS only
#
# Bullish OB (scan backward from SWING HIGH):
#   Phase 1: Skip pullback bars (bearish at the top)
#   Phase 2: Find bullish impulse bars (the run-up to the high)
#   Phase 3: The bearish bar BEFORE the impulse = Bullish OB
#
#   Sequence: ↓↓↓ (bearish OB) → ↑↑↑ (bullish impulse) → up to swing high
#
# Bearish OB (scan backward from SWING LOW):
#   Phase 1: Skip bounce bars (bullish at the bottom)  
#   Phase 2: Find bearish impulse bars (the drop to the low)
#   Phase 3: The bullish bar BEFORE the impulse = Bearish OB
#
#   Sequence: ↑↑↑ (bullish OB) → ↓↓↓ (bearish impulse) → down to swing low
# ═══════════════════════════════════════════════════════════════════════

def detect_ob_v12(ohlcv: List[Dict], strength_min: float = None,
                  adaptive: Dict = None, require_volume: bool = True,
                  displacement_mult: float = 1.3,
                  swings: Tuple[List, List] = None,
                  tf: str = 'daily', body_pct_min: float = None) -> List[Dict]:
    """CORRECTED ICT Order Block detection using backward swing scan."""
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    if strength_min is None:
        strength_min = adaptive['ob_strength_min']
    if body_pct_min is None:
        body_pct_min = 0.15  # default for daily

    n = len(ohlcv)
    if n < 30:
        return []

    signals = []
    vol_median = adaptive['vol_median']

    if swings:
        swing_highs, swing_lows = swings
    else:
        sw = detect_swings_v12(ohlcv)
        swing_highs, swing_lows = sw[0], sw[1]

    all_swing_idxs = set(i for i, _ in swing_highs + swing_lows)
    processed = set()

    def _near_swing(idx, w=5):
        return any(abs(idx - si) <= w for si in all_swing_idxs)

    # ────────────────────────────────────────────────────────────────────
    # BULLISH OB: scan backward from SWING HIGH
    # ────────────────────────────────────────────────────────────────────
    for sh_idx, sh_price in swing_highs:
        if sh_idx < 5:
            continue

        phase = 'skip'          # Phase 1: skip bearish pullback at the top
        impulse_len = 0
        ob_idx = None

        for bi in range(sh_idx - 1, max(sh_idx - 25, 4), -1):
            bar = ohlcv[bi]
            is_bear = bar['c'] < bar['o']
            is_bull = bar['c'] > bar['o']

            if phase == 'skip':
                if is_bear:
                    continue  # Still in pullback zone
                elif is_bull:
                    phase = 'impulse'
                    impulse_len = 1
                else:
                    continue  # doji

            elif phase == 'impulse':
                if is_bull:
                    impulse_len += 1
                    continue
                elif is_bear:
                    # Found the OB bar BEFORE the impulse!
                    ob_idx = bi
                    break
                else:
                    # doji — count as impulse extension, keep scanning backward
                    impulse_len += 1
                    continue

        if ob_idx is None or impulse_len < 1:
            continue

        # Validate OB candidate
        ob_bar = ohlcv[ob_idx]
        body_pct = abs(ob_bar['c'] - ob_bar['o']) / max(ob_bar['o'], 0.01) * 100
        if body_pct < body_pct_min:  # Allow very small bodies if displacement is high
            continue

        bar_range = ob_bar['h'] - ob_bar['l']
        if bar_range <= 0:
            continue

        displacement = sh_price - ob_bar['l']
        dis_ratio = displacement / bar_range

        if dis_ratio < displacement_mult:
            continue

        # Volume check on impulse
        impulse_end = ob_idx + impulse_len + 1
        impulse_vols = [ohlcv[j]['v'] for j in range(ob_idx + 1, min(impulse_end + 1, n))]
        avg_imp_v = sum(impulse_vols) / max(len(impulse_vols), 1)
        vol_ok = avg_imp_v > vol_median * 1.2 or ob_bar['v'] > vol_median * 1.2

        if vol_ok or not require_volume:
            at_structure = _near_swing(ob_idx)

            sig = Signal(
                type='OB_Bull', idx=ob_idx, direction='bull',
                price=ob_bar['l'], upper=ob_bar['h'], lower=ob_bar['l'],
                timeframe=tf, confirmed_at=ob_idx + 1,
                volume_ratio=round(ob_bar['v'] / max(vol_median, 1), 2),
            )
            sig.strength = min(10, 2.0 + max(0, dis_ratio - 1.0) * 2 + min(3, impulse_len * 0.5))
            sig.confidence = min(0.95, 0.35 + dis_ratio * 0.06 + (0.10 if vol_ok else 0) + (0.15 if at_structure else 0))
            sig.metadata = {
                'body_pct': round(body_pct, 2),
                'impulse_bars': impulse_len,
                'at_structure': at_structure,
                'displacement_ratio': round(dis_ratio, 2),
                'swing_high_idx': sh_idx,
                'swing_high_price': round(sh_price, 2),
                'ob_method': 'swing_backward_v2',
                'preceding_range': round(bar_range / max(ob_bar['c'], 0.01) * 100, 2),
            }
            signals.append(sig)
            processed.add(ob_idx)

    # ────────────────────────────────────────────────────────────────────
    # BEARISH OB: scan backward from SWING LOW
    # ────────────────────────────────────────────────────────────────────
    for sl_idx, sl_price in swing_lows:
        if sl_idx < 5:
            continue

        phase = 'skip'
        impulse_len = 0
        ob_idx = None

        for bi in range(sl_idx - 1, max(sl_idx - 25, 4), -1):
            if bi in processed:
                continue

            bar = ohlcv[bi]
            is_bull = bar['c'] > bar['o']
            is_bear = bar['c'] < bar['o']

            if phase == 'skip':
                if is_bull:
                    continue  # Still in bounce zone at bottom
                elif is_bear:
                    phase = 'impulse'
                    impulse_len = 1
                else:
                    continue

            elif phase == 'impulse':
                if is_bear:
                    impulse_len += 1
                    continue
                elif is_bull:
                    ob_idx = bi
                    break
                else:
                    # doji — keep scanning backward, not a valid OB
                    continue

        if ob_idx is None or impulse_len < 1:
            continue

        ob_bar = ohlcv[ob_idx]
        body_pct = abs(ob_bar['c'] - ob_bar['o']) / max(ob_bar['o'], 0.01) * 100
        if body_pct < body_pct_min:
            continue

        bar_range = ob_bar['h'] - ob_bar['l']
        if bar_range <= 0:
            continue

        displacement = ob_bar['h'] - sl_price
        dis_ratio = displacement / bar_range

        if dis_ratio < displacement_mult:
            continue

        impulse_end = ob_idx + impulse_len + 1
        impulse_vols = [ohlcv[j]['v'] for j in range(ob_idx + 1, min(impulse_end + 1, n))]
        avg_imp_v = sum(impulse_vols) / max(len(impulse_vols), 1)
        vol_ok = avg_imp_v > vol_median * 1.2 or ob_bar['v'] > vol_median * 1.2

        if vol_ok or not require_volume:
            at_structure = _near_swing(ob_idx)

            sig = Signal(
                type='OB_Bear', idx=ob_idx, direction='bear',
                price=ob_bar['h'], upper=ob_bar['h'], lower=ob_bar['l'],
                timeframe=tf, confirmed_at=ob_idx + 1,
                volume_ratio=round(ob_bar['v'] / max(vol_median, 1), 2),
            )
            sig.strength = min(10, 2.0 + max(0, dis_ratio - 1.0) * 2 + min(3, impulse_len * 0.5))
            sig.confidence = min(0.95, 0.35 + dis_ratio * 0.06 + (0.10 if vol_ok else 0) + (0.15 if at_structure else 0))
            sig.metadata = {
                'body_pct': round(body_pct, 2),
                'impulse_bars': impulse_len,
                'at_structure': at_structure,
                'displacement_ratio': round(dis_ratio, 2),
                'swing_low_idx': sl_idx,
                'swing_low_price': round(sl_price, 2),
                'ob_method': 'swing_backward_v2',
                'preceding_range': round(bar_range / max(ob_bar['c'], 0.01) * 100, 2),
            }
            signals.append(sig)
            processed.add(ob_idx)

    # ────────────────────────────────────────────────────────────────────────
    # CONSTRAINED FORWARD FALLBACK — only for 60min/tight data where
    # swing-backward might find too few OBs.
    #
    # Rules (stricter than the old hybrid pass):
    #   1. Must be within 8 bars of a swing point (positional validation)
    #   2. body_pct >= 0.3 (stricter than backward's 0.15)
    #   3. displacement_ratio >= 1.0 (reduced for 60min noise)
    #   4. Impulse must start in the NEXT bar (position correction —
    #      verifies OB candle is NOT inside the impulse run)
    #   5. At least 1 impulse bar
    #   6. Must not duplicate backward OBs
    # ────────────────────────────────────────────────────────────────────────
    if len(signals) < 3:  # swing-backward found very few, add constrained forward
        quick_sh = _quick_sh(ohlcv, 8)
        quick_sl = _quick_sl(ohlcv, 8)
        swing_near_idxs = set(i for i, _ in quick_sh + quick_sl)

        for i in range(5, n - 3):
            if i in processed:
                continue
            bar = ohlcv[i]
            body = abs(bar['c'] - bar['o'])
            if body == 0:
                continue
            body_pct = body / max(bar['o'], 0.01) * 100
            if body_pct < 0.3:  # stricter than backward
                continue
            bar_range = bar['h'] - bar['l']

            # Positional check: must be near a swing point
            near_sw = any(abs(i - si) <= 8 for si in swing_near_idxs)
            if not near_sw:
                continue

            # Bullish OB: bearish candle
            if bar['c'] < bar['o']:
                # Forward displacement check
                max_fwd = max(b['h'] for b in ohlcv[i+1:min(i+15, n)])
                displacement = max_fwd - bar['l']
                dis_ratio = displacement / max(bar_range, 0.001)

                if dis_ratio >= 1.0:
                    # Position correction: impulse must start at i+1
                    if ohlcv[i+1]['c'] <= ohlcv[i+1]['o']:
                        continue  # impulse didn't start next bar = wrong position

                    imp = 0
                    for j in range(i+1, min(i+8, n)):
                        if ohlcv[j]['c'] > ohlcv[j]['o']:
                            imp += 1
                        else:
                            break

                    if imp >= 1:
                        fwd_vols = [ohlcv[j]['v'] for j in range(i+1, min(i+imp+2, n))]
                        avg_fv = sum(fwd_vols) / max(len(fwd_vols), 1)
                        vol_ok = avg_fv > vol_median * 1.0 or bar['v'] > vol_median * 1.0

                        if vol_ok or not require_volume:
                            sig = Signal(
                                type='OB_Bull', idx=i, direction='bull',
                                price=bar['l'], upper=bar['h'], lower=bar['l'],
                                timeframe=tf, confirmed_at=i + 1,
                                volume_ratio=round(bar['v'] / max(vol_median, 1), 2),
                            )
                            sig.strength = min(8, 1.5 + dis_ratio * 1.5 + min(2, imp * 0.5))
                            sig.confidence = min(0.80, 0.25 + dis_ratio * 0.04 + (0.08 if vol_ok else 0))
                            sig.metadata = {
                                'body_pct': round(body_pct, 2),
                                'impulse_bars': imp,
                                'at_structure': True,
                                'displacement_ratio': round(dis_ratio, 2),
                                'ob_method': 'constrained_forward',
                                'preceding_range': round(bar_range / max(bar['c'], 0.01) * 100, 2),
                            }
                            signals.append(sig)
                            processed.add(i)

            # Bearish OB: bullish candle
            elif bar['c'] > bar['o']:
                min_fwd = min(b['l'] for b in ohlcv[i+1:min(i+15, n)])
                displacement = bar['h'] - min_fwd
                dis_ratio = displacement / max(bar_range, 0.001)

                if dis_ratio >= 1.0:
                    if ohlcv[i+1]['c'] >= ohlcv[i+1]['o']:
                        continue

                    imp = 0
                    for j in range(i+1, min(i+8, n)):
                        if ohlcv[j]['c'] < ohlcv[j]['o']:
                            imp += 1
                        else:
                            break

                    if imp >= 1:
                        fwd_vols = [ohlcv[j]['v'] for j in range(i+1, min(i+imp+2, n))]
                        avg_fv = sum(fwd_vols) / max(len(fwd_vols), 1)
                        vol_ok = avg_fv > vol_median * 1.0 or bar['v'] > vol_median * 1.0
                        if vol_ok or not require_volume:
                            sig = Signal(
                                type='OB_Bear', idx=i, direction='bear',
                                price=bar['h'], upper=bar['h'], lower=bar['l'],
                                timeframe=tf, confirmed_at=i + 1,
                                volume_ratio=round(bar['v'] / max(vol_median, 1), 2),
                            )
                            sig.strength = min(8, 1.5 + dis_ratio * 1.5 + min(2, imp * 0.5))
                            sig.confidence = min(0.80, 0.25 + dis_ratio * 0.04 + (0.08 if vol_ok else 0))
                            sig.metadata = {
                                'body_pct': round(body_pct, 2),
                                'impulse_bars': imp,
                                'at_structure': True,
                                'displacement_ratio': round(dis_ratio, 2),
                                'ob_method': 'constrained_forward',
                                'preceding_range': round(bar_range / max(bar['c'], 0.01) * 100, 2),
                            }
                            signals.append(sig)
                            processed.add(i)

    # Deduplicate: keep strongest OB per price level
    signals.sort(key=lambda s: -s.strength)
    unique = []
    seen = set()
    for s in signals:
        key = (round(s.price, 2), s.direction)
        if key not in seen:
            seen.add(key)
            unique.append(s)

    unique.sort(key=lambda s: s.idx)
    return [s.to_dict() for s in unique]


# ═══════════════════════════════════════════════════════════════════════
# 3. STATE MACHINE STRUCTURE
# ═══════════════════════════════════════════════════════════════════════

def detect_structure_v12(ohlcv: List[Dict],
                         swings: Tuple[List, List] = None,
                         tf: str = 'daily') -> List[Dict]:
    """State machine BOS/CHOCH detection."""
    if swings:
        swing_highs, swing_lows = swings
    else:
        sh, sl = detect_swings_v12(ohlcv)
        swing_highs, swing_lows = sh, sl

    n = len(ohlcv)
    signals = []

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return []

    av = []
    for i, p in swing_highs: av.append((i, p, 'h'))
    for i, p in swing_lows: av.append((i, p, 'l'))
    av.sort(key=lambda x: x[0])

    trend = 0
    lsh = lsh_i = lsl = lsl_i = lsi = None

    def _find_between(sw, si, ei):
        for i, p, t in av:
            if si < i < ei and t == sw:
                return p
        return None

    for idx, price, st in av:
        if idx < 10 or idx >= n - 2:
            continue
        bar = ohlcv[idx]

        if st == 'h':
            if lsh is not None:
                if price > lsh:
                    hl = _find_between('l', lsi if lsi is not None else -1, idx) if trend == -1 else None
                    bp = (price - lsh) / max(lsh, 0.01) * 100
                    if trend == -1:
                        sig = Signal(type='CHOCH_Bull', idx=idx, direction='bull', price=bar['c'],
                                     timeframe=tf, upper=bar['h'], lower=lsh, confirmed_at=idx, grade=3)
                        sig.strength = min(10, 3.0 + bp * 2); sig.confidence = min(0.85, 0.45 + bp * 0.02)
                        sig.metadata = {'break_level': round(lsh,2), 'break_strength': round(bp,2),
                                        'swing_type': 'HH_after_LH', 'structure_type': 'CHoCH'}
                        signals.append(sig)
                    elif trend == 1:
                        sig = Signal(type='BOS_Bull', idx=idx, direction='bull', price=bar['c'],
                                     timeframe=tf, upper=bar['h'], lower=lsh, confirmed_at=idx, grade=2)
                        sig.strength = min(8, 2.5 + bp); sig.confidence = min(0.75, 0.35 + bp * 0.01)
                        sig.metadata = {'break_level': round(lsh,2), 'break_strength': round(bp,2),
                                        'swing_type': 'HH_in_uptrend', 'structure_type': 'BOS'}
                        signals.append(sig)

            if lsl is not None:
                hl = _find_between('l', lsi if lsi is not None else -1, idx)
                if hl is not None:
                    if price > lsh and hl > lsl: trend = 1
                    elif price < lsh and hl < lsl: trend = -1

            lsh, lsh_i, lsi = price, idx, idx

        elif st == 'l':
            if lsl is not None:
                if price < lsl:
                    bp = (lsl - price) / max(lsl, 0.01) * 100
                    if trend == 1:
                        sig = Signal(type='CHOCH_Bear', idx=idx, direction='bear', price=bar['c'],
                                     timeframe=tf, upper=lsl, lower=bar['l'], confirmed_at=idx, grade=3)
                        sig.strength = min(10, 3.0 + bp * 2); sig.confidence = min(0.85, 0.45 + bp * 0.02)
                        sig.metadata = {'break_level': round(lsl,2), 'break_strength': round(bp,2),
                                        'swing_type': 'LL_after_HL', 'structure_type': 'CHoCH'}
                        signals.append(sig)
                    elif trend == -1:
                        sig = Signal(type='BOS_Bear', idx=idx, direction='bear', price=bar['c'],
                                     timeframe=tf, upper=lsl, lower=bar['l'], confirmed_at=idx, grade=2)
                        sig.strength = min(8, 2.5 + bp); sig.confidence = min(0.75, 0.35 + bp * 0.01)
                        sig.metadata = {'break_level': round(lsl,2), 'break_strength': round(bp,2),
                                        'swing_type': 'LL_in_downtrend', 'structure_type': 'BOS'}
                        signals.append(sig)

            if lsh is not None:
                hh = _find_between('h', lsi if lsi is not None else -1, idx)
                if hh is not None:
                    if hh > lsh and price > lsl: trend = 1
                    elif hh < lsh and price < lsl: trend = -1

            lsl, lsl_i, lsi = price, idx, idx

    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 4. FVG Detection
# ═══════════════════════════════════════════════════════════════════════

def detect_fvg_v12(ohlcv: List[Dict], min_width: float = None,
                   merge_dist: int = 3, adaptive: Dict = None,
                   tf: str = 'daily') -> List[Dict]:
    """FVG detection — maintained from V11."""
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    if min_width is None:
        min_width = adaptive.get('fvg_min_width', 0.001)

    n = len(ohlcv)
    signals = []
    atr_pct = adaptive.get('atr_pct', 2.0)

    for i in range(n - 2):
        b1, b2, b3 = ohlcv[i], ohlcv[i+1], ohlcv[i+2]
        ab1, ab2, ab3 = b1['c'] < b1['o'], b2['c'] < b2['o'], b3['c'] < b3['o']
        a1b, a2b, a3b = b1['c'] > b1['o'], b2['c'] > b2['o'], b3['c'] > b3['o']
        all_bear = ab1 and ab2 and ab3
        all_bull = a1b and a2b and a3b
        c2b = abs(b2['c'] - b2['o']) / max(b2['c'], 0.01) * 100
        c2ok = c2b >= atr_pct * 0.6

        if b1['h'] < b3['l']:
            gp = (b3['l'] - b1['h']) / max(b1['c'], 0.01) * 100
            if gp >= min_width and (c2ok or all_bear):
                gv = 1
                rt = gp / max(atr_pct / 100, 0.001)
                if rt > 1.5: gv = 4
                elif rt > 0.8: gv = 3
                elif rt > 0.3: gv = 2
                if all_bear: gv = max(gv, 3)
                ta_ = _trend_ok(ohlcv, i, 'bull')
                s = Signal(type='FVG_Bull', idx=i+1, direction='bull', price=(b1['h']+b3['l'])/2,
                           upper=b3['l'], lower=b1['h'], timeframe=tf, grade=gv, trend_aligned=ta_, confirmed_at=i+2)
                s.strength = 2.0 + (gv-1)*1.5
                s.confidence = 0.4 + (gv-1)*0.1 + (0.1 if c2ok else 0)
                if all_bear:
                    s.confidence = min(1.0, s.confidence + 0.15); s.strength = min(10, s.strength + 2.0)
                s.metadata = {'gap_pct': round(gp,4), 'consecutive_bearish': all_bear}
                signals.append(s)

        elif b1['l'] > b3['h']:
            gp = (b1['l'] - b3['h']) / max(b1['c'], 0.01) * 100
            if gp >= min_width and (c2ok or all_bull):
                gv = 1
                rt = gp / max(atr_pct / 100, 0.001)
                if rt > 1.5: gv = 4
                elif rt > 0.8: gv = 3
                elif rt > 0.3: gv = 2
                if all_bull: gv = max(gv, 3)
                ta_ = _trend_ok(ohlcv, i, 'bear')
                s = Signal(type='FVG_Bear', idx=i+1, direction='bear', price=(b1['l']+b3['h'])/2,
                           upper=b1['l'], lower=b3['h'], timeframe=tf, grade=gv, trend_aligned=ta_, confirmed_at=i+2)
                s.strength = 2.0 + (gv-1)*1.5
                s.confidence = 0.4 + (gv-1)*0.1 + (0.1 if c2ok else 0)
                if all_bull:
                    s.confidence = min(1.0, s.confidence + 0.15); s.strength = min(10, s.strength + 2.0)
                s.metadata = {'gap_pct': round(gp,4), 'consecutive_bullish': all_bull}
                signals.append(s)

    if merge_dist > 0 and signals:
        merged = [signals[0]]
        for s in signals[1:]:
            l = merged[-1]
            if s.direction == l.direction and s.idx - l.idx <= merge_dist + 2:
                l.upper = max(l.upper, s.upper); l.lower = min(l.lower, s.lower)
                l.price = (l.upper + l.lower) / 2; l.grade = max(l.grade, s.grade)
                l.strength = max(l.strength, s.strength); l.confidence = max(l.confidence, s.confidence)
                l.idx = (l.idx + s.idx) // 2
            else:
                merged.append(s)
        signals = merged

    for s in signals:
        idx = s.idx
        s.metadata['mitigated'] = False; s.metadata['mitigated_at'] = None
        for j in range(idx+1, min(idx+50, n)):
            if (s.direction == 'bull' and ohlcv[j]['l'] <= s.upper) or \
               (s.direction == 'bear' and ohlcv[j]['h'] >= s.lower):
                s.metadata['mitigated'] = True; s.metadata['mitigated_at'] = j; break

    return [s.to_dict() for s in signals]


def _trend_ok(ohlcv, idx, direction):
    if idx < 5: return True
    lb = min(8, idx)
    ch = (ohlcv[idx]['c'] - ohlcv[idx-lb]['c']) / max(ohlcv[idx-lb]['c'], 0.01) * 100
    if direction == 'bull': return ch > -0.5
    return ch < 0.5


# ═══════════════════════════════════════════════════════════════════════
# 5. Sweep Detection
# ═══════════════════════════════════════════════════════════════════════

def detect_sweep_v12(ohlcv: List[Dict], lookback: int = 8,
                     wick_ratio: float = None, adaptive: Dict = None,
                     require_volume: bool = True, require_reversal: bool = True,
                     swings: Tuple[List, List] = None,
                     tf: str = 'daily') -> List[Dict]:
    """
    Swing-point level sweep detection — fixed for signal correctness.

    V11 problem: scanned EVERY candle for local window breaks — produced sweeps
    at random locations, not at real structure points.

    V12 fix: scan FROM confirmed swing points. For each swing high/low,
    look within 20 bars for a candle that breaks through and reverses.
    Only sweeps AT structure levels are real liquidity hunts.
    """
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    if wick_ratio is None:
        wick_ratio = adaptive.get('sweep_wick_ratio', 2.0)

    n = len(ohlcv)
    signals = []
    vol_median = adaptive['vol_median']
    avg_vol = adaptive['avg_volume']

    if swings:
        sh, sl = swings
    else:
        sh = _quick_sh(ohlcv, lookback)
        sl = _quick_sl(ohlcv, lookback)

    # Build price:idx map for quick lookup
    swing_prices_h = {p: i for i, p in sh}
    swing_prices_l = {p: i for i, p in sl}

    # ── BSL Sweep: scan forward from each swing high ──
    for sw_idx, sw_price in sh:
        scan_end = min(sw_idx + 20, n)
        for j in range(sw_idx + 1, scan_end):
            bar = ohlcv[j]
            body = abs(bar['c'] - bar['o'])
            if body == 0:
                continue

            if bar['h'] > sw_price:
                wick = bar['h'] - max(bar['o'], bar['c'])
                ratio = wick / body

                if ratio >= wick_ratio:
                    nxt_idx = j + 1
                    vok = (not require_volume or
                           bar['v'] > vol_median * 1.2 or
                           bar['v'] > avg_vol * 1.15)
                    rok = (not require_reversal or
                           (nxt_idx < n and ohlcv[nxt_idx]['c'] < bar['c'] * 0.998) or
                           (nxt_idx + 1 < n and ohlcv[nxt_idx + 1]['c'] < bar['c']))

                    if vok and rok:
                        sig = Signal(
                            type='Sweep', idx=j, direction='bull',
                            price=bar['h'], timeframe=tf,
                            upper=bar['h'], lower=bar['h'] - wick,
                            confirmed_at=j + 1, grade=3,
                        )
                        sig.strength = min(10, 3.0 + (ratio / wick_ratio) * 3)
                        sig.confidence = min(0.85, 0.35 + (ratio / wick_ratio) * 0.2)
                        sig.metadata = {
                            'wick_ratio': round(ratio, 2),
                            'sweep_type': 'BSL',
                            'liquidity_type': 'BSL',
                            'break_price': round(sw_price, 2),
                            'swing_idx': sw_idx,
                            'volume_ok': vok,
                            'reversal_ok': rok,
                        }
                        signals.append(sig)
                    break  # Only one break per swing high

    # ── SSL Sweep: scan forward from each swing low ──
    for sw_idx, sw_price in sl:
        scan_end = min(sw_idx + 20, n)
        for j in range(sw_idx + 1, scan_end):
            bar = ohlcv[j]
            body = abs(bar['c'] - bar['o'])
            if body == 0:
                continue

            if bar['l'] < sw_price:
                wick = min(bar['o'], bar['c']) - bar['l']
                ratio = wick / body

                if ratio >= wick_ratio:
                    nxt_idx = j + 1
                    vok = (not require_volume or
                           bar['v'] > vol_median * 1.2 or
                           bar['v'] > avg_vol * 1.15)
                    rok = (not require_reversal or
                           (nxt_idx < n and ohlcv[nxt_idx]['c'] > bar['c'] * 1.002) or
                           (nxt_idx + 1 < n and ohlcv[nxt_idx + 1]['c'] > bar['c']))

                    if vok and rok:
                        sig = Signal(
                            type='Sweep', idx=j, direction='bear',
                            price=bar['l'], timeframe=tf,
                            upper=bar['l'] + wick, lower=bar['l'],
                            confirmed_at=j + 1, grade=3,
                        )
                        sig.strength = min(10, 3.0 + (ratio / wick_ratio) * 3)
                        sig.confidence = min(0.85, 0.35 + (ratio / wick_ratio) * 0.2)
                        sig.metadata = {
                            'wick_ratio': round(ratio, 2),
                            'sweep_type': 'SSL',
                            'liquidity_type': 'SSL',
                            'break_price': round(sw_price, 2),
                            'swing_idx': sw_idx,
                            'volume_ok': vok,
                            'reversal_ok': rok,
                        }
                        signals.append(sig)
                    break  # Only one break per swing low

    signals.sort(key=lambda s: s.idx)
    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 6. Pivot-based EQH/EQL — Pine-style
# ═══════════════════════════════════════════════════════════════════════

def detect_eql_v12(ohlcv: List[Dict], threshold_pct: float = 0.1,
                   swings: Tuple[List, List] = None,
                   tf: str = 'daily') -> List[Dict]:
    """
    Pivot-based EQH/EQL — Pine Script UAlgo style.

    V11 problem: O(n^2) brute-force pairwise comparison of ALL bars.
    V12 fix: compare ONLY adjacent swing points (from detect_swings_v12).
    If two adjacent swing highs are within threshold_pct → EQL_High.
    If two adjacent swing lows are within threshold_pct → EQL_Low.
    """
    if swings:
        swing_highs, swing_lows = swings
    else:
        swing_highs = _quick_sh(ohlcv, 8)
        swing_lows = _quick_sl(ohlcv, 8)

    signals = []

    # Equal Highs: adjacent swing highs within threshold
    for k in range(1, len(swing_highs)):
        i1, p1 = swing_highs[k - 1]
        i2, p2 = swing_highs[k]
        diff_pct = abs(p1 - p2) / max(p1, p2, 0.01) * 100
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
                    'candle1_idx': i1, 'candle2_idx': i2,
                    'diff_pct': round(diff_pct, 3),
                    'gap_bars': i2 - i1, 'closeness': round(closeness, 3),
                },
            )
            signals.append(sig)

    # Equal Lows: adjacent swing lows within threshold
    for k in range(1, len(swing_lows)):
        i1, p1 = swing_lows[k - 1]
        i2, p2 = swing_lows[k]
        diff_pct = abs(p1 - p2) / max(p1, p2, 0.01) * 100
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
                    'candle1_idx': i1, 'candle2_idx': i2,
                    'diff_pct': round(diff_pct, 3),
                    'gap_bars': i2 - i1, 'closeness': round(closeness, 3),
                },
            )
            signals.append(sig)

    # Deduplicate: keep strongest per price level
    signals.sort(key=lambda s: -s.strength)
    unique = []
    seen = set()
    for sig in signals:
        key = (round(sig.metadata.get('level', 0), 2), sig.direction)
        if key not in seen:
            seen.add(key)
            unique.append(sig)
    unique.sort(key=lambda s: s.idx)
    return [s.to_dict() for s in unique]


# ═══════════════════════════════════════════════════════════════════════
# 7. Composite Signals (BPR, IFVG, LV, RJ, OTE, PO3, BreakerBlock, MitigatedFVG, MSS)
# — V12 uses the same algorithms as V11 for these; correctness depends on
#   underlying signals (FVG, OB, swings) which are now fixed.
# ═══════════════════════════════════════════════════════════════════════

def detect_bpr_v12(ohlcv: List[Dict], fvg_signals: List[Dict],
                   tf: str = 'daily') -> List[Dict]:
    """BPR — Balanced Price Range (FVG overlap area), same as V11."""
    if not fvg_signals or len(fvg_signals) < 2:
        return []
    n = len(ohlcv)
    signals = []
    bull_f = [f for f in fvg_signals if 'Bull' in f.get('type', '')]
    bear_f = [f for f in fvg_signals if 'Bear' in f.get('type', '')]
    if not bull_f or not bear_f:
        return []
    for bf in bull_f:
        bi = bf.get('idx', 0); bu = bf.get('upper', 0); bl = bf.get('lower', 0)
        if bu <= 0 or bl <= 0: continue
        for bf2 in bear_f:
            bi2 = bf2.get('idx', 0); bu2 = bf2.get('upper', 0); bl2 = bf2.get('lower', 0)
            if bu2 <= 0 or bl2 <= 0: continue
            if bi2 <= bi or bi2 > bi + 30: continue
            if bu > bl2 and bl < bu2:
                oh = min(bu, bu2); ol = max(bl, bl2)
                if oh > ol:
                    s = Signal(type='BPR', idx=bi2, direction='neutral',
                              price=(oh + ol) / 2, timeframe=tf,
                              upper=oh, lower=ol, confirmed_at=bi2,
                              grade=max(bf.get('grade', 1), bf2.get('grade', 1)),
                              strength=min(8, bf.get('strength', 3) + bf2.get('strength', 3)),
                              confidence=min(0.75, bf.get('confidence', 0.4) + bf2.get('confidence', 0.4)),
                              metadata={'bull_fvg_idx': bi, 'bear_fvg_idx': bi2,
                                       'overlap_high': round(oh, 4), 'overlap_low': round(ol, 4)})
                    signals.append(s)
                    break
    return [s.to_dict() for s in signals]

def detect_liquidity_void_v12(ohlcv: List[Dict], min_gap_pct: float = 0.3,
                              tf: str = 'daily') -> List[Dict]:
    """LV — Liquidity Void (gap), same as V11."""
    signals = []
    for i in range(1, len(ohlcv)):
        b, p = ohlcv[i], ohlcv[i-1]
        gu = b['l'] - p['h']; gp = gu / max(p['c'], 0.01) * 100
        if gu > 0 and gp >= min_gap_pct:
            s = Signal(type='LiquidityVoid', idx=i, direction='bear', price=p['h'],
                      timeframe=tf, upper=b['l'], lower=p['h'], confirmed_at=i,
                      grade=4 if gp > 1.0 else 3 if gp > 0.6 else 2,
                      strength=min(8, 3 + gp * 3), confidence=min(0.8, 0.3 + gp * 0.3),
                      metadata={'gap_pct': round(gp, 2), 'gap_type': 'up'})
            signals.append(s)
        gd = p['l'] - b['h']; gp = gd / max(p['c'], 0.01) * 100
        if gd > 0 and gp >= min_gap_pct:
            s = Signal(type='LiquidityVoid', idx=i, direction='bull', price=p['l'],
                      timeframe=tf, upper=p['l'], lower=b['h'], confirmed_at=i,
                      grade=4 if gp > 1.0 else 3 if gp > 0.6 else 2,
                      strength=min(8, 3 + gp * 3), confidence=min(0.8, 0.3 + gp * 0.3),
                      metadata={'gap_pct': round(gp, 2), 'gap_type': 'down'})
            signals.append(s)
    return [s.to_dict() for s in signals]

def detect_rejection_block_v12(ohlcv: List[Dict], min_wick_pct: float = 2.0,
                                tf: str = 'daily') -> List[Dict]:
    """RJ — Rejection Block (long wick), same as V11."""
    signals = []
    atr_pct = 2.0
    for i in range(len(ohlcv)):
        b = ohlcv[i]
        rng = b['h'] - b['l']; body = abs(b['c'] - b['o']); wu = b['h'] - max(b['o'], b['c']); wd = min(b['o'], b['c']) - b['l']
        if rng == 0: continue
        wu_pct = wu / b['c'] * 100 if b['c'] > 0 else 0; wd_pct = wd / b['c'] * 100 if b['c'] > 0 else 0
        if wu > body and wu_pct >= min_wick_pct and b['c'] < b['o']:
            s = Signal(type='RejectionBlock', idx=i, direction='bear', price=b['h'],
                      timeframe=tf, upper=b['h'], lower=b['h'] - wu * 0.3, confirmed_at=i,
                      grade=4 if wu_pct > atr_pct else 3 if wu_pct > atr_pct * 0.6 else 2,
                      strength=min(8, 3 + wu_pct * 2), confidence=min(0.8, 0.3 + wu_pct * 0.1),
                      metadata={'wick_pct': round(wu_pct, 2), 'wick_type': 'upper'})
            signals.append(s)
        elif wd > body and wd_pct >= min_wick_pct and b['c'] > b['o']:
            s = Signal(type='RejectionBlock', idx=i, direction='bull', price=b['l'],
                      timeframe=tf, upper=b['l'] + wd * 0.3, lower=b['l'], confirmed_at=i,
                      grade=4 if wd_pct > atr_pct else 3 if wd_pct > atr_pct * 0.6 else 2,
                      strength=min(8, 3 + wd_pct * 2), confidence=min(0.8, 0.3 + wd_pct * 0.1),
                      metadata={'wick_pct': round(wd_pct, 2), 'wick_type': 'lower'})
            signals.append(s)
    return [s.to_dict() for s in signals]

def detect_ifvg_v12(ohlcv: List[Dict], min_width: float = None,
                    adaptive: Dict = None, tf: str = 'daily') -> List[Dict]:
    """IFVG — Implied FVG (wick midpoint gap), same as V11."""
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    if min_width is None:
        min_width = adaptive.get('fvg_min_width', 0.001)
    signals = []
    for i in range(len(ohlcv) - 2):
        b1, b2, b3 = ohlcv[i], ohlcv[i+1], ohlcv[i+2]
        gap_up = b3['l'] - b1['h']
        if gap_up > 0:
            gp = gap_up / b1['c'] * 100 if b1['c'] > 0 else 0
            if gp < min_width:
                mid = (max(b2['l'], b1['h']) + min(b2['h'], b3['l'])) / 2
                wms = b2['h'] - b2['l']
                if wms > 0:
                    imp = (min(b2['h'], b3['l']) - max(b2['l'], b1['h'])) / wms
                    if 0.3 <= imp <= 0.7:
                        s = Signal(type='IFVG_Bull', idx=i+1, direction='bull',
                                  price=mid, timeframe=tf, upper=b3['l'], lower=b1['h'],
                                  confirmed_at=i+2, grade=2, strength=3.0, confidence=0.45,
                                  metadata={'gap_pct': round(gp, 4), 'wms_ratio': round(imp, 2)})
                        signals.append(s)
        gap_dn = b1['l'] - b3['h']
        if gap_dn > 0:
            gp = gap_dn / b1['c'] * 100 if b1['c'] > 0 else 0
            if gp < min_width:
                mid = (max(b2['l'], b3['h']) + min(b2['h'], b1['l'])) / 2
                wms = b2['h'] - b2['l']
                if wms > 0:
                    imp = (min(b2['h'], b1['l']) - max(b2['l'], b3['h'])) / wms
                    if 0.3 <= imp <= 0.7:
                        s = Signal(type='IFVG_Bear', idx=i+1, direction='bear',
                                  price=mid, timeframe=tf, upper=b1['l'], lower=b3['h'],
                                  confirmed_at=i+2, grade=2, strength=3.0, confidence=0.45,
                                  metadata={'gap_pct': round(gp, 4), 'wms_ratio': round(imp, 2)})
                        signals.append(s)
    return [s.to_dict() for s in signals]

def detect_mitigated_fvg_v12(ohlcv: List[Dict], fvg_signals: List[Dict],
                              tf: str = 'daily') -> List[Dict]:
    """Mitigated FVG — price returned to fill the gap, same as V11."""
    n = len(ohlcv); signals = []
    for f in fvg_signals:
        if 'FVG' not in f.get('type', ''): continue
        idx = f.get('idx', 0); d = f.get('direction', 'bull')
        upper = f.get('upper', 0); lower = f.get('lower', 0)
        for j in range(idx + 1, min(idx + 50, n)):
            b = ohlcv[j]
            hit = (d == 'bull' and b['l'] <= upper) or (d == 'bear' and b['h'] >= lower)
            if hit:
                sig_dir = 'bear' if d == 'bull' else 'bull'
                s = Signal(type='FVG_Mitigated_Bull' if d == 'bull' else 'FVG_Mitigated_Bear',
                          idx=j, direction=sig_dir, timeframe=tf,
                          price=upper if d == 'bull' else lower,
                          upper=upper, lower=lower, confirmed_at=j,
                          grade=f.get('grade', 1), strength=f.get('strength', 3) * 0.8,
                          confidence=f.get('confidence', 0.4) * 0.7,
                          metadata={'source_fvg_idx': idx, 'mitigated_at': j})
                signals.append(s)
                break
    return [s.to_dict() for s in signals]

def detect_breaker_block_v12(ohlcv: List[Dict], choch_signals: List[Dict],
                              fvg_signals: List[Dict], tf: str = 'daily') -> List[Dict]:
    """Breaker Block — CHOCH + previous OB area, same as V11."""
    n = len(ohlcv); signals = []
    fvg_set = {}
    for f in fvg_signals:
        fn = f.get('type', ''); fi = f.get('idx', 0)
        if 'FVG_Bull' in fn: fvg_set.setdefault('bull', []).append(f)
        elif 'FVG_Bear' in fn: fvg_set.setdefault('bear', []).append(f)
    for c in choch_signals:
        ct = c.get('type', ''); ci = c.get('idx', 0); cd = c.get('direction', '')
        if 'CHOCH' not in ct: continue
        brk = c.get('metadata', {}).get('break_level', 0)
        if brk == 0: continue
        fvgs = fvg_set.get('bull' if cd == 'bull' else 'bear', [])
        near_fvg = any(abs(f.get('idx', 0) - ci) <= 10 and f.get('lower', 0) <= brk <= f.get('upper', 0) for f in fvgs)
        sig_dir = 'bull' if cd == 'bear' else 'bear'
        s = Signal(type='BreakerBlock_Bull' if sig_dir == 'bull' else 'BreakerBlock_Bear',
                  idx=ci, direction=sig_dir, timeframe=tf,
                  price=c.get('price', 0), confirmed_at=ci,
                  grade=3, strength=5.0 if near_fvg else 3.0,
                  confidence=0.6 if near_fvg else 0.35,
                  metadata={'break_level': brk, 'choch_idx': ci, 'has_fvg_overlap': near_fvg,
                           'choch_type': ct})
        signals.append(s)
    return [s.to_dict() for s in signals]

def detect_ote_v12(ohlcv: List[Dict], swing_signals: List[Dict] = None,
                   adaptive: Dict = None, tf: str = 'daily') -> List[Dict]:
    """OTE — Optimal Trade Entry (61.8% Fibonacci retracement), same as V11."""
    signals = []
    if not swing_signals or len(swing_signals) < 4: return []
    f = 0.618
    for i in range(2, len(swing_signals) - 1):
        s0 = swing_signals[i]; s1 = swing_signals[i+1]
        if s0.get('type') != 'SwingHigh' or s1.get('type') != 'SwingLow': continue
        range_pts = s0['price'] - s1['price']
        if range_pts <= 0: continue
        retrace = s0['price'] - range_pts * f
        for j in range(s1['idx'], min(s1['idx'] + 15, len(ohlcv))):
            b = ohlcv[j]
            if b['l'] <= retrace <= b['h'] or abs(b['c'] - retrace) / max(retrace, 0.01) < 0.005:
                s = Signal(type='OTE', idx=j, direction='bull', price=retrace,
                          timeframe=tf, upper=retrace * 1.002, lower=retrace * 0.998,
                          confirmed_at=j, strength=4.0, confidence=0.5,
                          metadata={'fib_level': 61.8, 'swing_high': s0['price'], 'swing_low': s1['price']})
                signals.append(s)
                break
    return [s.to_dict() for s in signals]

def detect_po3_v12(ohlcv: List[Dict], lookback: int = 20,
                   adaptive: Dict = None, tf: str = 'daily') -> List[Dict]:
    """PO3 — Power of 3 (accumulation/manipulation/distribution), same as V11."""
    n = len(ohlcv); signals = []
    if adaptive is None: adaptive = calc_adaptive_thresholds(ohlcv)
    atr = adaptive.get('atr_pct', 2.0)
    acc_thresh = atr / 100  # ACC threshold as ratio
    for i in range(lookback * 2, n - lookback):
        seg = ohlcv[i - lookback:i + lookback]
        seg_range = max(b['h'] for b in seg) - min(b['l'] for b in seg)
        if seg_range == 0: continue
        first = seg[:lookback]; last = seg[lookback:]
        first_avg = sum(b['c'] for b in first) / lookback
        last_avg = sum(b['c'] for b in last) / lookback
        f_high = max(b['h'] for b in first); f_low = min(b['l'] for b in first)
        l_high = max(b['h'] for b in last); l_low = min(b['l'] for b in last)
        first_range = f_high - f_low
        if first_range == 0: continue
        if abs(first_avg - last_avg) / first_avg < 0.005 and l_high > f_high and l_low < f_low:
            if first_range <= seg_range * 0.3:
                s = Signal(type='PO3', idx=i, direction='neutral', price=(l_high + l_low) / 2,
                          timeframe=tf, upper=l_high, lower=l_low, confirmed_at=i,
                          grade=3, strength=5.0, confidence=0.55,
                          metadata={'phase': 'accumulation', 'range_pct': round(first_range / f_high * 100, 2)})
                signals.append(s)
    return [s.to_dict() for s in signals]


def detect_mss_v12(ohlcv: List[Dict], lookback: int = 5,
                   tf: str = 'daily') -> List[Dict]:
    """
    MSS — Micro Structure Shift (3-candle window for direction change).

    V11 compatible: detects local direction shifts via SMA crossover.
    Used when state machine swings are too sparse for BOS/CHOCH.
    """
    n = len(ohlcv)
    if n < lookback + 3: return []
    signals = []
    sma = [sum(b['c'] for b in ohlcv[max(0,i-lookback):i]) / max(min(i, lookback), 1) for i in range(n)]
    for i in range(lookback + 1, n - 2):
        short = sum(b['c'] for b in ohlcv[i-2:i+1]) / 3
        prev_short = sum(b['c'] for b in ohlcv[i-3:i]) / 3
        if short > sma[i] and prev_short <= sma[i-1]:
            s = Signal(type='MSS_Bull', idx=i, direction='bull', price=ohlcv[i]['c'],
                      timeframe=tf, confirmed_at=i, grade=2,
                      strength=3.0, confidence=0.45,
                      metadata={'sma_cross': 'bull', 'sma_val': round(sma[i], 4)})
            signals.append(s)
        elif short < sma[i] and prev_short >= sma[i-1]:
            s = Signal(type='MSS_Bear', idx=i, direction='bear', price=ohlcv[i]['c'],
                      timeframe=tf, confirmed_at=i, grade=2,
                      strength=3.0, confidence=0.45,
                      metadata={'sma_cross': 'bear', 'sma_val': round(sma[i], 4)})
            signals.append(s)
    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# UNIFIED DETECTION ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════

def detect_all_signals_v12(ohlcv: List[Dict], params: Dict = None,
                           tf: str = 'daily') -> Dict:
    """
    Universal signal detection — drop-in replacement for V11 detect_all_signals_v11().

    V12 improvements:
    - Pine-style swings with right confirmation
    - Corrected OB detection: backward from swing points + displacement filter
    - Swing-point level sweeps (no per-candle scanning)
    - State machine structure detection (BOS/CHOCH via HH/HL tracking)
    - Pivot-based EQH/EQL (adjacent swing comparison)
    - Composite signals react to fixed underlying signals
    """
    if params is None:
        params = {}

    adaptive = params.get('adaptive')
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)

    req_vol = params.get('require_volume', True)
    ob_disp = params.get('ob_displacement_mult', 1.3)
    swing_left = params.get('swing_left', 8)
    swing_right = params.get('swing_right', 3)

    swing_highs, swing_lows = detect_swings_v12(
        ohlcv, left=swing_left, right=swing_right, adaptive=adaptive
    )
    swings = (swing_highs, swing_lows)

    # Primary signals
    fvg_signals = detect_fvg_v12(ohlcv, adaptive=adaptive, tf=tf)
    ob_signals = detect_ob_v12(
        ohlcv, adaptive=adaptive, require_volume=req_vol,
        displacement_mult=ob_disp, swings=swings, tf=tf
    )
    sweep_signals = detect_sweep_v12(
        ohlcv, adaptive=adaptive, require_volume=req_vol,
        swings=swings, tf=tf
    )
    structure_signals = detect_structure_v12(ohlcv, swings=swings, tf=tf)

    # MSS: micro structure shifts
    mss_signals = detect_mss_v12(ohlcv, tf=tf)

    # EQL: pivot-based equal highs/lows
    eql_signals = detect_eql_v12(ohlcv, swings=swings, tf=tf)

    # Composite signals (based on already-detected signals)
    bpr_signals = detect_bpr_v12(ohlcv, fvg_signals, tf=tf)
    ifvg_signals = detect_ifvg_v12(ohlcv, adaptive=adaptive, tf=tf)
    lv_signals = detect_liquidity_void_v12(ohlcv, tf=tf)
    rj_signals = detect_rejection_block_v12(ohlcv, tf=tf)
    mitigated_fvg = detect_mitigated_fvg_v12(ohlcv, fvg_signals, tf=tf)
    breaker_block = detect_breaker_block_v12(ohlcv, structure_signals, fvg_signals, tf=tf)
    ote_signals = detect_ote_v12(ohlcv, tf=tf)
    po3_signals = detect_po3_v12(ohlcv, adaptive=adaptive, tf=tf)

    all_s = fvg_signals + ob_signals + sweep_signals + structure_signals + \
            mss_signals + eql_signals + bpr_signals + ifvg_signals + lv_signals + rj_signals + \
            mitigated_fvg + breaker_block + ote_signals + po3_signals
    all_s.sort(key=lambda s: s.get('idx', 0))

    return {
        'FVG_Bull': [s for s in fvg_signals if 'Bull' in s.get('type', '')],
        'FVG_Bear': [s for s in fvg_signals if 'Bear' in s.get('type', '')],
        'OB_Bull': [s for s in ob_signals if 'Bull' in s.get('type', '')],
        'OB_Bear': [s for s in ob_signals if 'Bear' in s.get('type', '')],
        'Sweep': sweep_signals,
        'CHOCH_Bull': [s for s in structure_signals if 'CHOCH_Bull' in s.get('type', '')],
        'CHOCH_Bear': [s for s in structure_signals if 'CHOCH_Bear' in s.get('type', '')],
        'BOS_Bull': [s for s in structure_signals if 'BOS_Bull' in s.get('type', '')],
        'BOS_Bear': [s for s in structure_signals if 'BOS_Bear' in s.get('type', '')],
        'MSS': mss_signals,
        'EQL_High': [s for s in eql_signals if 'High' in s.get('type', '')],
        'EQL_Low': [s for s in eql_signals if 'Low' in s.get('type', '')],
        'BPR': bpr_signals,
        'IFVG_Bull': [s for s in ifvg_signals if 'Bull' in s.get('type', '')],
        'IFVG_Bear': [s for s in ifvg_signals if 'Bear' in s.get('type', '')],
        'LiquidityVoid': lv_signals,
        'RejectionBlock': rj_signals,
        'FVG_Mitigated': mitigated_fvg,
        'BreakerBlock': breaker_block,
        'OTE': ote_signals,
        'PO3': po3_signals,
        'all': all_s,
        'swing_highs': [{'idx': i, 'price': p} for i, p in swing_highs],
        'swing_lows': [{'idx': i, 'price': p} for i, p in swing_lows],
    }


# ═══════════════════════════════════════════════════════════════════════
# V13 — 60min Optimized OB Detection (Mixed Strategy)
# ═══════════════════════════════════════════════════════════════════════
# Strategy:
#   1) Swing-backward scan (correctness priority) with relaxed 60min params
#   2) Improved constrained forward fallback for coverage
# ═══════════════════════════════════════════════════════════════════════

def detect_ob_v13_60min(ohlcv: List[Dict], adaptive: Dict = None,
                         swings: Tuple[List, List] = None,
                         tf: str = '60min') -> List[Dict]:
    """60min-optimized OB: swing-backward + aggressively relaxed forward fallback.
    
    Fallback relaxed to approach V11 coverage levels:
    - body_pct >= 0.05 (was 0.08)
    - No positional swing constraint (was near_sw +/-5)
    - displacement >= 0.5x (was 0.8x)
    - No volume filter (was vol > median*0.5)
    - Always runs (was skip if primary >=3)
    """
    n = len(ohlcv)
    if n < 30:
        return []

    # Step 1: Swing-backward with relaxed 60min parameters
    primary_obs = detect_ob_v12(
        ohlcv, adaptive=adaptive,
        require_volume=True,
        displacement_mult=1.0,
        swings=swings, tf=tf,
        body_pct_min=0.08,
    )

    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)

    # Step 2: Relaxed forward fallback with positional constraint
    # Use V12 swing parameters (left=8, right=3) for positional filter
    sh = _quick_sh(ohlcv, 8)
    sl = _quick_sl(ohlcv, 8)
    swing_near_idxs = set(i for i, _ in sh + sl)
    processed = set(s.get('idx', -1) for s in primary_obs)

    fallback = []
    for i in range(5, n - 3):
        if i in processed:
            continue
        bar = ohlcv[i]
        body = abs(bar['c'] - bar['o'])
        if body == 0:
            continue
        body_pct = body / max(bar['o'], 0.01) * 100
        if body_pct < 0.10:          # 0.10% minimum body (was 0.08)
            continue
        bar_range = bar['h'] - bar['l']
        if bar_range <= 0:
            continue

        # Positional: near swing point (keep original)
        near_sw = any(abs(i - si) <= 5 for si in swing_near_idxs)
        if not near_sw:
            continue

        # Bullish OB candidate: bearish candle
        if bar['c'] < bar['o']:
            max_fwd = max(b['h'] for b in ohlcv[i+1:min(i+12, n)])
            displacement = max_fwd - bar['l']
            dis_ratio = displacement / max(bar_range, 0.001)

            if dis_ratio >= 0.7:     # relaxed: 0.7x displacement (was 0.8)
                if ohlcv[i+1]['c'] <= ohlcv[i+1]['o']:
                    continue
                imp = 0
                for j in range(i+1, min(i+6, n)):
                    if ohlcv[j]['c'] > ohlcv[j]['o']:
                        imp += 1
                    else:
                        break
                if imp >= 1:
                    vol_ok = bar['v'] > adaptive['vol_median'] * 0.3  # loose volume
                    if not vol_ok:
                        continue
                    sig = Signal(
                        type='OB_Bull', idx=i, direction='bull',
                        price=bar['l'], upper=bar['h'], lower=bar['l'],
                        timeframe=tf, confirmed_at=i + 1,
                        volume_ratio=round(bar['v'] / max(adaptive['vol_median'], 1), 2),
                    )
                    sig.strength = min(6, 1.5 + dis_ratio * 1.0 + min(1, imp * 0.3))
                    sig.confidence = min(0.60, 0.20 + dis_ratio * 0.04 + (0.05 if vol_ok else 0))
                    sig.metadata = {
                        'body_pct': round(body_pct, 2), 'impulse_bars': imp,
                        'displacement_ratio': round(dis_ratio, 2),
                        'ob_method': 'v13_fallback_relaxed',
                    }
                    fallback.append(sig)
                    processed.add(i)

        # Bearish OB candidate: bullish candle
        elif bar['c'] > bar['o']:
            min_fwd = min(b['l'] for b in ohlcv[i+1:min(i+12, n)])
            displacement = bar['h'] - min_fwd
            dis_ratio = displacement / max(bar_range, 0.001)

            if dis_ratio >= 0.7:     # relaxed: 0.7x displacement (was 0.8)
                if ohlcv[i+1]['c'] >= ohlcv[i+1]['o']:
                    continue
                imp = 0
                for j in range(i+1, min(i+6, n)):
                    if ohlcv[j]['c'] < ohlcv[j]['o']:
                        imp += 1
                    else:
                        break
                if imp >= 1:
                    vol_ok = bar['v'] > adaptive['vol_median'] * 0.3  # loose volume
                    if not vol_ok:
                        continue
                    sig = Signal(
                        type='OB_Bear', idx=i, direction='bear',
                        price=bar['h'], upper=bar['h'], lower=bar['l'],
                        timeframe=tf, confirmed_at=i + 1,
                        volume_ratio=round(bar['v'] / max(adaptive['vol_median'], 1), 2),
                    )
                    sig.strength = min(6, 1.5 + dis_ratio * 1.0 + min(1, imp * 0.3))
                    sig.confidence = min(0.60, 0.20 + dis_ratio * 0.04 + (0.05 if vol_ok else 0))
                    sig.metadata = {
                        'body_pct': round(body_pct, 2), 'impulse_bars': imp,
                        'displacement_ratio': round(dis_ratio, 2),
                        'ob_method': 'v13_fallback_relaxed',
                    }
                    fallback.append(sig)
                    processed.add(i)

    # Combine
    combined = primary_obs + [s.to_dict() for s in fallback]
    combined.sort(key=lambda s: -s.get('strength', 0))
    unique = []
    seen = set()
    for s in combined:
        key = (round(s.get('price', 0), 2), s.get('direction', ''))
        if key not in seen:
            seen.add(key)
            unique.append(s)
    unique.sort(key=lambda s: s.get('idx', 0))
    return unique


def detect_all_signals_v13_60min(ohlcv: List[Dict], params: Dict = None,
                                  tf: str = '60min') -> Dict:
    """V13 60min signal detection — uses 60min-optimized OB detection."""
    if params is None:
        params = {}

    adaptive = params.get('adaptive')
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)

    req_vol = params.get('require_volume', True)
    swing_left = params.get('swing_left', 8)
    swing_right = params.get('swing_right', 3)

    # V13 60min: use dedicated swing detection (right=2, ATR=1.0x)
    swing_highs, swing_lows = detect_swings_v13_60min(
        ohlcv, left=swing_left, right=swing_right, adaptive=adaptive
    )
    swings = (swing_highs, swing_lows)

    # FVG, Sweep, Structure — same as V12
    fvg_signals = detect_fvg_v12(ohlcv, adaptive=adaptive, tf=tf)
    ob_signals = detect_ob_v13_60min(  # V13 60min OB
        ohlcv, adaptive=adaptive, swings=swings, tf=tf
    )
    sweep_signals = detect_sweep_v12(
        ohlcv, adaptive=adaptive, require_volume=req_vol,
        swings=swings, tf=tf
    )
    structure_signals = detect_structure_v12(ohlcv, swings=swings, tf=tf)
    mss_signals = detect_mss_v12(ohlcv, tf=tf)
    eql_signals = detect_eql_v12(ohlcv, swings=swings, tf=tf)

    # Composite signals
    bpr_signals = detect_bpr_v12(ohlcv, fvg_signals, tf=tf)
    ifvg_signals = detect_ifvg_v12(ohlcv, adaptive=adaptive, tf=tf)
    lv_signals = detect_liquidity_void_v12(ohlcv, tf=tf)
    rj_signals = detect_rejection_block_v12(ohlcv, tf=tf)
    mitigated_fvg = detect_mitigated_fvg_v12(ohlcv, fvg_signals, tf=tf)
    breaker_block = detect_breaker_block_v12(ohlcv, structure_signals, fvg_signals, tf=tf)
    ote_signals = detect_ote_v12(ohlcv, tf=tf)
    po3_signals = detect_po3_v12(ohlcv, adaptive=adaptive, tf=tf)

    all_s = (fvg_signals + ob_signals + sweep_signals + structure_signals +
             mss_signals + eql_signals + bpr_signals + ifvg_signals + lv_signals +
             rj_signals + mitigated_fvg + breaker_block + ote_signals + po3_signals)
    all_s.sort(key=lambda s: s.get('idx', 0))

    return {
        'FVG_Bull': [s for s in fvg_signals if 'Bull' in s.get('type', '')],
        'FVG_Bear': [s for s in fvg_signals if 'Bear' in s.get('type', '')],
        'OB_Bull': [s for s in ob_signals if 'Bull' in s.get('type', '')],
        'OB_Bear': [s for s in ob_signals if 'Bear' in s.get('type', '')],
        'Sweep': sweep_signals,
        'CHOCH_Bull': [s for s in structure_signals if 'CHOCH_Bull' in s.get('type', '')],
        'CHOCH_Bear': [s for s in structure_signals if 'CHOCH_Bear' in s.get('type', '')],
        'BOS_Bull': [s for s in structure_signals if 'BOS_Bull' in s.get('type', '')],
        'BOS_Bear': [s for s in structure_signals if 'BOS_Bear' in s.get('type', '')],
        'MSS': mss_signals,
        'EQL_High': [s for s in eql_signals if 'High' in s.get('type', '')],
        'EQL_Low': [s for s in eql_signals if 'Low' in s.get('type', '')],
        'BPR': bpr_signals,
        'IFVG_Bull': [s for s in ifvg_signals if 'Bull' in s.get('type', '')],
        'IFVG_Bear': [s for s in ifvg_signals if 'Bear' in s.get('type', '')],
        'LiquidityVoid': lv_signals,
        'RejectionBlock': rj_signals,
        'FVG_Mitigated': mitigated_fvg,
        'BreakerBlock': breaker_block,
        'OTE': ote_signals,
        'PO3': po3_signals,
        'all': all_s,
        'swing_highs': [{'idx': i, 'price': p} for i, p in swing_highs],
        'swing_lows': [{'idx': i, 'price': p} for i, p in swing_lows],
    }
