#!/usr/bin/env python3
"""Fail-closed contract: active-looking rows are not buy authorization."""
from __future__ import annotations
import importlib.util
import pathlib
import tempfile

MOD = pathlib.Path('/root/.hermes/scripts/smc_monitor_state.py')


def load(tmpdir):
    spec = importlib.util.spec_from_file_location('smc_monitor_state_buy_gate_test', MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    root = pathlib.Path(tmpdir)
    mod.MON_DIR = root
    mod.STATE = root / 'positions.json'
    mod.DAILY_DIR = root / 'daily'
    mod.REVIEW = root / 'closed_reviews.json'
    mod.LEDGER = root / 'trade_ledger.json'
    mod.save_json(mod.STATE, [])
    mod.save_json(root / 'production_registry.json', {
        'state': 'ACTIVE',
        'production_strategy': 'TEST_CAUSAL_STRATEGY',
        'buy_enabled': True,
        'data_epoch': {
            'valid': True,
            'status': 'COMMITTED',
            'epoch_id': 'epoch-test',
            'market_date': '20260713',
        },
    })
    return mod


def base_pick(**changes):
    row = {
        'symbol': '000001.SZ', 'pick_scope': 'ACTIVE_CANDIDATE',
        'is_active_pick': True, 'pick_date': '20260713', 'join_date': '20260714',
        'entry_price': 10.0, 'price': 10.0, 'zone_low': 9.8, 'zone_high': 10.2,
        'sl': 9.7, 'tp1': 10.5, 'risk_pct': 3.0, 'zone_type': 'DEMAND_OB',
        'conf_type': 'HOLD_ABOVE_POI', 'zone_idx': 1, 'conf_index': 2,
        'production_strategy': 'TEST_CAUSAL_STRATEGY',
        'data_epoch_id': 'epoch-test',
        'current_raw_scanner_source': True,
        'semantic_oracle_pass': True,
        'chronology_pass': True,
        'strict_t1_contract': True,
    }
    row.update(changes)
    return row


def test_each_missing_buy_authorization_field_fails_closed():
    valid = dict(live_guard_status='BUY_VALID', trade_action='BUY', buy_enabled=True, tradable=True)
    invalid = [
        {},
        {**valid, 'live_guard_status': 'WATCH_ONLY'},
        {**valid, 'trade_action': 'WATCH_ONLY'},
        {**valid, 'buy_enabled': False},
        {**valid, 'tradable': False},
    ]
    with tempfile.TemporaryDirectory() as td:
        mod = load(td)
        mod.ymd = lambda: '20260714'
        mod.market_entry_allowed = lambda ts=None: True
        mod.live_execution_price = lambda symbol: (10.0, 'test')
        for fields in invalid:
            result = mod.ingest_daily_picks([base_pick(**fields)])
            assert result['buy_added'] == 0
            assert result['pending_count'] == 0
        assert mod.load_positions() == []


def test_complete_buy_valid_contract_can_reach_existing_t1_path():
    with tempfile.TemporaryDirectory() as td:
        mod = load(td)
        mod.ymd = lambda: '20260714'
        mod.market_entry_allowed = lambda ts=None: True
        mod.live_execution_price = lambda symbol: (10.0, 'test')
        result = mod.ingest_daily_picks([base_pick(
            live_guard_status='BUY_VALID', trade_action='BUY',
            buy_enabled=True, tradable=True,
        )])
        assert result['unauthorized_count'] == 0
        assert result['buy_added'] + result['pending_count'] == 1


def test_empty_book_registry_blocks_complete_looking_pick():
    with tempfile.TemporaryDirectory() as td:
        mod = load(td)
        mod.save_json(mod.MON_DIR / 'production_registry.json', {
            'state': 'EMPTY_BOOK',
            'production_strategy': None,
            'buy_enabled': False,
            'active_buy_valid_count': 0,
            'forbidden_fallback': True,
            'data_epoch': {
                'valid': True, 'status': 'COMMITTED',
                'epoch_id': 'epoch-test', 'market_date': '20260713',
            },
        })
        mod.ymd = lambda: '20260714'
        mod.market_entry_allowed = lambda ts=None: True
        mod.live_execution_price = lambda symbol: (10.0, 'test')
        result = mod.ingest_daily_picks([base_pick(
            live_guard_status='BUY_VALID', trade_action='BUY',
            buy_enabled=True, tradable=True,
        )])
        assert result['buy_added'] == 0
        assert result['pending_count'] == 0
        assert result['unauthorized_count'] == 1
        assert mod.load_positions() == []


if __name__ == '__main__':
    test_each_missing_buy_authorization_field_fails_closed()
    test_complete_buy_valid_contract_can_reach_existing_t1_path()
    test_empty_book_registry_blocks_complete_looking_pick()
    print('PASS: BUY_VALID fail-closed contract')