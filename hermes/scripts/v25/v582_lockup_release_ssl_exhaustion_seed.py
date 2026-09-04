#!/usr/bin/env python3
"""V582 outcome-blind lockup-release -> SSL exhaustion -> bullish reversal seeds.

Reads only PIT announcement metadata and daily OHLC through each planned entry.
No outcome, trade, PnL, MFE, MAE, or exit data is opened.
"""
from __future__ import annotations

import csv
import json
import math
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
DAILY = ROOT / 'kline_cache'
METADATA = AUDIT / 'v563_pit_event_archive_full_coverage_no_outcome_20260724_124935' / 'v563_event_metadata.jsonl'
PRE = AUDIT / 'v581_lockup_release_sell_side_exhaustion_preregistration_latest.json'
LATEST = AUDIT / 'v582_lockup_release_ssl_exhaustion_seed_latest.json'
OUT = AUDIT / f'v582_lockup_release_ssl_exhaustion_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
YEARS = ('2023', '2024', '2025')
SUPPORT = {'raw_external_events_min': 6000, 'canonical_seed_total_min': 800,
           'canonical_seed_each_year_min': 150, 'unique_symbols_min': 300}


def positive(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def date8(value: Any) -> str:
    text = str(value or '')
    digits = ''.join(char for char in text if char.isdigit())
    return digits[:8] if len(digits) >= 8 else ''


def lockup_events() -> list[dict[str, Any]]:
    """Source-only event extractor; title rule is frozen in V581."""
    rows: list[dict[str, Any]] = []
    with METADATA.open(encoding='utf-8') as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            title = str(item.get('title') or '')
            event_date = date8(item.get('notice_date'))
            symbol = str(item.get('symbol') or '')
            if (item.get('kind') != 'LOCKUP' or event_date[:4] not in YEARS or
                    '限售' not in title or not any(token in title for token in ('解除限售', '解禁', '上市流通')) or
                    len(symbol) != 9 or symbol[6] != '.'):
                continue
            rows.append({
                'symbol': symbol,
                'announcement_id': str(item.get('announcement_id') or ''),
                'event_date': event_date,
                'publication_time': str(item.get('publication_time') or ''),
                'external_event': 'LOCKUP_RELEASE_SUPPLY_EVENT',
                'title': title,
            })
    # Announcement pages frequently have a company notice and a broker opinion for one event.
    # The frozen canonical event identity is the earliest source record per symbol/date.
    canonical: dict[tuple[str, str], dict[str, Any]] = {}
    for row in sorted(rows, key=lambda x: (x['symbol'], x['event_date'], x['announcement_id'])):
        canonical.setdefault((row['symbol'], row['event_date']), row)
    return sorted(canonical.values(), key=lambda x: (x['symbol'], x['event_date'], x['announcement_id']))


def daily_bars(symbol: str) -> list[dict[str, Any]]:
    path = DAILY / f'{symbol.replace(".", "_")}_daily_750.json'
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    rows: list[dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        date = date8(item.get('t') or item.get('date'))
        values = [positive(item.get(key)) for key in ('o', 'h', 'l', 'c')]
        if len(date) == 8 and all(value is not None for value in values):
            rows.append({'d': date, 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3]})
    return sorted(rows, key=lambda x: x['d'])


def confirmed_swings(rows: list[dict[str, Any]]) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """3L/3R pivots; confirmation index encodes information availability."""
    lows: list[tuple[int, int]] = []
    highs: list[tuple[int, int]] = []
    for index in range(3, len(rows) - 3):
        if rows[index]['l'] < min(row['l'] for row in rows[index - 3:index]) and rows[index]['l'] <= min(row['l'] for row in rows[index + 1:index + 4]):
            lows.append((index, index + 3))
        if rows[index]['h'] > max(row['h'] for row in rows[index - 3:index]) and rows[index]['h'] >= max(row['h'] for row in rows[index + 1:index + 4]):
            highs.append((index, index + 3))
    return lows, highs


def first_response(event: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
    dates = [row['d'] for row in rows]
    start = bisect_right(dates, event['event_date'])  # strict PIT: D itself forbidden
    if start >= len(rows):
        return 'NO_NEXT_RESPONSE_SESSION', None
    if start + 53 >= len(rows):
        return 'RIGHT_EDGE_UNOBSERVED', None
    # All candidate locations are decided solely by bars no later than planned entry.
    for sweep_index in range(start, min(start + 30, len(rows))):
        observed_lows, _ = confirmed_swings(rows[:sweep_index + 1])
        known_lows = [x for x in observed_lows if x[1] < sweep_index and rows[x[0]]['l'] > rows[sweep_index]['l'] and rows[sweep_index]['c'] > rows[x[0]]['l']]
        if not known_lows:
            continue
        ssl_index, ssl_confirm = known_lows[-1]
        for break_index in range(sweep_index + 1, min(sweep_index + 11, len(rows))):
            _, observed_highs = confirmed_swings(rows[:break_index + 1])
            known_highs = [x for x in observed_highs if x[1] < break_index and rows[x[0]]['h'] < rows[break_index]['c']]
            if not known_highs:
                continue
            bsl_index, bsl_confirm = known_highs[-1]
            bearish = [i for i in range(sweep_index, break_index + 1) if rows[i]['c'] < rows[i]['o']]
            if not bearish:
                continue
            poi_index = bearish[-1]
            zone_low, zone_high = rows[poi_index]['l'], rows[poi_index]['o']
            for reclaim_index in range(break_index + 1, min(break_index + 11, len(rows))):
                bar = rows[reclaim_index]
                if bar['l'] <= zone_high and bar['h'] >= zone_low and bar['c'] >= zone_high:
                    entry_index = reclaim_index + 1
                    if entry_index >= len(rows):
                        return 'ENTRY_UNOBSERVED', None
                    return 'SEED', {
                        **event,
                        'response_start_date': rows[start]['d'],
                        'ssl_anchor_date': rows[ssl_index]['d'],
                        'ssl_anchor_confirm_date': rows[ssl_confirm]['d'],
                        'ssl_sweep_date': rows[sweep_index]['d'],
                        'bsl_anchor_date': rows[bsl_index]['d'],
                        'bsl_anchor_confirm_date': rows[bsl_confirm]['d'],
                        'bsl_break_date': rows[break_index]['d'],
                        'poi_date': rows[poi_index]['d'],
                        'zone_low': round(zone_low, 6),
                        'zone_high': round(zone_high, 6),
                        'reclaim_date': rows[reclaim_index]['d'],
                        'planned_entry_date': rows[entry_index]['d'],
                        'causal_path': 'PIT_LOCKUP_RELEASE>CONFIRMED_SSL_SWEEP>CONFIRMED_BSL_BREAK>DEMAND_POI_RECLAIM>NEXT_OPEN',
                    }
    return 'NO_COMPLETED_ABSORPTION_REVERSAL', None


def main() -> None:
    preregistration = json.loads(PRE.read_text())
    assert preregistration['decision'] == 'PREREGISTRATION_COMPLETE__OUTCOME_BLIND_SEED_GENERATION_AUTHORIZED'
    OUT.mkdir(parents=True, exist_ok=False)
    events = lockup_events()
    by_symbol: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_symbol[event['symbol']].append(event)
    all_rows: list[dict[str, Any]] = []
    for n, (symbol, symbol_events) in enumerate(sorted(by_symbol.items()), 1):
        bars = daily_bars(symbol)
        for event in symbol_events:
            status, seed = first_response(event, bars)
            row = {**event, 'seed_status': status}
            if seed:
                row.update(seed)
            all_rows.append(row)
        if n % 500 == 0:
            print(json.dumps({'symbols': n, 'events_processed': len(all_rows)}, ensure_ascii=False), flush=True)
    candidates = [x for x in all_rows if x['seed_status'] == 'SEED' and x['planned_entry_date'][:4] in YEARS]
    canonical: dict[tuple[str, str], dict[str, Any]] = {}
    for row in sorted(candidates, key=lambda x: (x['symbol'], x['planned_entry_date'], x['event_date'], x['announcement_id'])):
        canonical.setdefault((row['symbol'], row['planned_entry_date']), row)
    seeds = sorted(canonical.values(), key=lambda x: (x['planned_entry_date'], x['symbol']))
    fields = sorted({key for row in all_rows for key in row} | {key for row in seeds for key in row})
    for name, source in (('v582_all_lockup_events.csv', all_rows), ('v582_outcome_blind_seeds.csv', seeds)):
        with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
            writer.writeheader(); writer.writerows(source)
    seed_years = {year: sum(x['planned_entry_date'].startswith(year) for x in seeds) for year in YEARS}
    invariants = {
        'no_outcome_or_trade_files_read': True,
        'all_external_events_before_response': all(x['event_date'] < x['response_start_date'] for x in seeds),
        'all_ssl_anchors_confirmed_before_sweep': all(x['ssl_anchor_confirm_date'] < x['ssl_sweep_date'] for x in seeds),
        'all_bsl_anchors_confirmed_before_break': all(x['bsl_anchor_confirm_date'] < x['bsl_break_date'] for x in seeds),
        'all_causal_nodes_before_entry': all(x['event_date'] < x['ssl_sweep_date'] < x['bsl_break_date'] < x['reclaim_date'] < x['planned_entry_date'] for x in seeds),
        'one_seed_per_symbol_entry_date': len(seeds) == len({(x['symbol'], x['planned_entry_date']) for x in seeds}),
        'raw_external_events_capacity': len(events) >= SUPPORT['raw_external_events_min'],
        'canonical_seed_capacity': len(seeds) >= SUPPORT['canonical_seed_total_min'],
        'each_year_seed_capacity': all(seed_years[year] >= SUPPORT['canonical_seed_each_year_min'] for year in YEARS),
        'unique_symbol_capacity': len({x['symbol'] for x in seeds}) >= SUPPORT['unique_symbols_min'],
    }
    support_pass = all(invariants[x] for x in ('raw_external_events_capacity', 'canonical_seed_capacity', 'each_year_seed_capacity', 'unique_symbol_capacity'))
    report = {
        'version': 'V582_LOCKUP_RELEASE_SSL_EXHAUSTION_SEED_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'input_contract': 'PIT lockup-release metadata plus daily OHLC only through planned entry; no outcome, trade, PnL, exit, MFE, or MAE file read.',
        'raw_lockup_event_count': len(events),
        'raw_event_years': dict(sorted(Counter(x['event_date'][:4] for x in events).items())),
        'status_counts': dict(Counter(x['seed_status'] for x in all_rows)),
        'canonical_seed_count': len(seeds), 'canonical_seed_years': seed_years, 'unique_symbols': len({x['symbol'] for x in seeds}),
        'support_gate': SUPPORT, 'invariants': invariants,
        'decision': 'V582_SUPPORT_PASS__INDEPENDENT_RAW_ORACLE_REQUIRED' if support_pass else 'V582_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_OBJECT',
        'artifacts': {'out_dir': str(OUT), 'all_events': str(OUT / 'v582_all_lockup_events.csv'), 'seeds': str(OUT / 'v582_outcome_blind_seeds.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v582_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
