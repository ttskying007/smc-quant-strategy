#!/usr/bin/env python3
from __future__ import annotations

from typing import Any, Dict, Mapping

DEMAND_VALID_AFTER_TAKEOVER = {'BULL_CONTINUATION', 'RECOVERY', 'ACCUMULATION'}
REVERSAL_RECOVERY_AFTER_TAKEOVER = {'RECOVERY', 'ACCUMULATION', 'BULL_CONTINUATION'}


def f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        return float(x)
    except Exception:
        return default


def _date_key(value: Any) -> str:
    return str(value or '')[:8]


def _env_state(row: Mapping[str, Any] | None) -> str:
    if not row:
        return ''
    return str(row.get('market_state') or row.get('market_state_v74') or row.get('state') or '')


def _post_takeover_state(row: Mapping[str, Any], env_by_date: Mapping[str, Mapping[str, Any]]) -> str:
    """Return the broad environment at entry/takeover time.

    V83 showed that many setups reclaim the POI but fail after entry because the
    broad environment deteriorates. V84 therefore re-checks environment after
    takeover, not only at original event creation.
    """
    for key in ('entry_date', 'v83_entry_date', 'v83_takeover_date'):
        d = _date_key(row.get(key))
        if d and d in env_by_date:
            return _env_state(env_by_date.get(d))
    return str(row.get('market_state') or '')


def _sweep_pierce_pct(row: Mapping[str, Any]) -> float:
    if row.get('sweep_pierce_pct') not in (None, ''):
        return f(row.get('sweep_pierce_pct'))
    sweep_level = f(row.get('sweep_level'))
    zone_low = f(row.get('zone_low'))
    if sweep_level and zone_low:
        return max(0.0, (sweep_level / zone_low - 1) * 100)
    return 0.0


def evaluate_v84_path_gate(row: Dict[str, Any], env_by_date: Mapping[str, Mapping[str, Any]] | None = None) -> Dict[str, Any]:
    """Split V83 into explicit smart-money paths.

    The goal is not another static post-filter.  It encodes the mechanism split
    found in V83:
    - continuation quality comes from BOS pullback + HOLD_ABOVE_POI;
    - weak post-reclaim higher-low is not enough smart-money control;
    - reversal requires SSL sweep -> CHOCH plus meaningful sweep pierce and a
      recovering environment after takeover.
    """
    env_by_date = env_by_date or {}
    out = {
        'v84_path_gate': False,
        'v84_path': 'REJECTED',
        'v84_post_takeover_market_state': _post_takeover_state(row, env_by_date),
        'v84_sweep_pierce_pct': round(_sweep_pierce_pct(row), 4),
    }
    story = str(row.get('story') or '')
    event_type = str(row.get('event_type') or '')
    trend = str(row.get('trend_regime') or '')
    takeover = str(row.get('v83_takeover_type') or '')
    post_state = out['v84_post_takeover_market_state']

    if takeover != 'HOLD_ABOVE_POI':
        if story.startswith('UP_CONTINUATION') or event_type == 'BOS_CONTINUATION':
            out['v84_reject_reason'] = 'CONTINUATION_REQUIRES_HOLD_ABOVE_POI'
        else:
            out['v84_reject_reason'] = 'REVERSAL_REQUIRES_HOLD_ABOVE_POI'
        return out

    if story.startswith('UP_CONTINUATION') or event_type == 'BOS_CONTINUATION':
        if trend != 'UP_CONTINUATION':
            out['v84_reject_reason'] = 'CONTINUATION_TREND_NOT_UP'
            return out
        if post_state not in DEMAND_VALID_AFTER_TAKEOVER:
            out['v84_reject_reason'] = 'POST_TAKEOVER_ENV_NOT_DEMAND_VALID'
            return out
        out.update({
            'v84_path_gate': True,
            'v84_path': 'CONTINUATION_HOLD_ABOVE_POI',
            'v84_reject_reason': '',
        })
        return out

    if story.startswith('DOWN_REVERSAL') or event_type == 'SSL_SWEEP_CHOCH_REVERSAL':
        if event_type != 'SSL_SWEEP_CHOCH_REVERSAL':
            out['v84_reject_reason'] = 'REVERSAL_REQUIRES_SSL_SWEEP_CHOCH'
            return out
        if _sweep_pierce_pct(row) < 0.8:
            out['v84_reject_reason'] = 'REVERSAL_SWEEP_PIERCE_TOO_WEAK'
            return out
        if str(row.get('market_state') or '') == 'MIXED' and post_state not in REVERSAL_RECOVERY_AFTER_TAKEOVER:
            out['v84_reject_reason'] = 'MIXED_REVERSAL_NEEDS_POST_TAKEOVER_RECOVERY'
            return out
        if post_state not in REVERSAL_RECOVERY_AFTER_TAKEOVER:
            out['v84_reject_reason'] = 'POST_TAKEOVER_ENV_NOT_REVERSAL_RECOVERY'
            return out
        out.update({
            'v84_path_gate': True,
            'v84_path': 'REVERSAL_SSL_CHOCH_HOLD_ABOVE_POI',
            'v84_reject_reason': '',
        })
        return out

    out['v84_reject_reason'] = 'UNKNOWN_STORY'
    return out
