#!/usr/bin/env python3
"""Contract tests for the independent V438 Target-First DOL oracle."""
from __future__ import annotations
import importlib.util
from pathlib import Path

MODULE = Path(__file__).with_name('v438_target_first_dol_independent_oracle.py')


def load_module():
    spec = importlib.util.spec_from_file_location('v438', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bar(o, h, l, c, t='20260101'):
    return {'o': float(o), 'h': float(h), 'l': float(l), 'c': float(c), 't': t}


def test_target_selection_is_visible_nearest_and_unconsumed():
    m = load_module()
    bars = [bar(99, 100, 98, 99) for _ in range(10)]
    highs = [
        {'idx': 1, 'price': 110.0, 'confirm_idx': 4},
        {'idx': 2, 'price': 105.0, 'confirm_idx': 5},
        {'idx': 3, 'price': 103.0, 'confirm_idx': 7},
    ]
    assert m.choose_dol(bars, highs, 7)['price'] == 105.0
    bars[6]['h'] = 105.0
    assert m.choose_dol(bars, highs, 7)['price'] == 110.0


def test_lifecycle_requires_strictly_ordered_touch_reclaim_hold_and_entry():
    m = load_module()
    bars = [
        bar(100, 101, 99, 100),
        bar(101, 104, 100, 103),
        bar(103, 104, 101, 102),
        bar(102, 106, 102, 105),
        bar(105, 107, 103, 106),
        bar(106, 108, 105, 107),
    ]
    assert m.lifecycle(bars, 1, 100, 104, 110) == (2, 3, 4, 5)


def test_lifecycle_cancels_if_dol_or_poi_is_consumed():
    m = load_module()
    dol_hit = [bar(100, 101, 99, 100), bar(101, 104, 100, 103), bar(103, 110, 101, 109)]
    poi_dead = [bar(100, 101, 99, 100), bar(101, 104, 100, 103), bar(102, 103, 98, 99)]
    assert m.lifecycle(dol_hit, 1, 100, 104, 110) is None
    assert m.lifecycle(poi_dead, 1, 100, 104, 110) is None


def test_oracle_does_not_import_generator_or_v27():
    text = MODULE.read_text()
    assert 'v437_target_first_dol_generator' not in text
    assert 'smc_core_v27' not in text


if __name__ == '__main__':
    tests = [value for name, value in sorted(globals().items()) if name.startswith('test_')]
    for test in tests:
        test()
    print(f'PASS: {len(tests)} V438 independent-oracle contract tests')
