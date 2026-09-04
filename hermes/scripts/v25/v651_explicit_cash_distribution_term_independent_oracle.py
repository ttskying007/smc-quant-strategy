#!/usr/bin/env python3
"""V651 independent regex oracle for V649/V650 source-only cash-term catalog."""
from __future__ import annotations

import csv
import gzip
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
CACHE = ROOT / 'pit_cache' / 'v643_cash_distribution_terms_raw'
CONTRACT = AUD / 'v649_annual_cash_distribution_explicit_cash_term_semantic_contract.json'
PRIMARY = AUD / 'v650_explicit_cash_distribution_term_catalog_latest.json'
OUT = AUD / f'v651_explicit_cash_distribution_term_independent_oracle_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v651_explicit_cash_distribution_term_independent_oracle_latest.json'
YEARS = ('2023', '2024', '2025')
ANCHOR = re.compile(r'利润分配预案|利润分配方案')
CASH = re.compile(r'向全体股东每10股派发现金(?:红利|股利)(?:人民币)?(?P<amount>[0-9]+(?:\.[0-9]+)?)元')


def rows() -> list[dict]:
    result = []
    for path in CACHE.glob('[0-9][0-9][0-9][0-9]/AN*.json.gz'):
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            doc = json.load(handle)
        if doc['notice_date'][:4] in YEARS:
            result.append(doc)
    return result


def covered_by_anchor(text: str, position: int) -> bool:
    for anchor in ANCHOR.finditer(text):
        if anchor.start() <= position < anchor.start() + 800:
            return True
    return False


def oracle_accept(doc: dict) -> dict | None:
    text = ''.join(str(doc['notice_content']).split())
    title = str(doc.get('notice_title') or '')
    if '业绩快报' in title:
        return None
    amounts = []
    for match in CASH.finditer(text):
        if covered_by_anchor(text, match.start()):
            amount = match.group('amount')
            if float(amount) <= 0:
                return None
            amounts.append(amount)
    if len(set(amounts)) != 1:
        return None
    if not amounts:
        return None
    return {'symbol': doc['metadata_symbol'], 'announcement_id': doc['announcement_id'], 'notice_date': doc['notice_date'], 'publication_time': doc['publication_time'], 'cash_per_10_shares_cny': amounts[0]}


def primary_rows(path: Path) -> dict[str, str]:
    answer = {}
    with path.open(newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            answer[row['announcement_id']] = row['cash_per_10_shares_cny']
    return answer


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    primary = json.loads(PRIMARY.read_text())
    if contract['decision'] != 'SOURCE_ONLY_EXPLICIT_CASH_TERM_CATALOG_AND_INDEPENDENT_ORACLE_AUTHORIZED__NO_MARKET_DATA':
        raise RuntimeError('V649 contract missing')
    if primary['decision'] != 'PRIMARY_CATALOG_READY_FOR_INDEPENDENT_ORACLE':
        raise RuntimeError('V650 primary not ready')
    accepted = [row for doc in rows() if (row := oracle_accept(doc))]
    grouped = defaultdict(list)
    for row in accepted:
        grouped[(row['symbol'], row['notice_date'])].append(row)
    canonical = []
    for group in grouped.values():
        canonical.append(sorted(group, key=lambda row: row['announcement_id'])[0])
    canonical.sort(key=lambda row: (row['publication_time'], row['announcement_id']))
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / 'v651_oracle_canonical_terms.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(canonical[0]) if canonical else ['announcement_id'])
        writer.writeheader(); writer.writerows(canonical)
    primary_map = primary_rows(Path(primary['artifacts']['canonical_terms']))
    oracle_map = {row['announcement_id']: row['cash_per_10_shares_cny'] for row in canonical}
    missing = sorted(set(primary_map) - set(oracle_map))
    extra = sorted(set(oracle_map) - set(primary_map))
    values = [{'announcement_id': key, 'primary': primary_map[key], 'oracle': oracle_map[key]} for key in sorted(set(primary_map) & set(oracle_map)) if primary_map[key] != oracle_map[key]]
    report = {
        'version': 'V651_EXPLICIT_CASH_DISTRIBUTION_TERM_INDEPENDENT_ORACLE_NO_OUTCOME', 'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'Independent source-only regular-expression oracle. No market/OHLCV, SMC, seed, trade, outcome, PnL, stop or target was read.',
        'lineage': {'contract': str(CONTRACT), 'primary': str(PRIMARY)},
        'oracle_canonical_count': len(canonical), 'primary_canonical_count': len(primary_map),
        'missing_ids': missing, 'extra_ids': extra, 'value_mismatches': values,
        'agreement': {'missing_ids': len(missing), 'extra_ids': len(extra), 'value_mismatches': len(values), 'pass': not missing and not extra and not values},
        'artifacts': {'dir': str(OUT), 'oracle_canonical_terms': str(csv_path)},
        'decision': 'PRIMARY_AND_INDEPENDENT_ORACLE_AGREE__SEMANTIC_CATALOG_PASS__SEPARATE_CAUSAL_ONTOLOGY_PREREGISTRATION_REQUIRED_BEFORE_MARKET_DATA' if not missing and not extra and not values else 'PARSER_ORACLE_DISAGREEMENT__CLOSE_EXPLICIT_CASH_TERM_OBJECT_NO_MARKET_DATA',
    }
    (OUT / 'v651_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
