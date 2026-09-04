#!/usr/bin/env python3
"""Silent durable batch runner for V562; stdout only on failure or completion."""
from __future__ import annotations

import fcntl
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path('/root/.hermes')
SCRIPT = ROOT / 'scripts/v25/v562_exchange_margin_raw_builder.py'
LATEST = ROOT / 'smc_audit/v562_exchange_margin_raw_build_latest.json'
LOG = ROOT / 'smc_audit/v562_exchange_margin_raw_builder.log'
LOCK = ROOT / 'pit_cache/v562_exchange_margin_raw/.builder.lock'

LOCK.parent.mkdir(parents=True, exist_ok=True)
with LOCK.open('w') as lock:
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit(0)
    run = subprocess.run([sys.executable, str(SCRIPT), '--limit', '80', '--pause', '0.2'], text=True, capture_output=True, timeout=1800)

LOG.parent.mkdir(parents=True, exist_ok=True)
with LOG.open('a', encoding='utf-8') as f:
    f.write(run.stdout + run.stderr)
try:
    report = json.loads(LATEST.read_text())
except Exception as exc:
    print(f'V562_MARGIN_BUILD_BLOCKED: cannot read report: {exc}')
    raise SystemExit(1)
if run.returncode or report.get('failed'):
    print(json.dumps({'event': 'V562_MARGIN_BUILD_FAILURE', 'returncode': run.returncode, 'failed': report.get('failed'), 'errors': report.get('errors'), 'remaining': report.get('remaining_estimate')}, ensure_ascii=False))
elif report.get('decision') == 'SOURCE_BUILD_COMPLETE_FOR_AVAILABLE_PRIOR_SESSIONS__CURRENT_TAIL_PENDING_PUBLICATION':
    print(json.dumps({'event': 'V562_MARGIN_RAW_BUILD_COMPLETE', 'dates': report.get('date_denominator_from_daily_cache'), 'remaining': report.get('remaining_estimate'), 'next': 'run source coverage and PIT audit before any SMC seed'}, ensure_ascii=False))
