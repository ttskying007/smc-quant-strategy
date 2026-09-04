#!/usr/bin/env python3
"""V355 no-write operational-frontier audit for V354 current lifecycle paths.

V354 intentionally preserves renewed BOS windows as separate lifecycle provenance.
For a current scanner, however, one unresolved OB/zone must have one canonical
operational state. This audit never discards history: it writes a frontier view
(latest event for the same symbol + OB + zone) and a superseded-provenance view.
It does not create entries, exits, PnL, risk, SL/TP, tradable picks, or writes
outside the audit directory.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
SRC = AUD / 'v354_lifecycle_setup_identity_latest.json'
OUT = AUD / f'v355_current_lifecycle_frontier_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v355_current_lifecycle_frontier_latest.json'
WAITING = {'WAIT_TOUCH_UNOBSERVED', 'WAIT_RECLAIM_UNOBSERVED', 'WAIT_HOLD_UNOBSERVED'}
FORBIDDEN = ('entry', 'exit', 'pnl', 'tp', 'sl', 'risk', 'won')
STATE_MATURITY = {
    'WAIT_TOUCH_UNOBSERVED': 1,
    'WAIT_RECLAIM_UNOBSERVED': 2,
    'WAIT_HOLD_UNOBSERVED': 3,
}


def i(value: object) -> int:
    try:
        return int(str(value or '').strip())
    except (TypeError, ValueError):
        return -1


def zone_key(row: dict[str, str]) -> tuple[str, str]:
    """Same OB should have one fixed zone; retain any differing zone as a conflict."""
    return (str(row.get('zone_low', '')).strip(), str(row.get('zone_high', '')).strip())


def base_key(row: dict[str, str]) -> tuple[str, str]:
    return (str(row.get('symbol', '')).strip(), str(row.get('ob_idx', '')).strip())


def rank(row: dict[str, str]) -> tuple[int, int, str]:
    # Later BOS is the new observation window.  For an equal event, preserve the
    # most mature observed lifecycle evidence rather than creating two current states.
    return (i(row.get('event_idx')), STATE_MATURITY.get(str(row.get('lifecycle_state')), 0), str(row.get('setup_key', '')))


def no_outcome_columns(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return []
    return [c for c in rows[0] if not c.startswith('no_') and any(x in c.lower() for x in FORBIDDEN)]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    parent = json.loads(SRC.read_text())
    source = Path(parent['artifacts']['current_waiting_paths'])
    with source.open(newline='') as handle:
        rows = list(csv.DictReader(handle))

    by_ob: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_ob[base_key(row)].append(dict(row))

    frontier: list[dict[str, str]] = []
    superseded: list[dict[str, str]] = []
    zone_conflicts: list[dict[str, str]] = []
    groups_with_multiple_paths = 0
    multi_event_groups = 0

    for key, group in sorted(by_ob.items()):
        if len(group) > 1:
            groups_with_multiple_paths += 1
        by_zone: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        for row in group:
            by_zone[zone_key(row)].append(row)

        # A zone mismatch under the same OB is evidence of an upstream contract
        # breach, so it is explicitly isolated instead of silently deduplicated.
        if len(by_zone) > 1:
            for row in group:
                row['frontier_disposition'] = 'ZONE_CONFLICT_NOT_COLLAPSED'
                row['frontier_group_size'] = str(len(group))
                zone_conflicts.append(row)
            continue

        event_idxs = {str(row.get('event_idx', '')) for row in group}
        if len(event_idxs) > 1:
            multi_event_groups += 1
        winner = max(group, key=rank)
        winner_key = str(winner.get('setup_key', ''))
        for row in group:
            row['frontier_group_size'] = str(len(group))
            row['frontier_key'] = '|'.join((*key, *zone_key(row)))
            if row.get('setup_key') == winner_key:
                row['frontier_disposition'] = 'CANONICAL_CURRENT_STATE'
                row['superseded_by_setup_key'] = ''
                frontier.append(row)
            else:
                row['frontier_disposition'] = 'SUPERSEDED_BY_LATER_OR_MORE_MATURE_EVENT_SAME_OB_ZONE'
                row['superseded_by_setup_key'] = winner_key
                superseded.append(row)

    fields = list(rows[0]) + ['frontier_group_size', 'frontier_key', 'frontier_disposition', 'superseded_by_setup_key'] if rows else ['symbol', 'ob_idx']
    # Rows in a zone conflict did not receive a frontier key because they are never
    # allowed into an operational view. Normalise field presence for CSV output.
    for collection in (frontier, superseded, zone_conflicts):
        for row in collection:
            for field in fields:
                row.setdefault(field, '')
    for name, collection in (
        ('v355_current_frontier_paths.csv', frontier),
        ('v355_superseded_current_paths.csv', superseded),
        ('v355_zone_conflict_paths.csv', zone_conflicts),
    ):
        with (OUT / name).open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(collection)

    count_before = Counter(str(row.get('lifecycle_state', '')) for row in rows)
    count_frontier = Counter(str(row.get('lifecycle_state', '')) for row in frontier)
    forbidden = no_outcome_columns(rows)
    uniqueness = len({row['frontier_key'] for row in frontier}) == len(frontier)
    result = {
        'version': 'V355_CURRENT_LIFECYCLE_FRONTIER_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'source': str(source),
        'contract': 'V354 preserves all renewed BOS lifecycle paths as provenance; V355 exposes at most one current canonical state per symbol + OB + exact zone, selecting latest event then most mature same-event state',
        'input_current_paths': len(rows),
        'input_symbols': len({row.get('symbol', '') for row in rows}),
        'ob_groups': len(by_ob),
        'groups_with_multiple_current_paths': groups_with_multiple_paths,
        'multi_event_groups': multi_event_groups,
        'zone_conflict_paths': len(zone_conflicts),
        'canonical_frontier_paths': len(frontier),
        'superseded_provenance_paths': len(superseded),
        'state_counts_before_frontier': dict(count_before),
        'state_counts_frontier': dict(count_frontier),
        'invariants': {
            'all_input_rows_unresolved_wait_states': all(str(row.get('lifecycle_state')) in WAITING for row in rows),
            'all_input_rows_fresh_data': all(str(row.get('fresh_data')).lower() == 'true' for row in rows),
            'all_input_rows_non_tradable': all(str(row.get('tradable')).lower() == 'false' and str(row.get('buy_enabled')).lower() == 'false' for row in rows),
            'no_outcome_fields': not forbidden,
            'no_zone_conflict_promoted': not zone_conflicts,
            'one_canonical_path_per_symbol_ob_zone': uniqueness,
            'frontier_rows_non_tradable': all(str(row.get('tradable')).lower() == 'false' and str(row.get('buy_enabled')).lower() == 'false' for row in frontier),
        },
        'forbidden_columns_found': forbidden,
        'decision': 'CURRENT_LIFECYCLE_FRONTIER_READY__SHADOW_ONLY__HISTORICAL_M60_REMAINS_BLOCKED' if not zone_conflicts else 'CURRENT_LIFECYCLE_ZONE_CONFLICTS_BLOCK_OPERATIONAL_FRONTIER',
        'artifacts': {
            'out_dir': str(OUT),
            'frontier_paths': str(OUT / 'v355_current_frontier_paths.csv'),
            'superseded_paths': str(OUT / 'v355_superseded_current_paths.csv'),
            'zone_conflicts': str(OUT / 'v355_zone_conflict_paths.csv'),
            'latest': str(LATEST),
        },
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v355_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
