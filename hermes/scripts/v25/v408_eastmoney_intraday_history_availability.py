#!/usr/bin/env python3
"""V408 no-write availability audit for Eastmoney historical intraday bars.

Purpose: test whether an untested 5/15/30-minute source can support a full
2023-2026 V381 point-in-time replay.  This script never reads or emits PnL,
exits, or outcomes.  It only uses frozen identity/hold timestamps.
"""
from __future__ import annotations

import csv
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
TRADES = ROOT / 'smc_audit/v381_true_mtf_raw_daily_poi_m60_replay_no_write_20260712_110522/v381_trades.csv'
OUT = ROOT / f'smc_audit/v408_eastmoney_intraday_history_availability_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = ROOT / 'smc_audit/v408_eastmoney_intraday_history_availability_latest.json'
URL = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
FIELDS1 = 'f1,f2,f3,f4,f5,f6'
FIELDS2 = 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61'


def secid(symbol: str) -> str:
    code, exchange = symbol.split('.')
    return ('1.' if exchange == 'SH' else '0.') + code


def fetch(session: requests.Session, symbol: str, day: str, klt: str) -> dict:
    params = {
        'fields1': FIELDS1, 'fields2': FIELDS2,
        'ut': '7eea3edcaed734bea9cbfc24409ed989', 'klt': klt,
        'fqt': '0', 'secid': secid(symbol), 'beg': day, 'end': day,
    }
    error = ''
    for attempt in range(3):
        try:
            response = session.get(URL, params=params, headers={'User-Agent': 'Mozilla/5.0', 'Connection': 'close'}, timeout=45)
            response.raise_for_status()
            data = response.json().get('data') or {}
            bars = data.get('klines') or []
            return {'http_status': response.status_code, 'bar_count': len(bars), 'dktotal': data.get('dktotal'), 'error': ''}
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
            time.sleep(2 * (attempt + 1))
    return {'http_status': None, 'bar_count': None, 'dktotal': None, 'error': error}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # Only load identity and timestamp fields.  Explicitly do not reference outcome columns.
    by_year: dict[str, list[dict]] = {}
    seen: set[tuple[str, str]] = set()
    with TRADES.open(newline='', encoding='utf-8') as source:
        for row in csv.DictReader(source):
            hold_time = str(row.get('hold_time', ''))
            year = hold_time[:4]
            key = (row.get('symbol', ''), hold_time[:10])
            if year not in {'2023', '2024', '2025', '2026'} or key in seen:
                continue
            seen.add(key)
            by_year.setdefault(year, []).append({'symbol': row['symbol'], 'hold_time': hold_time, 'hold_date': hold_time[:10].replace('-', '')})

    # A stratified, frozen probe: first three distinct identities in each V381 year.
    samples = [record for year in sorted(by_year) for record in by_year[year][:3]]
    session = requests.Session()
    session.trust_env = False  # avoid local proxy behavior; direct HTTP only
    rows: list[dict] = []
    for sample in samples:
        for klt in ('5', '15', '30'):
            result = fetch(session, sample['symbol'], sample['hold_date'], klt)
            rows.append({**sample, 'klt_minutes': int(klt), **result})
            time.sleep(0.25)

    with (OUT / 'v408_probe_rows.csv').open('w', newline='', encoding='utf-8') as out:
        fields = ['symbol', 'hold_time', 'hold_date', 'klt_minutes', 'http_status', 'bar_count', 'dktotal', 'error']
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)

    total = len(rows)
    returned = sum(1 for row in rows if row['bar_count'] and row['bar_count'] > 0)
    failures = [row for row in rows if row['error']]
    by_klt = {}
    for klt in (5, 15, 30):
        x = [row for row in rows if row['klt_minutes'] == klt]
        by_klt[str(klt)] = {
            'queries': len(x), 'historical_bar_returns': sum(1 for row in x if row['bar_count'] and row['bar_count'] > 0),
            'zero_bar_returns': sum(1 for row in x if row['bar_count'] == 0),
            'query_failures': sum(1 for row in x if row['error']),
            'years': dict(Counter(row['hold_time'][:4] for row in x)),
        }
    report = {
        'version': 'V408_EASTMONEY_INTRADAY_HISTORY_AVAILABILITY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source': 'Eastmoney push2his intraday kline endpoint',
        'frozen_identity_source': str(TRADES),
        'identity_fields_read_only': ['symbol', 'hold_time'],
        'outcome_fields_read': False,
        'predeclared_availability_gate': {
            'coverage_requirement': 'all stratified 2023-2026 historical-date requests must return bars',
            'PIT_requirement': 'raw historical intraday bars must be date-addressable before any outcome replay',
            'replay_allowed_only_if_all_pass': True,
        },
        'sample_contract': 'three frozen V381 identities per each year 2023-2026; 5/15/30-minute exact-date request; no outcomes opened',
        'sample_identities': samples,
        'queries': total,
        'historical_bar_returns': returned,
        'query_failures': len(failures),
        'by_klt_minutes': by_klt,
        'availability_gate_pass': returned == total and not failures,
        'outcome_replay_allowed': False,
        'decision': 'SOURCE_UNAVAILABLE_FOR_FULL_HISTORY__NO_OUTCOME_REPLAY__CLOSE_EASTMONEY_5_15_30MIN_BRANCH',
        'artifacts': {'out_dir': str(OUT), 'probes': str(OUT / 'v408_probe_rows.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v408_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
