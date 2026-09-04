#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path('/root/.hermes/scripts/v25/v96_adaptive_entry_exit_search.py')
OUT = Path('/root/.hermes/smc_opt_v96_adaptive_entry_exit_search')


def load_mod():
    spec = importlib.util.spec_from_file_location('v96_adaptive_entry_exit_search', SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_v96_module_exists_and_exposes_universal_rules():
    mod = load_mod()
    assert hasattr(mod, 'ENTRY_RULES')
    assert hasattr(mod, 'SL_RULES')
    assert hasattr(mod, 'EXIT_RULES')
    assert len(mod.ENTRY_RULES) >= 4
    assert len(mod.SL_RULES) >= 3
    assert len(mod.EXIT_RULES) >= 4
    for rules in (mod.ENTRY_RULES, mod.SL_RULES, mod.EXIT_RULES):
        for rule in rules:
            assert 'symbol' not in str(rule).lower(), rule
            assert '000' not in str(rule), rule


def test_v96_run_generates_full_market_non_stock_specific_report():
    mod = load_mod()
    report = mod.run_search(write_outputs=True)
    assert report['source_trade_count'] == 532
    assert report['field_audit']['missing_kline_count'] == 0
    assert report['field_audit']['t1_violation_count'] == 0
    assert report['field_audit']['stock_specific_rule_count'] == 0
    assert report['matrix_rows'] >= 532 * 20
    assert len(report['best_by_score']) >= 10
    best = report['best_by_score'][0]
    assert best['n'] >= 300
    assert best['wr'] >= 80
    assert best['avg'] > report['baseline_v88']['avg']
    assert best['post20_big_up10_rate'] < report['baseline_post_exit']['post20_big_up10_rate']


def test_v96_best_contract_has_year_stability_and_required_fields():
    mod = load_mod()
    report = mod.run_search(write_outputs=True)
    best = report['best_by_score'][0]
    for y in ['2023', '2024', '2025', '2026']:
        yy = best['by_year'][y]
        assert yy['n'] >= 40
        assert yy['wr'] >= 70
    rows_path = OUT / 'v96_best_rows.json'
    assert rows_path.exists() and rows_path.stat().st_size > 1000
    import json
    rows = json.loads(rows_path.read_text())
    assert len(rows) == best['n']
    required = ['symbol','pick_date','entry_date_v96','exit_date_v96','entry_price_v96','sl_v96','tp1_v96','tp2_v96','exit_reason_v96','pnl_pct_v96','entry_rule','sl_rule','exit_rule','post20_max_after_exit_pct_v96']
    for r in rows[:50]:
        for k in required:
            assert k in r and r[k] not in (None, ''), (k, r.get('symbol'))


if __name__ == '__main__':
    tests = [
        test_v96_module_exists_and_exposes_universal_rules,
        test_v96_run_generates_full_market_non_stock_specific_report,
        test_v96_best_contract_has_year_stability_and_required_fields,
    ]
    for t in tests:
        t()
        print('PASS', t.__name__)
