#!/usr/bin/env python3
"""Quarantine historical/diagnostic V66 monitor pollution out of production files.

Keeps active legacy OPEN/WATCH_ONLY positions visible for risk monitoring, but removes
closed diagnostic samples and their ledger rows from production review/ledger files.
"""
from __future__ import annotations
import json, shutil, datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
MON = ROOT / 'smc_monitor'
AUDIT = ROOT / 'smc_audit'
STATE = MON / 'positions.json'
REVIEW = MON / 'closed_reviews.json'
LEDGER = MON / 'trade_ledger.json'


def load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return default


def save(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2))


def date_key(v):
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def is_clean(row):
    return row.get('sample_class') == 'PRODUCTION_CLEAN'


def is_diagnostic_closed_position(pos):
    return pos.get('status') == 'CLOSED' and not is_clean(pos)


def is_diagnostic_review(review):
    return not is_clean(review)


def main():
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = MON / 'backups' / f'{ts}_pre_quarantine'
    backup.mkdir(parents=True, exist_ok=True)
    for path in (STATE, REVIEW, LEDGER):
        if path.exists():
            shutil.copy2(path, backup / path.name)

    positions = load(STATE, [])
    reviews = load(REVIEW, [])
    ledger = load(LEDGER, [])

    archived_positions = [p for p in positions if is_diagnostic_closed_position(p)]
    archived_position_ids = {p.get('id') for p in archived_positions if p.get('id')}
    kept_positions = [p for p in positions if not is_diagnostic_closed_position(p)]

    archived_reviews = [r for r in reviews if is_diagnostic_review(r)]
    kept_reviews = [r for r in reviews if not is_diagnostic_review(r)]

    archived_ledger = []
    kept_ledger = []
    for row in ledger:
        row_pos = row.get('position_id')
        diagnostic_by_position = row_pos in archived_position_ids
        diagnostic_by_invalidated = bool(row.get('invalidated'))
        diagnostic_by_review = row.get('sample_class') == 'DIAGNOSTIC_ONLY'
        if diagnostic_by_position or diagnostic_by_invalidated or diagnostic_by_review:
            archived_ledger.append(row)
        else:
            if row.get('sample_class') is None and row.get('source') in ('manual_daily', 'manual'):
                row = dict(row)
                row['sample_class'] = 'LEGACY_ACTIVE_DIAGNOSTIC'
            kept_ledger.append(row)

    archive_dir = MON / 'quarantine' / ts
    archive_dir.mkdir(parents=True, exist_ok=True)
    save(archive_dir / 'positions_diagnostic_closed.json', archived_positions)
    save(archive_dir / 'closed_reviews_diagnostic.json', archived_reviews)
    save(archive_dir / 'trade_ledger_diagnostic.json', archived_ledger)
    save(archive_dir / 'manifest.json', {
        'created_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'backup_dir': str(backup),
        'reason': 'Physical quarantine of historical/diagnostic closed samples so production review metrics only use PRODUCTION_CLEAN rows.',
        'archived_closed_positions': len(archived_positions),
        'archived_reviews': len(archived_reviews),
        'archived_ledger_rows': len(archived_ledger),
        'kept_positions': len(kept_positions),
        'kept_reviews': len(kept_reviews),
        'kept_ledger_rows': len(kept_ledger),
    })

    save(STATE, kept_positions)
    save(REVIEW, kept_reviews)
    save(LEDGER, kept_ledger)

    out = {
        'ok': True,
        'archive_dir': str(archive_dir),
        'backup_dir': str(backup),
        'archived_closed_positions': len(archived_positions),
        'archived_reviews': len(archived_reviews),
        'archived_ledger_rows': len(archived_ledger),
        'kept_positions': len(kept_positions),
        'kept_reviews': len(kept_reviews),
        'kept_ledger_rows': len(kept_ledger),
        'legacy_open_or_watch_kept': sum(1 for p in kept_positions if p.get('status') in ('OPEN', 'WATCH_ONLY') and not is_clean(p)),
    }
    AUDIT.mkdir(parents=True, exist_ok=True)
    save(AUDIT / 'v66_pollution_quarantine.json', out)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
