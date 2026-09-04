#!/usr/bin/env python3
"""V371 no-write: strict Baostock 60m raw-price coverage audit against local daily dates.

Success: for every eligible SH/SZ symbol, every locally available daily date in
2023-01-01..2026-07-10 has exactly four **unadjusted** Baostock 60m OHLCV bars
in the expected A-share slots. `adjustflag=3` is mandatory because forward/
back-adjusted series can embed post-event corporate-action factors. This is a
data-source audit only: no signals, trades, PnL, production, frontend, or
watchlist writes.
"""
from __future__ import annotations

import json
import os
import re
import signal
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import baostock as bs

ROOT = Path('/root/.hermes')
KCACHE = ROOT / 'kline_cache'
AUDIT = ROOT / 'smc_audit'
START, END = '20230101', '20260710'
SLOTS = {'103000000', '113000000', '140000000', '150000000'}
# Baostock's shared remote session is not safe under concurrent logins in this
# environment (workers can fail with 10002007/BrokenProcessPool).  Keep the
# correctness audit serial by default; a caller may explicitly override only
# after a provider-session probe proves parallel operation stable.
WORKERS = max(1, min(4, int(os.environ.get('V371_WORKERS', '1'))))
LIMIT = int(os.environ.get('V371_LIMIT', '0'))
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v371_baostock_m60_strict_coverage_no_write_{TS}'
LATEST = AUDIT / 'v371_baostock_m60_strict_coverage_latest.json'


def ds(value: object) -> str:
    return ''.join(c for c in str(value or '') if c.isdigit())[:8]


def universe() -> list[tuple[str, str, list[str]]]:
    rows = []
    for path in KCACHE.glob('*_daily_750.json'):
        m = re.fullmatch(r'(\d+)_(SH|SZ)_daily_750\.json', path.name)
        if not m:
            continue
        try:
            daily = json.loads(path.read_text())
        except Exception:
            continue
        expected = sorted({ds(b.get('t') or b.get('date')) for b in daily
                           if START <= ds(b.get('t') or b.get('date')) <= END})
        if expected:
            rows.append((m.group(1), m.group(2), expected))
    return sorted(rows)


def query_chunk(bs_code: str, start_date: str, end_date: str):
    """Read one capped calendar chunk; retry only an expired Baostock session."""
    last = None
    for attempt in range(3):
        try:
            signal.signal(signal.SIGALRM, lambda _sig, _frame: (_ for _ in ()).throw(TimeoutError('Baostock query timed out after 45s')))
            signal.alarm(45)
            query = bs.query_history_k_data_plus(
                bs_code, 'date,time,open,high,low,close,volume,amount,adjustflag',
                start_date=start_date, end_date=end_date, frequency='60', adjustflag='3')
            rows: list[list[str]] = []
            while query.error_code == '0' and query.next():
                rows.append(query.get_row_data())
        except TimeoutError as exc:
            return [], 'QUERY_TIMEOUT', str(exc)
        finally:
            signal.alarm(0)
        if query.error_code != '10001001':
            return rows, query.error_code, query.error_msg
        last = query
        # Baostock invalidates a long-lived socket unpredictably; a fresh login
        # and a retry of the same source query distinguishes that transport error
        # from genuine missing historical bars.
        bs.logout()
        time.sleep(0.2 * (attempt + 1))
        login = bs.login()
        if login.error_code != '0':
            return [], f'LOGIN_{login.error_code}', login.error_msg
    return [], last.error_code, last.error_msg


def worker_init() -> None:
    login = bs.login()
    if login.error_code != '0':
        raise RuntimeError(f'baostock worker login failed: {login.error_code} {login.error_msg}')


def fetch_one(item: tuple[str, str, list[str]]) -> dict:
    code, exch, expected = item
    symbol = f'{code}.{exch}'
    bs_code = ('sh.' if exch == 'SH' else 'sz.') + code
    try:
        # Baostock caps a single intraday query at 1,500 bars.  A multi-year
        # request silently truncates around mid-2024, so fetch calendar-year
        # chunks; never interpret a capped response as a historical coverage pass.
        bars: list[list[str]] = []
        for start_date, end_date in (
            ('2023-01-01', '2023-12-31'),
            ('2024-01-01', '2024-12-31'),
            ('2025-01-01', '2025-12-31'),
            ('2026-01-01', '2026-07-10'),
        ):
            chunk_rows, status, message = query_chunk(bs_code, start_date, end_date)
            if status != '0':
                return {'symbol': symbol, 'status': status, 'message': message,
                        'expected_days': len(expected), 'failed_chunk': f'{start_date}:{end_date}'}
            bars.extend(chunk_rows)
        by_day: dict[str, list[list[str]]] = {}
        for bar in bars:
            date = ds(bar[0])
            if date:
                by_day.setdefault(date, []).append(bar)
        actual = set(by_day)
        expected_set = set(expected)
        missing = sorted(expected_set - actual)
        unexpected = sorted(actual - expected_set)
        bad_slots = 0
        bad_day_dates = []
        for date, daybars in by_day.items():
            slots = [str(b[1])[-9:] for b in daybars]
            if len(daybars) != 4 or set(slots) != SLOTS:
                bad_day_dates.append(date)
                bad_slots += sum(1 for slot in slots if slot not in SLOTS)
        years = ('2023', '2024', '2025', '2026')
        expected_years = {y: sum(d.startswith(y) for d in expected) for y in years}
        actual_years = {y: sum(d.startswith(y) for d in actual & expected_set) for y in years}
        return {
            'symbol': symbol, 'status': '0', 'message': 'success',
            'expected_days': len(expected), 'actual_days': len(actual), 'bars': len(bars),
            'missing_day_count': len(missing), 'missing_dates_sample': missing[:12],
            'unexpected_day_count': len(unexpected), 'unexpected_dates_sample': unexpected[:12],
            'bad_day_count': len(bad_day_dates), 'bad_day_dates_sample': bad_day_dates[:12],
            'bad_slot_bars': bad_slots,
            'expected_year_days': expected_years, 'actual_year_days': actual_years,
            'first': bars[0][1] if bars else '', 'last': bars[-1][1] if bars else '',
        }
    except Exception as exc:
        return {'symbol': symbol, 'status': 'EXCEPTION', 'message': repr(exc), 'expected_days': len(expected)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    items = universe()
    if LIMIT:
        items = items[:LIMIT]
    rows = []
    with ProcessPoolExecutor(max_workers=WORKERS, initializer=worker_init) as pool:
        futures = [pool.submit(fetch_one, item) for item in items]
        for n, future in enumerate(as_completed(futures), 1):
            rows.append(future.result())
            if n % 100 == 0:
                print(json.dumps({'completed': n, 'total': len(items)}, ensure_ascii=False), flush=True)
    rows.sort(key=lambda x: x['symbol'])
    failed = [r for r in rows if r.get('status') != '0']
    coverage_failed = [r for r in rows if r.get('status') == '0' and
                       (r['missing_day_count'] or r['bad_day_count'] or r['bad_slot_bars'])]
    eligible = [r for r in rows if r.get('status') == '0' and not r['missing_day_count'] and not r['bad_day_count'] and not r['bad_slot_bars']]
    years = ('2023', '2024', '2025', '2026')
    coverage = {
        y: {
            'symbols_expected': sum(r.get('expected_year_days', {}).get(y, 0) > 0 for r in rows),
            'symbols_complete': sum(r.get('expected_year_days', {}).get(y, 0) > 0 and r.get('actual_year_days', {}).get(y, 0) == r.get('expected_year_days', {}).get(y, 0) for r in rows),
        } for y in years
    }
    report = {
        'version': 'V371_BAOSTOCK_M60_STRICT_COVERAGE_AUDIT_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source_contract': 'Baostock frequency=60 adjustflag=3 (raw OHLCV) compared against local daily_750 date availability',
        'range': {'start': START, 'end': END, 'expected_slots': sorted(SLOTS)},
        'universe_symbols': len(items), 'workers': WORKERS,
        'counts': {'query_failures': len(failed), 'coverage_failures': len(coverage_failed), 'eligible_complete_symbols': len(eligible)},
        'yearly_coverage': coverage,
        'decision': 'SOURCE_COVERAGE_PASS__DATASET_BUILD_ALLOWED' if not failed and not coverage_failed else 'SOURCE_COVERAGE_FAIL__DO_NOT_BUILD_MTF_STRATEGY',
        'failure_samples': (failed + coverage_failed)[:200],
        'artifacts': {'rows': str(OUT / 'v371_symbol_rows.json'), 'report': str(OUT / 'v371_report.json'), 'latest': str(LATEST)},
    }
    (OUT / 'v371_symbol_rows.json').write_text(json.dumps(rows, ensure_ascii=False))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v371_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
