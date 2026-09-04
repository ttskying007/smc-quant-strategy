#!/usr/bin/env python3
"""V438 no-write independent semantic oracle for V437 Target-First DOL.

Re-derives swings, structure, target selection, demand POI and lifecycle without
importing V27 or V437. It compares complete unique semantic identities and never
creates trades, outcomes, picks, or production writes.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
KDIR, AUD = ROOT / 'kline_cache', ROOT / 'smc_audit'
SOURCE = AUD / 'v437_target_first_dol_latest.json'
OUT = AUD / f'v438_target_first_dol_independent_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v438_target_first_dol_independent_oracle_latest.json'
LEFT = RIGHT = 3
STRUCTURE_START = 30
BREAK_BUFFER = 0.002
OB_BACKSCAN = 10


def f(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else 0.0
    except (TypeError, ValueError):
        return 0.0


def day(bar):
    return ''.join(c for c in str(bar.get('t') or bar.get('date') or '') if c.isdigit())[:8]


def load_bars(path):
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    rows = []
    for bar in raw:
        normalized = {key: f(bar.get(key)) for key in ('o', 'h', 'l', 'c')}
        if day(bar) and all(normalized.values()):
            normalized['t'] = day(bar)
            rows.append(normalized)
    return sorted(rows, key=lambda row: row['t'])


def symbol(path):
    code, exchange = path.name.removesuffix('_daily_750.json').split('_')
    return f'{code}.{exchange}'


def confirmed_swings(bars):
    highs, lows = [], []
    for idx in range(LEFT + RIGHT, len(bars) - RIGHT):
        high, low = bars[idx]['h'], bars[idx]['l']
        if all(bars[j]['h'] < high for j in range(idx - LEFT, idx + RIGHT + 1) if j != idx):
            highs.append({'idx': idx, 'price': high, 'confirm_idx': idx + RIGHT})
        if all(bars[j]['l'] > low for j in range(idx - LEFT, idx + RIGHT + 1) if j != idx):
            lows.append({'idx': idx, 'price': low, 'confirm_idx': idx + RIGHT})
    return highs, lows


def structure_events(bars, highs, lows):
    broken, trend, events = set(), 'unknown', []
    for idx in range(STRUCTURE_START, len(bars)):
        bull_levels = sorted((row for row in highs if row['confirm_idx'] <= idx and ('high', row['idx']) not in broken),
                             key=lambda row: row['confirm_idx'], reverse=True)
        bull_break = next((row for row in bull_levels if bars[idx]['c'] > row['price'] * (1 + BREAK_BUFFER)), None)
        if bull_break:
            events.append({'direction': 'bull', 'type': 'BOS' if trend == 'bullish' else 'CHOCH',
                           'index': idx, 'broken_swing_idx': bull_break['idx']})
            broken.add(('high', bull_break['idx']))
            trend = 'bullish'
            continue
        bear_levels = sorted((row for row in lows if row['confirm_idx'] <= idx and ('low', row['idx']) not in broken),
                             key=lambda row: row['confirm_idx'], reverse=True)
        bear_break = next((row for row in bear_levels if bars[idx]['c'] < row['price'] * (1 - BREAK_BUFFER)), None)
        if bear_break:
            events.append({'direction': 'bear', 'type': 'BOS' if trend == 'bearish' else 'CHOCH',
                           'index': idx, 'broken_swing_idx': bear_break['idx']})
            broken.add(('low', bear_break['idx']))
            trend = 'bearish'
    return events


def choose_dol(bars, highs, event_idx):
    event_close = bars[event_idx]['c']
    candidates = []
    for high in highs:
        confirm_idx, price = high['confirm_idx'], high['price']
        if confirm_idx >= event_idx or price <= event_close:
            continue
        if any(bars[idx]['h'] >= price for idx in range(confirm_idx + 1, event_idx)):
            continue
        candidates.append(high)
    return min(candidates, default=None, key=lambda row: (row['price'], -row['confirm_idx']))


def demand_poi(bars, event_idx):
    for idx in range(event_idx - 1, max(-1, event_idx - OB_BACKSCAN - 1), -1):
        if bars[idx]['c'] < bars[idx]['o']:
            return idx, bars[idx]['l'], bars[idx]['h']
    return None


def lifecycle(bars, event_idx, zone_low, zone_high, dol_price):
    touch = reclaim = None
    for idx in range(event_idx + 1, len(bars)):
        bar = bars[idx]
        if bar['h'] >= dol_price or bar['c'] < zone_low:
            return None
        if touch is None:
            if bar['l'] <= zone_high and bar['h'] >= zone_low:
                touch = idx
            continue
        if reclaim is None:
            if idx > touch and bar['c'] > zone_high:
                reclaim = idx
            continue
        if idx > reclaim and bar['c'] > zone_high and bar['l'] >= zone_low:
            eligible = idx + 1
            if eligible >= len(bars):
                return None
            entry_open = bars[eligible]['o']
            if entry_open >= dol_price or entry_open <= zone_low:
                return None
            return touch, reclaim, idx, eligible
    return None


def identity(row):
    return (
        str(row['symbol']), int(row['dol_idx']), int(row['dol_confirm_idx']), round(f(row['dol_price']), 6),
        int(row['event_idx']), int(row['broken_swing_idx']), int(row['poi_idx']),
        round(f(row['zone_low']), 6), round(f(row['zone_high']), 6), int(row['touch_idx']),
        int(row['reclaim_idx']), int(row['takeover_idx']), int(row['eligible_entry_idx']),
    )


def main():
    source_report = json.loads(SOURCE.read_text())
    if source_report.get('decision') != 'TARGET_FIRST_DOL_SEMANTIC_READY__INDEPENDENT_ORACLE_NEXT':
        raise RuntimeError('V437 pre-outcome semantic gate did not pass')
    with Path(source_report['artifacts']['unique_takeover']).open(newline='') as handle:
        source_rows = list(csv.DictReader(handle))
    source_set = {identity(row) for row in source_rows}

    OUT.mkdir(parents=True, exist_ok=True)
    oracle_rows, counts = [], Counter()
    chronology_failures = 0
    for index, path in enumerate(sorted(KDIR.glob('*_daily_750.json')), 1):
        bars = load_bars(path)
        if len(bars) < 60:
            continue
        sym = symbol(path)
        counts['symbols_scanned'] += 1
        highs, lows = confirmed_swings(bars)
        events = structure_events(bars, highs, lows)
        per_takeover = {}
        for event in events:
            if event['direction'] != 'bull' or event['type'] != 'BOS':
                continue
            event_idx = event['index']
            dol = choose_dol(bars, highs, event_idx)
            poi = demand_poi(bars, event_idx)
            if dol is None or poi is None:
                continue
            poi_idx, zone_low, zone_high = poi
            result = lifecycle(bars, event_idx, zone_low, zone_high, dol['price'])
            if result is None:
                continue
            touch, reclaim, takeover, eligible = result
            order = (event_idx, touch, reclaim, takeover, eligible)
            chronology_failures += int(not (dol['confirm_idx'] < event_idx and poi_idx < event_idx
                                             and all(a < b for a, b in zip(order, order[1:]))))
            row = {
                'symbol': sym, 'ontology': 'TARGET_FIRST_DOL',
                'dol_idx': dol['idx'], 'dol_date': bars[dol['idx']]['t'],
                'dol_confirm_idx': dol['confirm_idx'], 'dol_confirm_date': bars[dol['confirm_idx']]['t'],
                'dol_price': round(dol['price'], 6),
                'event_type': event['type'], 'event_idx': event_idx, 'event_date': bars[event_idx]['t'],
                'broken_swing_idx': event['broken_swing_idx'],
                'poi_idx': poi_idx, 'poi_date': bars[poi_idx]['t'],
                'zone_low': round(zone_low, 6), 'zone_high': round(zone_high, 6),
                'touch_idx': touch, 'touch_date': bars[touch]['t'],
                'reclaim_idx': reclaim, 'reclaim_date': bars[reclaim]['t'],
                'takeover_idx': takeover, 'takeover_date': bars[takeover]['t'],
                'eligible_entry_idx': eligible, 'eligible_entry_date': bars[eligible]['t'],
                'tradable': 'false', 'buy_enabled': 'false', 'outcome_fields_present': 'false',
            }
            key = (sym, row['takeover_date'])
            old = per_takeover.get(key)
            rank = (row['dol_price'], row['event_idx'], row['poi_idx'])
            old_rank = ((old['dol_price'], old['event_idx'], old['poi_idx']) if old else None)
            if old is None or rank < old_rank:
                per_takeover[key] = row
        oracle_rows.extend(per_takeover.values())
        if index % 500 == 0:
            print(json.dumps({'progress': index, 'oracle_unique': len(oracle_rows)}, ensure_ascii=False), flush=True)

    oracle_set = {identity(row) for row in oracle_rows}
    source_extra, oracle_extra = source_set - oracle_set, oracle_set - source_set
    mismatch_rows = ([{'disposition': 'V437_EXTRA', 'identity': repr(key)} for key in sorted(source_extra)] +
                     [{'disposition': 'ORACLE_EXTRA', 'identity': repr(key)} for key in sorted(oracle_extra)])
    fields = list(oracle_rows[0]) if oracle_rows else ['symbol', 'ontology']
    with (OUT / 'v438_oracle_unique_takeover_rows.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(oracle_rows)
    with (OUT / 'v438_differential_mismatches.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['disposition', 'identity']); writer.writeheader(); writer.writerows(mismatch_rows)

    report = {
        'version': 'V438_TARGET_FIRST_DOL_INDEPENDENT_ORACLE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'oracle_contract': 'independent confirmed BSL -> unconsumed nearest DOL -> later bull BOS -> backward demand POI -> touch/reclaim/hold -> next-session eligibility',
        'source_count': len(source_set), 'oracle_count': len(oracle_set),
        'v437_extra': len(source_extra), 'oracle_extra': len(oracle_extra),
        'mismatch_total': len(source_extra) + len(oracle_extra), 'stage_counts': dict(counts),
        'invariants': {'chronology_failures': chronology_failures,
                       'duplicate_oracle_identity': len(oracle_rows) - len(oracle_set),
                       'all_non_tradable': True, 'no_outcome_fields': True,
                       'identity_set_equal': source_set == oracle_set},
        'decision': ('INDEPENDENT_SEMANTIC_ORACLE_PASS__FROZEN_T1_REPLAY_NEXT'
                     if source_set == oracle_set and chronology_failures == 0 else
                     'INDEPENDENT_SEMANTIC_ORACLE_FAIL__STOP_TARGET_FIRST_DOL'),
        'artifacts': {'out_dir': str(OUT), 'oracle_rows': str(OUT / 'v438_oracle_unique_takeover_rows.csv'),
                      'mismatches': str(OUT / 'v438_differential_mismatches.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v438_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)
    if report['decision'].startswith('INDEPENDENT_SEMANTIC_ORACLE_FAIL'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
