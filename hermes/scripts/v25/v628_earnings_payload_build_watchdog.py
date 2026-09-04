#!/usr/bin/env python3
"""Durable, locked no-outcome controller for V628 source payload cache completion."""
from __future__ import annotations

import fcntl
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path('/root/.hermes')
SCRIPT = ROOT / 'scripts/v25/v628_earnings_payload_raw_builder.py'
LATEST = ROOT / 'smc_audit/v628_earnings_payload_raw_build_latest.json'
LOG = ROOT / 'smc_audit/v628_earnings_payload_raw_builder.log'
LOCK = ROOT / 'pit_cache/v628_earnings_payload_raw/.builder.lock'

LOCK.parent.mkdir(parents=True, exist_ok=True)
with LOCK.open('w') as lock:
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit(0)
    while True:
        run = subprocess.run([sys.executable, str(SCRIPT), '--limit', '200', '--workers', '4', '--pause', '0.04'], text=True, capture_output=True, timeout=1800)
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open('a', encoding='utf-8') as handle:
            handle.write(run.stdout + run.stderr)
        try:
            report = json.loads(LATEST.read_text())
        except Exception as exc:
            print(json.dumps({'event': 'V628_SOURCE_BUILD_BLOCKED', 'error': f'{type(exc).__name__}: {exc}'}, ensure_ascii=False))
            raise SystemExit(1)
        if run.returncode:
            print(json.dumps({'event': 'V628_SOURCE_BUILD_FAILURE', 'returncode': run.returncode, 'batch': report.get('batch')}, ensure_ascii=False))
            raise SystemExit(1)
        if report.get('decision') != 'SOURCE_BUILD_IN_PROGRESS':
            print(json.dumps({'event': 'V628_SOURCE_BUILD_COMPLETE', 'denominator': report.get('denominator'), 'committed_valid_by_year': report.get('committed_valid_by_year'), 'next': 'run full source coverage/PIT/semantic catalog audit; do not generate a strategy seed yet'}, ensure_ascii=False))
            break
