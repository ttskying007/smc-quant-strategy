#!/usr/bin/env python3
"""Contract tests for V440 Protected-Swing Transfer generator."""
from __future__ import annotations
import importlib.util
from pathlib import Path

MODULE = Path(__file__).with_name('v440_protected_swing_transfer_generator.py')


def load_module():
    spec = importlib.util.spec_from_file_location('v440', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bar(o, h, l, c, t='20260101'):
    return {'o': float(o), 'h': float(h), 'l': float(l), 'c': float(c), 't': t}


def test_transfer_requires_newer_higher_confirmed_low_and_old_boundary_hold():
    m = load_module()
    bars = [bar(100, 102, 99, 101) for _ in range(20)]
    lows = [
        {'idx': 2, 'price': 90.0, 'confirm_idx': 5},
        {'idx': 9, 'price': 95.0, 'confirm_idx': 12},
    ]
    transfer = m.protected_transfer(bars, lows, previous_event_idx=7, event_idx=15)
    assert transfer['old']['price'] == 90.0
    assert transfer['new']['price'] == 95.0
    bars[10]['c'] = 89.0
    assert m.protected_transfer(bars, lows, 7, 15) is None


def test_lifecycle_uses_new_protected_low_as_hard_invalidation():
    m = load_module()
    bars = [
        bar(100, 101, 99, 100), bar(102, 105, 101, 104),
        bar(103, 104, 100, 102), bar(102, 106, 102, 105),
        bar(105, 107, 103, 106), bar(106, 108, 105, 107),
    ]
    assert m.lifecycle(bars, 1, 100, 104, 99) == (2, 3, 4, 5)
    bars[2]['c'] = 98
    assert m.lifecycle(bars, 1, 100, 104, 99) is None


def test_poi_must_belong_to_transfer_leg_after_new_swing():
    m = load_module()
    bars = [bar(100, 101, 99, 101) for _ in range(12)]
    bars[5] = bar(101, 102, 99, 100)
    bars[8] = bar(100, 103, 99, 101)
    poi = m.demand_poi(bars, event_idx=10, new_swing_idx=7)
    assert poi is None
    bars[8] = bar(100, 103, 99, 101)
    bars[9] = bar(100, 103, 99, 101)
    bars[7] = bar(102, 103, 99, 100)
    assert m.demand_poi(bars, 10, 7)['idx'] == 7


if __name__ == '__main__':
    tests = [value for name, value in sorted(globals().items()) if name.startswith('test_')]
    for test in tests:
        test()
    print(f'PASS: {len(tests)} V440 Protected-Swing Transfer tests')
