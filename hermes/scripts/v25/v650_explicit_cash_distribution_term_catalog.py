#!/usr/bin/env python3
"""V650 primary bounded-clause extractor for V649's source-only cash term."""
from __future__ import annotations

import csv
import gzip
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
CACHE = ROOT / 'pit_cache' / 'v643_cash_distribution_terms_raw'
CONTRACT = AUD / 'v649_annual_cash_distribution_explicit_cash_term_semantic_contract.json'
OUT = AUD / f'v650_explicit_cash_distribution_term_catalog_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v650_explicit_cash_distribution_term_catalog_latest.json'
YEARS = ('2023', '2024', '2025')
ANCHOR = re.compile(r'利润分配(?:预案|方案)')
CASH = re.compile(r'向全体股东每10股派发现金(?:红利|股利)(?:人民币)?([0-9]+(?:\.[0-9]+)?)元')


def docs() -> list[dict]:
    rows = []
    for path in CACHE.glob('[0-9][0-9][0-9][0-9]/AN*.json.gz'):
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            row = json.load(handle)
        if row['notice_date'][:4] in YEARS:
            rows.append(row)
    return rows


def candidate_matches(text: str) -> list[re.Match[str]]:
    spans = [(match.start(), min(len(text), match.start() + 800)) for match in ANCHOR.finditer(text)]
    return [match for match in CASH.finditer(text) if any(start <= match.start() < end for start, end in spans)]


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    if contract['decision'] != 'SOURCE_ONLY_EXPLICIT_CASH_TERM_CATALOG_AND_INDEPENDENT_ORACLE_AUTHORIZED__NO_MARKET_DATA':
        raise RuntimeError('V649 authorization missing')
    all_rows, accepted = [], []
    for doc in docs():
        text = re.sub(r'\s+', '', str(doc['notice_content']))
        title = str(doc.get('notice_title') or '')
        matches = candidate_matches(text)
        values = {match.group(1) for match in matches if float(match.group(1)) > 0}
        decision = 'REJECT_NO_EXPLICIT_CASH_CLAUSE'
        if '业绩快报' in title:
            decision = 'REJECT_EARNINGS_FLASH'
        elif CASH.search(text) and not matches:
            decision = 'REJECT_CASH_CLAUSE_OUTSIDE_BOUNDED_PROPOSAL_CLAUSE'
        elif matches and any(float(match.group(1)) <= 0 for match in matches):
            decision = 'REJECT_NONPOSITIVE_CASH_VALUE'
        elif len(values) > 1:
            decision = 'REJECT_INCOMPATIBLE_MULTIPLE_CASH_VALUES'
        elif len(values) == 1:
            match = matches[0]
            value = match.group(1)
            tax = '含税' if '含税' in text[match.end():match.end() + 16] else ''
            accepted.append({
                'symbol': doc['metadata_symbol'], 'announcement_id': doc['announcement_id'],
                'notice_date': doc['notice_date'], 'publication_time': doc['publication_time'],
                'notice_title': title, 'content_sha256': doc['content_sha256'],
                'proposal_anchor': ANCHOR.search(text).group(0),
                'matched_clause': text[max(0, match.start() - 120):min(len(text), match.end() + 120)],
                'cash_per_10_shares_cny': value, 'tax_wording': tax,
                'availability_rule': 'later_completed_exchange_session_only',
            })
            decision = 'ACCEPT_EXPLICIT_CASH_TERM'
        all_rows.append({'announcement_id': doc['announcement_id'], 'symbol': doc['metadata_symbol'], 'notice_date': doc['notice_date'], 'decision': decision, 'match_count': len(matches), 'values': '|'.join(sorted(values))})
    groups = defaultdict(list)
    for row in accepted:
        groups[(row['symbol'], row['notice_date'])].append(row)
    canonical = []
    for group in groups.values():
        group.sort(key=lambda row: row['announcement_id'])
        item = group[0].copy()
        item['duplicate_announcement_ids'] = '|'.join(row['announcement_id'] for row in group)
        canonical.append(item)
    canonical.sort(key=lambda row: (row['publication_time'], row['announcement_id']))
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / 'v650_all_document_decisions.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_rows[0])); writer.writeheader(); writer.writerows(all_rows)
    fields = list(canonical[0]) if canonical else ['announcement_id']
    with (OUT / 'v650_canonical_explicit_cash_terms.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(canonical)
    by_year = Counter(row['notice_date'][:4] for row in canonical)
    gate = contract['support_gate_before_any_later_ontology']
    passed = len(canonical) >= gate['canonical_observations_total_min'] and len({row['symbol'] for row in canonical}) >= gate['unique_symbols_min'] and all(by_year[year] >= gate['canonical_observations_each_year_min'] for year in YEARS)
    report = {
        'version': 'V650_EXPLICIT_CASH_DISTRIBUTION_TERM_CATALOG_NO_OUTCOME', 'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'Primary source-only parser under V649. No market/OHLCV, SMC, seed, trade, outcome, PnL, stop or target was read.',
        'contract': str(CONTRACT), 'raw_documents_read': len(all_rows),
        'decision_counts': dict(Counter(row['decision'] for row in all_rows)),
        'canonical_observations': len(canonical), 'canonical_by_year': {year: by_year[year] for year in YEARS}, 'unique_symbols': len({row['symbol'] for row in canonical}),
        'support_gate': {**gate, 'pass': passed},
        'artifacts': {'dir': str(OUT), 'all_document_decisions': str(OUT / 'v650_all_document_decisions.csv'), 'canonical_terms': str(OUT / 'v650_canonical_explicit_cash_terms.csv')},
        'decision': 'PRIMARY_CATALOG_READY_FOR_INDEPENDENT_ORACLE' if passed else 'SUPPORT_FAIL__CLOSE_EXPLICIT_CASH_TERM_OBJECT_NO_ORACLE_OR_MARKET_DATA',
    }
    (OUT / 'v650_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
