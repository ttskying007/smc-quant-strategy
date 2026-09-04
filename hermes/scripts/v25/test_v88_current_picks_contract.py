#!/usr/bin/env python3
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('smc_unified_under_test', '/root/.hermes/scripts/smc_unified.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_latest_batch_filter():
    rows = [
        {'symbol':'A', 'pick_date':'20260410', 'engine':'V91', 'entry_idx':1},
        {'symbol':'B', 'pick_date':'20260528', 'engine':'V91', 'entry_idx':2},
        {'symbol':'C', 'pick_date':'20260605', 'engine':'V90', 'entry_idx':3},
        {'symbol':'D', 'entry_date':'20260611', 'engine':'V91', 'entry_idx':4},
    ]
    out = mod._latest_v88_scanner_rows(rows)
    assert {r['symbol'] for r in out} == {'C', 'D'}


def test_v88_active_picks_are_current_month_scanner_candidates_not_backtest_reps():
    mod._PICKS_CACHE = None
    mod._CACHE_MTIME = 0
    picks = mod.get_active_picks(version='V88')
    assert all(p.get('engine') != 'V88_PRODUCTION_CONTRACT' for p in picks), picks[:3]
    latest_market = mod._v88_latest_market_date()
    latest_month = latest_market[:6]
    assert latest_market == '20260612', latest_market
    assert picks, 'June scanner candidates should be visible after BEAR_RISK reversal promotion'
    assert all(latest_month in {
        mod._date_key(p.get('pick_date') or p.get('select_date'))[:6],
        mod._date_key(p.get('join_date') or p.get('entry_date'))[:6],
    } for p in picks), picks[:3]


if __name__ == '__main__':
    test_latest_batch_filter()
    test_v88_active_picks_are_current_month_scanner_candidates_not_backtest_reps()
    print('PASS V88 current picks contract: current-month scanner candidates; stale historical rows suppressed')
