#!/usr/bin/env python3
"""V608 outcome-blind PIT source qualification for equity-incentive events.

This is a new corporate-control information dimension, not a price/volume
strategy. It writes only announcement metadata and coverage diagnostics.
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
OUT = AUDIT / f'v608_equity_incentive_pit_source_catalog_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v608_equity_incentive_pit_source_catalog_latest.json'
API = 'https://np-anotice-stock.eastmoney.com/api/security/ann'
START, END = '2023-01-01', '2025-12-31'
WORKERS, PAGE_SIZE = 2, 100

# A corporate compensation/capital-alignment event must be explicitly named.
# Routine lockup, cancellation, exercise and legal-opinion notices are excluded.
INCLUDE = re.compile(r'股权激励|限制性股票|股票期权|员工持股')
EXCLUDE = re.compile(r'解除限售|上市流通|回购注销|行权|归属|法律意见|独立财务顾问|核查意见|调整|修订|终止')


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


def eligible(title: str) -> bool:
    return bool(INCLUDE.search(title)) and not bool(EXCLUDE.search(title))


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
            except Exception as exc:  # network boundary; surface failures in the catalog.
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
            if eligible(title):
                selected.append({
                    'symbol': symbol,
                    'announcement_id': str(item.get('art_code') or ''),
                    'notice_date': date8(item.get('notice_date')),
                    'publication_time': str(item.get('eiTime') or ''),
                    'title': title,
                })
        if page * PAGE_SIZE >= total_hits or not items:
            return {'symbol': symbol, 'ok': True, 'error': '', 'total_hits': total_hits,
                    'fetched_hits': page * PAGE_SIZE, 'events': selected}
        time.sleep(0.08)
    return {'symbol': symbol, 'ok': False, 'error': 'page_limit_exceeded', 'total_hits': total_hits,
            'fetched_hits': 1000 * PAGE_SIZE, 'events': []}


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
    events = [event for row in results if row['ok'] for event in row['events']]
    canonical = {(row['symbol'], row['announcement_id']): row for row in events if row['announcement_id']}
    events = sorted(canonical.values(), key=lambda row: (row['notice_date'], row['symbol'], row['announcement_id']))
    for row in events:
        row['event_year'] = row['notice_date'][:4]
    failed = [row for row in results if not row['ok']]
    years = ('2023', '2024', '2025')
    report = {
        'version': 'V608_EQUITY_INCENTIVE_PIT_SOURCE_CATALOG_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source_contract': {
            'provider': 'Eastmoney public announcement metadata endpoint', 'range': [START, END],
            'fields_read': ['symbol', 'announcement_id', 'notice_date', 'publication_time', 'title'],
            'event_definition': 'title contains equity-incentive/restricted-stock/stock-option/employee-ownership terms and excludes routine lifecycle/legal notices',
            'prohibited': ['price', 'volume', 'SMC seed', 'trade outcome', 'PnL', 'exit'],
            'same_day_execution_forbidden': True,
        },
        'coverage': {
            'universe_symbols': len(symbols), 'http_ok': len(results) - len(failed), 'http_failed': len(failed),
            'all_pages_fetched_for_ok_symbols': all(row['fetched_hits'] >= row['total_hits'] for row in results if row['ok']),
            'timestamp_complete_events': sum(bool(row['notice_date'] and row['publication_time']) for row in events),
        },
        'events': {'canonical_count': len(events), 'by_year': {year: sum(row['event_year'] == year for row in events) for year in years}, 'unique_symbols': len({row['symbol'] for row in events})},
        'invariants': {'no_market_or_outcome_read': True, 'no_production_write': True, 'no_frontend_write': True, 'no_watchlist_write': True},
        'artifacts': {'out_dir': str(OUT), 'events': str(OUT / 'v608_equity_incentive_events.jsonl'), 'failures': str(OUT / 'v608_fetch_failures.csv'), 'latest': str(LATEST)},
    }
    report['decision'] = ('V608_SOURCE_CATALOG_COMPLETE__PREREGISTRATION_REQUIRES_INDEPENDENT_EVENT_SEMANTICS_REVIEW'
                          if not failed and report['coverage']['all_pages_fetched_for_ok_symbols'] and report['coverage']['timestamp_complete_events'] == len(events)
                          else 'V608_SOURCE_CATALOG_INCOMPLETE__NO_ONTOLOGY')
    with (OUT / 'v608_equity_incentive_events.jsonl').open('w', encoding='utf-8') as handle:
        for row in events:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    with (OUT / 'v608_fetch_failures.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['symbol', 'error', 'total_hits', 'fetched_hits'])
        writer.writeheader()
        writer.writerows({key: row.get(key, '') for key in writer.fieldnames} for row in failed)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v608_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
