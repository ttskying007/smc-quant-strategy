#!/usr/bin/env python3
"""Regression tests for live execution price semantics after daily stock selection."""
import json
import pathlib
import tempfile
import importlib.util

MOD_PATH = pathlib.Path('/root/.hermes/scripts/smc_monitor_state.py')


def load_module(tmpdir):
    spec = importlib.util.spec_from_file_location('smc_monitor_state_test', MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    root = pathlib.Path(tmpdir)
    mod.MON_DIR = root
    mod.STATE = root / 'positions.json'
    mod.DAILY_DIR = root / 'daily'
    mod.REVIEW = root / 'closed_reviews.json'
    mod.LEDGER = root / 'trade_ledger.json'
    mod.save_json(mod.STATE, [])
    return mod


def pick(**overrides):
    row = {
        'symbol': '000001.SZ',
        'engine': 'V91_SHADOW_ZONE_ENTRY_SCANNER',
        'contract_source': 'V91_SHADOW_DAILY_ZONE_MID_LOW_LIMIT_ENTRY',
        'pick_scope': 'ACTIVE_CANDIDATE',
        'is_active_pick': True,
        'live_guard_status': 'BUY_VALID',
        'trade_action': 'BUY',
        'buy_enabled': True,
        'tradable': True,
        'pick_date': '20260612',
        'join_date': '20260613',
        'price': 10.0,
        'entry_price': 10.0,
        'sl': 9.8,
        'tp1': 10.3,
        'risk_pct': 2.0,
        'zone_type': 'DEMAND_OB',
        'conf_type': 'HOLD_ABOVE_POI',
        'zone_low': 9.8,
        'zone_high': 10.2,
        'zone_idx': 1,
        'conf_index': 2,
    }
    row.update(overrides)
    return row


def test_stale_historical_pick_never_opens_at_contract_price():
    with tempfile.TemporaryDirectory() as td:
        m = load_module(td)
        m.ymd = lambda: '20260618'
        m.market_entry_allowed = lambda ts=None: True
        m.live_execution_price = lambda symbol: (12.5, 'tencent_last')
        out = m.ingest_daily_picks([pick(pick_date='20260520', join_date='20260521')])
        rows = m.load_positions()
        assert out['buy_added'] == 0
        assert rows[0]['status'] == 'WATCH_ONLY'
        assert 'STALE_PICK' in rows[0].get('reject_reason', '')
        assert rows[0]['entry_price'] != 10.0 or rows[0]['status'] != 'OPEN'


def test_trading_time_fill_uses_live_price_even_for_contract_scanner_pick():
    with tempfile.TemporaryDirectory() as td:
        m = load_module(td)
        m.ymd = lambda: '20260618'
        m.market_entry_allowed = lambda ts=None: True
        m.live_execution_price = lambda symbol: (10.15, 'tencent_last')
        out = m.ingest_daily_picks([pick(pick_date='20260617', join_date='20260618')])
        rows = m.load_positions()
        assert out['buy_added'] == 1
        assert rows[0]['status'] == 'OPEN'
        assert rows[0]['entry_price'] == 10.15
        assert rows[0]['execution_price_source'] == 'tencent_last'
        assert rows[0]['entry_zone_relation'] == 'INSIDE_ZONE'


def test_active_flag_without_buy_valid_never_creates_position():
    with tempfile.TemporaryDirectory() as td:
        m = load_module(td)
        m.ymd = lambda: '20260618'
        m.market_entry_allowed = lambda ts=None: True
        m.live_execution_price = lambda symbol: (10.15, 'tencent_last')
        unauthorized = pick(live_guard_status='WATCH_ONLY_PRICE_NOT_NEAR_ENTRY',
                            trade_action='WATCH_ONLY', buy_enabled=False, tradable=False)
        out = m.ingest_daily_picks([unauthorized])
        assert out['buy_added'] == 0
        assert out['pending_count'] == 0
        assert out['unauthorized_count'] == 1
        assert m.load_positions() == []


def test_non_trading_time_auto_pick_waits_next_day_not_open_contract_price():
    with tempfile.TemporaryDirectory() as td:
        m = load_module(td)
        m.market_entry_allowed = lambda ts=None: False
        m.live_execution_price = lambda symbol: (10.15, 'tencent_last')
        out = m.ingest_daily_picks([pick(pick_date=m.ymd())])
        rows = m.load_positions()
        assert out['buy_added'] == 0
        assert rows[0]['status'] == 'NEXT_DAY_PENDING'
        assert rows[0]['execution_price_source'] == 'planned_entry_price'
        assert rows[0]['entry_price'] == 10.0
        assert rows[0]['filled_at'] == ''
        assert rows[0]['pending_reason'] == 'WAIT_NEXT_TRADING_DAY_ENTRY'


def test_same_day_auto_pick_waits_next_day_even_during_trading_time():
    with tempfile.TemporaryDirectory() as td:
        m = load_module(td)
        m.market_entry_allowed = lambda ts=None: True
        m.live_execution_price = lambda symbol: (10.15, 'tencent_last')
        out = m.ingest_daily_picks([pick(pick_date=m.ymd())])
        rows = m.load_positions()
        assert out['buy_added'] == 0
        assert rows[0]['status'] == 'NEXT_DAY_PENDING'
        assert rows[0]['execution_price_source'] == 'planned_entry_price'
        assert rows[0]['entry_price'] == 10.0
        assert rows[0]['filled_at'] == ''
        assert rows[0]['pending_reason'] == 'WAIT_NEXT_TRADING_DAY_ENTRY'


def test_next_day_pending_fill_uses_live_price_and_sets_buy_date():
    with tempfile.TemporaryDirectory() as td:
        m = load_module(td)
        today = '20260617'
        m.ymd = lambda: today
        m.market_entry_allowed = lambda ts=None: False
        m.live_execution_price = lambda symbol: (10.15, 'tencent_last')
        m.ingest_daily_picks([pick(pick_date=today)])
        rows = m.load_positions()
        assert rows[0]['status'] == 'NEXT_DAY_PENDING'
        m.market_entry_allowed = lambda ts=None: True
        m.ymd = lambda: '20260618'
        m.now_iso = lambda: '2026-06-18T09:31:00'
        out = m.fill_pending_orders()
        rows = m.load_positions()
        assert out['filled'] == ['000001.SZ']
        assert rows[0]['status'] == 'OPEN'
        assert rows[0]['entry_price'] == 10.15
        assert rows[0]['execution_price_source'] == 'tencent_last'
        assert rows[0]['filled_at'] == '2026-06-18T09:31:00'
        assert m.date_key(rows[0]['filled_at']) > today


if __name__ == '__main__':
    for fn in [
        test_stale_historical_pick_never_opens_at_contract_price,
        test_trading_time_fill_uses_live_price_even_for_contract_scanner_pick,
        test_active_flag_without_buy_valid_never_creates_position,
        test_non_trading_time_auto_pick_waits_next_day_not_open_contract_price,
        test_same_day_auto_pick_waits_next_day_even_during_trading_time,
        test_next_day_pending_fill_uses_live_price_and_sets_buy_date,
    ]:
        fn()
    print('6/6 monitor execution contract tests PASS')
