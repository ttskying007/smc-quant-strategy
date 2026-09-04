#!/usr/bin/env python3
"""V386 no-write PIT disclosure availability gate for the frozen V381 candidates.

Reads only candidate identity/timing.  It never reads or emits execution outcomes.
Eastmoney announcements are retained only when provider publication time (eiTime)
is no later than the completed 60m hold timestamp.
"""
from __future__ import annotations

import csv
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
V381 = AUD / 'v381_true_mtf_raw_daily_poi_m60_replay_latest.json'
OUT = AUD / f'v386_pit_disclosure_availability_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v386_pit_disclosure_availability_latest.json'
URL = 'https://np-anotice-stock.eastmoney.com/api/security/ann'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}
LOOKBACK_DAYS, CHUNK_SIZE = 5, 200


def stamp(value: str) -> datetime | None:
    try:
        return datetime.strptime(value[:19], '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return None


def code(symbol: str) -> str:
    return symbol.split('.', 1)[0]


def fetch(session: requests.Session, codes: list[str], start: str, end: str) -> tuple[list[dict], str | None]:
    rows: list[dict] = []
    page = 1
    try:
        while True:
            params = {'client_source': 'web', 'page_size': 100, 'page_index': page,
                      'ann_type': 'A', 'stock_list': ','.join(codes),
                      'begin_time': start, 'end_time': end}
            response = session.get(URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json().get('data') or {}
            batch = data.get('list') or []
            rows.extend(batch)
            if len(rows) >= int(data.get('total_hits') or 0) or not batch:
                return rows, None
            page += 1
            if page > 100:
                return rows, 'PAGE_CAP_EXCEEDED'
            time.sleep(.03)
    except Exception as exc:
        return rows, f'{type(exc).__name__}:{exc}'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads(V381.read_text())
    # Deliberately discard every column except source identity and decision cutoff.
    with Path(report['artifacts']['trades']).open(newline='') as handle:
        targets = [{'symbol': row['symbol'], 'hold_time': row['hold_time']} for row in csv.DictReader(handle)]
    targets = sorted(set((row['symbol'], row['hold_time']) for row in targets))
    by_day: dict[str, set[str]] = defaultdict(set)
    for symbol, hold_time in targets:
        by_day[hold_time[:10]].add(symbol)

    session = requests.Session(); session.headers.update(HEADERS)
    fetched: dict[str, list[dict]] = defaultdict(list)
    failures: list[dict] = []
    query_count = 0
    for day, symbols in sorted(by_day.items()):
        end = datetime.strptime(day, '%Y-%m-%d').date()
        start = end - timedelta(days=LOOKBACK_DAYS)
        symbol_list = sorted(symbols)
        for offset in range(0, len(symbol_list), CHUNK_SIZE):
            batch = symbol_list[offset:offset + CHUNK_SIZE]
            rows, error = fetch(session, [code(x) for x in batch], start.isoformat(), end.isoformat())
            query_count += 1
            if error:
                failures.append({'day': day, 'symbols': len(batch), 'error': error})
                continue
            for row in rows:
                for item in row.get('codes') or []:
                    stock = item.get('stock_code')
                    if stock:
                        fetched[stock].append(row)
            time.sleep(.04)

    feature_rows: list[dict] = []
    for symbol, hold_time in targets:
        cutoff = stamp(hold_time)
        history = fetched.get(code(symbol), [])
        eligible = []
        missing_time = 0
        for announcement in history:
            published = stamp(announcement.get('eiTime', ''))
            if published is None:
                missing_time += 1
            elif cutoff is not None and published <= cutoff:
                eligible.append(announcement)
        feature_rows.append({
            'symbol': symbol, 'hold_time': hold_time, 'feature_cutoff': hold_time,
            'query_window_days': LOOKBACK_DAYS,
            'provider_rows_for_symbol': len(history),
            'timestamped_rows': len(history) - missing_time,
            'pit_eligible_rows': len(eligible),
            'latest_eligible_eiTime': max((x.get('eiTime', '') for x in eligible), default=''),
            'provider_timestamp_complete': missing_time == 0,
            'source_contract': 'Eastmoney ann API; eiTime <= hold_time only',
        })

    with (OUT / 'v386_disclosure_availability_features.csv').open('w', newline='') as handle:
        fields = list(feature_rows[0]) if feature_rows else ['symbol']
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(feature_rows)
    timestamp_complete = all(row['provider_timestamp_complete'] for row in feature_rows)
    gate = {
        'target_rows': len(targets), 'feature_rows': len(feature_rows),
        'unique_hold_days': len(by_day), 'api_queries': query_count, 'query_failures': len(failures),
        'all_targets_accounted': len(feature_rows) == len(targets),
        'all_queries_succeeded': not failures,
        'all_provider_timestamps_parseable': timestamp_complete,
        'outcome_fields_read_or_emitted': False,
        'all_feature_cutoffs_equal_hold_time': all(row['feature_cutoff'] == row['hold_time'] for row in feature_rows),
    }
    passed = (gate['all_targets_accounted'] and gate['all_queries_succeeded'] and
              gate['all_provider_timestamps_parseable'] and not gate['outcome_fields_read_or_emitted'] and
              gate['all_feature_cutoffs_equal_hold_time'])
    result = {
        'version': 'V386_PIT_DISCLOSURE_AVAILABILITY_GATE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'contract': 'V381 identity/timing only; Eastmoney announcement publication eiTime must be <= completed hold time',
        'gate': gate,
        'decision': 'PIT_DISCLOSURE_AVAILABILITY_PASS__OUTCOME_BLIND_EVENT_SCHEMA_ALLOWED' if passed else 'PIT_DISCLOSURE_AVAILABILITY_FAIL__STOP',
        'artifacts': {'features': str(OUT / 'v386_disclosure_availability_features.csv'), 'latest': str(LATEST)},
        'failure_samples': failures[:50],
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v386_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
