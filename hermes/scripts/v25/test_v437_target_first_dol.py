#!/usr/bin/env python3
"""Contract tests for V437 Target-First DOL before full-market execution."""
from __future__ import annotations
import importlib.util
from pathlib import Path

MODULE = Path(__file__).with_name('v437_target_first_dol_generator.py')


def load_module():
    spec = importlib.util.spec_from_file_location('v437', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bar(o, h, l, c, t='20260101'):
    return {'o': float(o), 'h': float(h), 'l': float(l), 'c': float(c), 't': t}


def test_dol_is_visible_before_event_and_nearest_unconsumed_target():
    m = load_module()
    bars = [bar(99, 100, 98, 99) for _ in range(10)]
    bars[5] = bar(99, 103, 98, 100)
    bars[6] = bar(100, 104, 99, 102)
    highs = [
        {'idx': 1, 'price': 110.0, 'confirm_idx': 4},
        {'idx': 2, 'price': 105.0, 'confirm_idx': 5},
        {'idx': 4, 'price': 103.0, 'confirm_idx': 7},  # not visible before event=7
    ]
    chosen = m.choose_dol(bars, highs, event_idx=7)
    assert chosen['price'] == 105.0
    bars[6]['h'] = 105.0
    chosen = m.choose_dol(bars, highs, event_idx=7)
    assert chosen['price'] == 110.0


def test_lifecycle_requires_touch_then_later_reclaim_then_later_hold():
    m = load_module()
    bars = [
        bar(100, 101, 99, 100, '20260101'),
        bar(101, 104, 100, 103, '20260102'),  # event
        bar(103, 104, 101, 102, '20260103'),  # touch
        bar(102, 106, 102, 105, '20260104'),  # reclaim
        bar(105, 107, 103, 106, '20260105'),  # hold
        bar(106, 108, 105, 107, '20260106'),  # eligible entry still below DOL
    ]
    result = m.lifecycle(bars, event_idx=1, zone_low=100, zone_high=104, dol_price=110)
    assert result['status'] == 'TAKEOVER_CONFIRMED'
    assert (result['touch_idx'], result['reclaim_idx'], result['takeover_idx'], result['eligible_entry_idx']) == (2, 3, 4, 5)


def test_dol_consumed_or_poi_invalidated_before_entry_cancels():
    m = load_module()
    consumed = [
        bar(100, 101, 99, 100), bar(101, 104, 100, 103),
        bar(103, 110, 101, 109),
    ]
    assert m.lifecycle(consumed, 1, 100, 104, 110)['status'] == 'CANCEL_DOL_CONSUMED_BEFORE_ENTRY'
    invalid = [
        bar(100, 101, 99, 100), bar(101, 104, 100, 103),
        bar(102, 103, 98, 99),
    ]
    assert m.lifecycle(invalid, 1, 100, 104, 110)['status'] == 'CANCEL_POI_INVALIDATED'


def test_right_edge_is_wait_not_entry_or_failure():
    m = load_module()
    bars = [bar(100, 101, 99, 100), bar(101, 104, 100, 103), bar(103, 104, 101, 102)]
    result = m.lifecycle(bars, 1, 100, 104, 110)
    assert result['status'] == 'WAIT_RECLAIM_UNOBSERVED'
    assert result['eligible_entry_idx'] is None


def test_semantic_order_uses_visibility_not_demand_candle_order():
    m = load_module()
    result = {'touch_idx': 11, 'reclaim_idx': 12, 'takeover_idx': 13, 'eligible_entry_idx': 14}
    assert m.semantic_order_valid(8, 5, 10, result)
    assert not m.semantic_order_valid(10, 5, 10, result)
    assert not m.semantic_order_valid(8, 5, 10, {**result, 'reclaim_idx': 11})


if __name__ == '__main__':
    tests = [value for name, value in sorted(globals().items()) if name.startswith('test_')]
    for test in tests:
        test()
    print(f'PASS: {len(tests)} V437 Target-First DOL contract tests')
