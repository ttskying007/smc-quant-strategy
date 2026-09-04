#!/usr/bin/env python3
"""Independent raw-data Oracle for V577; outcome/replay files are never opened."""
from __future__ import annotations

import csv
import gzip
import json
import math
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import quantiles
from typing import Any

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
MARGIN = ROOT / 'pit_cache' / 'v562_exchange_margin_raw'
DAILY = ROOT / 'kline_cache'
SEED_LATEST = AUDIT / 'v577_lending_short_pressure_smc_squeeze_seed_latest.json'
LATEST = AUDIT / 'v578_v577_independent_raw_oracle_latest.json'
OUT = AUDIT / f'v578_v577_independent_raw_oracle_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
YEARS = ('2023', '2024', '2025')


def num(value: Any) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) and x > 0 else None
    except (TypeError, ValueError):
        return None


def source_rows(exchange: str, date: str) -> list[dict[str, Any]]:
    try:
        with gzip.open(MARGIN / exchange / f'{date}.json.gz', 'rt', encoding='utf-8') as handle:
            doc = json.load(handle)
    except (OSError, ValueError):
        return []
    if doc.get('exchange') != exchange or doc.get('date') != date:
        return []
    rows = doc.get('rows')
    return rows if isinstance(rows, list) else []


def external_event_dates() -> dict[str, set[str]]:
    """Independently reconstruct q75 lending-pressure state transitions."""
    output: dict[str, set[str]] = defaultdict(set)
    for exchange in ('SH', 'SZ'):
        prior_balance: dict[str, float] = {}
        prior_high: set[str] = set()
        for path in sorted((MARGIN / exchange).glob('20*.json.gz')):
            date = path.stem.split('.')[0]
            if date[:4] not in YEARS:
                continue
            parsed: list[tuple[str, float, float]] = []
            for row in source_rows(exchange, date):
                code = str(row.get('code') or '').zfill(6)
                sold = num(row.get('lending_sell'))
                balance = num(row.get('lending_balance'))
                prior = prior_balance.get(code)
                if code.isdigit() and sold is not None and balance is not None and prior:
                    parsed.append((code, sold / prior, balance))
            threshold = quantiles([x[1] for x in parsed], n=4, method='inclusive')[2] if len(parsed) >= 4 else math.inf
            current_high = {code for code, intensity, balance in parsed if intensity >= threshold and balance >= prior_balance[code]}
            suffix = 'SH' if exchange == 'SH' else 'SZ'
            for code in current_high - prior_high:
                output[f'{code}.{suffix}'].add(date)
            prior_high = current_high
            for row in source_rows(exchange, date):
                code = str(row.get('code') or '').zfill(6)
                balance = num(row.get('lending_balance'))
                if code.isdigit() and balance is not None:
                    prior_balance[code] = balance
    return output


def bars(symbol: str) -> list[dict[str, Any]]:
    try:
        raw = json.loads((DAILY / f'{symbol.replace(".", "_")}_daily_750.json').read_text())
    except (OSError, ValueError):
        return []
    output = []
    for row in raw if isinstance(raw, list) else []:
        date = str(row.get('t') or row.get('date') or '')[:8]
        values = [num(row.get(key)) for key in ('o', 'h', 'l', 'c')]
        if len(date) == 8 and date.isdigit() and all(value is not None for value in values):
            output.append({'d': date, 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3]})
    return sorted(output, key=lambda row: row['d'])


def confirmed_highs(rows: list[dict[str, Any]]) -> list[tuple[int, int]]:
    return [
        (i, i + 3) for i in range(3, len(rows) - 3)
        if rows[i]['h'] > max(x['h'] for x in rows[i - 3:i])
        and rows[i]['h'] >= max(x['h'] for x in rows[i + 1:i + 4])
    ]


def identity(symbol: str, event_date: str, rows: list[dict[str, Any]], highs: list[tuple[int, int]]) -> tuple[str, str] | None:
    dates = [row['d'] for row in rows]
    start = bisect_right(dates, event_date)
    if start + 29 >= len(rows):
        return None
    for break_i in range(start, min(start + 15, len(rows))):
        known = [item for item in highs if item[1] < break_i and rows[item[0]]['h'] < rows[break_i]['c']]
        if not known:
            continue
        bearish = [i for i in range(start, break_i + 1) if rows[i]['c'] < rows[i]['o']]
        if not bearish:
            continue
        poi_i = bearish[-1]
        low, high = rows[poi_i]['l'], rows[poi_i]['o']
        reclaim_i = next((
            i for i in range(break_i + 1, min(break_i + 11, len(rows)))
            if rows[i]['l'] <= high and rows[i]['h'] >= low and rows[i]['c'] >= high
        ), None)
        if reclaim_i is not None and reclaim_i + 1 < len(rows):
            return symbol, rows[reclaim_i + 1]['d']
    return None


def main() -> None:
    meta = json.loads(SEED_LATEST.read_text())
    with Path(meta['artifacts']['seeds']).open(newline='', encoding='utf-8') as handle:
        expected = {(row['symbol'], row['planned_entry_date']) for row in csv.DictReader(handle)}
    actual: set[tuple[str, str]] = set()
    for count, (symbol, dates) in enumerate(sorted(external_event_dates().items()), 1):
        xs = bars(symbol)
        pivots = confirmed_highs(xs)
        for event_date in dates:
            rebuilt = identity(symbol, event_date, xs, pivots)
            if rebuilt and rebuilt[1][:4] in YEARS:
                actual.add(rebuilt)
        if count % 500 == 0:
            print(json.dumps({'symbols': count, 'oracle_identities': len(actual)}), flush=True)
    missing, extra = expected - actual, actual - expected
    OUT.mkdir(parents=True, exist_ok=False)
    rows = OUT / 'v578_oracle_identities.csv'
    with rows.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['symbol', 'planned_entry_date'])
        writer.writeheader()
        writer.writerows({'symbol': symbol, 'planned_entry_date': date} for symbol, date in sorted(actual))
    matched = expected == actual
    report = {
        'version': 'V578_V577_INDEPENDENT_RAW_ORACLE_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'input_contract': 'V577 expected identities plus official raw SSE/SZSE lending records and daily OHLCV only; no outcome, trade, PnL, exit, target, stop, or replay files read.',
        'independent_rebuild': 'Rebuilds official q75 lending-pressure transitions and post-event confirmed BSL acceptance -> demand POI reclaim lifecycle without importing V577 code.',
        'expected_identities': len(expected), 'oracle_identities': len(actual),
        'missing': len(missing), 'extra': len(extra),
        'missing_sample': [{'symbol': s, 'planned_entry_date': d} for s, d in sorted(missing)[:20]],
        'extra_sample': [{'symbol': s, 'planned_entry_date': d} for s, d in sorted(extra)[:20]],
        'identity_match': matched,
        'invariants': {'no_outcome_files_read': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False},
        'decision': 'V578_ORACLE_PASS__ONE_FROZEN_STRICT_T1_REPLAY_AUTHORIZED' if matched else 'V578_ORACLE_FAIL__NO_REPLAY_ALLOWED',
        'artifacts': {'out_dir': str(OUT), 'oracle_identities': str(rows), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v578_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
