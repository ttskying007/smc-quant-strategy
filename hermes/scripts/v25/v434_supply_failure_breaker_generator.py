#!/usr/bin/env python3
"""V434 no-write Supply-Failure Breaker semantic/lifecycle generator.

Ontology (fixed before outcomes):
confirmed bearish structure event -> event-anchored supply OB -> first close above
supply high (supply failure) -> first retest -> reclaim above former supply -> one
hold bar -> next-session eligible entry. No outcomes or production artifacts.
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
OUT = AUD / f'v434_supply_failure_breaker_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v434_supply_failure_breaker_latest.json'

spec = importlib.util.spec_from_file_location('v27', ROOT / 'scripts/v25/smc_core_v27.py')
v27 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v27)


def f(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else 0.0
    except (TypeError, ValueError):
        return 0.0


def day(bar):
    return ''.join(c for c in str(bar.get('t') or bar.get('date') or '') if c.isdigit())[:8]


def load(path):
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return []
    return sorted([b for b in raw if day(b) and all(f(b.get(k)) > 0 for k in ('o','h','l','c'))], key=day)


def symbol(path):
    stem = path.name.replace('_daily_750.json', '')
    code, exchange = stem.split('_')
    return f'{code}.{exchange}'


def at(ks, idx):
    return day(ks[idx]) if isinstance(idx, int) and 0 <= idx < len(ks) else ''


def lifecycle(ks, anchor_i, low, high):
    failure = touch = reclaim = None
    for idx in range(anchor_i + 1, len(ks)):
        bar = ks[idx]
        close, bar_low, bar_high = f(bar.get('c')), f(bar.get('l')), f(bar.get('h'))
        if failure is None:
            if close > high:
                failure = idx
            continue
        if touch is None:
            if close < low:
                return 'CANCEL_BREAKER_INVALIDATED', idx, failure, None, None
            if bar_low <= high and bar_high >= low:
                touch = idx
            continue
        if reclaim is None:
            if close < low:
                return 'CANCEL_BREAKER_INVALIDATED', idx, failure, touch, None
            if idx > touch and close > high:
                reclaim = idx
            continue
        if close < low:
            return 'CANCEL_BREAKER_INVALIDATED', idx, failure, touch, reclaim
        if idx > reclaim and close > high and bar_low >= low:
            return 'TAKEOVER_CONFIRMED', idx, failure, touch, reclaim
    if failure is None:
        return 'WAIT_SUPPLY_FAILURE_UNOBSERVED', None, None, None, None
    if touch is None:
        return 'WAIT_RETEST_UNOBSERVED', None, failure, None, None
    if reclaim is None:
        return 'WAIT_RECLAIM_UNOBSERVED', None, failure, touch, None
    return 'WAIT_HOLD_UNOBSERVED', None, failure, touch, reclaim


def one_symbol(sym, ks):
    swings = v27.confirmed_swings([dict(x) for x in ks])
    structure = v27.structure_signals([dict(x) for x in ks], swings)
    obs = v27.ob_signals([dict(x) for x in ks], structure)
    rows = []
    for ob in obs:
        if ob.get('direction') != 'bear':
            continue
        anchor_i, ob_i = int(ob['anchor_event_idx']), int(ob['index'])
        # The same candle may be the nearest supply OB for multiple independently
        # confirmed bearish events. Event identity is causal and must not be
        # collapsed by OB index before the lifecycle is evaluated.
        low, high = f(ob['zone_low']), f(ob['zone_high'])
        status, state_i, failure_i, touch_i, reclaim_i = lifecycle(ks, anchor_i, low, high)
        eligible_i = state_i + 1 if status == 'TAKEOVER_CONFIRMED' and state_i + 1 < len(ks) else None
        order = [ob_i, anchor_i]
        order.extend(x for x in (failure_i, touch_i, reclaim_i, state_i, eligible_i) if x is not None)
        rows.append({
            'symbol': sym,
            'ontology': 'SUPPLY_FAILURE_BREAKER',
            'bear_event_type': ob.get('anchor_event'),
            'bear_event_idx': anchor_i, 'bear_event_date': at(ks, anchor_i),
            'supply_ob_idx': ob_i, 'supply_ob_date': at(ks, ob_i),
            'zone_low': round(low, 6), 'zone_high': round(high, 6),
            'supply_failure_idx': '' if failure_i is None else failure_i,
            'supply_failure_date': at(ks, failure_i),
            'touch_idx': '' if touch_i is None else touch_i, 'touch_date': at(ks, touch_i),
            'reclaim_idx': '' if reclaim_i is None else reclaim_i, 'reclaim_date': at(ks, reclaim_i),
            'takeover_idx': '' if state_i is None else state_i,
            'takeover_date': at(ks, state_i) if status == 'TAKEOVER_CONFIRMED' else '',
            'eligible_entry_idx': '' if eligible_i is None else eligible_i,
            'eligible_entry_date': at(ks, eligible_i),
            'lifecycle_state': status,
            'semantic_order_valid': all(a < b for a, b in zip(order, order[1:])),
            'tradable': 'false', 'buy_enabled': 'false', 'outcome_fields_present': 'false',
        })
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows, counts = [], Counter()
    for index, path in enumerate(sorted(KDIR.glob('*_daily_750.json')), 1):
        ks = load(path)
        if len(ks) < 60:
            continue
        counts['symbols_scanned'] += 1
        generated = one_symbol(symbol(path), ks)
        rows.extend(generated)
        for row in generated:
            counts[row['lifecycle_state']] += 1
        if index % 500 == 0:
            print(json.dumps({'progress': index, 'rows': len(rows)}, ensure_ascii=False), flush=True)

    # One execution identity per stock/takeover day; keep the earliest causal OB.
    takeover = [r for r in rows if r['lifecycle_state'] == 'TAKEOVER_CONFIRMED']
    dedup = {}
    for row in takeover:
        key = (row['symbol'], row['takeover_date'])
        old = dedup.get(key)
        if old is None or row['supply_ob_idx'] < old['supply_ob_idx']:
            dedup[key] = row
    unique_takeover = list(dedup.values())
    yearly = Counter(r['takeover_date'][:4] for r in unique_takeover if r['takeover_date'][:4] in {'2023','2024','2025','2026'})
    bad_order = sum(not r['semantic_order_valid'] for r in rows)
    support_pass = all(yearly.get(y, 0) >= 40 for y in ('2023','2024','2025','2026'))

    fields = list(rows[0]) if rows else ['symbol','ontology']
    with (OUT / 'v434_supply_failure_breaker_rows.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    with (OUT / 'v434_unique_takeover_rows.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(unique_takeover)

    report = {
        'version': 'V434_SUPPLY_FAILURE_BREAKER_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'frozen_contract': 'confirmed bear structure -> backward supply OB -> first close above supply high -> first retest -> later reclaim above high -> later hold above zone -> next-session eligible entry',
        'distinct_from_closed_R1_R5': 'No SSL/CHOCH reversal, bullish demand continuation, two-sided balance, or PO3 prerequisite; starts from failure and role reversal of a causally anchored bearish supply OB.',
        'stage_counts': dict(counts),
        'rows': len(rows), 'takeover_rows_raw': len(takeover), 'takeover_rows_unique': len(unique_takeover),
        'yearly_unique_takeover': dict(yearly),
        'support_gate': {'each_2023_2026_at_least_40': support_pass},
        'invariants': {
            'semantic_order_failures': bad_order,
            'duplicate_symbol_takeover_day_after_dedup': len(unique_takeover) - len(set((r['symbol'], r['takeover_date']) for r in unique_takeover)),
            'all_non_tradable': all(r['tradable'] == 'false' and r['buy_enabled'] == 'false' for r in rows),
            'no_outcome_fields': all(r['outcome_fields_present'] == 'false' for r in rows),
        },
        'decision': ('SEMANTIC_SUPPLY_READY__INDEPENDENT_ORACLE_NEXT' if support_pass and bad_order == 0 else
                     'SUPPLY_FAILURE_BREAKER_PRE_OUTCOME_GATE_FAIL__STOP'),
        'artifacts': {'out_dir': str(OUT), 'rows': str(OUT / 'v434_supply_failure_breaker_rows.csv'),
                      'unique_takeover': str(OUT / 'v434_unique_takeover_rows.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v434_report.json').write_text(text); LATEST.write_text(text)
    print(text)
    if report['decision'].endswith('STOP'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
