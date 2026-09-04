#!/usr/bin/env python3
"""Frontend live guard must not manufacture BUY_VALID while registry blocks buys."""
from __future__ import annotations
import importlib.util
import json
import pathlib
import tempfile

MOD = pathlib.Path('/root/.hermes/scripts/smc_unified.py')


def load_module():
    spec = importlib.util.spec_from_file_location('smc_unified_registry_guard_test', MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_empty_book_uses_latest_committed_cache_epoch():
    mod = load_module()
    with tempfile.TemporaryDirectory() as td:
        epoch = pathlib.Path(td) / 'kline_epoch_current.json'
        epoch.write_text(json.dumps({'status': 'COMMITTED', 'epoch_id': 'epoch-new', 'market_date': '20260722'}))
        mod.KLINE_EPOCH_CURRENT_FILE = epoch
        assert mod._current_committed_data_epoch({'epoch_id': 'epoch-old'}) == {
            'valid': True, 'epoch_id': 'epoch-new', 'market_date': '20260722', 'status': 'COMMITTED'
        }


def test_fail_closed_registry_uses_committed_epoch_not_stale_scanner_metadata():
    mod = load_module()
    with tempfile.TemporaryDirectory() as td:
        registry = pathlib.Path(td) / 'production_registry.json'
        epoch = pathlib.Path(td) / 'kline_epoch_current.json'
        registry.write_text(json.dumps({
            'state': 'FAIL_CLOSED_REPLAY_GATE_FAILED',
            'production_strategy': None,
            'buy_enabled': False,
            'data_epoch': {'epoch_id': 'registry-old', 'market_date': '20260716'},
        }))
        epoch.write_text(json.dumps({
            'status': 'COMMITTED', 'epoch_id': 'epoch-new', 'market_date': '20260728',
        }))
        mod.PRODUCTION_REGISTRY_FILE = registry
        mod.KLINE_EPOCH_CURRENT_FILE = epoch
        stale_ops = {'data_date': '20260716', 'generated_at': '2026-07-17T09:08:07'}
        meta = mod._ops_scan_meta(stale_ops)
        assert meta['data_date'] == '20260728'
        assert meta['latest_scan_date'] == ''
        assert meta['last_scan_at'] == ''
        assert meta['scanner_state'] == 'NOT_RUN_EMPTY_BOOK'


def test_empty_book_converts_active_candidate_to_watch_only():
    mod = load_module()
    with tempfile.TemporaryDirectory() as td:
        registry = pathlib.Path(td) / 'production_registry.json'
        registry.write_text(json.dumps({
            'state': 'EMPTY_BOOK',
            'production_strategy': None,
            'buy_enabled': False,
            'active_buy_valid_count': 0,
            'forbidden_fallback': True,
        }))
        mod.PRODUCTION_REGISTRY_FILE = registry
        mod._last_cached_daily_price = lambda symbol: {'price': 10.0, 'date': '20260714'}
        rows = mod._apply_current_price_live_guard([{
            'symbol': '000001.SZ',
            'pick_scope': 'ACTIVE_CANDIDATE',
            'is_active_pick': True,
            'entry_price': 10.0,
            'sl': 9.0,
            'tp1': 11.0,
        }])
        assert len(rows) == 1
        row = rows[0]
        assert row['tradable'] is False
        assert row['buy_enabled'] is False
        assert row['trade_action'] == 'WATCH_ONLY'
        assert row['live_guard_status'] == 'WATCH_ONLY_PRODUCTION_REGISTRY_BLOCKED'
        assert row['live_guard_reason'] == 'PRODUCTION_REGISTRY_BUY_DISABLED'


if __name__ == '__main__':
    test_empty_book_uses_latest_committed_cache_epoch()
    test_fail_closed_registry_uses_committed_epoch_not_stale_scanner_metadata()
    test_empty_book_converts_active_candidate_to_watch_only()
    print('PASS: frontend registry live guard')
