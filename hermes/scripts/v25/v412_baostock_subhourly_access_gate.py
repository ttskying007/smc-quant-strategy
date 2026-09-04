#!/usr/bin/env python3
"""V412 no-outcome Baostock sub-hourly source access gate.

A prior 60-minute dataset was once buildable, but provider availability can
change. This test requires a successful authenticated session before treating
5/15/30-minute data as a new research branch. No price, signal, or outcome data
is read when login fails.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import baostock as bs

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
OUT = AUD / f'v412_baostock_subhourly_access_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v412_baostock_subhourly_access_latest.json'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    login = bs.login()
    login_ok = login.error_code == '0'
    probes = []
    try:
        if login_ok:
            # Frozen, exact historical dates: only availability counts, never outcomes.
            for symbol, day in (('sz.000001', '2023-08-02'), ('sh.600519', '2024-09-27'), ('sz.000001', '2025-08-15'), ('sh.600519', '2026-06-03')):
                for frequency in ('5', '15', '30'):
                    q = bs.query_history_k_data_plus(symbol, 'date,time,open,high,low,close,volume', start_date=day, end_date=day, frequency=frequency, adjustflag='3')
                    n = 0
                    while q.error_code == '0' and q.next():
                        n += 1
                    probes.append({'symbol': symbol, 'date': day, 'frequency_min': int(frequency), 'query_status': q.error_code, 'query_message': q.error_msg, 'bar_count': n})
    finally:
        if login_ok:
            bs.logout()
    complete = login_ok and len(probes) == 12 and all(p['query_status'] == '0' and p['bar_count'] > 0 for p in probes)
    report = {
        'version': 'V412_BAOSTOCK_SUBHOURLY_ACCESS_AVAILABILITY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source': 'baostock query_history_k_data_plus, raw sub-hourly frequencies 5/15/30',
        'predeclared_gate': 'successful provider login plus non-empty exact-date 5/15/30-minute raw bars across frozen 2023-2026 probes before any coverage build or outcome replay',
        'login': {'status': login.error_code, 'message': login.error_msg, 'successful': login_ok},
        'probes_attempted_after_login_only': probes,
        'outcome_fields_read': False,
        'availability_gate_pass': complete,
        'outcome_replay_allowed': False,
        'decision': ('SOURCE_ACCESS_PASS__NEXT_FULL_COVERAGE_GATE_REQUIRED' if complete else 'SOURCE_ACCESS_UNAVAILABLE__CLOSE_BAOSTOCK_SUBHOURLY_BRANCH__NO_REPLAY'),
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v412_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
