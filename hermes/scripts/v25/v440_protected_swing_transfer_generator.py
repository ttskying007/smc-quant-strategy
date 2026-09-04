#!/usr/bin/env python3
"""V440 no-write Protected-Swing Transfer semantic generator.

Frozen ontology before outcomes:
first bull BOS establishes an old protected low -> a later higher confirmed swing
low forms without the old boundary closing invalid -> a later bull BOS transfers
protection to the higher low -> transfer-leg demand POI -> touch/reclaim/hold ->
next-session eligibility. No outcomes or production writes are permitted.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
KDIR, AUD = ROOT / 'kline_cache', ROOT / 'smc_audit'
OUT = AUD / f'v440_protected_swing_transfer_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v440_protected_swing_transfer_latest.json'
OB_BACKSCAN = 10

spec = importlib.util.spec_from_file_location('v27', ROOT / 'scripts/v25/smc_core_v27.py')
v27 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v27)


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


def protected_transfer(bars, confirmed_lows, previous_event_idx, event_idx):
    old_candidates = [row for row in confirmed_lows if row['confirm_idx'] < previous_event_idx]
    new_candidates = [row for row in confirmed_lows
                      if row['idx'] > previous_event_idx and row['confirm_idx'] < event_idx]
    if not old_candidates or not new_candidates:
        return None
    old = max(old_candidates, key=lambda row: row['confirm_idx'])
    new = max(new_candidates, key=lambda row: row['confirm_idx'])
    if f(new['price']) <= f(old['price']):
        return None
    if any(f(bars[idx]['c']) < f(old['price']) for idx in range(previous_event_idx + 1, event_idx)):
        return None
    return {'old': old, 'new': new}


def demand_poi(bars, event_idx, new_swing_idx):
    lower = max(new_swing_idx, event_idx - OB_BACKSCAN)
    for idx in range(event_idx - 1, lower - 1, -1):
        if f(bars[idx]['c']) < f(bars[idx]['o']):
            return {'idx': idx, 'zone_low': f(bars[idx]['l']), 'zone_high': f(bars[idx]['h'])}
    return None


def lifecycle_detail(bars, event_idx, zone_low, zone_high, protected_low):
    touch = reclaim = None
    for idx in range(event_idx + 1, len(bars)):
        bar = bars[idx]
        if f(bar['c']) < protected_low:
            return {'status': 'CANCEL_NEW_PROTECTED_LOW_INVALIDATED', 'touch_idx': touch,
                    'reclaim_idx': reclaim, 'takeover_idx': None, 'eligible_entry_idx': None}
        if touch is None:
            if f(bar['l']) <= zone_high and f(bar['h']) >= zone_low:
                touch = idx
            continue
        if reclaim is None:
            if idx > touch and f(bar['c']) > zone_high:
                reclaim = idx
            continue
        if idx > reclaim and f(bar['c']) > zone_high and f(bar['l']) >= protected_low:
            eligible = idx + 1
            if eligible >= len(bars):
                return {'status': 'WAIT_ENTRY_UNOBSERVED', 'touch_idx': touch,
                        'reclaim_idx': reclaim, 'takeover_idx': idx, 'eligible_entry_idx': None}
            if f(bars[eligible]['o']) <= protected_low:
                return {'status': 'CANCEL_ENTRY_GAP_INVALIDATED_PROTECTED_LOW', 'touch_idx': touch,
                        'reclaim_idx': reclaim, 'takeover_idx': idx, 'eligible_entry_idx': None}
            return {'status': 'TAKEOVER_CONFIRMED', 'touch_idx': touch,
                    'reclaim_idx': reclaim, 'takeover_idx': idx, 'eligible_entry_idx': eligible}
    status = 'WAIT_TOUCH_UNOBSERVED' if touch is None else ('WAIT_RECLAIM_UNOBSERVED' if reclaim is None else 'WAIT_HOLD_UNOBSERVED')
    return {'status': status, 'touch_idx': touch, 'reclaim_idx': reclaim,
            'takeover_idx': None, 'eligible_entry_idx': None}


def lifecycle(bars, event_idx, zone_low, zone_high, protected_low):
    result = lifecycle_detail(bars, event_idx, zone_low, zone_high, protected_low)
    if result['status'] != 'TAKEOVER_CONFIRMED':
        return None
    return result['touch_idx'], result['reclaim_idx'], result['takeover_idx'], result['eligible_entry_idx']


def at(bars, idx):
    return bars[idx]['t'] if isinstance(idx, int) and 0 <= idx < len(bars) else ''


def one_symbol(sym, bars):
    swings = v27.confirmed_swings([dict(row) for row in bars])
    events = v27.structure_signals([dict(row) for row in bars], swings)
    bull_bos = [event for event in events if event.get('direction') == 'bull' and event.get('type') == 'BOS']
    rows = []
    for previous, event in zip(bull_bos, bull_bos[1:]):
        previous_idx, event_idx = int(previous['index']), int(event['index'])
        transfer = protected_transfer(bars, swings.get('lows', []), previous_idx, event_idx)
        if transfer is None:
            continue
        old, new = transfer['old'], transfer['new']
        poi = demand_poi(bars, event_idx, int(new['idx']))
        if poi is None:
            continue
        result = lifecycle_detail(bars, event_idx, poi['zone_low'], poi['zone_high'], f(new['price']))
        indices = [previous_idx, int(new['idx']), int(new['confirm_idx']), event_idx]
        indices.extend(result[key] for key in ('touch_idx', 'reclaim_idx', 'takeover_idx', 'eligible_entry_idx')
                       if result.get(key) is not None)
        chronology = (int(old['confirm_idx']) < previous_idx < int(new['idx']) < int(new['confirm_idx']) < event_idx
                      and poi['idx'] >= int(new['idx']) and poi['idx'] < event_idx
                      and all(left < right for left, right in zip(indices, indices[1:])))
        rows.append({
            'symbol': sym, 'ontology': 'PROTECTED_SWING_TRANSFER',
            'previous_bos_idx': previous_idx, 'previous_bos_date': at(bars, previous_idx),
            'old_protected_low_idx': int(old['idx']), 'old_protected_low_date': at(bars, int(old['idx'])),
            'old_protected_low_price': round(f(old['price']), 6),
            'new_protected_low_idx': int(new['idx']), 'new_protected_low_date': at(bars, int(new['idx'])),
            'new_protected_low_confirm_idx': int(new['confirm_idx']),
            'new_protected_low_confirm_date': at(bars, int(new['confirm_idx'])),
            'new_protected_low_price': round(f(new['price']), 6),
            'transfer_bos_idx': event_idx, 'transfer_bos_date': at(bars, event_idx),
            'broken_swing_idx': int(event['broken_swing_idx']),
            'poi_idx': poi['idx'], 'poi_date': at(bars, poi['idx']),
            'zone_low': round(poi['zone_low'], 6), 'zone_high': round(poi['zone_high'], 6),
            'touch_idx': '' if result['touch_idx'] is None else result['touch_idx'],
            'touch_date': at(bars, result['touch_idx']),
            'reclaim_idx': '' if result['reclaim_idx'] is None else result['reclaim_idx'],
            'reclaim_date': at(bars, result['reclaim_idx']),
            'takeover_idx': '' if result['takeover_idx'] is None else result['takeover_idx'],
            'takeover_date': at(bars, result['takeover_idx']),
            'eligible_entry_idx': '' if result['eligible_entry_idx'] is None else result['eligible_entry_idx'],
            'eligible_entry_date': at(bars, result['eligible_entry_idx']),
            'lifecycle_state': result['status'], 'semantic_order_valid': chronology,
            'tradable': 'false', 'buy_enabled': 'false', 'outcome_fields_present': 'false',
        })
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows, counts = [], Counter()
    for index, path in enumerate(sorted(KDIR.glob('*_daily_750.json')), 1):
        bars = load_bars(path)
        if len(bars) < 60:
            continue
        counts['symbols_scanned'] += 1
        generated = one_symbol(symbol(path), bars)
        rows.extend(generated)
        for row in generated:
            counts[row['lifecycle_state']] += 1
        if index % 500 == 0:
            print(json.dumps({'progress': index, 'rows': len(rows)}, ensure_ascii=False), flush=True)

    completed = [row for row in rows if row['lifecycle_state'] == 'TAKEOVER_CONFIRMED']
    unique = {}
    for row in completed:
        key = (row['symbol'], row['takeover_date'])
        rank = (int(row['transfer_bos_idx']), int(row['new_protected_low_idx']), int(row['poi_idx']))
        old = unique.get(key)
        old_rank = ((int(old['transfer_bos_idx']), int(old['new_protected_low_idx']), int(old['poi_idx'])) if old else None)
        if old is None or rank < old_rank:
            unique[key] = row
    unique_rows = list(unique.values())
    yearly = Counter(row['eligible_entry_date'][:4] for row in unique_rows
                     if row['eligible_entry_date'][:4] in {'2023', '2024', '2025', '2026'})
    chronology_failures = sum(not row['semantic_order_valid'] for row in rows)
    support_pass = all(yearly.get(year, 0) >= 40 for year in ('2023', '2024', '2025', '2026'))

    fields = list(rows[0]) if rows else ['symbol', 'ontology']
    with (OUT / 'v440_protected_swing_transfer_rows.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    with (OUT / 'v440_unique_takeover_rows.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(unique_rows)
    report = {
        'version': 'V440_PROTECTED_SWING_TRANSFER_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'frozen_contract': 'bull BOS establishes old protected low -> higher confirmed swing low while old boundary holds -> later bull BOS transfers protection -> transfer-leg demand POI -> touch/reclaim/hold -> next-open eligibility',
        'distinct_from_closed_R1_R5': 'The causal identity is a two-BOS migration of the protected invalidation boundary, not a single event/POI pattern or an exit variant.',
        'stage_counts': dict(counts), 'rows': len(rows),
        'takeover_rows_raw': len(completed), 'takeover_rows_unique': len(unique_rows),
        'yearly_unique_takeover': dict(yearly),
        'support_gate': {'each_2023_2026_at_least_40': support_pass},
        'invariants': {'semantic_order_failures': chronology_failures,
                       'duplicate_symbol_takeover_day_after_dedup': len(unique_rows) - len(set((row['symbol'], row['takeover_date']) for row in unique_rows)),
                       'all_non_tradable': all(row['tradable'] == 'false' and row['buy_enabled'] == 'false' for row in rows),
                       'no_outcome_fields': all(row['outcome_fields_present'] == 'false' for row in rows)},
        'decision': ('PROTECTED_SWING_TRANSFER_SEMANTIC_READY__INDEPENDENT_ORACLE_NEXT'
                     if support_pass and chronology_failures == 0 else
                     'PROTECTED_SWING_TRANSFER_PRE_OUTCOME_GATE_FAIL__CLOSE_ONTOLOGY'),
        'artifacts': {'out_dir': str(OUT), 'rows': str(OUT / 'v440_protected_swing_transfer_rows.csv'),
                      'unique_takeover': str(OUT / 'v440_unique_takeover_rows.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v440_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)
    if report['decision'].endswith('CLOSE_ONTOLOGY'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
