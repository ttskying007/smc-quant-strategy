#!/usr/bin/env python3
"""V78 SMC lifecycle state machine primitives.

Separates the long setup lifecycle into:
1) trend regime, 2) SMC event, 3) demand POI, 4) entry location,
5) exit/invalidation semantics.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        return float(x)
    except Exception:
        return default


def _v(b: Dict[str, Any], k: str) -> float:
    return f(b.get(k))


def _date(b: Dict[str, Any]) -> Any:
    return b.get('t') or b.get('date')


def classify_trend_regime(ks: List[Dict[str, Any]], idx: int, lookback: int = 5) -> Dict[str, Any]:
    start = max(0, idx - lookback + 1)
    win = ks[start:idx + 1]
    if len(win) < 4:
        return {'regime': 'RANGE_TRANSITION', 'score': 0, 'reason': 'INSUFFICIENT_BARS'}
    highs = [_v(b, 'h') for b in win]
    lows = [_v(b, 'l') for b in win]
    closes = [_v(b, 'c') for b in win]
    high_slope = highs[-1] - highs[0]
    low_slope = lows[-1] - lows[0]
    close_slope = closes[-1] - closes[0]
    if high_slope > 0 and low_slope > 0 and close_slope > 0:
        return {'regime': 'UP_CONTINUATION', 'score': 2, 'reason': 'HH_HL_CLOSE_UP'}
    if high_slope < 0 and low_slope < 0:
        return {'regime': 'DOWN_REVERSAL_REQUIRED', 'score': -2, 'reason': 'LH_LL_NEEDS_SSL_CHOCH'}
    if close_slope > 0 and lows[-1] >= min(lows[:-1]):
        return {'regime': 'RECOVERY_TRANSITION', 'score': 1, 'reason': 'RECOVERY_BUT_NOT_CONFIRMED_UPTREND'}
    return {'regime': 'RANGE_TRANSITION', 'score': 0, 'reason': 'MIXED_STRUCTURE'}


def _last_bearish_before(ks: List[Dict[str, Any]], idx: int, max_back: int = 6) -> Optional[int]:
    for j in range(idx - 1, max(-1, idx - max_back - 1), -1):
        if _v(ks[j], 'c') < _v(ks[j], 'o'):
            return j
    return None


def _previous_low(ks: List[Dict[str, Any]], idx: int, lookback: int) -> float:
    prev = ks[max(0, idx - lookback):idx]
    return min((_v(b, 'l') for b in prev), default=_v(ks[idx], 'l'))


def _previous_high(ks: List[Dict[str, Any]], idx: int, lookback: int) -> float:
    prev = ks[max(0, idx - lookback):idx]
    return max((_v(b, 'h') for b in prev), default=_v(ks[idx], 'h'))


def detect_smc_lifecycle_event(ks: List[Dict[str, Any]], idx: int, trend: Dict[str, Any], lookback: int = 5) -> Dict[str, Any]:
    regime = trend.get('regime')
    start = max(1, idx - lookback + 1)
    ssl_sweep_idx = None
    ssl_level = None
    for i in range(start, idx + 1):
        prev_low = _previous_low(ks, i, lookback)
        if _v(ks[i], 'l') < prev_low and _v(ks[i], 'c') > prev_low:
            ssl_sweep_idx = i
            ssl_level = prev_low
    b = ks[idx]
    recent_high = _previous_high(ks, idx, min(3, lookback))
    bullish_break = _v(b, 'h') > recent_high and _v(b, 'c') > _v(b, 'o')
    if regime in {'DOWN_REVERSAL_REQUIRED', 'RANGE_TRANSITION', 'RECOVERY_TRANSITION'} and ssl_sweep_idx is not None and bullish_break:
        return {
            'event_type': 'SSL_SWEEP_CHOCH_REVERSAL', 'event_idx': idx,
            'event_date': _date(b), 'sweep_idx': ssl_sweep_idx,
            'sweep_level': ssl_level, 'break_level': recent_high,
        }
    if regime == 'UP_CONTINUATION' and bullish_break:
        return {
            'event_type': 'BOS_CONTINUATION', 'event_idx': idx,
            'event_date': _date(b), 'break_level': recent_high,
        }
    return {'event_type': 'NO_VALID_SMC_EVENT', 'event_idx': idx, 'event_date': _date(b)}


def locate_demand_poi(ks: List[Dict[str, Any]], event: Dict[str, Any]) -> Dict[str, Any]:
    if event.get('event_type') not in {'BOS_CONTINUATION', 'SSL_SWEEP_CHOCH_REVERSAL'}:
        return {'poi_type': 'NO_DEMAND_POI', 'valid': False, 'reason': 'NO_VALID_EVENT'}
    event_idx = int(event['event_idx'])
    ob_idx = _last_bearish_before(ks, event_idx)
    if ob_idx is None:
        return {'poi_type': 'NO_DEMAND_POI', 'valid': False, 'reason': 'NO_BEARISH_OB_BEFORE_EVENT'}
    ob = ks[ob_idx]
    zone_low = min(_v(ob, 'o'), _v(ob, 'c'), _v(ob, 'l'))
    zone_high = max(_v(ob, 'o'), _v(ob, 'c'), _v(ob, 'h'))
    prior_hl = min((_v(b, 'l') for b in ks[max(0, ob_idx - 5):ob_idx]), default=zone_low)
    bsl_target = _previous_high(ks, event_idx, 10)
    return {
        'poi_type': 'DEMAND_OB', 'valid': True, 'zone_idx': ob_idx,
        'zone_date': _date(ob), 'zone_low': round(zone_low, 6),
        'zone_high': round(zone_high, 6), 'prior_hl': round(prior_hl, 6),
        'bsl_target': round(bsl_target, 6), 'source_event': event.get('event_type'),
    }


def evaluate_entry_location(ks: List[Dict[str, Any]], poi: Dict[str, Any], start_idx: int, entry_idx: int) -> Dict[str, Any]:
    if not poi.get('valid'):
        return {'entry_valid': False, 'entry_type': 'NO_VALID_POI', 'entry_story': 'INVALID'}
    zl, zh = f(poi.get('zone_low')), f(poi.get('zone_high'))
    touched = False
    closed_below = False
    reclaimed = False
    touch_idx = None
    for i in range(max(0, start_idx), min(entry_idx + 1, len(ks))):
        b = ks[i]
        if _v(b, 'l') <= zh and _v(b, 'h') >= zl:
            touched = True
            touch_idx = touch_idx if touch_idx is not None else i
        if _v(b, 'c') < zl:
            closed_below = True
        if touched and not closed_below and _v(b, 'c') > zh:
            reclaimed = True
    valid = touched and reclaimed and not closed_below
    source = poi.get('source_event')
    story = 'REVERSAL_LIQUIDITY_TO_DEMAND' if source == 'SSL_SWEEP_CHOCH_REVERSAL' else 'CONTINUATION_BOS_PULLBACK_TO_DEMAND'
    return {
        'entry_valid': valid,
        'entry_type': 'POI_RECLAIM_AFTER_PULLBACK' if valid else 'INVALID_POI_ENTRY',
        'entry_story': story if valid else 'INVALID',
        'touch_idx': touch_idx,
        'zone_broken_before_entry': closed_below,
    }


def classify_exit_semantics(ks: List[Dict[str, Any]], poi: Dict[str, Any], entry_idx: int, max_idx: Optional[int] = None) -> Dict[str, Any]:
    zl = f(poi.get('zone_low'))
    prior_hl = f(poi.get('prior_hl'))
    bsl = f(poi.get('bsl_target'))
    stop = len(ks) if max_idx is None else min(len(ks), int(max_idx) + 1)
    for i in range(max(0, entry_idx), stop):
        b = ks[i]
        if bsl and _v(b, 'h') >= bsl:
            return {'exit_signal': 'TAKE_PROFIT_BSL_HIT', 'exit_idx': i, 'exit_date': _date(b), 'exit_price': bsl}
        if zl and _v(b, 'c') < zl:
            return {'exit_signal': 'EXIT_POI_CLOSE_BREAK', 'exit_idx': i, 'exit_date': _date(b), 'exit_price': _v(b, 'c')}
        if prior_hl and _v(b, 'c') < prior_hl:
            return {'exit_signal': 'EXIT_TREND_HL_BREAK', 'exit_idx': i, 'exit_date': _date(b), 'exit_price': _v(b, 'c')}
    return {'exit_signal': 'HOLD_NORMAL_POI_RETEST', 'exit_idx': None, 'exit_date': None, 'exit_price': None}
