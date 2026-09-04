#!/usr/bin/env python3
from __future__ import annotations

from v86_production_gate import passes_v86_production_gate


def row(**kw):
    base = {
        'v85_zone_width_pct': 1.4,
        'risk_pct': 1.3,
        'hold_bars': 1,
        'v83_takeover_type': 'HOLD_ABOVE_POI',
        'entry_date': '20250102',
        'exit_date': '20250103',
        'market_state': 'BULL_CONTINUATION',
    }
    base.update(kw)
    return base


def test_v86_keeps_v85_core_when_poi_is_tight_and_environment_not_recovery():
    assert passes_v86_production_gate(row()) is True


def test_v86_keeps_tight_recovery_rows_because_full_gate_must_keep_total_n_ge_500():
    assert passes_v86_production_gate(row(market_state='RECOVERY')) is True


def test_v86_rejects_wide_poi_above_1_6_percent_because_rejected_bucket_has_double_poi_break_rate():
    assert passes_v86_production_gate(row(v85_zone_width_pct=1.7)) is False


def test_v86_still_rejects_same_day_exit_for_t1():
    assert passes_v86_production_gate(row(entry_date='20250102', exit_date='20250102')) is False


def test_v86_still_requires_hold_above_poi_takeover():
    assert passes_v86_production_gate(row(v83_takeover_type='POST_RECLAIM_HIGHER_LOW')) is False
