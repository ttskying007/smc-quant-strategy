#!/usr/bin/env python3
"""V622: outcome-blind seeds for frozen V621 pledge-creation exhaustion ontology."""
from __future__ import annotations

import csv
import json
import math
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT, DAILY = ROOT / 'smc_audit', ROOT / 'kline_cache'
PRE = AUDIT / 'v621_controlling_pledge_creation_ssl_exhaustion_preregistration_latest.json'
CATALOG = AUDIT / 'v615_controlling_pledge_pit_event_catalog_latest.json'
LATEST = AUDIT / 'v622_controlling_pledge_creation_ssl_exhaustion_seed_latest.json'
OUT = AUDIT / f'v622_controlling_pledge_creation_ssl_exhaustion_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
YEARS = ('2023', '2024', '2025')


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


def event_rows(catalog: dict) -> list[dict]:
    canonical: dict[tuple[str, str], dict] = {}
    source = Path(catalog['artifacts']['events'])
    for line in source.open(encoding='utf-8'):
        try:
            item = json.loads(line)
        except ValueError:
            continue
        symbol, event_date = str(item.get('symbol') or ''), d8(item.get('notice_date'))
        if not (a_share(symbol) and event_date[:4] in YEARS and item.get('event_kind') == 'CONTROLLING_HOLDER_PLEDGE_CREATE'):
            continue
        row = {
            'symbol': symbol,
            'announcement_id': str(item.get('announcement_id') or ''),
            'event_date': event_date,
            'publication_time': str(item.get('publication_time') or ''),
            'title': str(item.get('title') or ''),
            'event_kind': 'CONTROLLING_HOLDER_PLEDGE_CREATE',
            'external_event': 'PIT_CONTROLLING_HOLDER_PLEDGE_CREATE',
        }
        canonical.setdefault((symbol, event_date), row)
    return sorted(canonical.values(), key=lambda row: (row['symbol'], row['event_date'], row['announcement_id']))


def bars(symbol: str) -> list[dict]:
    try:
        raw = json.loads((DAILY / f'{symbol.replace(".", "_")}_daily_750.json').read_text())
    except (OSError, ValueError):
        return []
    result = []
    for item in raw if isinstance(raw, list) else []:
        date = d8(item.get('t') or item.get('date'))
        values = [positive(item.get(key)) for key in ('o', 'h', 'l', 'c')]
        if len(date) == 8 and all(value is not None for value in values):
            result.append({'d': date, 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3]})
    return sorted(result, key=lambda row: row['d'])


def confirmed_lows(rows: list[dict], end: int) -> list[tuple[int, int]]:
    result = []
    for index in range(3, end - 3):
        if rows[index]['l'] < min(row['l'] for row in rows[index - 3:index]) and rows[index]['l'] <= min(row['l'] for row in rows[index + 1:index + 4]):
            result.append((index, index + 3))
    return result


def confirmed_lower_highs(rows: list[dict], end: int) -> list[tuple[int, int]]:
    pivots = []
    for index in range(3, end - 3):
        if rows[index]['h'] > max(row['h'] for row in rows[index - 3:index]) and rows[index]['h'] >= max(row['h'] for row in rows[index + 1:index + 4]):
            pivots.append((index, index + 3))
    return [(index, confirmed) for pos, (index, confirmed) in enumerate(pivots) if pos and rows[index]['h'] < rows[pivots[pos - 1][0]]['h']]


def seed_for(event: dict, rows: list[dict]) -> tuple[str, dict | None]:
    dates = [row['d'] for row in rows]
    start = bisect_right(dates, event['event_date'])
    if start >= len(rows):
        return 'NO_RESPONSE_SESSION', None
    for sweep_i in range(start, min(start + 30, len(rows))):
        ssl = [(index, confirmed) for index, confirmed in confirmed_lows(rows, sweep_i + 1) if confirmed < sweep_i and rows[sweep_i]['l'] < rows[index]['l'] and rows[sweep_i]['c'] > rows[index]['l']]
        if not ssl:
            continue
        ssl_i, ssl_confirm_i = ssl[-1]
        for break_i in range(sweep_i + 1, min(sweep_i + 16, len(rows))):
            lower_highs = [(index, confirmed) for index, confirmed in confirmed_lower_highs(rows, break_i + 1) if confirmed < sweep_i and rows[break_i]['c'] > rows[index]['h']]
            if not lower_highs:
                continue
            lh_i, lh_confirm_i = lower_highs[-1]
            bearish = [index for index in range(sweep_i, break_i + 1) if rows[index]['c'] < rows[index]['o']]
            if not bearish:
                continue
            poi_i = bearish[-1]
            low, high = rows[poi_i]['l'], rows[poi_i]['o']
            for reclaim_i in range(break_i + 1, min(break_i + 16, len(rows))):
                bar = rows[reclaim_i]
                if bar['l'] <= high and bar['h'] >= low and bar['c'] >= high and reclaim_i + 1 < len(rows):
                    entry_i = reclaim_i + 1
                    return 'SEED', {
                        **event,
                        'response_start_date': rows[start]['d'],
                        'ssl_anchor_date': rows[ssl_i]['d'],
                        'ssl_anchor_confirm_date': rows[ssl_confirm_i]['d'],
                        'ssl_sweep_date': rows[sweep_i]['d'],
                        'lower_high_date': rows[lh_i]['d'],
                        'lower_high_confirm_date': rows[lh_confirm_i]['d'],
                        'bullish_break_date': rows[break_i]['d'],
                        'poi_date': rows[poi_i]['d'],
                        'zone_low': round(low, 6),
                        'zone_high': round(high, 6),
                        'reclaim_date': rows[reclaim_i]['d'],
                        'planned_entry_date': rows[entry_i]['d'],
                        'causal_path': 'PIT_CONTROLLING_HOLDER_PLEDGE_CREATE>CONFIRMED_SSL_SWEEP>CONFIRMED_LH_BREAK>DEMAND_OB_RETEST_RECLAIM>NEXT_OPEN',
                    }
    return 'NO_COMPLETED_SSL_EXHAUSTION', None


def main() -> None:
    preregistration, catalog = json.loads(PRE.read_text()), json.loads(CATALOG.read_text())
    if preregistration['decision'] != 'PREREGISTRATION_COMPLETE__OUTCOME_BLIND_SEED_GENERATION_AUTHORIZED':
        raise RuntimeError('V621 preregistration required')
    if catalog['decision'] != 'SOURCE_CATALOG_COMPLETE__SEMANTIC_PREREGISTRATION_NEXT':
        raise RuntimeError('V615 catalog required')
    OUT.mkdir(parents=True, exist_ok=False)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in event_rows(catalog):
        grouped[event['symbol']].append(event)
    all_rows = []
    for number, (symbol, events) in enumerate(sorted(grouped.items()), 1):
        stock_bars = bars(symbol)
        for event in events:
            status, seed = seed_for(event, stock_bars)
            all_rows.append({**event, 'seed_status': status, **(seed or {})})
        if number % 500 == 0:
            print(json.dumps({'symbols': number, 'events_processed': len(all_rows)}), flush=True)
    candidates = [row for row in all_rows if row['seed_status'] == 'SEED' and row['planned_entry_date'][:4] in YEARS]
    canonical: dict[tuple[str, str], dict] = {}
    for row in sorted(candidates, key=lambda row: (row['symbol'], row['planned_entry_date'], row['event_date'], row['announcement_id'])):
        canonical.setdefault((row['symbol'], row['planned_entry_date']), row)
    seeds = sorted(canonical.values(), key=lambda row: (row['planned_entry_date'], row['symbol']))
    fields = sorted({key for row in all_rows for key in row} | {key for row in seeds for key in row})
    for name, data in [('v622_all_pledge_creation_events.csv', all_rows), ('v622_outcome_blind_seeds.csv', seeds)]:
        with (OUT / name).open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(data)
    years = {year: sum(row['planned_entry_date'].startswith(year) for row in seeds) for year in YEARS}
    checks = {'canonical_seed_total': len(seeds) >= 1000, 'canonical_seed_each_year': all(years[year] >= 300 for year in YEARS), 'unique_symbols': len({row['symbol'] for row in seeds}) >= 500}
    invariants = {
        'no_outcome_or_trade_files_read': True,
        'all_events_precede_response': all(row['event_date'] < row['response_start_date'] for row in seeds),
        'all_ssl_anchors_confirmed_before_sweep': all(row['ssl_anchor_confirm_date'] < row['ssl_sweep_date'] for row in seeds),
        'all_lower_highs_confirmed_before_sweep': all(row['lower_high_confirm_date'] < row['ssl_sweep_date'] for row in seeds),
        'all_causal_nodes_before_entry': all(row['event_date'] < row['ssl_sweep_date'] < row['bullish_break_date'] < row['reclaim_date'] < row['planned_entry_date'] for row in seeds),
        'one_seed_per_symbol_entry_date': len(seeds) == len({(row['symbol'], row['planned_entry_date']) for row in seeds}),
    }
    passed = all(checks.values()) and all(invariants.values())
    report = {
        'version': 'V622_CONTROLLING_HOLDER_PLEDGE_CREATION_SSL_EXHAUSTION_SEED_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'input_contract': 'V615 immutable controlling-holder pledge-creation metadata plus daily OHLC only through planned entry; no outcome/trade/PnL/exit/MFE/MAE file read.',
        'raw_canonical_event_count': len(event_rows(catalog)),
        'raw_canonical_event_years': {year: sum(row['event_date'].startswith(year) for row in event_rows(catalog)) for year in YEARS},
        'seed_status_counts': dict(Counter(row['seed_status'] for row in all_rows)),
        'canonical_seed_count': len(seeds),
        'canonical_seed_years': years,
        'unique_symbols': len({row['symbol'] for row in seeds}),
        'support_checks': checks,
        'invariants': invariants,
        'decision': 'V622_SUPPORT_PASS__INDEPENDENT_RAW_ORACLE_REQUIRED' if passed else 'V622_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_ONTOLOGY',
        'artifacts': {'out_dir': str(OUT), 'all_events': str(OUT / 'v622_all_pledge_creation_events.csv'), 'seeds': str(OUT / 'v622_outcome_blind_seeds.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v622_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
