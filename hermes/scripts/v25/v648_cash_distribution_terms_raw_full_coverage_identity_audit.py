#!/usr/bin/env python3
"""V648 independent source-only coverage/identity audit for V642/V643 cash-plan bodies."""
from __future__ import annotations

import gzip
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
BASE = ROOT / 'pit_cache' / 'v643_cash_distribution_terms_raw'
PREREG = AUD / 'v642_cash_distribution_terms_raw_source_qualification_preregistration.json'
RECOVERY = AUD / 'v647_cash_distribution_terms_same_identity_recovery_no_outcome.json'
OUT = AUD / 'v648_cash_distribution_terms_raw_full_coverage_identity_audit_no_outcome.json'
META = AUD / 'v609_cash_dividend_plan_event_catalog_no_outcome' / 'v609_events.jsonl'
YEARS = ('2023', '2024', '2025')


def event_map() -> dict[str, dict]:
    events: dict[str, dict] = {}
    for line in META.open(encoding='utf-8'):
        if line.strip():
            row = json.loads(line)
            if row['notice_date'][:4] in YEARS:
                events.setdefault(row['announcement_id'], row)
    return events


def raw_path(event: dict) -> Path:
    return BASE / event['notice_date'][:4] / f"{event['announcement_id']}.json.gz"


def read_doc(path: Path) -> dict:
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        return json.load(handle)


def audit(event: dict) -> tuple[bool, str, str]:
    path = raw_path(event)
    if not path.exists():
        return False, 'MISSING_RAW_PAYLOAD', ''
    try:
        doc = read_doc(path)
    except (OSError, ValueError, TypeError) as exc:
        return False, f'UNREADABLE_RAW_PAYLOAD:{type(exc).__name__}', ''
    if doc.get('announcement_id') != event['announcement_id']:
        return False, 'METADATA_ANNOUNCEMENT_ID_MISMATCH', ''
    if doc.get('payload_art_code') != event['announcement_id']:
        return False, 'PAYLOAD_ART_CODE_MISMATCH', ''
    if str(doc.get('publication_time') or '')[:19] != event['publication_time'][:19]:
        return False, 'METADATA_PUBLICATION_TIME_MISMATCH', ''
    if str(doc.get('payload_publication_time') or '')[:19] != event['publication_time'][:19]:
        return False, 'PAYLOAD_PUBLICATION_TIME_MISMATCH', ''
    if not str(doc.get('notice_content') or '').strip():
        return False, 'EMPTY_NOTICE_CONTENT', ''
    kind = str(doc.get('source_kind') or '')
    if kind not in {'provider_raw_inline', 'provider_raw_official_pdf_attachment'}:
        return False, 'UNRECOGNIZED_TRANSPORT', kind
    if kind == 'provider_raw_official_pdf_attachment' and (not doc.get('attachment_url') or not doc.get('attachment_sha256')):
        return False, 'OFFICIAL_ATTACHMENT_PROVENANCE_MISSING', kind
    return True, '', kind


def main() -> None:
    prereg = json.loads(PREREG.read_text())
    recovery = json.loads(RECOVERY.read_text())
    if prereg['decision'] != 'SOURCE_ONLY_RAW_PAYLOAD_COLLECTION_AND_COVERAGE_AUDIT_AUTHORIZED__NO_MARKET_DATA':
        raise RuntimeError('V642 authorization invalid')
    if recovery['decision'] != 'RECOVERY_COMPLETE__INDEPENDENT_V642_COVERAGE_AUDIT_AUTHORIZED':
        raise RuntimeError('V647 recovery incomplete')
    events = event_map()
    failures: list[dict] = []
    valid_by_year = Counter()
    transport = Counter()
    for event in events.values():
        ok, issue, kind = audit(event)
        if ok:
            valid_by_year[event['notice_date'][:4]] += 1
            transport[kind] += 1
        else:
            failures.append({'announcement_id': event['announcement_id'], 'year': event['notice_date'][:4], 'issue': issue})
    expected_ids = set(events)
    actual_ids = set()
    duplicate_or_invalid_paths = []
    for path in BASE.glob('[0-9][0-9][0-9][0-9]/AN*.json.gz'):
        actual_ids.add(path.name.removesuffix('.json.gz'))
        if path.parent.name not in YEARS:
            duplicate_or_invalid_paths.append(str(path))
    extra_raw_ids = sorted(actual_ids - expected_ids)
    per_year = {year: {'denominator': sum(event['notice_date'].startswith(year) for event in events.values()), 'valid': valid_by_year[year]} for year in YEARS}
    exact = not failures and not extra_raw_ids and not duplicate_or_invalid_paths and len(events) == prereg['metadata_denominator']['unique_announcement_ids']
    report = {
        'version': 'V648_CASH_DISTRIBUTION_TERMS_RAW_FULL_COVERAGE_IDENTITY_AUDIT_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'Independent raw-source coverage and identity audit only. No body-term parser, semantic catalog, market/OHLCV, SMC, seed, trade, outcome, PnL, stop or target was read.',
        'lineage': {'preregistration': str(PREREG), 'recovery': str(RECOVERY), 'raw_cache': str(BASE)},
        'unique_announcement_denominator': len(events), 'yearly': per_year,
        'transport_counts': dict(transport), 'failure_count': len(failures), 'failures': failures[:100],
        'raw_cache_extra_ids': extra_raw_ids[:100], 'unexpected_raw_paths': duplicate_or_invalid_paths[:100],
        'hard_gate': {'complete_unique_announcement_payload_coverage_required': True, 'yearly_coverage_required': 1.0, 'identity_mismatches_required': 0, 'unresolved_empty_payloads_required': 0, 'pass': exact},
        'decision': 'V642_SOURCE_GATE_PASS__SEPARATE_BODY_TERM_SEMANTIC_CONTRACT_AUTHORIZED__NO_MARKET_DATA' if exact else 'V642_SOURCE_GATE_FAIL__CLOSE_RAW_TERMS_OBJECT_NO_SEMANTIC_EXTRACTION_OR_MARKET_DATA',
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
