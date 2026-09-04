#!/usr/bin/env python3
"""V602 outcome-blind canonical bullish continuation seed generator.

Ontology (fixed before any outcome is opened):
1. a completed 3L/3R swing high is known before a bullish close breaks it;
2. the nearest bearish candle in the five bars immediately before that break is
   a demand OB; it is discovered backwards from the structural break;
3. after the break, price returns to the OB without closing below its low,
   closes back above the OB high, then a later bar holds above the OB high;
4. only the following session is entry-eligible.

The generator reads only local daily OHLCV and emits no outcomes, exits,
stops, targets, PnL, historical trades, watchlists, or production state.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
KLINE = ROOT / 'kline_cache'
AUDIT = ROOT / 'smc_audit'
OUT = AUDIT / f'v602_canonical_bos_demand_reclaim_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v602_canonical_bos_demand_reclaim_seed_latest.json'
YEARS = ('2023', '2024', '2025', '2026')
LEFT = RIGHT = 3
OB_LOOKBACK = 5
MAX_RETEST_BARS = 20
SUPPORT = {'total_min': 1000, 'each_year_min': 300, 'unique_symbols_min': 1000}


def number(value: Any) -> float | None:
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except (TypeError, ValueError):
        return None


def date8(value: Any) -> str:
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else ''


def symbol(path: Path) -> str:
    code, exchange, _, _ = path.stem.split('_')
    return f'{code}.{exchange}'


def load(path: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    rows = []
    for item in raw if isinstance(raw, list) else []:
        values = [number(item.get(key)) for key in ('o', 'h', 'l', 'c', 'v')]
        date = date8(item.get('t') or item.get('date'))
        if len(date) == 8 and all(value is not None for value in values):
            rows.append({'d': date, 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3], 'v': values[4]})
    return sorted(rows, key=lambda row: row['d'])


def confirmed_highs(rows: list[dict[str, Any]]) -> list[tuple[int, int, float]]:
    output = []
    for index in range(LEFT, len(rows) - RIGHT):
        high = rows[index]['h']
        if (high > max(row['h'] for row in rows[index - LEFT:index]) and
                high >= max(row['h'] for row in rows[index + 1:index + RIGHT + 1])):
            output.append((index, index + RIGHT, high))
    return output


def nearest_bearish_ob(rows: list[dict[str, Any]], break_i: int) -> int | None:
    for index in range(break_i - 1, max(-1, break_i - OB_LOOKBACK - 1), -1):
        if rows[index]['c'] < rows[index]['o']:
            return index
    return None


def lifecycle(rows: list[dict[str, Any]], start_i: int, zone_low: float, zone_high: float) -> tuple[str, int | None, int | None, int | None, int | None]:
    touch = reclaim = hold = None
    for index in range(start_i + 1, min(len(rows), start_i + 1 + MAX_RETEST_BARS)):
        bar = rows[index]
        if bar['c'] < zone_low:
            return 'OB_INVALIDATED_CLOSE', touch, reclaim, hold, None
        if touch is None:
            if bar['l'] <= zone_high and bar['h'] >= zone_low:
                touch = index
            continue
        if reclaim is None:
            if index > touch and bar['c'] > zone_high:
                reclaim = index
            continue
        if index > reclaim and bar['c'] > zone_high and bar['l'] > zone_low:
            hold = index
            eligible = index + 1
            if eligible >= len(rows):
                return 'RIGHT_EDGE_ENTRY', touch, reclaim, hold, None
            return 'DEMAND_RECLAIM_CONFIRMED', touch, reclaim, hold, eligible
    if touch is None:
        return 'EXPIRE_NO_TOUCH', None, None, None, None
    if reclaim is None:
        return 'EXPIRE_NO_RECLAIM', touch, None, None, None
    return 'EXPIRE_NO_HOLD', touch, reclaim, None, None


def generate(sym: str, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
    output: list[dict[str, Any]] = []
    states: Counter[str] = Counter()
    pivots = confirmed_highs(rows)
    consumed_pivots: set[int] = set()
    for break_i in range(RIGHT + 1, len(rows) - 1):
        # BOS is a crossing event, not every later close that remains above an old high.
        # The pivot must have been right-confirmed before this bar; yesterday had not
        # accepted above it, and today's bullish close crosses it for the first time.
        crossed = [
            item for item in pivots
            if item[0] not in consumed_pivots and item[1] < break_i
            and rows[break_i - 1]['c'] <= item[2] < rows[break_i]['c']
        ]
        if not crossed or rows[break_i]['c'] <= rows[break_i]['o']:
            continue
        # A structural high can be broken only once.  Subsequent trips through the
        # same price are not new BOS events and cannot mint another lifecycle.
        pivot_i, pivot_confirm_i, pivot_high = max(crossed, key=lambda item: item[0])
        # When one displacement closes through several known highs, record the
        # latest one as the BOS anchor but consume every crossed level.  A later
        # dip-and-recross of an already broken high is not a fresh BOS.
        consumed_pivots.update(item[0] for item in crossed)
        ob_i = nearest_bearish_ob(rows, break_i)
        if ob_i is None:
            states['NO_BACKWARD_BEARISH_OB'] += 1
            continue
        zone_low, zone_high = rows[ob_i]['l'], rows[ob_i]['o']
        if not (zone_low < zone_high):
            states['INVALID_OB_RANGE'] += 1
            continue
        status, touch_i, reclaim_i, hold_i, entry_i = lifecycle(rows, break_i, zone_low, zone_high)
        states[status] += 1
        if status != 'DEMAND_RECLAIM_CONFIRMED' or entry_i is None:
            continue
        output.append({
            'symbol': sym,
            'ontology': 'CANONICAL_CONFIRMED_BOS_BACKWARD_DEMAND_OB_RECLAIM',
            'signal_date': rows[break_i]['d'],
            'eligible_entry_date': rows[entry_i]['d'],
            'pivot_high_date': rows[pivot_i]['d'],
            'pivot_high_confirm_date': rows[pivot_confirm_i]['d'],
            'pivot_high': round(pivot_high, 6),
            'bos_close': round(rows[break_i]['c'], 6),
            'backward_ob_date': rows[ob_i]['d'],
            'zone_low': round(zone_low, 6),
            'zone_high': round(zone_high, 6),
            'touch_date': rows[touch_i]['d'],
            'reclaim_date': rows[reclaim_i]['d'],
            'hold_date': rows[hold_i]['d'],
            'semantic_order_valid': rows[pivot_confirm_i]['d'] < rows[break_i]['d'] < rows[touch_i]['d'] < rows[reclaim_i]['d'] < rows[hold_i]['d'] < rows[entry_i]['d'],
            'tradable': 'false',
            'buy_enabled': 'false',
            'no_outcome_fields': 'true',
        })
    return output, states


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    raw: list[dict[str, Any]] = []
    states: Counter[str] = Counter()
    scanned = valid = 0
    for path in sorted(KLINE.glob('*_daily_750.json')):
        scanned += 1
        rows = load(path)
        if len(rows) < 80:
            continue
        valid += 1
        seeds, local_states = generate(symbol(path), rows)
        raw.extend(seed for seed in seeds if seed['eligible_entry_date'][:4] in YEARS)
        states.update(local_states)
        if scanned % 500 == 0:
            print(json.dumps({'symbols_scanned': scanned, 'raw_seeds': len(raw)}, ensure_ascii=False), flush=True)
    dedup = {(row['symbol'], row['eligible_entry_date']): row for row in raw}
    seeds = sorted(dedup.values(), key=lambda row: (row['eligible_entry_date'], row['symbol']))
    year_counts = {year: sum(row['eligible_entry_date'].startswith(year) for row in seeds) for year in YEARS}
    unique_symbols = len({row['symbol'] for row in seeds})
    checks = {
        'total_n>=1000': len(seeds) >= SUPPORT['total_min'],
        'each_year_n>=300': all(year_counts[year] >= SUPPORT['each_year_min'] for year in YEARS),
        'unique_symbols>=1000': unique_symbols >= SUPPORT['unique_symbols_min'],
        'strict_causal_order': all(row['semantic_order_valid'] for row in seeds),
        'entry_after_signal': all(row['eligible_entry_date'] > row['signal_date'] for row in seeds),
        'no_outcome_fields': all(row['no_outcome_fields'] == 'true' for row in seeds),
    }
    seed_path = OUT / 'v602_outcome_blind_seeds.csv'
    with seed_path.open('w', encoding='utf-8', newline='') as handle:
        fields = list(seeds[0]) if seeds else ['symbol', 'eligible_entry_date']
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(seeds)
    report = {
        'version': 'V602_CANONICAL_CONFIRMED_BOS_BACKWARD_DEMAND_OB_RECLAIM_SEED_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source_contract': 'Local full-universe daily OHLCV only; no historical outcome/trade/PnL/exit/target/stop artifacts read.',
        'frozen_causal_contract': 'confirmed 3L/3R external swing high -> later bullish close above it -> backward nearest bearish candle among prior five is demand OB -> later OB touch without close invalidation -> later close reclaim -> later hold -> following-session open only.',
        'support_gate': SUPPORT,
        'symbols_scanned': scanned, 'valid_symbol_files': valid, 'raw_seed_count': len(raw),
        'canonical_seed_count': len(seeds), 'canonical_seed_years': year_counts, 'unique_symbols': unique_symbols,
        'lifecycle_counts': dict(states), 'support_checks': checks,
        'decision': 'V602_SUPPORT_PASS__INDEPENDENT_RAW_ORACLE_REQUIRED' if all(checks.values()) else 'V602_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_ONTOLOGY',
        'artifacts': {'out_dir': str(OUT), 'seeds': str(seed_path), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v602_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
