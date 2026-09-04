#!/usr/bin/env python3
import sys
sys.path.insert(0, '/root/.hermes/scripts/v25')

import v32b_engine as v32b


def k(o,h,l,c,t='20260101'):
    return {'t': t, 'o': o, 'h': h, 'l': l, 'c': c}


def test_next_retrace_rejects_zone_invalidated_before_touch():
    kl = [k(10,10.2,9.9,10), k(10,10.1,9.6,9.70), k(9.8,10.1,9.9,10.0)]
    assert v32b.next_retrace_strict(kl, 0, 9.80, 10.00, lookahead=3) is None


def test_next_retrace_requires_actual_zone_touch():
    kl = [k(10,10.2,10.05,10.1), k(10.2,10.5,10.05,10.4), k(10.3,10.4,9.95,10.2)]
    assert v32b.next_retrace_strict(kl, 0, 9.80, 10.00, lookahead=4) == 2


def test_confirm_at_zone_requires_rejection_at_zone_not_above_zone():
    above = [k(10.3,10.5,10.2,10.45)]
    valid = [k(9.95,10.15,9.80,10.12)]
    assert v32b.confirm_at_zone_strict(above, 0, 9.80, 10.00) == (None, None)
    assert v32b.confirm_at_zone_strict(valid, 0, 9.80, 10.00) == (0, 'BULLISH_REJECTION')


def test_make_entry_rejects_open_gap_above_zone_without_retouch():
    kl = [k(10,10.1,9.9,10.0), k(10.5,10.7,10.4,10.6)]
    zone = {'zone_low': 9.80, 'zone_high': 10.00, 'index': 0, 'date': '20260101'}
    assert v32b.entry_from_next_open(kl, 0, zone, max_gap_pct=0.01) is None


def test_backtest_gap_through_stop_exits_at_open_not_stop_price():
    setup = {'entry_index': 0, 'entry_price': 10.0, 'sl': 9.5, 'tp1': 11.0, 'tp2': 12.0, 'tp3': 13.0, 'risk': 0.5}
    kl = [k(10,10.1,9.9,10.0), k(9.2,9.4,9.1,9.3)]
    tr = v32b.backtest_v32b_setups([setup], kl, max_hold_bars=5, min_hold_bars=1)[0]
    assert tr['exit_reason'] == 'GAP_SL_HIT'
    assert tr['exit_price'] == 9.2
    assert tr['pnl_pct'] == -8.0


def test_dedupe_keeps_best_quality_per_entry_zone_symbol():
    setups = [
        {'symbol': 'AAA', 'entry_index': 10, 'zone_idx': 5, 'quality_score': 5, 'rr': 2},
        {'symbol': 'AAA', 'entry_index': 10, 'zone_idx': 5, 'quality_score': 7, 'rr': 1.5},
        {'symbol': 'AAA', 'entry_index': 11, 'zone_idx': 5, 'quality_score': 4, 'rr': 3},
    ]
    out = v32b.dedupe_setups(setups)
    assert len(out) == 2
    assert out[0]['quality_score'] == 7


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print('PASS', name)
