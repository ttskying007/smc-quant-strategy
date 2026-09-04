#!/usr/bin/env python3
"""V528 independent raw-bar oracle for the frozen V527 Spring-Test-SOS seed set."""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
KDIR = ROOT / 'kline_cache'
V527 = AUD / 'v527_wyckoff_spring_test_sos_seed_gate_latest.json'
OUT = AUD / f'v528_wyckoff_spring_test_sos_independent_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v528_wyckoff_spring_test_sos_independent_oracle_latest.json'
LEFT = RIGHT = 3
BREACH = 0.003
LOOKBACK = 20
HIGH_RANK = 0.80
TEST_RATIO = 0.60
TEST_MAX_WAIT = 5
SOS_MAX_WAIT = 3


def number(value: Any) -> float | None:
    try:
        value = float(value)
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def date_key(value: Any) -> str:
    text = ''.join(c for c in str(value or '') if c.isdigit())
    return text[:8] if len(text) >= 8 else ''


def bars(path: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return []
    result = []
    for item in raw if isinstance(raw, list) else []:
        date = date_key(item.get('t') or item.get('date') or item.get('day'))
        values = [number(item.get(field)) for field in ('o', 'h', 'l', 'c', 'v')]
        if date and all(value is not None for value in values):
            result.append(dict(zip(('d', 'o', 'h', 'l', 'c', 'v'), (date, *values))))
    return sorted(result, key=lambda row: row['d'])


def pivot_low(series: list[dict[str, Any]], at: int) -> bool:
    if at < LEFT or at + RIGHT >= len(series):
        return False
    neighborhood = series[at - LEFT:at] + series[at + 1:at + RIGHT + 1]
    return series[at]['l'] < min(row['l'] for row in neighborhood[:LEFT]) and series[at]['l'] <= min(row['l'] for row in neighborhood[LEFT:])


def oracle_rows(symbol: str, series: list[dict[str, Any]]) -> set[tuple[str, str, str, str, str]]:
    found: set[tuple[str, str, str, str, str]] = set()
    for spring_at in range(max(LOOKBACK, LEFT + RIGHT + 1), len(series) - TEST_MAX_WAIT - SOS_MAX_WAIT - 1):
        swing_at = spring_at - RIGHT - 1
        if not pivot_low(series, swing_at):
            continue
        swing, spring = series[swing_at], series[spring_at]
        rank = sum(row['v'] <= spring['v'] for row in series[spring_at - LOOKBACK:spring_at]) / LOOKBACK
        if not (spring['l'] <= swing['l'] * (1 - BREACH) and spring['c'] > swing['l'] and rank >= HIGH_RANK):
            continue
        test_at = None
        for candidate in range(spring_at + 1, spring_at + 1 + TEST_MAX_WAIT):
            test = series[candidate]
            if test['l'] >= spring['l'] and test['c'] > swing['l'] and test['v'] <= spring['v'] * TEST_RATIO:
                test_at = candidate
                break
        if test_at is None:
            continue
        sos_at = next((candidate for candidate in range(test_at + 1, test_at + 1 + SOS_MAX_WAIT)
                       if series[candidate]['c'] > series[test_at]['h']), None)
        if sos_at is None:
            continue
        found.add((symbol, spring['d'], series[test_at]['d'], series[sos_at]['d'], series[sos_at + 1]['d']))
    return found


def main() -> None:
    source = json.loads(V527.read_text())
    if not source.get('support_gate_pass') or source.get('outcomes_opened'):
        raise RuntimeError('V527 support gate must pass without opened outcomes')
    with Path(source['artifacts']['seeds']).open(newline='', encoding='utf-8') as handle:
        generated = list(csv.DictReader(handle))
    expected = {(row['symbol'], row['spring_date'], row['test_date'], row['sos_date'], row['entry_eligible_date']) for row in generated}
    actual: set[tuple[str, str, str, str, str]] = set()
    for path in sorted(KDIR.glob('*_daily_750.json')):
        try:
            code, exchange = path.name.removesuffix('_daily_750.json').rsplit('_', 1)
        except ValueError:
            continue
        actual.update(oracle_rows(f'{code}.{exchange}', bars(path)))
    missing, extra = expected - actual, actual - expected
    report = {
        'version': 'V528_WYCKOFF_SPRING_TEST_SOS_INDEPENDENT_ORACLE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'contract': source['frozen_contract'],
        'generator_seed_count': len(expected), 'oracle_seed_count': len(actual),
        'missing_from_oracle_count': len(missing), 'extra_from_oracle_count': len(extra),
        'missing_examples': sorted(missing)[:10], 'extra_examples': sorted(extra)[:10],
        'oracle_pass': expected == actual,
        'outcomes_opened': False,
        'decision': 'V528_ORACLE_PASS__ONE_FROZEN_T1_REPLAY_ALLOWED' if expected == actual else 'V528_ORACLE_FAIL__CLOSE_ONTOLOGY',
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST), 'v527': str(V527)},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v528_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
