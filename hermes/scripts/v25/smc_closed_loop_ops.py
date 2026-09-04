#!/usr/bin/env python3
"""SMC closed-loop automation runner.

Modes:
- daily: run selector + daily audit + auto-ingest today's picks.
- live: poll /api/live-prices during market hours so SL/TP closes, reviews and ledger persist.
- postmarket: run live once (if available) then refresh daily audit snapshot.
"""
from __future__ import annotations
import argparse, json, pathlib, subprocess, sys, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path('/root/.hermes')
SCRIPTS = ROOT / 'scripts'
MON = ROOT / 'smc_monitor'
MON.mkdir(parents=True, exist_ok=True)
DAILY_SCRIPT = SCRIPTS / 'v25' / 'smc_daily_ops.py'
BASE_URL = 'http://127.0.0.1:8890'


def now_cst():
    return datetime.now(timezone(timedelta(hours=8)))


def is_market_open(ts=None):
    ts = ts or now_cst()
    mins = ts.hour * 60 + ts.minute
    return ts.weekday() < 5 and ((570 <= mins < 690) or (780 <= mins < 900))


def append_log(name, rec):
    rec = {'ts': now_cst().isoformat(timespec='seconds'), **rec}
    with (MON / name).open('a') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    return rec


def run_daily():
    # Daily ops now runs K-line refresh + scanner + multi-stage shadow gates.
    # Normal runs can exceed 15 minutes (2026-06-23: ~17 minutes), so the
    # outer closed-loop wrapper must not kill the inner audited stages early.
    timeout = 2400
    try:
        proc = subprocess.run([sys.executable, str(DAILY_SCRIPT)], cwd=str(SCRIPTS), text=True, capture_output=True, timeout=timeout)
        rec = {'mode': 'daily', 'ok': proc.returncode == 0, 'returncode': proc.returncode,
               'stdout_tail': proc.stdout[-2000:], 'stderr_tail': proc.stderr[-2000:], 'timeout_sec': timeout}
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode(errors='replace') if isinstance(e.stdout, bytes) else (e.stdout or '')
        stderr = e.stderr.decode(errors='replace') if isinstance(e.stderr, bytes) else (e.stderr or '')
        rec = {'mode': 'daily', 'ok': False, 'returncode': 124,
               'stdout_tail': stdout[-2000:], 'stderr_tail': stderr[-2000:] + f'\nTIMEOUT after {timeout}s',
               'timeout_sec': timeout}
    append_log('closed_loop.log', rec)
    return rec


def call_json(path, timeout=30):
    with urllib.request.urlopen(BASE_URL + path, timeout=timeout) as r:
        return json.loads(r.read().decode())


def run_live(force=False):
    open_now = is_market_open()
    if not force and not open_now:
        rec = {'mode': 'live', 'ok': True, 'skipped': True, 'reason': 'MARKET_CLOSED'}
        append_log('closed_loop.log', rec)
        return rec
    try:
        data = call_json('/api/live-prices', timeout=45)
        rec = {'mode': 'live', 'ok': True, 'market_open': data.get('market_open'),
               'total': data.get('total'), 'monitor_update': data.get('monitor_update'),
               'ledger_count': len(data.get('tradeLedger') or []), 'error': data.get('error')}
    except Exception as e:
        rec = {'mode': 'live', 'ok': False, 'error': str(e)}
    append_log('closed_loop.log', rec)
    return rec


def run_postmarket():
    live = run_live(force=True)
    daily = run_daily()
    rec = {'mode': 'postmarket', 'ok': bool(live.get('ok')) and bool(daily.get('ok')), 'live': live, 'daily': daily}
    append_log('closed_loop.log', rec)
    return rec


def selftest():
    checks = {}
    checks['daily_script_exists'] = DAILY_SCRIPT.exists()
    checks['server_summary'] = call_json('/api/summary', timeout=15)
    checks['logs'] = call_json('/api/logs', timeout=15)
    checks['monitor_state'] = call_json('/api/monitor/state', timeout=15)
    checks['live'] = call_json('/api/live-prices', timeout=45)
    checks['pages'] = {}
    for p in ['/', '/monitor', '/live', '/logs', '/analysis', '/autopsy']:
        try:
            with urllib.request.urlopen(BASE_URL + p, timeout=20) as r:
                body = r.read(200000).decode(errors='ignore')
            checks['pages'][p] = {'ok': True, 'status': r.status, 'len': len(body)}
        except Exception as e:
            checks['pages'][p] = {'ok': False, 'error': str(e)}
    ok = checks['daily_script_exists'] and all(v.get('ok') for v in checks['pages'].values())
    rec = {'mode': 'selftest', 'ok': ok, 'checks': checks}
    (MON / 'closed_loop_selftest.json').write_text(json.dumps(rec, ensure_ascii=False, indent=2))
    append_log('closed_loop.log', {'mode': 'selftest', 'ok': ok})
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['daily', 'live', 'postmarket', 'selftest'])
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()
    if args.mode == 'daily':
        out = run_daily()
    elif args.mode == 'live':
        out = run_live(force=args.force)
    elif args.mode == 'postmarket':
        out = run_postmarket()
    else:
        out = selftest()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(0 if out.get('ok') else 1)


if __name__ == '__main__':
    main()
