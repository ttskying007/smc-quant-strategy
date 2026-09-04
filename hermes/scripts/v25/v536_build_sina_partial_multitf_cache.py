#!/usr/bin/env python3
"""Build a source-isolated, recent-range Sina multi-timeframe research cache.

This is deliberately a separate partial-range source.  It never supplements
Baostock and it never writes signals, trades, watchlists, or production state.
The source range is the intersection of valid Sina daily and complete 15-minute
sessions returned for each symbol (currently about 2025-04 onward).
"""
from __future__ import annotations

import argparse
import gzip
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import akshare as ak
import requests

ROOT = Path('/root/.hermes')
OUT = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina'
AUDIT = ROOT / 'smc_audit'
URL = 'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData'
SLOTS_15 = ('0945', '1000', '1015', '1030', '1045', '1100', '1115', '1130', '1315', '1330', '1345', '1400', '1415', '1430', '1445', '1500')
SLOT_60 = {'0945': '1030', '1000': '1030', '1015': '1030', '1030': '1030', '1045': '1130', '1100': '1130', '1115': '1130', '1130': '1130', '1315': '1400', '1330': '1400', '1345': '1400', '1400': '1400', '1415': '1500', '1430': '1500', '1445': '1500', '1500': '1500'}
PROVENANCE_SCHEMA = 'V536_SOURCE_ISOLATED_BAR_V1'
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'Mozilla/5.0'})


def atomic_gzip(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with gzip.open(temporary, 'wt', encoding='utf-8') as handle:
        json.dump(rows, handle, ensure_ascii=False, separators=(',', ':'))
    temporary.replace(path)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    temporary.replace(path)


CANONICAL = AUDIT / 'v536_sina_canonical_universe_latest.json'


def canonical_universe() -> list[str]:
    """Use the last dated independent denominator when its live refresh is unavailable."""
    try:
        prior = json.loads(CANONICAL.read_text())
        symbols = prior.get('symbols')
        if isinstance(symbols, list) and symbols:
            return sorted(set(str(symbol) for symbol in symbols))
    except (OSError, ValueError, TypeError):
        pass
    table = ak.stock_info_a_code_name()
    symbols = []
    for value in table['code'].astype(str):
        code = value.zfill(6)
        exchange = 'SH' if code.startswith('6') else 'SZ' if code.startswith(('0', '3')) else 'BJ' if code.startswith('9') else ''
        if exchange:
            symbols.append(f'{code}.{exchange}')
    return sorted(set(symbols))


def sina_symbol(symbol: str) -> str:
    code, exchange = symbol.split('.')
    return f"{'sh' if exchange == 'SH' else 'sz' if exchange == 'SZ' else 'bj'}{code}"


def fetch(symbol: str, scale: int) -> list[dict[str, str]]:
    response = SESSION.get(URL, params={'symbol': sina_symbol(symbol), 'scale': scale, 'ma': 'no', 'datalen': 10000}, timeout=35)
    rows = response.json()
    if response.status_code != 200 or not isinstance(rows, list) or not rows:
        raise ValueError(f'sina_empty_or_invalid scale={scale} status={response.status_code}')
    return rows


def valid_m15_dates(rows: list[dict[str, str]]) -> set[str]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        day = str(row.get('day') or '')
        if len(day) >= 16:
            grouped[day[:10]].append(day[11:16].replace(':', ''))
    return {day for day, slots in grouped.items() if tuple(slots) == SLOTS_15}


def normalize(rows: list[dict[str, str]], frame: str, requested: dict[str, Any], received: dict[str, str], keep_dates: set[str] | None = None) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        day = str(row['day'])
        date = day[:10]
        if keep_dates is not None and date not in keep_dates:
            continue
        clock = day[11:16].replace(':', '') if len(day) >= 16 else ''
        timestamp = date.replace('-', '') + (clock + '00' if clock else '')
        result.append({
            't': timestamp, 'd': date.replace('-', ''), 'o': float(row['open']), 'h': float(row['high']),
            'l': float(row['low']), 'c': float(row['close']), 'v': float(row['volume']), 'a': 0.0,
            'source': 'sina', 'adjustment': 'provider_undocumented_no_cross_source_assumption',
            'requested_range': requested, 'received_range': received, 'provider_timestamp': day,
            'coverage_audit': 'SOURCE_LOCAL_PARTIAL_RANGE_PENDING_AUDIT',
            'cross_source_validation': 'NOT_SUBSTITUTABLE__INDEPENDENT_WITNESS_ONLY',
            'source_kind': 'provider_raw' if frame in {'daily', 'm15'} else 'same_source_deterministic_aggregation',
            'provenance_schema': PROVENANCE_SCHEMA,
        })
    if not result:
        raise ValueError(f'no_normalized_{frame}_rows')
    return result


def derived_weekly(daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in daily:
        buckets[datetime.strptime(row['t'], '%Y%m%d').isocalendar()[:2]].append(row)
    result = []
    for rows in buckets.values():
        last = rows[-1]
        result.append({**last, 'o': rows[0]['o'], 'h': max(x['h'] for x in rows), 'l': min(x['l'] for x in rows), 'c': last['c'], 'v': sum(x['v'] for x in rows), 'a': 0.0, 'source_kind': 'same_source_deterministic_aggregation'})
    return result


def derived_m60(m15: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in m15:
        end = SLOT_60[row['t'][8:12]]
        buckets[(row['d'], end)].append(row)
    result = []
    for (day, end), rows in sorted(buckets.items()):
        if len(rows) != 4:
            raise ValueError(f'incomplete_m60_bucket {day} {end}')
        last = rows[-1]
        result.append({**last, 't': f'{day}{end}00', 'o': rows[0]['o'], 'h': max(x['h'] for x in rows), 'l': min(x['l'] for x in rows), 'c': last['c'], 'v': sum(x['v'] for x in rows), 'a': 0.0, 'source_kind': 'same_source_deterministic_aggregation'})
    return result


def build(symbol: str) -> dict[str, Any]:
    m15_raw, daily_raw = fetch(symbol, 15), fetch(symbol, 240)
    complete_dates = valid_m15_dates(m15_raw)
    daily_dates = {str(row['day'])[:10] for row in daily_raw}
    dates = complete_dates & daily_dates
    if not dates:
        raise ValueError('no_complete_common_daily_m15_range')
    requested = {'datalen': 10000, 'daily_scale': 240, 'm15_scale': 15}
    received = {'start': min(dates), 'end': max(dates)}
    m15 = normalize(m15_raw, 'm15', requested, received, dates)
    daily = normalize(daily_raw, 'daily', requested, received, dates)
    weekly, m60 = derived_weekly(daily), derived_m60(m15)
    frames = {'daily': daily, 'weekly': weekly, 'm60': m60, 'm15': m15}
    base = symbol.replace('.', '_')
    for frame, rows in frames.items():
        atomic_gzip(OUT / frame / f'{base}_{frame}.json.gz', rows)
    return {'symbol': symbol, 'status': 'COMPLETE', 'range': received, 'frames': {name: len(rows) for name, rows in frames.items()}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', default='')
    parser.add_argument('--resume-from', default='')
    parser.add_argument('--limit', type=int, default=1)
    args = parser.parse_args()
    if args.limit < 1:
        raise SystemExit('--limit must be positive')
    universe = canonical_universe()
    if not CANONICAL.exists():
        atomic_json(CANONICAL, {
            'version': 'V536_SINA_CANONICAL_A_SHARE_UNIVERSE_V1', 'generated_at': datetime.now().isoformat(timespec='seconds'),
            'source': 'akshare.stock_info_a_code_name', 'canonical_count': len(universe),
            'by_exchange': {x: sum(s.endswith(f'.{x}') for s in universe) for x in ('SH', 'SZ', 'BJ')},
            'symbols': universe, 'research_only': True, 'production_write': False,
        })
    if args.symbol:
        wanted = [args.symbol] if args.symbol in universe else []
    else:
        existing = {p.name.removesuffix('_m15.json.gz').replace('_', '.') for p in (OUT / 'm15').glob('*_m15.json.gz')}
        wanted = [s for s in universe if s not in existing and (not args.resume_from or s >= args.resume_from)][:args.limit]
    rows = []
    for symbol in wanted:
        try:
            rows.append(build(symbol))
        except Exception as exc:
            rows.append({'symbol': symbol, 'status': 'FAILED', 'error': repr(exc)})
        time.sleep(0.35)
    failed = [row for row in rows if row['status'] != 'COMPLETE']
    report = {'version': 'V536_SINA_PARTIAL_SOURCE_CACHE_BUILD_V1', 'generated_at': datetime.now().isoformat(timespec='seconds'),
              'source': 'sina', 'source_root': str(OUT), 'scope': 'SOURCE_ISOLATED_PARTIAL_RANGE_ONLY',
              'requested': len(wanted), 'completed': len(rows) - len(failed), 'failed': len(failed), 'rows': rows,
              'research_only': True, 'production_write': False, 'cross_source_substitution': False,
              'decision': 'PARTIAL_SOURCE_BUILD_PASS' if not failed else 'PARTIAL_SOURCE_BUILD_RETRY_REQUIRED'}
    atomic_json(AUDIT / f"v536_sina_partial_source_build_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", report)
    atomic_json(AUDIT / 'v536_sina_partial_source_build_latest.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
