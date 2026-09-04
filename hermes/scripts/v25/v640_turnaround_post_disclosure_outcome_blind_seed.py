#!/usr/bin/env python3
"""V640: frozen V638 outcome-blind seed generator; it never reads post-entry bars."""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
KDIR = ROOT / 'kline_cache'
PREREG = AUD / 'v638_turnaround_post_disclosure_smc_response_ontology_preregistration.json'
SOURCE_AUDIT = AUD / 'v639_turnaround_event_universe_daily_ohlcv_source_audit_no_outcome.json'
EVENTS = AUD / 'v636_current_forecast_turnaround_semantic_catalog_no_outcome_20260726_115224/v636_current_forecast_turnaround_events.csv'
OUT = AUD / f'v640_turnaround_post_disclosure_outcome_blind_seed_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v640_turnaround_post_disclosure_outcome_blind_seed_latest.json'


def sym_path(symbol: str) -> Path:
    code, exchange = symbol.split('.')
    return KDIR / f'{code}_{exchange}_daily_750.json'


def bars(symbol: str) -> list[dict]:
    raw = json.loads(sym_path(symbol).read_text())
    result = []
    for x in raw:
        try:
            row = {'t': str(x.get('t', x.get('date')))[:8], **{k: float(x[k]) for k in ('o', 'h', 'l', 'c')}}
        except (KeyError, TypeError, ValueError):
            continue
        if len(row['t']) == 8 and all(row[k] > 0 for k in ('o', 'h', 'l', 'c')):
            result.append(row)
    return sorted(result, key=lambda row: row['t'])


def close_after_publication(rows: list[dict], publication_time: str) -> int | None:
    published = datetime.strptime(publication_time[:19], '%Y-%m-%d %H:%M:%S')
    for i, row in enumerate(rows):
        closed = datetime.strptime(row['t'] + ' 15:00:00', '%Y%m%d %H:%M:%S')
        if closed > published:
            return i
    return None


def confirmed_highs(rows: list[dict], available_through: int) -> list[tuple[int, float]]:
    pivots = []
    for i in range(3, available_through - 2):
        if rows[i]['h'] > max(rows[j]['h'] for j in range(i - 3, i)) and all(rows[j]['h'] < rows[i]['h'] for j in range(i + 1, i + 4)):
            pivots.append((i, rows[i]['h']))
    return pivots


def target(rows: list[dict], hold: int, entry: int, entry_open: float) -> float | None:
    floor = max(entry_open, rows[hold]['h'])
    choices = []
    for pivot, level in confirmed_highs(rows, hold):
        if level <= floor:
            continue
        if any(rows[j]['h'] >= level for j in range(pivot + 1, hold + 1)):
            continue
        choices.append(level)
    return min(choices) if choices else None


def invalid(row: dict, reason: str) -> dict:
    return {**row, 'status': 'REJECTED', 'reason': reason}


def one_event(event: dict, rows: list[dict], start: int, boundary: int) -> dict:
    """Build one causal chain using only rows up to its planned entry open."""
    end_e1 = min(start + 19, boundary - 1, len(rows) - 1)
    if start >= boundary or start >= len(rows):
        return invalid(event, 'NO_OBSERVABLE_RESPONSE_SESSION')
    pivots = confirmed_highs(rows, start)
    e1, break_swing = None, None
    for i in range(start, end_e1 + 1):
        bar = rows[i]
        crossed = [(p, h) for p, h in pivots if h < bar['c'] and not any(rows[j]['h'] >= h for j in range(p + 1, i))]
        if not crossed:
            continue
        span = bar['h'] - bar['l']
        if bar['c'] > bar['o'] and span > 0 and (bar['c'] - bar['o']) / span >= .60 and (bar['c'] - bar['l']) / span >= .75:
            e1, break_swing = i, max(crossed, key=lambda pair: pair[1])
            break
    if e1 is None:
        return invalid(event, 'NO_POST_DISCLOSURE_DISPLACEMENT_BREAK')
    origins = [i for i in range(max(start, e1 - 10), e1) if rows[i]['c'] < rows[i]['o']]
    if not origins:
        return invalid(event, 'NO_CAUSAL_BEARISH_OB')
    origin = origins[-1]
    low, upper = rows[origin]['l'], rows[origin]['o']
    if any(rows[j]['l'] <= upper or rows[j]['c'] < low for j in range(origin + 1, e1)):
        return invalid(event, 'OB_PRE_E1_MITIGATED_OR_INVALIDATED')
    touch = None
    maximum_touch = min(e1 + 15, boundary - 1, len(rows) - 1)
    for i in range(e1 + 1, maximum_touch + 1):
        bar = rows[i]
        if bar['c'] < low:
            return invalid(event, 'ZONE_CLOSED_BELOW_LOW_BEFORE_TOUCH')
        if bar['l'] <= upper and bar['h'] >= low:
            if bar['c'] < low:
                return invalid(event, 'TOUCH_CLOSES_BELOW_LOW')
            touch = i
            break
    if touch is None:
        return invalid(event, 'NO_FIRST_TOUCH_WITHIN_15')
    reclaim = None
    for i in range(touch + 1, min(touch + 3, boundary - 1, len(rows) - 1) + 1):
        bar = rows[i]
        if bar['c'] < low:
            return invalid(event, 'ZONE_CLOSED_BELOW_LOW_BEFORE_RECLAIM')
        if bar['l'] <= upper and bar['h'] >= low:
            return invalid(event, 'SECOND_TOUCH_BEFORE_RECLAIM')
        if bar['c'] > upper:
            reclaim = i
            break
    if reclaim is None:
        return invalid(event, 'NO_RECLAIM_1_TO_3_AFTER_TOUCH')
    hold = reclaim + 1
    if hold >= boundary or hold >= len(rows) or rows[hold]['c'] <= upper:
        return invalid(event, 'HOLD_FAILURE')
    entry = hold + 1
    if entry >= boundary or entry >= len(rows):
        return invalid(event, 'NO_PLANNED_ENTRY_SESSION')
    entry_open = rows[entry]['o']
    stop = min(low, rows[touch]['l']) * .995
    price_target = target(rows, hold, entry, entry_open)
    if price_target is None:
        return invalid(event, 'NO_PREENTRY_UNCONSUMED_STRUCTURAL_TARGET')
    risk = entry_open - stop
    planned_rr = (price_target - entry_open) / risk if risk > 0 else None
    if entry_open <= stop:
        return invalid(event, 'ENTRY_OPEN_AT_OR_BELOW_STOP')
    if entry_open >= price_target:
        return invalid(event, 'ENTRY_OPEN_AT_OR_ABOVE_TARGET')
    if planned_rr is None or planned_rr < 1.5:
        return invalid(event, 'PLANNED_RR_BELOW_1_5')
    return {
        **event, 'status': 'VALID', 'reason': 'VALID',
        'observation_start_date': rows[start]['t'], 'pre_event_swing_pivot_date': rows[break_swing[0]]['t'],
        'pre_event_swing_confirm_date': rows[break_swing[0] + 3]['t'], 'displacement_date': rows[e1]['t'], 'origin_date': rows[origin]['t'], 
        'origin_low': f'{low:.6f}', 'origin_open': f'{upper:.6f}', 'first_touch_date': rows[touch]['t'],
        'first_touch_low': f"{rows[touch]['l']:.6f}", 'reclaim_date': rows[reclaim]['t'], 'hold_date': rows[hold]['t'],
        'planned_entry_date': rows[entry]['t'], 'planned_entry_open': f'{entry_open:.6f}', 'stop': f'{stop:.6f}',
        'target': f'{price_target:.6f}', 'planned_rr': f'{planned_rr:.6f}',
    }


def main() -> None:
    prereg, source = json.loads(PREREG.read_text()), json.loads(SOURCE_AUDIT.read_text())
    if prereg['decision'] != 'V638_PREREGISTRATION_COMPLETE__OUTCOME_BLIND_SEED_GENERATION_AND_INDEPENDENT_ORACLE_ARE_THE_ONLY_NEXT_PERMITTED_ACTIONS__NO_PRODUCTION':
        raise RuntimeError('V638 preregistration missing')
    if source['decision'] != 'EVENT_UNIVERSE_SOURCE_PASS__V638_OUTCOME_BLIND_SEED_GENERATION_AUTHORIZED__NO_FULL_MARKET_OR_PRODUCTION_AUTHORIZATION':
        raise RuntimeError('V639 source qualification missing')
    with EVENTS.open(newline='', encoding='utf-8') as handle:
        events = list(csv.DictReader(handle))
    grouped: dict[str, list[dict]] = {}
    for event in events:
        grouped.setdefault(event['symbol'], []).append(event)
    records = []
    for symbol, symbol_events in sorted(grouped.items()):
        rows = bars(symbol)
        indexed = [(event, close_after_publication(rows, event['publication_time'])) for event in sorted(symbol_events, key=lambda x: (x['publication_time'], x['announcement_id']))]
        for pos, (event, start) in enumerate(indexed):
            boundary = indexed[pos + 1][1] if pos + 1 < len(indexed) and indexed[pos + 1][1] is not None else len(rows)
            records.append(one_event(event, rows, start if start is not None else len(rows), boundary))
    valid = [row for row in records if row['status'] == 'VALID']
    event_year = Counter(row['notice_date'][:4] for row in valid)
    gate = prereg['outcome_blind_seed_contract']['support_gate_before_execution_replay']
    support = len(valid) >= gate['valid_seed_total_min'] and all(event_year[y] >= gate['valid_seed_each_year_min'] for y in gate['source_event_years']) and len({x['symbol'] for x in valid}) >= gate['unique_symbols_min']
    OUT.mkdir(parents=True, exist_ok=False)
    fields = sorted({key for row in records for key in row})
    for name, rows_to_write in [('v640_all_event_paths.csv', records), ('v640_valid_seeds.csv', valid)]:
        with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore'); writer.writeheader(); writer.writerows(rows_to_write)
    report = {
        'version': 'V640_TURNAROUND_POST_DISCLOSURE_OUTCOME_BLIND_SEED', 'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'V638 causal nodes only. No trade/outcome/PnL/exit file and no OHLCV after each planned entry date was used.',
        'events_total': len(events), 'paths_by_status': Counter(row['status'] for row in records), 'rejections_by_reason': Counter(row['reason'] for row in records if row['status'] != 'VALID'),
        'valid_seed_total': len(valid), 'valid_seed_event_years': dict(event_year), 'valid_seed_unique_symbols': len({x['symbol'] for x in valid}),
        'support_gate': {**gate, 'pass': support},
        'decision': 'V640_SEED_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED__NO_REPLAY_YET' if support else 'V640_SEED_SUPPORT_FAIL__CLOSE_V638_ONTOLOGY__NO_ORACLE_REPLAY_OR_PRODUCTION',
        'artifacts': {'dir': str(OUT), 'all_paths': str(OUT / 'v640_all_event_paths.csv'), 'valid_seeds': str(OUT / 'v640_valid_seeds.csv')},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2, default=dict)
    (OUT / 'v640_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__':
    main()
