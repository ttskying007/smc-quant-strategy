#!/usr/bin/env python3
import datetime as dt
import importlib.util
import json
import pathlib
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


def load(name):
    path = pathlib.Path(__file__).with_name(name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sina_parser_contract():
    mod = load('refresh_daily_750')
    raw = json.dumps([{'day':'2026-07-13','open':'1','close':'2','high':'3','low':'0.5','volume':'9'}])
    assert mod.parse_sina(raw) == [{'t':'20260713','o':1.0,'c':2.0,'h':3.0,'l':0.5,'v':9.0}]


def test_ops_refresh_gate_is_fail_closed():
    mod = load('smc_daily_ops')
    original = mod.MON
    with tempfile.TemporaryDirectory() as td:
        mod.MON = pathlib.Path(td)
        manifest = {'status': 'COMMITTED', 'epoch_id': 'e1', 'market_date': '20260713'}
        (mod.MON / 'kline_epoch_current.json').write_text(json.dumps(manifest))
        assert not mod.refresh_is_usable({'returncode': 0, 'summary': {'gate_pass': False}})
        assert not mod.refresh_is_usable({'returncode': 2, 'summary': {'gate_pass': True}})
        assert not mod.refresh_is_usable({'returncode': 0, 'summary': {
            'gate_pass': True, 'epoch_status': 'PREPARING', 'epoch_id': 'e1'}})
        good = {'returncode': 0, 'summary': {'gate_pass': True, 'epoch_status': 'COMMITTED',
                                            'epoch_id': 'e1', 'observed_latest_date': '20260713'}}
        assert mod.refresh_is_usable(good)
        good['summary']['epoch_id'] = 'other'
        assert not mod.refresh_is_usable(good)
    mod.MON = original


def test_ops_ingests_only_complete_buy_valid_rows():
    mod = load('smc_daily_ops')
    original_mon = mod.automatic_buy_authorized.__globals__['MON_DIR']
    with tempfile.TemporaryDirectory() as td:
        mon = pathlib.Path(td)
        mod.automatic_buy_authorized.__globals__['MON_DIR'] = mon
        (mon / 'production_registry.json').write_text(json.dumps({
            'state': 'ACTIVE', 'production_strategy': 'TEST_CAUSAL_STRATEGY',
            'buy_enabled': True,
            'data_epoch': {'valid': True, 'status': 'COMMITTED',
                           'epoch_id': 'epoch-test', 'market_date': '20260713'},
        }))
        base = {'is_active_pick': True, 'pick_scope': 'ACTIVE_CANDIDATE'}
        valid = {
            **base, 'live_guard_status': 'BUY_VALID', 'trade_action': 'BUY',
            'buy_enabled': True, 'tradable': True,
            'production_strategy': 'TEST_CAUSAL_STRATEGY',
            'data_epoch_id': 'epoch-test', 'pick_date': '20260713',
            'current_raw_scanner_source': True, 'semantic_oracle_pass': True,
            'chronology_pass': True, 'strict_t1_contract': True,
        }
        assert mod.buy_valid_rows([base, valid]) == [valid]
    mod.automatic_buy_authorized.__globals__['MON_DIR'] = original_mon


def test_intraday_partial_daily_bar_is_excluded():
    mod = load('refresh_daily_750')
    morning = dt.datetime(2026, 7, 14, 9, 30, tzinfo=mod.ZoneInfo('Asia/Shanghai'))
    assert mod.completed_market_cutoff(morning) == '20260713'
    rows = [{'t':'20260713'}, {'t':'20260714'}]
    assert mod.keep_completed_rows(rows, '20260713') == [{'t':'20260713'}]


def test_failed_refresh_uses_only_committed_manifest_date():
    mod = load('smc_daily_ops')
    original = mod.MON
    with tempfile.TemporaryDirectory() as td:
        mod.MON = pathlib.Path(td)
        failed = {'returncode': 2, 'summary': {'gate_pass': False,
                                              'latest_counts': {'20260714': 4640},
                                              'before_latest_counts': {'20260713': 4640}}}
        assert mod.latest_market_date(failed) == ''
        (mod.MON / 'kline_epoch_current.json').write_text(json.dumps({
            'status': 'COMMITTED', 'epoch_id': 'e1', 'market_date': '20260713'}))
        assert mod.latest_market_date(failed) == '20260713'
    mod.MON = original


def test_refresh_gate_rejects_stale_or_fragmented_latest_market_date():
    mod = load('refresh_daily_750')
    now = dt.datetime(2026, 7, 14, 16, 0, tzinfo=mod.ZoneInfo('Asia/Shanghai'))
    stale = mod.evaluate_refresh_gate(4905, 4903, {'20260701': 4903}, {'20260701': 4903}, now)
    fragmented = mod.evaluate_refresh_gate(4905, 4903, {'20260713': 4800, '20260701': 103}, {'20260713': 4888}, now)
    healthy = mod.evaluate_refresh_gate(4905, 4903, {'20260713': 4888, '20260706': 15}, {'20260713': 4888}, now)
    assert not stale['gate_pass']
    assert 'LATEST_DATE_STALE' in stale['gate_failures']
    assert not fragmented['gate_pass']
    assert 'CURRENT_DATE_COVERAGE_BELOW_MIN' in fragmented['gate_failures']
    assert healthy['gate_pass']
    assert healthy['current_date_coverage_pct'] == 99.65


def test_epoch_promotion_and_interrupted_rollback():
    mod = load('refresh_daily_750')
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        mod.KLINE_DIR = root / 'cache'
        mod.MONITOR_DIR = root / 'monitor'
        mod.EPOCH_DIR = mod.MONITOR_DIR / 'epochs'
        mod.CURRENT_MANIFEST = mod.MONITOR_DIR / 'current.json'
        mod.KLINE_DIR.mkdir(parents=True)
        stage = mod.EPOCH_DIR / 'e1'; stage.mkdir(parents=True)
        target = mod.KLINE_DIR / '000001_SZ_daily_750.json'
        target.write_text('[{"t":"20260710"}]')
        staged = stage / target.name
        staged.write_text('[{"t":"20260713"}]')
        gate = {'gate_pass': True, 'observed_latest_date': '20260713'}
        manifest = mod.promote_epoch('e1', stage, [
            {'target_path': str(target), 'staged_path': str(staged)}], gate)
        assert manifest['status'] == 'COMMITTED'
        assert json.loads(target.read_text())[-1]['t'] == '20260713'
        assert json.loads(mod.CURRENT_MANIFEST.read_text())['epoch_id'] == 'e1'

        interrupted = mod.EPOCH_DIR / 'e2'; backup = interrupted / 'backup'
        backup.mkdir(parents=True)
        (backup / target.name).write_text('[{"t":"20260713"}]')
        target.write_text('[{"t":"20990101"}]')
        journal = {'epoch_id': 'e2', 'state': 'PREPARING',
                   'targets': [{'target': str(target), 'existed': True}]}
        (interrupted / 'promotion_journal.json').write_text(json.dumps(journal))
        assert mod.recover_incomplete_promotions() == ['e2']
        assert json.loads(target.read_text())[-1]['t'] == '20260713'


def test_partial_tencent_updates_only_latest_bar():
    mod = load('refresh_daily_750')
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / '920010_BJ_daily_750.json'
        old = [
            {'t':'20260720','o':8.0,'c':8.1,'h':8.2,'l':7.9,'v':100},
            {'t':'20260721','o':8.1,'c':8.2,'h':8.3,'l':8.0,'v':100},
            {'t':'20260722','o':8.2,'c':8.3,'h':8.4,'l':8.1,'v':100},
        ]
        path.write_text(json.dumps(old))
        latest = [{'t':'20260722','o':8.2,'c':8.1,'h':8.4,'l':8.0,'v':101}]
        assert mod.aligned_with_existing(path, latest, allow_latest_update=True)
        merged = mod.merge_new_rows(path, latest, replace_latest=True)
        assert len(merged) == 3 and merged[-1] == latest[0]
        historical_mismatch = [{'t':'20260721','o':9.0,'c':9.0,'h':9.1,'l':8.9,'v':100}]
        assert not mod.aligned_with_existing(path, historical_mismatch, allow_latest_update=True)


def test_open_market_witness_preserves_existing_bj_cache_in_stage():
    mod = load('refresh_daily_750')
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        cache = root / 'cache'
        stage = root / 'stage'
        cache.mkdir(); stage.mkdir()
        mod.KLINE_DIR = cache
        path = mod.out_path('920010', 'bj')
        existing = [
            {'t': f'2025{month:02d}{day:02d}', 'o': 8.0, 'c': 8.1, 'h': 8.2, 'l': 7.9, 'v': 100}
            for month in range(1, 11) for day in range(1, 13)
        ]
        path.write_text(json.dumps(existing))
        today = dt.datetime.now(mod.ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d')
        raw = json.dumps({
            'data': {
                'market': ['x_open_交易中'],
                'bj920010': {'qfqday': [[today, '8.1', '8.2', '8.3', '8.0', '1']]},
            }
        }, ensure_ascii=False)
        with patch.object(mod.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=raw)):
            result = mod.fetch_one(('920010', 'bj'), stage_dir=stage)
        staged = pathlib.Path(result['staged_path'])
        assert result['ok'] is True
        assert result['source'] == 'tencent_open_preserve_existing'
        assert staged.exists()
        assert json.loads(staged.read_text()) == existing
        assert json.loads(path.read_text()) == existing


def test_short_listing_history_is_explicitly_bounded():
    mod = load('refresh_daily_750')
    now = dt.datetime(2026, 7, 22, tzinfo=mod.ZoneInfo('Asia/Shanghai')).date()
    rows = [{'t': f'202606{day:02d}'} for day in range(1, 31)]
    assert mod.valid_short_listing_history(rows, now=now)
    assert not mod.valid_short_listing_history(rows[:1], now=now)
    stale = [{'t': f'202401{day:02d}'} for day in range(1, 31)]
    assert not mod.valid_short_listing_history(stale, now=now)


def test_v365_shadow_stays_no_write_and_runs_independently():
    mod = load('smc_daily_ops')
    result = mod.run_v365_shadow()
    summary = result['summary']
    assert result['returncode'] == 0
    assert summary['shadow_only'] is True
    assert summary['production_write'] is False
    assert summary['frontend_write'] is False
    assert summary['watchlist_write'] is False
    assert summary['buy_enabled'] is False


if __name__ == '__main__':
    test_sina_parser_contract()
    test_ops_refresh_gate_is_fail_closed()
    test_ops_ingests_only_complete_buy_valid_rows()
    test_intraday_partial_daily_bar_is_excluded()
    test_failed_refresh_uses_only_committed_manifest_date()
    test_refresh_gate_rejects_stale_or_fragmented_latest_market_date()
    test_epoch_promotion_and_interrupted_rollback()
    test_partial_tencent_updates_only_latest_bar()
    test_open_market_witness_preserves_existing_bj_cache_in_stage()
    test_short_listing_history_is_explicitly_bounded()
    test_v365_shadow_stays_no_write_and_runs_independently()
    print('PASS: transactional refresh, rollback, and fail-closed gates')
