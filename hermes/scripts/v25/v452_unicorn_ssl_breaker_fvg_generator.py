#!/usr/bin/env python3
"""V452 no-outcome generator for the bullish ICT Unicorn model.

Frozen ontology before outcomes:
confirmed SSL -> wick raid/reclaim -> bullish CHOCH -> failed event-anchored
supply OB overlapping a bullish FVG -> first overlap retest -> reclaim -> hold ->
next-session eligibility.  It writes no production, entry, exit, or PnL data.
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
OUT = AUD / f'v452_unicorn_ssl_breaker_fvg_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v452_unicorn_ssl_breaker_fvg_latest.json'

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


def load(path):
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    rows = []
    for bar in raw:
        row = {key: f(bar.get(key)) for key in ('o', 'h', 'l', 'c')}
        if day(bar) and all(row.values()):
            row['t'] = day(bar)
            rows.append(row)
    return sorted(rows, key=lambda row: row['t'])


def symbol(path):
    code, exchange = path.name.removesuffix('_daily_750.json').split('_')
    return f'{code}.{exchange}'


def bull_fvgs(bars):
    rows = []
    for idx in range(2, len(bars)):
        low, high = bars[idx - 2]['h'], bars[idx]['l']
        if high > low * 1.0005:
            rows.append({'idx': idx, 'low': low, 'high': high})
    return rows


def first_lifecycle(bars, born, zone_low, zone_high, ssl_low):
    touch = reclaim = None
    for idx in range(born + 1, min(len(bars), born + 31)):
        bar = bars[idx]
        if bar['c'] < min(zone_low, ssl_low):
            return 'CANCEL_UNICORN_INVALIDATED', idx, touch, reclaim
        if touch is None:
            if bar['l'] <= zone_high and bar['h'] >= zone_low:
                touch = idx
            continue
        if reclaim is None:
            if idx > touch and bar['c'] > zone_high:
                reclaim = idx
            continue
        if idx > reclaim and bar['c'] > zone_high and bar['l'] >= zone_low:
            return 'TAKEOVER_CONFIRMED', idx, touch, reclaim
    if touch is None:
        return 'EXPIRE_NO_RETEST_30B', None, None, None
    if reclaim is None:
        return 'EXPIRE_NO_RECLAIM_30B', None, touch, None
    return 'EXPIRE_NO_HOLD_30B', None, touch, reclaim


def one_symbol(sym, bars):
    swings = v27.confirmed_swings([dict(row) for row in bars])
    events = v27.structure_signals([dict(row) for row in bars], swings)
    obs = v27.ob_signals([dict(row) for row in bars], events)
    lows = swings.get('lows', [])
    choch = [event for event in events if event.get('direction') == 'bull' and event.get('type') == 'CHOCH']
    supply = [ob for ob in obs if ob.get('direction') == 'bear']
    fvgs = bull_fvgs(bars)
    rows, rejects = [], Counter()

    for event in choch:
        event_idx = int(event['index'])
        ssl_candidates = []
        for low in lows:
            pivot, visible, price = int(low['idx']), int(low['confirm_idx']), f(low['price'])
            if visible >= event_idx or event_idx - pivot > 80:
                continue
            for raid in range(visible + 1, event_idx + 1):
                if bars[raid]['l'] < price * 0.997 and bars[raid]['c'] > price and event_idx - raid <= 20:
                    ssl_candidates.append((raid, pivot, visible, price))
        if not ssl_candidates:
            rejects['NO_CONFIRMED_SSL_RAID'] += 1
            continue
        raid, ssl_idx, ssl_confirm, ssl_price = max(ssl_candidates)

        failed_supply = [ob for ob in supply
                         if int(ob['anchor_event_idx']) < raid
                         and raid - int(ob['anchor_event_idx']) <= 60
                         and bars[event_idx]['c'] > f(ob['zone_high'])]
        if not failed_supply:
            rejects['NO_FAILED_CAUSAL_SUPPLY_OB'] += 1
            continue
        failed_supply.sort(key=lambda ob: (int(ob['anchor_event_idx']), int(ob['index'])), reverse=True)

        displacement_fvgs = [gap for gap in fvgs if raid <= gap['idx'] <= event_idx + 2]
        if not displacement_fvgs:
            rejects['NO_BULL_FVG_IN_CHOCH_LEG'] += 1
            continue

        chosen = None
        for ob in failed_supply:
            for gap in sorted(displacement_fvgs, key=lambda item: item['idx'], reverse=True):
                overlap_low = max(f(ob['zone_low']), gap['low'])
                overlap_high = min(f(ob['zone_high']), gap['high'])
                if overlap_high > overlap_low * 1.0005:
                    chosen = (ob, gap, overlap_low, overlap_high)
                    break
            if chosen:
                break
        if chosen is None:
            rejects['NO_BREAKER_FVG_OVERLAP'] += 1
            continue

        ob, gap, zone_low, zone_high = chosen
        born = max(event_idx, gap['idx'])
        status, state_idx, touch, reclaim = first_lifecycle(
            bars, born, zone_low, zone_high, min(ssl_price, bars[raid]['l']))
        if status != 'TAKEOVER_CONFIRMED' or state_idx + 1 >= len(bars):
            rejects[status] += 1
            continue
        eligible = state_idx + 1
        chronology = (int(ob['index']) < int(ob['anchor_event_idx']) < raid <= event_idx
                      and raid <= gap['idx'] <= event_idx + 2
                      and born < touch < reclaim < state_idx < eligible)
        rows.append({
            'symbol': sym, 'ontology': 'SSL_CHOCH_UNICORN_BREAKER_FVG',
            'ssl_idx': ssl_idx, 'ssl_confirm_idx': ssl_confirm, 'ssl_price': round(ssl_price, 6),
            'raid_idx': raid, 'raid_date': bars[raid]['t'], 'raid_low': round(bars[raid]['l'], 6),
            'choch_idx': event_idx, 'choch_date': bars[event_idx]['t'],
            'broken_swing_idx': int(event['broken_swing_idx']),
            'supply_ob_idx': int(ob['index']), 'supply_event_idx': int(ob['anchor_event_idx']),
            'supply_low': round(f(ob['zone_low']), 6), 'supply_high': round(f(ob['zone_high']), 6),
            'bull_fvg_idx': gap['idx'], 'bull_fvg_low': round(gap['low'], 6), 'bull_fvg_high': round(gap['high'], 6),
            'zone_low': round(zone_low, 6), 'zone_high': round(zone_high, 6),
            'touch_idx': touch, 'touch_date': bars[touch]['t'],
            'reclaim_idx': reclaim, 'reclaim_date': bars[reclaim]['t'],
            'takeover_idx': state_idx, 'takeover_date': bars[state_idx]['t'],
            'eligible_entry_idx': eligible, 'eligible_entry_date': bars[eligible]['t'],
            'structural_sl_ref': round(min(ssl_price, bars[raid]['l'], zone_low), 6),
            'semantic_order_valid': chronology, 'tradable': False, 'buy_enabled': False,
            'no_outcome_fields': True,
        })
    return rows, rejects


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows, rejects = [], Counter()
    scanned = 0
    for index, path in enumerate(sorted(KDIR.glob('*_daily_750.json')), 1):
        bars = load(path)
        if len(bars) < 100:
            continue
        scanned += 1
        generated, bad = one_symbol(symbol(path), bars)
        rows.extend(generated)
        rejects.update(bad)
        if index % 500 == 0:
            print(json.dumps({'progress': index, 'seeds': len(rows)}, ensure_ascii=False), flush=True)

    dedup = {}
    for row in rows:
        key = (row['symbol'], row['eligible_entry_date'])
        old = dedup.get(key)
        if old is None or row['choch_idx'] < old['choch_idx']:
            dedup[key] = row
    seeds = list(dedup.values())
    yearly = Counter(row['eligible_entry_date'][:4] for row in seeds)
    fields = list(seeds[0]) if seeds else ['symbol', 'ontology']
    seed_file = OUT / 'v452_semantic_seeds.csv'
    with seed_file.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(seeds)
    support = len(seeds) >= 300 and all(yearly.get(year, 0) >= 40 for year in ('2023','2024','2025','2026'))
    report = {
        'version': 'V452_UNICORN_SSL_BREAKER_FVG_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'frozen_contract': 'confirmed SSL raid/reclaim -> bull CHOCH -> prior causal supply OB fails -> bull displacement FVG overlaps breaker -> first retest/reclaim/hold -> next-open eligibility',
        'distinct_information': 'ICT Unicorn intersection of liquidity raid, structure shift, failed supply role reversal, and FVG imbalance; not a scalar or exit variant of prior engines.',
        'symbols_scanned': scanned, 'raw_seed_count': len(rows), 'seed_count': len(seeds),
        'yearly_seed_count': dict(sorted(yearly.items())), 'rejection_counts': dict(rejects),
        'semantic_order_failures': sum(not row['semantic_order_valid'] for row in seeds),
        'duplicate_symbol_entry': len(seeds) - len(set((row['symbol'], row['eligible_entry_date']) for row in seeds)),
        'support_gate_pass': support,
        'invariants': {'no_entries_created': True, 'no_outcome_fields': all(row['no_outcome_fields'] for row in seeds),
                       'all_nontradable': all(not row['tradable'] and not row['buy_enabled'] for row in seeds)},
        'decision': 'UNICORN_SEMANTIC_SEEDS_READY__INDEPENDENT_ORACLE_NEXT' if support else 'UNICORN_SUPPORT_GATE_FAIL__NO_REPLAY',
        'artifacts': {'out_dir': str(OUT), 'seeds': str(seed_file), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v452_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__':
    main()
