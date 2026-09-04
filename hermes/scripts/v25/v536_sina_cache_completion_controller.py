#!/usr/bin/env python3
"""Durably finish the V536 Sina source-isolated partial-range cache.

The controller derives missing work from all four committed frames on every
batch, so a restart cannot skip a partially written symbol.  It writes only
Sina research-cache and audit state; it never writes production artifacts.
"""
from __future__ import annotations

import fcntl
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
V25 = ROOT / 'scripts/v25'
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina'
AUDIT = ROOT / 'smc_audit'
CANONICAL = AUDIT / 'v536_sina_canonical_universe_latest.json'
STATE = ROOT / 'smc_monitor/v536_sina_cache_completion_state.json'
LOCK = ROOT / 'smc_monitor/v536_sina_cache_completion.lock'
FRAMES = ('daily', 'weekly', 'm60', 'm15')
BATCH_SIZE = 50


def atomic(payload: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    temporary.replace(STATE)


def complete_symbols() -> tuple[list[str], int]:
    universe = json.loads(CANONICAL.read_text())['symbols']
    sets = []
    for frame in FRAMES:
        suffix = f'_{frame}.json.gz'
        sets.append({path.name.removesuffix(suffix).replace('_', '.') for path in (RAW / frame).glob(f'*{suffix}')})
    complete = set.intersection(*sets)
    return [symbol for symbol in universe if symbol not in complete], len(complete)


def run(script: str, *args: str, timeout: int) -> tuple[int, dict, str]:
    proc = subprocess.run([sys.executable, str(V25 / script), *args], cwd=V25, capture_output=True, text=True, timeout=timeout)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {}
    return proc.returncode, payload, (proc.stderr or proc.stdout)[-1000:]


def main() -> None:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open('w') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            atomic({'version': 'V536_SINA_COMPLETION_CONTROLLER_V1', 'state': 'SKIP_LOCKED', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'research_only': True, 'production_write': False})
            return
        consecutive_failures = 0
        started = datetime.now().isoformat(timespec='seconds')
        while True:
            missing, complete = complete_symbols()
            base = {'version': 'V536_SINA_COMPLETION_CONTROLLER_V1', 'started_at': started, 'generated_at': datetime.now().isoformat(timespec='seconds'), 'research_only': True, 'production_write': False, 'cross_source_substitution': False, 'complete': complete, 'remaining': len(missing), 'batch_size': BATCH_SIZE}
            if not missing:
                rc, coverage, tail = run('v536_sina_partial_coverage_audit.py', timeout=120)
                rc2, audit, tail2 = run('v536_source_isolated_cache_audit.py', '--source', 'sina', timeout=1800)
                atomic({**base, 'state': 'COMPLETE' if rc == 0 and rc2 == 0 and audit.get('failed') == 0 else 'FINAL_AUDIT_FAILED', 'coverage': coverage, 'source_audit': audit, 'errors': [tail, tail2]})
                while True:
                    time.sleep(3600)
            rc, report, tail = run('v536_build_sina_partial_multitf_cache.py', '--limit', str(BATCH_SIZE), timeout=1500)
            completed = int(report.get('completed', 0) or 0)
            failed = int(report.get('failed', BATCH_SIZE) or 0)
            if rc == 0 and completed > 0:
                consecutive_failures = 0
                state = 'RUNNING'
                delay = 2
            else:
                consecutive_failures += 1
                state = 'BACKOFF_RETRY'
                delay = min(900, 15 * (2 ** min(consecutive_failures, 6)))
            after_missing, after_complete = complete_symbols()
            atomic({**base, 'complete': after_complete, 'remaining': len(after_missing), 'state': state, 'last_batch': {'returncode': rc, 'requested': report.get('requested'), 'completed': completed, 'failed': failed, 'decision': report.get('decision'), 'error_tail': tail if rc else ''}, 'consecutive_failures': consecutive_failures, 'next_retry_seconds': delay})
            time.sleep(delay)


if __name__ == '__main__':
    main()
