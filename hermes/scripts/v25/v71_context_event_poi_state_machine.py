#!/usr/bin/env python3
"""Context→Event→POI state machine primitives for SMC long setups.

This module is intentionally small and deterministic. It separates:
1) trend/context, 2) SMC event, 3) demand POI, 4) POI reaction/reclaim,
so later engines do not treat a naked FVG/OB label as a valid signal.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _bar(b: Dict[str, Any], k: str) -> float:
    return f(b.get(k))


def classify_market_context(ks: List[Dict[str, Any]], idx: int, lookback: int = 6) -> Dict[str, Any]:
    start = max(0, idx - lookback + 1)
    win = ks[start:idx + 1]
    if len(win) < 4:
        return {'context': 'RANGE_OR_TRANSITION_CONTEXT', 'score': 0, 'reason': 'INSUFFICIENT_BARS'}
    highs = [_bar(b, 'h') for b in win]
    lows = [_bar(b, 'l') for b in win]
    closes = [_bar(b, 'c') for b in win]
    high_slope = highs[-1] - highs[0]
    low_slope = lows[-1] - lows[0]
    close_slope = closes[-1] - closes[0]
    if high_slope > 0 and low_slope > 0 and close_slope > 0:
        return {'context': 'UP_CONTINUATION_CONTEXT', 'score': 2, 'reason': 'HH_HL_CLOSE_UP'}
    if high_slope < 0 and low_slope < 0 and close_slope < 0:
        if closes[-1] <= min(closes[:-1]):
            return {'context': 'DOWN_CONTINUATION_DANGER', 'score': -2, 'reason': 'LL_LH_CLOSE_DOWN'}
        return {'context': 'DOWN_REVERSAL_NEEDED_CONTEXT', 'score': -1, 'reason': 'LH_LL'}
    return {'context': 'RANGE_OR_TRANSITION_CONTEXT', 'score': 0, 'reason': 'MIXED_STRUCTURE'}


def detect_smc_events(ks: List[Dict[str, Any]], idx: int, lookback: int = 5) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    start = max(1, idx - lookback + 1)
    for i in range(start, idx + 1):
        prev_start = max(0, i - lookback)
        prev = ks[prev_start:i]
        if len(prev) < 2:
            continue
        prev_high = max(_bar(b, 'h') for b in prev)
        prev_low = min(_bar(b, 'l') for b in prev)
        recent_prev = ks[max(0, i - 3):i]
        recent_high = max(_bar(b, 'h') for b in recent_prev) if recent_prev else prev_high
        b = ks[i]
        c = _bar(b, 'c')
        h = _bar(b, 'h')
        l = _bar(b, 'l')
        o = _bar(b, 'o')
        if l < prev_low and c > prev_low:
            events.append({'event_type': 'SSL_SWEEP_RECLAIM', 'idx': i, 'date': b.get('t') or b.get('date'), 'level': prev_low})
        # Structure break is wick-through plus bullish close. Requiring close >
        # prior high misses many A-share CHOCH/BOS bars where the wick clears
        # liquidity and the body closes strong but just below the old swing high.
        if h > recent_high and c > o:
            has_recent_sweep = any(e['event_type'] == 'SSL_SWEEP_RECLAIM' and i - e['idx'] <= lookback for e in events)
            events.append({'event_type': 'CHOCH_BULL_REVERSAL' if has_recent_sweep else 'BOS_BULL_CONTINUATION', 'idx': i, 'date': b.get('t') or b.get('date'), 'level': recent_high})
        if c > o and h > recent_high and l > prev_low:
            events.append({'event_type': 'MSS_BULL_SHIFT', 'idx': i, 'date': b.get('t') or b.get('date'), 'level': recent_high})
    return events


def _last_bearish_before(ks: List[Dict[str, Any]], idx: int, max_back: int = 5) -> Optional[int]:
    for j in range(idx - 1, max(-1, idx - max_back - 1), -1):
        if _bar(ks[j], 'c') < _bar(ks[j], 'o'):
            return j
    return None


def build_demand_pois(ks: List[Dict[str, Any]], events: List[Dict[str, Any]], idx: int) -> List[Dict[str, Any]]:
    pois: List[Dict[str, Any]] = []
    for e in events:
        if e['event_type'] not in {'BOS_BULL_CONTINUATION', 'CHOCH_BULL_REVERSAL', 'MSS_BULL_SHIFT'}:
            continue
        ob_idx = _last_bearish_before(ks, e['idx'])
        if ob_idx is None:
            continue
        ob = ks[ob_idx]
        hi = max(_bar(ob, 'o'), _bar(ob, 'c'), _bar(ob, 'h'))
        lo = min(_bar(ob, 'o'), _bar(ob, 'c'), _bar(ob, 'l'))
        impulse_high = max(_bar(b, 'h') for b in ks[ob_idx:e['idx'] + 1])
        impulse_low = min(_bar(b, 'l') for b in ks[ob_idx:e['idx'] + 1])
        # Demand POI validity is based on where the resting bid starts
        # (zone_low for long demand), not the candle wick high. Using zone_high
        # misclassifies valid OB retests as premium/mid.
        pd_pos = (lo - impulse_low) / max(impulse_high - impulse_low, 1e-9)
        pois.append({
            'poi_type': 'OB_DEMAND', 'event_type': e['event_type'], 'event_idx': e['idx'],
            'zone_idx': ob_idx, 'zone_date': ob.get('t') or ob.get('date'),
            'zone_low': round(lo, 6), 'zone_high': round(hi, 6),
            'impulse_low': round(impulse_low, 6), 'impulse_high': round(impulse_high, 6),
            'pd_zone': 'OTE_DISCOUNT' if pd_pos <= 0.62 else 'PREMIUM_OR_MID',
        })
    return [p for p in pois if p['zone_idx'] <= idx]


def evaluate_entry_window(ks: List[Dict[str, Any]], poi: Dict[str, Any], start_idx: int, entry_idx: int) -> Dict[str, Any]:
    touched = False
    broken = False
    reaction = False
    touch_idx = None
    for i in range(max(0, start_idx), min(entry_idx + 1, len(ks))):
        b = ks[i]
        if _bar(b, 'l') <= f(poi['zone_high']) and _bar(b, 'h') >= f(poi['zone_low']):
            touched = True
            touch_idx = i if touch_idx is None else touch_idx
        if _bar(b, 'c') < f(poi['zone_low']):
            broken = True
        if touched and not broken and _bar(b, 'c') > f(poi['zone_high']):
            reaction = True
    return {'touched': touched, 'touch_idx': touch_idx, 'zone_broken_before_entry': broken, 'has_reaction': reaction}


def classify_setup_story(ks: List[Dict[str, Any]], ctx: Dict[str, Any], events: List[Dict[str, Any]], pois: List[Dict[str, Any]], entry_idx: int) -> Dict[str, Any]:
    fail: List[str] = []
    context = ctx.get('context')
    has_sweep = any(e['event_type'] == 'SSL_SWEEP_RECLAIM' for e in events)
    has_choch = any(e['event_type'] == 'CHOCH_BULL_REVERSAL' for e in events)
    has_bos = any(e['event_type'] == 'BOS_BULL_CONTINUATION' for e in events)
    valid_pois = []
    for poi in pois:
        evw = evaluate_entry_window(ks, poi, poi['event_idx'] + 1, entry_idx)
        if poi.get('pd_zone') not in {'OTE_DISCOUNT'}:
            continue
        if evw['zone_broken_before_entry']:
            continue
        if evw['touched'] and evw['has_reaction']:
            valid_pois.append((poi, evw))
    if not valid_pois:
        fail.append('NO_POI_REACTION_BEFORE_ENTRY')
    if context == 'UP_CONTINUATION_CONTEXT' and has_bos and valid_pois:
        poi, _ = valid_pois[-1]
        return {'valid_story': True, 'story_type': 'CONTINUATION_BOS_PULLBACK_POI_RECLAIM', 'poi_type': poi['poi_type'], 'fail_reasons': []}
    if context in {'DOWN_REVERSAL_NEEDED_CONTEXT', 'DOWN_CONTINUATION_DANGER', 'RANGE_OR_TRANSITION_CONTEXT'} and has_sweep and has_choch and valid_pois:
        poi, _ = valid_pois[-1]
        return {'valid_story': True, 'story_type': 'REVERSAL_SSL_SWEEP_CHOCH_POI_RECLAIM', 'poi_type': poi['poi_type'], 'fail_reasons': []}
    if context in {'DOWN_REVERSAL_NEEDED_CONTEXT', 'DOWN_CONTINUATION_DANGER'} and not (has_sweep and has_choch):
        fail.append('NO_VALID_LIQ_OR_STRUCTURE_EVENT')
    if context == 'UP_CONTINUATION_CONTEXT' and not has_bos:
        fail.append('NO_BOS_CONTINUATION_EVENT')
    return {'valid_story': False, 'story_type': 'INVALID_OR_INCOMPLETE_STORY', 'poi_type': None, 'fail_reasons': sorted(set(fail))}
