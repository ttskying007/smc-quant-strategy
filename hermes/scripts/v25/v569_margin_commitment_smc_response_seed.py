#!/usr/bin/env python3
"""V569 outcome-blind official-margin commitment -> daily SMC-response seeds.

This program reads only official prior-session financing records and daily bars
through each planned entry. It never opens trades, PnL, MFE, MAE, or exit files.
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
PRE = AUDIT / 'v569_margin_commitment_smc_response_preregistration.json'
LATEST = AUDIT / 'v569_margin_commitment_smc_response_seed_latest.json'
OUT = AUDIT / f'v569_margin_commitment_smc_response_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
YEARS = ('2023', '2024', '2025')
SUPPORT = {'raw_margin_events_min': 30000, 'canonical_smcreponse_seeds_min': 3000,
           'each_complete_year_seeds_min': 800, 'unique_symbols_min': 500}


def number(value: Any) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) and x > 0 else None
    except (TypeError, ValueError):
        return None


def load_margin(exchange: str, date: str) -> list[dict[str, Any]]:
    path = MARGIN / exchange / f'{date}.json.gz'
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            doc = json.load(handle)
    except (OSError, ValueError):
        return []
    if doc.get('date') != date or doc.get('exchange') != exchange:
        return []
    return doc.get('rows') if isinstance(doc.get('rows'), list) else []


def margin_impulses() -> tuple[list[dict[str, Any]], int, dict[str, int]]:
    """Return transition-into-high commitment events; all ranks are source-only."""
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_days = 0
    per_year: Counter[str] = Counter()
    for exchange in ('SH', 'SZ'):
        paths = sorted((MARGIN / exchange).glob('20*.json.gz'))
        previous: dict[str, float] = {}
        was_high: dict[str, bool] = defaultdict(bool)
        for path in paths:
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
                buy, balance = number(row.get('financing_buy')), number(row.get('financing_balance'))
                prior = previous.get(code)
                if not code.isdigit() or buy is None or balance is None or prior is None or prior <= 0:
                    continue
                intensity = buy / prior
                if math.isfinite(intensity):
                    values.append(intensity); parsed.append((code, intensity, balance))
            cutoff = quantiles(values, n=4, method='inclusive')[2] if len(values) >= 4 else math.inf
            current_codes = {str(row.get('code') or '').zfill(6) for row in rows}
            for code, intensity, balance in parsed:
                high = intensity >= cutoff and balance >= previous[code]
                if high and not was_high[code]:
                    suffix = 'SH' if exchange == 'SH' else 'SZ'
                    by_symbol[f'{code}.{suffix}'].append({
                        'symbol': f'{code}.{suffix}', 'margin_date': date, 'margin_exchange': exchange,
                        'margin_buy_intensity': round(intensity, 10), 'margin_intensity_q75': round(cutoff, 10),
                        'financing_balance': round(balance, 2), 'external_commitment': 'MARGIN_HIGH_BUY_AND_RISING_BALANCE',
                    })
                    per_year[date[:4]] += 1
                was_high[code] = high
            for row in rows:
                code = str(row.get('code') or '').zfill(6)
                balance = number(row.get('financing_balance'))
                if code.isdigit() and balance is not None:
                    previous[code] = balance
            for code in list(was_high):
                if code not in current_codes:
                    was_high[code] = False
    events = [event for items in by_symbol.values() for event in items]
    events.sort(key=lambda x: (x['symbol'], x['margin_date']))
    return events, source_days, dict(sorted(per_year.items()))


def daily(symbol: str) -> list[dict[str, Any]]:
    path = DAILY / f'{symbol.replace(".", "_")}_daily_750.json'
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    rows = []
    for item in raw if isinstance(raw, list) else []:
        date = str(item.get('t') or item.get('date') or '')[:8]
        values = [number(item.get(key)) for key in ('o', 'h', 'l', 'c')]
        if len(date) == 8 and date.isdigit() and all(v is not None for v in values):
            rows.append({'d': date, 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3]})
    return sorted(rows, key=lambda x: x['d'])


def pivots(rows: list[dict[str, Any]]) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    lows, highs = [], []
    for i in range(3, len(rows) - 3):
        if rows[i]['l'] < min(x['l'] for x in rows[i - 3:i]) and rows[i]['l'] <= min(x['l'] for x in rows[i + 1:i + 4]):
            lows.append((i, i + 3))
        if rows[i]['h'] > max(x['h'] for x in rows[i - 3:i]) and rows[i]['h'] >= max(x['h'] for x in rows[i + 1:i + 4]):
            highs.append((i, i + 3))
    return lows, highs


def first_chain(event: dict[str, Any], rows: list[dict[str, Any]], lows: list[tuple[int, int]], highs: list[tuple[int, int]]) -> tuple[str, dict[str, Any] | None]:
    dates = [row['d'] for row in rows]
    start = bisect_right(dates, event['margin_date'])
    if start >= len(rows):
        return 'NO_NEXT_RESPONSE_SESSION', None
    if start + 34 >= len(rows):
        return 'RIGHT_EDGE_UNOBSERVED', None
    for sweep_i in range(start, min(start + 15, len(rows) - 1)):
        known_lows = [pivot for pivot in lows if pivot[1] < sweep_i]
        if not known_lows:
            continue
        ssl_i, ssl_confirm = known_lows[-1]
        sweep = rows[sweep_i]
        if not (sweep['l'] < rows[ssl_i]['l'] and sweep['c'] > rows[ssl_i]['l']):
            continue
        known_highs = [pivot for pivot in highs if pivot[1] < sweep_i]
        lh_i = None
        for j in range(len(known_highs) - 1, 0, -1):
            candidate, prior = known_highs[j][0], known_highs[j - 1][0]
            if rows[candidate]['h'] < rows[prior]['h']:
                lh_i = candidate
                break
        if lh_i is None:
            continue
        choch_i = next((i for i in range(sweep_i + 1, min(sweep_i + 9, len(rows))) if rows[i]['c'] > rows[lh_i]['h']), None)
        if choch_i is None:
            continue
        bearish = [i for i in range(sweep_i, choch_i + 1) if rows[i]['c'] < rows[i]['o']]
        if not bearish:
            continue
        poi_i = bearish[-1]
        zone_low, zone_high = rows[poi_i]['l'], rows[poi_i]['o']
        reclaim_i = next((
            i for i in range(choch_i + 1, min(choch_i + 11, len(rows)))
            if rows[i]['l'] <= zone_high and rows[i]['h'] >= zone_low and rows[i]['c'] >= zone_high
        ), None)
        if reclaim_i is None:
            continue
        entry_i = reclaim_i + 1
        if entry_i >= len(rows):
            return 'ENTRY_UNOBSERVED', None
        return 'SEED', {
            **event, 'response_start_date': rows[start]['d'], 'ssl_anchor_date': rows[ssl_i]['d'],
            'ssl_anchor_confirm_date': rows[ssl_confirm]['d'], 'sweep_date': rows[sweep_i]['d'],
            'lh_anchor_date': rows[lh_i]['d'], 'choch_date': rows[choch_i]['d'], 'poi_date': rows[poi_i]['d'],
            'zone_low': round(zone_low, 6), 'zone_high': round(zone_high, 6),
            'reclaim_date': rows[reclaim_i]['d'], 'planned_entry_date': rows[entry_i]['d'],
            'causal_path': 'PIT_MARGIN_COMMITMENT>CONFIRMED_SSL_SWEEP_RECLAIM>CONFIRMED_LH_CHOCH>DEMAND_POI_RECLAIM>NEXT_OPEN',
        }
    return 'NO_COMPLETED_SMC_RESPONSE', None


def main() -> None:
    pre = json.loads(PRE.read_text())
    assert pre['decision'] == 'PREREGISTRATION_COMPLETE__OUTCOME_BLIND_MARGIN_SMC_SEED_GENERATION_AUTHORIZED'
    OUT.mkdir(parents=True, exist_ok=False)
    events, source_days, event_years = margin_impulses()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[event['symbol']].append(event)
    all_rows: list[dict[str, Any]] = []
    for n, (symbol, items) in enumerate(sorted(grouped.items()), 1):
        rows = daily(symbol)
        lows, highs = pivots(rows)
        for event in items:
            status, seed = first_chain(event, rows, lows, highs)
            result = {**event, 'seed_status': status}
            if seed:
                result.update(seed)
            all_rows.append(result)
        if n % 500 == 0:
            print(json.dumps({'symbols': n, 'margin_events': len(all_rows)}, ensure_ascii=False), flush=True)
    candidates = [row for row in all_rows if row['seed_status'] == 'SEED' and row['planned_entry_date'][:4] in YEARS]
    canonical: dict[tuple[str, str], dict[str, Any]] = {}
    for row in sorted(candidates, key=lambda x: (x['symbol'], x['planned_entry_date'], x['margin_date'])):
        canonical.setdefault((row['symbol'], row['planned_entry_date']), row)
    seeds = sorted(canonical.values(), key=lambda x: (x['planned_entry_date'], x['symbol']))
    fields = sorted({key for row in all_rows for key in row} | {key for row in seeds for key in row})
    for name, rows in [('v569_all_margin_events.csv', all_rows), ('v569_outcome_blind_seeds.csv', seeds)]:
        with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
            writer.writeheader(); writer.writerows(rows)
    seed_years = {year: sum(row['planned_entry_date'].startswith(year) for row in seeds) for year in YEARS}
    report = {
        'version': 'V569_MARGIN_COMMITMENT_SMC_RESPONSE_SEED_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'input_contract': 'Official SSE/SZSE raw margin dates plus local daily OHLCV only through planned entry; no outcome/trade/PnL/exit files read.',
        'source_days_read': source_days, 'raw_margin_impulse_count': len(events), 'margin_event_years': event_years,
        'status_counts': dict(Counter(row['seed_status'] for row in all_rows)), 'canonical_seed_count': len(seeds),
        'canonical_seed_years': seed_years, 'unique_symbols': len({row['symbol'] for row in seeds}),
        'invariants': {
            'no_outcome_or_trade_files_read': True,
            'all_margin_features_before_response': all(row['margin_date'] < row['response_start_date'] for row in seeds),
            'all_ssl_anchors_confirmed_before_sweep': all(row['ssl_anchor_confirm_date'] < row['sweep_date'] for row in seeds),
            'all_lh_anchors_confirmed_before_sweep': all(row['lh_anchor_date'] < row['sweep_date'] for row in seeds),
            'all_causal_nodes_before_entry': all(row['margin_date'] < row['sweep_date'] < row['choch_date'] < row['reclaim_date'] < row['planned_entry_date'] for row in seeds),
            'one_seed_per_symbol_entry_date': len(seeds) == len({(row['symbol'], row['planned_entry_date']) for row in seeds}),
            'raw_margin_events_capacity': len(events) >= SUPPORT['raw_margin_events_min'],
            'canonical_seed_capacity': len(seeds) >= SUPPORT['canonical_smcreponse_seeds_min'],
            'each_year_seed_capacity': all(seed_years[year] >= SUPPORT['each_complete_year_seeds_min'] for year in YEARS),
            'unique_symbol_capacity': len({row['symbol'] for row in seeds}) >= SUPPORT['unique_symbols_min'],
        },
        'support_gate': SUPPORT,
        'decision': '',
        'artifacts': {'out_dir': str(OUT), 'all_events': str(OUT / 'v569_all_margin_events.csv'), 'seeds': str(OUT / 'v569_outcome_blind_seeds.csv'), 'latest': str(LATEST)},
    }
    capacity = all(report['invariants'][key] for key in ('raw_margin_events_capacity', 'canonical_seed_capacity', 'each_year_seed_capacity', 'unique_symbol_capacity'))
    report['decision'] = 'V569_SUPPORT_PASS__INDEPENDENT_RAW_ORACLE_REQUIRED' if capacity else 'V569_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_OBJECT'
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v569_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__':
    main()
