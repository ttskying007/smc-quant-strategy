#!/usr/bin/env python3
"""V632 source-only catalog for the preregistered positive-preannouncement field."""
from __future__ import annotations

import csv
import gzip
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
CACHE = ROOT / 'pit_cache' / 'v628_earnings_payload_raw'
PREREG = AUD / 'v631_positive_earnings_preannouncement_semantic_catalog_preregistration.json'
OUT = AUD / f'v632_positive_earnings_preannouncement_semantic_catalog_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v632_positive_earnings_preannouncement_semantic_catalog_latest.json'
YEARS = ('2023', '2024', '2025')
PATTERN = re.compile(r'业绩预告情况.{0,20}?预计净利润为正值')


def documents() -> list[dict]:
    rows = []
    for path in CACHE.glob('[0-9][0-9][0-9][0-9]/AN*.json.gz'):
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            doc = json.load(handle)
        if doc.get('notice_date', '')[:4] in YEARS:
            rows.append(doc)
    return rows


def main() -> None:
    prereg = json.loads(PREREG.read_text())
    assert prereg['decision'] == 'SEMANTIC_CATALOG_EXTRACTION_AUTHORIZED__SOURCE_ONLY_NO_MARKET_DATA'
    docs = documents()
    selected = []
    for doc in docs:
        normalized = re.sub(r'\s+', '', str(doc.get('notice_content') or ''))
        title = str(doc.get('notice_title') or '')
        if '业绩快报' in title:
            continue
        if PATTERN.search(normalized):
            selected.append({
                'symbol': doc['symbol'], 'announcement_id': doc['announcement_id'],
                'notice_date': doc['notice_date'], 'publication_time': doc['publication_time'],
                'notice_title': title, 'content_sha256': doc['content_sha256'],
                'semantic_label': 'POSITIVE_EARNINGS_PREANNOUNCEMENT_EXPLICIT_CURRENT_PERIOD',
                'availability_rule': 'later_completed_exchange_session_only',
            })
    selected.sort(key=lambda row: (row['publication_time'], row['announcement_id']))
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / 'v632_positive_preannouncement_events.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(selected[0]) if selected else ['symbol'])
        writer.writeheader(); writer.writerows(selected)
    by_year = Counter(row['notice_date'][:4] for row in selected)
    symbols = len({row['symbol'] for row in selected})
    gate = prereg['support_gate_before_any_ontology']
    passed = len(selected) >= gate['canonical_events_total_min'] and all(by_year[year] >= gate['canonical_events_each_year_min'] for year in YEARS) and symbols >= gate['unique_symbols_min']
    report = {
        'version': 'V632_POSITIVE_EARNINGS_PREANNOUNCEMENT_SEMANTIC_CATALOG_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'Preregistered announcement-body semantic extraction only. No market/OHLCV, signal, seed, trade, outcome, PnL, stop, target or replay file was read.',
        'preregistration': str(PREREG), 'raw_documents_read': len(docs),
        'semantic_rule': prereg['semantic_rule'],
        'canonical_events': len(selected), 'events_by_year': {year: by_year[year] for year in YEARS}, 'unique_symbols': symbols,
        'support_gate': {**gate, 'pass': passed},
        'decision': 'SUPPORT_PASS__SEPARATE_CAUSAL_ONTOLOGY_PREREGISTRATION_REQUIRED_BEFORE_MARKET_DATA' if passed else 'SUPPORT_FAIL__CLOSE_POSITIVE_EARNINGS_PREANNOUNCEMENT_SEMANTIC_OBJECT_NO_ONTOLOGY',
        'artifacts': {'dir': str(OUT), 'events': str(OUT / 'v632_positive_preannouncement_events.csv')},
    }
    (OUT / 'v632_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
