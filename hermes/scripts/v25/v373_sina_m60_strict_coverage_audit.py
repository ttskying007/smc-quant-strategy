#!/usr/bin/env python3
"""V373 no-write strict coverage audit for the downloaded Sina 60-minute cache.

Only validates source bars against locally available daily dates. It creates no
signals, trades, PnL, production, frontend, or watchlist output.
"""
from __future__ import annotations

import gzip
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
DAILY = ROOT / 'kline_cache'
CACHE = ROOT / 'intraday_cache' / 'sina_m60_v1'
AUDIT = ROOT / 'smc_audit'
START, END = '20230101', '20260710'
SLOTS = {'10:30:00', '11:30:00', '14:00:00', '15:00:00'}
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v373_sina_m60_strict_coverage_no_write_{TS}'
LATEST = AUDIT / 'v373_sina_m60_strict_coverage_latest.json'


def date_of(value: object) -> str:
    return ''.join(str(value or '').split(' ')[0].split('-'))[:8]


def read_json(path: Path):
    return json.loads(path.read_text())


def expected_days(path: Path) -> set[str]:
    return {date_of(x.get('t') or x.get('date')) for x in read_json(path)
            if START <= date_of(x.get('t') or x.get('date')) <= END}


def check(path: Path, code: str, exchange: str) -> dict:
    symbol = f'{code}.{exchange}'
    expected = expected_days(path)
    cache_path = CACHE / f'{code}_{exchange}_m60_sina.json.gz'
    if not expected:
        return {'symbol': symbol, 'expected_days': 0, 'status': 'NO_LOCAL_EXPECTED_DAYS'}
    if not cache_path.exists():
        return {'symbol': symbol, 'expected_days': len(expected), 'status': 'CACHE_MISSING'}
    try:
        with gzip.open(cache_path, 'rt') as handle:
            raw = json.load(handle)
    except Exception as exc:
        return {'symbol': symbol, 'expected_days': len(expected), 'status': 'CACHE_PARSE_ERROR', 'error': repr(exc)}
    per_day: dict[str, list[dict]] = defaultdict(list)
    for bar in raw:
        day = date_of(bar.get('day'))
        if START <= day <= END:
            per_day[day].append(bar)
    actual = set(per_day)
    missing = sorted(expected - actual)
    bad_slots = []
    for day in sorted(expected & actual):
        rows = per_day[day]
        slots = {str(row.get('day') or '')[-8:] for row in rows}
        if len(rows) != 4 or slots != SLOTS:
            bad_slots.append(day)
    status = 'COMPLETE' if not missing and not bad_slots else 'INCOMPLETE'
    return {
        'symbol': symbol, 'status': status, 'expected_days': len(expected), 'actual_days': len(actual),
        'missing_days': len(missing), 'missing_sample': missing[:20],
        'bad_slot_days': len(bad_slots), 'bad_slot_sample': bad_slots[:20],
        'year_expected': {y: sum(d.startswith(y) for d in expected) for y in ('2023', '2024', '2025', '2026')},
        'year_covered': {y: sum(d.startswith(y) and d not in bad_slots for d in expected & actual) for y in ('2023', '2024', '2025', '2026')},
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in sorted(DAILY.glob('*_daily_750.json')):
        match = re.fullmatch(r'(\d+)_(SH|SZ)_daily_750\.json', path.name)
        if match:
            rows.append(check(path, match.group(1), match.group(2)))
    rows.sort(key=lambda row: row['symbol'])
    scoped = [row for row in rows if row['status'] != 'NO_LOCAL_EXPECTED_DAYS']
    incomplete = [row for row in scoped if row['status'] != 'COMPLETE']
    year = {}
    for y in ('2023', '2024', '2025', '2026'):
        expected = sum(row.get('year_expected', {}).get(y, 0) for row in scoped)
        covered = sum(row.get('year_covered', {}).get(y, 0) for row in scoped)
        year[y] = {'expected_days': expected, 'covered_days': covered,
                   'coverage_pct': round(covered / expected * 100, 8) if expected else 0,
                   'symbols_complete': sum(row.get('year_expected', {}).get(y, 0) == row.get('year_covered', {}).get(y, 0) and row.get('year_expected', {}).get(y, 0) > 0 for row in scoped)}
    report = {
        'version': 'V373_SINA_M60_STRICT_COVERAGE_AUDIT_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source_contract': 'Sina cached 60m bars; every locally available daily date must have exactly 10:30/11:30/14:00/15:00 slots',
        'range': {'start': START, 'end': END, 'expected_slots': sorted(SLOTS)},
        'universe_symbols': len(rows), 'symbols_with_expected_dates': len(scoped),
        'counts': {'complete_symbols': sum(row['status'] == 'COMPLETE' for row in scoped),
                   'incomplete_symbols': len(incomplete),
                   'missing_day_count': sum(row.get('missing_days', 0) for row in scoped),
                   'bad_slot_day_count': sum(row.get('bad_slot_days', 0) for row in scoped)},
        'yearly_coverage': year,
        'decision': 'SOURCE_COVERAGE_PASS__MTF_GENERATOR_ALLOWED' if not incomplete else 'SOURCE_COVERAGE_FAIL__REPAIR_OR_EXPLICITLY_QUARANTINE_INCOMPLETE_SYMBOLS',
        'failure_samples': incomplete[:200],
        'artifacts': {'rows': str(OUT / 'v373_symbol_rows.json'), 'report': str(OUT / 'v373_report.json'), 'latest': str(LATEST)},
    }
    (OUT / 'v373_symbol_rows.json').write_text(json.dumps(rows, ensure_ascii=False))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v373_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
