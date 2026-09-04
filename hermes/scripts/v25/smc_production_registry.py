#!/usr/bin/env python3
"""Build the single fail-closed SMC production registry from audited evidence."""
from __future__ import annotations

import json
import pathlib
import tempfile
from datetime import datetime

ROOT = pathlib.Path('/root/.hermes')
MON = ROOT / 'smc_monitor'
OUT = MON / 'production_registry.json'
EPOCH = MON / 'kline_epoch_current.json'
V432 = ROOT / 'smc_audit/v432_v185_causality_provenance_latest.json'
V433 = ROOT / 'smc_audit/v433_v365_negative_control_shadow_latest.json'
V443 = ROOT / 'smc_audit/v443_causal_production_rebuild_program_closure_latest.json'


def load(path, default=None):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except Exception:
        return default


def write_atomic(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, prefix=path.name + '.', suffix='.tmp', delete=False) as handle:
        temp = pathlib.Path(handle.name)
        json.dump(value, handle, ensure_ascii=False, indent=2)
    temp.replace(path)


def build_registry(epoch, v432, v433, v443):
    epoch_valid = bool(epoch and epoch.get('status') == 'COMMITTED' and epoch.get('epoch_id') and epoch.get('market_date'))
    v185_rejected = bool(
        v432
        and v432.get('current_scanner_rebuild_allowed') is False
        and str(v432.get('decision', '')).startswith('REJECT_V185_AS_PRODUCTION_BASELINE')
    )
    v365_negative = bool(
        v433
        and v433.get('buy_enabled') is False
        and v433.get('decision') == 'V365_REMAINS_REJECTED_NEGATIVE_CONTROL__NO_BUY'
    )
    program_closed = bool(
        v443
        and v443.get('decision') == 'CAUSAL_PRODUCTION_REBUILD_COMPLETE__NO_PROMOTABLE_LOCAL_PURE_STRUCTURE_STRATEGY__KEEP_EMPTY_BOOK'
        and v443.get('production_strategy') is None
        and v443.get('shadow_challenger') is None
        and v443.get('active_buy_valid_count') == 0
    )
    evidence_complete = v185_rejected and v365_negative and program_closed
    state = 'EMPTY_BOOK' if epoch_valid and evidence_complete else 'FAIL_CLOSED_CONTROL_EVIDENCE_INVALID'
    return {
        'schema_version': 'SMC_PRODUCTION_REGISTRY_V1',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'state': state,
        'production_strategy': None,
        'shadow_challenger': None,
        'buy_enabled': False,
        'active_buy_valid_count': 0,
        'forbidden_fallback': True,
        'data_epoch': {
            'valid': epoch_valid,
            'epoch_id': (epoch or {}).get('epoch_id'),
            'market_date': (epoch or {}).get('market_date'),
            'status': (epoch or {}).get('status'),
        },
        'lineages': {
            'V185': {
                'status': 'REJECTED_RESEARCH' if v185_rejected else 'EVIDENCE_INVALID',
                'buy_enabled': False,
                'reason': (v432 or {}).get('decision'),
            },
            'V365': {
                'status': 'NEGATIVE_CONTROL' if v365_negative else 'EVIDENCE_INVALID',
                'buy_enabled': False,
                'reason': (v433 or {}).get('decision'),
            },
        },
        'negative_controls': ['V365'] if v365_negative else [],
        'research_program': {
            'status': 'COMPLETE_NO_PROMOTABLE_LOCAL_PURE_STRUCTURE_STRATEGY' if program_closed else 'EVIDENCE_INVALID',
            'closed_ontologies': (v443 or {}).get('distinct_ontology_results', {}),
            'decision': (v443 or {}).get('decision'),
        },
        'next_ontology': None,
        'invariants': {
            'historical_pick_fallback_disabled': True,
            'shadow_buy_disabled': True,
            'empty_book_is_valid_operational_state': True,
            'buy_requires_promoted_current_raw_scanner': True,
        },
    }


def main():
    registry = build_registry(load(EPOCH, {}), load(V432, {}), load(V433, {}), load(V443, {}))
    write_atomic(OUT, registry)
    print(json.dumps(registry, ensure_ascii=False, indent=2))
    if registry['state'] != 'EMPTY_BOOK':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
