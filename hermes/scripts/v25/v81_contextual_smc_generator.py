#!/usr/bin/env python3
"""V81 environment-aware SMC candidate generator.

This module is intentionally built as a fresh signal layer instead of another
filter over old V71/V74 trades.  Candidate generation order is:

1. broad environment permission,
2. single-stock trend regime,
3. SMC event,
4. demand POI in discount location,
5. POI touch + reclaim entry,
6. semantic exit labels.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

DEMAND_VALID_MARKETS = {'ACCUMULATION', 'RECOVERY', 'BULL_CONTINUATION'}
REVERSAL_ALLOWED_MARKETS = {'BEAR_RISK', 'DISTRIBUTION', 'MIXED', 'ACCUMULATION', 'RECOVERY'}


def f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        return float(x)
    except Exception:
        return default


def _v(b: Dict[str, Any], key: str) -> float:
    return f(b.get(key))


def _date(b: Dict[str, Any]) -> Any:
    return b.get('t') or b.get('date')


def _env_state(env: Dict[str, Any]) -> str:
    return str(env.get('market_state') or env.get('market_state_v74') or '')


def _previous_high(ks: List[Dict[str, Any]], idx: int, lookback: int) -> float:
    return max((_v(b, 'h') for b in ks[max(0, idx - lookback):idx]), default=_v(ks[idx], 'h'))


def _previous_low(ks: List[Dict[str, Any]], idx: int, lookback: int) -> float:
    return min((_v(b, 'l') for b in ks[max(0, idx - lookback):idx]), default=_v(ks[idx], 'l'))


def _last_bearish_before(ks: List[Dict[str, Any]], idx: int, max_back: int = 8) -> Optional[int]:
    for j in range(idx - 1, max(-1, idx - max_back - 1), -1):
        if _v(ks[j], 'c') <= _v(ks[j], 'o'):
            return j
    return None


def classify_context(ks: List[Dict[str, Any]], idx: int, env: Dict[str, Any], lookback: int = 5) -> Dict[str, Any]:
    """Classify environment permission and local stock trend at idx.

    Environment is not a later filter: it decides which stories may be created.
    Demand-valid states permit continuation/reversal; risk states permit only
    explicit liquidity-sweep reversal setups.
    """
    state = _env_state(env)
    start = max(0, idx - lookback + 1)
    win = ks[start:idx + 1]
    if len(win) < 4:
        trend = 'RANGE_TRANSITION'
        reason = 'INSUFFICIENT_BARS'
    else:
        highs = [_v(b, 'h') for b in win]
        lows = [_v(b, 'l') for b in win]
        closes = [_v(b, 'c') for b in win]
        high_slope = highs[-1] - highs[0]
        low_slope = lows[-1] - lows[0]
        close_slope = closes[-1] - closes[0]
        if high_slope > 0 and low_slope > 0 and close_slope > 0:
            trend = 'UP_CONTINUATION'
            reason = 'HH_HL_CLOSE_UP'
        elif high_slope < 0 and low_slope < 0:
            trend = 'DOWN_REVERSAL_REQUIRED'
            reason = 'LH_LL_NEEDS_SSL_CHOCH'
        elif close_slope > 0 and lows[-1] >= min(lows[:-1]):
            trend = 'RECOVERY_TRANSITION'
            reason = 'RECOVERY_BUT_NOT_CONFIRMED_UPTREND'
        else:
            trend = 'RANGE_TRANSITION'
            reason = 'MIXED_STRUCTURE'

    if state in DEMAND_VALID_MARKETS:
        permission = 'DEMAND_CONTINUATION_OR_REVERSAL'
        allows_demand = True
    elif state in REVERSAL_ALLOWED_MARKETS:
        permission = 'REVERSAL_ONLY'
        allows_demand = False
    else:
        permission = 'BLOCKED'
        allows_demand = False

    return {
        'market_state': state,
        'environment_permission': permission,
        'environment_allows_demand': allows_demand,
        'trend_regime': trend,
        'trend_reason': reason,
    }


def detect_event(ks: List[Dict[str, Any]], idx: int, context: Dict[str, Any], lookback: int = 5) -> Dict[str, Any]:
    if idx <= 0:
        return {'event_type': 'NO_VALID_SMC_EVENT', 'event_idx': idx, 'event_date': _date(ks[idx])}

    permission = context.get('environment_permission')
    trend = context.get('trend_regime')
    b = ks[idx]
    recent_high = _previous_high(ks, idx, min(3, lookback))
    bullish_break = _v(b, 'h') > recent_high and _v(b, 'c') > _v(b, 'o')

    ssl_sweep_idx = None
    ssl_level = None
    for i in range(max(1, idx - lookback + 1), idx + 1):
        prev_low = _previous_low(ks, i, lookback)
        if _v(ks[i], 'l') < prev_low and _v(ks[i], 'c') > prev_low:
            ssl_sweep_idx = i
            ssl_level = prev_low

    if permission in {'DEMAND_CONTINUATION_OR_REVERSAL', 'REVERSAL_ONLY'} and ssl_sweep_idx is not None and bullish_break:
        if trend in {'DOWN_REVERSAL_REQUIRED', 'RANGE_TRANSITION', 'RECOVERY_TRANSITION'} or permission == 'REVERSAL_ONLY':
            return {
                'event_type': 'SSL_SWEEP_CHOCH_REVERSAL',
                'event_idx': idx,
                'event_date': _date(b),
                'sweep_idx': ssl_sweep_idx,
                'sweep_level': ssl_level,
                'break_level': recent_high,
                'swing_low_idx': ssl_sweep_idx,
                'swing_high_idx': idx,
            }

    if permission == 'DEMAND_CONTINUATION_OR_REVERSAL' and trend == 'UP_CONTINUATION' and bullish_break:
        lows = [_v(x, 'l') for x in ks[max(0, idx - lookback):idx + 1]]
        swing_low_idx = max(0, idx - lookback) + lows.index(min(lows)) if lows else max(0, idx - 1)
        return {
            'event_type': 'BOS_CONTINUATION',
            'event_idx': idx,
            'event_date': _date(b),
            'break_level': recent_high,
            'swing_low_idx': swing_low_idx,
            'swing_high_idx': idx,
        }

    return {'event_type': 'NO_VALID_SMC_EVENT', 'event_idx': idx, 'event_date': _date(b)}


def _future_liquidity_target(ks: List[Dict[str, Any]], event_idx: int, min_price: float, lookahead: int = 20) -> float:
    for j in range(event_idx + 1, min(len(ks), event_idx + lookahead + 1)):
        future_high = _v(ks[j], 'h')
        if future_high > min_price:
            return future_high
    return min_price


def locate_poi(ks: List[Dict[str, Any]], event: Dict[str, Any], env: Dict[str, Any]) -> Dict[str, Any]:
    """Find demand OB POI and validate it is below equilibrium/discount."""
    if event.get('event_type') not in {'BOS_CONTINUATION', 'SSL_SWEEP_CHOCH_REVERSAL'}:
        return {'valid': False, 'poi_type': 'NO_DEMAND_POI', 'reason': 'NO_VALID_EVENT'}
    event_idx = int(event['event_idx'])
    # Prefer the first bearish pullback after the bullish event.  This makes the
    # generator story-ordered: trend -> event -> pullback POI -> reclaim entry.
    ob_idx = None
    for j in range(event_idx + 1, min(len(ks), event_idx + 4)):
        if _v(ks[j], 'c') < _v(ks[j], 'o'):
            ob_idx = j
            break
    if ob_idx is None:
        ob_idx = _last_bearish_before(ks, event_idx)
    if ob_idx is None:
        return {'valid': False, 'poi_type': 'NO_DEMAND_POI', 'reason': 'NO_BEARISH_OB_AROUND_EVENT'}

    ob = ks[ob_idx]
    zone_low = min(_v(ob, 'o'), _v(ob, 'c'), _v(ob, 'l'))
    body_high = max(_v(ob, 'o'), _v(ob, 'c'))
    # Use the lower half of the bearish pullback body/wick as the effective
    # demand zone.  The full upper wick often represents the liquidity probe,
    # not the smart-money cost line.
    zone_high = min(body_high, zone_low + (_v(ob, 'h') - zone_low) * 0.5)
    swing_low_idx = int(event.get('swing_low_idx', max(0, event_idx - 5)))
    swing_high_idx = int(event.get('swing_high_idx', event_idx))
    swing_low = min((_v(b, 'l') for b in ks[min(swing_low_idx, swing_high_idx):max(swing_low_idx, swing_high_idx) + 1]), default=zone_low)
    swing_high = max((_v(b, 'h') for b in ks[min(swing_low_idx, swing_high_idx):max(swing_low_idx, swing_high_idx) + 1]), default=zone_high)
    eq = swing_low + (swing_high - swing_low) * 0.5
    discount = swing_low + (swing_high - swing_low) * 0.79
    if zone_high <= eq:
        pd_zone = 'DEEP_DISCOUNT'
    elif zone_high <= discount:
        pd_zone = 'DISCOUNT'
    else:
        return {'valid': False, 'poi_type': 'DEMAND_OB', 'reason': 'POI_NOT_IN_DISCOUNT', 'zone_idx': ob_idx}

    prior_structure_low = min((_v(b, 'l') for b in ks[max(0, ob_idx - 6):ob_idx]), default=zone_low)
    liquidity_target = _future_liquidity_target(ks, event_idx, max(_v(ks[event_idx], 'h'), zone_high))
    return {
        'valid': True,
        'poi_type': 'DEMAND_OB',
        'zone_idx': ob_idx,
        'zone_date': _date(ob),
        'zone_low': round(zone_low, 6),
        'zone_high': round(zone_high, 6),
        'pd_zone': pd_zone,
        'equilibrium': round(eq, 6),
        'prior_structure_low': round(prior_structure_low, 6),
        'liquidity_target': round(liquidity_target, 6),
        'source_event': event.get('event_type'),
    }


def locate_entry(ks: List[Dict[str, Any]], poi: Dict[str, Any], event_idx: int, max_wait: int = 5) -> Dict[str, Any]:
    if not poi.get('valid'):
        return {'entry_valid': False, 'entry_semantic': 'NO_VALID_POI', 'reason': poi.get('reason', 'NO_VALID_POI')}
    zl = f(poi.get('zone_low'))
    zh = f(poi.get('zone_high'))
    touched = False
    touch_idx = None
    for i in range(event_idx + 1, min(len(ks), event_idx + max_wait + 1)):
        b = ks[i]
        if _v(b, 'l') <= zl and _v(b, 'c') <= zh:
            if touched:
                return {'entry_valid': False, 'entry_semantic': 'INVALID', 'reason': 'POI_CLOSED_BROKEN_BEFORE_RECLAIM', 'touch_idx': touch_idx}
            touched = True
            touch_idx = i
            continue
        if _v(b, 'c') < zl:
            if touched:
                return {'entry_valid': False, 'entry_semantic': 'INVALID', 'reason': 'POI_CLOSED_BROKEN_BEFORE_RECLAIM', 'touch_idx': touch_idx}
            touched = True
            touch_idx = i
            continue
        if _v(b, 'l') <= zh and _v(b, 'h') >= zl:
            touched = True
            touch_idx = i if touch_idx is None else touch_idx
        if touched and _v(b, 'c') > zh:
            entry_idx = i + 1
            # The bar that touches/breaks the POI is not allowed to be its own
            # reclaim confirmation; require a later bar to prove reaction.
            if i == touch_idx:
                continue
            if entry_idx >= len(ks):
                return {'entry_valid': False, 'entry_semantic': 'WAIT_NEXT_OPEN', 'reason': 'NO_NEXT_BAR_AFTER_RECLAIM', 'touch_idx': touch_idx}
            return {
                'entry_valid': True,
                'entry_semantic': 'NEXT_OPEN_AFTER_POI_RECLAIM',
                'touch_idx': touch_idx,
                'reclaim_idx': i,
                'entry_idx': entry_idx,
                'entry_date': _date(ks[entry_idx]),
                'entry_price': round(_v(ks[entry_idx], 'o'), 6),
            }
    return {'entry_valid': False, 'entry_semantic': 'NO_RECLAIM', 'reason': 'NO_POI_RECLAIM_WITHIN_WAIT', 'touch_idx': touch_idx}


def next_exit_semantic(ks: List[Dict[str, Any]], poi: Dict[str, Any], start_idx: int) -> Dict[str, Any]:
    zl = f(poi.get('zone_low'))
    prior = f(poi.get('prior_structure_low'))
    target = f(poi.get('liquidity_target'))
    for i in range(max(0, start_idx), len(ks)):
        b = ks[i]
        if target and _v(b, 'h') >= target:
            return {'exit_signal': 'TAKE_PROFIT_LIQUIDITY_TARGET', 'exit_idx': i, 'exit_date': _date(b), 'exit_price': target}
        if prior and _v(b, 'c') < prior:
            return {'exit_signal': 'EXIT_TREND_STRUCTURE_DAMAGE', 'exit_idx': i, 'exit_date': _date(b), 'exit_price': _v(b, 'c')}
        if zl and _v(b, 'c') < zl:
            return {'exit_signal': 'EXIT_POI_CLOSE_BREAK', 'exit_idx': i, 'exit_date': _date(b), 'exit_price': _v(b, 'c')}
    return {'exit_signal': 'HOLD_NORMAL_POI_RETEST', 'exit_idx': None, 'exit_date': None, 'exit_price': None}


def generate_candidates(symbol: str, ks: List[Dict[str, Any]], env_by_date: Dict[str, Dict[str, Any]], lookback: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for idx in range(max(lookback - 1, 3), max(0, len(ks) - 2)):
        env = env_by_date.get(str(_date(ks[idx]))[:8], {})
        context = classify_context(ks, idx, env, lookback=lookback)
        if context.get('environment_permission') == 'BLOCKED':
            continue
        event = detect_event(ks, idx, context, lookback=lookback)
        if event.get('event_type') == 'NO_VALID_SMC_EVENT':
            continue
        poi = locate_poi(ks, event, env)
        if not poi.get('valid'):
            continue
        entry = locate_entry(ks, poi, idx, max_wait=5)
        if not entry.get('entry_valid'):
            continue

        if event['event_type'] == 'BOS_CONTINUATION':
            story = 'UP_CONTINUATION_BOS_PULLBACK_TO_POI_RECLAIM'
        else:
            story = 'DOWN_REVERSAL_SSL_SWEEP_CHOCH_PULLBACK_TO_POI_RECLAIM'
        exit_sem = next_exit_semantic(ks[entry['entry_idx']:], poi, 0)
        out.append({
            'symbol': symbol,
            'story': story,
            **context,
            **event,
            **poi,
            **entry,
            **{f'planned_{k}': v for k, v in exit_sem.items()},
        })
    return out
