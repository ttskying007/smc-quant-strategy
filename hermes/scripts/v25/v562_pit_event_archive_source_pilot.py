#!/usr/bin/env python3
"""V562 no-outcome source qualification pilot for PIT corporate-event research.

This checks whether Eastmoney's public announcement metadata can be used as an
independent, timestamped event source. It deliberately does not load prices,
SMC candidates, trade outcomes, or shareholder values.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
MAPPING = AUDIT / 'v399_pit_shareholder_holdings_feasibility_no_write_20260712_194542' / 'v399_fixed_identity_pit_holder_mapping.csv'
OUT = AUDIT / f'v562_pit_event_archive_source_pilot_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v562_pit_event_archive_source_pilot_latest.json'
API = 'https://np-anotice-stock.eastmoney.com/api/security/ann'
WORKERS = 4
PAGES_MAX = 6
START = '2023-01-01'
END = '2026-07-23'

# Immutable before collection: only metadata title + publication timestamp is read.
EVENT_PATTERNS = {
    'BUYBACK': re.compile(r'回购'),
    'HOLDER_INCREASE': re.compile(r'增持'),
    'HOLDER_DECREASE': re.compile(r'减持'),
    'EARNINGS_PREANNOUNCEMENT': re.compile(r'业绩(?:预告|快报)'),
    'LOCKUP': re.compile(r'(?:限售股|解除限售|解禁)'),
}


def prefix(symbol: str) -> str:
    code = symbol[:6]
    if code.startswith(('000', '001')):
        return 'SZ_MAIN'
    if code.startswith(('002', '003')):
        return 'SZ_SME'
    if code.startswith(('300', '301')):
        return 'SZ_CHINEXT'
    if code.startswith('688'):
        return 'SH_STAR'
    if code.startswith(('600', '601', '603', '605')):
        return 'SH_MAIN'
    if code.startswith(('4', '8', '9')):
        return 'BJ'
    return 'OTHER'


def symbols_by_stratum() -> dict[str, list[str]]:
    rows = list(csv.DictReader(MAPPING.open(encoding='utf-8-sig')))
    universe = sorted({r['symbol'] for r in rows if r.get('symbol')})
    strata: dict[str, list[str]] = {}
    for symbol in universe:
        strata.setdefault(prefix(symbol), []).append(symbol)
    # Deterministic stratified sample: up to 20 each market board, enough to
    # expose endpoint/schema differences without reading any market outcome.
    selected: dict[str, list[str]] = {}
    for group, values in sorted(strata.items()):
        ordered = sorted(values, key=lambda s: hashlib.sha256(('V562|' + s).encode()).hexdigest())
        selected[group] = ordered[:20]
    return selected


def event_type(title: str) -> str | None:
    for name, pattern in EVENT_PATTERNS.items():
        if pattern.search(title):
            return name
    return None


def fetch_symbol(symbol: str) -> dict:
    notices: list[dict] = []
    session = requests.Session()
    for page in range(1, PAGES_MAX + 1):
        params = {
            'client_source': 'web', 'page_size': 100, 'page_index': page,
            'ann_type': 'A', 'stock_list': symbol[:6],
            'begin_time': START, 'end_time': END,
        }
        payload = None
        error = ''
        for attempt in range(3):
            try:
                response = session.get(API, params=params, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
                payload = response.json()
                if payload.get('success') != 1:
                    raise ValueError(f"api_success={payload.get('success')}")
                break
            except Exception as exc:
                error = f'{type(exc).__name__}: {exc}'
                payload = None
                time.sleep(0.75 * (attempt + 1))
        if payload is None:
            return {'symbol': symbol, 'ok': False, 'error': error, 'events': []}
        data = payload.get('data') or {}
        items = data.get('list') or []
        notices.extend(items)
        if page * 100 >= int(data.get('total_hits') or 0) or not items:
            break
        time.sleep(0.12)

    events = []
    for item in notices:
        title = str(item.get('title') or '')
        kind = event_type(title)
        if kind:
            events.append({
                'kind': kind,
                'announcement_id': str(item.get('art_code') or ''),
                'notice_date': str(item.get('notice_date') or ''),
                'publication_time': str(item.get('eiTime') or ''),
                'title': title,
            })
    return {'symbol': symbol, 'ok': True, 'error': '', 'events': events}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    strata = symbols_by_stratum()
    sample = [symbol for values in strata.values() for symbol in values]
    rows = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(fetch_symbol, symbol) for symbol in sample]
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda r: r['symbol'])

    success = [r for r in rows if r['ok']]
    events = [e for r in success for e in r['events']]
    by_kind = {kind: sum(e['kind'] == kind for e in events) for kind in EVENT_PATTERNS}
    timestamped = [e for e in events if e['notice_date'] and e['publication_time']]
    # A given disclosure timestamp is required; same-day execution is explicitly
    # out of scope because any future research event would enter no earlier than
    # the following trading day.
    report = {
        'version': 'V562_PIT_EVENT_ARCHIVE_SOURCE_PILOT_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'purpose': 'Qualify independent PIT corporate-event metadata before defining any event-to-SMC ontology.',
        'source_contract': {
            'provider': 'Eastmoney public announcement metadata endpoint',
            'range': [START, END],
            'fields_read': ['symbol', 'announcement_id', 'title', 'notice_date', 'publication_time'],
            'fields_prohibited': ['price', 'volume', 'SMC seed', 'trade outcome', 'holder value'],
            'same_day_execution_forbidden': True,
        },
        'sample': {
            'strata': {k: len(v) for k, v in strata.items()},
            'symbols_requested': len(sample),
            'http_ok': len(success),
            'http_ok_pct': round(100 * len(success) / len(sample), 2) if sample else 0,
            'classified_events': len(events),
            'timestamp_complete_events': len(timestamped),
            'by_kind': by_kind,
        },
        'qualification_contract': {
            'pilot_transport_pass': 'http_ok_pct>=95 and timestamp_complete_events>0 in every represented stratum',
            'full_archive_next': 'Only if pilot transport passes; then download all canonical symbols and measure annual symbol-date coverage before outcomes.',
            'event_ontology_forbidden_before_full_coverage': True,
        },
        'invariants': {
            'no_price_or_outcome_fields_read': True,
            'no_production_write': True,
            'no_frontend_write': True,
            'no_watchlist_write': True,
        },
        'artifacts': {'out_dir': str(OUT), 'events': str(OUT / 'v562_sample_events.json'), 'latest': str(LATEST)},
    }
    represented = {prefix(r['symbol']) for r in success}
    complete_by_stratum = {
        group: any(prefix(r['symbol']) == group and any(e['notice_date'] and e['publication_time'] for e in r['events']) for r in success)
        for group in strata
    }
    passed = (report['sample']['http_ok_pct'] >= 95.0 and all(complete_by_stratum.get(g, False) for g in represented))
    report['sample']['timestamp_complete_by_stratum'] = complete_by_stratum
    report['decision'] = 'PILOT_SOURCE_TRANSPORT_PASS__FULL_COVERAGE_AUDIT_NEXT' if passed else 'PILOT_SOURCE_TRANSPORT_OR_SCHEMA_FAIL__STOP'
    (OUT / 'v562_sample_events.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v562_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
