#!/usr/bin/env python3
"""Audit V88 executable-entry contract: no zone-limit fill may be outside its entry-day range."""
import json
from pathlib import Path

ROOT = Path('/root/.hermes')
TRADES = ROOT / 'smc_opt_v88_production_contract' / 'v88_trades.json'


def dk(v):
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def load_kline(symbol):
    stem = str(symbol).replace('.', '_')
    for suffix in ('daily_750', 'daily_300'):
        p = ROOT / 'kline_cache' / f'{stem}_{suffix}.json'
        if p.exists():
            return json.loads(p.read_text())
    return []


def test_v88_entries_are_executable_on_entry_day():
    rows = json.loads(TRADES.read_text())
    bad = []
    for r in rows:
        ks = load_kline(r.get('symbol'))
        by_date = {dk(b.get('t') or b.get('date')): b for b in ks}
        b = by_date.get(dk(r.get('entry_date')))
        if not b:
            continue
        ep = float(r.get('entry_price') or 0)
        lo = float(b.get('l') or 0)
        hi = float(b.get('h') or 0)
        if ep and lo and hi and not (lo * 0.999 <= ep <= hi * 1.001):
            bad.append((r.get('symbol'), r.get('entry_date'), ep, lo, hi, r.get('entry_mode')))
    assert not bad, f'non-executable V88 entries: {len(bad)} sample={bad[:5]}'


if __name__ == '__main__':
    test_v88_entries_are_executable_on_entry_day()
    print('V88 executable-entry audit PASS')
