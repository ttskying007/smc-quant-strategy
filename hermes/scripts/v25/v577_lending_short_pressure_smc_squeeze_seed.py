#!/usr/bin/env python3
"""V577 outcome-blind official lending-pressure -> BSL acceptance/reclaim seeds.

The event is an official prior-session short-sale-pressure transition. This
program reads only that source and daily OHLCV through each planned entry.
It never opens outcome, trade, PnL, MFE, MAE, or exit data.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import quantiles
from typing import Any

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
MARGIN = ROOT / 'pit_cache' / 'v562_exchange_margin_raw'
DAILY = ROOT / 'kline_cache'
PRE = AUDIT / 'v576_lending_short_pressure_smc_squeeze_preregistration_latest.json'
LATEST = AUDIT / 'v577_lending_short_pressure_smc_squeeze_seed_latest.json'
OUT = AUDIT / f'v577_lending_short_pressure_smc_squeeze_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
YEARS = ('2023', '2024', '2025')
SUPPORT = {'raw_external_events_min': 30000, 'canonical_seed_total_min': 3000,
           'canonical_seed_each_year_min': 800, 'unique_symbols_min': 500}


def positive(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


def load_margin(exchange: str, date: str) -> list[dict[str, Any]]:
    path = MARGIN / exchange / f'{date}.json.gz'
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            document = json.load(handle)
    except (OSError, ValueError):
        return []
    if document.get('date') != date or document.get('exchange') != exchange:
        return []
    rows = document.get('rows')
    return rows if isinstance(rows, list) else []


def lending_pressure_events() -> tuple[list[dict[str, Any]], int, dict[str, int]]:
    """Build cross-sectional source-only transitions into high short pressure."""
    events: list[dict[str, Any]] = []
    source_days = 0
    years: Counter[str] = Counter()
    for exchange in ('SH', 'SZ'):
        prior_balance: dict[str, float] = {}
        prior_high: set[str] = set()
        for path in sorted((MARGIN / exchange).glob('20*.json.gz')):
            date = path.stem.split('.')[0]
            if date[:4] not in YEARS:
                continue
            rows = load_margin(exchange, date)
            if not rows:
                continue
            source_days += 1
            values: list[float] = []
            parsed: list[tuple[str, float, float]] = []
            for row in rows:
                code = str(row.get('code') or '').zfill(6)
                sold = positive(row.get('lending_sell'))
                balance = positive(row.get('lending_balance'))
                prior = prior_balance.get(code)
                if not code.isdigit() or sold is None or balance is None or prior is None or prior <= 0:
                    continue
                intensity = sold / prior
                if math.isfinite(intensity):
                    values.append(intensity)
                    parsed.append((code, intensity, balance))
            threshold = quantiles(values, n=4, method='inclusive')[2] if len(values) >= 4 else math.inf
            current_high: set[str] = set()
            for code, intensity, balance in parsed:
                if intensity >= threshold and balance >= prior_balance[code]:
                    current_high.add(code)
                    if code not in prior_high:
                        events.append({
                            'symbol': f'{code}.{"SH" if exchange == "SH" else "SZ"}', 'lending_date': date, 'lending_exchange': exchange,
                            'lending_sell_intensity': round(intensity, 10),
                            'lending_intensity_q75': round(threshold, 10),
                            'lending_balance': round(balance, 2),
                            'external_event': 'LENDING_SELL_PRESSURE_TRANSITION',
                        })
                        years[date[:4]] += 1
            prior_high = current_high
            for row in rows:
                code = str(row.get('code') or '').zfill(6)
                balance = positive(row.get('lending_balance'))
                if code.isdigit() and balance is not None:
                    prior_balance[code] = balance
    events.sort(key=lambda row: (row['symbol'], row['lending_date']))
    return events, source_days, dict(sorted(years.items()))


def daily_bars(symbol: str) -> list[dict[str, Any]]:
    path = DAILY / f'{symbol.replace(".", "_")}_daily_750.json'
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    rows = []
    for item in raw if isinstance(raw, list) else []:
        date = str(item.get('t') or item.get('date') or '')[:8]
        values = [positive(item.get(key)) for key in ('o', 'h', 'l', 'c')]
        if len(date) == 8 and date.isdigit() and all(value is not None for value in values):
            rows.append(dict(d=date, o=values[0], h=values[1], l=values[2], c=values[3]))
    return sorted(rows, key=lambda row: row['d'])


def confirmed_highs(rows: list[dict[str, Any]]) -> list[tuple[int, int]]:
    highs = []
    for index in range(3, len(rows) - 3):
        if rows[index]['h'] > max(row['h'] for row in rows[index - 3:index]) and rows[index]['h'] >= max(row['h'] for row in rows[index + 1:index + 4]):
            highs.append((index, index + 3))
    return highs


def first_response(event: dict[str, Any], rows: list[dict[str, Any]], highs: list[tuple[int, int]]) -> tuple[str, dict[str, Any] | None]:
    dates = [row['d'] for row in rows]
    start = bisect_right(dates, event['lending_date'])
    if start >= len(rows):
        return 'NO_NEXT_RESPONSE_SESSION', None
    if start + 29 >= len(rows):
        return 'RIGHT_EDGE_UNOBSERVED', None
    for break_index in range(start, min(start + 15, len(rows))):
        known = [item for item in highs if item[1] < break_index and rows[item[0]]['h'] < rows[break_index]['c']]
        if not known:
            continue
        high_index, high_confirm = known[-1]
        bearish = [index for index in range(start, break_index + 1) if rows[index]['c'] < rows[index]['o']]
        if not bearish:
            continue
        poi_index = bearish[-1]
        zone_low, zone_high = rows[poi_index]['l'], rows[poi_index]['o']
        reclaim_index = next((
            index for index in range(break_index + 1, min(break_index + 11, len(rows)))
            if rows[index]['l'] <= zone_high and rows[index]['h'] >= zone_low and rows[index]['c'] >= zone_high
        ), None)
        if reclaim_index is None:
            continue
        entry_index = reclaim_index + 1
        if entry_index >= len(rows):
            return 'ENTRY_UNOBSERVED', None
        return 'SEED', {
            **event,
            'response_start_date': rows[start]['d'],
            'bsl_anchor_date': rows[high_index]['d'],
            'bsl_anchor_confirm_date': rows[high_confirm]['d'],
            'bsl_break_date': rows[break_index]['d'],
            'poi_date': rows[poi_index]['d'],
            'zone_low': round(zone_low, 6),
            'zone_high': round(zone_high, 6),
            'reclaim_date': rows[reclaim_index]['d'],
            'planned_entry_date': rows[entry_index]['d'],
            'causal_path': 'PIT_LENDING_SELL_PRESSURE>CONFIRMED_BSL_ACCEPTANCE>DEMAND_POI_RECLAIM>NEXT_OPEN',
        }
    return 'NO_COMPLETED_SQUEEZE_RESPONSE', None


def main() -> None:
    preregistration = json.loads(PRE.read_text())
    assert preregistration['decision'] == 'PREREGISTRATION_COMPLETE__OUTCOME_BLIND_SEED_GENERATION_AUTHORIZED'
    OUT.mkdir(parents=True, exist_ok=False)
    events, source_days, event_years = lending_pressure_events()
    by_symbol: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_symbol[event['symbol']].append(event)
    all_rows = []
    for count, (symbol, symbol_events) in enumerate(sorted(by_symbol.items()), 1):
        bars = daily_bars(symbol)
        highs = confirmed_highs(bars)
        for event in symbol_events:
            status, seed = first_response(event, bars, highs)
            row = {**event, 'seed_status': status}
            if seed:
                row.update(seed)
            all_rows.append(row)
        if count % 500 == 0:
            print(json.dumps({'symbols': count, 'events_processed': len(all_rows)}, ensure_ascii=False), flush=True)
    candidates = [row for row in all_rows if row['seed_status'] == 'SEED' and row['planned_entry_date'][:4] in YEARS]
    canonical: dict[tuple[str, str], dict[str, Any]] = {}
    for row in sorted(candidates, key=lambda item: (item['symbol'], item['planned_entry_date'], item['lending_date'])):
        canonical.setdefault((row['symbol'], row['planned_entry_date']), row)
    seeds = sorted(canonical.values(), key=lambda row: (row['planned_entry_date'], row['symbol']))
    fields = sorted({key for row in all_rows for key in row} | {key for row in seeds for key in row})
    for name, rows in (('v577_all_lending_events.csv', all_rows), ('v577_outcome_blind_seeds.csv', seeds)):
        with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
    seed_years = {year: sum(row['planned_entry_date'].startswith(year) for row in seeds) for year in YEARS}
    invariant = {
        'no_outcome_or_trade_files_read': True,
        'all_external_events_before_response': all(row['lending_date'] < row['response_start_date'] for row in seeds),
        'all_bsl_anchors_confirmed_before_break': all(row['bsl_anchor_confirm_date'] < row['bsl_break_date'] for row in seeds),
        'all_causal_nodes_before_entry': all(row['lending_date'] < row['bsl_break_date'] < row['reclaim_date'] < row['planned_entry_date'] for row in seeds),
        'one_seed_per_symbol_entry_date': len(seeds) == len({(row['symbol'], row['planned_entry_date']) for row in seeds}),
        'raw_external_events_capacity': len(events) >= SUPPORT['raw_external_events_min'],
        'canonical_seed_capacity': len(seeds) >= SUPPORT['canonical_seed_total_min'],
        'each_year_seed_capacity': all(seed_years[year] >= SUPPORT['canonical_seed_each_year_min'] for year in YEARS),
        'unique_symbol_capacity': len({row['symbol'] for row in seeds}) >= SUPPORT['unique_symbols_min'],
    }
    support_pass = all(invariant[key] for key in ('raw_external_events_capacity', 'canonical_seed_capacity', 'each_year_seed_capacity', 'unique_symbol_capacity'))
    report = {
        'version': 'V577_LENDING_SHORT_PRESSURE_SMC_SQUEEZE_SEED_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'input_contract': 'Official SSE/SZSE lending_sell/lending_balance records plus local daily OHLCV only through planned entry; no outcome/trade/PnL/exit file read.',
        'raw_lending_pressure_event_count': len(events), 'event_years': event_years, 'source_days_read': source_days,
        'status_counts': dict(Counter(row['seed_status'] for row in all_rows)), 'canonical_seed_count': len(seeds),
        'canonical_seed_years': seed_years, 'unique_symbols': len({row['symbol'] for row in seeds}),
        'support_gate': SUPPORT, 'invariants': invariant,
        'decision': 'V577_SUPPORT_PASS__INDEPENDENT_RAW_ORACLE_REQUIRED' if support_pass else 'V577_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_OBJECT',
        'artifacts': {'out_dir': str(OUT), 'all_events': str(OUT / 'v577_all_lending_events.csv'), 'seeds': str(OUT / 'v577_outcome_blind_seeds.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v577_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
