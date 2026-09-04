#!/usr/bin/env python3
"""V623 independent no-outcome identity oracle for frozen V621/V622 seeds."""
from __future__ import annotations

import csv
import json
import math
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT, DAILY = ROOT / 'smc_audit', ROOT / 'kline_cache'
CATALOG = AUDIT / 'v615_controlling_pledge_pit_event_catalog_latest.json'
SEED_REPORT = AUDIT / 'v622_controlling_pledge_creation_ssl_exhaustion_seed_latest.json'
LATEST = AUDIT / 'v623_v622_independent_raw_oracle_latest.json'
OUT = AUDIT / f'v623_v622_independent_raw_oracle_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
YEARS = ('2023', '2024', '2025')


def clean_date(value: object) -> str:
    text = ''.join(ch for ch in str(value or '') if ch.isdigit())
    return text[:8] if len(text) >= 8 else ''


def number(value: object) -> float | None:
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except (TypeError, ValueError):
        return None


def equity(symbol: str) -> bool:
    return len(symbol) == 9 and symbol[6:] in {'.SH', '.SZ'} and symbol[:6].startswith(('00', '30', '60', '68'))


def load_events(catalog: dict) -> list[dict]:
    chosen: dict[tuple[str, str], dict] = {}
    with Path(catalog['artifacts']['events']).open(encoding='utf-8') as handle:
        for text in handle:
            try:
                event = json.loads(text)
            except ValueError:
                continue
            symbol, date = str(event.get('symbol') or ''), clean_date(event.get('notice_date'))
            if not (equity(symbol) and date[:4] in YEARS and event.get('event_kind') == 'CONTROLLING_HOLDER_PLEDGE_CREATE'):
                continue
            chosen.setdefault((symbol, date), {
                'symbol': symbol,
                'event_date': date,
                'announcement_id': str(event.get('announcement_id') or ''),
            })
    return sorted(chosen.values(), key=lambda row: (row['symbol'], row['event_date'], row['announcement_id']))


def load_bars(symbol: str) -> list[dict]:
    try:
        raw = json.loads((DAILY / f'{symbol.replace(".", "_")}_daily_750.json').read_text())
    except (OSError, ValueError):
        return []
    result = []
    for item in raw if isinstance(raw, list) else []:
        date = clean_date(item.get('t') or item.get('date'))
        o, h, l, c = (number(item.get(key)) for key in ('o', 'h', 'l', 'c'))
        if len(date) == 8 and None not in (o, h, l, c):
            result.append({'d': date, 'o': o, 'h': h, 'l': l, 'c': c})
    return sorted(result, key=lambda row: row['d'])


def pivots(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    lows, highs = [], []
    for index in range(3, len(rows) - 3):
        left, right = rows[index - 3:index], rows[index + 1:index + 4]
        if rows[index]['l'] < min(bar['l'] for bar in left) and rows[index]['l'] <= min(bar['l'] for bar in right):
            lows.append({'i': index, 'known': index + 3})
        if rows[index]['h'] > max(bar['h'] for bar in left) and rows[index]['h'] >= max(bar['h'] for bar in right):
            highs.append({'i': index, 'known': index + 3})
    lower_highs = []
    for position, pivot in enumerate(highs):
        if position and rows[pivot['i']]['h'] < rows[highs[position - 1]['i']]['h']:
            lower_highs.append(pivot)
    return lows, lower_highs


def reconstruct(event: dict, rows: list[dict]) -> dict | None:
    dates = [bar['d'] for bar in rows]
    response_start = bisect_right(dates, event['event_date'])
    if response_start >= len(rows):
        return None
    lows, lower_highs = pivots(rows)
    for sweep in range(response_start, min(response_start + 30, len(rows))):
        eligible_ssl = [pivot for pivot in lows if pivot['known'] < sweep and rows[sweep]['l'] < rows[pivot['i']]['l'] and rows[sweep]['c'] > rows[pivot['i']]['l']]
        if not eligible_ssl:
            continue
        ssl = eligible_ssl[-1]
        for broken in range(sweep + 1, min(sweep + 16, len(rows))):
            eligible_lh = [pivot for pivot in lower_highs if pivot['known'] < sweep and rows[broken]['c'] > rows[pivot['i']]['h']]
            if not eligible_lh:
                continue
            lower_high = eligible_lh[-1]
            bearish = [index for index in range(sweep, broken + 1) if rows[index]['c'] < rows[index]['o']]
            if not bearish:
                continue
            poi = bearish[-1]
            zone_low, zone_high = rows[poi]['l'], rows[poi]['o']
            for reclaim in range(broken + 1, min(broken + 16, len(rows))):
                bar = rows[reclaim]
                if bar['l'] <= zone_high and bar['h'] >= zone_low and bar['c'] >= zone_high and reclaim + 1 < len(rows):
                    return {
                        **event,
                        'ssl_anchor_date': rows[ssl['i']]['d'],
                        'ssl_anchor_confirm_date': rows[ssl['known']]['d'],
                        'ssl_sweep_date': rows[sweep]['d'],
                        'lower_high_date': rows[lower_high['i']]['d'],
                        'lower_high_confirm_date': rows[lower_high['known']]['d'],
                        'bullish_break_date': rows[broken]['d'],
                        'poi_date': rows[poi]['d'],
                        'reclaim_date': rows[reclaim]['d'],
                        'planned_entry_date': rows[reclaim + 1]['d'],
                    }
    return None


def identity(row: dict) -> tuple[str, ...]:
    return tuple(str(row.get(key) or '') for key in ('symbol', 'event_date', 'announcement_id', 'ssl_anchor_date', 'ssl_sweep_date', 'lower_high_date', 'bullish_break_date', 'poi_date', 'reclaim_date', 'planned_entry_date'))


def main() -> None:
    catalog, seed_report = json.loads(CATALOG.read_text()), json.loads(SEED_REPORT.read_text())
    if seed_report['decision'] != 'V622_SUPPORT_PASS__INDEPENDENT_RAW_ORACLE_REQUIRED':
        raise RuntimeError('V622 support pass required')
    expected_path = Path(seed_report['artifacts']['seeds'])
    expected = list(csv.DictReader(expected_path.open(encoding='utf-8')))
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for event in load_events(catalog):
        by_symbol[event['symbol']].append(event)
    raw = []
    for count, (symbol, events) in enumerate(sorted(by_symbol.items()), 1):
        rows = load_bars(symbol)
        for event in events:
            rebuilt = reconstruct(event, rows)
            if rebuilt is not None and rebuilt['planned_entry_date'][:4] in YEARS:
                raw.append(rebuilt)
        if count % 500 == 0:
            print(json.dumps({'symbols': count, 'raw_identities': len(raw)}), flush=True)
    canonical: dict[tuple[str, str], dict] = {}
    for row in sorted(raw, key=lambda item: (item['symbol'], item['planned_entry_date'], item['event_date'], item['announcement_id'])):
        canonical.setdefault((row['symbol'], row['planned_entry_date']), row)
    rebuilt = sorted(canonical.values(), key=lambda item: (item['planned_entry_date'], item['symbol']))
    expected_set, rebuilt_set = {identity(row) for row in expected}, {identity(row) for row in rebuilt}
    missing, extra = sorted(expected_set - rebuilt_set), sorted(rebuilt_set - expected_set)
    OUT.mkdir(parents=True, exist_ok=False)
    fields = ['symbol', 'event_date', 'announcement_id', 'ssl_anchor_date', 'ssl_anchor_confirm_date', 'ssl_sweep_date', 'lower_high_date', 'lower_high_confirm_date', 'bullish_break_date', 'poi_date', 'reclaim_date', 'planned_entry_date']
    with (OUT / 'v623_oracle_identities.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rebuilt)
    report = {
        'version': 'V623_V622_INDEPENDENT_RAW_ORACLE_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'input_contract': 'V622 expected identities plus immutable V615 catalog and daily OHLC only; no outcome, trade, PnL, exit, target, stop, or replay file read.',
        'independent_rebuild': 'Separately rebuilds exact controlling-holder pledge-creation -> confirmed SSL sweep -> confirmed lower-high break -> demand-OB retest identities without importing V622 code.',
        'expected_identities': len(expected_set),
        'oracle_identities': len(rebuilt_set),
        'missing': len(missing),
        'extra': len(extra),
        'missing_sample': [list(value) for value in missing[:10]],
        'extra_sample': [list(value) for value in extra[:10]],
        'identity_match': not missing and not extra,
        'invariants': {'no_outcome_files_read': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False},
        'decision': 'V623_ORACLE_PASS__ONE_FROZEN_STRICT_T1_REPLAY_AUTHORIZED' if not missing and not extra else 'V623_ORACLE_MISMATCH__CLOSE_ONTOLOGY_NO_REPLAY',
        'artifacts': {'out_dir': str(OUT), 'oracle_identities': str(OUT / 'v623_oracle_identities.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v623_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
