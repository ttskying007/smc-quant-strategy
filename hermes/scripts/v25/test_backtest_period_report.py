#!/usr/bin/env python3
"""Regression tests for immutable yearly/monthly frozen-backtest reporting."""
from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

from backtest_period_report import build_period_report, write_period_reports


def test_period_metrics_are_entry_date_based_and_do_not_filter_rows():
    rows = [
        {'symbol': '000001.SZ', 'status': 'CLOSED', 'entry_date': '20240102', 'net_pnl_pct': '2.0', 'reason': 'TP_STRUCTURAL', 'hold_bars': '2', 'same_day_exit_violation': 'False'},
        {'symbol': '000002.SZ', 'status': 'CLOSED', 'entry_date': '20240103', 'net_pnl_pct': '-1.0', 'reason': 'SL', 'hold_bars': '3', 'same_day_exit_violation': 'False'},
        {'symbol': '000003.SZ', 'status': 'CLOSED', 'entry_date': '20250203', 'net_pnl_pct': '3.0', 'reason': 'TP_STRUCTURAL', 'hold_bars': '4', 'same_day_exit_violation': 'False'},
    ]
    report = build_period_report(rows, engine='TEST', input_ledger='fixture.csv')
    assert report['closed_rows_read'] == 3
    assert [row['entry_year'] for row in report['yearly']] == ['2024', '2025']
    assert [row['entry_month'] for row in report['monthly']] == ['202401', '202502']
    assert report['monthly'][0]['trade_count'] == 2
    assert report['monthly'][0]['gross_wr_pct'] == 50.0
    assert report['invariants']['periods_derived_after_replay_only'] is True
    assert report['invariants']['no_period_filtering_or_parameter_search'] is True


def test_period_artifacts_are_written_and_readable():
    rows = [{'symbol': '000001.SZ', 'status': 'CLOSED', 'entry_date': '20240102', 'net_pnl_pct': '1', 'reason': 'TP_STRUCTURAL'}]
    with tempfile.TemporaryDirectory() as temp:
        artifacts = write_period_reports(rows, out_dir=Path(temp), stem='fixture', engine='TEST', input_ledger='fixture.csv')
        payload = json.loads(Path(artifacts['json']).read_text())
        assert payload['overall']['trade_count'] == 1
        with Path(artifacts['yearly_csv']).open(newline='', encoding='utf-8') as handle:
            assert list(csv.DictReader(handle))[0]['entry_year'] == '2024'
        with Path(artifacts['monthly_csv']).open(newline='', encoding='utf-8') as handle:
            assert list(csv.DictReader(handle))[0]['entry_month'] == '202401'


if __name__ == '__main__':
    test_period_metrics_are_entry_date_based_and_do_not_filter_rows()
    test_period_artifacts_are_written_and_readable()
    print('PASS: immutable yearly/monthly backtest reporting')
