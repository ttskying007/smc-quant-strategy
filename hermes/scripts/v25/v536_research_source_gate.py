#!/usr/bin/env python3
"""Fail-closed authorization gate for V536 future research inputs.

It authorizes a source namespace only from explicit source-local evidence. It
cannot and does not combine provider files to make a source appear complete.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path('/root/.hermes')
REGISTRY = ROOT / 'intraday_cache/raw_multitf_v536/source_registry.json'
AUDIT = ROOT / 'smc_audit'


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default='baostock')
    parser.add_argument('--scope', choices=('partial_source_local', 'full_universe', 'cross_source_validated'), default='full_universe')
    parser.add_argument('--required-symbols', type=int, default=0, help='0 means derive no count threshold beyond audit pass')
    args = parser.parse_args()
    registry = read(REGISTRY)
    source = registry['sources'].get(args.source)
    if not source:
        raise SystemExit(f'unknown source: {args.source}')
    full_audit_path = AUDIT / f'v536_source_isolated_cache_audit_{args.source}_full_latest.json'
    audit_path = full_audit_path if full_audit_path.exists() else AUDIT / f'v536_source_isolated_cache_audit_{args.source}_latest.json'
    source_audit = read(audit_path) if audit_path.exists() else {}
    local_pass = source_audit.get('decision') in {'SOURCE_ISOLATED_CACHE_PASS', 'CACHED_SUBSET_INTEGRITY_PASS__UNIVERSE_INCOMPLETE'}
    enough_symbols = source_audit.get('symbols', 0) >= args.required_symbols
    source_local_eligible = source.get('eligible_for_source_local_research') is True
    full_universe_eligible = source.get('universe_coverage', {}).get('full_universe_complete') is True
    cross_source_eligible = source.get('eligible_for_full_market_research') is True
    eligibility = {
        'partial_source_local': source_local_eligible,
        'full_universe': full_universe_eligible,
        'cross_source_validated': cross_source_eligible,
    }[args.scope]
    allowed = local_pass and enough_symbols and eligibility
    decision = 'READ_AUTHORIZED_PARTIAL_SAME_SOURCE_ONLY' if allowed and args.scope == 'partial_source_local' else ('READ_AUTHORIZED_FULL_UNIVERSE' if allowed else 'READ_BLOCKED__UNIVERSE_OR_SOURCE_NOT_PROMOTED')
    reason = ('Partial same-source diagnostics only; all-market conclusions and promotion remain prohibited.' if allowed else 'The requested research scope is not fully covered and promoted; no fallback or cross-provider filling is permitted.')
    result = {
        'version': 'V536_RESEARCH_SOURCE_GATE_V1',
        'research_only': True,
        'production_write': False,
        'source': args.source,
        'scope': args.scope,
        'source_root': source.get('root'),
        'source_writer_state': source.get('writer_state'),
        'source_local_audit': {'path': str(audit_path), 'decision': source_audit.get('decision'), 'symbols': source_audit.get('symbols'), 'passed': source_audit.get('passed'), 'failed': source_audit.get('failed')},
        'source_local_eligible_from_registry': source_local_eligible,
        'full_universe_eligible_from_registry': full_universe_eligible,
        'cross_source_eligible_from_registry': cross_source_eligible,
        'required_symbols': args.required_symbols,
        'research_read_authorized': allowed,
        'decision': decision,
        'reason': reason,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not allowed:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
