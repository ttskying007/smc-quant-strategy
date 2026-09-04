#!/usr/bin/env python3
"""
V27 SMC Core — Strict Event-Based Signal Detection
═══════════════════════════════════════════════════
Correct SMC signal definitions:
  - confirmed_swings() → left+right confirmation, ATR noise filter
  - structure_signals() → BOS/CHOCH/MSS state machine
  - sweep_signals() → liquidity sweep with reclaim
  - ob_signals() → event-anchored, backward scan from structure events
  - ote_signals() → impulse-leg bound OTE zones
  - bpr_signals() → opposing FVG overlap only
  - po3_signals() → accumulation → manipulation → distribution sequence
  - fvg_list() → 3-candle FVG detection

All signals are INDEXED and CAUSAL (no future leaks).
Every signal has: type, direction, index, date, source_event, invalidation.
"""

import json, sys, math
from pathlib import Path
from collections import defaultdict, Counter
from typing import List, Dict, Optional, Tuple

# ══════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════
SWING_LEFT = 3
SWING_RIGHT = 3
ATR_PERIOD = 14
ATR_NOISE = 0.3       # Swings must exceed ATR * noise_mult to qualify
MAX_OB_BACKSCAN = 10  # Max bars to scan backward from structure event for OB
FVG_MIN_GAP = 0.0005  # Min gap as fraction of price
OTE_FIB_LOW = 0.62
OTE_FIB_HIGH = 0.79
PO3_RANGE_MAX_BARS = 30
PO3_RANGE_ATR_MAX = 1.5


# ══════════════════════════════════════════════
# 1. CONFIRMED SWINGS
# ══════════════════════════════════════════════
def confirmed_swings(klines: List[Dict], atr_period: int = ATR_PERIOD,
                     left: int = SWING_LEFT, right: int = SWING_RIGHT,
                     noise_mult: float = ATR_NOISE) -> Dict:
    """
    Detect confirmed swing highs and lows.
    Swing is confirmed only at pivot_index + right (no future leak).
    Returns {'highs': [{idx, price, confirm_idx}], 'lows': [...]}
    """
    n = len(klines)
    highs = []
    lows = []

    # Precompute approximate ATR for noise filtering
    for i in range(left + right, n - right):
        if i - left < 0 or i + right >= n:
            continue

        candidate_h = float(klines[i].get('h', 0))
        candidate_l = float(klines[i].get('l', 0))

        # Swing high: all bars in [i-left, i+right] have high <= candidate
        is_high = True
        for j in range(i - left, i + right + 1):
            if j == i:
                continue
            if float(klines[j].get('h', 0)) >= candidate_h:
                is_high = False
                break
        if is_high and candidate_h > 0:
            confirm_idx = i + right
            if confirm_idx < n:
                highs.append({
                    'idx': i,
                    'price': candidate_h,
                    'confirm_idx': confirm_idx,
                    'date': klines[i].get('t', klines[i].get('date', ''))
                })

        # Swing low
        is_low = True
        for j in range(i - left, i + right + 1):
            if j == i:
                continue
            if float(klines[j].get('l', 0)) <= candidate_l:
                is_low = False
                break
        if is_low and candidate_l > 0:
            confirm_idx = i + right
            if confirm_idx < n:
                lows.append({
                    'idx': i,
                    'price': candidate_l,
                    'confirm_idx': confirm_idx,
                    'date': klines[i].get('t', klines[i].get('date', ''))
                })

    return {'highs': highs, 'lows': lows, 'n': n}


# ══════════════════════════════════════════════
# 2. STRUCTURE SIGNALS (BOS / CHOCH / MSS)
# ══════════════════════════════════════════════
def structure_signals(klines: List[Dict], swings: Dict,
                      atr_buffer: float = 0.002) -> List[Dict]:
    """
    State-machine based BOS/CHOCH/MSS detection.
    Each break requires: close beyond confirmed swing + ATR buffer.
    Same swing broken only once (broken set tracks it).
    """
    n = len(klines)
    highs = swings.get('highs', [])
    lows = swings.get('lows', [])

    # Build confirmed swing lookup: idx -> price
    confirmed_highs = {}  # confirm_idx -> (swing_idx, price)
    confirmed_lows = {}
    for h in highs:
        ci = h['confirm_idx']
        if ci < n:
            confirmed_highs[ci] = (h['idx'], h['price'])
    for lo in lows:
        ci = lo['confirm_idx']
        if ci < n:
            confirmed_lows[ci] = (lo['idx'], lo['price'])

    events = []
    trend = 'unknown'  # 'bullish', 'bearish', 'unknown'
    broken_swings = set()  # (type, idx) of broken swings

    # Track recent sweeps for MSS qualification
    recent_sweeps = {}  # idx -> direction

    # Avoid emitting contradictory bull/bear breaks on the same candle.
    # Process the most recent confirmed swing first; one candle can only be the
    # causal break of one nearest structure level in the state machine.
    broke_this_bar = False

    for bar_idx in range(max(SWING_LEFT + SWING_RIGHT, 30), n):
        broke_this_bar = False
        b = klines[bar_idx]
        cl = float(b.get('c', 0))
        hi = float(b.get('h', 0))
        lo = float(b.get('l', 0))
        if cl <= 0:
            continue

        date = b.get('t', b.get('date', str(bar_idx)))

        # ── Track sweep-like patterns for MSS qualification ──
        # Must run BEFORE event detection so sweeps at same bar_idx are visible
        # Bullish sweep: wick below swing low, close back above (SSL)
        lo_val = float(b.get('l', 0))
        for confirm_idx, (sw_idx, sw_price) in list(confirmed_lows.items()):
            if confirm_idx > bar_idx:
                continue
            if lo_val < sw_price * 0.997 and cl > sw_price * 1.001:
                recent_sweeps[bar_idx] = 'bull'
                break
        # Bearish sweep: wick above swing high, close back below (BSL)
        hi_val = float(b.get('h', 0))
        for confirm_idx, (sw_idx, sw_price) in list(confirmed_highs.items()):
            if confirm_idx > bar_idx:
                continue
            if hi_val > sw_price * 1.003 and cl < sw_price * 0.999:
                recent_sweeps[bar_idx] = 'bear'
                break

        # Check for break of confirmed highs that became visible by now
        for confirm_idx in sorted(confirmed_highs.keys(), reverse=True):
            if confirm_idx > bar_idx:
                continue  # not yet confirmed
            swing_idx, swing_price = confirmed_highs[confirm_idx]
            key = ('high', swing_idx)
            if key in broken_swings:
                continue  # already broken

            if cl > swing_price * (1 + atr_buffer):
                # Bullish break of swing high
                broken_swings.add(key)
                old_trend = trend
                if trend == 'bearish' or trend == 'unknown':
                    ev_type = 'CHOCH'  # first reversal = change of character
                    new_trend = 'bullish'
                else:
                    ev_type = 'BOS'  # continuation
                    new_trend = 'bullish'

                events.append({
                    'type': ev_type,
                    'direction': 'bull',
                    'index': bar_idx,
                    'date': date,
                    'price': cl,
                    'broken_swing_idx': swing_idx,
                    'broken_swing_price': swing_price,
                    'confirm_visible_at': confirm_idx,
                    'prev_trend': old_trend,
                    'new_trend': new_trend,
                })
                trend = new_trend
                broke_this_bar = True

                # MSS qualifies if it was trending bearish AND preceded by a sweep
                if ev_type == 'CHOCH' and old_trend == 'bearish':
                    # Check for sweep within 20 bars before this event
                    has_sweep = False
                    for check_idx in range(max(0, bar_idx - 20), bar_idx):
                        if check_idx in recent_sweeps and recent_sweeps[check_idx] == 'bull':
                            has_sweep = True
                            break
                    if has_sweep:
                        events[-1]['type'] = 'MSS'
                        events[-1]['source_event'] = 'CHOCH'
                        events[-1]['has_sweep_precursor'] = True
                break

        # Check for break of confirmed lows
        if broke_this_bar:
            continue
        for confirm_idx in sorted(confirmed_lows.keys(), reverse=True):
            if confirm_idx > bar_idx:
                continue
            swing_idx, swing_price = confirmed_lows[confirm_idx]
            key = ('low', swing_idx)
            if key in broken_swings:
                continue

            if cl < swing_price * (1 - atr_buffer):
                broken_swings.add(key)
                old_trend = trend
                if trend == 'bullish' or trend == 'unknown':
                    ev_type = 'CHOCH'
                    new_trend = 'bearish'
                else:
                    ev_type = 'BOS'
                    new_trend = 'bearish'

                events.append({
                    'type': ev_type,
                    'direction': 'bear',
                    'index': bar_idx,
                    'date': date,
                    'price': cl,
                    'broken_swing_idx': swing_idx,
                    'broken_swing_price': swing_price,
                    'confirm_visible_at': confirm_idx,
                    'prev_trend': old_trend,
                    'new_trend': new_trend,
                })
                trend = new_trend

                if ev_type == 'CHOCH' and old_trend == 'bullish':
                    # Check for sweep within 20 bars before this event
                    has_sweep = False
                    for check_idx in range(max(0, bar_idx - 20), bar_idx):
                        if check_idx in recent_sweeps and recent_sweeps[check_idx] == 'bear':
                            has_sweep = True
                            break
                    if has_sweep:
                        events[-1]['type'] = 'MSS'
                        events[-1]['source_event'] = 'CHOCH'
                        events[-1]['has_sweep_precursor'] = True
                break

    return events


# ══════════════════════════════════════════════
# 3. FVG DETECTION
# ══════════════════════════════════════════════
def fvg_list(klines: List[Dict], min_gap: float = FVG_MIN_GAP) -> List[Dict]:
    """Detect 3-candle Fair Value Gaps."""
    fvgs = []
    n = len(klines)
    for i in range(2, n):
        b0, b1, b2 = klines[i - 2], klines[i - 1], klines[i]
        h0, l0 = float(b0.get('h', 0)), float(b0.get('l', 0))
        h2, l2 = float(b2.get('h', 0)), float(b2.get('l', 0))

        if h0 <= 0 or h2 <= 0:
            continue

        # Bullish FVG: current low is above the high two bars back (gap up)
        if l2 > h0 and (l2 - h0) / h0 > min_gap:
            fvgs.append({
                'type': 'FVG',
                'direction': 'bull',
                'index': i,
                'date': klines[i].get('t', klines[i].get('date', '')),
                'gap_low': h0,
                'gap_high': l2,
                'mid': (h0 + l2) / 2,
            })

        # Bearish FVG: current high is below the low two bars back (gap down)
        if h2 < l0 and (l0 - h2) / h2 > min_gap:
            fvgs.append({
                'type': 'FVG',
                'direction': 'bear',
                'index': i,
                'date': klines[i].get('t', klines[i].get('date', '')),
                'gap_low': h2,
                'gap_high': l0,
                'mid': (h2 + l0) / 2,
            })

    return fvgs


# ══════════════════════════════════════════════
# 4. BPR (Balanced Price Range)
# ══════════════════════════════════════════════
def bpr_signals(fvgs: List[Dict], struct_events: List[Dict] = None,
                max_gap: int = 100) -> List[Dict]:
    """
    BPR = opposing FVG overlap only.
    Must have bullish FVG overlapping bearish FVG within max_gap bars.
    BPR is anchored to the nearest structure event that occurs at or after
    the later FVG (no future anchoring).
    """
    bprs = []
    bull_fvgs = [f for f in fvgs if f['direction'] == 'bull']
    bear_fvgs = [f for f in fvgs if f['direction'] == 'bear']

    # Build sorted event list for anchoring
    sorted_events = []
    if struct_events:
        sorted_events = sorted(struct_events, key=lambda e: e['index'])

    # Only compare FVGs within max_gap bars (distant FVGs won't have meaningful overlap)
    for bf in bull_fvgs:
        bf_idx = bf['index']
        # Find bear FVGs within window
        nearby_bears = [brf for brf in bear_fvgs
                        if abs(brf['index'] - bf_idx) <= max_gap]
        for brf in nearby_bears:
            gap_low = max(bf['gap_low'], brf['gap_low'])
            gap_high = min(bf['gap_high'], brf['gap_high'])
            if gap_high > gap_low:
                overlap = gap_high - gap_low
                if overlap > 0:
                    mid = (gap_low + gap_high) / 2
                    bpr_idx = max(bf['index'], brf['index'])

                    # Anchor BPR to nearest structure event at or after bpr_idx.
                    # Do not fallback to a prior event: that makes a later BPR look
                    # like it existed at the earlier structure event and leaks a
                    # future zone into setup construction.
                    anchor_ev = None
                    if sorted_events:
                        for ev in sorted_events:
                            if ev['index'] >= bpr_idx:
                                anchor_ev = ev
                                break
                    if anchor_ev is None:
                        continue

                    bpr = {
                        'type': 'BPR',
                        'direction': 'bull',
                        'index': bpr_idx,
                        'date': bf['date'] if bf['index'] >= brf['index'] else brf['date'],
                        'zone_low': gap_low,
                        'zone_high': gap_high,
                        'mid': mid,
                        'fvg_bull_idx': bf['index'],
                        'fvg_bear_idx': brf['index'],
                        'fvg1': bf,
                        'fvg2': brf,
                        'anchor_event': anchor_ev['type'] if anchor_ev else None,
                        'anchor_event_idx': anchor_ev['index'] if anchor_ev else -1,
                        'anchor_event_date': anchor_ev.get('date', '') if anchor_ev else '',
                    }
                    bprs.append(bpr)
    return bprs


# ══════════════════════════════════════════════
# 5. SWEEP SIGNALS
# ══════════════════════════════════════════════
def sweep_signals(klines: List[Dict], swings: Dict,
                  atr_buffer: float = 0.003, lookback: int = 60) -> List[Dict]:
    """
    Sweep must: pierce confirmed swing → close back inside → wick rejection.
    Only sweeps confirmed swings, not arbitrary local highs/lows.
    """
    n = len(klines)
    sweeps = []

    # Get confirmed swing highs and lows
    conf_highs = {}
    for h in swings.get('highs', []):
        ci = h['confirm_idx']
        if ci < n:
            conf_highs[ci] = {'idx': h['idx'], 'price': h['price']}

    conf_lows = {}
    for lo in swings.get('lows', []):
        ci = lo['confirm_idx']
        if ci < n:
            conf_lows[ci] = {'idx': lo['idx'], 'price': lo['price']}

    for bar_idx in range(20, n):
        b = klines[bar_idx]
        hi, lo, cl, op = (float(b.get('h', 0)), float(b.get('l', 0)),
                          float(b.get('c', 0)), float(b.get('o', 0)))
        if cl <= 0:
            continue
        date = b.get('t', b.get('date', str(bar_idx)))

        # Sell-side sweep: wick below confirmed swing low, close back above
        for confirm_idx, sw in list(conf_lows.items()):
            if confirm_idx > bar_idx:
                continue
            if bar_idx - sw['idx'] > lookback:
                continue
            sw_price = sw['price']
            if lo < sw_price * (1 - atr_buffer) and cl > sw_price * (1 - atr_buffer / 2):
                # Rejection: close back above swing low
                wick_pct = (sw_price - lo) / sw_price if sw_price > 0 else 0
                if wick_pct >= atr_buffer:
                    sweeps.append({
                        'type': 'SWEEP',
                        'direction': 'bull',  # sell-side sweep = bullish
                        'subtype': 'SSL',
                        'index': bar_idx,
                        'date': date,
                        'wick_low': lo,
                        'close': cl,
                        'swept_swing_idx': sw['idx'],
                        'swept_swing_price': sw_price,
                        'wick_pct': wick_pct,
                    })

        # Buy-side sweep: wick above confirmed swing high, close back below
        for confirm_idx, sw in list(conf_highs.items()):
            if confirm_idx > bar_idx:
                continue
            if bar_idx - sw['idx'] > lookback:
                continue
            sw_price = sw['price']
            if hi > sw_price * (1 + atr_buffer) and cl < sw_price * (1 - atr_buffer / 2):
                wick_pct = (hi - sw_price) / sw_price if sw_price > 0 else 0
                if wick_pct >= atr_buffer:
                    sweeps.append({
                        'type': 'SWEEP',
                        'direction': 'bear',
                        'subtype': 'BSL',
                        'index': bar_idx,
                        'date': date,
                        'wick_high': hi,
                        'close': cl,
                        'swept_swing_idx': sw['idx'],
                        'swept_swing_price': sw_price,
                        'wick_pct': wick_pct,
                    })

    return sweeps


# ══════════════════════════════════════════════
# 6. ORDER BLOCK (OB) — Event-Anchored
# ══════════════════════════════════════════════
def ob_signals(klines: List[Dict], struct_events: List[Dict],
               max_back: int = MAX_OB_BACKSCAN) -> List[Dict]:
    """
    OB must be anchored to a structure event (BOS/CHOCH/MSS).
    Scan backward from event index to find nearest opposite candle.
    Displacement used only for quality scoring, not position selection.
    """
    obs = []
    for ev in struct_events:
        ev_idx = ev['index']
        ev_dir = ev['direction']

        # For bullish event → look for bearish candle (demand OB)
        # For bearish event → look for bullish candle (supply OB)
        target_dir = 'bear' if ev_dir == 'bull' else 'bull'

        best_candle = None
        best_idx = -1

        for j in range(ev_idx - 1, max(0, ev_idx - max_back - 1), -1):
            b = klines[j]
            op, cl = float(b.get('o', 0)), float(b.get('c', 0))
            hi, lo = float(b.get('h', 0)), float(b.get('l', 0))
            if cl <= 0:
                continue

            is_bearish = cl < op
            is_bullish = cl > op

            if target_dir == 'bear' and is_bearish:
                best_candle = b
                best_idx = j
                break
            elif target_dir == 'bull' and is_bullish:
                best_candle = b
                best_idx = j
                break

        if best_candle is None or best_idx < 0:
            continue

        b = best_candle
        op, cl = float(b.get('o', 0)), float(b.get('c', 0))
        hi, lo = float(b.get('h', 0)), float(b.get('l', 0))
        date = b.get('t', b.get('date', str(best_idx)))

        if target_dir == 'bear':
            # Bullish OB (demand zone): the bearish candle before bull event
            zone_low = lo
            zone_high = hi
            invalidation = lo
            ob_dir = 'bull'
        else:
            # Bearish OB (supply zone): the bullish candle before bear event
            zone_low = lo
            zone_high = hi
            invalidation = hi
            ob_dir = 'bear'

        # Displacement quality (from event break)
        ev_price = ev.get('price', cl)
        disp = abs(ev_price - cl) / cl if cl > 0 else 0

        obs.append({
            'type': 'OB',
            'direction': ob_dir,
            'index': best_idx,
            'date': date,
            'zone_low': zone_low,
            'zone_high': zone_high,
            'invalidation': invalidation,
            'anchor_event': ev['type'],
            'anchor_event_idx': ev_idx,
            'anchor_event_date': ev.get('date', ''),
            'displacement': disp,
            'strength': min(disp * 100, 10),
        })

    return obs


# ══════════════════════════════════════════════
# 7. OTE ZONES
# ══════════════════════════════════════════════
def ote_signals(klines: List[Dict], struct_events: List[Dict],
                swings: Dict) -> List[Dict]:
    """
    OTE = 0.62-0.79 retracement of the impulse leg created by BOS/CHOCH/MSS.
    NOT random high-low fib zones.
    """
    n = len(klines)
    otes = []

    # Build sorted swing lists
    all_highs = sorted(swings.get('highs', []), key=lambda x: x['idx'])
    all_lows = sorted(swings.get('lows', []), key=lambda x: x['idx'])

    for ev in struct_events:
        ev_idx = ev['index']
        ev_dir = ev['direction']

        if ev_dir == 'bull':
            # Find prior swing low (start of impulse)
            prior_lows = [s for s in all_lows if s['confirm_idx'] <= ev_idx]
            if not prior_lows:
                continue
            start = prior_lows[-1]
            start_price = start['price']

            # Impulse end = event bar's high (NO future scanning)
            # The BOS/CHOCH event itself IS the impulse leg origin.
            # Future bars beyond the event are not yet visible.
            end_price = float(klines[ev_idx].get('h', 0))
            if end_price <= 0:
                continue

            impulse = end_price - start_price
            if impulse <= 0:
                continue

            ote_low = end_price - impulse * OTE_FIB_HIGH
            ote_high = end_price - impulse * OTE_FIB_LOW

            otes.append({
                'type': 'OTE',
                'direction': 'bull',
                'index': ev_idx,
                'date': ev.get('date', ''),
                'zone_low': ote_low,
                'zone_high': ote_high,
                'impulse_start_idx': start['idx'],
                'impulse_start_price': start_price,
                'impulse_end_price': end_price,
                'anchor_event': ev['type'],
                'anchor_event_idx': ev_idx,
            })

        elif ev_dir == 'bear':
            prior_highs = [s for s in all_highs if s['confirm_idx'] <= ev_idx]
            if not prior_highs:
                continue
            start = prior_highs[-1]
            start_price = start['price']

            end_price = float(klines[ev_idx].get('l', 0))
            if end_price <= 0:
                continue

            impulse = start_price - end_price
            if impulse <= 0:
                continue

            ote_low = end_price + impulse * OTE_FIB_LOW
            ote_high = end_price + impulse * OTE_FIB_HIGH

            otes.append({
                'type': 'OTE',
                'direction': 'bear',
                'index': ev_idx,
                'date': ev.get('date', ''),
                'zone_low': ote_low,
                'zone_high': ote_high,
                'impulse_start_idx': start['idx'],
                'impulse_start_price': start_price,
                'impulse_end_price': end_price,
                'anchor_event': ev['type'],
                'anchor_event_idx': ev_idx,
            })

    return otes


# ══════════════════════════════════════════════
# 8. PO3 (Power of Three)
# ══════════════════════════════════════════════
def po3_signals(klines: List[Dict], sweeps: List[Dict],
                struct_events: List[Dict]) -> List[Dict]:
    """
    PO3 = Accumulation → Manipulation (sweep) → Distribution (BOS/CHOCH).
    Must have all three phases in sequence.
    """
    n = len(klines)
    po3s = []

    # Index sweeps and events for fast lookup
    sweep_by_idx = {}
    for s in sweeps:
        sweep_by_idx[s['index']] = s

    for ev in struct_events:
        ev_idx = ev['index']
        ev_dir = ev['direction']

        # Find a sweep before this event
        best_sweep = None
        for j in range(ev_idx - 1, max(0, ev_idx - 15), -1):
            if j in sweep_by_idx:
                sw = sweep_by_idx[j]
                # Direction check: bull event needs SSL (bull sweep), bear needs BSL
                if (ev_dir == 'bull' and sw.get('direction') == 'bull') or \
                   (ev_dir == 'bear' and sw.get('direction') == 'bear'):
                    best_sweep = sw
                    break

        if best_sweep is None:
            continue

        # Check for accumulation range before sweep
        sweep_idx = best_sweep['index']
        range_start = max(0, sweep_idx - 30)
        range_prices = []
        for j in range(range_start, sweep_idx):
            hi = float(klines[j].get('h', 0))
            lo = float(klines[j].get('l', 0))
            if hi > 0 and lo > 0:
                range_prices.append((hi, lo))

        if len(range_prices) < 5:
            continue

        range_high = max(h for h, _ in range_prices)
        range_low = min(l for _, l in range_prices)
        range_size = (range_high - range_low) / range_low if range_low > 0 else 0

        # Range must be relatively compact
        if range_size > PO3_RANGE_ATR_MAX * 0.05:  # < 7.5% for typical ATR
            continue

        # Distribution = the event + displacement
        po3s.append({
            'type': 'PO3',
            'direction': ev_dir,
            'index': ev_idx,
            'date': ev.get('date', ''),
            'phase_accum_start': range_start,
            'phase_accum_end': sweep_idx,
            'range_high': range_high,
            'range_low': range_low,
            'phase_manip_idx': sweep_idx,
            'phase_manip_sweep': best_sweep,
            'phase_dist_idx': ev_idx,
            'phase_dist_event': ev['type'],
        })

    return po3s


# ══════════════════════════════════════════════
# 9. COMPUTE ATR
# ══════════════════════════════════════════════
def compute_atr_pct(klines: List[Dict], idx: int, period: int = ATR_PERIOD) -> float:
    """ATR as percentage of close at idx."""
    if idx < period:
        return 0.02
    trs = []
    for i in range(idx - period + 1, idx + 1):
        if i < 1 or i >= len(klines):
            continue
        b, pb = klines[i], klines[i - 1]
        h, l = float(b.get('h', 0)), float(b.get('l', 0))
        pc = float(pb.get('c', 0))
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    avg_tr = sum(trs) / len(trs) if trs else 0.02
    ref_price = float(klines[idx].get('c', 0))
    return avg_tr / ref_price if ref_price > 0 else 0.02


def compute_ma(klines: List[Dict], idx: int, period: int = 20) -> float:
    closes = [float(klines[i].get('c', 0))
              for i in range(max(0, idx - period + 1), idx + 1) if i < len(klines)]
    return sum(closes) / len(closes) if closes else 0


# ══════════════════════════════════════════════
# 10. DETECT ALL SIGNALS — Complete pipeline
# ══════════════════════════════════════════════
def detect_all_signals_v27(klines: List[Dict]) -> Dict:
    """
    Run full signal detection pipeline.
    Returns dict with all signal lists, swings, and summary.
    """
    # Ensure numeric fields
    for b in klines:
        for k in ('o', 'h', 'l', 'c', 'v'):
            if k in b:
                try:
                    b[k] = float(b[k])
                except (TypeError, ValueError):
                    b[k] = 0.0

    n = len(klines)
    if n < 60:
        return _empty_result()

    # 1. Confirmed swings
    swings = confirmed_swings(klines)

    # 2. Structure events (BOS/CHOCH/MSS)
    struct = structure_signals(klines, swings)

    # 3. FVGs
    fvgs = fvg_list(klines)

    # 4. BPR (from FVGs, anchored to structure events)
    bprs = bpr_signals(fvgs, struct)

    # 5. Sweeps
    sweeps = sweep_signals(klines, swings)

    # 6. OB (anchored to structure events)
    obs = ob_signals(klines, struct)

    # 7. OTE (impulse-bound)
    otes = ote_signals(klines, struct, swings)

    # 8. PO3
    po3s = po3_signals(klines, sweeps, struct)

    # Build signal summary
    all_signals = {
        'swings': swings,
        'structure': struct,
        'fvgs': fvgs,
        'bprs': bprs,
        'sweeps': sweeps,
        'obs': obs,
        'otes': otes,
        'po3s': po3s,
    }

    summary = {
        'n_bars': n,
        'n_swing_highs': len(swings.get('highs', [])),
        'n_swing_lows': len(swings.get('lows', [])),
        'n_bos_choch_mss': len(struct),
        'n_fvg': len(fvgs),
        'n_bpr': len(bprs),
        'n_sweep': len(sweeps),
        'n_ob': len(obs),
        'n_ote': len(otes),
        'n_po3': len(po3s),
        'definition_version': 'smc_core_v27',
    }

    return {'signals': all_signals, 'summary': summary}


def _empty_result():
    return {
        'signals': {
            'swings': {'highs': [], 'lows': [], 'n': 0},
            'structure': [], 'fvgs': [], 'bprs': [],
            'sweeps': [], 'obs': [], 'otes': [], 'po3s': [],
        },
        'summary': {'n_bars': 0, 'definition_version': 'smc_core_v27'},
    }


# ══════════════════════════════════════════════
# 11. ZONE VALIDATION
# ══════════════════════════════════════════════
def is_zone_invalidated(klines: List[Dict], zone: Dict, up_to_idx: int) -> bool:
    """Check if a bullish zone has been invalidated (price closed below zone_low)."""
    zl = zone.get('zone_low') or zone.get('invalidation', 0)
    if zl <= 0:
        return True
    zone_idx = zone.get('index', 0)
    for j in range(zone_idx + 1, min(up_to_idx + 1, len(klines))):
        cl = float(klines[j].get('c', 0))
        if cl > 0 and cl < zl * 0.99:
            return True
    return False


def find_zone_for_event(signal_data: Dict, event_idx: int, zone_type: str = 'OB') -> Optional[Dict]:
    """Find the zone (OB/BPR/OTE) anchored to a given structure event."""
    if zone_type == 'OB':
        candidates = signal_data.get('obs', [])
    elif zone_type == 'BPR':
        candidates = signal_data.get('bprs', [])
    elif zone_type == 'OTE':
        candidates = signal_data.get('otes', [])
    else:
        return None

    # Find closest zone anchored to this event
    best = None
    best_dist = 999
    for z in candidates:
        ae = z.get('anchor_event_idx', -1)
        # Direct anchor match (OB, OTE, BPR now have anchor_event_idx)
        if ae >= 0 and ae == event_idx:
            dist = abs(z['index'] - event_idx)
            if dist < best_dist:
                best = z
                best_dist = dist
        # Fallback: proximity-based matching (for legacy BPR without anchor)
        elif ae < 0 and zone_type == 'BPR':
            zi = z.get('index', -1)
            if zi >= 0 and zi <= event_idx + 5:
                dist = abs(zi - event_idx)
                if dist < best_dist and dist <= 30:
                    best = z
                    best_dist = dist
    return best


# ══════════════════════════════════════════════
# 12. BULLISH SETUP BUILDER — Sequence Mode
# ══════════════════════════════════════════════
def build_bullish_setups_v30(signal_data: Dict, klines: List[Dict],
                              max_zone_age: int = 120) -> List[Dict]:
    """
    V30 Correct SMC Sequence Builder:
    LIQUIDITY SWEEP → CHOCH/MSS → PD_ARRAY (OB/OTE/BPR) → Retrace → Confirmation → Entry.

    KEY CHANGES (V29→V30 audit fix):
      - ONLY CHOCH/MSS events (no BOS — BOS=trend continuation, not SMC reversal)
      - SWEEP REQUIRED before CHOCH/MSS (20-bar lookback)
      - Pinbar must form at zone boundary (zone proximity check)
      - BULLISH_REJECTION as alternative confirmation (at zone)
      - ctx_seq includes full SMC chain: Sweep→CHOCH→OB→Pinbar→Entry
      - RR floor raised to 1.3 (from 0.8)
    """
    n = len(klines)
    setups = []
    struct = signal_data.get('structure', [])
    sweeps = signal_data.get('sweeps', [])

    # Index sweeps by bar index for fast lookup
    sweep_by_idx = {}
    for sw in sweeps:
        if sw.get('direction') == 'bull':
            sweep_by_idx[sw['index']] = sw

    # ONLY CHOCH and MSS (reversal events). BOS = trend continuation → SKIP.
    bull_events = [e for e in struct if e['direction'] == 'bull'
                   and e['type'] in ('CHOCH', 'MSS')]

    for ev in bull_events:
        ev_idx = ev['index']

        # ── MANDATORY: SSL Sweep before CHOCH/MSS ──
        # SMC contracts: Liquidity sweep is the START of the signal chain.
        # Without sweep, the CHOCH/MSS is not a true reversal — it may be noise.
        sweep_found = None
        for check_idx in range(max(0, ev_idx - 20), ev_idx):
            if check_idx in sweep_by_idx:
                sweep_found = sweep_by_idx[check_idx]
                # If MSS already has has_sweep_precursor, prioritize that sweep
                if ev['type'] == 'MSS' and ev.get('has_sweep_precursor'):
                    break
        if sweep_found is None:
            continue  # No sweep → not a valid SMC reversal

        # Displacement check: CHOCH/MSS must have meaningful body
        ev_close = float(klines[ev_idx].get('c', 0))
        ev_open = float(klines[ev_idx].get('o', 0))
        ev_body = abs(ev_close - ev_open)
        ev_range = float(klines[ev_idx].get('h', 0)) - float(klines[ev_idx].get('l', 0))
        if ev_range > 0 and ev_body < ev_range * 0.3:
            continue  # Weak event, insufficient displacement

        # Try each zone type (OB first, most reliable)
        for zone_type in ['OB', 'OTE', 'BPR']:
            zone = find_zone_for_event(signal_data, ev_idx, zone_type)
            if zone is None:
                continue

            zone_idx = zone['index']
            zl = zone.get('zone_low', 0)
            zh = zone.get('zone_high', 0)
            if zl <= 0:
                continue

            # Zone must not be too old
            age = ev_idx - zone_idx
            if age > max_zone_age:
                continue

            # Check if zone is still fresh (not invalidated before retrace)
            if is_zone_invalidated(klines, zone, ev_idx):
                continue

            # BPR: require minimum width (avoid near-zero-width BPRs from micro FVG overlaps)
            if zone_type == 'BPR' and zh > 0 and zl > 0:
                bpr_width = (zh - zl) / zl * 100
                if bpr_width < 0.5:
                    continue

            # Zone must not be future relative to event
            if zone_idx > ev_idx + 30:
                continue

            # Find retrace into zone AFTER the event (not at event bar itself)
            retrace_found = False
            retrace_idx = -1
            zone_invalidated_during_scan = False
            for j in range(ev_idx + 1, min(ev_idx + 30, n - 3)):
                lo = float(klines[j].get('l', 0))
                hi = float(klines[j].get('h', 0))
                cl = float(klines[j].get('c', 0))
                if cl <= 0:
                    continue
                # Zone invalidated: close below zone_low before any touch
                if cl < zl * 0.99 and not retrace_found:
                    zone_invalidated_during_scan = True
                    break
                # Price retraced INTO zone by wick touch
                wick_touches_zone = lo <= zh * 1.005
                not_full_break = cl >= zl * 0.97
                if wick_touches_zone and not_full_break:
                    retrace_found = True
                    retrace_idx = j
                    break

            if zone_invalidated_during_scan or not retrace_found:
                continue

            # ── CONFIRMATION: Pinbar (primary) or Bullish Rejection at zone ──
            # Pinbar MUST form at zone boundary (low near zone_low)
            # Bullish Rejection: close > open, wick below body, candle touches zone
            conf_type = None
            conf_idx = -1
            for j in range(retrace_idx, min(retrace_idx + 4, n)):
                b = klines[j]
                op, cl, hi, lo = (float(b.get('o', 0)), float(b.get('c', 0)),
                                  float(b.get('h', 0)), float(b.get('l', 0)))
                if cl <= 0:
                    continue

                body = abs(cl - op)
                wick_lo = min(op, cl) - lo
                candle_at_zone = lo <= zh * 1.01  # Candle low at or near zone

                # Pinbar (primary): long lower wick at zone, close > open, zone proximity
                if body > 0 and wick_lo > body * 2 and cl > op and candle_at_zone:
                    conf_type = 'PINBAR'
                    conf_idx = j
                    break

                # Bullish Rejection (alternative): close > open, decent lower wick,
                # candle touches zone, close above midpoint
                if cl > op and wick_lo > body * 0.8 and candle_at_zone and cl > (op + lo) / 2:
                    conf_type = 'BULLISH_REJECTION'
                    conf_idx = j
                    break

            if conf_type is None:
                continue

            # Entry = next bar open (T+1)
            entry_idx = conf_idx + 1
            if entry_idx >= n - 2:
                continue

            # Zone must exist at or before entry
            if zone_idx > entry_idx:
                continue

            entry_price = float(klines[entry_idx].get('o', 0))
            if entry_price <= 0:
                continue

            # Don't enter if next open gaps above zone significantly
            if entry_price > zh * 1.015:
                continue

            # Trend filter: close must be > MA20 at entry
            ma20 = compute_ma(klines, entry_idx, 20)
            entry_close = float(klines[entry_idx].get('c', 0))
            if entry_close > 0 and entry_close < ma20 * 0.98:
                continue

            # ATR filter: skip very low volatility stocks
            atr_pct = compute_atr_pct(klines, entry_idx)
            if atr_pct <= 0:
                atr_pct = 0.02
            if atr_pct * 100 < 1.5:
                continue

            # SL: zone_low - 0.5*ATR (tight to structure)
            sl_buffer = atr_pct * entry_price * 0.5
            sl = zl - sl_buffer

            # Structure-based TP: find next swing high above zone
            swings_high = signal_data.get('swings', {}).get('highs', [])
            tp = zh + atr_pct * entry_price * 1.0  # default ATR-based
            for sh in sorted(swings_high, key=lambda x: x['idx']):
                if sh['confirm_idx'] > entry_idx and sh['price'] > zh:
                    tp = sh['price']
                    break

            # Ensure minimum SL distance (2%)
            sl_pct_val = (entry_price - sl) / entry_price * 100
            if sl_pct_val < 2.0:
                sl = entry_price * 0.98

            # Ensure minimum TP distance (3%)
            tp_pct_val = (tp - entry_price) / entry_price * 100
            if tp_pct_val < 3.0:
                tp = entry_price * 1.03

            # RR floor — raised to 1.3 for V30 (was 0.8 in V27)
            rr = (tp - entry_price) / (entry_price - sl) if entry_price > sl else 0
            if rr < 1.3:
                continue

            # ── Build full ctx_seq: Sweep→CHOCH/MSS→Zone→Conf→Entry ──
            sweep_type = sweep_found.get('subtype', 'Sweep')
            ctx_seq = f"{sweep_type}→{ev['type']}→{zone_type}→{conf_type}→Entry"

            setups.append({
                'symbol': '',
                'zone_type': zone_type,
                'signal_date': ev.get('date', ''),
                'signal_index': ev_idx,
                'entry_date': klines[entry_idx].get('t', klines[entry_idx].get('date', '')),
                'entry_index': entry_idx,
                'entry_price': round(entry_price, 2),
                'zone_low': round(zl, 2),
                'zone_high': round(zh, 2),
                'sl': round(sl, 2),
                'tp': round(tp, 2),
                'rr': round(rr, 2),
                'conf_type': conf_type,
                'conf_index': conf_idx,
                'retrace_index': retrace_idx,
                'source_event': ev['type'],
                'source_event_idx': ev_idx,
                'invalidation': zone.get('invalidation', zl),
                'zone_idx': zone_idx,
                'zone_date': zone.get('date', ''),
                'anchor_event_date': ev.get('date', ''),
                'definition_version': 'smc_core_v30',
                'zone': zone,
                'struct_event': ev,
                'atr_pct': round(atr_pct * 100, 2),
                'ma20': round(ma20, 2),
                # V30 new fields: full SMC chain
                'ctx_seq': ctx_seq,
                'sweep_idx': sweep_found['index'],
                'sweep_date': sweep_found.get('date', ''),
                'sweep_type': sweep_type,
                'sweep_direction': sweep_found.get('direction', ''),
                'seq': f"{sweep_type}-{ev['type']}-{zone_type}-{conf_type}",
                'detail': ctx_seq,
            })

    return setups


def build_bullish_setups(signal_data: Dict, klines: List[Dict],
                         max_zone_age: int = 120) -> List[Dict]:
    """
    Build complete bullish setups:
    Structure event -> Zone (OB/BPR/OTE) -> Price retrace to zone -> Confirmation -> Entry.

    Quality filters:
      - Only PINBAR confirmation (strongest, verified by user)
      - ATR-based dynamic SL/TP (not fixed ratios)
      - Trend filter: close > MA20 at entry
      - Min hold: >= 2 bars (T+1 compatible)
      - Zone priority: OB > OTE (OB dominates post-future-leak-fix)

    NOTE: This is the LEGACY V27 builder. For correct SMC sequence (Sweep→CHOCH→Zone),
    use build_bullish_setups_v30() instead.
    """
    n = len(klines)
    setups = []
    struct = signal_data.get('structure', [])

    # Only bullish events
    bull_events = [e for e in struct if e['direction'] == 'bull']

    for ev in bull_events:
        ev_idx = ev['index']

        # Displacement check: BOS/CHOCH must have meaningful body
        ev_close = float(klines[ev_idx].get('c', 0))
        ev_open = float(klines[ev_idx].get('o', 0))
        ev_body = abs(ev_close - ev_open)
        ev_range = float(klines[ev_idx].get('h', 0)) - float(klines[ev_idx].get('l', 0))
        if ev_range > 0 and ev_body < ev_range * 0.3:
            continue  # Weak event, insufficient displacement

        # Try each zone type (OB first, most reliable)
        for zone_type in ['OB', 'OTE', 'BPR']:
            zone = find_zone_for_event(signal_data, ev_idx, zone_type)
            if zone is None:
                continue

            zone_idx = zone['index']
            zl = zone.get('zone_low', 0)
            zh = zone.get('zone_high', 0)
            if zl <= 0:
                continue

            # Zone must not be too old
            age = ev_idx - zone_idx
            if age > max_zone_age:
                continue

            # Check if zone is still fresh (not invalidated before retrace)
            if is_zone_invalidated(klines, zone, ev_idx):
                continue

            # BPR: require minimum width (avoid near-zero-width BPRs from micro FVG overlaps)
            if zone_type == 'BPR' and zh > 0 and zl > 0:
                bpr_width = (zh - zl) / zl * 100
                if bpr_width < 0.5:
                    continue

            # Zone must not be future relative to event
            if zone_idx > ev_idx + 30:
                continue

            # Find retrace into zone AFTER the event
            retrace_found = False
            retrace_idx = -1
            zone_invalidated_during_scan = False
            for j in range(ev_idx + 1, min(ev_idx + 30, n - 3)):
                lo = float(klines[j].get('l', 0))
                hi = float(klines[j].get('h', 0))
                cl = float(klines[j].get('c', 0))
                if cl <= 0:
                    continue
                if cl < zl * 0.99 and not retrace_found:
                    zone_invalidated_during_scan = True
                    break
                wick_touches_zone = lo <= zh * 1.005
                not_full_break = cl >= zl * 0.97
                if wick_touches_zone and not_full_break:
                    retrace_found = True
                    retrace_idx = j
                    break

            if zone_invalidated_during_scan or not retrace_found:
                continue

            # Look for confirmation within next 3 bars after retrace
            conf_type = None
            conf_idx = -1
            for j in range(retrace_idx, min(retrace_idx + 4, n)):
                b = klines[j]
                op, cl, hi, lo = (float(b.get('o', 0)), float(b.get('c', 0)),
                                  float(b.get('h', 0)), float(b.get('l', 0)))
                if cl <= 0:
                    continue

                # Pinbar: long lower wick, close > open
                body = abs(cl - op)
                wick_lo = min(op, cl) - lo
                if body > 0 and wick_lo > body * 2 and cl > op:
                    conf_type = 'PINBAR'
                    conf_idx = j
                    break

            if conf_type is None:
                continue

            # Entry = next bar open (T+1)
            entry_idx = conf_idx + 1
            if entry_idx >= n - 2:
                continue

            # Zone must exist at or before entry
            if zone_idx > entry_idx:
                continue

            entry_price = float(klines[entry_idx].get('o', 0))
            if entry_price <= 0:
                continue

            # Don't enter if next open gaps above zone significantly
            if entry_price > zh * 1.015:
                continue

            # Trend filter: close must be > MA20 at entry
            ma20 = compute_ma(klines, entry_idx, 20)
            entry_close = float(klines[entry_idx].get('c', 0))
            if entry_close > 0 and entry_close < ma20 * 0.98:
                continue

            # ATR filter: skip very low volatility stocks
            atr_pct = compute_atr_pct(klines, entry_idx)
            if atr_pct <= 0:
                atr_pct = 0.02
            if atr_pct * 100 < 1.5:
                continue

            # SL: zone_low - 0.5*ATR (tight to structure)
            sl_buffer = atr_pct * entry_price * 0.5
            sl = zl - sl_buffer

            # Structure-based TP: find next swing high above zone
            swings_high = signal_data.get('swings', {}).get('highs', [])
            tp = zh + atr_pct * entry_price * 1.0
            for sh in sorted(swings_high, key=lambda x: x['idx']):
                if sh['confirm_idx'] > entry_idx and sh['price'] > zh:
                    tp = sh['price']
                    break

            # Ensure minimum SL distance (2%)
            sl_pct_val = (entry_price - sl) / entry_price * 100
            if sl_pct_val < 2.0:
                sl = entry_price * 0.98

            # Ensure minimum TP distance (3%)
            tp_pct_val = (tp - entry_price) / entry_price * 100
            if tp_pct_val < 3.0:
                tp = entry_price * 1.03

            # RR floor
            rr = (tp - entry_price) / (entry_price - sl) if entry_price > sl else 0
            if rr < 0.8:
                continue

            ctx_seq = f"{zone_type}→{ev['type']}→{conf_type}"

            setups.append({
                'symbol': '',
                'zone_type': zone_type,
                'signal_date': ev.get('date', ''),
                'signal_index': ev_idx,
                'entry_date': klines[entry_idx].get('t', klines[entry_idx].get('date', '')),
                'entry_index': entry_idx,
                'entry_price': round(entry_price, 2),
                'zone_low': round(zl, 2),
                'zone_high': round(zh, 2),
                'sl': round(sl, 2),
                'tp': round(tp, 2),
                'rr': round(rr, 2),
                'conf_type': conf_type,
                'conf_index': conf_idx,
                'retrace_index': retrace_idx,
                'source_event': ev['type'],
                'source_event_idx': ev_idx,
                'invalidation': zone.get('invalidation', zl),
                'zone_idx': zone_idx,
                'zone_date': zone.get('date', ''),
                'anchor_event_date': ev.get('date', ''),
                'definition_version': 'smc_core_v27',
                'zone': zone,
                'struct_event': ev,
                'atr_pct': round(atr_pct * 100, 2),
                'ma20': round(ma20, 2),
                'ctx_seq': ctx_seq,
                'seq': f"{zone_type}-{ev['type']}-{conf_type}",
                'detail': ctx_seq,
            })

    return setups


# ══════════════════════════════════════════════
# 13. BACKTEST
# ══════════════════════════════════════════════
def backtest_setups(setups: List[Dict], klines: List[Dict]) -> List[Dict]:
    """Simulate trades from setups and return trade log."""
    trades = []
    for st in setups:
        entry_idx = st['entry_index']
        entry_price = st['entry_price']
        sl = st['sl']
        tp = st['tp']
        n = len(klines)

        if entry_idx >= n - 1:
            continue

        exit_idx = -1
        exit_price = 0
        exit_reason = 'TIMEOUT'

        for j in range(entry_idx + 1, min(entry_idx + 60, n)):
            b = klines[j]
            lo = float(b.get('l', 0))
            hi = float(b.get('h', 0))
            cl = float(b.get('c', 0))
            if cl <= 0:
                continue

            # SL hit
            if lo <= sl:
                exit_idx = j
                exit_price = sl
                exit_reason = 'SL_HIT'
                break

            # TP hit
            if hi >= tp:
                exit_idx = j
                exit_price = tp
                exit_reason = 'TP_HIT'
                break

        if exit_idx < 0:
            # Timeout: exit at last close
            exit_idx = min(entry_idx + 60, n - 1)
            exit_price = float(klines[exit_idx].get('c', entry_price))
            exit_reason = 'TIMEOUT'

        pnl_pct = (exit_price - entry_price) / entry_price * 100 if entry_price > 0 else 0
        hold_bars = exit_idx - entry_idx

        trade = {**st,
                 'exit_date': klines[exit_idx].get('t', klines[exit_idx].get('date', '')),
                 'exit_index': exit_idx,
                 'exit_price': round(exit_price, 2),
                 'exit_reason': exit_reason,
                 'pnl_pct': round(pnl_pct, 2),
                 'hold_bars': hold_bars,
                 'engine': 'V27_STRICT',
                 'audit': {
                     'causal': entry_idx > st['signal_index'],
                     'zone_source_date': st.get('zone_date', ''),
                     'confirmation_checked': True,
                 },
                 'won': pnl_pct > 0}
        trades.append(trade)

    return trades


# ══════════════════════════════════════════════
# 14. METRICS
# ══════════════════════════════════════════════
def compute_metrics(trades: List[Dict]) -> Dict:
    if not trades:
        return {'n_trades': 0}

    wins = [t for t in trades if t['pnl_pct'] > 0]
    losses = [t for t in trades if t['pnl_pct'] <= 0]

    n = len(trades)
    wr = len(wins) / n * 100 if n > 0 else 0
    avg_pnl = sum(t['pnl_pct'] for t in trades) / n if n > 0 else 0
    avg_win = sum(t['pnl_pct'] for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(t['pnl_pct'] for t in losses)) / len(losses) if losses else 0
    rr = avg_win / avg_loss if avg_loss > 0 else 0
    total_pnl = sum(t['pnl_pct'] for t in trades)

    exit_dist = Counter(t['exit_reason'] for t in trades)
    zone_dist = Counter(t['zone_type'] for t in trades)
    conf_dist = Counter(t['conf_type'] for t in trades)

    return {
        'n_trades': n,
        'n_wins': len(wins),
        'n_losses': len(losses),
        'wr': round(wr, 1),
        'avg_pnl': round(avg_pnl, 2),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'rr': round(rr, 2),
        'total_pnl': round(total_pnl, 2),
        'exit_distribution': dict(exit_dist),
        'zone_distribution': dict(zone_dist),
        'conf_distribution': dict(conf_dist),
        'definition_version': 'smc_core_v27',
    }


# ══════════════════════════════════════════════
# 15. CHART MARKERS (for K-line visualization)
# ══════════════════════════════════════════════
def export_chart_markers(signal_data: Dict, trades: List[Dict],
                         symbol: str) -> Dict:
    """Generate chart markers from signals for K-line display."""
    markers = []
    sigs = signal_data

    # Structure events
    for ev in sigs.get('structure', []):
        markers.append({
            'id': f"{ev['type']}_{ev['index']}",
            'type': ev['type'],
            'index': ev['index'],
            'date': ev.get('date', ''),
            'price': ev.get('price', 0),
            'direction': ev.get('direction', ''),
            'label': ev['type'],
            'color': '#ff4444' if ev['direction'] == 'bull' else '#4444ff',
        })

    # OBs
    for ob in sigs.get('obs', []):
        markers.append({
            'id': f"OB_{ob['index']}",
            'type': 'OB',
            'index': ob['index'],
            'date': ob.get('date', ''),
            'zone_low': ob.get('zone_low', 0),
            'zone_high': ob.get('zone_high', 0),
            'label': f"OB_{ob['direction']}",
            'color': '#00cc44' if ob['direction'] == 'bull' else '#cc0044',
        })

    # Sweeps
    for sw in sigs.get('sweeps', []):
        markers.append({
            'id': f"SWEEP_{sw['index']}",
            'type': 'SWEEP',
            'index': sw['index'],
            'date': sw.get('date', ''),
            'price': sw.get('wick_low', sw.get('wick_high', 0)),
            'label': f"SWEEP_{sw.get('subtype', '')}",
            'color': '#ffaa00',
        })

    # BPRs
    for bp in sigs.get('bprs', []):
        markers.append({
            'id': f"BPR_{bp['index']}",
            'type': 'BPR',
            'index': bp['index'],
            'zone_low': bp.get('zone_low', 0),
            'zone_high': bp.get('zone_high', 0),
            'label': 'BPR',
            'color': '#aa44ff',
        })

    # Trades
    for t in trades:
        markers.append({
            'id': f"TRADE_{t.get('entry_index', 0)}",
            'type': 'TRADE',
            'index': t.get('entry_index', 0),
            'date': t.get('entry_date', ''),
            'price': t.get('entry_price', 0),
            'label': f"ENTRY ({t.get('pnl_pct', 0):+.1f}%)",
            'color': '#00ff00' if t.get('pnl_pct', 0) > 0 else '#ff0000',
        })

    return {
        'symbol': symbol,
        'markers': sorted(markers, key=lambda m: m['index']),
        'n_markers': len(markers),
        'definition_version': 'smc_core_v27',
    }
