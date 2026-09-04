#!/usr/bin/env python3
"""V643 resumable source-only body collector for V642's immutable cash-plan IDs."""
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
AUD, BASE = ROOT / 'smc_audit', ROOT / 'pit_cache' / 'v643_cash_distribution_terms_raw'
PREREG = AUD / 'v642_cash_distribution_terms_raw_source_qualification_preregistration.json'
METADATA = AUD / 'v609_cash_dividend_plan_event_catalog_no_outcome' / 'v609_events.jsonl'
LATEST = AUD / 'v643_cash_distribution_terms_raw_build_latest.json'
API, UA = 'https://np-cnotice-stock.eastmoney.com/api/content/ann', 'Mozilla/5.0'
YEARS = ('2023', '2024', '2025')


def denominator() -> list[dict]:
    rows = [json.loads(line) for line in METADATA.open(encoding='utf-8') if line.strip()]
    by_id = {}
    for row in rows:
        if row['notice_date'][:4] in YEARS:
            by_id.setdefault(row['announcement_id'], row)
    return sorted(by_id.values(), key=lambda row: (row['publication_time'], row['announcement_id']))


def output(event: dict) -> Path:
    return BASE / event['notice_date'][:4] / f"{event['announcement_id']}.json.gz"


def failure(event: dict) -> Path:
    return BASE / 'failures' / event['notice_date'][:4] / f"{event['announcement_id']}.json.gz"


def good(event: dict) -> bool:
    try:
        with gzip.open(output(event), 'rt', encoding='utf-8') as h:
            doc = json.load(h)
        return doc.get('announcement_id') == event['announcement_id'] and doc.get('payload_art_code') == event['announcement_id'] and doc.get('publication_time', '')[:19] == event['publication_time'][:19] and bool(doc.get('notice_content'))
    except (OSError, ValueError, TypeError):
        return False


def fetch(event: dict) -> tuple[dict, str]:
    issue = ''
    for attempt in range(3):
        try:
            client = requests.Session(); client.trust_env = False
            r = client.get(API, params={'art_code': event['announcement_id'], 'client_source': 'web', 'page_index': 1}, headers={'User-Agent': UA}, timeout=30)
            r.raise_for_status(); payload = r.json().get('data') or {}
            if str(payload.get('art_code') or '') != event['announcement_id']:
                raise RuntimeError('PAYLOAD_ID_MISMATCH')
            if str(payload.get('eitime') or '')[:19] != event['publication_time'][:19]:
                raise RuntimeError('PAYLOAD_TIMESTAMP_MISMATCH')
            content = str(payload.get('notice_content') or '')
            if not content:
                raise RuntimeError('EMPTY_INLINE_PAYLOAD__OFFICIAL_PDF_RECOVERY_REQUIRED')
            return {'source': 'eastmoney_announcement_payload', 'source_kind': 'provider_raw_inline', 'announcement_id': event['announcement_id'], 'metadata_symbol': event['symbol'], 'notice_date': event['notice_date'], 'publication_time': event['publication_time'], 'payload_art_code': str(payload['art_code']), 'payload_publication_time': str(payload['eitime']), 'notice_title': str(payload.get('notice_title') or ''), 'notice_content': content, 'content_sha256': hashlib.sha256(content.encode()).hexdigest(), 'provider_timestamp': datetime.now().isoformat(timespec='seconds'), 'publication_timing_contract': 'Use only after a later completed exchange session; same-date use forbidden.'}, ''
        except Exception as exc:
            issue = f'{type(exc).__name__}:{exc}'
            time.sleep(.4 * (attempt + 1))
    return {}, issue


def save(path: Path, body: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); temp = path.with_suffix('.tmp')
    with gzip.open(temp, 'wt', encoding='utf-8') as h:
        json.dump(body, h, ensure_ascii=False, separators=(',', ':'))
    temp.replace(path)


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument('--limit', type=int, default=1000); ap.add_argument('--workers', type=int, default=8); args = ap.parse_args()
    prereg = json.loads(PREREG.read_text())
    if prereg['decision'] != 'SOURCE_ONLY_RAW_PAYLOAD_COLLECTION_AND_COVERAGE_AUDIT_AUTHORIZED__NO_MARKET_DATA':
        raise RuntimeError('V642 source-only authorization missing')
    rows = denominator(); pending = [x for x in rows if not good(x)][:args.limit]
    ok, bad, errors = 0, 0, []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch, event): event for event in pending}
        for n, future in enumerate(as_completed(futures), 1):
            event = futures[future]; doc, err = future.result()
            if doc:
                save(output(event), doc); ok += 1
            else:
                save(failure(event), {'announcement_id': event['announcement_id'], 'notice_date': event['notice_date'], 'publication_time': event['publication_time'], 'error': err, 'status': 'UNRESOLVED_SOURCE_FETCH_FAILURE'}); bad += 1; errors.append({'announcement_id': event['announcement_id'], 'error': err})
            if n % 100 == 0:
                print(f'PROGRESS {n}/{len(pending)} ok={ok} failed={bad}', flush=True)
    committed = {year: sum(good(x) for x in rows if x['notice_date'].startswith(year)) for year in YEARS}
    unresolved = {year: sum(not good(x) for x in rows if x['notice_date'].startswith(year)) for year in YEARS}
    report = {'version': 'V643_CASH_DISTRIBUTION_TERMS_RAW_BUILD_NO_OUTCOME', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False, 'scope': 'V642 raw source collection only; market/OHLCV, semantic extraction, seeds, outcomes, trades, PnL, stops and targets prohibited.', 'denominator': {'unique_announcement_ids': len(rows), 'by_year': {y: sum(x['notice_date'].startswith(y) for x in rows) for y in YEARS}}, 'batch': {'requested': len(pending), 'fetched': ok, 'failed': bad, 'errors': errors[:20]}, 'committed_valid_by_year': committed, 'unresolved_by_year': unresolved, 'decision': 'SOURCE_BUILD_IN_PROGRESS' if any(unresolved.values()) else 'SOURCE_BUILD_COMPLETE__FULL_COVERAGE_AUDIT_REQUIRED_BEFORE_ANY_SEMANTIC_CONTRACT'}
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2)); print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
