#!/usr/bin/env python3
"""V457 no-outcome weekly SSL rejection-block transfer generator.

Frozen ontology:
- aggregate each stock's local daily bars into completed ISO weeks;
- a visible 2L/2R weekly swing low is raided by a later weekly wick and reclaimed
  by that week's close;
- the raid week's lower rejection wick is the POI;
- only after the completed raid week, require first daily touch -> later reclaim
  above the POI -> later hold above it;
- the following daily session is entry-eligible.

This changes the causal timeframe and POI ontology.  It is not a daily
Turtle-Soup/OB/FVG threshold or exit variant.  No outcomes are read.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
KDIR = ROOT / 'kline_cache'
AUD = ROOT / 'smc_audit'
OUT = AUD / f"v457_weekly_ssl_rejection_block_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST = AUD / 'v457_weekly_ssl_rejection_block_latest.json'
YEARS = ('2023', '2024', '2025', '2026')
MAX_SSL_AGE_WEEKS = 26
MAX_RETEST_DAYS = 20


def f(value: object) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else 0.0
    except (TypeError, ValueError):
        return 0.0


def ds(value: object) -> str:
    return ''.join(char for char in str(value or '') if char.isdigit())[:8]


def load_daily(path: Path) -> list[dict]:
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    rows = []
    for bar in raw:
        row = {key: f(bar.get(key)) for key in ('o', 'h', 'l', 'c')}
        date = ds(bar.get('t') or bar.get('date'))
        if date and all(row.values()):
            row['t'] = date
            rows.append(row)
    return sorted(rows, key=lambda row: row['t'])


def symbol(path: Path) -> str:
    code, exchange = path.name.removesuffix('_daily_750.json').split('_')
    return f'{code}.{exchange}'


def completed_weeks(daily: list[dict]) -> list[dict]:
    buckets: list[list[dict]] = []
    current_key = None
    for bar in daily:
        date = datetime.strptime(bar['t'], '%Y%m%d').date()
        key = date.isocalendar()[:2]
        if key != current_key:
            buckets.append([])
            current_key = key
        buckets[-1].append(bar)
    # The rightmost ISO week may be incomplete at scanner time and is never used.
    buckets = buckets[:-1]
    return [
        {
            'start_date': group[0]['t'],
            'end_date': group[-1]['t'],
            'o': group[0]['o'],
            'h': max(bar['h'] for bar in group),
            'l': min(bar['l'] for bar in group),
            'c': group[-1]['c'],
        }
        for group in buckets if group
    ]


def confirmed_weekly_lows(weeks: list[dict]) -> list[dict]:
    return [
        {'idx': idx, 'confirm_idx': idx + 2, 'price': weeks[idx]['l']}
        for idx in range(2, len(weeks) - 2)
        if all(weeks[j]['l'] > weeks[idx]['l'] for j in range(idx - 2, idx + 3) if j != idx)
    ]


def lifecycle(daily: list[dict], raid_end_date: str, zone_low: float, zone_high: float) -> tuple[str, int | None, int | None, int | None, int | None]:
    start = next((idx for idx, bar in enumerate(daily) if bar['t'] > raid_end_date), None)
    if start is None:
        return 'RIGHT_EDGE_AFTER_RAID', None, None, None, None
    touch = reclaim = hold = None
    for idx in range(start, min(len(daily), start + MAX_RETEST_DAYS)):
        bar = daily[idx]
        if bar['c'] < zone_low:
            return 'CANCEL_POI_INVALIDATED', touch, reclaim, hold, None
        if touch is None:
            if bar['l'] <= zone_high:
                touch = idx
            continue
        if reclaim is None:
            if idx > touch and bar['c'] > zone_high:
                reclaim = idx
            continue
        if idx > reclaim and bar['c'] > zone_high and bar['l'] > zone_low:
            hold = idx
            eligible = idx + 1
            if eligible >= len(daily):
                return 'RIGHT_EDGE_ENTRY', touch, reclaim, hold, None
            return 'TAKEOVER_CONFIRMED', touch, reclaim, hold, eligible
    return ('EXPIRE_NO_TOUCH' if touch is None else 'EXPIRE_NO_RECLAIM' if reclaim is None else 'EXPIRE_NO_HOLD'), touch, reclaim, hold, None


def generate(sym: str, daily: list[dict]) -> tuple[list[dict], Counter]:
    weeks = completed_weeks(daily)
    lows = confirmed_weekly_lows(weeks)
    rows: list[dict] = []
    counts: Counter = Counter()
    for raid_idx in range(5, len(weeks)):
        raid = weeks[raid_idx]
        refs = [
            item for item in lows
            if item['confirm_idx'] < raid_idx
            and raid_idx - item['idx'] <= MAX_SSL_AGE_WEEKS
            and raid['l'] < item['price']
            and raid['c'] > item['price']
        ]
        if not refs:
            continue
        ref = max(refs, key=lambda item: item['idx'])
        zone_low = raid['l']
        zone_high = min(raid['o'], raid['c'])
        if not (zone_low < zone_high):
            counts['INVALID_REJECTION_WICK'] += 1
            continue
        status, touch, reclaim, hold, eligible = lifecycle(daily, raid['end_date'], zone_low, zone_high)
        counts[status] += 1
        if status != 'TAKEOVER_CONFIRMED':
            continue
        rows.append({
            'symbol': sym,
            'ontology': 'WEEKLY_SSL_REJECTION_BLOCK_TRANSFER',
            'weekly_ssl_idx': ref['idx'],
            'weekly_ssl_confirm_idx': ref['confirm_idx'],
            'weekly_ssl_price': round(ref['price'], 6),
            'weekly_raid_idx': raid_idx,
            'weekly_raid_start_date': raid['start_date'],
            'weekly_raid_end_date': raid['end_date'],
            'weekly_raid_low': round(raid['l'], 6),
            'weekly_raid_close': round(raid['c'], 6),
            'zone_low': round(zone_low, 6),
            'zone_high': round(zone_high, 6),
            'touch_idx': touch,
            'touch_date': daily[touch]['t'],
            'reclaim_idx': reclaim,
            'reclaim_date': daily[reclaim]['t'],
            'hold_idx': hold,
            'hold_date': daily[hold]['t'],
            'eligible_entry_idx': eligible,
            'eligible_entry_date': daily[eligible]['t'],
            'semantic_order_valid': raid['end_date'] < daily[touch]['t'] < daily[reclaim]['t'] < daily[hold]['t'] < daily[eligible]['t'],
            'tradable': False,
            'buy_enabled': False,
            'no_outcome_fields': True,
        })
    return rows, counts


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw: list[dict] = []
    counts: Counter = Counter()
    scanned = 0
    for number, path in enumerate(sorted(KDIR.glob('*_daily_750.json')), 1):
        daily = load_daily(path)
        if len(daily) < 150:
            continue
        scanned += 1
        rows, local = generate(symbol(path), daily)
        raw.extend(rows)
        counts.update(local)
        if number % 500 == 0:
            print(json.dumps({'progress': number, 'raw_seeds': len(raw)}), flush=True)
    dedup = {}
    for row in raw:
        key = (row['symbol'], row['eligible_entry_date'])
        old = dedup.get(key)
        if old is None or row['weekly_raid_idx'] < old['weekly_raid_idx']:
            dedup[key] = row
    rows = list(dedup.values())
    yearly = Counter(row['eligible_entry_date'][:4] for row in rows)
    support = len(rows) >= 300 and all(yearly.get(year, 0) >= 40 for year in YEARS)
    fields = list(rows[0]) if rows else ['symbol', 'ontology']
    seed_file = OUT / 'v457_semantic_seeds.csv'
    with seed_file.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    result = {
        'version': 'V457_WEEKLY_SSL_REJECTION_BLOCK_TRANSFER_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'frozen_contract': 'completed weekly 2L/2R SSL -> later weekly wick raid and close-back -> raid-week lower rejection-wick POI -> first post-week daily touch -> later reclaim -> later hold -> next-open eligibility',
        'distinct_information': 'Higher-timeframe liquidity rejection transferred into a lower-timeframe POI lifecycle; no daily OB/FVG/BPR/IFVG/breaker/Turtle-Soup immediate entry.',
        'frozen_support_gate': {'aggregate_n': 300, 'each_2023_2026_year_n': 40},
        'symbols_scanned': scanned,
        'raw_seed_count': len(raw),
        'seed_count': len(rows),
        'yearly_seed_count': dict(sorted(yearly.items())),
        'lifecycle_counts': dict(counts),
        'semantic_order_failures': sum(not row['semantic_order_valid'] for row in rows),
        'duplicate_symbol_entry': len(rows) - len(set((row['symbol'], row['eligible_entry_date']) for row in rows)),
        'support_gate_pass': support,
        'invariants': {
            'daily_and_weekly_same_raw_source': True,
            'rightmost_partial_week_excluded': True,
            'no_entries_created': True,
            'no_outcome_fields': all(row['no_outcome_fields'] for row in rows),
            'all_nontradable': all(not row['tradable'] and not row['buy_enabled'] for row in rows),
        },
        'decision': 'WEEKLY_REJECTION_BLOCK_SEEDS_READY__INDEPENDENT_ORACLE_NEXT' if support else 'WEEKLY_REJECTION_BLOCK_SUPPORT_FAIL__NO_REPLAY',
        'artifacts': {'out_dir': str(OUT), 'seeds': str(seed_file), 'latest': str(LATEST)},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v457_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
