#!/usr/bin/env python3
"""V636 source-only canonical catalog + independent semantic oracle for forecast turnarounds."""
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
CONTRACT = AUD / 'v635_current_forecast_turnaround_semantic_contract.json'
OUT = AUD / f'v636_current_forecast_turnaround_semantic_catalog_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v636_current_forecast_turnaround_semantic_catalog_latest.json'
YEARS = ('2023', '2024', '2025')
TURN = re.compile(r'(?:扭亏为盈|由亏转盈)')
START = re.compile(r'业绩预告情况')
END = re.compile(r'(?:（三）|\(三\)|三、本期)')


def docs() -> list[dict]:
    rows = []
    for path in CACHE.glob('[0-9][0-9][0-9][0-9]/AN*.json.gz'):
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            doc = json.load(handle)
        if doc.get('notice_date', '')[:4] in YEARS:
            rows.append(doc)
    return rows


def normalized(doc: dict) -> str:
    return re.sub(r'\s+', '', str(doc.get('notice_content') or ''))


def primary(doc: dict) -> bool:
    """Bounded-section parser: required headings then exact phrase before next section."""
    title, text = str(doc.get('notice_title') or ''), normalized(doc)
    if '业绩快报' in title or '业绩预告期间' not in text:
        return False
    start = START.search(text)
    if not start:
        return False
    tail = text[start.end():]
    end = END.search(tail)
    section = tail[:end.start()] if end else tail
    return bool(TURN.search(section))


def oracle(doc: dict) -> bool:
    """Independent regex: required headings and phrase in non-greedy situation span."""
    title, text = str(doc.get('notice_title') or ''), normalized(doc)
    if '业绩快报' in title or '业绩预告期间' not in text:
        return False
    return bool(re.search(r'业绩预告情况(?:(?!（三）|\(三\)|三、本期).){0,2000}?(?:扭亏为盈|由亏转盈)', text))


def canonical(rows: list[dict]) -> list[dict]:
    selected = [row for row in rows if primary(row)]
    selected.sort(key=lambda row: (row['symbol'], row['notice_date'], row['publication_time'], row['announcement_id']))
    result, seen = [], set()
    for row in selected:
        key = (row['symbol'], row['notice_date'])
        if key in seen:
            continue
        seen.add(key)
        result.append({
            'symbol': row['symbol'], 'announcement_id': row['announcement_id'], 'notice_date': row['notice_date'],
            'publication_time': row['publication_time'], 'notice_title': row['notice_title'], 'content_sha256': row['content_sha256'],
            'semantic_label': 'CURRENT_FORECAST_LOSS_TO_PROFIT_TURNAROUND',
            'availability_rule': 'later_completed_exchange_session_only',
        })
    return result


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    assert contract['decision'] == 'SOURCE_ONLY_SEMANTIC_CATALOG_AND_INDEPENDENT_ORACLE_AUTHORIZED'
    rows = docs()
    assert len(rows) == 8849
    primary_ids = {row['announcement_id'] for row in rows if primary(row)}
    oracle_ids = {row['announcement_id'] for row in rows if oracle(row)}
    canonical_rows = canonical(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / 'v636_current_forecast_turnaround_events.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(canonical_rows[0]) if canonical_rows else ['symbol'])
        writer.writeheader(); writer.writerows(canonical_rows)
    by_year = Counter(row['notice_date'][:4] for row in canonical_rows)
    unique_symbols = len({row['symbol'] for row in canonical_rows})
    gate = contract['support_gate_before_any_market_data']
    support_pass = len(canonical_rows) >= gate['canonical_events_total_min'] and all(by_year[year] >= gate['canonical_events_each_year_min'] for year in YEARS) and unique_symbols >= gate['unique_symbols_min']
    parity = primary_ids == oracle_ids
    report = {
        'version': 'V636_CURRENT_FORECAST_TURNAROUND_SEMANTIC_CATALOG_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'Source-only semantic catalog and independent semantic identity parity. No market/OHLCV, SMC response, seed, trade, outcome, PnL, stop, target or replay was read or generated.',
        'contract': str(CONTRACT), 'raw_document_denominator': len(rows),
        'semantic_parity': {'primary_raw_count': len(primary_ids), 'oracle_raw_count': len(oracle_ids), 'missing_from_oracle': sorted(primary_ids - oracle_ids), 'extra_from_oracle': sorted(oracle_ids - primary_ids), 'pass': parity},
        'canonical_events': len(canonical_rows), 'events_by_year': {year: by_year[year] for year in YEARS}, 'unique_symbols': unique_symbols,
        'support_gate': {**gate, 'pass': support_pass},
        'decision': ('SEMANTIC_ORACLE_AND_SUPPORT_PASS__SEPARATE_CAUSAL_ONTOLOGY_PREREGISTRATION_MAY_BE_CONSIDERED' if parity and support_pass else
                     ('SEMANTIC_ORACLE_MISMATCH__CLOSE_OBJECT_NO_MARKET_DATA' if not parity else 'SUPPORT_FAIL__CLOSE_CURRENT_FORECAST_TURNAROUND_OBJECT_NO_MARKET_DATA')),
        'artifacts': {'dir': str(OUT), 'events': str(OUT / 'v636_current_forecast_turnaround_events.csv')},
    }
    (OUT / 'v636_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
