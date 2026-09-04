#!/usr/bin/env python3
"""Build resumable 2023-2026 raw OHLCV cache for multi-timeframe research.

Contract:
- SH/SZ only: Baostock supports unadjusted (adjustflag=3) historic intraday bars.
- 15m is requested in calendar quarters because the provider silently caps long
  intraday requests. 60m is requested by calendar year.
- daily is raw Baostock data; weekly is derived only from the same raw daily bars.
- This script writes research data and manifests only. It never emits signals,
  trades, watchlists, production candidates, frontend payloads, or positions.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import baostock as bs

ROOT = Path('/root/.hermes')
DAILY_QFQ = ROOT / 'kline_cache'
CACHE = ROOT / 'intraday_cache' / 'raw_multitf_v536'
# Legacy root is retained read-only. New provider writes are source-isolated.
SOURCE_CACHE = CACHE / 'source_raw' / 'baostock'
QUARANTINE = CACHE / 'quarantine'
AUDIT = ROOT / 'smc_audit'
LATEST = AUDIT / 'v536_multitf_raw_cache_latest.json'
START, END = '2023-01-01', '2026-07-17'
YEARS = (2023, 2024, 2025, 2026)
M60_SLOTS = {'1030', '1130', '1400', '1500'}
M15_SLOTS = {'0945', '1000', '1015', '1030', '1045', '1100', '1115', '1130', '1315', '1330', '1345', '1400', '1415', '1430', '1445', '1500'}


def date8(value: object) -> str:
    return ''.join(c for c in str(value or '') if c.isdigit())[:8]


def atomic_gzip_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with gzip.open(temporary, 'wt', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(',', ':'))
    temporary.replace(path)


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    temporary.replace(path)


def quarantine(symbol: str, reason: str) -> None:
    """Record a provider-confirmed permanent no-data symbol atomically."""
    atomic_json(QUARANTINE / f'{symbol}.json', {
        'symbol': symbol, 'reason': reason,
        'recorded_at': datetime.now().isoformat(timespec='seconds'),
    })


def universe() -> tuple[list[tuple[str, str]], list[str]]:
    supported: list[tuple[str, str]] = []
    quarantined: list[str] = []
    for path in sorted(DAILY_QFQ.glob('*_daily_750.json')):
        m = re.fullmatch(r'(\d+)_(SH|SZ|BJ)_daily_750\.json', path.name)
        if not m:
            continue
        code, exchange = m.groups()
        if exchange in {'SH', 'SZ'}:
            supported.append((code, exchange))
        else:
            quarantined.append(f'{code}.{exchange}')
    return sorted(set(supported)), sorted(set(quarantined))


def path_for(code: str, exchange: str, frame: str) -> Path:
    return SOURCE_CACHE / frame / f'{code}_{exchange}_{frame}.json.gz'


def attach_provenance(rows: list[dict[str, Any]], frame: str) -> list[dict[str, Any]]:
    """Attach immutable source contract before any provider-derived cache write."""
    kind = 'provider_raw' if frame in {'daily', 'm15'} else 'same_source_deterministic_aggregation'
    for row in rows:
        timestamp = str(row['t'])
        row.update({
            'source': 'baostock',
            'adjustment': 'raw_unadjusted_adjustflag_3',
            'requested_range': {'start': START, 'end': END},
            'received_range': {'start': START, 'end': END},
            'provider_timestamp': timestamp,
            'coverage_audit': 'PENDING_SOURCE_ISOLATION_AUDIT',
            'cross_source_validation': 'PENDING_INDEPENDENT_OVERLAP_AUDIT',
            'source_kind': kind,
            'provenance_schema': 'V536_SOURCE_ISOLATED_BAR_V1',
        })
    return rows


def query(fields: str, code: str, exchange: str, start: str, end: str, frequency: str) -> tuple[list[list[str]], str, str]:
    bs_code = f"{'sh' if exchange == 'SH' else 'sz'}.{code}"
    for attempt in range(4):
        q = bs.query_history_k_data_plus(bs_code, fields, start_date=start, end_date=end, frequency=frequency, adjustflag='3')
        rows: list[list[str]] = []
        while q.error_code == '0' and q.next():
            rows.append(q.get_row_data())
        if q.error_code == '0':
            return rows, '0', 'success'
        if q.error_code != '10001001':
            return [], q.error_code, q.error_msg
        bs.logout()
        time.sleep(0.5 * (attempt + 1))
        login = bs.login()
        if login.error_code != '0':
            return [], f'LOGIN_{login.error_code}', login.error_msg
    return [], 'RETRY_EXHAUSTED', 'Baostock session repeatedly expired'


def parse_daily(rows: list[list[str]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        try:
            d = date8(r[0]); o, h, l, c = map(float, r[1:5])
            if d and min(o, h, l, c) > 0 and h >= max(o, c) and l <= min(o, c):
                out.append({'t': d, 'o': o, 'h': h, 'l': l, 'c': c, 'v': float(r[5]), 'a': float(r[6])})
        except (IndexError, TypeError, ValueError):
            continue
    return sorted({x['t']: x for x in out}.values(), key=lambda x: x['t'])


def parse_intraday(rows: list[list[str]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        try:
            t = ''.join(c for c in str(r[1]) if c.isdigit())[:14]
            d = date8(r[0]); o, h, l, c = map(float, r[2:6])
            if len(t) == 14 and d and min(o, h, l, c) > 0 and h >= max(o, c) and l <= min(o, c):
                out.append({'t': t, 'd': d, 'o': o, 'h': h, 'l': l, 'c': c, 'v': float(r[6]), 'a': float(r[7])})
        except (IndexError, TypeError, ValueError):
            continue
    return sorted({x['t']: x for x in out}.values(), key=lambda x: x['t'])


def weekly_from_daily(daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for bar in daily:
        dt = datetime.strptime(bar['t'], '%Y%m%d')
        buckets.setdefault(dt.isocalendar()[:2], []).append(bar)
    out = []
    for rows in buckets.values():
        rows.sort(key=lambda x: x['t'])
        out.append({'t': rows[-1]['t'], 'o': rows[0]['o'], 'h': max(x['h'] for x in rows), 'l': min(x['l'] for x in rows), 'c': rows[-1]['c'], 'v': sum(x['v'] for x in rows), 'a': sum(x['a'] for x in rows)})
    return out


def m60_from_m15(m15: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate each four 15m raw bars into the official A-share 60m slots."""
    slot_end = {'0945': '1030', '1000': '1030', '1015': '1030', '1030': '1030',
                '1045': '1130', '1100': '1130', '1115': '1130', '1130': '1130',
                '1315': '1400', '1330': '1400', '1345': '1400', '1400': '1400',
                '1415': '1500', '1430': '1500', '1445': '1500', '1500': '1500'}
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for bar in m15:
        end = slot_end.get(bar['t'][8:12])
        if end:
            groups.setdefault((bar['d'], end), []).append(bar)
    out = []
    for (day, end), bars in sorted(groups.items()):
        if len(bars) != 4:
            continue
        out.append({'t': f'{day}{end}00', 'd': day, 'o': bars[0]['o'],
                    'h': max(x['h'] for x in bars), 'l': min(x['l'] for x in bars),
                    'c': bars[-1]['c'], 'v': sum(x['v'] for x in bars),
                    'a': sum(x['a'] for x in bars)})
    return out


def quarter_chunks() -> list[tuple[str, str]]:
    chunks = []
    for year in YEARS:
        for month_a, month_b in ((1, 3), (4, 6), (7, 9), (10, 12)):
            start = f'{year}-{month_a:02d}-01'
            if month_b == 12:
                end = f'{year}-12-31'
            else:
                end = f'{year}-{month_b + 1:02d}-01'
            if start <= END:
                chunks.append((start, min(end, END)))
    return chunks


def validate_intraday(rows: list[dict[str, Any]], expected_dates: set[str], slots: set[str]) -> dict[str, Any]:
    per_day: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row['d'] in expected_dates:
            per_day.setdefault(row['d'], []).append(row)
    actual = set(per_day)
    bad = []
    for d, day_rows in per_day.items():
        got = {x['t'][8:12] for x in day_rows}
        if len(day_rows) != len(slots) or got != slots:
            bad.append(d)
    missing = sorted(expected_dates - actual)
    return {'expected_days': len(expected_dates), 'actual_days': len(actual), 'missing_days': len(missing), 'bad_slot_days': len(bad), 'missing_sample': missing[:12], 'bad_slot_sample': sorted(bad)[:12]}


def load_cache(path: Path) -> list[dict[str, Any]] | None:
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            rows = json.load(handle)
        return rows if isinstance(rows, list) else None
    except Exception:
        return None


def build_one(code: str, exchange: str) -> dict[str, Any]:
    symbol = f'{code}.{exchange}'
    dp, wp, p60, p15 = (path_for(code, exchange, x) for x in ('daily', 'weekly', 'm60', 'm15'))
    existing = {name: load_cache(p) for name, p in {'daily': dp, 'weekly': wp, 'm60': p60, 'm15': p15}.items()}
    if all(existing.values()):
        daily = existing['daily']
        expected = {x['t'] for x in daily if START.replace('-', '') <= x['t'] <= END.replace('-', '')}
        a60 = validate_intraday(existing['m60'], expected, M60_SLOTS)
        a15 = validate_intraday(existing['m15'], expected, M15_SLOTS)
        if not (a60['missing_days'] or a60['bad_slot_days'] or a15['missing_days'] or a15['bad_slot_days']):
            return {'symbol': symbol, 'status': 'CACHED_COMPLETE', 'daily_bars': len(daily), 'weekly_bars': len(existing['weekly']), 'm60_bars': len(existing['m60']), 'm15_bars': len(existing['m15']), 'm60_audit': a60, 'm15_audit': a15}
    daily_rows, status, message = query('date,open,high,low,close,volume,amount,adjustflag', code, exchange, START, END, 'd')
    if status != '0':
        return {'symbol': symbol, 'status': 'FAIL_DAILY', 'provider_status': status, 'message': message}
    daily = parse_daily(daily_rows)
    expected = {x['t'] for x in daily}
    if not expected:
        quarantine(symbol, 'BAOSTOCK_DAILY_EMPTY_2023_2026')
        return {'symbol': symbol, 'status': 'FAIL_DAILY_EMPTY'}
    # One full-range raw m15 request is validated below then deterministically
    # aggregated into 60m; this removes a redundant provider round trip.
    m15_raw, status, message = query('date,time,open,high,low,close,volume,amount,adjustflag', code, exchange, START, END, '15')
    if status != '0':
        return {'symbol': symbol, 'status': 'FAIL_M15', 'provider_status': status, 'message': message}
    m15 = parse_intraday(m15_raw)
    m60 = m60_from_m15(m15)
    weekly = weekly_from_daily(daily)
    daily, weekly, m60, m15 = (
        attach_provenance(daily, 'daily'),
        attach_provenance(weekly, 'weekly'),
        attach_provenance(m60, 'm60'),
        attach_provenance(m15, 'm15'),
    )
    a60, a15 = validate_intraday(m60, expected, M60_SLOTS), validate_intraday(m15, expected, M15_SLOTS)
    if a60['missing_days'] or a60['bad_slot_days'] or a15['missing_days'] or a15['bad_slot_days']:
        return {'symbol': symbol, 'status': 'FAIL_COVERAGE', 'daily_bars': len(daily), 'm60_bars': len(m60), 'm15_bars': len(m15), 'm60_audit': a60, 'm15_audit': a15}
    atomic_gzip_json(dp, daily)
    atomic_gzip_json(wp, weekly)
    atomic_gzip_json(p60, m60)
    atomic_gzip_json(p15, m15)
    return {'symbol': symbol, 'status': 'BUILT_COMPLETE', 'daily_bars': len(daily), 'weekly_bars': len(weekly), 'm60_bars': len(m60), 'm15_bars': len(m15), 'm60_audit': a60, 'm15_audit': a15}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--resume-from', default='')
    parser.add_argument('--symbols-file', default='',
                        help='newline-delimited exact SH/SZ symbols to build; takes precedence over resume-from')
    args = parser.parse_args()
    symbols, bj_quarantine = universe()
    if args.symbols_file:
        requested = {line.strip() for line in Path(args.symbols_file).read_text().splitlines() if line.strip()}
        symbols = [x for x in symbols if f'{x[0]}.{x[1]}' in requested]
        found = {f'{code}.{exchange}' for code, exchange in symbols}
        unknown = requested - found
        if unknown:
            raise ValueError(f'unsupported symbols requested: {sorted(unknown)[:10]}')
    elif args.resume_from:
        symbols = [x for x in symbols if f'{x[0]}.{x[1]}' >= args.resume_from]
    if args.limit:
        symbols = symbols[:args.limit]
    started = time.time()
    run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    out = AUDIT / f'v536_multitf_raw_cache_build_{run_id}'
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    login = bs.login()
    if login.error_code != '0':
        raise RuntimeError(f'Baostock login failed: {login.error_code} {login.error_msg}')
    try:
        for index, (code, exchange) in enumerate(symbols, 1):
            result = build_one(code, exchange)
            rows.append(result)
            # Persist after every symbol so a mid-batch kill never loses row status
            # of symbols already written to the gzip cache.
            ok = sum(r['status'] in {'BUILT_COMPLETE', 'CACHED_COMPLETE'} for r in rows)
            print(json.dumps({'progress': index, 'total': len(symbols), 'complete': ok, 'failed': index - ok, 'last': result['symbol'], 'last_status': result['status'], 'elapsed_sec': round(time.time() - started, 1)}, ensure_ascii=False), flush=True)
            atomic_json(out / 'rows.partial.json', rows)
    finally:
        bs.logout()
    status_counts = Counter(x['status'] for x in rows)
    completed = [x for x in rows if x['status'] in {'BUILT_COMPLETE', 'CACHED_COMPLETE'}]
    report = {
        'version': 'V536_RAW_MULTITF_2023_2026_CACHE_BUILD',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'range': {'start': START, 'end': END},
        'source_contract': 'Source-isolated Baostock raw daily + full-range raw 15m under source_raw/baostock; weekly and 60m are deterministically aggregated from same-source lower timeframe bars; every bar carries provenance; no qfq/raw or cross-provider mixing',
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False, 'signal_or_trade_generation': False,
        'requested_symbols': len(symbols), 'completed_symbols': len(completed), 'failed_symbols': len(rows) - len(completed), 'status_counts': dict(status_counts),
        'bj_quarantined_count': len(bj_quarantine), 'bj_quarantined_sample': bj_quarantine[:20],
        'decision': 'CACHE_COMPLETE_FOR_SH_SZ__BJ_SOURCE_QUARANTINED' if len(completed) == len(symbols) else 'CACHE_INCOMPLETE__RESUME_REQUIRED',
        'artifacts': {'cache_root': str(CACHE), 'rows': str(out / 'rows.json'), 'latest': str(LATEST)},
    }
    atomic_json(out / 'rows.json', rows)
    atomic_json(out / 'report.json', report)
    atomic_json(LATEST, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
