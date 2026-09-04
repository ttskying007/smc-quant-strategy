#!/usr/bin/env python3
"""V627 source-only pilot for timestamped earnings-preannouncement payloads.

This validates that an immutable announcement id can retrieve the disclosed
profit-direction text. It intentionally reads no market, OHLCV, seed, trade,
outcome, stop, target, or PnL data and does not define a strategy.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
ARCHIVE = AUD / 'v563_pit_event_archive_full_coverage_no_outcome_20260724_124935' / 'v563_event_metadata.jsonl'
OUT = AUD / f'v627_earnings_payload_pit_source_pilot_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v627_earnings_payload_pit_source_pilot_latest.json'
API = 'https://np-cnotice-stock.eastmoney.com/api/content/ann'
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122 Safari/537.36'
YEARS = ('2023', '2024', '2025')
PER_YEAR = 12


def declared_direction(content: str) -> str:
    """Only accept the notice's explicit current-period direction sentence."""
    normalized = re.sub(r'\s+', '', content)
    match = re.search(r'业绩预告情况[：:]预计净利润为(正值|负值)', normalized)
    if match:
        return 'POSITIVE' if match.group(1) == '正值' else 'NEGATIVE'
    match = re.search(r'业绩预告情况[：:]?[^。；]{0,160}?(盈利|亏损)', normalized)
    if match:
        return 'POSITIVE' if match.group(1) == '盈利' else 'NEGATIVE'
    return 'UNCLASSIFIED_EXPLICIT_RULE'


def sample(events: list[dict], year: str) -> list[dict]:
    candidates = [event for event in events if event['notice_date'][:4] == year]
    # Fixed source-only sampling, independent of text contents or any outcome.
    return sorted(candidates, key=lambda event: hashlib.sha256(event['announcement_id'].encode()).hexdigest())[:PER_YEAR]


def fetch(event: dict) -> dict:
    result = {key: event[key] for key in ('symbol', 'announcement_id', 'notice_date', 'publication_time', 'title')}
    try:
        response = requests.get(API, params={'art_code': event['announcement_id'], 'client_source': 'web', 'page_index': 1}, headers={'User-Agent': UA}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        data = payload.get('data') or {}
        content = str(data.get('notice_content') or '')
        received_time = str(data.get('eitime') or '')
        result.update({
            'http_status': response.status_code,
            'payload_art_code_matches': str(data.get('art_code') or '') == event['announcement_id'],
            'payload_publication_time_matches': bool(received_time) and received_time[:19] == event['publication_time'][:19],
            'content_chars': len(content),
            'explicit_direction': declared_direction(content),
            'content_sha256': hashlib.sha256(content.encode()).hexdigest(),
            'error': '',
        })
    except Exception as exc:
        result.update({'http_status': 0, 'payload_art_code_matches': False, 'payload_publication_time_matches': False, 'content_chars': 0, 'explicit_direction': 'FETCH_FAILED', 'content_sha256': '', 'error': f'{type(exc).__name__}: {exc}'})
    return result


def main() -> None:
    events = [json.loads(line) for line in ARCHIVE.open(encoding='utf-8') if line.strip()]
    events = [event for event in events if event.get('kind') == 'EARNINGS_PREANNOUNCEMENT' and event.get('notice_date', '')[:4] in YEARS and event.get('announcement_id')]
    rows = []
    for year in YEARS:
        for event in sample(events, year):
            rows.append(fetch(event))
            time.sleep(0.12)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / 'v627_payload_pilot_rows.jsonl').open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    counts = {state: sum(row['explicit_direction'] == state for row in rows) for state in ('POSITIVE', 'NEGATIVE', 'UNCLASSIFIED_EXPLICIT_RULE', 'FETCH_FAILED')}
    report = {
        'version': 'V627_EARNINGS_PAYLOAD_PIT_SOURCE_PILOT_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'Source-only transport, identity and payload-field pilot. No market/OHLCV, seed, trade, outcome, PnL, target or stop source was opened.',
        'source_contract': {
            'metadata_archive': str(ARCHIVE), 'payload_endpoint': API,
            'identity': 'announcement_id must equal payload art_code',
            'PIT_timestamp': 'payload eitime must equal metadata publication_time; any future ontology may act only after a later completed session',
            'direction_rule': 'Only explicit current-period 业绩预告情况 direction text is classified; title-only direction inference is forbidden.',
        },
        'sampling': {'years': list(YEARS), 'per_year': PER_YEAR, 'selection': 'SHA256(announcement_id) sorted, first N; independent of content and all market outcomes'},
        'results': {
            'requested': len(rows), 'http_ok': sum(row['http_status'] == 200 for row in rows),
            'identity_matches': sum(row['payload_art_code_matches'] for row in rows),
            'timestamp_matches': sum(row['payload_publication_time_matches'] for row in rows),
            'nonempty_payloads': sum(row['content_chars'] > 0 for row in rows), 'direction_counts': counts,
            'rows_by_year': {year: sum(row['notice_date'][:4] == year for row in rows) for year in YEARS},
            'transport_identity_and_timestamp_pass': all(row['http_status'] == 200 and row['payload_art_code_matches'] and row['payload_publication_time_matches'] and row['content_chars'] > 0 for row in rows),
        },
        'decision': 'PAYLOAD_SOURCE_PILOT_PASS__FULL_METADATA_ONLY_CATALOG_AND_PIT_COVERAGE_AUDIT_REQUIRED_BEFORE_ANY_OUTCOME_BLIND_ONTOLOGY' if all(row['http_status'] == 200 and row['payload_art_code_matches'] and row['payload_publication_time_matches'] and row['content_chars'] > 0 for row in rows) else 'PAYLOAD_SOURCE_PILOT_FAIL__NO_ONTOLOGY',
        'artifacts': {'dir': str(OUT), 'rows': str(OUT / 'v627_payload_pilot_rows.jsonl')},
    }
    (OUT / 'v627_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
