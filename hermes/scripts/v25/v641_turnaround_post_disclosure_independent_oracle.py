#!/usr/bin/env python3
"""V641 independent raw-bar identity Oracle for V638; intentionally does not import V640."""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD, KDIR = ROOT / 'smc_audit', ROOT / 'kline_cache'
PREREG = AUD / 'v638_turnaround_post_disclosure_smc_response_ontology_preregistration.json'
SEED_REPORT = AUD / 'v640_turnaround_post_disclosure_outcome_blind_seed_latest.json'
EVENTS = AUD / 'v636_current_forecast_turnaround_semantic_catalog_no_outcome_20260726_115224/v636_current_forecast_turnaround_events.csv'
OUT = AUD / f'v641_turnaround_post_disclosure_independent_oracle_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v641_turnaround_post_disclosure_independent_oracle_latest.json'


def load(symbol: str) -> list[dict]:
    code, ex = symbol.split('.')
    raw = json.loads((KDIR / f'{code}_{ex}_daily_750.json').read_text())
    return sorted([{'d': str(x.get('t', x.get('date')))[:8], 'O': float(x['o']), 'H': float(x['h']), 'L': float(x['l']), 'C': float(x['c'])} for x in raw], key=lambda x: x['d'])


def observed_at(data: list[dict], published: str) -> int | None:
    stamp = datetime.strptime(published[:19], '%Y-%m-%d %H:%M:%S')
    return next((i for i, b in enumerate(data) if datetime.strptime(b['d'] + '150000', '%Y%m%d%H%M%S') > stamp), None)


def high_pivots(data: list[dict], known: int) -> list[int]:
    return [i for i in range(3, known - 2) if all(data[i]['H'] > data[j]['H'] for j in range(i - 3, i)) and all(data[i]['H'] > data[j]['H'] for j in range(i + 1, i + 4))]


def unbroken(data: list[dict], pivot: int, through: int) -> bool:
    return all(data[j]['H'] < data[pivot]['H'] for j in range(pivot + 1, through + 1))


def desired_target(data: list[dict], hold: int, entry: int) -> float | None:
    threshold = max(data[hold]['H'], data[entry]['O'])
    prices = [data[p]['H'] for p in high_pivots(data, hold) if data[p]['H'] > threshold and unbroken(data, p, hold)]
    return min(prices) if prices else None


def scan(event: dict, data: list[dict], first: int, cutoff: int) -> dict | None:
    if first is None or first >= cutoff:
        return None
    pivots = high_pivots(data, first)
    response = None
    swing = None
    for e1 in range(first, min(first + 20, cutoff, len(data))):
        b = data[e1]
        body, total = b['C'] - b['O'], b['H'] - b['L']
        if body <= 0 or total <= 0 or body / total < .60 or (b['C'] - b['L']) / total < .75:
            continue
        available = [p for p in pivots if b['C'] > data[p]['H'] and unbroken(data, p, e1 - 1)]
        if available:
            response, swing = e1, max(available, key=lambda p: data[p]['H'])
            break
    if response is None:
        return None
    bearish = [j for j in range(max(first, response - 10), response) if data[j]['C'] < data[j]['O']]
    if not bearish:
        return None
    origin = bearish[-1]
    zl, zh = data[origin]['L'], data[origin]['O']
    if any(data[j]['L'] <= zh or data[j]['C'] < zl for j in range(origin + 1, response)):
        return None
    touch = None
    for j in range(response + 1, min(response + 16, cutoff, len(data))):
        b = data[j]
        if b['C'] < zl:
            return None
        if b['L'] <= zh <= b['H'] or b['L'] <= zl <= b['H'] or (b['L'] <= zh and b['H'] >= zl):
            touch = j
            break
    if touch is None or data[touch]['C'] < zl:
        return None
    accept = None
    for j in range(touch + 1, min(touch + 4, cutoff, len(data))):
        b = data[j]
        if b['C'] < zl or (b['L'] <= zh and b['H'] >= zl):
            return None
        if b['C'] > zh:
            accept = j
            break
    if accept is None:
        return None
    hold, entry = accept + 1, accept + 2
    if entry >= cutoff or entry >= len(data) or data[hold]['C'] <= zh:
        return None
    stop = min(zl, data[touch]['L']) * .995
    tgt = desired_target(data, hold, entry)
    if tgt is None or data[entry]['O'] <= stop or data[entry]['O'] >= tgt:
        return None
    rr = (tgt - data[entry]['O']) / (data[entry]['O'] - stop)
    if rr < 1.5:
        return None
    return {'symbol': event['symbol'], 'announcement_id': event['announcement_id'], 'displacement_date': data[response]['d'], 'origin_date': data[origin]['d'], 'first_touch_date': data[touch]['d'], 'reclaim_date': data[accept]['d'], 'hold_date': data[hold]['d'], 'planned_entry_date': data[entry]['d'], 'origin_low': f'{zl:.6f}', 'origin_open': f'{zh:.6f}', 'stop': f'{stop:.6f}', 'target': f'{tgt:.6f}', 'planned_rr': f'{rr:.6f}', 'pre_event_swing_pivot_date': data[swing]['d'], 'pre_event_swing_confirm_date': data[swing + 3]['d']}


def key(row: dict) -> tuple:
    return tuple(row[k] for k in ('symbol', 'announcement_id', 'displacement_date', 'origin_date', 'first_touch_date', 'reclaim_date', 'hold_date', 'planned_entry_date'))


def main() -> None:
    prereg, source = json.loads(PREREG.read_text()), json.loads(SEED_REPORT.read_text())
    if prereg['version'] != 'V638_TURNAROUND_POST_DISCLOSURE_SMC_RESPONSE_ONTOLOGY_PREREGISTRATION':
        raise RuntimeError('V638 preregistration unavailable')
    with open(source['artifacts']['valid_seeds'], newline='', encoding='utf-8') as handle:
        expected_rows = list(csv.DictReader(handle))
    with EVENTS.open(newline='', encoding='utf-8') as handle:
        events = list(csv.DictReader(handle))
    grouped: dict[str, list[dict]] = {}
    for event in events:
        grouped.setdefault(event['symbol'], []).append(event)
    actual_rows = []
    for symbol, items in sorted(grouped.items()):
        data = load(symbol)
        indexed = [(event, observed_at(data, event['publication_time'])) for event in sorted(items, key=lambda row: (row['publication_time'], row['announcement_id']))]
        for i, (event, start) in enumerate(indexed):
            next_start = indexed[i + 1][1] if i + 1 < len(indexed) and indexed[i + 1][1] is not None else len(data)
            result = scan(event, data, start, next_start)
            if result is not None:
                actual_rows.append(result)
    expected, actual = {key(row): row for row in expected_rows}, {key(row): row for row in actual_rows}
    common = expected.keys() & actual.keys()
    node_fields = ('origin_low', 'origin_open', 'stop', 'target', 'planned_rr', 'pre_event_swing_pivot_date', 'pre_event_swing_confirm_date')
    differences = [{'seed': list(k), 'fields': [f for f in node_fields if expected[k].get(f) != actual[k].get(f)]} for k in sorted(common) if any(expected[k].get(f) != actual[k].get(f) for f in node_fields)]
    dupes = len(actual_rows) - len(actual)
    OUT.mkdir(parents=True, exist_ok=False)
    with (OUT / 'v641_oracle_valid_seeds.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(actual_rows[0]) if actual_rows else ['symbol']); writer.writeheader(); writer.writerows(actual_rows)
    report = {'version': 'V641_TURNAROUND_POST_DISCLOSURE_INDEPENDENT_ORACLE_NO_OUTCOME', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False, 'scope': 'Independent V638 raw-bar reconstruction. It reads no trade/outcome/PnL/exit file and no OHLCV after a candidate planned entry date.', 'generator_valid_seed_count': len(expected), 'oracle_valid_seed_count': len(actual), 'missing_seed_identities': len(expected.keys() - actual.keys()), 'extra_seed_identities': len(actual.keys() - expected.keys()), 'node_date_or_price_mismatches': len(differences), 'duplicate_symbol_planned_entry_date': dupes, 'sample_differences': differences[:10], 'oracle_pass': not (expected.keys() - actual.keys() or actual.keys() - expected.keys() or differences or dupes), 'support_gate_pass': source['support_gate']['pass'], 'decision': 'V641_ORACLE_PASS_BUT_V640_SUPPORT_FAIL__CLOSE_V638_ONTOLOGY__NO_REPLAY_OR_PRODUCTION' if not (expected.keys() - actual.keys() or actual.keys() - expected.keys() or differences or dupes) else 'V641_ORACLE_MISMATCH__CLOSE_V638_ONTOLOGY__NO_REPLAY_OR_PRODUCTION', 'artifacts': {'dir': str(OUT), 'oracle_seeds': str(OUT / 'v641_oracle_valid_seeds.csv'), 'generator': str(SEED_REPORT)}}
    text = json.dumps(report, ensure_ascii=False, indent=2); (OUT / 'v641_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__':
    main()
