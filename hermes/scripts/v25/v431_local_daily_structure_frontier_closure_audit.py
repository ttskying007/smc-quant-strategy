#!/usr/bin/env python3
"""V431 no-write closure audit for all defined local-daily pure-SMC ontologies.

This is a registry/integrity audit only. It reads prior reports and never opens
prices, outcomes, candidates, watchlists, or production surfaces.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
OUT = AUD / f'v431_local_daily_structure_frontier_closure_audit_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v431_local_daily_structure_frontier_closure_latest.json'

SOURCES = {
    'R1_R2_C1': AUD / 'v422_pure_structure_closure_latest.json',
    'R4': AUD / 'v426_r4_range_accumulation_breaker_closure_latest.json',
    'R5_INTEGRITY': AUD / 'v428_po3_breaker_integrity_latest.json',
    'R5_REPLAY': AUD / 'v429_po3_breaker_frozen_t1_replay_latest.json',
    'R4_R5_SUMMARY': AUD / 'v430_local_daily_pure_structure_r4_r5_closure_latest.json',
}


def load(path: Path) -> dict:
    if not path.exists():
        raise RuntimeError(f'MISSING_ARTIFACT:{path}')
    return json.loads(path.read_text())


def main() -> None:
    docs = {name: load(path) for name, path in SOURCES.items()}
    errors: list[str] = []

    if 'LOCAL_DAILY_PURE_STRUCTURE_FRONTIER_CLOSED' not in docs['R1_R2_C1'].get('decision', ''):
        errors.append('R1_R2_C1_NOT_CLOSED')
    if 'R4_CLOSED_ECONOMIC' not in docs['R4'].get('decision', ''):
        errors.append('R4_NOT_CLOSED')
    if not docs['R5_INTEGRITY'].get('pass'):
        errors.append('R5_SEMANTIC_INTEGRITY_NOT_PROVEN')
    if docs['R5_REPLAY'].get('annual_gate_pass', {}).get('5d') or docs['R5_REPLAY'].get('annual_gate_pass', {}).get('10d'):
        errors.append('R5_UNEXPECTED_ANNUAL_GATE_PASS')
    if docs['R4_R5_SUMMARY'].get('research_state') != 'R1_R2_C1_R3_R4_R5_LOCAL_DAILY_PURE_STRUCTURE_BRANCHES_CLOSED':
        errors.append('R1_R5_SUMMARY_NOT_CLOSED')

    for name, doc in docs.items():
        for field in ('production_write', 'frontend_write', 'watchlist_write'):
            if doc.get(field) is True:
                errors.append(f'{name}_{field}_TRUE')

    branches = [
        {'id': 'R1', 'ontology': 'SSL -> CHOCH -> fresh demand OB -> retest/reclaim/hold', 'status': 'CLOSED_ECONOMIC'},
        {'id': 'R2', 'ontology': 'SSL -> CHOCH -> post-creation bull FVG -> retest/reclaim/hold', 'status': 'CLOSED_ECONOMIC'},
        {'id': 'C1', 'ontology': 'bull BOS -> fresh demand OB -> retest/reclaim/hold', 'status': 'CLOSED_ECONOMIC'},
        {'id': 'R3', 'ontology': 'EQL pool -> SSL -> CHOCH -> fresh demand OB -> retest/reclaim/hold', 'status': 'CLOSED_ECONOMIC'},
        {'id': 'R4', 'ontology': 'two-sided balance -> SSL reclaim -> range-high BOS -> breaker -> retest/reclaim/hold', 'status': 'CLOSED_ECONOMIC'},
        {'id': 'R5', 'ontology': 'PO3 accumulation -> SSL manipulation -> bull distribution -> breaker -> retest/reclaim/hold', 'status': 'CLOSED_ECONOMIC'},
    ]
    result = {
        'version': 'V431_LOCAL_DAILY_STRUCTURE_FRONTIER_CLOSURE_AUDIT_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'scope': 'Registry closure of all defined local daily pure-structure ontologies; no raw prices or outcomes read.',
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'source_artifacts': {name: str(path) for name, path in SOURCES.items()},
        'defined_branch_registry': branches,
        'invariants': {
            'all_required_artifacts_present': True,
            'no_source_report_claims_production_write': not any('production_write' in e for e in errors),
            'r5_independent_semantic_integrity_pass': docs['R5_INTEGRITY'].get('pass') is True,
            'r5_frozen_annual_gate_pass': docs['R5_REPLAY'].get('annual_gate_pass'),
            'unclosed_defined_local_daily_ontology_count': 0 if not errors else None,
        },
        'audit_failures': errors,
        'decision': (
            'LOCAL_DAILY_PURE_STRUCTURE_RESEARCH_COMPLETE__NO_DEFINED_LEGAL_NEXT_REPLAY'
            if not errors else 'CLOSURE_AUDIT_FAIL__RECONCILE_ARTIFACTS_BEFORE_ANY_ACTION'
        ),
        'remaining_work': {
            'strategy_research': 'NONE on the local daily OHLCV information set. R1-R5 parameter/entry/exit/window variants are prohibited.',
            'operational': 'Only data freshness, semantic drift, current scanner provenance, and frontend/API consistency monitoring remain; none may be represented as a new strategy result.',
            'restart_condition': 'A not-yet-defined causal ontology that is demonstrably distinct from R1-R5 must first pass full-universe no-outcome semantic/lifecycle/chronology audit and >=40 takeover seeds in every 2023-2026 year before exactly one frozen T+1 replay.',
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    report = OUT / 'v431_report.json'
    text = json.dumps(result, ensure_ascii=False, indent=2)
    report.write_text(text)
    LATEST.write_text(text)
    print(text)
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
