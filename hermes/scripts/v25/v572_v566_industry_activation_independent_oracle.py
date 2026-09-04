#!/usr/bin/env python3
"""V572 independent raw-bar identity Oracle for V566; outcome files are forbidden."""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
DAILY = ROOT / 'kline_cache'
M60 = ROOT / 'kline_cache_60min'
MAPPING = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854' / 'baostock_stock_industry.json'
SEED_LATEST = AUDIT / 'v566_industry_activation_m60_micro_continuation_seed_latest.json'
LATEST = AUDIT / 'v572_v566_industry_activation_independent_oracle_latest.json'
OUT = AUDIT / f'v572_v566_industry_activation_independent_oracle_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
YEARS = {'2025', '2026'}
FORBIDDEN = ('pnl', 'outcome', 'exit', 'mfe', 'mae', 'win', 'loss', 'return')


def num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


def date_of(value: Any) -> str:
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else ''


def symbol_from_file(path: Path) -> str:
    fields = path.name.split('_')
    return f'{fields[0]}.{fields[1]}' if len(fields) >= 4 and len(fields[0]) == 6 else ''


def read_list(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text())
        return payload if isinstance(payload, list) else []
    except (OSError, ValueError):
        return []


def read_industry() -> dict[str, str]:
    return {
        str(row['symbol']): str(row['industry'])
        for row in read_list(MAPPING)
        if row.get('symbol') and row.get('industry')
    }


def daily_activation(industry: dict[str, str]) -> tuple[dict[tuple[str, str], bool], dict[str, str]]:
    """Rebuild previous-session sector activation directly from daily raw bars."""
    returns: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    calendar: set[str] = set()
    for path in DAILY.glob('*_daily_750.json'):
        symbol = symbol_from_file(path)
        sector = industry.get(symbol)
        if not sector:
            continue
        previous_close: float | None = None
        for row in sorted(read_list(path), key=lambda item: date_of(item.get('t') or item.get('date'))):
            day = date_of(row.get('t') or row.get('date'))
            close, high = num(row.get('c')), num(row.get('h'))
            if not day or close is None:
                continue
            calendar.add(day)
            if previous_close is not None:
                returns[(day, sector)].append((100 * (close / previous_close - 1), 100 * ((high or close) / previous_close - 1)))
            previous_close = close
    active = {
        key: sum(high_return >= 9.5 for _, high_return in values) >= 3
        or 100 * sum(close_return >= 5 for close_return, _ in values) / len(values) >= 20
        for key, values in returns.items()
        if len(values) >= 5
    }
    ordered = sorted(calendar)
    prior = {today: yesterday for yesterday, today in zip(ordered, ordered[1:])}
    return active, prior


def m60_snapshot(industry: dict[str, str]) -> dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]]:
    """Build first/second 60m observations, independently of the V566 generator."""
    events: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]] = {}
    for path in M60.glob('*_60min_500.json'):
        symbol = symbol_from_file(path)
        if symbol not in industry:
            continue
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in read_list(path):
            day = date_of(row.get('t'))
            if day:
                grouped[day].append(row)
        for day, bars in grouped.items():
            bars.sort(key=lambda item: str(item.get('t') or ''))
            if len(bars) >= 2:
                events[(symbol, day)] = (bars[0], bars[1])
    return events


def industry_leaders(industry: dict[str, str], snapshots: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]]) -> dict[tuple[str, str], bool]:
    by_day_sector: dict[tuple[str, str], list[float]] = defaultdict(list)
    for (symbol, day), (first, _) in snapshots.items():
        opening, closing = num(first.get('o')), num(first.get('c'))
        if opening is not None and closing is not None:
            by_day_sector[(day, industry[symbol])].append(100 * (closing / opening - 1))
    leaders: dict[tuple[str, str], bool] = {}
    sectors_per_day: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for (day, sector), values in by_day_sector.items():
        if len(values) >= 5:
            sectors_per_day[day].append((sector, median(values), 100 * sum(value >= 0 for value in values) / len(values)))
    for day, values in sectors_per_day.items():
        ordered = sorted(values, key=lambda item: item[1], reverse=True)
        total = len(ordered)
        for rank, (sector, _, green_pct) in enumerate(ordered, 1):
            # Match the preregistered finite-decimal upper-third boundary exactly.
            leaders[(day, sector)] = 100 * rank / total <= 33.333333 and green_pct >= 60
    return leaders


def actual_identities() -> set[tuple[str, str]]:
    industry = read_industry()
    activation, previous_day = daily_activation(industry)
    snapshots = m60_snapshot(industry)
    leaders = industry_leaders(industry, snapshots)
    # The source contract allows only dates that exist in the symbol's daily
    # execution calendar; minute-only observations are not executable identities.
    daily_sessions = {
        symbol: {date_of(row.get('t') or row.get('date')) for row in read_list(path)}
        for path in DAILY.glob('*_daily_750.json')
        if (symbol := symbol_from_file(path)) in industry
    }
    selected: set[tuple[str, str]] = set()
    for (symbol, day), (first, second) in snapshots.items():
        sector = industry[symbol]
        prior = previous_day.get(day)
        if day not in daily_sessions.get(symbol, set()):
            continue
        if not prior or not activation.get((prior, sector), False) or not leaders.get((day, sector), False):
            continue
        first_open, first_close, first_low, first_high, first_volume = (num(first.get(key)) for key in ('o', 'c', 'l', 'h', 'v'))
        second_close, second_low, second_volume = (num(second.get(key)) for key in ('c', 'l', 'v'))
        if None in (first_open, first_close, first_low, first_high, first_volume, second_close, second_low, second_volume):
            continue
        if first_close >= first_open and second_low >= first_low and second_volume >= first_volume and second_close > first_high:
            selected.add((symbol, day))
    return selected


def expected_identities() -> set[tuple[str, str]]:
    metadata = json.loads(SEED_LATEST.read_text())
    seed_path = Path(metadata['artifacts']['rows'])
    with seed_path.open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    headers = set(rows[0]) if rows else set()
    bad = sorted(header for header in headers if any(word in header.lower() for word in FORBIDDEN))
    if bad:
        raise RuntimeError(f'forbidden outcome headers in seed input: {bad}')
    return {(str(row['symbol']), str(row['event_date'])) for row in rows}


def main() -> None:
    expected = expected_identities()
    actual = actual_identities()
    missing, extra = expected - actual, actual - expected
    OUT.mkdir(parents=True, exist_ok=False)
    identity_file = OUT / 'v572_oracle_identities.csv'
    with identity_file.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['symbol', 'event_date'])
        writer.writeheader()
        writer.writerows({'symbol': symbol, 'event_date': day} for symbol, day in sorted(actual))
    report = {
        'version': 'V572_V566_INDUSTRY_ACTIVATION_INDEPENDENT_RAW_ORACLE_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'input_contract': 'V566 expected identities plus raw local daily/60m OHLCV and frozen industry mapping only; no trade, PnL, exit, target, stop, outcome or replay file is read.',
        'independent_rebuild': 'Reconstructs prior-session industry activation, same-session first-60m median-return leadership, and stock second-60m micro-BOS without importing the V566 generator.',
        'expected_identities': len(expected),
        'oracle_identities': len(actual),
        'yearly_oracle_identities': {year: sum(day.startswith(year) for _, day in actual) for year in sorted(YEARS)},
        'missing_count': len(missing),
        'extra_count': len(extra),
        'missing_sample': [{'symbol': symbol, 'event_date': day} for symbol, day in sorted(missing)[:20]],
        'extra_sample': [{'symbol': symbol, 'event_date': day} for symbol, day in sorted(extra)[:20]],
        'identity_match': expected == actual,
        'invariants': {'no_outcome_files_read': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False},
        'decision': 'V572_ORACLE_PASS__ONE_FROZEN_STRICT_T1_REPLAY_AUTHORIZED' if expected == actual else 'V572_ORACLE_FAIL__NO_REPLAY_ALLOWED',
        'artifacts': {'out_dir': str(OUT), 'oracle_identities': str(identity_file), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v572_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
