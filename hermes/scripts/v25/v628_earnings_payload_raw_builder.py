#!/usr/bin/env python3
"""V628 resumable source-only builder for PIT earnings-preannouncement payloads.

It consumes only the pre-existing timestamped announcement metadata archive and
Eastmoney's announcement-payload endpoint. No OHLCV, signal, trade, outcome,
PnL, stop, target, or replay artifact is read.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
ARCHIVE = AUD / 'v563_pit_event_archive_full_coverage_no_outcome_20260724_124935' / 'v563_event_metadata.jsonl'
BASE = ROOT / 'pit_cache' / 'v628_earnings_payload_raw'
LATEST = AUD / 'v628_earnings_payload_raw_build_latest.json'
API = 'https://np-cnotice-stock.eastmoney.com/api/content/ann'
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122 Safari/537.36'
YEARS = {'2023', '2024', '2025'}


def events() -> list[dict]:
    rows = [json.loads(line) for line in ARCHIVE.open(encoding='utf-8') if line.strip()]
    selected = [row for row in rows if row.get('kind') == 'EARNINGS_PREANNOUNCEMENT' and row.get('notice_date', '')[:4] in YEARS and row.get('announcement_id')]
    return sorted({row['announcement_id']: row for row in selected}.values(), key=lambda row: (row['notice_date'], row['announcement_id']))


def path(event: dict) -> Path:
    return BASE / event['notice_date'][:4] / f"{event['announcement_id']}.json.gz"


def failure_path(event: dict) -> Path:
    return BASE / 'failures' / event['notice_date'][:4] / f"{event['announcement_id']}.json.gz"


def valid(event: dict) -> bool:
    try:
        with gzip.open(path(event), 'rt', encoding='utf-8') as handle:
            doc = json.load(handle)
        return (
            doc.get('source') == 'eastmoney_announcement_payload'
            and doc.get('announcement_id') == event['announcement_id']
            and doc.get('payload_art_code') == event['announcement_id']
            and doc.get('publication_time') == event['publication_time']
            and bool(doc.get('notice_content'))
        )
    except (OSError, ValueError, TypeError):
        return False


def terminal_failure(event: dict) -> bool:
    try:
        with gzip.open(failure_path(event), 'rt', encoding='utf-8') as handle:
            doc = json.load(handle)
        return doc.get('announcement_id') == event['announcement_id'] and bool(doc.get('error'))
    except (OSError, ValueError, TypeError):
        return False


def fetch(event: dict) -> tuple[dict, str]:
    error = ''
    for attempt in range(1, 4):
        try:
            # Payload provider is directly reachable; bypass a flaky inherited
            # proxy so a transient proxy outage cannot be recorded as provider
            # source absence.
            session = requests.Session()
            session.trust_env = False
            response = session.get(API, params={'art_code': event['announcement_id'], 'client_source': 'web', 'page_index': 1}, headers={'User-Agent': UA}, timeout=30)
            response.raise_for_status()
            payload = response.json().get('data') or {}
            content = str(payload.get('notice_content') or '')
            if str(payload.get('art_code') or '') != event['announcement_id']:
                raise RuntimeError('PAYLOAD_ID_MISMATCH')
            if str(payload.get('eitime') or '')[:19] != str(event['publication_time'] or '')[:19]:
                raise RuntimeError('PAYLOAD_TIMESTAMP_MISMATCH')
            if not content:
                raise RuntimeError('EMPTY_PAYLOAD')
            doc = {
                'source': 'eastmoney_announcement_payload', 'source_kind': 'provider_raw',
                'announcement_id': event['announcement_id'], 'symbol': event['symbol'],
                'notice_date': event['notice_date'], 'publication_time': event['publication_time'],
                'payload_art_code': str(payload.get('art_code') or ''), 'payload_publication_time': str(payload.get('eitime') or ''),
                'notice_title': str(payload.get('notice_title') or ''), 'notice_content': content,
                'content_sha256': hashlib.sha256(content.encode()).hexdigest(),
                'provider_timestamp': datetime.now().isoformat(timespec='seconds'),
                'publication_timing_contract': 'Payload may only inform a decision after a later completed exchange session; same-date use is forbidden.',
            }
            return doc, ''
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
            if attempt < 3:
                time.sleep(0.5 * attempt)
    return {}, error


def store(event: dict, doc: dict) -> None:
    out = path(event); out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix('.tmp')
    with gzip.open(tmp, 'wt', encoding='utf-8') as handle:
        json.dump(doc, handle, ensure_ascii=False, separators=(',', ':'))
    tmp.replace(out)


def store_failure(event: dict, error: str) -> None:
    out = failure_path(event); out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix('.tmp')
    doc = {'source': 'eastmoney_announcement_payload', 'announcement_id': event['announcement_id'], 'symbol': event['symbol'],
           'notice_date': event['notice_date'], 'publication_time': event['publication_time'], 'error': error,
           'provider_timestamp': datetime.now().isoformat(timespec='seconds'), 'status': 'PAYLOAD_UNAVAILABLE__SOURCE_COVERAGE_FAIL'}
    with gzip.open(tmp, 'wt', encoding='utf-8') as handle:
        json.dump(doc, handle, ensure_ascii=False, separators=(',', ':'))
    tmp.replace(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=200)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--pause', type=float, default=0.06)
    args = parser.parse_args()
    denominator = events()
    pending = [event for event in denominator if not valid(event) and not terminal_failure(event)]
    batch = pending[:max(1, args.limit)]
    done = failed = 0
    errors = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fetch, event): event for event in batch}
        for index, future in enumerate(as_completed(futures), 1):
            event = futures[future]
            doc, error = future.result()
            if error:
                failed += 1
                errors.append({'announcement_id': event['announcement_id'], 'year': event['notice_date'][:4], 'error': error})
                store_failure(event, error)
            else:
                store(event, doc); done += 1
            if args.pause:
                time.sleep(args.pause)
            if index % 50 == 0:
                print(f'PROGRESS {index}/{len(batch)} ok={done} failed={failed}', flush=True)
    remaining = len(pending) - done - failed
    yearly = {year: sum(valid(event) for event in denominator if event['notice_date'].startswith(year)) for year in sorted(YEARS)}
    terminal_failures = {year: sum(terminal_failure(event) for event in denominator if event['notice_date'].startswith(year)) for year in sorted(YEARS)}
    report = {
        'version': 'V628_EARNINGS_PAYLOAD_RAW_BUILD_NO_OUTCOME', 'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'contract': 'Source-only raw PIT payload build from timestamped announcement identifiers. Market/OHLCV, seeds, trades, outcomes, PnL, stops and targets are prohibited.',
        'denominator': {'events': len(denominator), 'by_year': {year: sum(event['notice_date'].startswith(year) for event in denominator) for year in sorted(YEARS)}, 'metadata_archive': str(ARCHIVE)},
        'batch': {'pending_before': len(pending), 'requested': len(batch), 'completed': done, 'new_terminal_failures': failed, 'remaining_estimate': remaining, 'errors': errors[:20]},
        'committed_valid_by_year': yearly,
        'terminal_source_failures_by_year': terminal_failures,
        'decision': ('SOURCE_BUILD_IN_PROGRESS' if remaining else
                     ('SOURCE_BUILD_COMPLETE__REQUIRES_FULL_COVERAGE_PIT_AND_SEMANTIC_CATALOG_AUDIT_BEFORE_ANY_ONTOLOGY'
                      if not sum(terminal_failures.values()) else 'SOURCE_BUILD_COMPLETE_WITH_SOURCE_FAILURES__NO_ONTOLOGY')),
    }
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
