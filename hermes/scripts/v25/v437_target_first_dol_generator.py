#!/usr/bin/env python3
"""V437 no-write Target-First Draw-on-Liquidity semantic generator.

Frozen ontology, defined before outcomes:
known unconsumed BSL target first -> later bullish BOS toward that target ->
event-anchored demand POI -> first touch -> later reclaim -> later hold ->
next-session eligibility while the DOL remains unconsumed.
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
OUT = AUD / f'v437_target_first_dol_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v437_target_first_dol_latest.json'
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


def choose_dol(bars, confirmed_highs, event_idx):
    """Nearest BSL above event close, visible and still unconsumed before event."""
    event_close = f(bars[event_idx].get('c'))
    candidates = []
    for high in confirmed_highs:
        confirm_idx, price = int(high['confirm_idx']), f(high['price'])
        if confirm_idx >= event_idx or price <= event_close:
            continue
        if any(f(bars[idx].get('h')) >= price for idx in range(confirm_idx + 1, event_idx)):
            continue
        candidates.append(high)
    return min(candidates, default=None, key=lambda row: (f(row['price']), -int(row['confirm_idx'])))


def demand_poi(bars, event_idx):
    """Nearest bearish candle before the same bullish event."""
    for idx in range(event_idx - 1, max(-1, event_idx - OB_BACKSCAN - 1), -1):
        if f(bars[idx].get('c')) < f(bars[idx].get('o')):
            return {'idx': idx, 'zone_low': f(bars[idx].get('l')), 'zone_high': f(bars[idx].get('h'))}
    return None


def lifecycle(bars, event_idx, zone_low, zone_high, dol_price):
    touch = reclaim = takeover = None
    for idx in range(event_idx + 1, len(bars)):
        bar = bars[idx]
        close, low, high, opening = (f(bar.get(key)) for key in ('c', 'l', 'h', 'o'))
        if high >= dol_price:
            return {'status': 'CANCEL_DOL_CONSUMED_BEFORE_ENTRY', 'state_idx': idx,
                    'touch_idx': touch, 'reclaim_idx': reclaim, 'takeover_idx': takeover,
                    'eligible_entry_idx': None}
        if close < zone_low:
            return {'status': 'CANCEL_POI_INVALIDATED', 'state_idx': idx,
                    'touch_idx': touch, 'reclaim_idx': reclaim, 'takeover_idx': takeover,
                    'eligible_entry_idx': None}
        if touch is None:
            if low <= zone_high and high >= zone_low:
                touch = idx
            continue
        if reclaim is None:
            if idx > touch and close > zone_high:
                reclaim = idx
            continue
        if idx > reclaim and close > zone_high and low >= zone_low:
            takeover = idx
            eligible = idx + 1
            if eligible >= len(bars):
                return {'status': 'WAIT_ENTRY_UNOBSERVED', 'state_idx': None,
                        'touch_idx': touch, 'reclaim_idx': reclaim, 'takeover_idx': takeover,
                        'eligible_entry_idx': None}
            entry_open = f(bars[eligible].get('o'))
            if entry_open >= dol_price:
                return {'status': 'CANCEL_ENTRY_GAP_CONSUMED_DOL', 'state_idx': eligible,
                        'touch_idx': touch, 'reclaim_idx': reclaim, 'takeover_idx': takeover,
                        'eligible_entry_idx': None}
            if entry_open <= zone_low:
                return {'status': 'CANCEL_ENTRY_GAP_INVALIDATED_POI', 'state_idx': eligible,
                        'touch_idx': touch, 'reclaim_idx': reclaim, 'takeover_idx': takeover,
                        'eligible_entry_idx': None}
            return {'status': 'TAKEOVER_CONFIRMED', 'state_idx': takeover,
                    'touch_idx': touch, 'reclaim_idx': reclaim, 'takeover_idx': takeover,
                    'eligible_entry_idx': eligible}
    if touch is None:
        status = 'WAIT_TOUCH_UNOBSERVED'
    elif reclaim is None:
        status = 'WAIT_RECLAIM_UNOBSERVED'
    else:
        status = 'WAIT_HOLD_UNOBSERVED'
    return {'status': status, 'state_idx': None, 'touch_idx': touch,
            'reclaim_idx': reclaim, 'takeover_idx': takeover, 'eligible_entry_idx': None}


def at(bars, idx):
    return day(bars[idx]) if isinstance(idx, int) and 0 <= idx < len(bars) else ''


def semantic_order_valid(dol_confirm_idx, poi_idx, event_idx, result):
    """Check information visibility, not the POI candle's historical position.

    The demand candle is physically before its anchoring BOS but becomes a usable
    POI only when that BOS occurs. DOL confirmation and POI index therefore both
    need to precede the event; neither must precede the other.
    """
    if not (dol_confirm_idx < event_idx and poi_idx < event_idx):
        return False
    lifecycle_indices = [event_idx]
    lifecycle_indices.extend(result[key] for key in ('touch_idx', 'reclaim_idx', 'takeover_idx', 'eligible_entry_idx')
                             if result.get(key) is not None)
    return all(left < right for left, right in zip(lifecycle_indices, lifecycle_indices[1:]))


def one_symbol(sym, bars):
    swings = v27.confirmed_swings([dict(row) for row in bars])
    events = v27.structure_signals([dict(row) for row in bars], swings)
    rows = []
    for event in events:
        if event.get('direction') != 'bull' or event.get('type') != 'BOS':
            continue
        event_idx = int(event['index'])
        dol = choose_dol(bars, swings.get('highs', []), event_idx)
        poi = demand_poi(bars, event_idx)
        if dol is None or poi is None:
            continue
        result = lifecycle(bars, event_idx, poi['zone_low'], poi['zone_high'], f(dol['price']))
        rows.append({
            'symbol': sym, 'ontology': 'TARGET_FIRST_DOL',
            'dol_idx': int(dol['idx']), 'dol_date': at(bars, int(dol['idx'])),
            'dol_confirm_idx': int(dol['confirm_idx']), 'dol_confirm_date': at(bars, int(dol['confirm_idx'])),
            'dol_price': round(f(dol['price']), 6),
            'event_type': event.get('type'), 'event_idx': event_idx, 'event_date': at(bars, event_idx),
            'broken_swing_idx': int(event.get('broken_swing_idx')),
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
            'lifecycle_state': result['status'],
            'semantic_order_valid': semantic_order_valid(int(dol['confirm_idx']), poi['idx'], event_idx, result),
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
        old = unique.get(key)
        rank = (f(row['dol_price']), int(row['event_idx']), int(row['poi_idx']))
        old_rank = ((f(old['dol_price']), int(old['event_idx']), int(old['poi_idx'])) if old else None)
        if old is None or rank < old_rank:
            unique[key] = row
    unique_rows = list(unique.values())
    yearly = Counter(row['eligible_entry_date'][:4] for row in unique_rows
                     if row['eligible_entry_date'][:4] in {'2023', '2024', '2025', '2026'})
    chronology_failures = sum(not row['semantic_order_valid'] for row in rows)
    support_pass = all(yearly.get(year, 0) >= 40 for year in ('2023', '2024', '2025', '2026'))

    fields = list(rows[0]) if rows else ['symbol', 'ontology']
    with (OUT / 'v437_target_first_dol_rows.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    with (OUT / 'v437_unique_takeover_rows.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(unique_rows)

    report = {
        'version': 'V437_TARGET_FIRST_DOL_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'frozen_contract': 'known unconsumed confirmed BSL first -> later bullish BOS -> backward demand POI -> touch -> later reclaim -> later hold -> next-open eligibility while DOL remains unconsumed',
        'distinct_from_closed_R1_R5': 'The candidate universe begins with a pre-existing external liquidity destination; DOL validity is checked before event and throughout setup formation. It is not an SSL reversal, raw demand continuation, balance, PO3, or exit variant.',
        'stage_counts': dict(counts), 'rows': len(rows),
        'takeover_rows_raw': len(completed), 'takeover_rows_unique': len(unique_rows),
        'yearly_unique_takeover': dict(yearly),
        'support_gate': {'each_2023_2026_at_least_40': support_pass},
        'invariants': {
            'semantic_order_failures': chronology_failures,
            'duplicate_symbol_takeover_day_after_dedup': len(unique_rows) - len(set((row['symbol'], row['takeover_date']) for row in unique_rows)),
            'all_non_tradable': all(row['tradable'] == 'false' and row['buy_enabled'] == 'false' for row in rows),
            'no_outcome_fields': all(row['outcome_fields_present'] == 'false' for row in rows),
        },
        'decision': ('TARGET_FIRST_DOL_SEMANTIC_READY__INDEPENDENT_ORACLE_NEXT'
                     if support_pass and chronology_failures == 0 else
                     'TARGET_FIRST_DOL_PRE_OUTCOME_GATE_FAIL__CLOSE_ONTOLOGY'),
        'artifacts': {'out_dir': str(OUT), 'rows': str(OUT / 'v437_target_first_dol_rows.csv'),
                      'unique_takeover': str(OUT / 'v437_unique_takeover_rows.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v437_report.json').write_text(text); LATEST.write_text(text)
    print(text)
    if report['decision'].endswith('CLOSE_ONTOLOGY'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
