#!/usr/bin/env python3
"""V66 extra hard gates for closure gaps.

Runs and aggregates the audits that were missing from the original release gate:
OB loss-bucket replay, semantic signal invariants, retrace-rank buckets, and
daily full-market completeness.
"""
from __future__ import annotations
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
V25 = ROOT / 'scripts/v25'
OUT_JSON = ROOT / 'smc_audit/v66_extra_hard_gates.json'
OUT_MD = ROOT / 'smc_audit/v66_extra_hard_gates.md'

AUDITS = [
    ('ob_loss_bucket', 'v66_ob_loss_bucket_audit.py', ROOT / 'smc_audit/v66_ob_loss_bucket_audit.json'),
    ('signal_semantic', 'v66_signal_semantic_audit.py', ROOT / 'smc_audit/v66_signal_semantic_audit.json'),
    ('multi_retrace_rank', 'v66_multi_retrace_rank_audit.py', ROOT / 'smc_audit/v66_multi_retrace_rank_audit.json'),
    ('daily_completeness', 'v66_daily_completeness_gate.py', ROOT / 'smc_audit/v66_daily_completeness_gate.json'),
]


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def run(script: str) -> dict:
    proc = subprocess.run([sys.executable, str(V25 / script)], cwd=str(V25), text=True, capture_output=True, timeout=300)
    return {'script': script, 'returncode': proc.returncode, 'stdout_tail': proc.stdout[-2000:], 'stderr_tail': proc.stderr[-2000:]}


def main() -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    runs = {name: run(script) for name, script, _ in AUDITS}
    data = {name: load(path, {}) for name, _, path in AUDITS}
    ob = data['ob_loss_bucket'].get('summary', {}) if isinstance(data['ob_loss_bucket'], dict) else {}
    sem = data['signal_semantic'].get('summary', {}) if isinstance(data['signal_semantic'], dict) else {}
    retr = data['multi_retrace_rank'].get('summary', {}) if isinstance(data['multi_retrace_rank'], dict) else {}
    daily = data['daily_completeness'] if isinstance(data['daily_completeness'], dict) else {}
    checks = {
        'audit_scripts_return_zero': all(r['returncode'] == 0 for r in runs.values()),
        'daily_full_market_completeness_pass': daily.get('pass') is True,
        'multi_retrace_materialized': retr.get('pass') is True and bool(retr.get('rank_summary')),
        'ob_loss_bucket_materialized': ob.get('ob_loss_count', 0) > 0 and bool(ob.get('root_counts')),
        'signal_semantic_strict_pass': sem.get('strict_pass') is True,
    }
    blocking_failed = [k for k, v in checks.items() if not v]
    out = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'pass': not blocking_failed,
        'failed_checks': blocking_failed,
        'checks': checks,
        'runs': runs,
        'ob_loss_summary': ob,
        'signal_semantic_summary': sem,
        'multi_retrace_summary': retr,
        'daily_completeness_summary': daily,
        'decision': 'BLOCK_SIGNAL_CORRECTNESS_CLAIM' if not checks['signal_semantic_strict_pass'] else 'SIGNAL_SEMANTICS_VERIFIED',
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    OUT_MD.write_text('# V66 Extra Hard Gates\n\n```json\n' + json.dumps(out, ensure_ascii=False, indent=2) + '\n```\n')
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
