#!/usr/bin/env python3
"""V598 outcome-blind PIT contract-award -> demand-OB retest seeds."""
from __future__ import annotations

import csv
import json
import math
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
DAILY = ROOT / 'kline_cache'
CATALOG = AUDIT / 'v596_contract_award_event_catalog_latest.json'
PRE = AUDIT / 'v597_contract_award_demand_retest_preregistration_latest.json'
LATEST = AUDIT / 'v598_contract_award_demand_retest_seed_latest.json'
OUT = AUDIT / f'v598_contract_award_demand_retest_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
YEARS = ('2024', '2025')


def d8(value: object) -> str:
    digits = ''.join(char for char in str(value or '') if char.isdigit())
    return digits[:8] if len(digits) >= 8 else ''


def positive(value: object) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def events(catalog: dict) -> list[dict]:
    source = Path(catalog['artifacts']['events'])
    canonical: dict[tuple[str, str], dict] = {}
    with source.open(encoding='utf-8') as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            symbol, date = str(item.get('symbol') or ''), d8(item.get('notice_date'))
            if len(symbol) != 9 or date[:4] not in YEARS:
                continue
            row = {
                'symbol': symbol,
                'announcement_id': str(item.get('announcement_id') or ''),
                'event_date': date,
                'publication_time': str(item.get('publication_time') or ''),
                'title': str(item.get('title') or ''),
                'matched_terms': '|'.join(item.get('matched_terms') or []),
                'external_event': 'PIT_CONTRACT_AWARD',
            }
            canonical.setdefault((symbol, date), row)
    return sorted(canonical.values(), key=lambda row: (row['symbol'], row['event_date'], row['announcement_id']))


def bars(symbol: str) -> list[dict]:
    path = DAILY / f'{symbol.replace(".", "_")}_daily_750.json'
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    result = []
    for item in raw if isinstance(raw, list) else []:
        date = d8(item.get('t') or item.get('date'))
        values = [positive(item.get(key)) for key in ('o', 'h', 'l', 'c')]
        if len(date) == 8 and all(value is not None for value in values):
            result.append({'d': date, 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3]})
    return sorted(result, key=lambda row: row['d'])


def confirmed_highs(rows: list[dict], end: int) -> list[tuple[int, int]]:
    found = []
    for index in range(3, end - 3):
        if rows[index]['h'] > max(x['h'] for x in rows[index - 3:index]) and rows[index]['h'] >= max(x['h'] for x in rows[index + 1:index + 4]):
            found.append((index, index + 3))
    return found


def first_response(event: dict, rows: list[dict]) -> tuple[str, dict | None]:
    dates = [row['d'] for row in rows]
    start = bisect_right(dates, event['event_date'])
    if start >= len(rows):
        return 'NO_RESPONSE_SESSION', None
    for break_i in range(start, min(start + 30, len(rows))):
        known = [(i, confirm) for i, confirm in confirmed_highs(rows, break_i + 1) if confirm < break_i and rows[i]['h'] < rows[break_i]['c']]
        if not known:
            continue
        bsl_i, bsl_confirm_i = known[-1]
        bearish = [i for i in range(start, break_i + 1) if rows[i]['c'] < rows[i]['o']]
        if not bearish:
            continue
        poi_i = bearish[-1]
        zone_low, zone_high = rows[poi_i]['l'], rows[poi_i]['o']
        for reclaim_i in range(break_i + 1, min(break_i + 16, len(rows))):
            bar = rows[reclaim_i]
            if bar['l'] <= zone_high and bar['h'] >= zone_low and bar['c'] >= zone_high and reclaim_i + 1 < len(rows):
                entry_i = reclaim_i + 1
                return 'SEED', {
                    **event,
                    'response_start_date': rows[start]['d'],
                    'bsl_anchor_date': rows[bsl_i]['d'],
                    'bsl_anchor_confirm_date': rows[bsl_confirm_i]['d'],
                    'bsl_break_date': rows[break_i]['d'],
                    'poi_date': rows[poi_i]['d'],
                    'zone_low': round(zone_low, 6),
                    'zone_high': round(zone_high, 6),
                    'reclaim_date': rows[reclaim_i]['d'],
                    'planned_entry_date': rows[entry_i]['d'],
                    'causal_path': 'PIT_CONTRACT_AWARD>CONFIRMED_BSL_ACCEPTANCE>DEMAND_OB_RETEST_RECLAIM>NEXT_OPEN',
                }
    return 'NO_COMPLETED_DEMAND_RETEST', None


def main() -> None:
    catalog = json.loads(CATALOG.read_text())
    preregistration = json.loads(PRE.read_text())
    if catalog['decision'] != 'SOURCE_CATALOG_COMPLETE__SEMANTIC_PREREGISTRATION_NEXT':
        raise RuntimeError('V596 complete source catalog required')
    if preregistration['decision'] != 'PREREGISTRATION_COMPLETE__OUTCOME_BLIND_SEED_GENERATION_AUTHORIZED':
        raise RuntimeError('V597 preregistration required')
    OUT.mkdir(parents=True, exist_ok=False)
    source = events(catalog)
    grouped: defaultdict[str, list[dict]] = defaultdict(list)
    for event in source:
        grouped[event['symbol']].append(event)
    all_rows = []
    for number, (symbol, event_rows) in enumerate(sorted(grouped.items()), 1):
        stock_bars = bars(symbol)
        for event in event_rows:
            status, seed = first_response(event, stock_bars)
            row = {**event, 'seed_status': status}
            if seed:
                row.update(seed)
            all_rows.append(row)
        if number % 500 == 0:
            print(json.dumps({'symbols': number, 'events_processed': len(all_rows)}, ensure_ascii=False), flush=True)
    candidates = [row for row in all_rows if row['seed_status'] == 'SEED' and row['planned_entry_date'][:4] in YEARS]
    canonical: dict[tuple[str, str], dict] = {}
    for row in sorted(candidates, key=lambda item: (item['symbol'], item['planned_entry_date'], item['event_date'], item['announcement_id'])):
        canonical.setdefault((row['symbol'], row['planned_entry_date']), row)
    seeds = sorted(canonical.values(), key=lambda row: (row['planned_entry_date'], row['symbol']))
    fields = sorted({key for row in all_rows for key in row} | {key for row in seeds for key in row})
    for name, rows in (('v598_all_contract_events.csv', all_rows), ('v598_outcome_blind_seeds.csv', seeds)):
        with (OUT / name).open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
    years = {year: sum(row['planned_entry_date'].startswith(year) for row in seeds) for year in YEARS}
    checks = {'canonical_seed_total': len(seeds) >= 1000, 'canonical_seed_each_year': all(years[year] >= 300 for year in YEARS), 'unique_symbols': len({row['symbol'] for row in seeds}) >= 500}
    invariants = {
        'no_outcome_or_trade_files_read': True,
        'all_events_precede_response': all(row['event_date'] < row['response_start_date'] for row in seeds),
        'all_bsl_anchors_confirmed_before_break': all(row['bsl_anchor_confirm_date'] < row['bsl_break_date'] for row in seeds),
        'all_causal_nodes_before_entry': all(row['event_date'] < row['bsl_break_date'] < row['reclaim_date'] < row['planned_entry_date'] for row in seeds),
        'one_seed_per_symbol_entry_date': len(seeds) == len({(row['symbol'], row['planned_entry_date']) for row in seeds}),
    }
    passed = all(checks.values()) and all(invariants.values())
    report = {
        'version': 'V598_CONTRACT_AWARD_DEMAND_RETEST_SEED_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'input_contract': 'V596 immutable contract-award metadata plus daily OHLC only through planned entry; no outcome/trade/PnL/exit/MFE/MAE file read.',
        'raw_canonical_event_count': len(source),
        'raw_canonical_event_years': {year: sum(row['event_date'].startswith(year) for row in source) for year in YEARS},
        'seed_status_counts': dict(Counter(row['seed_status'] for row in all_rows)),
        'canonical_seed_count': len(seeds), 'canonical_seed_years': years, 'unique_symbols': len({row['symbol'] for row in seeds}),
        'support_checks': checks, 'invariants': invariants,
        'decision': 'V598_SUPPORT_PASS__INDEPENDENT_RAW_ORACLE_REQUIRED' if passed else 'V598_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_ONTOLOGY',
        'artifacts': {'out_dir': str(OUT), 'all_events': str(OUT / 'v598_all_contract_events.csv'), 'seeds': str(OUT / 'v598_outcome_blind_seeds.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v598_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
