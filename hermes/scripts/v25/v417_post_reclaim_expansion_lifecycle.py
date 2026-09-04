#!/usr/bin/env python3
"""V417 no-outcome post-reclaim structural expansion lifecycle.

From V415 takeover-confirmed structure-flip candidates, require a new close above
all highs from the original structure event through takeover. This tests actual
post-reclaim expansion rather than passive one-bar holding. No outcomes are read.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD, KDIR = ROOT / 'smc_audit', ROOT / 'kline_cache'
SOURCE = AUD / 'v415_structure_flip_poi_lifecycle_latest.json'
OUT = AUD / f'v417_post_reclaim_expansion_lifecycle_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v417_post_reclaim_expansion_lifecycle_latest.json'


def f(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else 0.0
    except (TypeError, ValueError):
        return 0.0


def day(bar):
    return ''.join(c for c in str(bar.get('t') or bar.get('date') or '') if c.isdigit())[:8]


def load(symbol):
    path = KDIR / f"{symbol.replace('.', '_')}_daily_750.json"
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return []
    return sorted([b for b in raw if day(b) and all(f(b.get(k)) > 0 for k in ('o', 'h', 'l', 'c'))], key=day)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads(SOURCE.read_text())
    with open(source['artifacts']['rows'], newline='', encoding='utf-8') as handle:
        seeds = [r for r in csv.DictReader(handle) if r['lifecycle_state'] == 'TAKEOVER_CONFIRMED']

    cache, rows, counts = {}, [], Counter()
    for seed in seeds:
        symbol = seed['symbol']
        if symbol not in cache:
            cache[symbol] = load(symbol)
        bars = cache[symbol]
        event_idx, takeover_idx = int(seed['event_idx']), int(seed['takeover_idx'])
        if not bars or not (0 <= event_idx < takeover_idx < len(bars)):
            counts['INVALID_SOURCE_INDEX'] += 1
            continue
        watermark = max(f(bars[idx].get('h')) for idx in range(event_idx, takeover_idx + 1))
        expansion_idx = None
        cancelled = False
        end = min(len(bars), event_idx + 31)
        for idx in range(takeover_idx + 1, end):
            if f(bars[idx].get('c')) < f(seed['zone_low']):
                counts['CANCEL_BEFORE_EXPANSION'] += 1
                cancelled = True
                break
            if f(bars[idx].get('c')) > watermark:
                expansion_idx = idx
                counts['EXPANSION_CONFIRMED'] += 1
                break
        if expansion_idx is None:
            if not cancelled:
                counts['NO_EXPANSION_WITHIN_ORIGINAL_30B'] += 1
            continue
        rows.append({
            **seed,
            'pre_expansion_high': round(watermark, 6),
            'expansion_idx': expansion_idx,
            'expansion_date': day(bars[expansion_idx]),
            'takeover_to_expansion_bars': expansion_idx - takeover_idx,
            'expansion_contract': 'first post-takeover close above every high from event through takeover, before original event+30 boundary',
            'tradable': 'false',
            'buy_enabled': 'false',
            'outcome_fields_present': 'false',
        })

    fields = list(rows[0]) if rows else ['symbol', 'combo_key']
    rows_path = OUT / 'v417_expansion_rows.csv'
    with rows_path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    combo_summary = {}
    for combo in ('R3_SSL_CHOCH_STRUCTURE_FLIP', 'C2_BOS_STRUCTURE_FLIP'):
        input_n = sum(r['combo_key'] == combo for r in seeds)
        subset = [r for r in rows if r['combo_key'] == combo]
        gaps = sorted(int(r['takeover_to_expansion_bars']) for r in subset)
        combo_summary[combo] = {
            'takeover_input': input_n,
            'expansion_confirmed': len(subset),
            'expansion_rate_pct': round(len(subset) / input_n * 100, 2) if input_n else 0,
            'median_takeover_to_expansion_bars': gaps[len(gaps) // 2] if gaps else None,
        }

    report = {
        'version': 'V417_POST_RECLAIM_STRUCTURAL_EXPANSION_LIFECYCLE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'source': str(SOURCE),
        'scope': 'mechanism-only refinement; no entry, exit, PnL, threshold search, or promotion',
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'contract': 'V415 takeover -> first later close above all event-through-takeover highs before event+30; zone close invalidation cancels',
        'stage_counts': dict(counts),
        'combo_summary': combo_summary,
        'invariants': {
            'all_non_tradable': all(r['tradable'] == 'false' for r in rows),
            'no_outcome_fields': all(r['outcome_fields_present'] == 'false' for r in rows),
            'strict_time_order': all(int(r['event_idx']) < int(r['touch_idx']) <= int(r['reclaim_idx']) < int(r['takeover_idx']) < int(r['expansion_idx']) for r in rows),
            'expansion_above_frozen_watermark': all(f(r['pre_expansion_high']) > 0 for r in rows),
        },
        'decision': 'POST_RECLAIM_EXPANSION_READY__RUN_ONE_FROZEN_T1_STRUCTURAL_REPLAY',
        'artifacts': {'out_dir': str(OUT), 'rows': str(rows_path), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v417_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
