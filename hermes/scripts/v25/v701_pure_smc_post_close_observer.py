#!/usr/bin/env python3
"""Refresh and run the current V700 pure-SMC scanner.

This observer owns current candidate supply while V699 is being audited. It is
explicitly no-write: it never changes the production registry, watchlist,
positions, pending orders, or trade ledger.
"""
from __future__ import annotations
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
V25 = ROOT / 'scripts/v25'
AUD = ROOT / 'smc_audit'
MON = ROOT / 'smc_monitor'
LATEST = AUD / 'v701_pure_smc_post_close_observer_latest.json'


def run(cmd: list[str], timeout: int) -> dict:
    started = datetime.now()
    p = subprocess.run(cmd, cwd=str(V25), text=True, capture_output=True, timeout=timeout)
    return {'command': ' '.join(cmd), 'returncode': p.returncode,
            'duration_sec': round((datetime.now() - started).total_seconds(), 1),
            'stdout_tail': p.stdout[-1200:], 'stderr_tail': p.stderr[-1200:]}


def load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def main() -> None:
    refresh = run([sys.executable, str(V25 / 'refresh_daily_750.py'), '--workers', '20'], 900)
    summary = load(MON / 'kline_refresh_latest.json')
    committed = refresh['returncode'] == 0 and summary.get('gate_pass') is True and summary.get('epoch_status') == 'COMMITTED'
    scan = run([sys.executable, str(V25 / 'v700_pure_smc_ssl_reclaim_current_scanner.py')], 180) if committed else None
    scanner = load(AUD / 'v700_pure_smc_ssl_reclaim_current_scanner_latest.json')
    report = {
        'version': 'V701_PURE_SMC_POST_CLOSE_OBSERVER_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_write': False, 'watchlist_write': False,
        'position_write': False, 'registry_write': False,
        'refresh': {'returncode': refresh['returncode'], 'duration_sec': refresh['duration_sec'],
                    'gate_pass': summary.get('gate_pass'), 'epoch_status': summary.get('epoch_status'),
                    'epoch_id': summary.get('epoch_id'), 'market_date': summary.get('observed_latest_date')},
        'scanner': {'returncode': scan['returncode'] if scan else None,
                    'generated_at': scanner.get('generated_at'), 'epoch_id': scanner.get('epoch_id'),
                    'market_date': scanner.get('market_date'),
                    'pending_next_open_count': scanner.get('pending_next_open_count', 0),
                    'buy_valid_count': scanner.get('buy_valid_count', 0),
                    'decision': scanner.get('decision'),
                    'funnel': ((scanner.get('diagnostic_funnel') or {}).get('counts') or {}),
                    'rows': scanner.get('rows', [])},
        'decision': 'V701_CURRENT_SCANNER_REFRESHED_NO_PRODUCTION_WRITE' if committed else 'V701_REFRESH_NOT_COMMITTED_SCANNER_NOT_RUN',
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
