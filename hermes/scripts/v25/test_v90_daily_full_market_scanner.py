#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from v90_daily_full_market_scanner import OUT, date_key, num, field_audit


def load(name: str):
    return json.loads((OUT / name).read_text())


def test_v90_active_picks_have_frontend_contract_fields():
    rows = load('v90_active_picks.json')
    assert rows, 'V90 scanner should produce recent active picks'
    audit = field_audit(rows)
    assert all(v == 0 for v in audit.values()), audit
    aliases = ['pick_date','select_date','join_date','pickDate','selectDate','joinDate','选股日期','加入日期','zone_type','zone_low','zone_high','zone','cost_line','smart_money_cost','volatility_pct','volatility','vol_class','entry_price','sl','tp1','tp2','tp3']
    for r in rows:
        for k in aliases:
            assert r.get(k) not in (None, ''), (k, r.get('symbol'))


def test_v90_does_not_use_future_liquidity_target_as_plan():
    rows = load('v90_active_picks.json')
    assert rows
    for r in rows:
        assert r.get('v90_target_semantics') == 'PRE_ENTRY_KNOWN_BSL_OR_FIXED_RR_NO_FUTURE_LIQUIDITY_TARGET'
        assert 'liquidity_target_original_future_v86' in r
        assert num(r.get('known_bsl_target')) > 0
        assert num(r.get('liquidity_target')) == num(r.get('known_bsl_target'))
        assert int(num(r.get('known_bsl_idx'))) < int(num(r.get('entry_idx')))
        assert date_key(r.get('known_bsl_date')) <= date_key(r.get('pick_date')) or int(num(r.get('known_bsl_idx'))) < int(num(r.get('entry_idx')))


def test_v90_t1_pick_to_join_guard():
    rows = load('v90_active_picks.json')
    assert rows
    same_day = [r for r in rows if date_key(r.get('pick_date')) == date_key(r.get('join_date'))]
    assert not same_day


def test_v90_report_matches_output_counts_and_field_audit():
    report = load('v90_daily_scan_report.json')
    rows = load('v90_active_picks.json')
    assert report['recent_active_candidates'] == len(rows)
    assert report['latest_market_date'] == '20260612'
    assert all(v == 0 for v in report['field_audit_recent'].values())
    assert report['known_bsl_rate_recent'] == 100.0
