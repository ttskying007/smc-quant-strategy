#!/usr/bin/env python3
"""V370: no-write source audit for Baostock 60-minute A-share history.

Validates source availability and OHLCV completeness only. It never generates
signals, trades, performance, production files, watchlists, or frontend data.
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import baostock as bs

ROOT = Path('/root/.hermes')
KCACHE = ROOT / 'kline_cache'
AUDIT = ROOT / 'smc_audit'
START, END = '2023-01-01', '2026-07-10'
SLOTS = {'103000000', '113000000', '140000000', '150000000'}
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v370_baostock_m60_full_source_audit_no_write_{TS}'
LATEST = AUDIT / 'v370_baostock_m60_full_source_audit_latest.json'


def universe() -> list[tuple[str, str]]:
    out = []
    for p in KCACHE.glob('*_daily_750.json'):
        m = re.fullmatch(r'(\d+)_(SH|SZ)_daily_750\.json', p.name)
        if m:
            out.append((m.group(1), m.group(2)))
    return sorted(set(out))


def norm_date(s: str) -> str:
    return ''.join(c for c in str(s) if c.isdigit())[:8]


def fetch(code: str, exch: str) -> dict:
    sym = ('sh.' if exch == 'SH' else 'sz.') + code
    q = bs.query_history_k_data_plus(
        sym, 'date,time,open,high,low,close,volume,amount,adjustflag',
        start_date=START, end_date=END, frequency='60', adjustflag='2')
    rows = []
    while q.error_code == '0' and q.next():
        rows.append(q.get_row_data())
    days = Counter(x[0] for x in rows)
    slots = Counter(x[1][-9:] for x in rows)
    year_days = Counter(d[:4] for d in days)
    bad_slot = sum(n for s, n in slots.items() if s not in SLOTS)
    bad_day = sum(1 for n in days.values() if n != 4)
    return {
        'symbol': f'{code}.{exch}', 'baostock_code': sym,
        'status': q.error_code, 'message': q.error_msg,
        'bars': len(rows), 'days': len(days), 'year_days': dict(year_days),
        'first': rows[0][1] if rows else '', 'last': rows[-1][1] if rows else '',
        'bad_slot_bars': bad_slot, 'bad_day_count': bad_day,
        'slot_counts': dict(slots),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    symbols = universe()
    login = bs.login()
    if login.error_code != '0':
        raise RuntimeError(f'baostock login failed: {login.error_code} {login.error_msg}')
    rows, failures = [], []
    t0 = time.time()
    try:
        for i, (code, exch) in enumerate(symbols, 1):
            item = fetch(code, exch)
            rows.append(item)
            bad = item['status'] != '0' or not item['bars'] or item['bad_slot_bars'] or item['bad_day_count']
            if bad and len(failures) < 500:
                failures.append(item)
            if i % 100 == 0:
                print(json.dumps({'progress': i, 'total': len(symbols), 'elapsed_s': round(time.time()-t0, 1), 'bad': len(failures)}, ensure_ascii=False), flush=True)
    finally:
        bs.logout()
    years = ('2023', '2024', '2025', '2026')
    per_year = {y: sum(1 for r in rows if int(r['year_days'].get(y, 0)) > 0) for y in years}
    hard_fail = [r for r in rows if r['status'] != '0' or not r['bars'] or r['bad_slot_bars'] or r['bad_day_count']]
    report = {
        'version': 'V370_BAOSTOCK_M60_FULL_SOURCE_AUDIT_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source': 'baostock query_history_k_data_plus frequency=60 adjustflag=2',
        'range': {'start': START, 'end': END, 'expected_slots': sorted(SLOTS)},
        'universe': {'symbols': len(symbols), 'exchange_counts': dict(Counter(exch for _, exch in symbols))},
        'coverage': {'per_year_symbols_with_bars': per_year, 'all_year_symbols': sum(1 for r in rows if all(r['year_days'].get(y, 0) > 0 for y in years))},
        'quality': {'hard_fail_count': len(hard_fail), 'status_counts': dict(Counter(r['status'] for r in rows)), 'zero_bar_count': sum(not r['bars'] for r in rows), 'bad_slot_bars': sum(r['bad_slot_bars'] for r in rows), 'bad_day_count': sum(r['bad_day_count'] for r in rows)},
        'decision': 'SOURCE_COMPLETE_FOR_NEXT_DATASET_BUILD' if not hard_fail else 'SOURCE_INCOMPLETE__DO_NOT_BUILD_MTF_STRATEGY',
        'failures': failures,
        'artifacts': {'rows': str(OUT / 'v370_symbol_rows.json'), 'report': str(OUT / 'v370_report.json'), 'latest': str(LATEST)},
    }
    (OUT / 'v370_symbol_rows.json').write_text(json.dumps(rows, ensure_ascii=False))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v370_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
