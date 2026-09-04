#!/usr/bin/env python3
"""V612: independent raw identity Oracle for V611; outcome data is prohibited."""
from __future__ import annotations

import csv
import json
import math
from bisect import bisect_right
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT, DAILY = ROOT / 'smc_audit', ROOT / 'kline_cache'
CATALOG = AUDIT / 'v609_cash_dividend_plan_event_catalog_latest.json'
SEED = AUDIT / 'v611_profit_distribution_demand_retest_seed_latest.json'
LATEST = AUDIT / 'v612_v611_independent_raw_oracle_latest.json'
OUT = AUDIT / f'v612_v611_independent_raw_oracle_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
YEARS = ('2023', '2024', '2025')
INCLUDE = ('利润分配预案', '现金分红预案', '利润分配方案')
EXCLUDE = ('实施', '权益分派', '除权除息', '调整', '更正', '终止', '进展', '结果', '完成', '法律意见书', '独立财务顾问', '征求投资者意见', '转增股本')


def d8(value: object) -> str:
    digits = ''.join(char for char in str(value or '') if char.isdigit())
    return digits[:8] if len(digits) >= 8 else ''


def positive(value: object) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def a_share(symbol: str) -> bool:
    return len(symbol) == 9 and symbol[6:] in ('.SH', '.SZ') and symbol[:6].startswith(('00', '30', '60', '68'))


def source_events(catalog: dict) -> dict[str, set[str]]:
    canonical: set[tuple[str, str]] = set()
    for line in Path(catalog['artifacts']['events']).open(encoding='utf-8'):
        try:
            item = json.loads(line)
        except ValueError:
            continue
        symbol, day, title = str(item.get('symbol') or ''), d8(item.get('notice_date')), str(item.get('title') or '')
        if a_share(symbol) and day[:4] in YEARS and any(term in title for term in INCLUDE) and not any(term in title for term in EXCLUDE):
            canonical.add((symbol, day))
    result: dict[str, set[str]] = {}
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
        values = [positive(item.get(key)) for key in ('o', 'h', 'l', 'c')]
        day = d8(item.get('t') or item.get('date'))
        if len(day) == 8 and all(value is not None for value in values):
            rows.append({'d': day, 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3]})
    return sorted(rows, key=lambda row: row['d'])


def identity(symbol: str, event_day: str, rows: list[dict]) -> tuple[str, str] | None:
    start = bisect_right([row['d'] for row in rows], event_day)
    for break_i in range(start, min(start + 30, len(rows))):
        pivots = []
        for pivot_i in range(3, break_i - 3):
            if rows[pivot_i]['h'] > max(row['h'] for row in rows[pivot_i - 3:pivot_i]) and rows[pivot_i]['h'] >= max(row['h'] for row in rows[pivot_i + 1:pivot_i + 4]):
                pivots.append(pivot_i)
        valid = [pivot_i for pivot_i in pivots if rows[pivot_i]['h'] < rows[break_i]['c']]
        bearish = [i for i in range(start, break_i + 1) if rows[i]['c'] < rows[i]['o']]
        if not valid or not bearish:
            continue
        poi_i = bearish[-1]
        low, high = rows[poi_i]['l'], rows[poi_i]['o']
        for reclaim_i in range(break_i + 1, min(break_i + 16, len(rows))):
            bar = rows[reclaim_i]
            if bar['l'] <= high and bar['h'] >= low and bar['c'] >= high and reclaim_i + 1 < len(rows):
                return symbol, rows[reclaim_i + 1]['d']
    return None


def main() -> None:
    catalog, seed_report = json.loads(CATALOG.read_text()), json.loads(SEED.read_text())
    with Path(seed_report['artifacts']['seeds']).open(newline='', encoding='utf-8') as handle:
        expected = {(row['symbol'], row['planned_entry_date']) for row in csv.DictReader(handle)}
    actual: set[tuple[str, str]] = set()
    for count, (symbol, days) in enumerate(sorted(source_events(catalog).items()), 1):
        rows = daily(symbol)
        for event_day in days:
            found = identity(symbol, event_day, rows)
            if found and found[1][:4] in YEARS:
                actual.add(found)
        if count % 500 == 0:
            print(json.dumps({'symbols': count, 'oracle_identities': len(actual)}, ensure_ascii=False), flush=True)
    missing, extra = expected - actual, actual - expected
    OUT.mkdir(parents=True, exist_ok=False)
    identities = OUT / 'v612_oracle_identities.csv'
    with identities.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['symbol', 'planned_entry_date'])
        writer.writeheader()
        writer.writerows({'symbol': symbol, 'planned_entry_date': day} for symbol, day in sorted(actual))
    matched = expected == actual
    report = {
        'version': 'V612_V611_INDEPENDENT_RAW_ORACLE_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'input_contract': 'V611 expected identities plus immutable V609 catalog and daily OHLC only; no outcome, trade, PnL, exit, target, stop, or replay file read.',
        'independent_rebuild': 'Separately rebuilds exact eligible profit-distribution event dates and post-event BSL acceptance -> demand-OB retest identities without importing V611 code.',
        'expected_identities': len(expected),
        'oracle_identities': len(actual),
        'missing': len(missing),
        'extra': len(extra),
        'missing_sample': [{'symbol': s, 'planned_entry_date': d} for s, d in sorted(missing)[:20]],
        'extra_sample': [{'symbol': s, 'planned_entry_date': d} for s, d in sorted(extra)[:20]],
        'identity_match': matched,
        'invariants': {'no_outcome_files_read': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False},
        'decision': 'V612_ORACLE_PASS__ONE_FROZEN_STRICT_T1_REPLAY_AUTHORIZED' if matched else 'V612_ORACLE_FAIL__NO_REPLAY_ALLOWED',
        'artifacts': {'out_dir': str(OUT), 'oracle_identities': str(identities), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v612_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
