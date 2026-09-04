#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path('/root/.hermes/scripts/v25/v89_recovery_known_target_repair.py')
spec = importlib.util.spec_from_file_location('v89', SCRIPT)
v89 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v89)  # type: ignore[union-attr]


def test_v89_uses_fixed_known_rr_target_not_liquidity_target():
    assert v89.TP_MODE == 'micro_0_8_1_5_3'
    base = {'symbol': '000001.SZ', 'entry_price': 10, 'zone_low': 9, 'zone_high': 11, 'entry_date': '20250102'}
    row = v89.apply_contract(base, {'entry_price': 10, 'sl': 9, 'tp1': 10.8, 'tp2': 11.5, 'tp3': 13, 'rr': 1.5}, 'TEST', 'production_like_daily_only')
    assert row['v89_target_semantics'].startswith('ENTRY_KNOWN_FIXED_RR')
    assert row['tp_mode'] == 'micro_0_8_1_5_3'
    assert 'liquidity' not in row['planned_exit_signal'].lower()


def test_recovery_filter_removes_weak_recovery_and_accumulation():
    filt = dict((name, fn) for name, _gate, fn in v89.FILTERS)['V89_A_DAILY_NO_RECOVERY_ACCUM']
    assert not filt({'market_state': 'RECOVERY'})
    assert not filt({'market_state': 'ACCUMULATION'})
    assert filt({'market_state': 'MIXED'})
    assert filt({'market_state': 'BULL_CONTINUATION'})


def test_research_filters_are_marked_partial_60min():
    gate_by_name = {name: gate for name, gate, _fn in v89.FILTERS}
    assert gate_by_name['V89_B_RECOVERY_REQUIRE_M60_BULL_OR_MIXED'] == 'research_uses_partial_60min'
    assert gate_by_name['V89_C_RECOVERY_REQUIRE_MTF3'] == 'research_uses_partial_60min'
    assert gate_by_name['V89_D_RECOVERY_REQUIRE_MTF2'] == 'research_uses_partial_60min'


def test_metrics_release_requirements_are_computable():
    rows = [
        {'pnl_pct': 1, 'rr': 1.5, 'exit_reason': 'TP_HIT', 'mfe_r': 2, 'mae_r': -0.5},
        {'pnl_pct': -1, 'rr': 1.5, 'exit_reason': 'SL_HIT', 'mfe_r': 0, 'mae_r': -1},
    ]
    m = v89.metrics(rows)
    assert m['n'] == 2
    assert m['wr'] == 50.0
    assert m['avg_rr'] == 1.5
    assert m['low_rr_rate'] == 0.0
    assert m['sl_rate'] == 50.0
