#!/usr/bin/env python3
"""SL attribution for SMC raw/display split validation."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def classify_trade_sl(trade: Dict[str, Any]) -> str:
    reason = str(trade.get('exit_reason', ''))
    if 'SL' not in reason and 'STOP' not in reason:
        return 'NOT_SL'
    if 'TRAILING' in reason:
        return 'TRAILING_PROFIT_STOP'
    zl = _f(trade.get('raw_zone_low', trade.get('zone_low')))
    zh = _f(trade.get('raw_zone_high', trade.get('zone_high')))
    dl = _f(trade.get('display_zone_low'))
    dh = _f(trade.get('display_zone_high'))
    entry = _f(trade.get('entry_price'))
    sl = _f(trade.get('sl'))
    risk_pct = _f(trade.get('risk_pct'))
    if dl and dh and (abs(dl - zl) / max(zl, 1e-9) > 0.003 or abs(dh - zh) / max(zh, 1e-9) > 0.003):
        # Not necessarily bad now, but mark if trade still came from old display-only fields.
        if not trade.get('raw_zone_low') or not trade.get('raw_zone_high'):
            return 'DISPLAY_ZONE_ONLY'
    if trade.get('zone_invalidated_before_entry'):
        return 'ZONE_INVALIDATED_BEFORE_ENTRY'
    if trade.get('sl_was_capped_to_max_risk'):
        return 'STRUCTURAL_SL_TOO_WIDE_CAPPED'
    if entry and zh and entry > zh * 1.012:
        return 'ENTRY_TOO_LATE_CHASE'
    if entry and zl and entry < zl * 0.995:
        return 'ENTRY_BELOW_ZONE'
    if risk_pct and risk_pct < 1.2:
        return 'SL_TOO_TIGHT'
    if risk_pct and risk_pct > 4.0:
        return 'SL_TOO_WIDE'
    if 'GAP' in reason:
        return 'EXECUTION_GAP_SL'
    if trade.get('source_event') not in ('MSS', 'CHOCH'):
        return 'STRUCTURE_CONTEXT_WEAK'
    if not trade.get('sweep_idx'):
        return 'NO_LIQUIDITY_SWEEP_CONTEXT'
    return 'VALID_STRUCTURE_FAILED'


def summarize_attribution(trades: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    trades = list(trades)
    by_cause = Counter(classify_trade_sl(t) for t in trades)
    by_zone = defaultdict(Counter)
    for t in trades:
        by_zone[str(t.get('zone_type', ''))][classify_trade_sl(t)] += 1
    return {
        'n_trades': len(trades),
        'sl_trades': sum(v for k, v in by_cause.items() if k != 'NOT_SL'),
        'by_cause': dict(by_cause),
        'by_zone_cause': {k: dict(v) for k, v in by_zone.items()},
    }
