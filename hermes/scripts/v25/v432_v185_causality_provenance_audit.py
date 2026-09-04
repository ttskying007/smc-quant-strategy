#!/usr/bin/env python3
"""V432: audit whether V185 can be reconstructed causally as a current scanner.

This audit does not replay outcomes or search rules. It verifies source promotion
state, confirmation chronology, and the provenance needed to reproduce selectors
from current raw bars.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
TRADES = ROOT / 'smc_opt_v185_combined_production_candidate/v185_trades.json'
FORMAL = ROOT / 'smc_audit/v185_formal_candidate_v175_plus_child_20260626_001218/summary.json'
LATEST = ROOT / 'smc_audit/v432_v185_causality_provenance_latest.json'


def i(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def main():
    rows = json.loads(TRADES.read_text())
    formal = json.loads(FORMAL.read_text())
    v175 = [r for r in rows if str(r.get('semantic_layer') or '').startswith('V175_')]
    child = [r for r in rows if str(r.get('semantic_layer') or '').startswith('V185_CHILD_')]

    before_confirm2 = []
    before_confirm3 = []
    for row in v175:
        entry = i(row.get('entry_idx'))
        confirm2 = i(row.get('v132_entry_after_confirm_idx_2'))
        confirm3 = i(row.get('v132_entry_after_confirm_idx_3'))
        if entry is not None and confirm2 is not None and entry < confirm2:
            before_confirm2.append(row)
        if entry is not None and confirm3 is not None and entry < confirm3:
            before_confirm3.append(row)

    child_required = ('reclaim_idx', 'v132_entry_after_confirm_idx_3', 'touch_idx', 'zone_idx')
    child_missing = {key: sum(i(r.get(key)) is None for r in child) for key in child_required}
    child_uses_post_reclaim = sum(i(r.get('v132_bull_count_3')) == 3 for r in child)

    failures = []
    if formal.get('production_write') is not True:
        failures.append('FORMAL_SOURCE_WAS_SHADOW_ONLY_NOT_PRODUCTION_APPROVED')
    if before_confirm2:
        failures.append('V175_ENTRY_PRECEDES_REQUIRED_TAKEOVER2_CONFIRMATION')
    if before_confirm3:
        failures.append('V175_ENTRY_PRECEDES_REQUIRED_TAKEOVER3_CONFIRMATION')
    if child_uses_post_reclaim:
        failures.append('CHILD_SELECTOR_USES_THREE_POST_RECLAIM_BARS')
    if any(child_missing.values()):
        failures.append('CHILD_MISSING_CAUSAL_PROVENANCE_INDICES')

    report = {
        'version': 'V432_V185_CAUSALITY_PROVENANCE_AUDIT',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'source_rows': len(rows),
        'components': {'v175': len(v175), 'child': len(child)},
        'formal_source_gate': {
            'decision': formal.get('decision'),
            'production_write': formal.get('production_write'),
            'frontend_write': formal.get('frontend_write'),
            'watchlist_write': formal.get('watchlist_write'),
        },
        'v175_chronology': {
            'rows': len(v175),
            'entry_before_confirm2': len(before_confirm2),
            'entry_before_confirm3': len(before_confirm3),
            'entry_minus_confirm2': dict(Counter(i(r.get('entry_idx')) - i(r.get('v132_entry_after_confirm_idx_2')) for r in v175)),
            'entry_minus_confirm3': dict(Counter(i(r.get('entry_idx')) - i(r.get('v132_entry_after_confirm_idx_3')) for r in v175)),
        },
        'child_provenance': {
            'rows': len(child),
            'rows_using_v132_bull_count_3_eq_3': child_uses_post_reclaim,
            'missing_required_indices': child_missing,
            'selector_definition': 'v132_bull_count_3 is computed from bars reclaim_idx+1..reclaim_idx+3; legal entry is reclaim_idx+4 open',
        },
        'audit_failures': failures,
        'current_scanner_rebuild_allowed': not failures,
        'decision': ('V185_CAUSAL_SCANNER_REBUILD_ALLOWED' if not failures else
                     'REJECT_V185_AS_PRODUCTION_BASELINE__HISTORICAL_ADVANTAGE_NOT_CAUSALLY_PROVEN'),
        'required_action': ('BUILD_CURRENT_SCANNER' if not failures else
                            'FAIL_CLOSED_EMPTY_BOOK__PRESERVE_HISTORY_AS_REJECTED_RESEARCH_ONLY'),
    }
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
