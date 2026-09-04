#!/usr/bin/env python3
"""V419 independent no-outcome integrity audit for V416 -> V417.

Success means every V417 row can be independently traced to a V416 strict
semantic lifecycle and enters exactly at the following session's open.
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
V416 = AUD / 'v416_strict_semantic_combination_rebuild_latest.json'
V417 = AUD / 'v417_strict_semantic_frozen_t1_replay_latest.json'
OUT = AUD / f'v419_strict_semantic_replay_integrity_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v419_strict_semantic_replay_integrity_latest.json'
FORBIDDEN = ('pnl', 'exit', 'won', 'mfe', 'mae', 'tp', 'sl', 'rr', 'mark')


def f(x: object) -> float:
    try:
        value = float(x)
        return value if math.isfinite(value) else 0.0
    except (TypeError, ValueError):
        return 0.0


def day(bar: dict) -> str:
    return ''.join(c for c in str(bar.get('t') or bar.get('date') or '') if c.isdigit())[:8]


def load(symbol: str) -> list[dict]:
    path = KDIR / f"{symbol.replace('.', '_')}_daily_750.json"
    try:
        bars = json.loads(path.read_text())
    except Exception:
        return []
    return sorted([b for b in bars if day(b) and f(b.get('o')) > 0], key=day)


def key(row: dict) -> tuple[str, str, str]:
    return row['symbol'], row['combo_key'], row['takeover_date']


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads(V416.read_text())
    replay = json.loads(V417.read_text())
    with Path(source['artifacts']['rows']).open(newline='', encoding='utf-8') as handle:
        seeds = list(csv.DictReader(handle))
    with Path(replay['artifacts']['rows']).open(newline='', encoding='utf-8') as handle:
        replay_rows = list(csv.DictReader(handle))

    forbidden_fields = [name for name in (seeds[0].keys() if seeds else []) if any(x in name.lower() for x in FORBIDDEN)]
    takeover_seeds = [row for row in seeds if row['lifecycle_state'] == 'TAKEOVER_CONFIRMED']
    cache: dict[str, list[dict]] = {}
    failures, checks = Counter(), Counter()

    # Audit exact chronology on every source seed.  This avoids collapsing distinct
    # same-symbol/same-day events into one dictionary key.
    for seed in takeover_seeds:
        checks['takeover_seeds'] += 1
        symbol = seed['symbol']
        if symbol not in cache:
            cache[symbol] = load(symbol)
        bars = cache[symbol]
        dates = {day(bar): i for i, bar in enumerate(bars)}
        if seed['takeover_date'] not in dates:
            failures['SEED_TAKEOVER_DATE_MISSING_FROM_RAW'] += 1
            continue
        start = int(seed['strict_lifecycle_start_idx'])
        if start != max(int(seed['event_idx']), int(seed['poi_idx'])):
            failures['START_NOT_EQUAL_TO_LAST_PREREQUISITE_BAR'] += 1
        if int(seed['touch_idx']) <= start:
            failures['TOUCH_NOT_STRICTLY_AFTER_PREREQUISITES'] += 1
        if int(seed['reclaim_idx']) <= int(seed['touch_idx']):
            failures['RECLAIM_NOT_AFTER_TOUCH'] += 1
        if dates[seed['takeover_date']] <= int(seed['reclaim_idx']):
            failures['TAKEOVER_NOT_AFTER_RECLAIM'] += 1
        if seed['combo_key'].startswith('R') and int(seed['sweep_idx']) >= int(seed['event_idx']):
            failures['SWEEP_NOT_BEFORE_REVERSAL_EVENT'] += 1
        checks['chronology_verified_seeds'] += 1

    # Verify every materialized replay row uses the raw next-session open.  Matching
    # is intentionally by its visible replay identity because V417 stores no internal
    # event id; multiplicities are checked separately below.
    for row in replay_rows:
        checks['replay_rows'] += 1
        symbol = row['symbol']
        if symbol not in cache:
            cache[symbol] = load(symbol)
        bars = cache[symbol]
        dates = {day(bar): i for i, bar in enumerate(bars)}
        takeover_i = dates.get(row['takeover_date'])
        if takeover_i is None or takeover_i + 1 >= len(bars):
            failures['REPLAY_TAKEOVER_OR_T1_BAR_MISSING'] += 1
            continue
        entry_i = takeover_i + 1
        if day(bars[entry_i]) != row['entry_date']:
            failures['ENTRY_DATE_NOT_NEXT_SESSION'] += 1
        if abs(f(bars[entry_i].get('o')) - f(row['entry_price'])) > 1e-6:
            failures['ENTRY_PRICE_NOT_T1_OPEN'] += 1
        checks['t1_verified_rows'] += 1

    source_keys = Counter(key(row) for row in takeover_seeds)
    replay_keys = Counter(key(row) for row in replay_rows)
    skipped_keys = sum(max(0, source_keys[k] - replay_keys[k]) for k in source_keys)
    extra_replay_keys = sum(max(0, replay_keys[k] - source_keys[k]) for k in replay_keys)
    if skipped_keys != sum(replay.get('skipped', {}).values()):
        failures['SKIP_COUNT_DOES_NOT_MATCH_SOURCE_MINUS_REPLAY'] += 1
    if extra_replay_keys:
        failures['REPLAY_KEY_NOT_IN_SOURCE'] += extra_replay_keys

    result = {
        'version': 'V419_STRICT_SEMANTIC_REPLAY_INTEGRITY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'scope': 'Independent V416-to-V417 chronology and next-session-open audit only; no mark, PnL, exit, threshold, or parameter operation.',
        'fixed_success_criteria': {
            'strict_seed_fields_contain_no_outcome_or_exit_data': True,
            'each_replay_row_maps_to_one_takeover_confirmed_seed': True,
            'lifecycle_starts_after_all_prerequisites': True,
            'touch_then_reclaim_then_takeover_is_ordered': True,
            'entry_is_exact_following_session_open': True,
            't1_violations': 0,
        },
        'input_counts': {
            'v416_rows': len(seeds),
            'v416_takeover_seeds': len(takeover_seeds),
            'v417_replay_rows': len(replay_rows),
            'source_minus_replay_skips': skipped_keys,
            'replay_without_source': extra_replay_keys,
        },
        'forbidden_input_fields': forbidden_fields,
        'checks': dict(checks),
        'failures': dict(failures),
        'pass': not forbidden_fields and not failures and checks['chronology_verified_seeds'] == len(takeover_seeds) and checks['t1_verified_rows'] == len(replay_rows),
        'decision': ('INTEGRITY_PASS__V417_STRICT_SEMANTIC_RESULTS_ARE_CAUSAL_AND_T1_ALIGNED'
                     if not forbidden_fields and not failures and checks['chronology_verified_seeds'] == len(takeover_seeds) and checks['t1_verified_rows'] == len(replay_rows)
                     else 'INTEGRITY_FAIL__V417_ECONOMIC_CONCLUSION_MUST_NOT_BE_USED'),
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST)},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v419_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
