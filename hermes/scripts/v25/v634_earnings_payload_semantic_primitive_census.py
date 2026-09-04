#!/usr/bin/env python3
"""V634 source-only census of explicit earnings-payload semantic primitives.

This is not a strategy parser. It inventories exact text primitives and their
coverage before any field becomes eligible for a separately preregistered event
semantic object. No market/OHLCV, seed, trade, outcome or PnL file is read.
"""
from __future__ import annotations

import gzip
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
CACHE = ROOT / 'pit_cache' / 'v628_earnings_payload_raw'
COVERAGE = AUD / 'v630_earnings_payload_full_coverage_pit_audit_latest.json'
OUT = AUD / f'v634_earnings_payload_semantic_primitive_census_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v634_earnings_payload_semantic_primitive_census_latest.json'
YEARS = ('2023', '2024', '2025')

# Exact source-text primitives only; these are inventory flags, not trading labels.
PRIMITIVES = {
    'EXPLICIT_POSITIVE_VALUE': r'预计净利润为正值',
    'EXPLICIT_NEGATIVE_VALUE': r'预计净利润为负值',
    'TURNAROUND_TO_PROFIT': r'(?:扭亏为盈|由亏转盈)',
    'PROFIT_TO_LOSS': r'(?:由盈转亏|转为亏损)',
    'PROFIT_INCREASE': r'(?:同比(?:上升|增长)|较上年同期(?:上升|增长))',
    'PROFIT_DECREASE': r'(?:同比(?:下降|减少)|较上年同期(?:下降|减少))',
    'FORECAST_PERIOD_HEADING': r'业绩预告期间',
    'FORECAST_SITUATION_HEADING': r'业绩预告情况',
    'NET_PROFIT_TEXT': r'归属于上市公司股东的净利润',
    'NUMERIC_RANGE_MARKER': r'(?:预计|为).{0,48}?(?:万元|亿元)',
}
COMPILED = {name: re.compile(pattern) for name, pattern in PRIMITIVES.items()}


def documents() -> list[dict]:
    docs = []
    for path in CACHE.glob('[0-9][0-9][0-9][0-9]/AN*.json.gz'):
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            doc = json.load(handle)
        if doc.get('notice_date', '')[:4] in YEARS:
            docs.append(doc)
    return docs


def main() -> None:
    coverage = json.loads(COVERAGE.read_text())
    assert coverage['hard_gate']['pass'] is True
    docs = documents()
    assert len(docs) == coverage['coverage']['denominator']
    counts = {name: Counter() for name in PRIMITIVES}
    intersections = Counter()
    samples: dict[str, list[dict]] = defaultdict(list)
    unstructured = Counter()
    for doc in docs:
        year = doc['notice_date'][:4]
        text = re.sub(r'\s+', '', str(doc.get('notice_content') or ''))
        flags = {name for name, regex in COMPILED.items() if regex.search(text)}
        for name in flags:
            counts[name][year] += 1
            if len(samples[name]) < 5:
                samples[name].append({'announcement_id': doc['announcement_id'], 'symbol': doc['symbol'], 'notice_date': doc['notice_date'], 'content_sha256': doc['content_sha256']})
        direction = '+'.join(sorted(flags & {'EXPLICIT_POSITIVE_VALUE', 'EXPLICIT_NEGATIVE_VALUE', 'TURNAROUND_TO_PROFIT', 'PROFIT_TO_LOSS'})) or 'NO_EXACT_DIRECTION_PRIMITIVE'
        intersections[(year, direction)] += 1
        if not {'FORECAST_PERIOD_HEADING', 'FORECAST_SITUATION_HEADING', 'NET_PROFIT_TEXT'} <= flags:
            unstructured[year] += 1
    support = {
        name: {
            'total': sum(counts[name].values()),
            'by_year': {year: counts[name][year] for year in YEARS},
            'all_years_ge_300': all(counts[name][year] >= 300 for year in YEARS),
            'total_ge_1000': sum(counts[name].values()) >= 1000,
        }
        for name in PRIMITIVES
    }
    report = {
        'version': 'V634_EARNINGS_PAYLOAD_SEMANTIC_PRIMITIVE_CENSUS_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'Exact text primitive inventory only. No semantic object, SMC response, market/OHLCV, seed, outcome, trade, PnL, stop, target or replay was generated.',
        'lineage': {'full_coverage_pit_audit': str(COVERAGE), 'raw_cache': str(CACHE), 'closed_exact_positive_object': str(AUD / 'v632_positive_earnings_preannouncement_semantic_catalog_latest.json')},
        'denominator': {'documents': len(docs), 'years': {year: sum(doc['notice_date'].startswith(year) for doc in docs) for year in YEARS}},
        'primitive_contract': {'patterns': PRIMITIVES, 'interpretation': 'Counts are source-text occurrences. They do not prove event semantics, market relevance, forecast magnitude, or eligibility for strategy use.'},
        'support_inventory': support,
        'exact_direction_intersections_by_year': {year: {key[1]: value for key, value in intersections.items() if key[0] == year} for year in YEARS},
        'not_all_three_core_headings_by_year': {year: unstructured[year] for year in YEARS},
        'identity_samples_hash_only': dict(samples),
        'decision': 'SOURCE_SEMANTIC_CENSUS_COMPLETE__ONLY_A_DIFFERENT_PREDECLARED_FIELD_OBJECT_MAY_PROCEED_TO_SEMANTIC_AUDIT__CLOSED_EXPLICIT_POSITIVE_OBJECT_REMAINS_CLOSED',
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'v634_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
