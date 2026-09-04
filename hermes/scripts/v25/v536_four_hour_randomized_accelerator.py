#!/usr/bin/env python3
"""Bounded V536 raw multi-timeframe cache accelerator.

Baostock can hang on a single socket read.  Process symbols one-at-a-time so a
hang only loses that symbol, not the rest of the batch.  History range remains
fixed 2023-01-01..2026-07-17.  Never writes signals, trades, or production state.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import random
import re
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
V25 = ROOT / 'scripts/v25'
DAILY = ROOT / 'kline_cache'
M15 = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/baostock/m15'
QUARANTINE = ROOT / 'intraday_cache/raw_multitf_v536/quarantine'
MON = ROOT / 'smc_monitor'
LOCK = MON / 'v536_multitf_cache_batch.lock'
OUT = MON / 'v536_four_hour_acceleration_latest.json'
BATCH_FILE = MON / 'v536_active_batch_symbols.txt'
HANG_FILE = MON / 'v536_symbol_hang_counts.json'
BUILDER_LATEST = ROOT / 'smc_audit/v536_multitf_raw_cache_latest.json'
DEADLINE_SEC = 4 * 60 * 60
HANG_QUARANTINE_THRESHOLD = 3


def atomic(payload: dict) -> None:
    tmp = OUT.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    tmp.replace(OUT)


def atomic_path(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    tmp.replace(path)


def missing() -> list[str]:
    universe = []
    for p in DAILY.glob('*_daily_750.json'):
        m = re.fullmatch(r'(\d+)_(SH|SZ)_daily_750\.json', p.name)
        if m:
            universe.append(f'{m.group(1)}.{m.group(2)}')
    # A symbol is complete only when every derived frame committed.  m15 alone
    # cannot be a completion marker because process death can occur between the
    # four atomic file replacements.
    cache_root = M15.parent
    frames = ('daily', 'weekly', 'm60', 'm15')
    complete_sets = []
    for frame in frames:
        suffix = f'_{frame}.json.gz'
        complete_sets.append({p.name.removesuffix(suffix).replace('_', '.')
                              for p in (cache_root / frame).glob(f'*{suffix}')})
    done = set.intersection(*complete_sets) if complete_sets else set()
    quarantined = {p.stem for p in QUARANTINE.glob('*.json')}
    return [s for s in sorted(set(universe)) if s not in done and s not in quarantined]


def load_hangs() -> dict[str, int]:
    try:
        data = json.loads(HANG_FILE.read_text())
        return {str(k): int(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def record_failure(symbol: str, reason: str) -> int:
    """Quarantine a repeatedly non-buildable source response after 3 attempts."""
    hangs = load_hangs()
    hangs[symbol] = hangs.get(symbol, 0) + 1
    atomic_path(HANG_FILE, hangs)
    if hangs[symbol] >= HANG_QUARANTINE_THRESHOLD:
        atomic_path(QUARANTINE / f'{symbol}.json', {
            'symbol': symbol,
            'reason': f'{reason}_x{hangs[symbol]}',
            'recorded_at': datetime.now().isoformat(timespec='seconds'),
        })
    return hangs[symbol]


def clear_hang(symbol: str) -> None:
    hangs = load_hangs()
    if symbol in hangs:
        del hangs[symbol]
        atomic_path(HANG_FILE, hangs)


def run_one(symbol: str, timeout_sec: int) -> dict:
    temporary = BATCH_FILE.with_suffix('.tmp')
    temporary.write_text(symbol + '\n')
    temporary.replace(BATCH_FILE)
    cmd = ['/usr/bin/python3', str(V25 / 'v536_build_multitf_raw_cache.py'),
           '--symbols-file', str(BATCH_FILE)]
    process = subprocess.Popen(
        cmd, cwd=V25, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_sec)
        return {'returncode': process.returncode, 'timed_out': False,
                'stdout_tail': stdout[-1200:], 'stderr_tail': stderr[-800:]}
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        return {'returncode': 124, 'timed_out': True,
                'stdout_tail': stdout[-1200:], 'stderr_tail': stderr[-800:]}


def builder_status(symbol: str) -> dict:
    try:
        report = json.loads(BUILDER_LATEST.read_text())
        rows_path = Path(report['artifacts']['rows'])
        rows = json.loads(rows_path.read_text())
        got = {row.get('symbol') for row in rows}
        if report.get('requested_symbols') != 1 or got != {symbol}:
            return {'status_counts': {'BUILDER_REPORT_STALE_OR_MISMATCH': 1},
                    'builder_status': None}
        status = rows[0].get('status') if rows else None
        return {'status_counts': report.get('status_counts', {}),
                'builder_status': status,
                'builder_generated_at': report.get('generated_at')}
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        return {'status_counts': {'BUILDER_REPORT_UNAVAILABLE': 1}, 'builder_status': None}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--window-sec', type=int, default=DEADLINE_SEC)
    parser.add_argument('--max-batches', type=int, default=0,
                        help='max symbols in this invocation; 0 = until window expires')
    parser.add_argument('--batch-min', type=int, default=1,
                        help='kept for CLI compatibility; treated as symbol-count min')
    parser.add_argument('--batch-max', type=int, default=1,
                        help='kept for CLI compatibility; treated as symbol-count max')
    parser.add_argument('--per-batch-timeout-sec', type=int, default=75,
                        help='hard timeout per single symbol')
    args = parser.parse_args()
    if args.window_sec <= 0 or args.per_batch_timeout_sec <= 0:
        raise SystemExit('invalid bounded incremental-run arguments')
    # Prefer explicit max-batches; else use batch-max as symbol budget for this run.
    symbol_budget = args.max_batches if args.max_batches > 0 else max(args.batch_min, args.batch_max)
    if symbol_budget <= 0:
        symbol_budget = 8

    MON.mkdir(parents=True, exist_ok=True)
    with LOCK.open('w') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('{"state":"SKIP_LOCKED","production_write":false}')
            return
        began = time.monotonic()
        started_at = datetime.now().isoformat(timespec='seconds')
        initial = len(missing())
        rows = []
        processed = 0
        source_blacklisted = False
        while time.monotonic() - began < args.window_sec and processed < symbol_budget:
            todo = missing()
            if not todo:
                break
            symbol = todo[0]
            before = len(todo)
            atomic({
                'version': 'V536_PER_SYMBOL_ACCELERATION',
                'state': 'BATCH_RUNNING',
                'started_at': started_at,
                'elapsed_sec': round(time.monotonic() - began, 1),
                'initial_remaining': initial,
                'current_remaining': before,
                'active_symbol': symbol,
                'processed_in_window': processed,
                'batches': rows[-40:],
                'production_write': False,
                'signal_or_trade_generation': False,
            })
            result = run_one(symbol, args.per_batch_timeout_sec)
            source_blacklisted = '黑名单用户' in (result['stdout_tail'] + result['stderr_tail'])
            after = len(missing())
            completed = 1 if after < before else 0
            hang_count = 0
            if source_blacklisted:
                outcome = {
                    'status_counts': {'BAOSTOCK_SOURCE_BLACKLISTED': 1},
                    'builder_status': 'BAOSTOCK_SOURCE_BLACKLISTED',
                }
            elif result['timed_out']:
                hang_count = record_failure(symbol, 'BAOSTOCK_HANG_TIMEOUT')
                outcome = {
                    'status_counts': {'TIMED_OUT': 1}, 'builder_status': 'TIMEOUT',
                    'hang_count': hang_count,
                }
            elif completed:
                clear_hang(symbol)
                outcome = builder_status(symbol)
            else:
                outcome = builder_status(symbol)
                status = str(outcome.get('builder_status') or 'BUILDER_UNAVAILABLE')
                hang_count = record_failure(symbol, status)
                outcome['failure_count'] = hang_count
            row = {
                'at': datetime.now().isoformat(timespec='seconds'),
                'symbol': symbol,
                'requested_symbols': 1,
                'before_remaining': before,
                'after_remaining': after,
                'completed': completed,
                'returncode': result['returncode'],
                'timed_out': result['timed_out'],
                'no_progress': completed == 0,
                **outcome,
            }
            rows.append(row)
            processed += 1
            state = 'NO_PROGRESS_RETRY_REQUIRED' if completed == 0 else 'RUNNING'
            atomic({
                'version': 'V536_PER_SYMBOL_ACCELERATION',
                'state': state,
                'started_at': started_at,
                'elapsed_sec': round(time.monotonic() - began, 1),
                'initial_remaining': initial,
                'current_remaining': after,
                'completed_in_window': initial - after,
                'batches': rows[-40:],
                'production_write': False,
                'signal_or_trade_generation': False,
            })
            if source_blacklisted:
                break
            if result['timed_out'] or result['returncode'] != 0:
                time.sleep(random.uniform(1.0, 3.0))
            else:
                time.sleep(random.uniform(0.2, 1.2))

        remaining = len(missing())
        if source_blacklisted:
            final_state = 'SOURCE_BLACKLISTED__CRON_PAUSED_REQUIRED'
        elif not remaining:
            final_state = 'CACHE_COMPLETE'
        elif any(x.get('no_progress') for x in rows) and all(x.get('no_progress') for x in rows):
            final_state = 'NO_PROGRESS_RETRY_REQUIRED'
        elif processed >= symbol_budget:
            final_state = 'MAX_BATCHES_FINISHED'
        else:
            final_state = 'TIMEBOX_FINISHED'
        report = {
            'version': 'V536_PER_SYMBOL_ACCELERATION',
            'state': final_state,
            'started_at': started_at,
            'finished_at': datetime.now().isoformat(timespec='seconds'),
            'elapsed_sec': round(time.monotonic() - began, 1),
            'initial_remaining': initial,
            'current_remaining': remaining,
            'completed_in_window': initial - remaining,
            'processed_symbols': processed,
            'batches': rows,
            'production_write': False,
            'signal_or_trade_generation': False,
        }
        atomic(report)
        print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
