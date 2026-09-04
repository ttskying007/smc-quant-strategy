#!/usr/bin/env python3
"""Independent raw-data identity Oracle for V598; no outcome/replay inputs."""
from __future__ import annotations

import csv
import json
import math
from bisect import bisect_right
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
DAILY = ROOT / 'kline_cache'
CATALOG = AUDIT / 'v596_contract_award_event_catalog_latest.json'
SEED_LATEST = AUDIT / 'v598_contract_award_demand_retest_seed_latest.json'
LATEST = AUDIT / 'v599_v598_independent_raw_oracle_latest.json'
OUT = AUDIT / f'v599_v598_independent_raw_oracle_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
YEARS = ('2024', '2025')


def date8(value: object) -> str:
    text = ''.join(char for char in str(value or '') if char.isdigit())
    return text[:8] if len(text) >= 8 else ''


def number(value: object) -> float | None:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) and parsed > 0 else None
    except (TypeError, ValueError):
        return None


def event_dates(catalog: dict) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    canonical: set[tuple[str, str]] = set()
    with Path(catalog['artifacts']['events']).open(encoding='utf-8') as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            symbol, day = str(item.get('symbol') or ''), date8(item.get('notice_date'))
            if len(symbol) == 9 and day[:4] in YEARS:
                canonical.add((symbol, day))
    for symbol, day in canonical:
        result.setdefault(symbol, set()).add(day)
    return result


def daily(symbol: str) -> list[dict]:
    try:
        raw = json.loads((DAILY / f'{symbol.replace(".", "_")}_daily_750.json').read_text())
    except (OSError, ValueError):
        return []
    rows = []
    for item in raw if isinstance(raw, list) else []:
        values = [number(item.get(key)) for key in ('o', 'h', 'l', 'c')]
        day = date8(item.get('t') or item.get('date'))
        if len(day) == 8 and all(value is not None for value in values):
            rows.append({'d': day, 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3]})
    return sorted(rows, key=lambda row: row['d'])


def exact_identity(symbol: str, event_day: str, rows: list[dict]) -> tuple[str, str] | None:
    dates = [row['d'] for row in rows]
    first = bisect_right(dates, event_day)
    for break_i in range(first, min(first + 30, len(rows))):
        pivots = []
        for pivot_i in range(3, break_i - 3):
            left = max(row['h'] for row in rows[pivot_i - 3:pivot_i])
            right = max(row['h'] for row in rows[pivot_i + 1:pivot_i + 4])
            if rows[pivot_i]['h'] > left and rows[pivot_i]['h'] >= right:
                pivots.append(pivot_i)
        accepted = [pivot_i for pivot_i in pivots if rows[pivot_i]['h'] < rows[break_i]['c']]
        red_bars = [index for index in range(first, break_i + 1) if rows[index]['c'] < rows[index]['o']]
        if not accepted or not red_bars:
            continue
        poi_i = red_bars[-1]
        low, high = rows[poi_i]['l'], rows[poi_i]['o']
        for reclaim_i in range(break_i + 1, min(break_i + 16, len(rows))):
            bar = rows[reclaim_i]
            if bar['l'] <= high and bar['h'] >= low and bar['c'] >= high and reclaim_i + 1 < len(rows):
                return symbol, rows[reclaim_i + 1]['d']
    return None


def main() -> None:
    catalog = json.loads(CATALOG.read_text())
    seed_report = json.loads(SEED_LATEST.read_text())
    with Path(seed_report['artifacts']['seeds']).open(newline='', encoding='utf-8') as handle:
        expected = {(row['symbol'], row['planned_entry_date']) for row in csv.DictReader(handle)}
    actual: set[tuple[str, str]] = set()
    source = event_dates(catalog)
    for count, (symbol, days) in enumerate(sorted(source.items()), 1):
        rows = daily(symbol)
        for event_day in days:
            identity = exact_identity(symbol, event_day, rows)
            if identity and identity[1][:4] in YEARS:
                actual.add(identity)
        if count % 500 == 0:
            print(json.dumps({'symbols': count, 'oracle_identities': len(actual)}, ensure_ascii=False), flush=True)
    missing, extra = expected - actual, actual - expected
    OUT.mkdir(parents=True, exist_ok=False)
    identities = OUT / 'v599_oracle_identities.csv'
    with identities.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['symbol', 'planned_entry_date'])
        writer.writeheader()
        writer.writerows({'symbol': symbol, 'planned_entry_date': day} for symbol, day in sorted(actual))
    matched = expected == actual
    report = {
        'version': 'V599_V598_INDEPENDENT_RAW_ORACLE_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'input_contract': 'V598 expected identities plus immutable V596 event catalog and daily OHLC only; no outcome, trade, PnL, exit, target, stop, or replay file read.',
        'independent_rebuild': 'Separately rebuilds canonical PIT event dates and post-event BSL acceptance -> demand-OB retest identities without importing V598 code.',
        'expected_identities': len(expected), 'oracle_identities': len(actual), 'missing': len(missing), 'extra': len(extra),
        'missing_sample': [{'symbol': s, 'planned_entry_date': d} for s, d in sorted(missing)[:20]],
        'extra_sample': [{'symbol': s, 'planned_entry_date': d} for s, d in sorted(extra)[:20]],
        'identity_match': matched,
        'invariants': {'no_outcome_files_read': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False},
        'decision': 'V599_ORACLE_PASS__ONE_FROZEN_STRICT_T1_REPLAY_AUTHORIZED' if matched else 'V599_ORACLE_FAIL__NO_REPLAY_ALLOWED',
        'artifacts': {'out_dir': str(OUT), 'oracle_identities': str(identities), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v599_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
