#!/usr/bin/env python3
"""V418 records the semantic correction that supersedes V411's old-label closure."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
SOURCE = AUD / 'v417_strict_semantic_frozen_t1_replay_latest.json'
OUT = AUD / f'v418_strict_semantic_closure_correction_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v418_strict_semantic_closure_correction_latest.json'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads(SOURCE.read_text())
    passed = source['combination_horizon_passes']
    report = {
        'version': 'V418_STRICT_SEMANTIC_CLOSURE_CORRECTION_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'supersedes_as_economic_evidence': 'V411 old V409 lifecycle labels only; V411 is not semantic proof after V415 discovered pre-event OB mitigation and FVG creation-bar labeling defects.',
        'replacement_evidence': str(SOURCE),
        'strict_definition': 'exclude pre-event mitigated/invalidated OB; allow FVG after creation but start lifecycle strictly after max(event_idx, poi_idx); takeover -> next-session open.',
        'fixed_gate_unchanged': source['predeclared_annual_gate'],
        'strict_replay_rows': source['rows_with_t1_entry'],
        'combination_horizon_passes': passed,
        'invariants': source['invariants'],
        'decision': ('STRICT_SEMANTIC_DAILY_CAUSAL_COMBINATIONS_CLOSED__0_OF_6_FROZEN_ANNUAL_GATES_PASS__'
                     'NO_THRESHOLD_WINDOW_OR_EXIT_MINING__NO_PRODUCTION_PROMOTION'),
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v418_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
