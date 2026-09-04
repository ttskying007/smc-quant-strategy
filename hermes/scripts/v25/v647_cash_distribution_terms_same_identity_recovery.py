#!/usr/bin/env python3
"""V647: recover unresolved V643 records only from their own official payload/PDF."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
BASE = ROOT / 'pit_cache' / 'v643_cash_distribution_terms_raw'
META = AUD / 'v609_cash_dividend_plan_event_catalog_no_outcome' / 'v609_events.jsonl'
BUILD = AUD / 'v643_cash_distribution_terms_raw_build_latest.json'
OUT = AUD / 'v647_cash_distribution_terms_same_identity_recovery_no_outcome.json'
API = 'https://np-cnotice-stock.eastmoney.com/api/content/ann'
UA = 'Mozilla/5.0'


def destination(row: dict) -> Path:
    return BASE / row['notice_date'][:4] / f"{row['announcement_id']}.json.gz"


def valid(row: dict) -> bool:
    try:
        with gzip.open(destination(row), 'rt', encoding='utf-8') as handle:
            doc = json.load(handle)
        return (
            doc['announcement_id'] == row['announcement_id']
            and doc['payload_art_code'] == row['announcement_id']
            and doc['publication_time'][:19] == row['publication_time'][:19]
            and bool(doc['notice_content'])
        )
    except (OSError, KeyError, TypeError, ValueError):
        return False


def save(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    with gzip.open(temp, 'wt', encoding='utf-8') as handle:
        json.dump(doc, handle, ensure_ascii=False, separators=(',', ':'))
    temp.replace(path)


def fetch(row: dict) -> tuple[dict | None, str]:
    last = ''
    for attempt in range(8):
        try:
            client = requests.Session()
            client.trust_env = False
            response = client.get(
                API,
                params={'art_code': row['announcement_id'], 'client_source': 'web', 'page_index': 1},
                headers={'User-Agent': UA}, timeout=45,
            )
            response.raise_for_status()
            payload = response.json().get('data') or {}
            if str(payload.get('art_code') or '') != row['announcement_id']:
                raise RuntimeError('PAYLOAD_ID_MISMATCH')
            if str(payload.get('eitime') or '')[:19] != row['publication_time'][:19]:
                raise RuntimeError('PAYLOAD_TIMESTAMP_MISMATCH')
            content = str(payload.get('notice_content') or '')
            attachment_url = ''
            attachment_hash = ''
            kind = 'provider_raw_inline'
            if not content:
                attachment_url = str(payload.get('attach_url_web') or payload.get('attach_url') or '')
                if not attachment_url:
                    raise RuntimeError('EMPTY_INLINE_NO_OFFICIAL_ATTACHMENT')
                pdf = client.get(attachment_url, headers={'User-Agent': UA}, timeout=90)
                pdf.raise_for_status()
                if not pdf.content.startswith(b'%PDF'):
                    raise RuntimeError('OFFICIAL_ATTACHMENT_NOT_PDF')
                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as source:
                    source.write(pdf.content)
                    pdf_path = source.name
                text_path = f'{pdf_path}.txt'
                try:
                    result = subprocess.run(['pdftotext', pdf_path, text_path], capture_output=True, text=True, timeout=90)
                    content = Path(text_path).read_text(encoding='utf-8', errors='replace') if result.returncode == 0 else ''
                finally:
                    for path in (pdf_path, text_path):
                        try:
                            os.unlink(path)
                        except FileNotFoundError:
                            pass
                if not content.strip():
                    raise RuntimeError('OFFICIAL_ATTACHMENT_TEXT_EMPTY')
                attachment_hash = hashlib.sha256(pdf.content).hexdigest()
                kind = 'provider_raw_official_pdf_attachment'
            return {
                'source': 'eastmoney_announcement_payload', 'source_kind': kind,
                'announcement_id': row['announcement_id'], 'metadata_symbol': row['symbol'],
                'notice_date': row['notice_date'], 'publication_time': row['publication_time'],
                'payload_art_code': str(payload['art_code']), 'payload_publication_time': str(payload['eitime']),
                'notice_title': str(payload.get('notice_title') or ''), 'notice_content': content,
                'content_sha256': hashlib.sha256(content.encode()).hexdigest(),
                'attachment_url': attachment_url, 'attachment_sha256': attachment_hash,
                'provider_timestamp': datetime.now().isoformat(timespec='seconds'),
                'publication_timing_contract': 'Use only after a later completed exchange session; same-date use forbidden.',
            }, ''
        except Exception as exc:
            last = f'{type(exc).__name__}:{exc}'
            time.sleep(1.5 * (attempt + 1))
    return None, last


def main() -> None:
    rows_by_id = {}
    for line in META.open(encoding='utf-8'):
        if line.strip():
            row = json.loads(line)
            if row['notice_date'][:4] in {'2023', '2024', '2025'}:
                rows_by_id.setdefault(row['announcement_id'], row)
    pending = [row for row in rows_by_id.values() if not valid(row)]
    recovered, failures = [], []
    for row in sorted(pending, key=lambda item: (item['publication_time'], item['announcement_id'])):
        doc, error = fetch(row)
        if doc:
            save(destination(row), doc)
            recovered.append({'announcement_id': row['announcement_id'], 'transport': doc['source_kind']})
        else:
            failures.append({'announcement_id': row['announcement_id'], 'error': error})
    unresolved = [row['announcement_id'] for row in rows_by_id.values() if not valid(row)]
    report = {
        'version': 'V647_CASH_DISTRIBUTION_TERMS_SAME_IDENTITY_RECOVERY_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'Recovery only from each unresolved record\'s own official Eastmoney payload and, only for an empty inline payload, that exact payload\'s official attachment. No semantic fields or market data were read.',
        'lineage': {'preregistration': str(AUD / 'v642_cash_distribution_terms_raw_source_qualification_preregistration.json'), 'build': str(BUILD)},
        'requested': len(pending), 'recovered': recovered, 'failures': failures, 'unresolved_after': unresolved,
        'decision': 'RECOVERY_COMPLETE__INDEPENDENT_V642_COVERAGE_AUDIT_AUTHORIZED' if not unresolved else 'RECOVERY_INCOMPLETE__SOURCE_GATE_REMAINS_OPEN',
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
