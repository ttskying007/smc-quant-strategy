#!/usr/bin/env python3
from __future__ import annotations
from typing import Any, Dict

ALLOWED_ENV = {'BULL_CONTINUATION', 'BEAR_RISK', 'DISTRIBUTION', 'MIXED'}


def f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        return float(x)
    except Exception:
        return default


def enrich_v82_features(row: Dict[str, Any]) -> Dict[str, Any]:
    r = dict(row)
    entry = f(r.get('entry_price'))
    zl = f(r.get('zone_low'))
    zh = f(r.get('zone_high'))
    target = f(r.get('liquidity_target'))
    eq = f(r.get('equilibrium'))
    prior = f(r.get('prior_structure_low'))
    touch = int(f(r.get('touch_idx'), 0))
    reclaim = int(f(r.get('reclaim_idx'), 0))
    r['v82_risk_pct'] = (entry / zl - 1) * 100 if entry and zl else 999
    r['v82_zone_width_pct'] = (zh / zl - 1) * 100 if zh and zl else 999
    r['v82_target_rr'] = (target - entry) / (entry - zl) if target and entry and zl and entry > zl else 0
    r['v82_discount_depth_pct'] = (eq - zh) / eq * 100 if eq and zh else -999
    r['v82_prior_buffer_pct'] = (zl / prior - 1) * 100 if prior and zl else 999
    r['v82_reclaim_lag'] = reclaim - touch if reclaim and touch else 999
    return r


def passes_v82_quality_gate(row: Dict[str, Any]) -> bool:
    r = row if 'v82_risk_pct' in row else enrich_v82_features(row)
    if r.get('market_state') not in ALLOWED_ENV:
        return False
    if r.get('pd_zone') != 'DEEP_DISCOUNT':
        return False
    if not (1.5 < f(r.get('v82_risk_pct'), 999) <= 4.0):
        return False
    if not (0.5 < f(r.get('v82_zone_width_pct'), 999) <= 3.0):
        return False
    if f(r.get('v82_reclaim_lag'), 999) < 2:
        return False
    if f(r.get('v82_target_rr'), 0) < 1.0:
        return False
    if not (-5.0 <= f(r.get('v82_prior_buffer_pct'), 999) <= 5.0):
        return False
    return True
