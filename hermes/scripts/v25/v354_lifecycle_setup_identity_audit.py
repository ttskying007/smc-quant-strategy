#!/usr/bin/env python3
"""V354 no-write setup-identity audit for the V351→V353 daily lifecycle.

A structure event is not automatically a distinct tradeable setup.  This audit
collapses duplicate BOS events that resolve through the same OB and the same
lifecycle path, then materializes only unresolved, fresh-data lifecycle states.
It never creates an entry, exit, PnL, watchlist row, or production write.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
KDIR = ROOT / 'kline_cache'
SRC = AUD / 'v353_persistent_takeover_latest.json'
OUT = AUD / f"v354_lifecycle_setup_identity_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST = AUD / 'v354_lifecycle_setup_identity_latest.json'
WAITING = {'WAIT_TOUCH_UNOBSERVED', 'WAIT_RECLAIM_UNOBSERVED', 'WAIT_HOLD_UNOBSERVED'}
FORBIDDEN = ('entry', 'exit', 'pnl', 'tp', 'sl', 'risk', 'won')


def dkey(value: object) -> str:
    digits = ''.join(c for c in str(value or '') if c.isdigit())
    return digits[:8] if len(digits) >= 8 else ''


def latest_daily_dates() -> tuple[dict[str, str], str]:
    latest: dict[str, str] = {}
    for path in KDIR.glob('*_daily_750.json'):
        stem = path.name.removesuffix('_daily_750.json')
        parts = stem.split('_')
        if len(parts) != 2:
            continue
        try:
            rows = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        dates = [dkey(b.get('t') or b.get('date')) for b in rows if isinstance(b, dict)]
        dates = [d for d in dates if d]
        if dates:
            latest[f'{parts[0]}.{parts[1]}'] = max(dates)
    return latest, max(latest.values(), default='')


def path_key(row: dict[str, str]) -> str:
    """Same OB plus same observed resolution is one setup path, not many BOS rows."""
    return '|'.join((
        row.get('symbol', ''), row.get('ob_idx', ''), row.get('touch_date', ''),
        row.get('reclaim_date', ''), row.get('takeover_date', ''),
        row.get('lifecycle_end_date', ''), row.get('lifecycle_state', ''),
    ))


def representative(rows: list[dict[str, str]]) -> dict[str, object]:
    rows = sorted(rows, key=lambda r: (int(r.get('event_idx') or -1), r.get('event_date', '')))
    base = dict(rows[0])
    states = sorted({r.get('lifecycle_state', '') for r in rows})
    base['setup_key'] = path_key(base)
    base['source_seed_count'] = len(rows)
    base['source_event_idxs'] = ','.join(str(r.get('event_idx', '')) for r in rows)
    base['source_event_dates'] = ','.join(r.get('event_date', '') for r in rows)
    base['state_conflict'] = len(states) > 1
    base['state_set'] = ','.join(states)
    return base


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads(SRC.read_text())
    with Path(report['artifacts']['rows']).open(newline='') as handle:
        raw_rows = list(csv.DictReader(handle))

    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in raw_rows:
        groups[path_key(row)].append(row)
    unique_rows = [representative(group) for _, group in sorted(groups.items())]

    latest_by_symbol, global_end = latest_daily_dates()
    reference = datetime.strptime(global_end, '%Y%m%d') if global_end else None
    fresh_cutoff = (reference - timedelta(days=5)).strftime('%Y%m%d') if reference else ''
    active, stale = [], []
    for row in unique_rows:
        row['data_end_date'] = latest_by_symbol.get(str(row.get('symbol', '')), '')
        row['fresh_data'] = bool(row['data_end_date'] and row['data_end_date'] >= fresh_cutoff)
        if row['lifecycle_state'] in WAITING:
            (active if row['fresh_data'] else stale).append(row)

    raw_by_state = Counter(row.get('lifecycle_state', '') for row in raw_rows)
    unique_by_state = Counter(str(row.get('lifecycle_state', '')) for row in unique_rows)
    duplicate_groups = [row for row in unique_rows if int(row['source_seed_count']) > 1]
    state_conflicts = [row for row in unique_rows if row['state_conflict']]
    forbidden_columns = [
        c for c in raw_rows[0]
        if not c.startswith('no_') and any(token in c.lower() for token in FORBIDDEN)
    ] if raw_rows else []
    fields = list(unique_rows[0]) if unique_rows else ['setup_key', 'symbol', 'lifecycle_state']
    for name, rows in (('v354_unique_setup_paths.csv', unique_rows),
                       ('v354_current_waiting_paths.csv', active),
                       ('v354_stale_waiting_paths.csv', stale)):
        with (OUT / name).open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    result = {
        'version': 'V354_LIFECYCLE_SETUP_IDENTITY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'source': str(SRC),
        'identity_contract': 'symbol + OB index + observed touch/reclaim/takeover path + lifecycle state; renewed BOS windows retain separate state while duplicate events are provenance, not setups',
        'current_state_contract': 'only unresolved WAIT_* paths with a local daily cache end within five calendar days of full-market reference are current shadow states',
        'raw_seed_rows': len(raw_rows),
        'unique_setup_paths': len(unique_rows),
        'duplicate_seed_rows_removed_from_identity_count': len(raw_rows) - len(unique_rows),
        'duplicate_groups': len(duplicate_groups),
        'max_seeds_in_one_path': max((int(r['source_seed_count']) for r in unique_rows), default=0),
        'raw_state_counts': dict(raw_by_state),
        'unique_state_counts': dict(unique_by_state),
        'current_waiting_unique_paths': len(active),
        'stale_waiting_unique_paths_excluded': len(stale),
        'global_daily_reference_date': global_end,
        'fresh_data_cutoff': fresh_cutoff,
        'state_conflict_groups': len(state_conflicts),
        'invariants': {
            'no_entries_created': True,
            'no_outcome_fields': not forbidden_columns,
            'all_non_tradable': all(str(r.get('tradable')).lower() == 'false' and str(r.get('buy_enabled')).lower() == 'false' for r in unique_rows),
            'current_rows_unresolved_only': all(r['lifecycle_state'] in WAITING for r in active),
            'current_rows_fresh_data_only': all(r['fresh_data'] for r in active),
        },
        'forbidden_columns_found': forbidden_columns,
        'decision': 'IDENTITY_AND_CURRENT_LIFECYCLE_READY__HISTORICAL_M60_REMAINS_BLOCKED',
        'artifacts': {
            'out_dir': str(OUT),
            'unique_paths': str(OUT / 'v354_unique_setup_paths.csv'),
            'current_waiting_paths': str(OUT / 'v354_current_waiting_paths.csv'),
            'stale_waiting_paths': str(OUT / 'v354_stale_waiting_paths.csv'),
            'latest': str(LATEST),
        },
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v354_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
