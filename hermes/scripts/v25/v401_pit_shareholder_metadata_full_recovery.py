#!/usr/bin/env python3
"""V401 no-write full recovery of V399 announcement metadata and PIT eligibility.

This corrects only V399's transport-failed metadata leg. It does not query holder
values or any trade outcome, and therefore cannot run an economic replay.
"""
from __future__ import annotations

import csv
import importlib.util
import json
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
V399 = AUD / 'v399_pit_shareholder_holdings_feasibility_latest.json'
MAP = AUD / 'v399_pit_shareholder_holdings_feasibility_no_write_20260712_194024/v399_fixed_identity_pit_holder_mapping.csv'
OUT = AUD / f'v401_pit_shareholder_metadata_full_recovery_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v401_pit_shareholder_metadata_full_recovery_latest.json'


def load_v400():
    path = ROOT / 'scripts/v25/v400_announcement_metadata_recovery_pilot.py'
    spec = importlib.util.spec_from_file_location('v400_recovery', path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def digits(value: str) -> str:
    return ''.join(char for char in str(value or '') if char.isdigit())[:8]


def report_end(title: str) -> str:
    import re
    match = re.search(r'(20\d{2})年(第一季度|半年度|第三季度|年度)报告', title or '')
    if not match:
        return ''
    year, period = match.groups()
    return year + {'第一季度': '0331', '半年度': '0630', '第三季度': '0930', '年度': '1231'}[period]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads(V399.read_text())
    failed = list(source['errors']['announcement_metadata'])
    v400 = load_v400()
    from concurrent.futures import ThreadPoolExecutor, as_completed
    recovered: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=v400.WORKERS) as pool:
        futures = {pool.submit(v400.fetch_symbol, symbol): symbol for symbol in failed}
        for future in as_completed(futures):
            row = future.result()
            recovered[row['symbol']] = row
    (OUT / 'v401_recovered_symbol_reports.json').write_text(json.dumps(recovered, ensure_ascii=False, indent=2))

    mapping: list[dict] = []
    with MAP.open(newline='') as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        symbol, entry = row['symbol'], digits(row['entry_date'])
        if symbol not in recovered:
            mapping.append({**row, 'v401_metadata_status': 'UNCHANGED_V399', 'v401_report_end': ''})
            continue
        result = recovered[symbol]
        candidates = []
        for notice in result.get('reports', []):
            public = digits(notice.get('publication_time')) or digits(notice.get('notice_date'))
            period_end = report_end(notice.get('title', ''))
            if public and period_end and public < entry and period_end < entry:
                candidates.append((public, period_end, notice))
        if candidates:
            public, period_end, notice = max(candidates, key=lambda item: item[:2])
            mapping.append({**row, 'v401_metadata_status': 'RECOVERED_PRIOR_PERIODIC_REPORT',
                            'v401_report_end': period_end, 'v401_publication_time': public,
                            'v401_announcement_id': notice.get('id', ''), 'v401_title': notice.get('title', '')})
        elif result.get('ok'):
            mapping.append({**row, 'v401_metadata_status': 'RECOVERED_NO_PRIOR_PUBLIC_REPORT', 'v401_report_end': ''})
        else:
            mapping.append({**row, 'v401_metadata_status': 'RECOVERY_HTTP_FAILED', 'v401_report_end': ''})
    fields = sorted({key for row in mapping for key in row})
    with (OUT / 'v401_fixed_identity_metadata_mapping.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(mapping)

    total = len(mapping)
    recovered_prior = [row for row in mapping if row['v401_metadata_status'] == 'RECOVERED_PRIOR_PERIODIC_REPORT']
    recovery_failed = [row for row in mapping if row['v401_metadata_status'] == 'RECOVERY_HTTP_FAILED']
    existing_ready = [row for row in mapping if row['mapping_status'] == 'PIT_HOLDER_SNAPSHOT_READY']
    metadata_ready = len(existing_ready) + len(recovered_prior)
    by_year = {}
    for year in ('2023', '2024', '2025', '2026'):
        subset = [row for row in mapping if digits(row['entry_date']).startswith(year)]
        ready = sum(row['mapping_status'] == 'PIT_HOLDER_SNAPSHOT_READY' or row['v401_metadata_status'] == 'RECOVERED_PRIOR_PERIODIC_REPORT' for row in subset)
        by_year[year] = {'total': len(subset), 'metadata_eligible': ready,
                         'metadata_eligible_pct': round(100 * ready / len(subset), 4) if subset else 0}
    report = {
        'version': 'V401_PIT_SHAREHOLDER_METADATA_FULL_RECOVERY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'input_contract': 'V399 fixed identities plus metadata-failed symbols only; no holder values, outcome, PnL, exit, or replay field read',
        'recovery_contract': 'Eastmoney public announcement metadata; exact periodic-report title; report-end < entry and publication time < entry; same-day use prohibited',
        'counts': {'identities': total, 'v399_holder_snapshot_ready': len(existing_ready),
                   'recovery_symbols_requested': len(failed),
                   'recovery_symbol_http_ok': sum(row.get('ok', False) for row in recovered.values()),
                   'recovery_symbol_http_failed': sum(not row.get('ok', False) for row in recovered.values()),
                   'recovered_prior_periodic_reports': len(recovered_prior),
                   'recovery_http_failed_identities': len(recovery_failed),
                   'metadata_eligible_identities': metadata_ready,
                   'metadata_eligible_pct': round(100 * metadata_ready / total, 4) if total else 0},
        'yearly_metadata_eligibility': by_year,
        'gate': {'metadata_coverage_min_pct': 95.0,
                 'all_year_metadata_coverage_min_pct': 95.0,
                 'holder_snapshot_values_rematerialized': False,
                 'outcome_replay_allowed': False},
        'decision': ('METADATA_TRANSPORT_DEFECT_RECOVERED__HOLDER_VALUE_REHYDRATION_REQUIRED_BEFORE_REPLAY'
                     if metadata_ready / total >= 0.95 and all(v['metadata_eligible_pct'] >= 95 for v in by_year.values()) else
                     'METADATA_COVERAGE_STILL_INSUFFICIENT__KEEP_SOURCE_CLOSED'),
        'invariants': {'no_outcome_fields_read': True, 'no_holder_values_read': True, 'no_production_write': True,
                       'no_frontend_write': True, 'no_watchlist_write': True},
        'artifacts': {'out_dir': str(OUT), 'symbol_reports': str(OUT / 'v401_recovered_symbol_reports.json'),
                      'mapping': str(OUT / 'v401_fixed_identity_metadata_mapping.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v401_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
