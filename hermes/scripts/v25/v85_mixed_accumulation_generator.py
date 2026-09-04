#!/usr/bin/env python3
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from v81_contextual_smc_generator import (
    _date,
    f,
    generate_candidates,
    locate_entry,
    locate_poi,
    next_exit_semantic,
)
from v83_post_reclaim_takeover_gate import evaluate_post_reclaim_takeover


def _v(b: Dict[str, Any], key: str) -> float:
    return f(b.get(key))


def zone_width_pct(row: Dict[str, Any]) -> float:
    zl = f(row.get('zone_low'))
    zh = f(row.get('zone_high'))
    return (zh / zl - 1) * 100 if zl and zh else 999.0


def classify_mixed_after_poi(ks: List[Dict[str, Any]], poi_or_row: Dict[str, Any], market_state: str) -> Dict[str, Any]:
    if market_state != 'MIXED':
        return {
            'v85_market_substate': market_state,
            'v85_mixed_accumulation': False,
            'v85_reason': 'NOT_MIXED',
        }

    width = zone_width_pct(poi_or_row)
    if width > 1.5:
        return {
            'v85_market_substate': 'MIXED_DISTRIBUTION',
            'v85_mixed_accumulation': False,
            'v85_reason': 'POI_TOO_WIDE_FOR_MIXED_ACCUMULATION',
            'v85_zone_width_pct': round(width, 4),
        }

    reclaim_idx = int(f(poi_or_row.get('reclaim_idx'), -1))
    if 0 <= reclaim_idx < len(ks):
        zl = f(poi_or_row.get('zone_low'))
        start = max(0, reclaim_idx - 2)
        prior_low = min((_v(b, 'l') for b in ks[start:reclaim_idx]), default=zl)
        post_low = min((_v(b, 'l') for b in ks[reclaim_idx:min(len(ks), reclaim_idx + 3)]), default=prior_low)
        if post_low < min(zl, prior_low):
            return {
                'v85_market_substate': 'MIXED_DISTRIBUTION',
                'v85_mixed_accumulation': False,
                'v85_reason': 'POST_RECLAIM_LOWER_LOW',
                'v85_zone_width_pct': round(width, 4),
            }

    return {
        'v85_market_substate': 'MIXED_ACCUMULATION',
        'v85_mixed_accumulation': True,
        'v85_reason': 'NARROW_POI_HOLD_ABOVE_IN_MIXED',
        'v85_zone_width_pct': round(width, 4),
    }


def _previous_high(ks: List[Dict[str, Any]], idx: int, lookback: int) -> float:
    return max((_v(b, 'h') for b in ks[max(0, idx - lookback):idx]), default=_v(ks[idx], 'h'))


def _local_uptrend(ks: List[Dict[str, Any]], idx: int, lookback: int) -> bool:
    win = ks[max(0, idx - lookback + 1):idx + 1]
    if len(win) < 5:
        return False
    lows = [_v(b, 'l') for b in win]
    closes = [_v(b, 'c') for b in win]
    return closes[-1] > closes[0] and lows[-1] >= min(lows[:-1])


def _expanded_bos_event(ks: List[Dict[str, Any]], idx: int, lookback: int) -> Dict[str, Any]:
    b = ks[idx]
    recent_high = _previous_high(ks, idx, min(6, lookback))
    if not (_v(b, 'h') > recent_high and _v(b, 'c') > _v(b, 'o') and _local_uptrend(ks, idx, lookback)):
        return {'event_type': 'NO_VALID_SMC_EVENT'}
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


def _env_state(env: Dict[str, Any]) -> str:
    return str(env.get('market_state') or env.get('market_state_v74') or env.get('state') or '')


def _normalize_contract(row: Dict[str, Any], ks: List[Dict[str, Any]]) -> Dict[str, Any]:
    nr = dict(row)
    nr['select_date'] = nr.get('select_date') or nr.get('event_date') or nr.get('signal_date')
    nr['join_date'] = nr.get('join_date') or nr.get('entry_date')
    nr['smart_money_cost'] = nr.get('smart_money_cost') or round((f(nr.get('zone_low')) + f(nr.get('zone_high'))) / 2, 6)
    nr['volatility_pct'] = nr.get('volatility_pct') or round(max(zone_width_pct(nr), f(nr.get('risk_pct'), 0.0), 0.0001), 4)
    nr['v85_zone_width_pct'] = round(zone_width_pct(nr), 4)
    takeover = evaluate_post_reclaim_takeover(nr, ks)
    nr.update(takeover)
    return nr


def _candidate_from_event(symbol: str, ks: List[Dict[str, Any]], env: Dict[str, Any], event: Dict[str, Any], max_wait: int) -> Dict[str, Any] | None:
    poi = locate_poi(ks, event, env)
    if not poi.get('valid'):
        return None
    entry = locate_entry(ks, poi, int(event['event_idx']), max_wait=max_wait)
    if not entry.get('entry_valid'):
        return None
    exit_sem = next_exit_semantic(ks[entry['entry_idx']:], poi, 0)
    row = {
        'symbol': symbol,
        'story': 'UP_CONTINUATION_BOS_PULLBACK_TO_POI_RECLAIM',
        'market_state': _env_state(env),
        'environment_permission': 'DEMAND_CONTINUATION_OR_REVERSAL',
        'environment_allows_demand': True,
        'trend_regime': 'UP_CONTINUATION',
        'trend_reason': 'V85_EXPANDED_BOS_PULLBACK',
        **event,
        **poi,
        **entry,
        **{f'planned_{k}': v for k, v in exit_sem.items()},
    }
    return row


def generate_v85_candidates(
    symbol: str,
    ks: List[Dict[str, Any]],
    env_by_date: Dict[str, Dict[str, Any]],
    lookbacks: Iterable[int] = (5, 8, 13),
    max_wait: int = 8,
) -> List[Dict[str, Any]]:
    by_key: Dict[Tuple[Any, Any], Dict[str, Any]] = {}

    for row in generate_candidates(symbol, ks, env_by_date, lookback=5):
        nr = _normalize_contract(row, ks)
        mixed = classify_mixed_after_poi(ks, nr, nr.get('market_state', ''))
        nr.update(mixed)
        if nr.get('story') == 'UP_CONTINUATION_BOS_PULLBACK_TO_POI_RECLAIM' and nr.get('v83_takeover_type') == 'HOLD_ABOVE_POI':
            nr['v85_path'] = 'CONTINUATION_EXPANDED_HOLD_ABOVE_POI'
            by_key[(nr.get('event_date'), nr.get('entry_date'))] = nr
        elif nr.get('v85_mixed_accumulation') and nr.get('v83_takeover_type') == 'HOLD_ABOVE_POI':
            nr['v85_path'] = 'MIXED_ACCUMULATION_HOLD_ABOVE_POI'
            by_key[(nr.get('event_date'), nr.get('entry_date'))] = nr
        elif (
            nr.get('story') == 'DOWN_REVERSAL_SSL_SWEEP_CHOCH_PULLBACK_TO_POI_RECLAIM'
            and nr.get('market_state') == 'BEAR_RISK'
            and nr.get('v83_takeover_type') == 'HOLD_ABOVE_POI'
        ):
            nr['v85_path'] = 'BEAR_RISK_SSL_CHOCH_HOLD_ABOVE_POI'
            by_key[(nr.get('event_date'), nr.get('entry_date'))] = nr

    for lookback in lookbacks:
        for idx in range(max(lookback - 1, 3), max(0, len(ks) - 2)):
            env = env_by_date.get(str(_date(ks[idx]))[:8], {})
            if _env_state(env) not in {'BULL_CONTINUATION', 'RECOVERY', 'ACCUMULATION', 'MIXED'}:
                continue
            event = _expanded_bos_event(ks, idx, lookback)
            if event.get('event_type') == 'NO_VALID_SMC_EVENT':
                continue
            row = _candidate_from_event(symbol, ks, env, event, max_wait=max_wait)
            if not row:
                continue
            nr = _normalize_contract(row, ks)
            mixed = classify_mixed_after_poi(ks, nr, nr.get('market_state', ''))
            nr.update(mixed)
            if nr.get('market_state') == 'MIXED' and not nr.get('v85_mixed_accumulation'):
                continue
            if nr.get('v83_takeover_type') != 'HOLD_ABOVE_POI':
                continue
            nr['v85_path'] = 'MIXED_ACCUMULATION_HOLD_ABOVE_POI' if nr.get('v85_mixed_accumulation') else 'CONTINUATION_EXPANDED_HOLD_ABOVE_POI'
            by_key.setdefault((nr.get('event_date'), nr.get('entry_date')), nr)

    return list(by_key.values())
