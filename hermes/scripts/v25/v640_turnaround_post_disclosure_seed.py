#!/usr/bin/env python3
"""V640 outcome-blind seeds for the frozen V638 PIT-turnaround ontology."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
DAILY = ROOT / 'kline_cache'
PREREG = AUDIT / 'v638_turnaround_post_disclosure_smc_response_ontology_preregistration.json'
SOURCE_AUDIT = AUDIT / 'v639_turnaround_event_universe_daily_ohlcv_source_audit_no_outcome.json'
CATALOG = AUDIT / 'v636_current_forecast_turnaround_semantic_catalog_no_outcome_20260726_115224/v636_current_forecast_turnaround_events.csv'
OUT = AUDIT / f'v640_turnaround_post_disclosure_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v640_turnaround_post_disclosure_seed_latest.json'
YEARS = ('2023', '2024', '2025')


def day8(value: object) -> str:
    digits = ''.join(char for char in str(value or '') if char.isdigit())
    return digits[:8] if len(digits) >= 8 else ''


def clock(value: object) -> str:
    text = str(value or '')
    digits = ''.join(char for char in text if char.isdigit())
    return digits[8:14] if len(digits) >= 14 else '235959'


def number(value: object) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


def load_bars(symbol: str) -> list[dict]:
    path = DAILY / f'{symbol.replace(".", "_")}_daily_750.json'
    raw = json.loads(path.read_text())
    bars = []
    for item in raw:
        values = [number(item.get(key)) for key in ('o', 'h', 'l', 'c')]
        date = day8(item.get('t') or item.get('date'))
        if date and None not in values:
            bars.append(dict(d=date, o=values[0], h=values[1], l=values[2], c=values[3]))
    return sorted(bars, key=lambda bar: bar['d'])


def observation_index(bars: list[dict], publication_time: str) -> int | None:
    publication_day, publication_clock = day8(publication_time), clock(publication_time)
    for index, bar in enumerate(bars):
        if bar['d'] > publication_day or (bar['d'] == publication_day and publication_clock < '150000'):
            return index
    return None


def pivot_highs(bars: list[dict], e0: int) -> list[int]:
    found = []
    for index in range(3, e0 - 2):
        high = bars[index]['h']
        if high > max(bar['h'] for bar in bars[index - 3:index]) and high > max(bar['h'] for bar in bars[index + 1:index + 4]):
            found.append(index)
    return found


def response_break(bars: list[dict], e0: int, pivots: list[int]) -> tuple[int, int] | None:
    consumed: set[int] = set()
    for index in range(e0, min(e0 + 20, len(bars))):
        bar = bars[index]
        spread = bar['h'] - bar['l']
        body = bar['c'] - bar['o']
        crossed = [pivot for pivot in pivots if pivot not in consumed and bar['c'] > bars[pivot]['h']]
        if crossed:
            consumed.update(crossed)
        if not crossed or spread <= 0:
            continue
        if body / spread < 0.60 or (bar['h'] - bar['c']) / spread > 0.25:
            continue
        return index, max(crossed, key=lambda pivot: bars[pivot]['h'])
    return None


def origin_ob(bars: list[dict], e0: int, e1: int) -> int | None:
    lower = max(e0, e1 - 10)
    candidates = [index for index in range(lower, e1) if bars[index]['c'] < bars[index]['o']]
    if not candidates:
        return None
    origin = candidates[-1]
    low, upper = bars[origin]['l'], bars[origin]['o']
    for bar in bars[origin + 1:e1]:
        if bar['l'] <= upper or bar['c'] < low:
            return None
    return origin


def lifecycle(bars: list[dict], e1: int, origin: int) -> tuple[str, dict]:
    low, upper = bars[origin]['l'], bars[origin]['o']
    touch = None
    for index in range(e1 + 1, min(e1 + 16, len(bars))):
        bar = bars[index]
        if bar['c'] < low:
            return 'CANCELLED_CLOSE_BELOW_ZONE_LOW', {}
        if bar['l'] <= upper and bar['h'] >= low:
            if bar['c'] > upper:
                return 'CANCELLED_RECLAIM_ON_TOUCH_BAR', {}
            touch = index
            break
    if touch is None:
        return 'EXPIRED_NO_FIRST_TOUCH_15', {}
    for reclaim in range(touch + 1, min(touch + 4, len(bars))):
        bar = bars[reclaim]
        if bar['c'] < low:
            return 'CANCELLED_CLOSE_BELOW_ZONE_LOW', {}
        if bar['l'] <= upper and bar['h'] >= low:
            return 'CANCELLED_SECOND_TOUCH_BEFORE_RECLAIM', {}
        if bar['c'] > upper:
            hold = reclaim + 1
            if hold >= len(bars):
                return 'WAIT_HOLD_UNOBSERVED', {}
            if bars[hold]['c'] <= upper:
                return 'CANCELLED_HOLD_FAILURE', {}
            entry = hold + 1
            if entry >= len(bars):
                return 'WAIT_ENTRY_UNOBSERVED', {}
            return 'VALID_CHAIN', {'first_touch': touch, 'reclaim': reclaim, 'hold': hold, 'entry': entry}
    return 'CANCELLED_NO_RECLAIM_1_TO_3', {}


def candidate(event: dict, bars: list[dict]) -> dict:
    e0 = observation_index(bars, event['publication_time'])
    base = {key: event[key] for key in ('symbol', 'announcement_id', 'notice_date', 'publication_time', 'content_sha256')}
    if e0 is None:
        return {**base, 'status': 'WAIT_OBSERVATION_UNOBSERVED'}
    pivots = pivot_highs(bars, e0)
    found = response_break(bars, e0, pivots)
    if not found:
        return {**base, 'observation_start_date': bars[e0]['d'], 'status': 'EXPIRED_NO_RESPONSE_BREAK_20'}
    e1, pivot = found
    origin = origin_ob(bars, e0, e1)
    if origin is None:
        return {**base, 'observation_start_date': bars[e0]['d'], 'displacement_date': bars[e1]['d'], 'pre_event_swing_pivot_date': bars[pivot]['d'], 'status': 'CANCELLED_NO_FRESH_CAUSAL_OB'}
    status, nodes = lifecycle(bars, e1, origin)
    result = {
        **base, 'observation_start_date': bars[e0]['d'], 'pre_event_swing_pivot_date': bars[pivot]['d'],
        'pre_event_swing_confirm_date': bars[pivot + 3]['d'], 'pre_event_swing_high': bars[pivot]['h'],
        'displacement_date': bars[e1]['d'], 'origin_date': bars[origin]['d'], 'origin_low': bars[origin]['l'],
        'origin_open': bars[origin]['o'], 'status': status,
    }
    if status == 'VALID_CHAIN':
        result.update({
            'first_touch_date': bars[nodes['first_touch']]['d'], 'first_touch_low': bars[nodes['first_touch']]['l'],
            'reclaim_date': bars[nodes['reclaim']]['d'], 'hold_date': bars[nodes['hold']]['d'],
            'hold_high': bars[nodes['hold']]['h'], 'planned_entry_date': bars[nodes['entry']]['d'],
        })
    return result


def cancel_overlaps(records: list[dict]) -> None:
    by_symbol: dict[str, list[dict]] = {}
    for record in records:
        by_symbol.setdefault(record['symbol'], []).append(record)
    for group in by_symbol.values():
        events = sorted(group, key=lambda row: (row.get('observation_start_date', '99999999'), row['announcement_id']))
        for current in events:
            if current['status'] != 'VALID_CHAIN':
                continue
            later_starts = [row.get('observation_start_date', '') for row in events if row.get('observation_start_date', '') > current['observation_start_date']]
            if any(start <= current['planned_entry_date'] for start in later_starts):
                current['status'] = 'CANCELLED_LATER_CANONICAL_EVENT_BEFORE_ENTRY'
    seen: set[tuple[str, str]] = set()
    for record in sorted((row for row in records if row['status'] == 'VALID_CHAIN'), key=lambda row: (row['planned_entry_date'], row['symbol'], row['announcement_id'])):
        identity = record['symbol'], record['planned_entry_date']
        if identity in seen:
            record['status'] = 'CANCELLED_DUPLICATE_SYMBOL_ENTRY_DATE'
        else:
            seen.add(identity)


def main() -> None:
    prereg, source_audit = json.loads(PREREG.read_text()), json.loads(SOURCE_AUDIT.read_text())
    if not prereg['decision'].startswith('V638_PREREGISTRATION_COMPLETE'):
        raise RuntimeError('V638 preregistration is not authorizing seeds')
    if not source_audit['authorization']['outcome_blind_seed_generation']:
        raise RuntimeError('V639 source audit does not authorize seeds')
    events = list(csv.DictReader(CATALOG.open(encoding='utf-8')))
    grouped: dict[str, list[dict]] = {}
    for event in events:
        grouped.setdefault(event['symbol'], []).append(event)
    records = []
    for symbol, group in sorted(grouped.items()):
        bars = load_bars(symbol)
        records.extend(candidate(event, bars) for event in sorted(group, key=lambda row: (row['publication_time'], row['announcement_id'])))
    cancel_overlaps(records)
    fields = sorted({key for record in records for key in record})
    valid = [record for record in records if record['status'] == 'VALID_CHAIN']
    seed_years = Counter(record['notice_date'][:4] for record in valid)
    support = prereg['outcome_blind_seed_contract']['support_gate_before_execution_replay']
    support_pass = len(valid) >= support['valid_seed_total_min'] and len({record['symbol'] for record in valid}) >= support['unique_symbols_min'] and all(seed_years[year] >= support['valid_seed_each_event_year_min'] for year in support['source_event_years'])
    OUT.mkdir(parents=True, exist_ok=False)
    lifecycle_path, seed_path = OUT / 'v640_lifecycle_records.csv', OUT / 'v640_valid_seeds.csv'
    for path, items in ((lifecycle_path, records), (seed_path, valid)):
        with path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
            writer.writeheader(); writer.writerows(items)
    report = {
        'version': 'V640_TURNAROUND_POST_DISCLOSURE_SEED_NO_OUTCOME', 'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'V638 outcome-blind event-to-response lifecycle only. No trade, outcome, PnL, MFE, MAE, exit, stop, target or replay file was read.',
        'preregistration': str(PREREG), 'source_audit': str(SOURCE_AUDIT), 'event_denominator': len(events),
        'lifecycle_statuses': dict(Counter(record['status'] for record in records)), 'valid_seed_count': len(valid),
        'valid_seed_event_years': {year: seed_years[year] for year in YEARS}, 'valid_seed_unique_symbols': len({record['symbol'] for record in valid}),
        'support_gate': {**support, 'pass': support_pass},
        'decision': 'SEED_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED__NO_REPLAY_YET' if support_pass else 'SEED_SUPPORT_FAIL__CLOSE_V638_ONTOLOGY_NO_ORACLE_NO_REPLAY',
        'artifacts': {'dir': str(OUT), 'lifecycle_records': str(lifecycle_path), 'valid_seeds': str(seed_path)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v640_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__':
    main()
