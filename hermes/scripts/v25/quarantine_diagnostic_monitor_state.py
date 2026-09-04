#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

MON = Path('/root/.hermes/smc_monitor')
STAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
QUAR = MON / 'quarantine' / STAMP
QUAR.mkdir(parents=True, exist_ok=True)


def load(p, default):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return default


def save(p, data):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(data, ensure_ascii=False, indent=2))


def quarantine_file(name, keep_fn):
    path = MON / name
    rows = load(path, [])
    if path.exists():
        shutil.copy2(path, QUAR / f'{name}.bak')
    keep = []
    diag = []
    for r in rows:
        if keep_fn(r):
            keep.append(r)
        else:
            rr = dict(r)
            rr['quarantined_at'] = STAMP
            rr['quarantine_reason'] = rr.get('sample_class') or rr.get('root_cause') or 'DIAGNOSTIC_ONLY_OR_HISTORICAL_POLLUTION'
            diag.append(rr)
    save(path, keep)
    save(QUAR / name, diag)
    return {'file': str(path), 'before': len(rows), 'kept': len(keep), 'quarantined': len(diag), 'backup': str(QUAR / f'{name}.bak'), 'quarantine': str(QUAR / name)}


def is_clean_position(r):
    return r.get('sample_class') in ('PRODUCTION_CLEAN', 'PENDING_T1') or r.get('status') == 'NEXT_DAY_PENDING'


def is_clean_review(r):
    return r.get('sample_class') == 'PRODUCTION_CLEAN'


def is_clean_ledger(r):
    return r.get('sample_class') == 'PRODUCTION_CLEAN'


def main():
    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'stamp': STAMP,
        'positions': quarantine_file('positions.json', is_clean_position),
        'closed_reviews': quarantine_file('closed_reviews.json', is_clean_review),
        'trade_ledger': quarantine_file('trade_ledger.json', is_clean_ledger),
    }
    save(QUAR / 'quarantine_report.json', report)
    save(MON / 'quarantine_latest.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
