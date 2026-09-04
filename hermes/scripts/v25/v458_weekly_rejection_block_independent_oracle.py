#!/usr/bin/env python3
"""V458 independent raw-bar oracle for V457 weekly rejection-block seeds.

The implementation re-aggregates weekly bars and re-walks the daily lifecycle.
It reads no entries, exits, PnL, MFE/MAE, winners, or outcomes.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
KDIR = ROOT / 'kline_cache'
AUD = ROOT / 'smc_audit'
SRC = AUD / 'v457_weekly_ssl_rejection_block_latest.json'
OUT = AUD / f"v458_weekly_rejection_block_independent_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST = AUD / 'v458_weekly_rejection_block_independent_oracle_latest.json'
FORBIDDEN = ('entry_price', 'exit', 'pnl', 'mfe', 'mae', 'target', 'tp', 'rr', 'hold_bars', 'won', 'outcome')


def number(value: object) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else 0.0
    except (TypeError, ValueError):
        return 0.0


def integer(value: object) -> int:
    return int(float(value))


def date_string(value: object) -> str:
    return ''.join(char for char in str(value or '') if char.isdigit())[:8]


def raw_daily(sym: str) -> list[dict]:
    try:
        source = json.loads((KDIR / f"{sym.replace('.', '_')}_daily_750.json").read_text())
    except (OSError, json.JSONDecodeError):
        return []
    bars = []
    for source_bar in source:
        date = date_string(source_bar.get('t') or source_bar.get('date'))
        values = [number(source_bar.get(key)) for key in ('o', 'h', 'l', 'c')]
        if date and all(values):
            bars.append({'t': date, 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3]})
    return sorted(bars, key=lambda bar: bar['t'])


def weekly_bars(daily: list[dict]) -> list[dict]:
    groups: dict[tuple[int, int], list[dict]] = {}
    order: list[tuple[int, int]] = []
    for bar in daily:
        key = datetime.strptime(bar['t'], '%Y%m%d').date().isocalendar()[:2]
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(bar)
    order = order[:-1]
    result = []
    for key in order:
        group = groups[key]
        result.append({'start_date': group[0]['t'], 'end_date': group[-1]['t'], 'o': group[0]['o'],
                       'h': max(bar['h'] for bar in group), 'l': min(bar['l'] for bar in group), 'c': group[-1]['c']})
    return result


def is_weekly_low(weeks: list[dict], idx: int) -> bool:
    return 2 <= idx < len(weeks) - 2 and all(weeks[j]['l'] > weeks[idx]['l'] for j in range(idx - 2, idx + 3) if j != idx)


def same_price(left: float, right: float) -> bool:
    return abs(left - right) <= max(1e-6, abs(right) * 1e-6)


def first_lifecycle(daily: list[dict], raid_end: str, low: float, high: float) -> tuple[str, int | None, int | None, int | None, int | None]:
    start = next((idx for idx, bar in enumerate(daily) if bar['t'] > raid_end), None)
    if start is None:
        return 'RIGHT_EDGE_AFTER_RAID', None, None, None, None
    touch = reclaim = None
    for idx in range(start, min(len(daily), start + 20)):
        bar = daily[idx]
        if bar['c'] < low:
            return 'CANCEL_POI_INVALIDATED', touch, reclaim, None, None
        if touch is None:
            if bar['l'] <= high:
                touch = idx
            continue
        if reclaim is None:
            if idx > touch and bar['c'] > high:
                reclaim = idx
            continue
        if idx > reclaim and bar['c'] > high and bar['l'] > low:
            return 'TAKEOVER_CONFIRMED', touch, reclaim, idx, idx + 1 if idx + 1 < len(daily) else None
    return 'EXPIRED', touch, reclaim, None, None


def verify(row: dict, daily: list[dict]) -> str:
    try:
        weeks = weekly_bars(daily)
        pivot = integer(row['weekly_ssl_idx'])
        visible = integer(row['weekly_ssl_confirm_idx'])
        raid_idx = integer(row['weekly_raid_idx'])
        touch = integer(row['touch_idx'])
        reclaim = integer(row['reclaim_idx'])
        hold = integer(row['hold_idx'])
        eligible = integer(row['eligible_entry_idx'])
    except (KeyError, TypeError, ValueError):
        return 'BAD_INDEX'
    if not (is_weekly_low(weeks, pivot) and visible == pivot + 2 < raid_idx < len(weeks)):
        return 'WEEKLY_PIVOT_OR_VISIBILITY'
    if raid_idx - pivot > 26:
        return 'SSL_AGE'
    raid = weeks[raid_idx]
    if not (raid['l'] < weeks[pivot]['l'] and raid['c'] > weeks[pivot]['l']):
        return 'WEEKLY_RAID_GEOMETRY'
    references = [
        idx for idx in range(max(2, raid_idx - 26), raid_idx - 2)
        if idx + 2 < raid_idx and is_weekly_low(weeks, idx)
        and raid['l'] < weeks[idx]['l'] and raid['c'] > weeks[idx]['l']
    ]
    if not references or max(references) != pivot:
        return 'NOT_MOST_RECENT_RAIDED_SSL'
    low = raid['l']
    high = min(raid['o'], raid['c'])
    if not (
        same_price(number(row['weekly_ssl_price']), weeks[pivot]['l'])
        and same_price(number(row['weekly_raid_low']), raid['l'])
        and same_price(number(row['weekly_raid_close']), raid['c'])
        and same_price(number(row['zone_low']), low)
        and same_price(number(row['zone_high']), high)
    ):
        return 'PRICE_MISMATCH'
    if date_string(row.get('weekly_raid_start_date')) != raid['start_date'] or date_string(row.get('weekly_raid_end_date')) != raid['end_date']:
        return 'WEEK_DATE_MISMATCH'
    status, expected_touch, expected_reclaim, expected_hold, expected_eligible = first_lifecycle(daily, raid['end_date'], low, high)
    if status != 'TAKEOVER_CONFIRMED':
        return 'LIFECYCLE_NOT_TAKEOVER'
    if (touch, reclaim, hold, eligible) != (expected_touch, expected_reclaim, expected_hold, expected_eligible):
        return 'NOT_FIRST_LIFECYCLE_PATH'
    expected_dates = {'touch_date': touch, 'reclaim_date': reclaim, 'hold_date': hold, 'eligible_entry_date': eligible}
    if any(date_string(row.get(field)) != daily[idx]['t'] for field, idx in expected_dates.items()):
        return 'DAILY_DATE_MISMATCH'
    if not (raid['end_date'] < daily[touch]['t'] < daily[reclaim]['t'] < daily[hold]['t'] < daily[eligible]['t']):
        return 'CHRONOLOGY'
    return 'PASS'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads(SRC.read_text())
    if not report.get('support_gate_pass'):
        raise RuntimeError('V457 support gate did not pass')
    with open(report['artifacts']['seeds']) as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        rows = list(reader)
    forbidden = [header for header in headers if header != 'no_outcome_fields' and any(word in header.lower() for word in FORBIDDEN)]
    cache: dict[str, list[dict]] = {}
    counts: Counter = Counter()
    passed: list[dict] = []
    mismatches: list[dict] = []
    for idx, row in enumerate(rows, 1):
        sym = row['symbol']
        if sym not in cache:
            cache[sym] = raw_daily(sym)
        reason = verify(row, cache[sym]) if cache[sym] else 'MISSING_KLINE'
        counts[reason] += 1
        if reason == 'PASS':
            passed.append(row)
        elif len(mismatches) < 1000:
            mismatches.append({'symbol': sym, 'eligible_entry_date': row.get('eligible_entry_date', ''), 'reason': reason})
        if idx % 10000 == 0:
            print(json.dumps({'progress': idx, 'passed': len(passed)}), flush=True)
    passed_file = OUT / 'v458_oracle_passed_seeds.csv'
    mismatch_file = OUT / 'v458_mismatches.csv'
    with passed_file.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(passed)
    with mismatch_file.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['symbol', 'eligible_entry_date', 'reason'])
        writer.writeheader()
        writer.writerows(mismatches)
    mismatch_total = len(rows) - len(passed)
    gate = mismatch_total == 0 and not forbidden
    result = {
        'version': 'V458_WEEKLY_REJECTION_BLOCK_INDEPENDENT_ORACLE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'source_seed_count': len(rows),
        'oracle_pass_count': len(passed),
        'failure_counts': dict(counts),
        'mismatch_total': mismatch_total,
        'forbidden_outcome_headers': forbidden,
        'duplicate_symbol_entry': len(passed) - len(set((row['symbol'], row['eligible_entry_date']) for row in passed)),
        'oracle_gate_pass': gate,
        'decision': 'WEEKLY_REJECTION_BLOCK_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED' if gate else 'WEEKLY_REJECTION_BLOCK_ORACLE_FAIL__NO_REPLAY',
        'artifacts': {'out_dir': str(OUT), 'passed_seeds': str(passed_file), 'mismatches': str(mismatch_file), 'latest': str(LATEST)},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v458_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
