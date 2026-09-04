#!/usr/bin/env python3
"""V615 outcome-blind PIT catalog: controlling-holder pledge disclosures.

Reads only Eastmoney disclosure metadata. It deliberately does not open OHLCV,
SMC, trade, target, or result artifacts. The catalog is resumable by calendar
Day and records a complete source denominator before any strategy seed exists.
"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
OUT = AUDIT / 'v615_controlling_pledge_pit_event_catalog_no_outcome'
EVENTS = OUT / 'v615_events.jsonl'
STATE = OUT / 'v615_state.json'
LATEST = AUDIT / 'v615_controlling_pledge_pit_event_catalog_latest.json'
URL = 'https://np-anotice-stock.eastmoney.com/api/security/ann'
START, END = date(2023, 1, 1), date(2025, 12, 31)
WORKERS = 4

CONTROLLER = re.compile(r'控股股东|实际控制人|第一大股东|持股5%以上')
RELEASE = re.compile(r'解除质押|质押解除|解押|到期购回')
CREATE = re.compile(r'股份质押|股票质押|质押式回购|补充质押')
ROUTINE = re.compile(r'法律意见|核查意见|更正|补充公告')


def calendar_days() -> list[str]:
    result: list[str] = []
    current = START
    while current <= END:
        result.append(current.isoformat())
        current += timedelta(days=1)
    return result


def normalize_date(value: object) -> str:
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


def symbol_for(item: dict) -> str:
    for code in item.get('codes') or []:
        value = str(code.get('stock_code') or '')
        if len(value) == 6 and value.isdigit():
            return value + ('.SH' if value.startswith(('5', '6', '9')) else '.SZ')
    return ''


def fetch_day(day: str) -> dict:
    selected: list[dict] = []
    session = requests.Session()
    page = 1
    total_hits = 0
    for attempt in range(3):
        try:
            while True:
                response = session.get(
                    URL,
                    params={
                        'client_source': 'web', 'page_size': 100, 'page_index': page,
                        'ann_type': 'A', 'begin_time': day, 'end_time': day, 'title': '质押',
                    },
                    headers={'User-Agent': 'Mozilla/5.0'}, timeout=40,
                )
                payload = response.json()
                data = payload.get('data') or {}
                if response.status_code != 200 or payload.get('success') != 1:
                    raise RuntimeError(f'http={response.status_code} success={payload.get("success")}')
                batch = data.get('list') or []
                total_hits = int(data.get('total_hits') or 0)
                for item in batch:
                    title = re.sub(r'<[^>]+>', '', str(item.get('title') or ''))
                    kind = event_kind(title)
                    symbol = symbol_for(item)
                    notice_date = normalize_date(item.get('notice_date'))
                    publication_time = str(item.get('eiTime') or '')
                    if kind and symbol and notice_date and publication_time:
                        selected.append({
                            'symbol': symbol,
                            'announcement_id': str(item.get('art_code') or ''),
                            'notice_date': notice_date,
                            'publication_time': publication_time,
                            'event_kind': kind,
                            'title': title,
                            'source_day': day,
                        })
                if page * 100 >= total_hits or not batch:
                    return {'day': day, 'ok': True, 'events': selected,
                            'total_hits': total_hits, 'pages': page, 'error': ''}
                page += 1
                time.sleep(0.05)
        except Exception as exc:
            if attempt == 2:
                return {'day': day, 'ok': False, 'events': [], 'total_hits': total_hits,
                        'pages': page, 'error': f'{type(exc).__name__}:{exc}'}
            time.sleep(attempt + 1)
    raise AssertionError('unreachable')


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding='utf-8'))
    return {'completed_days': {}, 'failed_days': {}}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    state = load_state()
    all_days = calendar_days()
    pending = [day for day in all_days if day not in state['completed_days']]
    if pending:
        with EVENTS.open('a', encoding='utf-8') as handle, ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(fetch_day, day): day for day in pending}
            for count, future in enumerate(as_completed(futures), 1):
                row = future.result()
                if row['ok']:
                    state['completed_days'][row['day']] = {
                        'total_hits': row['total_hits'], 'pages': row['pages'],
                        'event_count': len(row['events']),
                    }
                    state['failed_days'].pop(row['day'], None)
                    for event in row['events']:
                        handle.write(json.dumps(event, ensure_ascii=False) + '\n')
                else:
                    state['failed_days'][row['day']] = row['error']
                if count % 10 == 0:
                    handle.flush()
                    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
                    print(json.dumps({'completed': len(state['completed_days']), 'failed': len(state['failed_days']),
                                      'pending': len(pending) - count}, ensure_ascii=False), flush=True)
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

    canonical: dict[tuple[str, str], dict] = {}
    if EVENTS.exists():
        for line in EVENTS.open(encoding='utf-8'):
            try:
                event = json.loads(line)
                if event.get('announcement_id'):
                    canonical[(event['symbol'], event['announcement_id'])] = event
            except (ValueError, KeyError):
                continue
    events = list(canonical.values())
    years = ('2023', '2024', '2025')
    complete = len(state['completed_days']) == len(all_days) and not state['failed_days']
    report = {
        'version': 'V615_CONTROLLING_HOLDER_PLEDGE_PIT_EVENT_CATALOG_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source_contract': {
            'provider': 'Eastmoney public announcement metadata endpoint',
            'date_range': [START.isoformat(), END.isoformat()],
            'query': 'title=质押, then controlling-holder semantics only',
            'fields': ['symbol', 'announcement_id', 'notice_date', 'publication_time', 'title'],
            'event_kinds': ['CONTROLLING_HOLDER_PLEDGE_CREATE', 'CONTROLLING_HOLDER_PLEDGE_RELEASE'],
            'prohibited': ['price', 'volume', 'SMC seed', 'outcome', 'trade', 'PnL'],
            'same_day_execution_forbidden': True,
        },
        'coverage': {
            'calendar_days_expected': len(all_days), 'calendar_days_completed': len(state['completed_days']),
            'calendar_days_failed': len(state['failed_days']), 'all_days_complete': complete,
        },
        'events': {
            'canonical_count': len(events),
            'by_year': {year: sum(event['notice_date'].startswith(year) for event in events) for year in years},
            'by_kind': {kind: sum(event['event_kind'] == kind for event in events) for kind in (
                'CONTROLLING_HOLDER_PLEDGE_CREATE', 'CONTROLLING_HOLDER_PLEDGE_RELEASE')},
            'unique_symbols': len({event['symbol'] for event in events}),
            'timestamp_complete_events': sum(bool(event['notice_date'] and event['publication_time']) for event in events),
        },
        'decision': ('SOURCE_CATALOG_COMPLETE__SEMANTIC_PREREGISTRATION_NEXT'
                     if complete else 'SOURCE_CATALOG_IN_PROGRESS__NO_STRATEGY_OR_OUTCOME_AUTHORIZED'),
        'artifacts': {'out_dir': str(OUT), 'events': str(EVENTS), 'state': str(STATE), 'latest': str(LATEST)},
    }
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
