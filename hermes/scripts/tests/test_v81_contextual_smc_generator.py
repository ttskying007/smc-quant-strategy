#!/usr/bin/env python3
"""Tests for V81 environment-aware SMC lifecycle generator.

These tests encode the next architecture requirement: candidates must be generated
from broad context -> trend -> event -> POI -> entry -> exit semantics, not by
renaming FVG/OB labels on old trades.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'v25'))

from v81_contextual_smc_generator import (  # noqa: E402
    classify_context,
    generate_candidates,
    locate_entry,
    locate_poi,
    next_exit_semantic,
)


def bar(t, o, h, l, c):
    return {'t': t, 'o': o, 'h': h, 'l': l, 'c': c}


def test_accumulation_environment_allows_up_continuation_bos_poi_reclaim():
    ks = [
        bar('20240101', 10.0, 10.2, 9.8, 10.0),
        bar('20240102', 10.0, 10.4, 9.9, 10.3),
        bar('20240103', 10.3, 10.6, 10.1, 10.5),
        bar('20240104', 10.5, 10.8, 10.3, 10.7),
        bar('20240105', 10.7, 11.2, 10.6, 11.1),  # BOS
        bar('20240106', 11.1, 11.2, 10.55, 10.65),  # last bearish POI retest
        bar('20240107', 10.65, 11.0, 10.58, 10.95),  # reclaim
        bar('20240108', 10.96, 11.5, 10.9, 11.4),
    ]
    env = {'market_state': 'ACCUMULATION', 'bull_breadth': 0.32, 'bear_breadth': 0.24, 'range_breadth': 0.44}

    context = classify_context(ks, 4, env)
    assert context['trend_regime'] == 'UP_CONTINUATION'
    assert context['environment_allows_demand'] is True

    cands = generate_candidates('TEST.SZ', ks, env_by_date={b['t']: env for b in ks})
    assert len(cands) == 1
    cand = cands[0]
    assert cand['story'] == 'UP_CONTINUATION_BOS_PULLBACK_TO_POI_RECLAIM'
    assert cand['event_type'] == 'BOS_CONTINUATION'
    assert cand['poi_type'] == 'DEMAND_OB'
    assert cand['entry_date'] == '20240108'
    assert cand['entry_semantic'] == 'NEXT_OPEN_AFTER_POI_RECLAIM'


def test_mixed_environment_blocks_continuation_even_when_bos_and_poi_exist():
    ks = [
        bar('20240201', 10.0, 10.2, 9.8, 10.0),
        bar('20240202', 10.0, 10.4, 9.9, 10.3),
        bar('20240203', 10.3, 10.6, 10.1, 10.5),
        bar('20240204', 10.5, 10.8, 10.3, 10.7),
        bar('20240205', 10.7, 11.2, 10.6, 11.1),
        bar('20240206', 11.1, 11.2, 10.55, 10.65),
        bar('20240207', 10.65, 11.0, 10.58, 10.95),
        bar('20240208', 10.96, 11.5, 10.9, 11.4),
    ]
    env = {'market_state': 'MIXED', 'bull_breadth': 0.31, 'bear_breadth': 0.37, 'range_breadth': 0.32}

    cands = generate_candidates('TEST.SZ', ks, env_by_date={b['t']: env for b in ks})
    assert cands == []


def test_bear_risk_allows_only_ssl_sweep_choch_reversal_not_plain_bos():
    ks = [
        bar('20240301', 10.0, 10.2, 9.8, 10.1),
        bar('20240302', 10.1, 10.15, 9.55, 9.7),
        bar('20240303', 9.7, 9.85, 9.35, 9.5),
        bar('20240304', 9.5, 9.65, 9.2, 9.35),
        bar('20240305', 9.35, 9.55, 9.0, 9.15),
        bar('20240306', 9.15, 9.5, 8.85, 9.32),  # SSL sweep, close back above prev low
        bar('20240307', 9.32, 9.92, 9.25, 9.86),  # CHOCH above recent LH
        bar('20240308', 9.86, 9.95, 9.22, 9.35),  # retest POI
        bar('20240309', 9.35, 9.78, 9.3, 9.72),  # reclaim
        bar('20240310', 9.72, 10.3, 9.7, 10.1),
    ]
    env = {'market_state': 'BEAR_RISK', 'bull_breadth': 0.18, 'bear_breadth': 0.55, 'range_breadth': 0.26}

    cands = generate_candidates('TEST.SZ', ks, env_by_date={b['t']: env for b in ks})
    assert len(cands) == 1
    cand = cands[0]
    assert cand['story'] == 'DOWN_REVERSAL_SSL_SWEEP_CHOCH_PULLBACK_TO_POI_RECLAIM'
    assert cand['event_type'] == 'SSL_SWEEP_CHOCH_REVERSAL'
    assert cand['environment_permission'] == 'REVERSAL_ONLY'


def test_liquidity_target_must_be_above_entry_not_old_break_level():
    ks = [
        bar('20240601', 10.0, 10.3, 9.8, 10.2),
        bar('20240602', 10.2, 10.5, 10.0, 10.4),
        bar('20240603', 10.4, 10.9, 10.2, 10.8),
        bar('20240604', 10.8, 11.4, 10.6, 11.2),
        bar('20240605', 11.2, 12.0, 11.0, 11.85),  # BOS over old 11.4
        bar('20240606', 11.5, 11.7, 10.9, 11.05),  # pullback POI
        bar('20240607', 11.05, 11.45, 11.0, 11.4),  # reclaim
        bar('20240608', 11.42, 12.2, 11.3, 12.0),  # future BSL target
        bar('20240609', 12.0, 12.4, 11.8, 12.3),
    ]
    event = {'event_type': 'BOS_CONTINUATION', 'event_idx': 4, 'swing_low_idx': 0, 'swing_high_idx': 4}
    poi = locate_poi(ks, event, {'market_state': 'BULL_CONTINUATION'})
    entry = locate_entry(ks, poi, event_idx=4, max_wait=3)
    assert entry['entry_valid'] is True
    assert poi['liquidity_target'] > entry['entry_price']
    assert poi['liquidity_target'] == 12.2


def test_poi_requires_discount_location_and_unbroken_reclaim_before_entry():
    ks = [
        bar('20240401', 10.0, 10.5, 9.9, 10.4),
        bar('20240402', 10.4, 10.8, 10.2, 10.7),
        bar('20240403', 10.7, 11.2, 10.5, 11.0),
        bar('20240404', 11.0, 11.4, 10.8, 11.3),
        bar('20240405', 11.3, 11.9, 11.2, 11.8),
        bar('20240406', 11.8, 12.0, 10.55, 10.6),  # deep close below POI = invalid
        bar('20240407', 10.6, 11.3, 10.5, 11.25),
        bar('20240408', 11.25, 11.6, 11.0, 11.5),
    ]
    event = {'event_type': 'BOS_CONTINUATION', 'event_idx': 4, 'swing_low_idx': 0, 'swing_high_idx': 4}
    poi = locate_poi(ks, event, {'market_state': 'BULL_CONTINUATION'})
    entry = locate_entry(ks, poi, event_idx=4, max_wait=3)
    assert poi['pd_zone'] in {'DISCOUNT', 'DEEP_DISCOUNT'}
    assert entry['entry_valid'] is False
    assert entry['reason'] == 'POI_CLOSED_BROKEN_BEFORE_RECLAIM'


def test_exit_semantics_distinguish_target_poi_break_and_trend_damage():
    poi = {'zone_low': 10.0, 'zone_high': 10.5, 'prior_structure_low': 9.7, 'liquidity_target': 11.8}
    target_hit = [bar('20240501', 10.6, 11.9, 10.4, 11.7)]
    poi_break = [bar('20240501', 10.6, 10.8, 9.9, 9.95)]
    trend_break = [bar('20240501', 10.6, 10.8, 9.6, 9.65)]

    assert next_exit_semantic(target_hit, poi, 0)['exit_signal'] == 'TAKE_PROFIT_LIQUIDITY_TARGET'
    assert next_exit_semantic(poi_break, poi, 0)['exit_signal'] == 'EXIT_POI_CLOSE_BREAK'
    assert next_exit_semantic(trend_break, poi, 0)['exit_signal'] == 'EXIT_TREND_STRUCTURE_DAMAGE'
