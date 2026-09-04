#!/usr/bin/env python3
from __future__ import annotations

from v87_mtf_entry_rr_matrix import (
    compute_rr,
    daily_state,
    find_m60_window_for_date,
    m60_entry_plan,
    simulate_exit_legs,
)


def test_find_m60_window_for_entry_date_uses_same_day_and_next_day_only():
    bars = [
        {'t': '202401021030', 'o': 10, 'h': 10.2, 'l': 9.9, 'c': 10.1},
        {'t': '202401031030', 'o': 10.1, 'h': 10.4, 'l': 10.0, 'c': 10.3},
        {'t': '202401041030', 'o': 10.3, 'h': 10.6, 'l': 10.2, 'c': 10.5},
    ]
    win = find_m60_window_for_date(bars, '20240103', lookahead_days=1)
    assert [b['t'][:8] for b in win] == ['20240103', '20240104']


def test_m60_reclaim_entry_uses_reclaim_close_and_intraday_swing_sl():
    bars = [
        {'t': '202401031030', 'o': 10.2, 'h': 10.25, 'l': 9.95, 'c': 10.05},
        {'t': '202401031130', 'o': 10.05, 'h': 10.35, 'l': 10.0, 'c': 10.32},
        {'t': '202401031430', 'o': 10.32, 'h': 10.5, 'l': 10.25, 'c': 10.45},
    ]
    plan = m60_entry_plan(bars, zone_low=10.0, zone_high=10.3, daily_entry=10.5, mode='m60_reclaim', sl_mode='m60_reclaim_low')
    assert plan['entry_found'] is True
    assert plan['entry_price'] == 10.32
    assert plan['sl'] < 10.0
    assert plan['entry_time'] == '202401031130'


def test_compute_rr_rejects_invalid_or_tiny_risk():
    assert compute_rr(10, 10, 11) == 0
    assert compute_rr(10, 10.01, 11) == 0
    assert round(compute_rr(10, 9.5, 11), 2) == 2.0


def test_simulate_exit_legs_returns_tp1_tp2_runner_and_mfe_mae_r():
    daily = [
        {'t': '20240104', 'o': 10.0, 'h': 10.8, 'l': 9.9, 'c': 10.6},
        {'t': '20240105', 'o': 10.6, 'h': 11.6, 'l': 10.5, 'c': 11.4},
        {'t': '20240108', 'o': 11.4, 'h': 12.2, 'l': 11.2, 'c': 11.8},
    ]
    out = simulate_exit_legs(daily, entry_price=10.0, sl=9.5, tp1=10.5, tp2=11.0, tp3=12.0, max_hold=3)
    assert out['exit_reason'] in {'TP3_HIT', 'RUNNER_TRAIL', 'TIME_STOP'}
    assert len(out['exit_legs']) >= 2
    assert out['mfe_r'] >= 3.0
    assert out['mae_r'] <= 0.2


def test_daily_state_distinguishes_bull_recovery_and_bear_risk():
    bull = [{'c': x, 'h': x+0.2, 'l': x-0.2} for x in [10, 10.2, 10.4, 10.6, 10.9, 11.2]]
    bear = [{'c': x, 'h': x+0.2, 'l': x-0.2} for x in [11, 10.8, 10.5, 10.2, 10.0, 9.8]]
    assert daily_state(bull) in {'BULL_CONTINUATION', 'RECOVERY'}
    assert daily_state(bear) == 'BEAR_RISK'
