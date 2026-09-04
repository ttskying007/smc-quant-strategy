#!/usr/bin/env python3
"""V415 no-write structure-flip POI lifecycle.

Tests a new pure-structure POI that was not covered by V409: the candle zone
of the confirmed swing high broken by bullish CHOCH/BOS becomes resistance-
to-support. No entries, exits, PnL, filters, or outcome fields are created.
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
OUT = AUD / f'v415_structure_flip_poi_lifecycle_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v415_structure_flip_poi_lifecycle_latest.json'

spec = importlib.util.spec_from_file_location('v27', ROOT / 'scripts/v25/smc_core_v27.py')
v27 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v27)


def f(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else 0.0
    except (TypeError, ValueError):
        return 0.0


def day(bar):
    return ''.join(c for c in str(bar.get('t') or bar.get('date') or '') if c.isdigit())[:8]


def load(path):
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return []
    bars = [b for b in raw if day(b) and all(f(b.get(k)) > 0 for k in ('o', 'h', 'l', 'c'))]
    return sorted(bars, key=day)


def symbol(path):
    parts = path.name.replace('_daily_750.json', '').split('_')
    return f'{parts[0]}.{parts[1]}' if len(parts) == 2 else path.stem


def lifecycle(bars, event_idx, zone_low, zone_high):
    touch = reclaim = None
    for idx in range(event_idx + 1, min(len(bars), event_idx + 31)):
        low, close = f(bars[idx].get('l')), f(bars[idx].get('c'))
        if close < zone_low:
            return 'CANCEL_ZONE_INVALIDATED', idx, touch, reclaim
        if touch is None:
            if low <= zone_high:
                touch = idx
            continue
        if reclaim is None:
            if close > zone_high:
                reclaim = idx
            continue
        if idx > reclaim and close > zone_high and low >= zone_low:
            return 'TAKEOVER_CONFIRMED', idx, touch, reclaim
    observed = event_idx + 30 < len(bars)
    if touch is None:
        return ('EXPIRE_NO_TOUCH_30B' if observed else 'WAIT_TOUCH_UNOBSERVED'), None, None, None
    if reclaim is None:
        return ('EXPIRE_NO_RECLAIM_30B' if observed else 'WAIT_RECLAIM_UNOBSERVED'), None, touch, None
    return ('EXPIRE_NO_HOLD_30B' if observed else 'WAIT_HOLD_UNOBSERVED'), None, touch, reclaim


def make_row(sym, bars, combo, event, sweep_idx):
    event_idx = int(event['index'])
    pivot_idx = int(event['broken_swing_idx'])
    if not (0 <= pivot_idx < event_idx < len(bars)):
        return None
    pivot = bars[pivot_idx]
    # Source-native resistance zone: body top through wick high of the broken,
    # already-confirmed swing-high candle. No ATR/percent width is fitted.
    zone_low = max(f(pivot.get('o')), f(pivot.get('c')))
    zone_high = f(pivot.get('h'))
    if zone_low <= 0 or zone_high < zone_low:
        return None
    state, state_idx, touch_idx, reclaim_idx = lifecycle(bars, event_idx, zone_low, zone_high)

    def date_at(idx):
        return day(bars[idx]) if idx is not None else ''

    return {
        'symbol': sym,
        'combo_key': combo,
        'lifecycle_state': state,
        'sweep_idx': '' if sweep_idx is None else sweep_idx,
        'sweep_date': date_at(sweep_idx),
        'event_type': event.get('type', ''),
        'event_idx': event_idx,
        'event_date': date_at(event_idx),
        'pivot_idx': pivot_idx,
        'pivot_confirm_idx': int(event['confirm_visible_at']),
        'pivot_date': date_at(pivot_idx),
        'zone_low': round(zone_low, 6),
        'zone_high': round(zone_high, 6),
        'touch_idx': '' if touch_idx is None else touch_idx,
        'touch_date': date_at(touch_idx),
        'reclaim_idx': '' if reclaim_idx is None else reclaim_idx,
        'reclaim_date': date_at(reclaim_idx),
        'takeover_idx': '' if state_idx is None else state_idx,
        'takeover_date': date_at(state_idx) if state == 'TAKEOVER_CONFIRMED' else '',
        'sweep_to_event_bars': '' if sweep_idx is None else event_idx - sweep_idx,
        'event_to_touch_bars': '' if touch_idx is None else touch_idx - event_idx,
        'touch_to_reclaim_bars': '' if touch_idx is None or reclaim_idx is None else reclaim_idx - touch_idx,
        'reclaim_to_takeover_bars': '' if reclaim_idx is None or state_idx is None else state_idx - reclaim_idx,
        'semantic_contract': 'confirmed swing-high -> bull structure break -> broken resistance candle-zone retest -> reclaim -> hold',
        'tradable': 'false',
        'buy_enabled': 'false',
        'outcome_fields_present': 'false',
    }


def median_int(rows, field):
    values = sorted(int(r[field]) for r in rows if str(r.get(field, '')).strip())
    return values[len(values) // 2] if values else None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    counts, rows = Counter(), []
    for path in sorted(KDIR.glob('*_daily_750.json')):
        bars = load(path)
        if len(bars) < 60:
            continue
        counts['symbols_scanned'] += 1
        swings = v27.confirmed_swings([dict(x) for x in bars])
        structure = v27.structure_signals([dict(x) for x in bars], swings)
        sweeps = [x for x in v27.sweep_signals([dict(x) for x in bars], swings) if x.get('direction') == 'bull']
        sym = symbol(path)
        seen = set()
        for event in structure:
            if event.get('direction') != 'bull':
                continue
            event_idx = int(event['index'])
            prior = [x for x in sweeps if 1 <= event_idx - int(x['index']) <= 20]
            combos = []
            if event.get('type') in ('CHOCH', 'MSS') and prior:
                combos.append(('R3_SSL_CHOCH_STRUCTURE_FLIP', int(max(prior, key=lambda x: int(x['index']))['index'])))
            if event.get('type') == 'BOS':
                combos.append(('C2_BOS_STRUCTURE_FLIP', None))
            for combo, sweep_idx in combos:
                key = (sym, combo, int(event['broken_swing_idx']))
                if key in seen:
                    continue
                row = make_row(sym, bars, combo, event, sweep_idx)
                if row is None:
                    continue
                seen.add(key)
                rows.append(row)
                counts[combo] += 1
                counts[row['lifecycle_state']] += 1

    fields = list(rows[0]) if rows else ['symbol', 'combo_key']
    rows_path = OUT / 'v415_lifecycle_rows.csv'
    with rows_path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    summary = {}
    for combo in ('R3_SSL_CHOCH_STRUCTURE_FLIP', 'C2_BOS_STRUCTURE_FLIP'):
        subset = [r for r in rows if r['combo_key'] == combo]
        stages = Counter(r['lifecycle_state'] for r in subset)
        summary[combo] = {
            'candidates': len(subset),
            'lifecycle': dict(stages),
            'takeover_rate_pct': round(stages['TAKEOVER_CONFIRMED'] / len(subset) * 100, 2) if subset else 0,
            'median_sweep_to_event_bars': median_int(subset, 'sweep_to_event_bars'),
            'median_event_to_touch_bars': median_int(subset, 'event_to_touch_bars'),
            'median_touch_to_reclaim_bars': median_int(subset, 'touch_to_reclaim_bars'),
            'median_reclaim_to_takeover_bars': median_int(subset, 'reclaim_to_takeover_bars'),
        }

    report = {
        'version': 'V415_STRUCTURE_FLIP_POI_LIFECYCLE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'scope': 'new pure-structure POI lifecycle; no entry, exit, PnL, or promotion',
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'contracts': {
            'R3_SSL_CHOCH_STRUCTURE_FLIP': 'confirmed SSL sweep -> bull CHOCH/MSS within 20 bars -> retest broken swing-high candle resistance zone -> reclaim -> hold',
            'C2_BOS_STRUCTURE_FLIP': 'confirmed bull BOS -> retest broken swing-high candle resistance zone -> reclaim -> hold',
            'poi': 'body-top to wick-high of the broken confirmed swing-high candle',
        },
        'stage_counts': dict(counts),
        'combination_summary': summary,
        'invariants': {
            'all_rows_non_tradable': all(r['tradable'] == 'false' for r in rows),
            'no_outcome_fields': all(r['outcome_fields_present'] == 'false' for r in rows),
            'pivot_confirmed_before_event': all(int(r['pivot_confirm_idx']) <= int(r['event_idx']) for r in rows),
            'causal_order_for_takeovers': all(int(r['event_idx']) < int(r['touch_idx']) <= int(r['reclaim_idx']) < int(r['takeover_idx']) for r in rows if r['lifecycle_state'] == 'TAKEOVER_CONFIRMED'),
        },
        'decision': 'STRUCTURE_FLIP_LIFECYCLE_READY__RUN_ONE_FROZEN_T1_STRUCTURAL_REPLAY',
        'artifacts': {'out_dir': str(OUT), 'rows': str(rows_path), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v415_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
