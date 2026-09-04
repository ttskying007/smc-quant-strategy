#!/usr/bin/env python3
"""V433: daily V365 negative-control shadow.

V365 is not a challenger: V366 proved future-contaminated entry timing and V367
proved its causal rebuild has no survivor. This check ensures the rejected branch
cannot silently re-enter production.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
LATEST = AUD / 'v433_v365_negative_control_shadow_latest.json'


def load(name):
    path = AUD / name
    return json.loads(path.read_text()) if path.exists() else {}


def main():
    v365 = load('v365_v333_rule_walkforward_closure_latest.json')
    v366 = load('v366_v365_candidate_causality_audit_latest.json')
    v367 = load('v367_causal_v132_reentry_walkforward_latest.json')
    v368 = load('v368_v367_independent_causality_audit_latest.json')
    required = {
        'v365_no_write': v365.get('production_write') is False,
        'v366_rejected': str(v366.get('decision') or '').startswith('REJECT_V365'),
        'v366_all_early': (v366.get('candidate_stats') or {}).get('entry_before_confirmation_3') == (v366.get('candidate_stats') or {}).get('n'),
        'v367_no_survivor': len(v367.get('common_oos_survivors') or []) == 0,
        'v368_causality_pass': v368.get('decision') == 'CAUSALITY_PASS__V367_ENTRY_AND_T1_CONTRACT_HOLD',
    }
    ok = all(required.values())
    report = {
        'version': 'V433_V365_NEGATIVE_CONTROL_SHADOW',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'shadow_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'buy_enabled': False,
        'checks': required,
        'decision': ('V365_REMAINS_REJECTED_NEGATIVE_CONTROL__NO_BUY' if ok else
                     'V365_REJECTION_EVIDENCE_DRIFT__FAIL_CLOSED'),
    }
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not ok:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
