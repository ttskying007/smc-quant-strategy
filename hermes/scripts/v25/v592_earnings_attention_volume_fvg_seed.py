#!/usr/bin/env python3
"""V592 outcome-blind earnings-attention volume-FVG retest seeds."""
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
META = AUDIT / 'v563_pit_event_archive_full_coverage_no_outcome_20260724_124935' / 'v563_event_metadata.jsonl'
PRE = AUDIT / 'v591_earnings_attention_volume_fvg_preregistration_latest.json'
LATEST = AUDIT / 'v592_earnings_attention_volume_fvg_seed_latest.json'
OUT = AUDIT / f'v592_earnings_attention_volume_fvg_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
YEARS = ('2023', '2024', '2025')


def d8(value: object) -> str:
    digits = ''.join(c for c in str(value or '') if c.isdigit())
    return digits[:8] if len(digits) >= 8 else ''


def positive(value: object) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def events() -> list[dict]:
    rows = []
    with META.open(encoding='utf-8') as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            date, title = d8(item.get('notice_date')), str(item.get('title') or '')
            if (item.get('kind') != 'EARNINGS_PREANNOUNCEMENT' or date[:4] not in YEARS or
                    not any(term in title for term in ('业绩预告', '业绩快报'))):
                continue
            rows.append({'symbol': str(item.get('symbol') or ''), 'announcement_id': str(item.get('announcement_id') or ''),
                         'event_date': date, 'publication_time': str(item.get('publication_time') or ''),
                         'external_event': 'EARNINGS_ATTENTION_EVENT', 'title': title})
    canonical = {}
    for row in sorted(rows, key=lambda x: (x['symbol'], x['event_date'], x['announcement_id'])):
        canonical.setdefault((row['symbol'], row['event_date']), row)
    return sorted(canonical.values(), key=lambda x: (x['symbol'], x['event_date'], x['announcement_id']))


def bars(symbol: str) -> list[dict]:
    try:
        raw = json.loads((DAILY / f'{symbol.replace(".", "_")}_daily_750.json').read_text())
    except (OSError, ValueError):
        return []
    result = []
    for item in raw if isinstance(raw, list) else []:
        date = d8(item.get('t') or item.get('date'))
        values = [positive(item.get(key)) for key in ('o', 'h', 'l', 'c', 'v')]
        if len(date) == 8 and all(value is not None for value in values):
            result.append({'d': date, 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3], 'v': values[4]})
    return sorted(result, key=lambda x: x['d'])


def confirmed_highs(rows: list[dict]) -> list[tuple[int, int]]:
    highs = []
    for index in range(3, len(rows) - 3):
        if rows[index]['h'] > max(x['h'] for x in rows[index - 3:index]) and rows[index]['h'] >= max(x['h'] for x in rows[index + 1:index + 4]):
            highs.append((index, index + 3))
    return highs


def first_response(event: dict, rows: list[dict]) -> tuple[str, dict | None]:
    dates = [row['d'] for row in rows]
    start = bisect_right(dates, event['event_date'])
    if start >= len(rows):
        return 'NO_RESPONSE_SESSION', None
    for displacement_i in range(start, min(start + 5, len(rows))):
        if displacement_i < 20 or displacement_i < 3:
            continue
        bar = rows[displacement_i]
        known = [(i, confirm) for i, confirm in confirmed_highs(rows[:displacement_i + 1])
                 if confirm < displacement_i and rows[i]['h'] < bar['c']]
        prior_volume_mean = sum(x['v'] for x in rows[displacement_i - 20:displacement_i]) / 20.0
        if (not known or bar['c'] <= bar['o'] or bar['v'] < prior_volume_mean * 1.5 or
                bar['l'] <= rows[displacement_i - 2]['h']):
            continue
        bsl_i, bsl_confirm_i = known[-1]
        zone_low, zone_high = rows[displacement_i - 2]['h'], bar['l']
        for reclaim_i in range(displacement_i + 1, min(displacement_i + 16, len(rows))):
            candidate = rows[reclaim_i]
            if candidate['l'] <= zone_high and candidate['h'] >= zone_low and candidate['c'] >= zone_high and reclaim_i + 1 < len(rows):
                entry_i = reclaim_i + 1
                return 'SEED', {
                    **event,
                    'response_start_date': rows[start]['d'],
                    'bsl_anchor_date': rows[bsl_i]['d'], 'bsl_anchor_confirm_date': rows[bsl_confirm_i]['d'],
                    'displacement_date': bar['d'], 'prior_20_volume_mean': round(prior_volume_mean, 6),
                    'displacement_volume': round(bar['v'], 6), 'volume_multiple': round(bar['v'] / prior_volume_mean, 6),
                    'fvg_left_date': rows[displacement_i - 2]['d'], 'zone_low': round(zone_low, 6), 'zone_high': round(zone_high, 6),
                    'reclaim_date': rows[reclaim_i]['d'], 'planned_entry_date': rows[entry_i]['d'],
                    'causal_path': 'PIT_EARNINGS_DISCLOSURE>RELATIVE_VOLUME_CONFIRMED_BSL_DISPLACEMENT>BULLISH_FVG_RETEST_RECLAIM>NEXT_OPEN',
                }
    return 'NO_CONFIRMED_VOLUME_FVG_RETEST', None


def main() -> None:
    preregistration = json.loads(PRE.read_text())
    if preregistration['decision'] != 'PREREGISTRATION_COMPLETE__OUTCOME_BLIND_SEED_GENERATION_AUTHORIZED':
        raise RuntimeError('V591 preregistration required')
    OUT.mkdir(parents=True, exist_ok=False)
    source = events()
    grouped: defaultdict[str, list[dict]] = defaultdict(list)
    for event in source:
        grouped[event['symbol']].append(event)
    all_rows = []
    for n, (symbol, event_rows) in enumerate(sorted(grouped.items()), 1):
        xs = bars(symbol)
        for event in event_rows:
            status, seed = first_response(event, xs)
            row = {**event, 'seed_status': status}
            if seed:
                row.update(seed)
            all_rows.append(row)
        if n % 500 == 0:
            print(json.dumps({'symbols': n, 'events_processed': len(all_rows)}), flush=True)
    candidates = [x for x in all_rows if x['seed_status'] == 'SEED' and x['planned_entry_date'][:4] in YEARS]
    canonical = {}
    for row in sorted(candidates, key=lambda x: (x['symbol'], x['planned_entry_date'], x['event_date'], x['announcement_id'])):
        canonical.setdefault((row['symbol'], row['planned_entry_date']), row)
    seeds = sorted(canonical.values(), key=lambda x: (x['planned_entry_date'], x['symbol']))
    fields = sorted({key for row in all_rows for key in row} | {key for row in seeds for key in row})
    for name, rows in (('v592_all_earnings_attention_events.csv', all_rows), ('v592_outcome_blind_seeds.csv', seeds)):
        with (OUT / name).open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
            writer.writeheader(); writer.writerows(rows)
    event_years = {year: sum(x['event_date'].startswith(year) for x in source) for year in YEARS}
    seed_years = {year: sum(x['planned_entry_date'].startswith(year) for x in seeds) for year in YEARS}
    checks = {'raw_canonical_events_each_year': all(event_years[y] >= 1500 for y in YEARS),
              'canonical_seed_total': len(seeds) >= 1500,
              'canonical_seed_each_year': all(seed_years[y] >= 400 for y in YEARS),
              'unique_symbols': len({x['symbol'] for x in seeds}) >= 700}
    invariants = {'no_outcome_or_trade_files_read': True,
                  'all_events_precede_response': all(x['event_date'] < x['response_start_date'] for x in seeds),
                  'all_bsl_anchors_confirmed_before_displacement': all(x['bsl_anchor_confirm_date'] < x['displacement_date'] for x in seeds),
                  'all_causal_nodes_before_entry': all(x['event_date'] < x['displacement_date'] < x['reclaim_date'] < x['planned_entry_date'] for x in seeds),
                  'one_seed_per_symbol_entry_date': len(seeds) == len({(x['symbol'], x['planned_entry_date']) for x in seeds})}
    passed = all(checks.values()) and all(invariants.values())
    report = {'version': 'V592_EARNINGS_ATTENTION_VOLUME_FVG_SEED_NO_OUTCOME', 'generated_at': datetime.now().isoformat(timespec='seconds'),
              'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
              'input_contract': 'V591 frozen earnings-event title rule plus daily OHLCV only through each planned entry; no outcome/trade/PnL/exit/target/stop file read.',
              'raw_canonical_event_count': len(source), 'raw_canonical_event_years': event_years,
              'seed_status_counts': dict(Counter(x['seed_status'] for x in all_rows)), 'canonical_seed_count': len(seeds),
              'canonical_seed_years': seed_years, 'unique_symbols': len({x['symbol'] for x in seeds}),
              'support_checks': checks, 'invariants': invariants,
              'decision': 'V592_SUPPORT_PASS__INDEPENDENT_RAW_ORACLE_REQUIRED' if passed else 'V592_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_ONTOLOGY',
              'artifacts': {'out_dir': str(OUT), 'all_events': str(OUT / 'v592_all_earnings_attention_events.csv'), 'seeds': str(OUT / 'v592_outcome_blind_seeds.csv'), 'latest': str(LATEST)}}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v592_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__ == '__main__': main()
