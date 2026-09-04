#!/usr/bin/env python3
"""V526 production controller for the validated V517 daily absorption contract.

The only entry path is: committed current scanner row -> durable pending snapshot
-> the immediately following eligible session's Tencent opening price -> BUY_VALID
-> monitor position. Historical replay rows are never imported.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
MON = ROOT / 'smc_monitor'
V25 = ROOT / 'scripts/v25'
sys.path.insert(0, str(ROOT / 'scripts'))
from smc_monitor_state import ingest_daily_picks, load_positions, update_with_live_results, live_execution_price

REGISTRY = MON / 'production_registry.json'
PENDING = MON / 'v526_pending_orders.json'
STATE = MON / 'v526_live_state.json'
LOCK = MON / 'v526_controller.lock'
V522 = AUD / 'v522_effort_result_release_audit_latest.json'
V519 = AUD / 'v519_daily_effort_result_absorption_frozen_t1_replay_latest.json'
STRATEGY = 'V526_V517_DAILY_EFFORT_RESULT_ABSORPTION'
SCANNER_CONTRACT_VERSION = 'V2_UNCONSUMED_TARGET'


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    tmp.replace(path)


def sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ''


IMMUTABLE_PENDING_KEYS = (
    'symbol', 'ontology', 'scanner_contract_version', 'response_date',
    'swing_idx', 'sweep_idx', 'response_idx', 'sweep_date', 'sweep_low',
    'sweep_high', 'stop', 'target_swing_date', 'target',
    'prior20_volume_rank', 'causal_trace', 'strategy', 'data_epoch_id',
    'expected_execution_date', 'execution_contract', 'execution_authorization',
)


def pending_digest(row: dict) -> str:
    payload = {key: row.get(key) for key in IMMUTABLE_PENDING_KEYS}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def pending_integrity_ok(row: dict) -> bool:
    return bool(row.get('pending_integrity_sha256')) and row.get('pending_integrity_sha256') == pending_digest(row)


def date_key(value: Any) -> str:
    return ''.join(ch for ch in str(value or '') if ch.isdigit())[:8]


def next_weekday(day: str) -> str:
    """Calendar lower bound only; exact exchange-session validation is in market_open()."""
    current = datetime.strptime(day, '%Y%m%d').date()
    while True:
        current += timedelta(days=1)
        if current.weekday() < 5:
            return current.strftime('%Y%m%d')


def record_open_attempt(row: dict, day: str, quote_date: str, state: str) -> None:
    attempts = row.setdefault('execution_attempts', [])
    if not any(x.get('date') == day for x in attempts if isinstance(x, dict)):
        attempts.append({'date': day, 'quote_date': quote_date, 'state': state, 'at': datetime.now().isoformat(timespec='seconds')})


def weekday_dates(start: str, end_exclusive: str) -> list[str]:
    """Weekday lower-bound dates between two YYYYMMDD dates."""
    day = datetime.strptime(start, '%Y%m%d').date()
    end = datetime.strptime(end_exclusive, '%Y%m%d').date()
    dates = []
    while day < end:
        if day.weekday() < 5:
            dates.append(day.strftime('%Y%m%d'))
        day += timedelta(days=1)
    return dates


def only_confirmed_non_sessions_before(row: dict, expected: str, today: str) -> bool:
    """Permit a later weekday only when every earlier weekday was proven closed.

    A stale symbol quote on an open exchange day is not a holiday and must never
    turn into a later fill.
    """
    attempts = {str(x.get('date')): x.get('state') for x in row.get('execution_attempts', []) if isinstance(x, dict)}
    prior = weekday_dates(expected, today)
    return bool(prior) and all(attempts.get(day) == 'NO_EXCHANGE_SESSION' for day in prior)


def quote_prefix(symbol: str) -> str:
    code = ''.join(ch for ch in symbol if ch.isdigit())
    exchange = str(symbol).upper().rsplit('.', 1)[-1]
    return {'SH': 'sh', 'SZ': 'sz', 'BJ': 'bj'}.get(exchange, 'sh' if code.startswith(('6', '9')) else ('bj' if code.startswith(('4', '8')) else 'sz'))


def quote(symbol: str) -> dict[str, Any]:
    code = ''.join(ch for ch in symbol if ch.isdigit())
    prefix = quote_prefix(symbol)
    import urllib.request
    try:
        raw = urllib.request.urlopen(f'http://qt.gtimg.cn/q={prefix}{code}', timeout=8).read().decode('gbk', errors='replace')
        fields = raw.split('"')[1].split('~')
        return {'last': float(fields[3] or 0), 'open': float(fields[5] or 0), 'quote_date': date_key(fields[30]), 'name': fields[1]}
    except Exception:
        return {'last': 0.0, 'open': 0.0, 'quote_date': '', 'name': ''}


def research_ready(release: dict) -> bool:
    replay = load(V519, {})
    return (
        release.get('research_result') == 'RESEARCH_PROMOTABLE'
        and release.get('production_license_granted') is True
        and all((release.get('checks') or {}).values())
        and replay.get('promotion_gate_pass') is True
    )


def execution_authorization(release: dict) -> dict:
    """Freeze only decision-time license facts onto a current scanner row."""
    artifact = Path((release.get('artifacts') or {}).get('out_dir') or '') / 'v522_report.json'
    return {
        'schema': 'V526_PENDING_EXECUTION_AUTHORIZATION_V1',
        'strategy': STRATEGY,
        'licensed': research_ready(release),
        'release_decision': release.get('decision'),
        'release_generated_at': release.get('generated_at'),
        'release_artifact': str(artifact),
        'release_artifact_sha256': sha256_file(artifact),
        'scanner_epoch_id': (release.get('current_scanner') or {}).get('epoch_id'),
    }


def pending_is_authorized(row: dict) -> bool:
    auth = row.get('execution_authorization') or {}
    artifact = Path(str(auth.get('release_artifact') or ''))
    expected_artifact_hash = str(auth.get('release_artifact_sha256') or '')
    return (
        auth.get('schema') == 'V526_PENDING_EXECUTION_AUTHORIZATION_V1'
        and auth.get('strategy') == STRATEGY
        and auth.get('licensed') is True
        and bool(auth.get('scanner_epoch_id'))
        and auth.get('scanner_epoch_id') == row.get('data_epoch_id')
        and pending_integrity_ok(row)
        and (not expected_artifact_hash or sha256_file(artifact) == expected_artifact_hash)
    )


def promote(release: dict) -> dict:
    replay = load(V519, {})
    scan = release.get('current_scanner') or {}
    if not research_ready(release):
        pending = load(PENDING, [])
        authorized_pending = sum(row.get('status') == 'PENDING_NEXT_OPEN' and pending_is_authorized(row) for row in pending)
        # A later aggregate/research gate may freeze *new admissions*, but it
        # cannot retroactively relabel a current-epoch row already authorized at
        # its own decision time. Each row still expires if its exact next-open
        # evidence is missing or fails its precommitted price range.
        save(REGISTRY, {
            'schema_version': 'SMC_PRODUCTION_REGISTRY_V2',
            'generated_at': datetime.now().isoformat(timespec='seconds'),
            'state': 'ADMISSION_FROZEN_PENDING_EXECUTION' if authorized_pending else 'FAIL_CLOSED_REPLAY_GATE_FAILED',
            'production_strategy': STRATEGY if authorized_pending else None,
            'buy_enabled': False,
            'active_buy_valid_count': 0,
            'pending_execution_enabled': authorized_pending > 0,
            'pending_execution_count': authorized_pending,
            'forbidden_fallback': True,
            'reason': replay.get('decision') or release.get('decision') or 'V517_REPLAY_GATE_NOT_PROVEN',
            'data_epoch': {'valid': bool(scan.get('epoch_id')), 'epoch_id': scan.get('epoch_id'), 'market_date': scan.get('market_date'), 'status': 'COMMITTED' if scan.get('epoch_id') else 'UNAVAILABLE'},
            'invariants': {
                'historical_pick_fallback_disabled': True,
                'buy_requires_promoted_current_raw_scanner': True,
                'later_research_gate_only_freezes_new_admissions': True,
                'authorized_pending_requires_exact_next_open': True,
            },
        })
        return {'registry': load(REGISTRY, {}), 'quarantined_legacy_positions': 0,
                'production_write': False, 'state': 'NOOP_FAIL_CLOSED_REPLAY_GATE_FAILED'}
    if not scan.get('epoch_id'):
        save(REGISTRY, {
            'schema_version': 'SMC_PRODUCTION_REGISTRY_V2',
            'generated_at': datetime.now().isoformat(timespec='seconds'),
            'state': 'FAIL_CLOSED_MISSING_COMMITTED_SCANNER_EPOCH',
            'production_strategy': None,
            'buy_enabled': False,
            'active_buy_valid_count': 0,
            'forbidden_fallback': True,
            'reason': 'V522_PRODUCTION_LICENSE_REQUIRES_COMMITTED_SCANNER_EPOCH',
            'invariants': {'historical_pick_fallback_disabled': True, 'buy_requires_promoted_current_raw_scanner': True},
        })
        raise RuntimeError('No committed scanner epoch exists for the licensed production strategy')
    if not scan.get('pending_next_open_count'):
        registry = {
            'schema_version': 'SMC_PRODUCTION_REGISTRY_V2',
            'generated_at': datetime.now().isoformat(timespec='seconds'),
            'state': 'LIVE_READY_NO_CURRENT_SIGNAL',
            'production_strategy': STRATEGY,
            'shadow_challenger': None,
            'buy_enabled': True,
            'active_buy_valid_count': 0,
            'forbidden_fallback': True,
            'reason': 'V517_PRODUCTION_LICENSED__NO_CURRENT_PENDING_NEXT_OPEN_SIGNAL',
            'data_epoch': {'valid': True, 'epoch_id': scan.get('epoch_id'), 'market_date': scan.get('market_date'), 'status': 'COMMITTED'},
            'lineages': {'V517': {'status': 'PRODUCTION_BUY_LICENSED_NO_CURRENT_SIGNAL', 'buy_enabled': True, 'release': release.get('decision')}},
            'invariants': {
                'historical_pick_fallback_disabled': True,
                'buy_requires_promoted_current_raw_scanner': True,
                'entry_only_from_durable_pending_snapshot': True,
                'entry_only_at_next_session_open': True,
                't_plus_1_exit_required': True,
            },
        }
        save(REGISTRY, registry)
        return {'registry': registry, 'quarantined_legacy_positions': 0}
    old = load(REGISTRY, {})
    # Legacy V66 positions were created by a rejected lineage. Quarantine them once;
    # live monitoring must not mix them with V526 positions.
    positions = load(MON / 'positions.json', [])
    legacy = [p for p in positions if str((p.get('raw_pick') or {}).get('engine') or '').startswith('V526') is False]
    if legacy:
        archive = MON / 'quarantine' / f'v526_pre_promotion_legacy_positions_{datetime.now():%Y%m%d_%H%M%S}.json'
        save(archive, legacy)
        save(MON / 'positions.json', [p for p in positions if p not in legacy])
    scan = release.get('current_scanner') or {}
    registry = {
        'schema_version': 'SMC_PRODUCTION_REGISTRY_V2',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'state': 'LIVE_READY',
        'production_strategy': STRATEGY,
        'shadow_challenger': None,
        'buy_enabled': True,
        'active_buy_valid_count': old.get('active_buy_valid_count', 0) if old.get('production_strategy') == STRATEGY else 0,
        'forbidden_fallback': True,
        'data_epoch': {'valid': bool(scan.get('epoch_id')), 'epoch_id': scan.get('epoch_id'), 'market_date': scan.get('market_date'), 'status': 'COMMITTED'},
        'lineages': {'V517': {'status': 'PROMOTED_CURRENT_RAW_SCANNER', 'buy_enabled': True, 'release': release.get('decision')}},
        'invariants': {
            'historical_pick_fallback_disabled': True,
            'buy_requires_promoted_current_raw_scanner': True,
            'entry_only_from_durable_pending_snapshot': True,
            'entry_only_at_next_session_open': True,
            't_plus_1_exit_required': True,
        },
    }
    save(REGISTRY, registry)
    return {'registry': registry, 'quarantined_legacy_positions': len(legacy)}


def post_close() -> dict:
    release = load(V522, {})
    promotion = promote(release)
    admissions_open = research_ready(release)
    scan = release.get('current_scanner') or {}
    pending = load(PENDING, [])
    superseded = 0
    for old_row in pending:
        if old_row.get('status') == 'PENDING_NEXT_OPEN' and old_row.get('scanner_contract_version') != SCANNER_CONTRACT_VERSION:
            old_row['status'] = 'EXPIRED_SCANNER_CONTRACT_SUPERSEDED'
            old_row['closed_at'] = datetime.now().isoformat(timespec='seconds')
            superseded += 1
    existing = {(x.get('symbol'), x.get('response_date')) for x in pending if x.get('status') == 'PENDING_NEXT_OPEN' and x.get('scanner_contract_version') == SCANNER_CONTRACT_VERSION}
    created = []
    for row in (scan.get('pending_rows') or []) if admissions_open else []:
        key = (row.get('symbol'), row.get('response_date'))
        if key in existing:
            continue
        item = {
            **row,
            'status': 'PENDING_NEXT_OPEN',
            'strategy': STRATEGY,
            'data_epoch_id': scan.get('epoch_id'),
            # This is a calendar lower bound, not an exchange-calendar assertion.
            # market_open() accepts only the first proven fresh exchange quote.
            'expected_execution_date': next_weekday(date_key(row.get('response_date'))),
            'execution_contract': 'FIRST_ELIGIBLE_EXCHANGE_SESSION_OPEN_AFTER_RESPONSE',
            'execution_authorization': execution_authorization(release),
            'execution_attempts': [],
            'created_at': datetime.now().isoformat(timespec='seconds'),
        }
        item['pending_integrity_sha256'] = pending_digest(item)
        created.append(item)
    pending.extend(created)
    save(PENDING, pending)
    result = {'ok': True, 'mode': 'post-close', 'market_date': scan.get('market_date'), 'new_admissions_open': admissions_open, 'created_pending': len(created), 'superseded_pending': superseded, 'pending_total': sum(x.get('status') == 'PENDING_NEXT_OPEN' for x in pending), **promotion}
    save(STATE, {**result, 'generated_at': datetime.now().isoformat(timespec='seconds')})
    return result


def market_open() -> dict:
    registry = load(REGISTRY, {})
    pending = load(PENDING, [])
    execution_window_open = (
        registry.get('production_strategy') == STRATEGY
        and (registry.get('buy_enabled') is True or registry.get('pending_execution_enabled') is True)
        and any(row.get('status') == 'PENDING_NEXT_OPEN' for row in pending)
    )
    if not execution_window_open:
        result = {'ok': True, 'mode': 'market-open', 'state': 'NOOP_FAIL_CLOSED_NO_ACTIVE_V526_STRATEGY', 'production_state': registry.get('state'), 'executed': [], 'rejected': [], 'open_positions': 0}
        save(STATE, {**result, 'generated_at': datetime.now().isoformat(timespec='seconds')})
        return result
    today = datetime.now().strftime('%Y%m%d')
    executed, rejected = [], []
    for row in pending:
        if row.get('status') != 'PENDING_NEXT_OPEN':
            continue
        if not pending_is_authorized(row):
            row['status'] = 'REJECTED_MISSING_DECISION_TIME_AUTHORIZATION'
            row['closed_at'] = datetime.now().isoformat(timespec='seconds')
            rejected.append({'symbol': row.get('symbol'), 'reason': 'MISSING_DECISION_TIME_AUTHORIZATION'})
            continue
        expected = date_key(row.get('expected_execution_date'))
        if not expected:
            row['status'] = 'REJECTED_MISSING_EXECUTION_LOWER_BOUND'
            row['closed_at'] = datetime.now().isoformat(timespec='seconds')
            rejected.append({'symbol': row.get('symbol'), 'reason': 'MISSING_EXECUTION_LOWER_BOUND'})
            continue
        if today < expected:
            continue
        session = quote('000001.SH')
        if session['quote_date'] != today:
            record_open_attempt(row, today, session['quote_date'], 'NO_EXCHANGE_SESSION')
            continue
        if today > expected and not only_confirmed_non_sessions_before(row, expected, today):
            row['status'] = 'EXPIRED_MISSED_EXACT_NEXT_SESSION_OPEN'
            row['closed_at'] = datetime.now().isoformat(timespec='seconds')
            rejected.append({'symbol': row.get('symbol'), 'reason': 'MISSED_EXACT_NEXT_SESSION_OPEN', 'expected_execution_date': expected})
            continue
        q = quote(row['symbol'])
        # The index quote has already proved that this is an exchange session.
        # A stale symbol quote is therefore a source/suspension failure, not a
        # holiday; it may retry only inside this exact opening session.
        if q['quote_date'] != today:
            record_open_attempt(row, today, q['quote_date'], 'NO_FRESH_SYMBOL_QUOTE')
            continue
        opening, stop, target = q['open'], float(row['stop']), float(row['target'])
        if opening <= 0:
            record_open_attempt(row, today, q['quote_date'], 'FRESH_QUOTE_WITHOUT_VALID_OPEN')
            row['status'] = 'REJECTED_INVALID_OPEN_QUOTE'
            row['closed_at'] = datetime.now().isoformat(timespec='seconds')
            rejected.append({'symbol': row['symbol'], 'reason': 'INVALID_OPEN_QUOTE', 'open': opening})
            continue
        if not (opening > stop and opening < target):
            row['status'] = 'REJECTED_OPEN_OUTSIDE_STRUCTURAL_RANGE'
            row['closed_at'] = datetime.now().isoformat(timespec='seconds')
            rejected.append({'symbol': row['symbol'], 'reason': 'OPEN_NOT_BETWEEN_STOP_AND_TARGET', 'open': opening, 'stop': stop, 'target': target})
            continue
        risk_pct = round((opening - stop) / opening * 100, 4)
        pick = {
            'symbol': row['symbol'], 'name': q['name'], 'engine': STRATEGY, 'production_strategy': STRATEGY,
            'pick_scope': 'ACTIVE_CANDIDATE', 'is_active_pick': True, 'live_guard_status': 'BUY_VALID',
            'trade_action': 'BUY', 'buy_enabled': True, 'tradable': True, 'current_raw_scanner_source': True,
            'semantic_oracle_pass': True, 'chronology_pass': True, 'strict_t1_contract': True,
            'data_epoch_id': row['data_epoch_id'], 'pick_date': row['response_date'], 'select_date': row['response_date'],
            'signal_date': row['response_date'], 'entry_date': today, 'entry_price': opening, 'price': opening,
            'sl': stop, 'tp1': target, 'risk_pct': risk_pct, 'zone_low': row['sweep_low'], 'zone_high': row['sweep_high'],
            'zone_type': 'HIGH_VOLUME_SSL_RECLAIM', 'conf_type': 'RESPONSE_CLOSE_BREAKS_SWEEP_HIGH',
            'entry_type': 'FOLLOWING_SESSION_OPEN_T1', 'entry_mode': 'FOLLOWING_SESSION_OPEN_T1',
            'zone_idx': row.get('sweep_idx'), 'conf_index': row.get('response_idx'),
            'seq': 'confirmed_swing_low -> high_volume_SSL_sweep_reclaim -> response_break -> next_open',
            'causal_trace': row.get('causal_trace', ''), 'sweep_date': row.get('sweep_date'), 'response_date': row.get('response_date'),
            'target_swing_date': row.get('target_swing_date'), 'execution_open': opening,
        }
        result = ingest_daily_picks([pick], source='v526_open')
        row['status'] = 'BUY_SUBMITTED' if result.get('buy_added') else 'REJECTED_MONITOR_GATE'
        row['execution_result'] = result
        row['closed_at'] = datetime.now().isoformat(timespec='seconds')
        executed.append({'symbol': row['symbol'], 'open': opening, 'result': result})
    save(PENDING, pending)
    registry['active_buy_valid_count'] = sum(1 for p in load_positions() if str((p.get('raw_pick') or {}).get('engine') or '') == STRATEGY and p.get('status') == 'OPEN')
    registry['generated_at'] = datetime.now().isoformat(timespec='seconds')
    save(REGISTRY, registry)
    result = {'ok': True, 'mode': 'market-open', 'date': today, 'executed': executed, 'rejected': rejected, 'open_positions': registry['active_buy_valid_count']}
    save(STATE, {**result, 'generated_at': datetime.now().isoformat(timespec='seconds')})
    return result


def monitor() -> dict:
    positions = [p for p in load_positions() if str((p.get('raw_pick') or {}).get('engine') or '') == STRATEGY and p.get('status') == 'OPEN']
    live = []
    for pos in positions:
        price, source = live_execution_price(pos.get('symbol'))
        if price <= 0:
            continue
        status = 'SL_HIT' if price <= float(pos.get('sl_price') or 0) else ('TP_HIT' if price >= float(pos.get('tp1_price') or 0) else 'HOLDING')
        live.append({'symbol': pos.get('symbol'), 'currentPrice': price, 'status': status, 'source': source})
    result = update_with_live_results(live)
    result.update({'ok': True, 'mode': 'monitor', 'checked': len(live), 'generated_at': datetime.now().isoformat(timespec='seconds')})
    save(STATE, result)
    return result


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if mode not in {'post-close', 'market-open', 'monitor'}:
        print(json.dumps(load(STATE, {}), ensure_ascii=False, indent=2))
        return
    import fcntl
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open('a+') as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'ok': True, 'mode': mode, 'state': 'NOOP_CONTROLLER_LOCKED'}, ensure_ascii=False, indent=2))
            return
        result = post_close() if mode == 'post-close' else market_open() if mode == 'market-open' else monitor()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
