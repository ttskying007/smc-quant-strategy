#!/usr/bin/env python3
"""Repair monitor state rows that violated A-share T+1 same-day sell rule."""
from __future__ import annotations
import json, pathlib, shutil, datetime

MON = pathlib.Path('/root/.hermes/smc_monitor')
STAMP = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')


def dk(v):
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def load(name):
    p = MON / name
    return json.loads(p.read_text()) if p.exists() else []


def save(name, rows):
    p = MON / name
    p.write_text(json.dumps(rows, ensure_ascii=False, indent=2))


def backup(name):
    p = MON / name
    if p.exists():
        b = MON / f'{name}.{STAMP}.bak'
        shutil.copy2(p, b)
        return str(b)
    return ''


def main():
    backups = {name: backup(name) for name in ['positions.json', 'trade_ledger.json', 'closed_reviews.json']}

    positions = load('positions.json')
    repaired_positions = []
    violation_ids = set()
    for pos in positions:
        if pos.get('status') == 'CLOSED' and dk(pos.get('created_at')) and dk(pos.get('created_at')) == dk(pos.get('closed_at')):
            violation_ids.add(pos.get('id'))
            for key in ['closed_at', 'close_reason', 'exit_price', 'review_id']:
                pos.pop(key, None)
            pos['status'] = 'OPEN'
            pos['t1_repair_note'] = f"same-day close removed at {datetime.datetime.now().isoformat(timespec='seconds')}"
            repaired_positions.append(pos.get('symbol'))
    save('positions.json', positions)

    ledger = load('trade_ledger.json')
    before_ledger = len(ledger)
    ledger = [r for r in ledger if not (r.get('action') == 'SELL' and (r.get('position_id') in violation_ids or (dk(r.get('buy_date')) and dk(r.get('buy_date')) == dk(r.get('sell_date')))))]
    save('trade_ledger.json', ledger)

    reviews = load('closed_reviews.json')
    before_reviews = len(reviews)
    reviews = [r for r in reviews if not (r.get('id') in violation_ids or (r.get('position') or {}).get('id') in violation_ids)]
    save('closed_reviews.json', reviews)

    out = {
        'backups': backups,
        'reopened_positions': len(repaired_positions),
        'symbols': repaired_positions,
        'removed_sell_ledger': before_ledger - len(ledger),
        'removed_reviews': before_reviews - len(reviews),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
