#!/usr/bin/env python3
"""Focused regression tests for V526 exact-next-session admission."""
import sys

sys.path.insert(0, '/root/.hermes/scripts/v25')
import v526_v517_live_execution as live


def test_weekday_lower_bound_sequence():
    assert live.weekday_dates('20260731', '20260804') == ['20260731', '20260803']


def test_later_open_allowed_only_after_proven_holiday_days():
    row = {
        'execution_attempts': [
            {'date': '20260731', 'state': 'NO_EXCHANGE_SESSION'},
            {'date': '20260803', 'state': 'NO_EXCHANGE_SESSION'},
        ]
    }
    assert live.only_confirmed_non_sessions_before(row, '20260731', '20260804') is True


def test_later_open_rejected_after_stale_symbol_on_open_day():
    row = {'execution_attempts': [{'date': '20260731', 'state': 'NO_FRESH_SYMBOL_QUOTE'}]}
    assert live.only_confirmed_non_sessions_before(row, '20260731', '20260803') is False


def test_exchange_suffix_controls_quote_prefix():
    # The Shanghai composite must use sh000001, not the Shenzhen stock prefix.
    assert live.quote_prefix('000001.SH') == 'sh'
    assert live.quote_prefix('000001.SZ') == 'sz'
    assert live.quote_prefix('920992.BJ') == 'bj'


if __name__ == '__main__':
    test_weekday_lower_bound_sequence()
    test_later_open_allowed_only_after_proven_holiday_days()
    test_later_open_rejected_after_stale_symbol_on_open_day()
    test_exchange_suffix_controls_quote_prefix()
    print('PASS V526 calendar/session exact-next-open gate')
