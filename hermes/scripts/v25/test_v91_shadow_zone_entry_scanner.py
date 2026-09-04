#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

OUT = Path('/root/.hermes/smc_opt_v91_shadow_zone_entry_scanner')


def load(name):
    p = OUT / name
    assert p.exists(), f'missing {p}'
    return json.loads(p.read_text())


def test_v91_active_picks_have_frontend_contract_fields():
    rows = load('v91_active_picks.json')
    assert rows, 'v91 active picks empty'
    required = ['engine','pick_date','join_date','pickDate','joinDate','selectDate','选股日期','加入日期','zone','zone_type','cost_line','volatility','volatility_pct','entry_price','sl','tp1','tp2','tp3','rr','v91_gate_reason','v91_target_semantics']
    for k in required:
        missing = [r.get('symbol') for r in rows if r.get(k) in (None, '', 0)]
        assert not missing, f'{k} missing: {missing[:10]}'


def test_v91_report_matches_outputs_and_zero_missing():
    report = load('v91_shadow_scan_report.json')
    active = load('v91_active_picks.json')
    all_rows = load('v91_all_contract_candidates.json')
    assert report['recent_active_candidates'] == len(active)
    assert report['all_contract_candidates'] == len(all_rows)
    assert all(v == 0 for v in report['field_audit_recent'].values()), report['field_audit_recent']
    assert all(v == 0 for v in report['field_audit_all'].values()), report['field_audit_all']
    assert report['t1_entry_guard_violations_recent'] == 0


def test_v91_no_future_target_and_t1_guard():
    rows = load('v91_active_picks.json')
    for r in rows:
        assert str(r.get('pick_date')) != str(r.get('join_date')), r.get('symbol')
        idx = int(r.get('entry_idx') or 0)
        bsl_idx = int(r.get('known_bsl_idx') or -1)
        if bsl_idx >= 0:
            assert bsl_idx < idx, (r.get('symbol'), bsl_idx, idx)
        assert 'PRE_ENTRY' not in str(r.get('liquidity_target_original_future_v86'))


def test_v91_gate_scope_is_shadow_not_v88_baseline():
    rows = load('v91_active_picks.json')
    assert all(r.get('engine') == 'V91_SHADOW_ZONE_ENTRY_SCANNER' for r in rows)
    assert all(r.get('contract_source') == 'V91_SHADOW_DAILY_ZONE_MID_LOW_LIMIT_ENTRY' for r in rows)
    assert {r.get('pick_scope') for r in rows} == {'ACTIVE_CANDIDATE'}


def test_v91_active_picks_recovery_only_v93_secondary_gate_after_v93_audit():
    rows = load('v91_active_picks.json')
    recovery = [r for r in rows if r.get('market_state') == 'RECOVERY']
    for r in recovery:
        assert r.get('v93_recovery_gate_label') == 'RECOVERY_BULL_FAST_DEEP_RISK', r.get('symbol')
        assert r.get('v93_recovery_pass') is True, r.get('symbol')
        assert r.get('daily_state') == 'BULL_CONTINUATION', r.get('symbol')
        assert float(r.get('hold_bars') or 999) <= 1, r.get('symbol')
        assert float(r.get('risk_pct_signal') or 0) > 5, r.get('symbol')


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            print(name, 'PASS')
