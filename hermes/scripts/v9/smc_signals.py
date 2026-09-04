#!/usr/bin/env python3
# SMC V9 — Signal Detection Module
"""
All SMC pattern detection algorithms.
Extracted from V84 engine with clean interfaces, type hints, and docstrings.
"""

import logging
from . import smc_config as config

log = logging.getLogger('smc_v9.signals')


# ═══════════════════════════════════════════════════════════════════
# FVG — Fair Value Gap
# ═══════════════════════════════════════════════════════════════════


def detect_fvg(ohlcv, min_width=0.001, merge_dist=3):
    """Detect Fair Value Gaps (3-candle inefficiency).
    
    Algorithm: three consecutive candles where candle 1's high < candle 3's low
    (bullish) or candle 1's low > candle 3's high (bearish), creating a price gap.
    
    Args:
        ohlcv: list of {o,h,l,c,v} dicts, earliest to latest
        min_width: minimum gap width as fraction of candle 1 close (0.1% default)
        merge_dist: merge gaps within N candles (0 = no merge)
    
    Returns: list of FVG signal dicts
    """
    signals = []
    i = 0
    while i < len(ohlcv) - 2:
        b1, _, b3 = ohlcv[i], ohlcv[i + 1], ohlcv[i + 2]
        upper = min(b1['h'], b3['h'])
        lower = max(b1['l'], b3['l'])
        if upper > lower:
            width = (upper - lower) / b1['c'] if b1['c'] > 0 else 0
            if width >= min_width:
                signals.append({
                    'type': 'FVG',
                    'idx': i + 1,
                    'upper': upper,
                    'lower': lower,
                    'width': width,
                    'direction': 'bull' if b3['c'] > b1['c'] else 'bear'
                })
        i += 1

    # Merge adjacent FVGs
    if merge_dist > 0 and signals:
        merged = [signals[0]]
        for s in signals[1:]:
            last = merged[-1]
            if s['idx'] - last['idx'] <= merge_dist:
                last['upper'] = max(last['upper'], s['upper'])
                last['lower'] = min(last['lower'], s['lower'])
                last['idx'] = (last['idx'] + s['idx']) // 2
            else:
                merged.append(s)
        return merged
    return signals


# ═══════════════════════════════════════════════════════════════════
# IFVG — Inverse Fair Value Gap
# ═══════════════════════════════════════════════════════════════════


def detect_ifvg(ohlcv, min_width=0.001):
    """Detect Inverse FVGs — overlapping gap pattern.
    
    Three candles where candle 1 and 3 overlap each other completely
    (candle 3's high < candle 1's high and candle 3's low > candle 1's low).
    
    Args:
        ohlcv: list of {o,h,l,c,v} dicts
        min_width: minimum gap width as fraction of price
    
    Returns: list of IFVG signal dicts
    """
    signals = []
    for i in range(len(ohlcv) - 2):
        b1, b3 = ohlcv[i], ohlcv[i + 2]
        if b1['h'] < b3['h'] and b1['l'] > b3['l']:
            gap = abs(b3['l'] - b1['h']) / b1['c'] if b1['c'] > 0 else 0
            if gap >= min_width:
                signals.append({
                    'type': 'IFVG',
                    'idx': i + 1,
                    'upper': max(b1['h'], b3['h']),
                    'lower': min(b1['l'], b3['l']),
                    'gap': gap,
                    'direction': 'bear' if b3['c'] < b1['c'] else 'bull'
                })
    return signals


# ═══════════════════════════════════════════════════════════════════
# Sweep — Liquidity Sweep / Stop Hunt
# ═══════════════════════════════════════════════════════════════════


def detect_sweep(ohlcv, lookback=12, wick_ratio=2.0):
    """Detect liquidity sweeps — price breaking then reversing.
    
    Algorithm:
    - Find recent high/low within lookback window
    - Price breaks above high (or below low) 
    - Immediate reversal: next candle closes back inside range
    - Long wick relative to body confirms the sweep
    
    Args:
        ohlcv: list of {o,h,l,c,v} dicts
        lookback: window to find recent HH/LL (default: 12)
        wick_ratio: minimum wick-to-body ratio (default: 2.0)
    
    Returns: list of Sweep signal dicts
    """
    signals = []
    for i in range(lookback, len(ohlcv) - 2):
        window = ohlcv[i - lookback:i]
        high = max(b['h'] for b in window)
        low = min(b['l'] for b in window)
        cur = ohlcv[i]
        nxt = ohlcv[i + 1]

        # Upward sweep (break above high → reverse down)
        if cur['h'] > high and nxt['c'] < cur['c']:
            wick_up = cur['h'] - max(cur['o'], cur['c'])
            body = abs(cur['c'] - cur['o'])
            if body > 0 and wick_up / body > wick_ratio:
                signals.append({
                    'type': 'SweepUp', 'idx': i,
                    'high': cur['h'], 'low': cur['l'],
                    'break_level': high,
                    'wick_ratio': wick_up / body,
                    'strength': wick_up / cur['c'] * 100,
                    'direction': 'bear'
                })

        # Downward sweep (break below low → reverse up)
        if cur['l'] < low and nxt['c'] > cur['c']:
            wick_down = min(cur['o'], cur['c']) - cur['l']
            body = abs(cur['c'] - cur['o'])
            if body > 0 and wick_down / body > wick_ratio:
                signals.append({
                    'type': 'SweepDown', 'idx': i,
                    'high': cur['h'], 'low': cur['l'],
                    'break_level': low,
                    'wick_ratio': wick_down / body,
                    'strength': wick_down / cur['c'] * 100,
                    'direction': 'bull'
                })
    return signals


# ═══════════════════════════════════════════════════════════════════
# OB — Order Block
# ═══════════════════════════════════════════════════════════════════


def detect_ob(ohlcv, strength_min=1.0):
    """Detect Order Blocks — last candle before a reversal.
    
    Algorithm:
    - Bullish OB: consecutive bear candles followed by a bull candle
      → the last bear candle before the reversal is the OB
    - Bearish OB: consecutive bull candles followed by a bear candle
      → the last bull candle before the reversal is the OB
    
    Args:
        ohlcv: list of {o,h,l,c,v} dicts
        strength_min: minimum OB candle range as % (default: 1.0%)
    
    Returns: list of OB signal dicts
    """
    signals = []
    for i in range(3, len(ohlcv) - 2):
        b0 = ohlcv[i - 3]
        b1 = ohlcv[i - 2]
        b2 = ohlcv[i - 1]
        b3 = ohlcv[i]

        # Bullish OB: two bearish → last bearish → bullish reversal
        if b2['c'] < b2['o'] and b1['c'] < b1['o'] and b3['c'] > b3['o']:
            ob_range = abs(b2['c'] - b2['o']) / b2['o'] * 100 if b2['o'] > 0 else 0
            if ob_range >= strength_min:
                signals.append({
                    'type': 'OB_Bull', 'idx': i - 1,
                    'upper': max(b2['o'], b2['c']),
                    'lower': min(b2['o'], b2['c']),
                    'strength': ob_range,
                    'direction': 'bull'
                })

        # Bearish OB: two bullish → last bullish → bearish reversal
        if b2['c'] > b2['o'] and b1['c'] > b1['o'] and b3['c'] < b3['o']:
            ob_range = abs(b2['c'] - b2['o']) / b2['o'] * 100 if b2['o'] > 0 else 0
            if ob_range >= strength_min:
                signals.append({
                    'type': 'OB_Bear', 'idx': i - 1,
                    'upper': max(b2['o'], b2['c']),
                    'lower': min(b2['o'], b2['c']),
                    'strength': ob_range,
                    'direction': 'bear'
                })
    return signals


# ═══════════════════════════════════════════════════════════════════
# BPR — Balanced Price Range (FVG retest)
# ═══════════════════════════════════════════════════════════════════


def detect_bpr(ohlcv, lookback=10):
    """Detect Balanced Price Range — price returns to FVG then reverses.
    
    Algorithm: for each FVG, check if price later enters the gap and reverses.
    
    Args:
        ohlcv: list of {o,h,l,c,v} dicts
        lookback: max candles to look for retest (default: 10)
    
    Returns: list of BPR signal dicts
    """
    fvgs = detect_fvg(ohlcv, min_width=0.001)
    signals = []
    for fvg in fvgs:
        idx = fvg['idx']
        for i in range(idx + 1, min(idx + lookback + 1, len(ohlcv))):
            bar = ohlcv[i]
            if fvg['direction'] == 'bull':
                if fvg['lower'] <= bar['l'] <= fvg['upper']:
                    if i + 1 < len(ohlcv) and ohlcv[i + 1]['c'] > bar['c']:
                        signals.append({
                            'type': 'BPR_Bull', 'idx': i,
                            'upper': fvg['upper'], 'lower': fvg['lower'],
                            'price': bar['c'],
                            'strength': abs(bar['c'] - fvg['lower']) / fvg['lower'] * 100,
                            'direction': 'bull'
                        })
                        break
            elif fvg['direction'] == 'bear':
                if fvg['lower'] <= bar['h'] <= fvg['upper']:
                    if i + 1 < len(ohlcv) and ohlcv[i + 1]['c'] < bar['c']:
                        signals.append({
                            'type': 'BPR_Bear', 'idx': i,
                            'upper': fvg['upper'], 'lower': fvg['lower'],
                            'price': bar['c'],
                            'strength': abs(bar['c'] - fvg['upper']) / fvg['upper'] * 100,
                            'direction': 'bear'
                        })
                        break
    return signals


# ═══════════════════════════════════════════════════════════════════
# MSB — Market Structure Break
# ═══════════════════════════════════════════════════════════════════


def detect_msb(ohlcv, lookback=10):
    """Detect Market Structure Breaks — sustained break of HH/LL.
    
    Algorithm: price breaks above recent high (or below low) and
    sustains the break for 2+ candles.
    
    Args:
        ohlcv: list of {o,h,l,c,v} dicts
        lookback: window to find HH/LL (default: 10)
    
    Returns: list of MSB signal dicts
    """
    signals = []
    for i in range(lookback, len(ohlcv) - 2):
        window = ohlcv[i - lookback:i]
        high = max(b['h'] for b in window)
        low = min(b['l'] for b in window)
        cur = ohlcv[i]
        nxt = ohlcv[i + 1]
        nxt2 = ohlcv[i + 2]

        # Upward break (sustained above high)
        if cur['h'] > high and nxt['h'] > high and nxt2['c'] > high:
            signals.append({
                'type': 'MSB_Up', 'idx': i,
                'break_level': high,
                'price': cur['c'],
                'strength': (cur['c'] - high) / high * 100 if high > 0 else 0,
                'direction': 'bull'
            })

        # Downward break (sustained below low)
        if cur['l'] < low and nxt['l'] < low and nxt2['c'] < low:
            signals.append({
                'type': 'MSB_Down', 'idx': i,
                'break_level': low,
                'price': cur['c'],
                'strength': (low - cur['c']) / low * 100 if low > 0 else 0,
                'direction': 'bear'
            })
    return signals


# ═══════════════════════════════════════════════════════════════════
# Aggregation
# ═══════════════════════════════════════════════════════════════════


def detect_all_signals(ohlcv, params):
    """Run all signal detectors and return deduplicated results.
    
    Args:
        ohlcv: list of {o,h,l,c,v} dicts
        params: dict with keys:
            fvg_min_width, fvg_merge_dist, sweep_lookback,
            sweep_wick_ratio, ob_strength_min
    
    Returns: list of deduplicated signal dicts, sorted by idx ascending
    """
    signals = []
    signals.extend(detect_fvg(
        ohlcv,
        params.get('fvg_min_width', 0.001),
        params.get('fvg_merge_dist', 3)
    ))
    signals.extend(detect_ifvg(
        ohlcv,
        params.get('fvg_min_width', 0.001)
    ))
    signals.extend(detect_sweep(
        ohlcv,
        params.get('sweep_lookback', 12),
        params.get('sweep_wick_ratio', 2.0)
    ))
    signals.extend(detect_ob(
        ohlcv,
        params.get('ob_strength_min', 1.0)
    ))
    signals.extend(detect_bpr(
        ohlcv,
        params.get('sweep_lookback', 10)
    ))
    signals.extend(detect_msb(
        ohlcv,
        params.get('sweep_lookback', 10)
    ))

    # Deduplicate by type+idx
    unique = []
    seen = set()
    for s in signals:
        key = f"{s['type']}_{s['idx']}"
        if key not in seen:
            seen.add(key)
            unique.append(s)

    # Sort by position
    unique.sort(key=lambda s: s['idx'])
    return unique


# ═══════════════════════════════════════════════════════════════════
# Signal scoring
# ═══════════════════════════════════════════════════════════════════


def score_signal(signal, ohlcv):
    """Score a single signal on quality (0-5).
    
    Criteria:
    - FVG: width bonus (+0 to +2)
    - Sweep: strength bonus (+0 to +2)
    - OB: strength bonus (+0 to +2)
    - Confirmation: price moved in signal direction (+1)
    
    Args:
        signal: signal dict from any detector
        ohlcv: full OHLCV list (for confirmation check)
    
    Returns: quality score 0.0-5.0
    """
    score = 1.0

    # FVG width
    if signal['type'] == 'FVG':
        width = signal.get('width', 0)
        score += min(2.0, width * 50)

    # Sweep strength
    if 'Sweep' in signal['type']:
        strength = signal.get('strength', 0)
        score += min(2.0, strength * 5)

    # OB strength
    if 'OB' in signal['type']:
        strength = signal.get('strength', 0)
        score += min(2.0, strength * 0.5)

    # Confirmation — next candle moves in signal direction
    idx = signal.get('idx', 0)
    direction = signal.get('direction', '')
    if idx + 2 < len(ohlcv):
        nxt = ohlcv[idx + 1]
        if direction == 'bull' and nxt['c'] > ohlcv[idx]['c']:
            score += 1.0
        elif direction == 'bear' and nxt['c'] < ohlcv[idx]['c']:
            score += 1.0

    return min(5.0, score)


# ═══════════════════════════════════════════════════════════════════
# Utility — get signal direction summary
# ═══════════════════════════════════════════════════════════════════


def signal_summary(signals):
    """Summarise detected signals by type and direction."""
    counts = {}
    dirs = {}
    for s in signals:
        t = s['type']
        counts[t] = counts.get(t, 0) + 1
        d = s.get('direction', 'n/a')
        dirs[t] = d
    return counts, dirs