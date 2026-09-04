#!/usr/bin/env python3
"""TDD tests for V78 SMC lifecycle state machine.

These tests encode the user's required decomposition:
1. trend regime first (up-continuation vs down-reversal vs range),
2. SMC event second (SSL sweep + CHOCH/MSS, or BOS continuation),
3. POI entry location third,
4. invalidation/exit reason last (POI close-break, trend structure break, or normal retest).
"""
from v78_smc_lifecycle_state_machine import (
    classify_trend_regime,
    detect_smc_lifecycle_event,
    locate_demand_poi,
    evaluate_entry_location,
    classify_exit_semantics,
)


def bar(o, h, l, c, t):
    return {'o': o, 'h': h, 'l': l, 'c': c, 't': t, 'v': 1000}


def test_uptrend_bos_pullback_to_intact_poi_is_continuation_entry():
    ks = [
        bar(10.0, 10.2, 9.8, 10.1, '20260101'),
        bar(10.1, 10.6, 10.0, 10.5, '20260102'),
        bar(10.5, 10.7, 10.25, 10.35, '20260103'),  # bearish demand OB
        bar(10.35, 11.05, 10.3, 10.95, '20260104'), # BOS
        bar(10.95, 11.15, 10.85, 11.05, '20260105'),
        bar(11.05, 11.08, 10.32, 10.62, '20260106'), # pullback into POI
        bar(10.62, 10.92, 10.45, 10.88, '20260107'), # reclaim
        bar(10.88, 11.2, 10.84, 11.12, '20260108'),
    ]
    trend = classify_trend_regime(ks, 4)
    event = detect_smc_lifecycle_event(ks, 4, trend)
    poi = locate_demand_poi(ks, event)
    entry = evaluate_entry_location(ks, poi, event['event_idx'] + 1, 6)

    assert trend['regime'] == 'UP_CONTINUATION'
    assert event['event_type'] == 'BOS_CONTINUATION'
    assert poi['poi_type'] == 'DEMAND_OB'
    assert entry['entry_valid'] is True
    assert entry['entry_type'] == 'POI_RECLAIM_AFTER_PULLBACK'


def test_downtrend_ssl_sweep_choch_pullback_is_reversal_entry_not_continuation():
    ks = [
        bar(12.0, 12.2, 11.8, 12.0, '20260101'),
        bar(12.0, 12.05, 11.25, 11.35, '20260102'),
        bar(11.35, 11.55, 10.85, 11.0, '20260103'),
        bar(11.0, 11.2, 10.45, 10.65, '20260104'),
        bar(10.65, 10.85, 10.15, 10.35, '20260105'),
        bar(10.35, 10.7, 9.88, 10.55, '20260106'),  # SSL sweep + reclaim
        bar(10.55, 11.35, 10.5, 11.25, '20260107'), # CHOCH/MSS
        bar(11.25, 11.3, 10.52, 10.62, '20260108'), # pullback to demand OB
        bar(10.62, 11.0, 10.55, 10.93, '20260109'), # reclaim
    ]
    trend = classify_trend_regime(ks, 5)
    event = detect_smc_lifecycle_event(ks, 6, trend)
    poi = locate_demand_poi(ks, event)
    entry = evaluate_entry_location(ks, poi, event['event_idx'] + 1, 8)

    assert trend['regime'] == 'DOWN_REVERSAL_REQUIRED'
    assert event['event_type'] == 'SSL_SWEEP_CHOCH_REVERSAL'
    assert entry['entry_valid'] is True
    assert entry['entry_story'] == 'REVERSAL_LIQUIDITY_TO_DEMAND'


def test_close_below_poi_is_real_invalidation_but_wick_retest_is_not():
    poi = {'zone_low': 10.30, 'zone_high': 10.70, 'prior_hl': 10.05, 'bsl_target': 11.25}
    entry_idx = 3
    ks_wick_retest = [
        bar(10.8, 11.0, 10.6, 10.9, '20260101'),
        bar(10.9, 11.1, 10.75, 10.95, '20260102'),
        bar(10.95, 11.0, 10.50, 10.80, '20260103'),
        bar(10.80, 10.85, 10.24, 10.42, '20260104'), # wick pierces POI, close inside
        bar(10.42, 10.95, 10.40, 10.90, '20260105'),
    ]
    assert classify_exit_semantics(ks_wick_retest, poi, entry_idx)['exit_signal'] == 'HOLD_NORMAL_POI_RETEST'

    ks_close_break = [
        bar(10.8, 11.0, 10.6, 10.9, '20260101'),
        bar(10.9, 11.1, 10.75, 10.95, '20260102'),
        bar(10.95, 11.0, 10.50, 10.80, '20260103'),
        bar(10.80, 10.85, 10.20, 10.22, '20260104'), # close below POI
    ]
    out = classify_exit_semantics(ks_close_break, poi, entry_idx)
    assert out['exit_signal'] == 'EXIT_POI_CLOSE_BREAK'
    assert out['exit_idx'] == 3


def test_break_prior_hl_exits_as_trend_damage_even_if_poi_not_closed_below():
    poi = {'zone_low': 10.30, 'zone_high': 10.70, 'prior_hl': 10.55, 'bsl_target': 11.25}
    ks = [
        bar(10.8, 11.0, 10.6, 10.9, '20260101'),
        bar(10.9, 11.1, 10.75, 10.95, '20260102'),
        bar(10.95, 11.0, 10.58, 10.80, '20260103'),
        bar(10.80, 10.88, 10.45, 10.50, '20260104'), # closes below prior HL but not below POI
    ]
    out = classify_exit_semantics(ks, poi, entry_idx=3)
    assert out['exit_signal'] == 'EXIT_TREND_HL_BREAK'
    assert out['exit_idx'] == 3


def test_nearest_bsl_hit_is_take_profit_target_before_structure_damage():
    poi = {'zone_low': 10.30, 'zone_high': 10.70, 'prior_hl': 10.05, 'bsl_target': 11.25}
    ks = [
        bar(10.8, 11.0, 10.6, 10.9, '20260101'),
        bar(10.9, 11.15, 10.75, 10.95, '20260102'),
        bar(10.95, 11.30, 10.9, 11.27, '20260103'), # takes nearest BSL
        bar(11.27, 11.3, 10.1, 10.2, '20260104'),
    ]
    out = classify_exit_semantics(ks, poi, entry_idx=1)
    assert out['exit_signal'] == 'TAKE_PROFIT_BSL_HIT'
    assert out['exit_idx'] == 2


def test_late_bsl_after_actual_stop_horizon_does_not_relabel_loss_as_tp():
    poi = {'zone_low': 10.30, 'zone_high': 10.70, 'prior_hl': 10.05, 'bsl_target': 11.25}
    ks = [
        bar(10.8, 11.0, 10.6, 10.9, '20260101'),
        bar(10.9, 11.0, 10.35, 10.55, '20260102'),
        bar(10.55, 10.6, 10.1, 10.20, '20260103'), # actual SL / POI close break
        bar(10.20, 11.40, 10.0, 11.30, '20260104'), # late BSL after stop must be ignored
    ]
    out = classify_exit_semantics(ks, poi, entry_idx=1, max_idx=2)
    assert out['exit_signal'] == 'EXIT_POI_CLOSE_BREAK'
    assert out['exit_idx'] == 2


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print(f'PASS {name}')
