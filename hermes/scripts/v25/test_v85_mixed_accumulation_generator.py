#!/usr/bin/env python3
from __future__ import annotations

from v85_mixed_accumulation_generator import (
    classify_mixed_after_poi,
    generate_v85_candidates,
    zone_width_pct,
)


def bar(t, o, h, l, c):
    return {'t': t, 'o': o, 'h': h, 'l': l, 'c': c}


def test_mixed_narrow_poi_hold_above_is_accumulation_not_blocked():
    ks = [
        bar('20250101', 10.0, 10.4, 9.8, 10.1),
        bar('20250102', 10.1, 10.5, 9.9, 10.2),
        bar('20250103', 10.2, 10.6, 10.0, 10.3),
        bar('20250104', 10.3, 10.7, 10.1, 10.5),
    ]
    poi = {'zone_low': 10.0, 'zone_high': 10.12, 'reclaim_idx': 3}

    out = classify_mixed_after_poi(ks, poi, 'MIXED')

    assert out['v85_market_substate'] == 'MIXED_ACCUMULATION'
    assert out['v85_mixed_accumulation'] is True


def test_mixed_wide_poi_is_distribution_even_if_reclaimed():
    ks = [
        bar('20250101', 10.0, 10.5, 9.8, 10.2),
        bar('20250102', 10.2, 10.8, 9.9, 10.6),
        bar('20250103', 10.6, 10.9, 10.2, 10.7),
        bar('20250104', 10.7, 11.0, 10.5, 10.8),
    ]
    poi = {'zone_low': 10.0, 'zone_high': 10.35, 'reclaim_idx': 3}

    out = classify_mixed_after_poi(ks, poi, 'MIXED')

    assert out['v85_market_substate'] == 'MIXED_DISTRIBUTION'
    assert out['v85_mixed_accumulation'] is False


def test_mixed_lower_low_after_reclaim_is_distribution():
    ks = [
        bar('20250101', 10.0, 10.4, 9.8, 10.2),
        bar('20250102', 10.2, 10.5, 9.9, 10.4),
        bar('20250103', 10.4, 10.6, 9.7, 10.5),
        bar('20250104', 10.5, 10.7, 9.6, 10.6),
    ]
    poi = {'zone_low': 10.0, 'zone_high': 10.1, 'reclaim_idx': 3}

    out = classify_mixed_after_poi(ks, poi, 'MIXED')

    assert out['v85_market_substate'] == 'MIXED_DISTRIBUTION'
    assert out['v85_reason'] == 'POST_RECLAIM_LOWER_LOW'


def test_zone_width_pct_uses_zone_low_high_contract():
    assert round(zone_width_pct({'zone_low': 100, 'zone_high': 101.5}), 2) == 1.5


def test_generate_v85_expands_continuation_with_wider_bos_pullback_window():
    ks = [
        bar('20250101', 10.0, 10.5, 9.8, 10.2),
        bar('20250102', 10.2, 10.7, 10.0, 10.5),
        bar('20250103', 10.5, 10.9, 10.2, 10.7),
        bar('20250104', 10.7, 11.1, 10.4, 10.9),
        bar('20250105', 10.9, 11.3, 10.6, 11.1),
        bar('20250106', 11.1, 11.8, 10.9, 11.6),  # BOS
        bar('20250107', 11.6, 11.7, 11.05, 11.10), # bearish pullback POI
        bar('20250108', 11.40, 11.50, 11.20, 11.32), # touch without close-break
        bar('20250109', 11.32, 11.60, 11.30, 11.50), # reclaim
        bar('20250110', 11.52, 11.7, 11.4, 11.6), # entry open
        bar('20250111', 11.4, 12.0, 11.3, 11.8),
    ]
    env = {b['t']: {'market_state': 'BULL_CONTINUATION'} for b in ks}

    rows = generate_v85_candidates('TEST.SZ', ks, env, lookbacks=(8,))

    assert rows
    assert rows[0]['v85_path'] == 'CONTINUATION_EXPANDED_HOLD_ABOVE_POI'
    assert rows[0]['select_date'] == rows[0]['event_date']
    assert rows[0]['join_date'] == rows[0]['entry_date']
    assert rows[0]['smart_money_cost']
    assert rows[0]['volatility_pct'] > 0
