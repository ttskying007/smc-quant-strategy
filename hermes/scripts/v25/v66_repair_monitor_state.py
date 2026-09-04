#!/usr/bin/env python3
"""One-shot repair for SMC monitor state: quarantine T+1 violations, mark sample classes."""
from __future__ import annotations
import json, shutil, datetime, sys
from pathlib import Path

ROOT = Path('/root/.hermes')
SCRIPTS = ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from smc_monitor_state import load_json, save_json, date_key, STATE, LEDGER, REVIEW, sample_class_for_position, production_entry_gate, live_execution_price, t1_entry_allowed, now_iso

BACKUP_DIR = ROOT / 'smc_monitor/backups' / datetime.datetime.now().strftime('%Y%m%d_%H%M%S')


def backup(path: Path):
    if path.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, BACKUP_DIR / path.name)


def main():
    for p in (STATE, LEDGER, REVIEW):
        backup(p)
    positions = load_json(STATE, [])
    ledger = load_json(LEDGER, [])
    reviews = load_json(REVIEW, [])
    today = datetime.datetime.now().strftime('%Y%m%d')
    repaired_positions = []
    invalidated_ledger = []

    for pos in positions:
        raw = pos.get('raw_pick') or {}
        pick = date_key(pos.get('pick_date') or raw.get('pick_date') or raw.get('select_date'))
        filled = date_key(pos.get('filled_at') or '')
        if pos.get('filled_at') and pick and filled and filled <= pick:
            pos.setdefault('execution_repairs', []).append({
                'at': now_iso(),
                'reason': 'T1_SAME_DAY_FILL_QUARANTINE',
                'old_status': pos.get('status'),
                'old_filled_at': pos.get('filled_at'),
                'old_entry_price': pos.get('entry_price'),
            })
            pos['invalid_execution'] = True
            pos['invalid_reason'] = 'T1_SAME_DAY_FILL'
            # Current OPEN records are re-queued only if today is after the pick date and the live gate accepts now.
            if pos.get('status') == 'OPEN' and t1_entry_allowed(pick, today):
                live_price, live_source = live_execution_price(pos.get('symbol'))
                raw2 = dict(raw)
                raw2.setdefault('symbol', pos.get('symbol'))
                raw2.setdefault('pick_date', pos.get('pick_date'))
                raw2.setdefault('zone_type', pos.get('zone_type'))
                raw2.setdefault('conf_type', pos.get('conf_type'))
                raw2.setdefault('zone_low', pos.get('zone_low'))
                raw2.setdefault('zone_high', pos.get('zone_high'))
                raw2.setdefault('risk_pct', pos.get('risk_pct'))
                gate = production_entry_gate(raw2, exec_price=live_price or pos.get('entry_price'), source=pos.get('source') or 'auto_daily')
                pos['production_gate'] = gate
                pos['entry_zone_relation'] = gate.get('entry_zone_relation')
                pos['entry_zone_distance_pct'] = gate.get('entry_zone_distance_pct')
                if gate.get('action') == 'ACCEPT':
                    pos['status'] = 'NEXT_DAY_PENDING'
                    pos['pending_reason'] = 'T1_VIOLATION_REQUEUED_FOR_VALID_T1_FILL'
                    pos['pending_at'] = now_iso()
                    pos.pop('filled_at', None)
                    pos.pop('filled_from_status', None)
                    pos['created_at'] = pos.get('joined_at') or pos.get('created_at')
                else:
                    pos['status'] = 'WATCH_ONLY'
                    pos['pending_reason'] = 'T1_VIOLATION_GATE_REJECTED'
                    pos['reject_reason'] = ';'.join(gate.get('reasons') or [])
                    pos.pop('filled_at', None)
                    pos.pop('filled_from_status', None)
            else:
                if pos.get('status') != 'CLOSED':
                    pos['status'] = 'WATCH_ONLY'
                    pos['pending_reason'] = 'T1_VIOLATION_QUARANTINED'
                    pos.pop('filled_at', None)
                    pos.pop('filled_from_status', None)
            repaired_positions.append(pos.get('symbol'))
        sc, flags = sample_class_for_position(pos)
        if pos.get('status') == 'NEXT_DAY_PENDING':
            sc, flags = 'PENDING_T1', []
        pos['sample_class'] = sc
        pos['sample_issue_flags'] = flags

    invalid_position_ids = {p.get('id') for p in positions if p.get('invalid_execution')}
    for row in ledger:
        pick = date_key(row.get('pick_date') or row.get('select_date'))
        buy = date_key(row.get('buy_date') or row.get('event_date'))
        if row.get('action') == 'BUY' and ((pick and buy and buy <= pick) or row.get('position_id') in invalid_position_ids):
            row['invalidated'] = True
            row['invalid_reason'] = 'T1_SAME_DAY_BUY'
            row['invalidated_at'] = now_iso()
            invalidated_ledger.append(row.get('symbol'))

    for review in reviews:
        pos = review.get('position') or {}
        sc, flags = sample_class_for_position(pos)
        review['sample_class'] = review.get('sample_class') or sc
        review['sample_issue_flags'] = review.get('sample_issue_flags') or flags
        if 'T1_SAME_DAY_FILL' in flags:
            root = 'T1_EXECUTION_VIOLATION'
        elif any(str(f).startswith('STALE_PICK') or f == 'MANUAL_OR_IMPORTED_SOURCE' for f in flags):
            root = 'HISTORICAL_POLLUTION'
        elif 'MISSING_ZONE' in flags:
            root = 'MISSING_ZONE'
        elif str(pos.get('entry_zone_relation') or '').startswith('BELOW_ZONE'):
            root = 'ZONE_INVALIDATED_BELOW_ENTRY'
        elif str(pos.get('entry_zone_relation') or '').startswith('ABOVE_ZONE'):
            root = 'PRICE_TOO_FAR_ABOVE_ZONE'
        else:
            root = review.get('root_cause') or 'VALID_SIGNAL_FAILED'
        review['root_cause'] = root

    save_json(STATE, positions)
    save_json(LEDGER, ledger)
    save_json(REVIEW, reviews)
    out = {
        'backup_dir': str(BACKUP_DIR),
        'repaired_positions': repaired_positions,
        'invalidated_ledger': invalidated_ledger,
        'positions_total': len(positions),
        'ledger_total': len(ledger),
        'reviews_total': len(reviews),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
