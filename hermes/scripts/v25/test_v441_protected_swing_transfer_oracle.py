#!/usr/bin/env python3
"""Contract tests for V441 independent Protected-Swing Transfer oracle."""
from __future__ import annotations
import importlib.util
from pathlib import Path

MODULE = Path(__file__).with_name('v441_protected_swing_transfer_independent_oracle.py')


def load_module():
    spec = importlib.util.spec_from_file_location('v441', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bar(o, h, l, c):
    return {'o': float(o), 'h': float(h), 'l': float(l), 'c': float(c), 't': '20260101'}


def test_independent_transfer_contract():
    m = load_module()
    bars = [bar(100, 102, 99, 101) for _ in range(20)]
    lows = [{'idx': 2, 'price': 90.0, 'confirm_idx': 5}, {'idx': 9, 'price': 95.0, 'confirm_idx': 12}]
    old, new = m.protected_transfer(bars, lows, 7, 15)
    assert old['price'] == 90.0 and new['price'] == 95.0
    bars[10]['c'] = 89.0
    assert m.protected_transfer(bars, lows, 7, 15) is None


def test_oracle_does_not_import_generator_or_v27():
    text = MODULE.read_text()
    assert 'v440_protected_swing_transfer_generator' not in text
    assert 'smc_core_v27' not in text


if __name__ == '__main__':
    tests = [value for name, value in sorted(globals().items()) if name.startswith('test_')]
    for test in tests:
        test()
    print(f'PASS: {len(tests)} V441 independent-oracle tests')
