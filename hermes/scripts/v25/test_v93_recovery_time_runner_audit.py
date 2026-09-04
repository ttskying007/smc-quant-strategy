#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from v93_recovery_time_runner_audit import OUT, main, metric, recovery_gate_label, recovery_passes_v93, runner_variant_pnl


def ensure_report():
    p = OUT / 'v93_recovery_time_runner_report.json'
    if not p.exists():
        main()
    return json.loads(p.read_text())


def test_recovery_gate_has_non_empty_recoverable_subbucket_and_rejects_rest():
    report = ensure_report()
    passed = report['recovery']['v93_pass']
    rejected = report['recovery']['v93_reject']
    assert passed['n'] >= 200
    assert passed['wr'] >= 88
    assert passed['sl_rate'] <= 12
    assert rejected['n'] > passed['n']


def test_recovery_gate_is_structural_not_blanket_reenable():
    good = {'market_state': 'RECOVERY', 'daily_state': 'BULL_CONTINUATION', 'gate': 'RISK', 'hold_bars': 1, 'zone_width': 1.2, 'risk_signal': 6.2}
    bad = {'market_state': 'RECOVERY', 'daily_state': 'BEAR_RISK', 'gate': 'ZONE_WIDTH+RISK', 'hold_bars': 5, 'zone_width': 2.4, 'risk_signal': 4.0}
    assert recovery_passes_v93(good)
    assert recovery_gate_label(good) == 'RECOVERY_BULL_FAST_DEEP_RISK'
    assert not recovery_passes_v93(bad)
    assert recovery_gate_label(bad) == 'RECOVERY_REJECT'


def test_time_stop_runner_only_improves_high_mfe_time_stop_rows():
    row = {'exit_reason': 'TIME_STOP', 'pnl_pct': 0.2, 'mfe_r': 3.2, 'entry_price': 10.0, 'sl': 9.8}
    improved = runner_variant_pnl(row, 'delay_to_1_5r_floor')
    assert improved['pnl_pct'] >= 3.0
    assert improved['captured_extra_r'] > 0
    untouched = runner_variant_pnl({**row, 'exit_reason': 'SL_HIT'}, 'delay_to_1_5r_floor')
    assert untouched['pnl_pct'] == 0.2
    assert untouched['captured_extra_r'] == 0


def test_runner_variant_improves_full_zone_mid_average_without_increasing_sl():
    report = ensure_report()
    base = report['baseline_zone_mid_micro']
    variant = report['time_stop']['variants_all_rows']['mfe_50pct_cap_3r']
    assert variant['avg'] > base['avg']
    assert variant['sl_rate'] == base['sl_rate']
    assert variant['wr'] >= base['wr']


def test_core_risk_no_recovery_remains_production_quality_after_recovery_split():
    report = ensure_report()
    core = report['production_readout']['core_risk_no_recovery']
    assert core['n'] >= 4000
    assert core['wr'] >= 90
    assert core['sl_rate'] <= 10
    for year, m in report['production_readout']['core_risk_no_recovery_by_year'].items():
        if int(year) < 2023:
            continue
        assert m['n'] >= 50
        assert m['wr'] >= 88
        assert m['sl_rate'] <= 12


if __name__ == '__main__':
    tests = [v for k, v in globals().items() if k.startswith('test_') and callable(v)]
    for t in tests:
        t()
        print(t.__name__, 'PASS')
