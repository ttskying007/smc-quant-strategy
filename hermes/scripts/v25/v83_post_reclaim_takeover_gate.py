#!/usr/bin/env python3
from __future__ import annotations

from typing import Any, Dict, List


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


def evaluate_post_reclaim_takeover(row: Dict[str, Any], ks: List[Dict[str, Any]], max_confirm_bars: int = 3) -> Dict[str, Any]:
    """Validate that smart money takes control after POI reclaim.

    V82 proved that touch+reclaim alone still allows many candidates that break
    trend structure immediately after reclaim.  V83 therefore requires an
    additional post-reclaim confirmation before the executable next-open entry:

    - hold/close above POI high, or
    - print a higher low above the touch low without closing below POI.

    Rejection is semantic, not TP/SL tuning: POI close break, micro-HL damage,
    no takeover, or no next open after confirmation.
    """
    if not ks:
        return {'v83_takeover_valid': False, 'v83_takeover_type': 'NO_KLINE'}

    touch_idx = int(f(row.get('touch_idx'), -1))
    reclaim_idx = int(f(row.get('reclaim_idx'), -1))
    zl = f(row.get('zone_low'))
    zh = f(row.get('zone_high'))
    prior = f(row.get('prior_structure_low'))
    if touch_idx < 0 or reclaim_idx < 0 or reclaim_idx >= len(ks) or not zl or not zh:
        return {'v83_takeover_valid': False, 'v83_takeover_type': 'BAD_INDEX_OR_ZONE'}

    touch_low = _v(ks[touch_idx], 'l') if touch_idx < len(ks) else zl
    # A post-reclaim pierce back into/below POI proves the reclaimed HL failed.
    # Use zone_low as the hard micro-HL boundary; prior_structure_low is only
    # used later for semantic trend-damage exits, not for entry confirmation.
    micro_break_level = zl
    start = reclaim_idx + 1
    end = min(len(ks), reclaim_idx + max_confirm_bars + 1)
    if start >= len(ks):
        return {'v83_takeover_valid': False, 'v83_takeover_type': 'NO_BAR_AFTER_RECLAIM'}

    for i in range(start, end):
        b = ks[i]
        close = _v(b, 'c')
        low = _v(b, 'l')
        if close < zl:
            return {
                'v83_takeover_valid': False,
                'v83_takeover_type': 'POI_CLOSE_BREAK_AFTER_RECLAIM',
                'v83_takeover_idx': i,
                'v83_takeover_date': _date(b),
            }
        if low < micro_break_level:
            return {
                'v83_takeover_valid': False,
                'v83_takeover_type': 'MICRO_HL_BREAK_AFTER_RECLAIM',
                'v83_takeover_idx': i,
                'v83_takeover_date': _date(b),
            }
        if close > zh and low >= zl:
            entry_idx = i + 1
            if entry_idx >= len(ks):
                return {
                    'v83_takeover_valid': False,
                    'v83_takeover_type': 'NO_NEXT_OPEN_AFTER_TAKEOVER',
                    'v83_takeover_idx': i,
                    'v83_takeover_date': _date(b),
                }
            return {
                'v83_takeover_valid': True,
                'v83_takeover_type': 'HOLD_ABOVE_POI',
                'v83_takeover_idx': i,
                'v83_takeover_date': _date(b),
                'v83_entry_idx': entry_idx,
                'v83_entry_date': _date(ks[entry_idx]),
                'v83_entry_price': round(_v(ks[entry_idx], 'o'), 6),
            }
        if low > touch_low and close >= zl:
            entry_idx = i + 1
            if entry_idx >= len(ks):
                return {
                    'v83_takeover_valid': False,
                    'v83_takeover_type': 'NO_NEXT_OPEN_AFTER_TAKEOVER',
                    'v83_takeover_idx': i,
                    'v83_takeover_date': _date(b),
                }
            return {
                'v83_takeover_valid': True,
                'v83_takeover_type': 'POST_RECLAIM_HIGHER_LOW',
                'v83_takeover_idx': i,
                'v83_takeover_date': _date(b),
                'v83_entry_idx': entry_idx,
                'v83_entry_date': _date(ks[entry_idx]),
                'v83_entry_price': round(_v(ks[entry_idx], 'o'), 6),
            }

    return {'v83_takeover_valid': False, 'v83_takeover_type': 'NO_POST_RECLAIM_TAKEOVER'}


def apply_v83_entry(row: Dict[str, Any], ks: List[Dict[str, Any]], features: Dict[str, Any] | None = None) -> Dict[str, Any]:
    ft = features or evaluate_post_reclaim_takeover(row, ks)
    out = dict(row)
    out.update(ft)
    if ft.get('v83_takeover_valid'):
        out['entry_idx'] = int(ft['v83_entry_idx'])
        out['entry_date'] = ft.get('v83_entry_date')
        out['entry_price'] = ft.get('v83_entry_price')
        out['join_date'] = ft.get('v83_entry_date')
        out['smart_money_cost'] = ft.get('v83_entry_price')
    return out
