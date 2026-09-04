#!/usr/bin/env python3
"""V415 no-write POI lifecycle-integrity audit of V409 causal combinations.

It reads only V409 signal/lifecycle fields and raw daily bars. It never reads or
creates entries, exits, PnL, marks, trade candidates, or production outputs.

The audit enforces the literal V409 contract:
- a lifecycle cannot start before every prerequisite exists;
- a pre-event OB touch cannot be called a post-confirmation first retest;
- a FVG's source/creation bar cannot be called its post-creation retest.
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
SRC = AUD / 'v409_causal_signal_combination_latest.json'
OUT = AUD / f'v415_poi_lifecycle_integrity_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v415_poi_lifecycle_integrity_latest.json'
COMBOS = ('R1_SSL_CHOCH_DEMAND_OB', 'R2_SSL_CHOCH_BULL_FVG', 'C1_BOS_DEMAND_OB')


def f(value: object) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else 0.0
    except (TypeError, ValueError):
        return 0.0


def day(bar: dict) -> str:
    return ''.join(c for c in str(bar.get('t') or bar.get('date') or '') if c.isdigit())[:8]


def load_bars(symbol: str, cache: dict[str, list[dict]]) -> list[dict]:
    if symbol not in cache:
        path = KDIR / f"{symbol.replace('.', '_')}_daily_750.json"
        try:
            raw = json.loads(path.read_text())
        except Exception:
            raw = []
        cache[symbol] = sorted(
            [bar for bar in raw if day(bar)], key=day,
        )
    return cache[symbol]


def lifecycle(bars: list[dict], start_idx: int, low: float, high: float) -> tuple[str, int | None, int | None, int | None]:
    """First fresh touch/reclaim/hold strictly after all prerequisites exist."""
    touch = reclaim = None
    end = min(len(bars), start_idx + 31)
    for idx in range(start_idx + 1, end):
        bar = bars[idx]
        if f(bar.get('c')) < low:
            return 'CANCEL_ZONE_INVALIDATED', idx, touch, reclaim
        if touch is None:
            if f(bar.get('l')) <= high:
                touch = idx
            continue
        if reclaim is None:
            if f(bar.get('c')) > high:
                reclaim = idx
            continue
        if idx > reclaim and f(bar.get('c')) > high and f(bar.get('l')) >= low:
            return 'TAKEOVER_CONFIRMED', idx, touch, reclaim
    observed = start_idx + 30 < len(bars)
    if touch is None:
        return ('EXPIRE_NO_TOUCH_30B' if observed else 'WAIT_TOUCH_UNOBSERVED'), None, None, None
    if reclaim is None:
        return ('EXPIRE_NO_RECLAIM_30B' if observed else 'WAIT_RECLAIM_UNOBSERVED'), None, touch, None
    return ('EXPIRE_NO_HOLD_30B' if observed else 'WAIT_HOLD_UNOBSERVED'), None, touch, reclaim


def source_state(row: dict, bars: list[dict]) -> str:
    """Classify whether V409's stated post-confirmation lifecycle was legal."""
    poi, event = int(row['poi_idx']), int(row['event_idx'])
    low, high = f(row['zone_low']), f(row['zone_high'])
    # A FVG does not exist until its third/source bar closes. V409 may have
    # begun its lifecycle on that creation bar when event_idx < poi_idx.
    if row['poi_type'] == 'BULL_FVG' and event < poi:
        return 'SOURCE_BAR_LIFECYCLE_ARTIFACT'
    # For a backward-anchored OB, a wick into the zone before the event means
    # it is not a post-event FIRST retest. A close below invalidates it first.
    if row['poi_type'] == 'DEMAND_OB':
        between = bars[poi + 1:event]
        if any(f(bar.get('c')) < low for bar in between):
            return 'PRE_EVENT_INVALIDATED'
        if any(f(bar.get('l')) <= high for bar in between):
            return 'PRE_EVENT_MITIGATED'
    return 'LIFECYCLE_START_LEGAL'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads(SRC.read_text())
    with Path(source['artifacts']['rows']).open() as handle:
        rows = list(csv.DictReader(handle))
    cache: dict[str, list[dict]] = {}
    summary: dict[str, Counter] = defaultdict(Counter)
    corrected_all: dict[str, Counter] = defaultdict(Counter)
    corrected_eligible: dict[str, Counter] = defaultdict(Counter)
    detail_rows: list[dict] = []

    for row in rows:
        combo = row['combo_key']
        if combo not in COMBOS:
            continue
        bars = load_bars(row['symbol'], cache)
        if not bars:
            summary[combo]['MISSING_KLINE'] += 1
            continue
        state = source_state(row, bars)
        summary[combo]['rows'] += 1
        summary[combo][state] += 1
        legal_start = max(int(row['event_idx']), int(row['poi_idx']))
        fixed_state, fixed_idx, touch_idx, reclaim_idx = lifecycle(
            bars, legal_start, f(row['zone_low']), f(row['zone_high'])
        )
        corrected_all[combo][fixed_state] += 1
        # A later-created FVG is legal if its lifecycle starts after creation;
        # the old V409 label was wrong, not the causal sequence itself.
        eligible = state in ('LIFECYCLE_START_LEGAL', 'SOURCE_BAR_LIFECYCLE_ARTIFACT')
        if eligible:
            corrected_eligible[combo][fixed_state] += 1
        detail_rows.append({
            'symbol': row['symbol'], 'combo_key': combo,
            'poi_idx': row['poi_idx'], 'event_idx': row['event_idx'],
            'poi_type': row['poi_type'], 'source_state': state,
            'strict_semantic_eligible': str(eligible).lower(),
            'legal_lifecycle_start_idx': legal_start,
            'v409_lifecycle_state': row['lifecycle_state'],
            'corrected_lifecycle_state': fixed_state,
            'corrected_state_idx': '' if fixed_idx is None else fixed_idx,
            'corrected_takeover_date': (
                day(bars[fixed_idx]) if fixed_state == 'TAKEOVER_CONFIRMED' and fixed_idx is not None else ''
            ),
            'corrected_touch_idx': '' if touch_idx is None else touch_idx,
            'corrected_reclaim_idx': '' if reclaim_idx is None else reclaim_idx,
            'tradable': 'false', 'buy_enabled': 'false',
            'outcome_fields_present': 'false',
        })

    report_combos = {}
    for combo in COMBOS:
        total = summary[combo]['rows']
        literal_legal = summary[combo]['LIFECYCLE_START_LEGAL']
        strict_eligible = literal_legal + summary[combo]['SOURCE_BAR_LIFECYCLE_ARTIFACT']
        report_combos[combo] = {
            'rows': total,
            'source_integrity': dict(summary[combo]),
            'strict_semantic_eligible_rows': strict_eligible,
            'strict_semantic_eligible_pct': round(strict_eligible / total * 100, 4) if total else 0.0,
            'corrected_post_prerequisite_lifecycle_all_rows': dict(corrected_all[combo]),
            'corrected_post_prerequisite_lifecycle_eligible_only': dict(corrected_eligible[combo]),
        }

    fields = list(detail_rows[0]) if detail_rows else ['symbol', 'combo_key']
    with (OUT / 'v415_rows.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(detail_rows)
    report = {
        'version': 'V415_POI_LIFECYCLE_INTEGRITY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'scope': 'semantic integrity only; no entries, exits, marks, PnL, or promotion',
        'input_contract': 'V409 three causal SMC combinations',
        'audit_contract': {
            'lifecycle_start': 'strictly after max(event_idx, poi_idx)',
            'ob_pre_event_rule': 'a pre-event wick touch is not a post-confirmation first retest; close below zone_low invalidates first',
            'fvg_source_bar_rule': 'the FVG creation/source bar is not a post-creation retest',
        },
        'combination_summary': report_combos,
        'invariants': {
            'all_rows_non_tradable': all(row['tradable'] == 'false' for row in detail_rows),
            'no_outcome_fields': all(row['outcome_fields_present'] == 'false' for row in detail_rows),
            'no_trade_fields_created': True,
        },
        'decision': 'V409_LIFECYCLE_LABELS_NOT_SEMANTICALLY_CLEAN__DO_NOT_REPLAY_OR_PROMOTE_UNTIL_GENERATOR_CONTRACT_IS_REBUILT',
        'artifacts': {'out_dir': str(OUT), 'rows': str(OUT / 'v415_rows.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v415_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
