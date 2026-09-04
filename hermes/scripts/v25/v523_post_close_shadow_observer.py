#!/usr/bin/env python3
"""Scheduled V517 production controller.

Refreshes the daily epoch, builds the current scanner/release snapshot, preserves
a read-only shadow audit of that snapshot, then runs the licensed V526 controller. V526 may only persist a current committed
scanner row as PENDING_NEXT_OPEN; it never imports historical replay trades.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
V25 = ROOT / 'scripts/v25'
MON = ROOT / 'smc_monitor'


def load(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def run(command: list[str], timeout: int) -> dict:
    started = datetime.now()
    proc = subprocess.run(command, cwd=str(V25), text=True, capture_output=True, timeout=timeout)
    return {
        'command': ' '.join(command),
        'returncode': proc.returncode,
        'duration_sec': round((datetime.now() - started).total_seconds(), 1),
        'stdout_tail': proc.stdout[-1200:],
        'stderr_tail': proc.stderr[-1200:],
    }


def save_scheduler_status(status: dict) -> None:
    """Keep the displayed scheduler state aligned with the actual cron outcome."""
    path = MON / 'internal_scheduler_state.json'
    state = load(path, {})
    job = (state.setdefault('jobs', {}).setdefault('v517_post_close_observer', {}))
    job.update(status)
    state['generated_at'] = datetime.now().isoformat(timespec='seconds')
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    tmp.replace(path)


def main() -> None:
    refresh = run([sys.executable, str(V25 / 'refresh_daily_750.py'), '--workers', '20'], 900)
    refresh_summary = load(MON / 'kline_refresh_latest.json', {})
    refresh_ok = refresh['returncode'] == 0 and (refresh_summary.get('gate_pass') is True) and refresh_summary.get('epoch_status') == 'COMMITTED'
    if not refresh_ok:
        result = {
            'version': 'V523_POST_CLOSE_SHADOW_OBSERVER',
            'ok': False,
            'state': 'FAIL_CLOSED_REFRESH_NOT_COMMITTED',
            'refresh_returncode': refresh['returncode'],
            'refresh_gate_pass': refresh_summary.get('gate_pass'),
            'refresh_epoch_status': refresh_summary.get('epoch_status'),
            'observed_latest_date': refresh_summary.get('observed_latest_date'),
            'current_date_coverage_pct': refresh_summary.get('current_date_coverage_pct'),
            'production_write': False,
        }
        save_scheduler_status({
            'last_verified_market_date': refresh_summary.get('observed_latest_date') or '',
            'last_verified_epoch_id': refresh_summary.get('epoch_id') or '',
            'last_verified_outcome': result['state'],
            'last_verified_pending_next_open_count': 0,
            'last_verified_release_state': 'NOT_RUN',
            'last_verified_production_license_state': 'NOT_RUN',
            'last_verified_pipeline_ok': False,
            'last_verified_at': datetime.now().isoformat(timespec='seconds'),
            'last_failure': result,
        })
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(1)
    scan = run([sys.executable, str(V25 / 'v521_daily_effort_result_absorption_scanner_time_dry_run.py')], 180)
    release = run([sys.executable, str(V25 / 'v522_effort_result_release_audit.py')], 120)
    shadow = run([sys.executable, str(V25 / 'v523_effort_result_pending_next_open_shadow.py')], 120)
    production = run([sys.executable, str(V25 / 'v526_v517_live_execution.py'), 'post-close'], 120)
    report = load(ROOT / 'smc_audit/v523_effort_result_pending_next_open_shadow_latest.json', {})
    scanner = load(ROOT / 'smc_audit/v521_daily_effort_result_absorption_scanner_time_dry_run_latest.json', {})
    release_report = load(ROOT / 'smc_audit/v522_effort_result_release_audit_latest.json', {})
    try:
        production_result = json.loads(production['stdout_tail'])
    except (TypeError, json.JSONDecodeError):
        production_result = {}
    result = {
        'version': 'V523_POST_CLOSE_SHADOW_OBSERVER',
        'ok': shadow['returncode'] == 0 and scan['returncode'] == 0 and release['returncode'] == 0 and production['returncode'] == 0,
        'state': report.get('decision'),
        'epoch': report.get('epoch'),
        'validations': report.get('validations'),
        'next_session_pending_count': scanner.get('pending_next_open_count'),
        'next_session_release_state': release_report.get('live_release_state'),
        'production_license_state': release_report.get('production_license_state'),
        'v526_production_controller_returncode': production['returncode'],
        'v526_production_controller_stdout': production['stdout_tail'],
        'v526_production_controller_stderr': production['stderr_tail'],
        'production_write': production_result.get('production_write') is True,
        'watchlist_write': False,
        'frontend_write': False,
        'refresh_duration_sec': refresh['duration_sec'],
        'shadow_duration_sec': shadow['duration_sec'],
        'scan_duration_sec': scan['duration_sec'],
        'release_duration_sec': release['duration_sec'],
    }
    epoch = result['epoch'] or {}
    save_scheduler_status({
        'last_verified_market_date': epoch.get('market_date') or scanner.get('market_date') or '',
        'last_verified_epoch_id': epoch.get('epoch_id') or scanner.get('epoch_id') or '',
        'last_verified_outcome': result['state'] or 'UNKNOWN',
        'last_verified_pending_next_open_count': result['next_session_pending_count'] or 0,
        'last_verified_release_state': result['next_session_release_state'] or 'UNKNOWN',
        'last_verified_production_license_state': result['production_license_state'] or 'UNKNOWN',
        'last_verified_pipeline_ok': result['ok'],
        'last_verified_at': datetime.now().isoformat(timespec='seconds'),
        'last_failure': None if result['ok'] else {
            'scan_returncode': scan['returncode'], 'release_returncode': release['returncode'],
            'shadow_returncode': shadow['returncode'], 'v526_returncode': production['returncode'],
            'v526_stderr_tail': production['stderr_tail'],
        },
    })
    print(json.dumps(result, ensure_ascii=False))
    if not result['ok']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
