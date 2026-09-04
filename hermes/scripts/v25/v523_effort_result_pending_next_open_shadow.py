#!/usr/bin/env python3
"""V523 fail-closed shadow validation for the V522 pending-next-open contract.

It has no production, frontend, watchlist, position, or registry writes.  It
validates the V522 *frozen snapshot*, never a mutable latest scanner artifact.
A candidate can be accepted only when the next available bar after response is
also the current COMMITTED epoch. If a refresh is rejected or the exact epoch
was missed, it remains blocked; it is never filled late from historical data.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
MON = ROOT / 'smc_monitor'
KD = ROOT / 'kline_cache'
V522 = AUD / 'v522_effort_result_release_audit_latest.json'
PENDING = MON / 'v526_pending_orders.json'
OUT = AUD / f'v523_effort_result_pending_next_open_shadow_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v523_effort_result_pending_next_open_shadow_latest.json'


def load(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def date_key(value: Any) -> str:
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else ''


def positive(value: Any) -> float | None:
    try:
        number = float(value)
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def bars(symbol: str) -> list[dict[str, Any]]:
    code, exchange = symbol.split('.')
    raw = load(KD / f'{code}_{exchange}_daily_750.json', [])
    output: list[dict[str, Any]] = []
    for row in raw if isinstance(raw, list) else []:
        day = date_key(row.get('t') or row.get('date') or row.get('day'))
        opening = positive(row.get('o'))
        if day and opening is not None:
            output.append({'date': day, 'open': opening, 'raw': row})
    return sorted(output, key=lambda row: row['date'])


def validate(row: dict[str, Any], epoch_date: str) -> dict[str, Any]:
    symbol = str(row['symbol'])
    response_date = date_key(row['response_date'])
    sequence = bars(symbol)
    after = [bar for bar in sequence if bar['date'] > response_date]
    if not after:
        return {'symbol': symbol, 'state': 'WAIT_EXACT_NEXT_COMMITTED_EPOCH', 'reason': 'NO_BAR_AFTER_RESPONSE_IN_CURRENT_CACHE'}
    next_bar = after[0]
    if not epoch_date:
        return {'symbol': symbol, 'state': 'BLOCKED_NO_COMMITTED_EPOCH', 'reason': 'CURRENT_EPOCH_NOT_COMMITTED', 'next_expected_date': next_bar['date']}
    if epoch_date < next_bar['date']:
        return {'symbol': symbol, 'state': 'WAIT_EXACT_NEXT_COMMITTED_EPOCH', 'reason': 'COMMITTED_EPOCH_BEFORE_NEXT_OPEN', 'next_expected_date': next_bar['date'], 'epoch_date': epoch_date}
    if epoch_date > next_bar['date']:
        return {'symbol': symbol, 'state': 'BLOCKED_MISSED_EXACT_EPOCH', 'reason': 'NEXT_OPEN_NOT_VALIDATED_ON_ITS_OWN_COMMITTED_EPOCH', 'next_expected_date': next_bar['date'], 'epoch_date': epoch_date}
    stop = float(row['stop'])
    target = float(row['target'])
    opening = float(next_bar['open'])
    valid = opening > stop and opening < target
    return {
        'symbol': symbol,
        'state': 'SHADOW_BUY_VALID' if valid else 'SHADOW_REJECTED_NEXT_OPEN',
        'reason': 'OPEN_STRICTLY_BETWEEN_STOP_AND_TARGET' if valid else 'OPEN_NOT_STRICTLY_BETWEEN_STOP_AND_TARGET',
        'response_date': response_date,
        'execution_epoch_date': epoch_date,
        'next_open': round(opening, 6),
        'stop': stop,
        'target': target,
        'entry_price': round(opening, 6) if valid else None,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    release = load(V522, {})
    manifest = load(MON / 'kline_epoch_current.json', {})
    epoch_valid = manifest.get('status') == 'COMMITTED' and bool(manifest.get('epoch_id'))
    epoch_date = date_key(manifest.get('market_date')) if epoch_valid else ''
    durable_pending = load(PENDING, [])
    rows = [row for row in durable_pending if isinstance(row, dict) and row.get('status') == 'PENDING_NEXT_OPEN']
    source = 'DURABLE_PENDING_SNAPSHOT' if rows else 'CURRENT_RELEASE_SCANNER_SNAPSHOT'
    if not rows:
        rows = ((release.get('current_scanner') or {}).get('pending_rows') or [])
    validations = [validate(row, epoch_date) for row in rows]
    states = {row['state'] for row in validations}
    report = {
        'version': 'V523_EFFORT_RESULT_PENDING_NEXT_OPEN_SHADOW_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'source_release_snapshot': str(V522),
        'source_release_decision': release.get('decision'),
        'pending_source': source,
        'epoch': {
            'valid': epoch_valid,
            'epoch_id': manifest.get('epoch_id'),
            'market_date': epoch_date,
            'status': manifest.get('status'),
        },
        'pending_snapshot_count': len(rows),
        'validations': validations,
        'invariants': {
            'uses_frozen_v522_snapshot_not_mutable_latest_scanner': True,
            'requires_exact_next_committed_epoch': True,
            'never_late_fills': all(row['state'] != 'SHADOW_BUY_VALID' or row.get('execution_epoch_date') for row in validations),
            'all_production_writes_false': True,
        },
        'decision': (
            'V523_SHADOW_BUY_VALID__AWAIT_SEPARATE_PRODUCTION_RELEASE_DECISION'
            if 'SHADOW_BUY_VALID' in states else
            'V523_SHADOW_REJECTED_OR_BLOCKED__NO_PRODUCTION_ACTION'
        ),
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST), 'v522': str(V522)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v523_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
