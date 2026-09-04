#!/usr/bin/env python3
"""Contract tests for the one-shot V439 Target-First DOL T+1 replay."""
from __future__ import annotations
import importlib.util
from pathlib import Path

MODULE = Path(__file__).with_name('v439_target_first_dol_frozen_t1_replay.py')


def load_module():
    spec = importlib.util.spec_from_file_location('v439', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bar(o, h, l, c, t):
    return {'o': float(o), 'h': float(h), 'l': float(l), 'c': float(c), 't': t}


def seed(**changes):
    row = {'eligible_entry_idx': '2', 'takeover_idx': '1', 'zone_low': '100', 'dol_price': '110'}
    row.update(changes)
    return row


def test_target_first_dol_is_the_frozen_target_and_exit_starts_t1():
    m = load_module()
    bars = [
        bar(100, 101, 99, 100, '20260101'),
        bar(102, 105, 101, 104, '20260102'),
        bar(105, 109, 104, 106, '20260103'),
        bar(106, 110, 103, 109, '20260104'),
    ] + [bar(109, 109, 108, 109, f'202602{i:02d}') for i in range(1, 32)]
    result = m.replay(seed(), bars)
    assert result['status'] == 'CLOSED'
    assert result['tp'] == 110.0
    assert result['exit_idx'] == 3
    assert result['exit_reason'] == 'PREDECLARED_DOL_TP_T1'
    assert result['t1_violation'] is False


def test_same_bar_sl_tp_collision_is_conservative_stop():
    m = load_module()
    bars = [
        bar(100, 101, 99, 100, '20260101'),
        bar(102, 105, 101, 104, '20260102'),
        bar(105, 109, 104, 106, '20260103'),
        bar(105, 111, 98, 100, '20260104'),
    ] + [bar(100, 101, 99, 100, f'202602{i:02d}') for i in range(1, 32)]
    result = m.replay(seed(), bars)
    assert result['exit_reason'] == 'SL_TP_COLLISION_CONSERVATIVE_T1'
    assert result['exit_price'] == 99.0


def test_entry_must_be_next_bar_after_takeover():
    m = load_module()
    bars = [bar(100, 101, 99, 100, f'202601{i:02d}') for i in range(1, 35)]
    assert m.replay(seed(eligible_entry_idx='3'), bars)['status'] == 'INVALID_ENTRY_CHRONOLOGY'


if __name__ == '__main__':
    tests = [value for name, value in sorted(globals().items()) if name.startswith('test_')]
    for test in tests:
        test()
    print(f'PASS: {len(tests)} V439 frozen-replay contract tests')
