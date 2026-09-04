#!/usr/bin/env python3
"""V435 no-write independent oracle for V434 Supply-Failure Breaker.

Re-derives confirmed swings, bearish structure events, event-anchored supply OBs,
and the breaker lifecycle without importing V27 or V434. It compares the complete
unique takeover identity set and never creates trades, outcomes, or production rows.
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
SOURCE = AUD / 'v434_supply_failure_breaker_latest.json'
OUT = AUD / f'v435_supply_failure_breaker_independent_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v435_supply_failure_breaker_independent_oracle_latest.json'
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
        if all(bars[j]['h'] < bars[idx]['h'] for j in range(idx - LEFT, idx + RIGHT + 1) if j != idx):
            highs.append({'idx': idx, 'price': bars[idx]['h'], 'confirm_idx': idx + RIGHT})
        if all(bars[j]['l'] > bars[idx]['l'] for j in range(idx - LEFT, idx + RIGHT + 1) if j != idx):
            lows.append({'idx': idx, 'price': bars[idx]['l'], 'confirm_idx': idx + RIGHT})
    return highs, lows


def structure_events(bars, highs, lows):
    broken, trend, events = set(), 'unknown', []
    for idx in range(STRUCTURE_START, len(bars)):
        bull_levels = sorted((x for x in highs if x['confirm_idx'] <= idx and ('high', x['idx']) not in broken),
                             key=lambda x: x['confirm_idx'], reverse=True)
        bull_break = next((x for x in bull_levels if bars[idx]['c'] > x['price'] * (1 + BREAK_BUFFER)), None)
        if bull_break:
            events.append({'direction': 'bull', 'type': 'BOS' if trend == 'bullish' else 'CHOCH',
                           'index': idx, 'broken_swing_idx': bull_break['idx'],
                           'confirm_visible_at': bull_break['confirm_idx']})
            broken.add(('high', bull_break['idx']))
            trend = 'bullish'
            continue
        bear_levels = sorted((x for x in lows if x['confirm_idx'] <= idx and ('low', x['idx']) not in broken),
                             key=lambda x: x['confirm_idx'], reverse=True)
        bear_break = next((x for x in bear_levels if bars[idx]['c'] < x['price'] * (1 - BREAK_BUFFER)), None)
        if bear_break:
            events.append({'direction': 'bear', 'type': 'BOS' if trend == 'bearish' else 'CHOCH',
                           'index': idx, 'broken_swing_idx': bear_break['idx'],
                           'confirm_visible_at': bear_break['confirm_idx']})
            broken.add(('low', bear_break['idx']))
            trend = 'bearish'
    return events


def supply_obs(bars, events):
    rows = []
    for event in events:
        if event['direction'] != 'bear':
            continue
        anchor = event['index']
        for idx in range(anchor - 1, max(0, anchor - OB_BACKSCAN - 1), -1):
            if bars[idx]['c'] > bars[idx]['o']:
                rows.append({'anchor_event_idx': anchor, 'event_type': event['type'], 'ob_idx': idx,
                             'zone_low': bars[idx]['l'], 'zone_high': bars[idx]['h']})
                break
    return rows


def breaker_lifecycle(bars, ob):
    state = 'WAIT_FAILURE'
    failure = touch = reclaim = takeover = None
    for idx in range(ob['anchor_event_idx'] + 1, len(bars)):
        close, low, high = bars[idx]['c'], bars[idx]['l'], bars[idx]['h']
        if state == 'WAIT_FAILURE':
            if close > ob['zone_high']:
                failure, state = idx, 'WAIT_TOUCH'
        elif close < ob['zone_low']:
            return None
        elif state == 'WAIT_TOUCH':
            if low <= ob['zone_high'] and high >= ob['zone_low']:
                touch, state = idx, 'WAIT_RECLAIM'
        elif state == 'WAIT_RECLAIM':
            if idx > touch and close > ob['zone_high']:
                reclaim, state = idx, 'WAIT_HOLD'
        elif idx > reclaim and close > ob['zone_high'] and low >= ob['zone_low']:
            takeover = idx
            break
    if takeover is None:
        return None
    eligible = takeover + 1 if takeover + 1 < len(bars) else None
    return failure, touch, reclaim, takeover, eligible


def identity(row):
    def integer(value):
        return int(value) if value not in ('', None) else -1
    return (str(row['symbol']), int(row['bear_event_idx']), int(row['supply_ob_idx']),
            int(row['supply_failure_idx']), int(row['touch_idx']), int(row['reclaim_idx']),
            int(row['takeover_idx']), integer(row['eligible_entry_idx']))


def main():
    source_report = json.loads(SOURCE.read_text())
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
        obs = supply_obs(bars, events)
        per_takeover = {}
        for ob in obs:
            lifecycle = breaker_lifecycle(bars, ob)
            if lifecycle is None:
                continue
            failure, touch, reclaim, takeover, eligible = lifecycle
            order = tuple(x for x in (ob['ob_idx'], ob['anchor_event_idx'], failure, touch, reclaim, takeover, eligible)
                          if x is not None)
            chronology_failures += int(not all(a < b for a, b in zip(order, order[1:])))
            row = {
                'symbol': sym, 'ontology': 'SUPPLY_FAILURE_BREAKER',
                'bear_event_idx': ob['anchor_event_idx'], 'bear_event_date': bars[ob['anchor_event_idx']]['t'],
                'supply_ob_idx': ob['ob_idx'], 'supply_ob_date': bars[ob['ob_idx']]['t'],
                'supply_failure_idx': failure, 'supply_failure_date': bars[failure]['t'],
                'touch_idx': touch, 'touch_date': bars[touch]['t'],
                'reclaim_idx': reclaim, 'reclaim_date': bars[reclaim]['t'],
                'takeover_idx': takeover, 'takeover_date': bars[takeover]['t'],
                'eligible_entry_idx': '' if eligible is None else eligible,
                'eligible_entry_date': '' if eligible is None else bars[eligible]['t'],
                'zone_low': ob['zone_low'], 'zone_high': ob['zone_high'],
                'tradable': 'false', 'buy_enabled': 'false', 'outcome_fields_present': 'false',
            }
            key = (sym, row['takeover_date'])
            old = per_takeover.get(key)
            if old is None or row['supply_ob_idx'] < old['supply_ob_idx']:
                per_takeover[key] = row
        oracle_rows.extend(per_takeover.values())
        if index % 500 == 0:
            print(json.dumps({'progress': index, 'oracle_unique': len(oracle_rows)}, ensure_ascii=False), flush=True)

    oracle_set = {identity(row) for row in oracle_rows}
    source_extra, oracle_extra = source_set - oracle_set, oracle_set - source_set
    mismatch_rows = ([{'disposition': 'V434_EXTRA', 'identity': repr(key)} for key in sorted(source_extra)] +
                     [{'disposition': 'ORACLE_EXTRA', 'identity': repr(key)} for key in sorted(oracle_extra)])
    with (OUT / 'v435_oracle_unique_takeover_rows.csv').open('w', newline='') as handle:
        fields = list(oracle_rows[0]) if oracle_rows else ['symbol', 'ontology']
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(oracle_rows)
    with (OUT / 'v435_differential_mismatches.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['disposition', 'identity']); writer.writeheader(); writer.writerows(mismatch_rows)

    report = {
        'version': 'V435_SUPPLY_FAILURE_BREAKER_INDEPENDENT_ORACLE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'oracle_contract': 'independent 3L/3R swings -> 0.2% bearish structure break -> nearest bullish candle <=10 bars -> supply failure/retest/reclaim/hold -> next-session eligibility',
        'source_count': len(source_set), 'oracle_count': len(oracle_set),
        'v434_extra': len(source_extra), 'oracle_extra': len(oracle_extra),
        'mismatch_total': len(source_extra) + len(oracle_extra),
        'stage_counts': dict(counts),
        'invariants': {'chronology_failures': chronology_failures, 'all_non_tradable': True,
                       'no_outcome_fields': True, 'identity_set_equal': source_set == oracle_set},
        'decision': ('INDEPENDENT_SEMANTIC_ORACLE_PASS__FROZEN_T1_REPLAY_NEXT'
                     if source_set == oracle_set and chronology_failures == 0 else
                     'INDEPENDENT_SEMANTIC_ORACLE_FAIL__STOP_SUPPLY_FAILURE_BREAKER'),
        'artifacts': {'out_dir': str(OUT), 'oracle_rows': str(OUT / 'v435_oracle_unique_takeover_rows.csv'),
                      'mismatches': str(OUT / 'v435_differential_mismatches.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v435_report.json').write_text(text); LATEST.write_text(text)
    print(text)
    if report['decision'].startswith('INDEPENDENT_SEMANTIC_ORACLE_FAIL'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
