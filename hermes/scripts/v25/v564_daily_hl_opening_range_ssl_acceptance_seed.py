#!/usr/bin/env python3
"""V564 outcome-blind seed gate: daily protected HL -> M15 opening-range SSL acceptance.

Frozen ontology, distinct from closed V543/V562 objects:
  1) before D, two completed daily 3L/3R swing lows establish a higher-low parent;
  2) on D, first four M15 bars establish an opening liquidity range;
  3) a later M15 bar raids the opening-range low and closes back above it;
  4) price then closes above the opening-range high and the following M15 bar holds it;
  5) only D+1 daily open is eligible.

The generator reads raw same-source Sina OHLCV only and writes no outcome, replay,
production, frontend, watchlist, or position data.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina'
DAILY = RAW / 'daily'
M15 = RAW / 'm15'
OUT = AUDIT / f'v564_daily_hl_opening_range_ssl_acceptance_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v564_daily_hl_opening_range_ssl_acceptance_seed_latest.json'
YEARS = ('2025', '2026')
LEFT = RIGHT = 3
SUPPORT = {'seed_total_min': 3000, 'seed_each_year_min': 1200, 'unique_symbols_min': 500}


def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


def load(path: Path) -> list[dict[str, Any]]:
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return []
    return raw if isinstance(raw, list) else []


def daily_bars(symbol: str) -> list[dict[str, Any]]:
    output = []
    for raw in load(DAILY / f'{symbol.replace(".", "_")}_daily.json.gz'):
        date = str(raw.get('d') or raw.get('t') or '')[:8]
        values = [number(raw.get(key)) for key in ('o', 'h', 'l', 'c')]
        if len(date) == 8 and all(value is not None for value in values):
            output.append({'d': date, 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3]})
    return sorted(output, key=lambda row: row['d'])


def m15_by_day(symbol: str) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in load(M15 / f'{symbol.replace(".", "_")}_m15.json.gz'):
        stamp = str(raw.get('t') or '')
        values = [number(raw.get(key)) for key in ('o', 'h', 'l', 'c')]
        if len(stamp) == 14 and all(value is not None for value in values):
            output[stamp[:8]].append({'t': stamp, 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3]})
    for bars in output.values():
        bars.sort(key=lambda row: row['t'])
    return output


def confirmed_lows(rows: list[dict[str, Any]]) -> list[tuple[int, int, float]]:
    output = []
    for index in range(LEFT, len(rows) - RIGHT):
        before = rows[index - LEFT:index]
        after = rows[index + 1:index + RIGHT + 1]
        if rows[index]['l'] < min(row['l'] for row in before) and rows[index]['l'] <= min(row['l'] for row in after):
            output.append((index, index + RIGHT, rows[index]['l']))
    return output


def parent_by_date(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lows = confirmed_lows(rows)
    output = {}
    for index, row in enumerate(rows):
        known = [item for item in lows if item[1] < index]
        if len(known) < 2:
            continue
        prior, latest = known[-2:]
        if latest[2] <= prior[2] or rows[index - 1]['c'] <= latest[2]:
            continue
        output[row['d']] = {
            'daily_prior_hl_date': rows[prior[0]]['d'],
            'daily_latest_hl_date': rows[latest[0]]['d'],
            'daily_hl_confirm_date': rows[latest[1]]['d'],
            'daily_prior_hl_low': round(prior[2], 8),
            'daily_latest_hl_low': round(latest[2], 8),
        }
    return output


def opening_range_event(bars: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    if len(bars) != 16:
        return None, 'M15_INCOMPLETE_SESSION'
    opening = bars[:4]
    range_low = min(row['l'] for row in opening)
    range_high = max(row['h'] for row in opening)
    for raid_index in range(4, 12):
        raid = bars[raid_index]
        if raid['l'] >= range_low * 0.997 or raid['c'] <= range_low:
            continue
        for break_index in range(raid_index + 1, 15):
            breakout, hold = bars[break_index], bars[break_index + 1]
            if breakout['c'] > range_high * 1.001 and hold['c'] > range_high:
                return {
                    'opening_range_start_time': opening[0]['t'],
                    'opening_range_end_time': opening[-1]['t'],
                    'opening_range_low': round(range_low, 8),
                    'opening_range_high': round(range_high, 8),
                    'ssl_raid_time': raid['t'],
                    'ssl_raid_low': round(raid['l'], 8),
                    'ssl_reclaim_close': round(raid['c'], 8),
                    'opening_range_break_time': breakout['t'],
                    'opening_range_hold_time': hold['t'],
                }, 'PASS'
    return None, 'NO_OPENING_RANGE_SSL_ACCEPTANCE'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, Any]] = []
    rejects: Counter[str] = Counter()
    scanned = 0
    for path in sorted(DAILY.glob('*_daily.json.gz')):
        stem = path.name.removesuffix('_daily.json.gz').split('_', 1)
        if len(stem) != 2:
            continue
        symbol = f'{stem[0]}.{stem[1]}'
        daily = daily_bars(symbol)
        if len(daily) < 30:
            rejects['DAILY_TOO_SHORT'] += 1
            continue
        parent = parent_by_date(daily)
        sessions = m15_by_day(symbol)
        next_day = {left['d']: right['d'] for left, right in zip(daily, daily[1:])}
        for date, state in parent.items():
            if date[:4] not in YEARS:
                continue
            event, status = opening_range_event(sessions.get(date, []))
            rejects[status] += 1
            entry_date = next_day.get(date)
            if event is None or not entry_date:
                if event is not None:
                    rejects['NO_NEXT_DAILY_SESSION'] += 1
                continue
            assert state['daily_hl_confirm_date'] < date < entry_date
            assert event['ssl_raid_time'] < event['opening_range_break_time'] < event['opening_range_hold_time'] < entry_date + '000000'
            rows.append({
                'symbol': symbol,
                'ontology': 'DAILY_PROTECTED_HL_TO_M15_OPENING_RANGE_SSL_ACCEPTANCE',
                'signal_date': date,
                'eligible_entry_date': entry_date,
                'tradable': 'false',
                'buy_enabled': 'false',
                'no_outcome_fields': 'true',
                **state,
                **event,
            })
        scanned += 1
        if scanned % 1000 == 0:
            print(json.dumps({'symbols_scanned': scanned, 'seeds': len(rows)}, ensure_ascii=False), flush=True)

    rows.sort(key=lambda row: (row['signal_date'], row['symbol'], row['opening_range_hold_time']))
    dedup = {(row['symbol'], row['signal_date']): row for row in rows}
    rows = sorted(dedup.values(), key=lambda row: (row['signal_date'], row['symbol']))
    years = Counter(row['signal_date'][:4] for row in rows)
    invariants = {
        'source_isolated_sina_only': True,
        'no_outcome_fields': all(not any(token in key.lower() for key in row for token in ('pnl', 'return', 'exit', 'mae', 'mfe', 'target', 'stop')) for row in rows),
        'all_parent_confirmed_before_signal': all(row['daily_hl_confirm_date'] < row['signal_date'] for row in rows),
        'all_m15_event_before_entry': all(row['ssl_raid_time'] < row['opening_range_break_time'] < row['opening_range_hold_time'] < row['eligible_entry_date'] + '000000' for row in rows),
        'all_execution_next_trade_day': all(row['eligible_entry_date'] > row['signal_date'] for row in rows),
        'seed_total_capacity': len(rows) >= SUPPORT['seed_total_min'],
        'seed_each_year_capacity': all(years[year] >= SUPPORT['seed_each_year_min'] for year in YEARS),
        'unique_symbols_capacity': len({row['symbol'] for row in rows}) >= SUPPORT['unique_symbols_min'],
    }
    seed_path = OUT / 'v564_outcome_blind_seeds.csv'
    fields = sorted({key for row in rows for key in row}) if rows else ['symbol', 'signal_date']
    with seed_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    report = {
        'version': 'V564_DAILY_HL_OPENING_RANGE_SSL_ACCEPTANCE_SEED_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'scope': 'SINA_SOURCE_ISOLATED_COMPLETE_2025_2026_PARTIAL_HISTORY__RESEARCH_ONLY',
        'hypothesis': 'A completed daily protected higher-low parent state plus a same-day M15 opening-range sell-side liquidity raid, reclaim, range-high acceptance and hold identifies a next-day-executable continuation/reversal transition.',
        'distinctness': 'This does not use V543 SSL-to-volume-displacement-to-FVG-retest identity, V557 daily demand/reclaim, V562 industry BOS, industry rank, or industry participation. Its lower-timeframe POI is the day-specific opening liquidity range.',
        'frozen_pre_outcome_contract': 'daily 3L/3R prior HL then higher HL both confirmed before D; D opening first four M15 bars define liquidity range; later M15 wick raid below range low by >=0.3% and close above it; later close > range high by >=0.1% followed by next M15 close above range high; only D+1 daily open may execute. No outcomes read.',
        'support_gate_before_outcomes': SUPPORT,
        'seed_count': len(rows),
        'year_counts': dict(sorted(years.items())),
        'unique_symbols': len({row['symbol'] for row in rows}),
        'symbols_scanned': scanned,
        'rejection_counts': dict(rejects),
        'invariants': invariants,
        'decision': 'V564_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED_NEXT' if all(invariants.values()) else 'V564_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_OBJECT',
        'artifacts': {'out_dir': str(OUT), 'seeds': str(seed_path), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v564_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
