#!/usr/bin/env python3
"""V416 no-write strict semantic rebuild of V409 lifecycle candidates.

Consumes only V409 raw signal fields and V415 semantic classifications. It keeps
only candidates whose literal post-confirmation lifecycle is legal, then uses
V415's lifecycle reconstructed strictly after max(event_idx, poi_idx).
No outcomes or tradable fields are produced.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
V409 = AUD / 'v409_causal_signal_combination_latest.json'
V415 = AUD / 'v415_poi_lifecycle_integrity_latest.json'
OUT = AUD / f'v416_strict_semantic_combination_rebuild_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v416_strict_semantic_combination_rebuild_latest.json'


def key(row: dict) -> tuple[str, str, str, str]:
    return row['symbol'], row['combo_key'], row['poi_idx'], row['event_idx']


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    v409 = json.loads(V409.read_text())
    v415 = json.loads(V415.read_text())
    with Path(v409['artifacts']['rows']).open() as handle:
        source_rows = list(csv.DictReader(handle))
    with Path(v415['artifacts']['rows']).open() as handle:
        integrity = {key(row): row for row in csv.DictReader(handle)}

    output, source_counts, lifecycle_counts = [], Counter(), defaultdict(Counter)
    for row in source_rows:
        audit = integrity.get(key(row))
        if audit is None:
            source_counts['MISSING_V415_AUDIT_ROW'] += 1
            continue
        source_counts[audit['source_state']] += 1
        if audit.get('strict_semantic_eligible') != 'true':
            continue
        output.append({
            'symbol': row['symbol'], 'combo_key': row['combo_key'],
            'sweep_idx': row['sweep_idx'], 'sweep_date': row['sweep_date'],
            'event_idx': row['event_idx'], 'event_date': row['event_date'],
            'poi_idx': row['poi_idx'], 'poi_date': row['poi_date'],
            'poi_type': row['poi_type'], 'zone_low': row['zone_low'], 'zone_high': row['zone_high'],
            'strict_lifecycle_start_idx': audit['legal_lifecycle_start_idx'],
            'lifecycle_state': audit['corrected_lifecycle_state'],
            'takeover_date': audit['corrected_takeover_date'],
            'touch_idx': audit['corrected_touch_idx'],
            'reclaim_idx': audit['corrected_reclaim_idx'],
            'semantic_contract': 'all prerequisites known -> fresh post-prerequisite touch -> reclaim -> hold',
            'tradable': 'false', 'buy_enabled': 'false', 'outcome_fields_present': 'false',
        })
        lifecycle_counts[row['combo_key']][audit['corrected_lifecycle_state']] += 1

    fields = list(output[0]) if output else ['symbol', 'combo_key']
    with (OUT / 'v416_strict_lifecycle_rows.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)
    by_combo = {}
    for combo in sorted({row['combo_key'] for row in source_rows}):
        rows = [row for row in output if row['combo_key'] == combo]
        by_combo[combo] = {
            'strict_semantic_candidates': len(rows),
            'lifecycle': dict(lifecycle_counts[combo]),
            'takeover_confirmed': lifecycle_counts[combo]['TAKEOVER_CONFIRMED'],
            'takeover_confirmed_pct': round(lifecycle_counts[combo]['TAKEOVER_CONFIRMED'] / len(rows) * 100, 4) if rows else 0.0,
        }
    report = {
        'version': 'V416_STRICT_SEMANTIC_COMBINATION_REBUILD_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'scope': 'signal-definition rebuild only; no entry, exit, mark, PnL, or promotion',
        'strict_contract': {
            'ob': 'backward-anchored demand OB must have no pre-event wick mitigation or close invalidation before a claimed post-confirmation first retest',
            'fvg': 'FVG lifecycle begins only after its creation bar',
            'lifecycle': 'starts strictly after max(event_idx, poi_idx)',
        },
        'source_state_counts': dict(source_counts),
        'combination_summary': by_combo,
        'invariants': {
            'all_rows_non_tradable': all(row['tradable'] == 'false' for row in output),
            'no_outcome_fields': all(row['outcome_fields_present'] == 'false' for row in output),
            'no_entries_exits_or_marks_created': True,
        },
        'decision': 'STRICT_SIGNAL_DEFINITION_MATERIALIZED__SEMANTICALLY_VALID_CANDIDATES_ONLY__NO_ECONOMIC_CLAIM_OR_PROMOTION',
        'artifacts': {'out_dir': str(OUT), 'rows': str(OUT / 'v416_strict_lifecycle_rows.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v416_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
