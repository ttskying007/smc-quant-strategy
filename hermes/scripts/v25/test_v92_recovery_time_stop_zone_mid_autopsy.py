#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

OUT = Path('/root/.hermes/smc_opt_v92_recovery_time_stop_zone_mid_autopsy')
REPORT = OUT / 'v92_autopsy_report.json'


def report():
    assert REPORT.exists(), f'missing {REPORT}'
    return json.loads(REPORT.read_text())


def test_scope_is_full_market_chain_not_top10_sample():
    r = report()['scope']
    assert r['kline_symbols_daily_750'] >= 4500
    assert r['v85_generator_candidates'] >= 20000
    assert r['v85_generator_symbols'] >= 4500
    assert r['v91_matrix_rows'] >= 180000
    assert r['v91_matrix_symbols'] == r['v85_generator_symbols']


def test_zone_mid_entry_materially_reduces_one_bar_sl_vs_orig_chase_entry():
    r = report()['one_bar_exit']
    assert r['orig_v85_micro']['sl_rate'] >= 20
    assert r['zone_mid_micro']['sl_rate'] <= 12
    assert r['zone_mid_micro']['sl_rate'] < r['orig_v85_micro']['sl_rate'] - 8


def test_recovery_loss_bucket_remains_unfit_for_blind_production():
    r = report()['recovery_loss_bucket']
    assert r['recovery_zone_mid']['wr'] < 88
    assert r['recovery_zone_mid']['sl_rate'] > 14
    assert r['losses']['n'] >= 900
    assert r['loss_exit_reason']['SL_HIT'] / r['losses']['n'] > 0.98


def test_time_stop_high_mfe_is_capture_issue_not_signal_failure():
    r = report()['time_stop_high_mfe']
    assert r['v88_high_mfe_ge_3']['n'] >= 30
    assert r['v88_high_mfe_ge_3']['wr'] == 100.0
    assert r['zone_mid_high_mfe_ge_3']['n'] >= 500
    assert r['zone_mid_high_mfe_ge_3']['wr'] == 100.0


def test_zone_mid_not_promoted_to_baseline_but_risk_layer_passes_shadow_threshold():
    p = report()['production_candidate_readout']
    assert p['zone_mid_pass_gate']['decision'] == 'SHADOW_ONLY_NOT_FULL_PRODUCTION'
    assert p['zone_mid_pass_gate']['by_year']['2026']['wr'] < 88
    assert p['zone_mid_risk_gate']['metric']['n'] >= 5000
    assert p['zone_mid_risk_gate']['metric']['wr'] >= 90
    assert p['zone_mid_risk_gate']['metric']['sl_rate'] <= 10


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            print(name, 'PASS')
