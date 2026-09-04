#!/usr/bin/env python3
"""V653 source-only daily-session coverage audit for frozen V652 cash-term events.

Reads only bar dates (`t`), never price/volume values. It creates no seed or outcome.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
CACHE = ROOT / 'kline_cache'
PREREG = AUD / 'v652_explicit_cash_distribution_post_disclosure_smc_response_ontology_preregistration.json'
CATALOG = AUD / 'v650_explicit_cash_distribution_term_catalog_no_outcome_20260726_171232' / 'v650_canonical_explicit_cash_terms.csv'
LATEST = AUD / 'v653_cash_distribution_event_daily_session_coverage_audit_no_outcome_latest.json'
YEARS = ('2023', '2024', '2025')


def cache_path(symbol: str) -> Path:
    code, exchange = symbol.split('.')
    return CACHE / f'{code}_{exchange}_daily_750.json'


def date_list(path: Path) -> list[str]:
    # Deliberately extract date only; no OHLCV field is accessed.
    rows = json.loads(path.read_text())
    return [str(row['t']) for row in rows if str(row.get('t', '')).isdigit() and len(str(row['t'])) == 8]


def main() -> None:
    prereg = json.loads(PREREG.read_text())
    assert prereg['decision'] == 'V652_CAUSAL_ONTOLOGY_PREREGISTERED__SOURCE_ONLY_DAILY_OHLCV_QUALIFICATION_AUTHORIZED__NO_SEED_NO_REPLAY_NO_PRODUCTION'
    events = list(csv.DictReader(CATALOG.open(encoding='utf-8')))

    # The union of all same-source daily-cache dates is the source-session calendar.
    calendar = set()
    all_cache_paths = list(CACHE.glob('*_daily_750.json'))
    for path in all_cache_paths:
        calendar.update(date_list(path))
    sessions = sorted(calendar)
    session_index = {date: index for index, date in enumerate(sessions)}

    by_symbol: dict[str, list[str]] = {}
    issues: list[dict] = []
    valid = []
    reasons = Counter()
    for event in events:
        symbol = event['symbol']
        if symbol not in by_symbol:
            path = cache_path(symbol)
            by_symbol[symbol] = date_list(path) if path.exists() else []
        stock_dates = by_symbol[symbol]
        notice = event['notice_date'].replace('-', '')
        next_positions = [i for i, date in enumerate(sessions) if date > notice]
        if not next_positions:
            reason = 'NO_LATER_SOURCE_SESSION'
            reasons[reason] += 1
            issues.append({**event, 'reason': reason})
            continue
        start_idx = next_positions[0]
        observation_start = sessions[start_idx]
        response_end_idx = start_idx + 19
        if response_end_idx >= len(sessions):
            reason = 'INSUFFICIENT_SOURCE_CALENDAR_AFTER_OBSERVATION_START'
            reasons[reason] += 1
            issues.append({**event, 'observation_start_date': observation_start, 'reason': reason})
            continue
        required = sessions[start_idx:response_end_idx + 1]
        stock_date_set = set(stock_dates)
        missing = [date for date in required if date not in stock_date_set]
        if missing:
            reason = 'MISSING_EXACT_OBSERVATION_OR_RESPONSE_SESSION_BARS'
            reasons[reason] += 1
            issues.append({**event, 'observation_start_date': observation_start, 'response_window_end_date': required[-1], 'missing_session_dates': '|'.join(missing), 'reason': reason})
            continue
        valid.append({**event, 'observation_start_date': observation_start, 'response_window_end_date': required[-1]})

    valid_by_year = {year: sum(x['notice_date'].startswith(year) for x in valid) for year in YEARS}
    total_by_year = {year: sum(x['notice_date'].startswith(year) for x in events) for year in YEARS}
    report = {
        'version': 'V653_CASH_DISTRIBUTION_EVENT_DAILY_SESSION_COVERAGE_AUDIT_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_lane': 'B_CORPORATE_ACTION_TERMS',
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'V652 source qualification only. The implementation reads only daily-cache bar dates t, not open/high/low/close/volume. No response, SMC node, seed, trade, outcome, PnL, stop, target or replay is generated.',
        'lineage': {'preregistration': str(PREREG), 'immutable_catalog': str(CATALOG), 'daily_cache': str(CACHE / '*_daily_750.json')},
        'session_calendar': {'construction': 'sorted union of t dates from same-source *_daily_750.json files', 'cache_files_read': len(all_cache_paths), 'sessions': len(sessions), 'first_date': sessions[0], 'last_date': sessions[-1]},
        'denominator': {'canonical_events': len(events), 'by_event_year': total_by_year, 'unique_symbols': len(by_symbol)},
        'coverage': {'valid_events_with_exact_observation_start_and_all_20_response_sessions': len(valid), 'valid_by_event_year': valid_by_year, 'invalid_events': len(issues), 'issue_counts': dict(reasons), 'issues': issues[:50]},
        'hard_gate': {'exact_next_source_session_required': True, 'twenty_consecutive_source_sessions_required': True, 'coverage_required': 1.0, 'pass': len(valid) == len(events)},
        'artifacts': {},
        'decision': 'SOURCE_SESSION_COVERAGE_PASS__OUTCOME_BLIND_V652_SEED_GENERATION_AUTHORIZED' if len(valid) == len(events) else 'SOURCE_SESSION_COVERAGE_FAIL__CLOSE_V652_NO_SEED_NO_ORACLE_NO_REPLAY_NO_PRODUCTION',
    }
    out = AUD / f'v653_cash_distribution_event_daily_session_coverage_audit_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
    out.mkdir(parents=True, exist_ok=True)
    with (out / 'v653_validated_event_sessions.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(valid[0]) if valid else list(events[0]) + ['observation_start_date', 'response_window_end_date'])
        writer.writeheader(); writer.writerows(valid)
    with (out / 'v653_issues.csv').open('w', newline='', encoding='utf-8') as handle:
        fields = sorted({key for row in issues for key in row}) or ['reason']
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(issues)
    report['artifacts'] = {'dir': str(out), 'validated_event_sessions': str(out / 'v653_validated_event_sessions.csv'), 'issues': str(out / 'v653_issues.csv')}
    (out / 'v653_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
