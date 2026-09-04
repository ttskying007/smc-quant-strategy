#!/usr/bin/env python3
"""V372 no-write: validate Baostock qfq 60m aggregates against local qfq daily bars.

This is a data-contract audit only. It creates no signals, entries, PnL, production,
frontend, or watchlist data. It is deliberately gated behind V371 source coverage.
"""
from __future__ import annotations

import json
import math
import os
import re
import signal
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import baostock as bs

ROOT = Path('/root/.hermes')
KCACHE = ROOT / 'kline_cache'
AUDIT = ROOT / 'smc_audit'
V371 = AUDIT / 'v371_baostock_m60_strict_coverage_latest.json'
START, END = '20230101', '20260710'
SLOTS = {'103000000', '113000000', '140000000', '150000000'}
# OHLC must agree closely enough to make a qfq POI/touch meaningful. The sample
# preflight's worst observed deviation was <1%; 1.25% leaves only a small vendor
# rounding/timestamp tolerance and keeps all exceptions observable.
MAX_OHLC_DEVIATION_PCT = 1.25
# Baostock remote sessions are not stable with concurrent logins in this host.
# Keep validation serial; correctness is more important than a fast but incomplete audit.
WORKERS = max(1, min(4, int(os.environ.get('V372_WORKERS', '1'))))
LIMIT = int(os.environ.get('V372_LIMIT', '0'))
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v372_baostock_m60_qfq_alignment_no_write_{TS}'
LATEST = AUDIT / 'v372_baostock_m60_qfq_alignment_latest.json'


def ds(value: object) -> str:
    return ''.join(c for c in str(value or '') if c.isdigit())[:8]


def f(value: object) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def source_pass() -> bool:
    try:
        r = json.loads(V371.read_text())
    except Exception:
        return False
    return r.get('decision') == 'SOURCE_COVERAGE_PASS__DATASET_BUILD_ALLOWED' and r.get('universe_symbols', 0) >= 4000


def universe() -> list[tuple[str, str, dict[str, dict[str, float]]]]:
    rows = []
    for path in KCACHE.glob('*_daily_750.json'):
        m = re.fullmatch(r'(\d+)_(SH|SZ)_daily_750\.json', path.name)
        if not m:
            continue
        try:
            bars = json.loads(path.read_text())
        except Exception:
            continue
        daily: dict[str, dict[str, float]] = {}
        for b in bars:
            date = ds(b.get('t') or b.get('date'))
            if not (START <= date <= END):
                continue
            values = {k: f(b.get(k)) for k in ('o', 'h', 'l', 'c', 'v')}
            if all(values[k] is not None for k in ('o', 'h', 'l', 'c')):
                daily[date] = values  # type: ignore[assignment]
        if daily:
            rows.append((m.group(1), m.group(2), daily))
    return sorted(rows)


def query_chunk(bs_code: str, start: str, end: str) -> tuple[list[list[str]], str, str]:
    last_code, last_message = 'EXCEPTION', ''
    for attempt in range(3):
        try:
            signal.signal(signal.SIGALRM, lambda _sig, _frame: (_ for _ in ()).throw(TimeoutError('Baostock query timed out after 45s')))
            signal.alarm(45)
            q = bs.query_history_k_data_plus(
                bs_code, 'date,time,open,high,low,close,volume,amount,adjustflag',
                start_date=start, end_date=end, frequency='60', adjustflag='2')
            rows: list[list[str]] = []
            while q.error_code == '0' and q.next():
                rows.append(q.get_row_data())
        except TimeoutError as exc:
            return [], 'QUERY_TIMEOUT', str(exc)
        finally:
            signal.alarm(0)
        if q.error_code != '10001001':
            return rows, q.error_code, q.error_msg
        last_code, last_message = q.error_code, q.error_msg
        bs.logout()
        time.sleep(0.2 * (attempt + 1))
        login = bs.login()
        if login.error_code != '0':
            return [], f'LOGIN_{login.error_code}', login.error_msg
    return [], last_code, last_message


def worker_init() -> None:
    login = bs.login()
    if login.error_code != '0':
        raise RuntimeError(f'baostock worker login failed: {login.error_code} {login.error_msg}')


def fetch_one(item: tuple[str, str, dict[str, dict[str, float]]]) -> dict:
    code, exchange, daily = item
    symbol, bs_code = f'{code}.{exchange}', ('sh.' if exchange == 'SH' else 'sz.') + code
    try:
        bars: list[list[str]] = []
        for start, end in (('2023-01-01', '2023-12-31'), ('2024-01-01', '2024-12-31'),
                           ('2025-01-01', '2025-12-31'), ('2026-01-01', '2026-07-10')):
            chunk, status, message = query_chunk(bs_code, start, end)
            if status != '0':
                return {'symbol': symbol, 'status': status, 'message': message}
            bars.extend(chunk)
        per_day: dict[str, list[list[str]]] = {}
        for row in bars:
            date = ds(row[0])
            if date:
                per_day.setdefault(date, []).append(row)
        mismatch_days, partial_days, deviations, volume_ratios = [], [], [], []
        for date, expected in daily.items():
            day = per_day.get(date, [])
            slots = {str(x[1])[-9:] for x in day}
            if len(day) != 4 or slots != SLOTS:
                partial_days.append(date)
                continue
            opens = [f(x[2]) for x in day]; highs = [f(x[3]) for x in day]
            lows = [f(x[4]) for x in day]; closes = [f(x[5]) for x in day]
            volumes = [f(x[6]) for x in day]
            if any(x is None for x in opens + highs + lows + closes):
                partial_days.append(date)
                continue
            aggregate = {'o': opens[0], 'h': max(highs), 'l': min(lows), 'c': closes[-1]}
            day_max = 0.0
            for key, actual in aggregate.items():
                base = expected[key]
                deviation = abs(actual / base - 1) * 100 if base else float('inf')
                day_max = max(day_max, deviation)
            deviations.append(day_max)
            if day_max > MAX_OHLC_DEVIATION_PCT:
                mismatch_days.append({'date': date, 'max_ohlc_deviation_pct': round(day_max, 6)})
            total_volume = sum(x for x in volumes if x is not None)
            if expected.get('v') and total_volume:
                volume_ratios.append(total_volume / expected['v'])
        years = ('2023', '2024', '2025', '2026')
        return {
            'symbol': symbol, 'status': '0', 'daily_days': len(daily),
            'aligned_days': len(deviations), 'partial_day_count': len(partial_days),
            'partial_dates_sample': partial_days[:12], 'mismatch_day_count': len(mismatch_days),
            'mismatch_dates_sample': mismatch_days[:12],
            'max_ohlc_deviation_pct': round(max(deviations), 6) if deviations else None,
            'p95_ohlc_deviation_pct': round(sorted(deviations)[int((len(deviations) - 1) * .95)], 6) if deviations else None,
            'volume_ratio_median': round(sorted(volume_ratios)[len(volume_ratios) // 2], 6) if volume_ratios else None,
            'yearly_aligned_days': {y: sum(d.startswith(y) for d in daily if d not in set(partial_days)) for y in years},
        }
    except Exception as exc:
        return {'symbol': symbol, 'status': 'EXCEPTION', 'message': repr(exc)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if not source_pass():
        report = {
            'version': 'V372_BAOSTOCK_M60_QFQ_ALIGNMENT_AUDIT_NO_WRITE',
            'generated_at': datetime.now().isoformat(timespec='seconds'),
            'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
            'decision': 'BLOCKED__V371_FULL_UNIVERSE_SOURCE_COVERAGE_NOT_PASSED',
        }
        LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
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
    rows.sort(key=lambda r: r['symbol'])
    query_failed = [r for r in rows if r.get('status') != '0']
    alignment_failed = [r for r in rows if r.get('status') == '0' and (r['partial_day_count'] or r['mismatch_day_count'])]
    eligible = [r for r in rows if r.get('status') == '0' and not r['partial_day_count'] and not r['mismatch_day_count']]
    report = {
        'version': 'V372_BAOSTOCK_M60_QFQ_ALIGNMENT_AUDIT_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source_contract': 'Baostock frequency=60 adjustflag=2 aggregated by day vs local Tencent qfq daily_750',
        'max_ohlc_deviation_pct': MAX_OHLC_DEVIATION_PCT, 'universe_symbols': len(items), 'workers': WORKERS,
        'counts': {'query_failures': len(query_failed), 'alignment_failures': len(alignment_failed), 'eligible_aligned_symbols': len(eligible)},
        'decision': 'QFQ_ALIGNMENT_PASS__STRUCTURAL_DIFFERENTIAL_AUDIT_ALLOWED' if not query_failed and not alignment_failed else 'QFQ_ALIGNMENT_FAIL__DO_NOT_BUILD_MTF_GENERATOR',
        'failure_samples': (query_failed + alignment_failed)[:200],
        'artifacts': {'rows': str(OUT / 'v372_symbol_rows.json'), 'report': str(OUT / 'v372_report.json'), 'latest': str(LATEST)},
    }
    (OUT / 'v372_symbol_rows.json').write_text(json.dumps(rows, ensure_ascii=False))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v372_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
