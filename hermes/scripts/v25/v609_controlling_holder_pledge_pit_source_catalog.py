#!/usr/bin/env python3
"""V609 outcome-blind PIT source qualification for controlling-holder pledge events.

This catalog records only timestamped public disclosure metadata. It does not
open market, trade, outcome, or prior research-result files.
"""
from __future__ import annotations

import csv
import json
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
DAILY = ROOT / 'kline_cache'
OUT = AUDIT / f'v609_controlling_holder_pledge_pit_source_catalog_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v609_controlling_holder_pledge_pit_source_catalog_latest.json'
API = 'https://np-anotice-stock.eastmoney.com/api/security/ann'
START, END = '2023-01-01', '2025-12-31'
WORKERS, PAGE_SIZE = 2, 100
CONTROLLER = re.compile(r'控股股东|实际控制人|第一大股东|持股5%以上')
RELEASE = re.compile(r'解除质押|解[除除]?除?质押|质押解除')
CREATE = re.compile(r'股份质押|股票质押|质押式回购')
ROUTINE = re.compile(r'法律意见|核查意见|更正|补充公告')


def universe() -> list[str]:
    symbols = set()
    for path in DAILY.glob('*_daily_750.json'):
        token = path.name.removesuffix('_daily_750.json')
        if re.fullmatch(r'\d{6}_(?:SH|SZ|BJ)', token):
            symbols.add(token.replace('_', '.'))
    return sorted(symbols)


def date8(value: Any) -> str:
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else ''


def event_kind(title: str) -> str | None:
    if ROUTINE.search(title) or not CONTROLLER.search(title):
        return None
    if RELEASE.search(title):
        return 'CONTROLLING_HOLDER_PLEDGE_RELEASE'
    if CREATE.search(title):
        return 'CONTROLLING_HOLDER_PLEDGE_CREATE'
    return None


def fetch(symbol: str) -> dict[str, Any]:
    session = requests.Session()
    selected: list[dict[str, str]] = []
    total_hits = 0
    for page in range(1, 1001):
        params = {
            'client_source': 'web', 'page_size': PAGE_SIZE, 'page_index': page,
            'ann_type': 'A', 'stock_list': symbol[:6], 'begin_time': START,
            'end_time': END,
        }
        payload: dict[str, Any] | None = None
        error = ''
        for attempt in range(3):
            try:
                response = session.get(API, params=params, timeout=30,
                                       headers={'User-Agent': 'Mozilla/5.0'})
                payload = response.json()
                if response.status_code != 200 or payload.get('success') != 1:
                    raise ValueError(f'http={response.status_code} success={payload.get("success")}')
                break
            except Exception as exc:
                error = f'{type(exc).__name__}: {exc}'
                payload = None
                time.sleep(0.75 * (attempt + 1))
        if payload is None:
            return {'symbol': symbol, 'ok': False, 'error': error, 'total_hits': total_hits,
                    'fetched_hits': (page - 1) * PAGE_SIZE, 'events': []}
        data = payload.get('data') or {}
        items = data.get('list') or []
        total_hits = int(data.get('total_hits') or 0)
        for item in items:
            title = str(item.get('title') or '')
            kind = event_kind(title)
            if kind:
                selected.append({
                    'symbol': symbol, 'event_kind': kind,
                    'announcement_id': str(item.get('art_code') or ''),
                    'notice_date': date8(item.get('notice_date')),
                    'publication_time': str(item.get('eiTime') or ''), 'title': title,
                })
        if page * PAGE_SIZE >= total_hits or not items:
            return {'symbol': symbol, 'ok': True, 'error': '', 'total_hits': total_hits,
                    'fetched_hits': page * PAGE_SIZE, 'events': selected}
        time.sleep(0.08)
    return {'symbol': symbol, 'ok': False, 'error': 'page_limit_exceeded',
            'total_hits': total_hits, 'fetched_hits': 1000 * PAGE_SIZE, 'events': []}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    symbols = universe()
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(fetch, symbol): symbol for symbol in symbols}
        for count, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if count % 200 == 0:
                print(json.dumps({'symbols_done': count, 'symbols_total': len(symbols)}, ensure_ascii=False), flush=True)
    results.sort(key=lambda row: row['symbol'])
    raw = [event for row in results if row['ok'] for event in row['events']]
    canonical = {(row['symbol'], row['announcement_id']): row for row in raw if row['announcement_id']}
    events = sorted(canonical.values(), key=lambda row: (row['notice_date'], row['symbol'], row['announcement_id']))
    for row in events:
        row['event_year'] = row['notice_date'][:4]
    failed = [row for row in results if not row['ok']]
    years = ('2023', '2024', '2025')
    by_kind_year = {
        kind: {year: sum(row['event_kind'] == kind and row['event_year'] == year for row in events) for year in years}
        for kind in ('CONTROLLING_HOLDER_PLEDGE_RELEASE', 'CONTROLLING_HOLDER_PLEDGE_CREATE')
    }
    report = {
        'version': 'V609_CONTROLLING_HOLDER_PLEDGE_PIT_SOURCE_CATALOG_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source_contract': {
            'provider': 'Eastmoney public announcement metadata endpoint', 'range': [START, END],
            'fields_read': ['symbol', 'announcement_id', 'notice_date', 'publication_time', 'title'],
            'event_definition': 'controlling-holder/actual-controller/major-holder pledge creation or release disclosure; routine legal/correction notices excluded',
            'prohibited': ['price', 'volume', 'SMC seed', 'trade outcome', 'PnL', 'exit'],
            'same_day_execution_forbidden': True,
        },
        'coverage': {
            'universe_symbols': len(symbols), 'http_ok': len(results) - len(failed), 'http_failed': len(failed),
            'all_pages_fetched_for_ok_symbols': all(row['fetched_hits'] >= row['total_hits'] for row in results if row['ok']),
            'timestamp_complete_events': sum(bool(row['notice_date'] and row['publication_time']) for row in events),
        },
        'events': {
            'canonical_count': len(events),
            'by_year': {year: sum(row['event_year'] == year for row in events) for year in years},
            'by_kind': dict(Counter(row['event_kind'] for row in events)),
            'by_kind_year': by_kind_year,
            'unique_symbols': len({row['symbol'] for row in events}),
        },
        'invariants': {'no_market_or_outcome_read': True, 'no_production_write': True, 'no_frontend_write': True, 'no_watchlist_write': True},
        'artifacts': {'out_dir': str(OUT), 'events': str(OUT / 'v609_controlling_holder_pledge_events.jsonl'), 'failures': str(OUT / 'v609_fetch_failures.csv'), 'latest': str(LATEST)},
    }
    report['decision'] = ('V609_SOURCE_CATALOG_COMPLETE__INDEPENDENT_EVENT_SEMANTICS_REVIEW_REQUIRED'
                          if not failed and report['coverage']['all_pages_fetched_for_ok_symbols'] and report['coverage']['timestamp_complete_events'] == len(events)
                          else 'V609_SOURCE_CATALOG_INCOMPLETE__NO_ONTOLOGY')
    with (OUT / 'v609_controlling_holder_pledge_events.jsonl').open('w', encoding='utf-8') as handle:
        for row in events:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    with (OUT / 'v609_fetch_failures.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['symbol', 'error', 'total_hits', 'fetched_hits'])
        writer.writeheader()
        writer.writerows({key: row.get(key, '') for key in writer.fieldnames} for row in failed)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v609_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
