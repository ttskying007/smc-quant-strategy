#!/usr/bin/env python3
"""One idempotent V536 cache batch: monitor → next 100 missing SH/SZ → monitor.

A non-blocking flock makes scheduler overlap fail closed. It only invokes the
research-only cache builder and never touches signal/production artifacts.
"""
from __future__ import annotations

import fcntl
import gzip
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
V25 = ROOT / 'scripts/v25'
DAILY = ROOT / 'kline_cache'
M15 = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/baostock/m15'
LOCK = ROOT / 'smc_monitor/v536_multitf_cache_batch.lock'


def symbols() -> list[str]:
    rows = []
    for path in DAILY.glob('*_daily_750.json'):
        match = re.fullmatch(r'(\d+)_(SH|SZ)_daily_750\.json', path.name)
        if match:
            rows.append(f'{match.group(1)}.{match.group(2)}')
    return sorted(set(rows))


def done() -> set[str]:
    return {p.name.replace('_m15.json.gz', '').replace('_', '.') for p in M15.glob('*_m15.json.gz')}


def run(cmd: list[str], timeout: int) -> dict:
    p = subprocess.run(cmd, cwd=V25, capture_output=True, text=True, timeout=timeout)
    return {'returncode': p.returncode, 'stdout_tail': p.stdout[-2000:], 'stderr_tail': p.stderr[-1000:]}


def main() -> None:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open('w') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('{"state":"SKIP_LOCKED","production_write":false}')
            return
        before = run(['/usr/bin/python3', str(V25 / 'v536_multitf_source_monitor.py')], 120)
        universe, completed = symbols(), done()
        missing = [x for x in universe if x not in completed]
        if not missing:
            print('{"state":"COMPLETE","production_write":false,"signal_or_trade_generation":false}')
            return
        start = missing[0]
        # 25 symbols reliably finish inside Hermes cron's one-hour execution cap.
        batch = run([
            '/usr/bin/python3', str(V25 / 'v536_build_multitf_raw_cache.py'),
            '--resume-from', start, '--limit', '25',
        ], 3000)
        after = run(['/usr/bin/python3', str(V25 / 'v536_multitf_source_monitor.py')], 120)
        now_done = done()
        print({
            'version': 'V536_MULTITF_CACHE_BATCH_CONTROLLER', 'generated_at': datetime.now().isoformat(timespec='seconds'),
            'state': 'BATCH_FINISHED' if batch['returncode'] == 0 else 'BATCH_FAILED',
            'batch_start_symbol': start, 'before_complete': len(completed), 'after_complete': len(now_done),
            'universe_sh_sz': len(universe), 'remaining': len(set(universe) - now_done),
            'pre_monitor_returncode': before['returncode'], 'builder_returncode': batch['returncode'], 'post_monitor_returncode': after['returncode'],
            'builder_stdout_tail': batch['stdout_tail'], 'builder_stderr_tail': batch['stderr_tail'],
            'production_write': False, 'signal_or_trade_generation': False,
        })


if __name__ == '__main__':
    main()
