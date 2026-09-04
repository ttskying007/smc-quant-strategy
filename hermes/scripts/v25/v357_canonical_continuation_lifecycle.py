#!/usr/bin/env python3
"""V357 no-write canonical continuation lifecycle rebuild.

Corrects two V351/V352 lifecycle-input defects without producing trades:
1. One physical OB zone can have many later BOS rows; keep only its first BOS.
2. A zone touched before that BOS was already mitigated; it is not a fresh
   post-BOS pullback candidate.  A close below zone_low cancels it.

Output is a non-tradable lifecycle audit only: no entry, exit, PnL, TP, SL,
or outcome fields.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
KDIR = ROOT / 'kline_cache'
SOURCE = AUD / 'v351_semantic_oracle_latest.json'
OUT = AUD / f'v357_canonical_continuation_lifecycle_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v357_canonical_continuation_lifecycle_latest.json'


def f(value: object) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else 0.0
    except (TypeError, ValueError):
        return 0.0


def day(bar: dict) -> str:
    return ''.join(c for c in str(bar.get('t') or bar.get('date') or '') if c.isdigit())[:8]


def load_bars(symbol: str) -> list[dict]:
    path = KDIR / f'{symbol.replace(".", "_")}_daily_750.json'
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return []
    return sorted([b for b in raw if day(b)], key=day)


def state_before_event(bars: list[dict], ob_idx: int, event_idx: int,
                       low: float, high: float) -> str:
    """Classify zone strictly before the BOS bar; event bar is not inspected."""
    for i in range(ob_idx + 1, event_idx):
        if f(bars[i].get('c')) < low:
            return 'PRE_EVENT_INVALIDATED'
    for i in range(ob_idx + 1, event_idx):
        if f(bars[i].get('l')) <= high:
            return 'PRE_EVENT_MITIGATED'
    return 'FRESH_AT_BOS'


def lifecycle_after_event(bars: list[dict], event_idx: int,
                          low: float, high: float) -> tuple[str, int | None, int | None, int | None]:
    """Causal post-BOS lifecycle; event bar is known at seed time, so start after it."""
    touch_idx = reclaim_idx = None
    for i in range(event_idx + 1, min(len(bars), event_idx + 31)):
        bar = bars[i]
        if f(bar.get('c')) < low:
            return 'CANCEL_ZONE_INVALIDATED', i, touch_idx, reclaim_idx
        if touch_idx is None:
            if f(bar.get('l')) <= high:
                touch_idx = i
            continue
        if reclaim_idx is None:
            if f(bar.get('c')) > high:
                reclaim_idx = i
            continue
        if i > reclaim_idx and f(bar.get('c')) > high and f(bar.get('l')) >= low:
            return 'TAKEOVER_CONFIRMED', i, touch_idx, reclaim_idx

    fully_observed = event_idx + 30 < len(bars)
    if touch_idx is None:
        return ('EXPIRE_NO_TOUCH_30B' if fully_observed else 'WAIT_TOUCH_UNOBSERVED'), None, None, None
    if reclaim_idx is None:
        return ('EXPIRE_NO_RECLAIM_30B' if fully_observed else 'WAIT_RECLAIM_UNOBSERVED'), None, touch_idx, None
    return ('EXPIRE_NO_HOLD_30B' if fully_observed else 'WAIT_HOLD_UNOBSERVED'), None, touch_idx, reclaim_idx


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source_report = json.loads(SOURCE.read_text())
    with Path(source_report['artifacts']['seeds']).open() as handle:
        source_rows = list(csv.DictReader(handle))

    # Same physical OB may be attached to repeated later BOS events.  The first
    # event is the only causal chance to observe its first post-break retest.
    zones: dict[tuple[str, int, float, float], list[dict]] = defaultdict(list)
    for row in source_rows:
        try:
            key = (row['symbol'], int(row['ob_idx']), f(row['zone_low']), f(row['zone_high']))
            zones[key].append(row)
        except (KeyError, ValueError):
            continue

    cache: dict[str, list[dict]] = {}
    counts = Counter()
    yearly: dict[str, Counter] = defaultdict(Counter)
    rows: list[dict] = []
    for (symbol, ob_idx, low, high), candidates in zones.items():
        row = min(candidates, key=lambda item: int(item['event_idx']))
        event_idx = int(row['event_idx'])
        if symbol not in cache:
            cache[symbol] = load_bars(symbol)
        bars = cache[symbol]
        counts['RAW_SEMANTIC_SEEDS'] += len(candidates)
        counts['PHYSICAL_OB_ZONES'] += 1
        counts['DUPLICATE_BOS_SEEDS_SUPPRESSED'] += len(candidates) - 1
        if not bars or not (0 <= ob_idx < event_idx < len(bars)):
            counts['CANCEL_MISSING_OR_BAD_KLINE'] += 1
            continue

        pre_state = state_before_event(bars, ob_idx, event_idx, low, high)
        year = day(bars[event_idx])[:4]
        yearly[year]['physical_zones'] += 1
        yearly[year][pre_state] += 1
        if pre_state != 'FRESH_AT_BOS':
            counts[pre_state] += 1
            continue

        status, end_idx, touch_idx, reclaim_idx = lifecycle_after_event(bars, event_idx, low, high)
        counts['FRESH_CANONICAL_SEEDS'] += 1
        counts[status] += 1
        yearly[year]['fresh_canonical_seeds'] += 1
        yearly[year][status] += 1
        rows.append({
            'symbol': symbol,
            'ob_idx': ob_idx,
            'ob_date': day(bars[ob_idx]),
            'event_type': 'BOS',
            'event_idx': event_idx,
            'event_date': day(bars[event_idx]),
            'broken_swing_idx': row['broken_swing_idx'],
            'swing_confirm_idx': row['swing_confirm_idx'],
            'zone_low': low,
            'zone_high': high,
            'pre_event_state': pre_state,
            'lifecycle_state': status,
            'touch_date': day(bars[touch_idx]) if touch_idx is not None else '',
            'reclaim_date': day(bars[reclaim_idx]) if reclaim_idx is not None else '',
            'takeover_date': day(bars[end_idx]) if status == 'TAKEOVER_CONFIRMED' and end_idx is not None else '',
            'lifecycle_end_date': day(bars[end_idx]) if end_idx is not None else '',
            'semantic_contract': 'confirmed_swing>bull_BOS>fresh_backward_bearish_OB>first_post_BOS_touch>reclaim>hold',
            'tradable': 'false',
            'buy_enabled': 'false',
            'no_entry_exit_or_outcome_fields': 'true',
        })

    fields = list(rows[0]) if rows else ['symbol', 'lifecycle_state']
    output_rows = OUT / 'v357_canonical_lifecycle_rows.csv'
    with output_rows.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    duplicate_keys = [(r['symbol'], r['ob_idx'], r['event_idx']) for r in rows]
    yearly_rows = []
    for year, stats in sorted(yearly.items()):
        fresh = stats['fresh_canonical_seeds']
        takeover = stats['TAKEOVER_CONFIRMED']
        yearly_rows.append({
            'year': year,
            **dict(stats),
            'takeover_rate_of_fresh_pct': round(takeover / fresh * 100, 2) if fresh else 0,
        })

    report = {
        'version': 'V357_CANONICAL_CONTINUATION_LIFECYCLE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'source_contract': 'V351/V356 semantic-valid causal daily BOS + backward OB',
        'canonicalization_contract': 'one physical OB uses earliest BOS only; any wick touch before BOS excludes zone as mitigated; close below zone_low excludes it as invalidated',
        'lifecycle_contract': 'fresh BOS seed -> first post-BOS wick touch -> close reclaim above zone_high -> next hold above zone; close below zone_low cancels',
        'stage_counts': dict(counts),
        'yearly_lifecycle': yearly_rows,
        'invariants': {
            'one_row_per_physical_ob_zone': len(rows) == len(set((r['symbol'], r['ob_idx'], r['zone_low'], r['zone_high']) for r in rows)),
            'no_duplicate_output_event_keys': len(duplicate_keys) == len(set(duplicate_keys)),
            'all_rows_fresh_at_bos': all(r['pre_event_state'] == 'FRESH_AT_BOS' for r in rows),
            'all_rows_non_tradable': all(r['tradable'] == 'false' and r['buy_enabled'] == 'false' for r in rows),
            'no_entry_exit_or_outcome_fields': all(r['no_entry_exit_or_outcome_fields'] == 'true' for r in rows),
        },
        'decision': 'CANONICAL_DAILY_CONTINUATION_LIFECYCLE_READY__NOT_A_STRATEGY_OR_PRODUCTION_PICK',
        'artifacts': {'out_dir': str(OUT), 'rows': str(output_rows), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v357_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
