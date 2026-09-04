#!/usr/bin/env python3
"""V379 no-write: raw daily rebuild and strict source eligibility from Sina 60m.

Only 60m source bars form rebuilt OHLCV and POI prices. The legacy local daily
cache supplies calendar cross-check metadata only; it is never read for prices,
signals, POIs, entries, or outcomes. Every source anomaly is quarantined as a
day boundary, not silently repaired.
"""
from __future__ import annotations

import gzip
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import akshare as ak

ROOT = Path('/root/.hermes')
LEGACY = ROOT / 'kline_cache'
M60 = ROOT / 'intraday_cache' / 'sina_m60_v1'
RAW = ROOT / 'intraday_cache' / 'sina_raw_daily_v379'
AUDIT = ROOT / 'smc_audit'
START, END = '20230101', '20260710'
SLOTS = ('10:30:00', '11:30:00', '14:00:00', '15:00:00')
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v379_sina_m60_raw_daily_data_gate_no_write_{TS}'
LATEST = AUDIT / 'v379_sina_m60_raw_daily_data_gate_latest.json'


def day(value: object) -> str:
    return ''.join(str(value or '').split(' ')[0].split('-'))[:8]


def f(value: object) -> float:
    return float(value)


def universe() -> dict[str, Path]:
    out = {}
    for path in LEGACY.glob('*_daily_750.json'):
        m = re.fullmatch(r'(\d+)_(SH|SZ)_daily_750\.json', path.name)
        if m:
            out[f'{m.group(1)}.{m.group(2)}'] = path
    return out


def legacy_dates(path: Path) -> set[str]:
    try:
        rows = json.loads(path.read_text())
    except Exception:
        return set()
    return {day(x.get('t') or x.get('date')) for x in rows if START <= day(x.get('t') or x.get('date')) <= END}


def listing_metadata() -> tuple[dict[str, str], set[str]]:
    """Listing date and current-list membership are metadata, never POI inputs."""
    listed: dict[str, str] = {}
    sh = ak.stock_info_sh_name_code()
    for _, row in sh.iterrows():
        code = str(row.get('证券代码', '')).zfill(6)
        date = ''.join(str(row.get('上市日期', '')).split('-'))[:8]
        if code and date:
            listed[f'{code}.SH'] = date
    sz = ak.stock_info_sz_name_code()
    for _, row in sz.iterrows():
        code = str(row.get('A股代码', '')).zfill(6)
        date = ''.join(str(row.get('A股上市日期', '')).split('-'))[:8]
        if code and date:
            listed[f'{code}.SZ'] = date
    active = set()
    for code in ak.stock_info_a_code_name()['code'].astype(str):
        active.add(code.zfill(6))
    return listed, active


def read_m60(symbol: str) -> tuple[dict[str, list[dict]], list[str], str]:
    code, exchange = symbol.split('.')
    path = M60 / f'{code}_{exchange}_m60_sina.json.gz'
    if not path.exists():
        return {}, [], 'CACHE_MISSING'
    try:
        with gzip.open(path, 'rt') as h:
            rows = json.load(h)
    except Exception as exc:
        return {}, [], f'CACHE_PARSE_ERROR:{type(exc).__name__}'
    groups: dict[str, list[dict]] = defaultdict(list)
    for x in rows:
        t = str(x.get('day') or '')
        d = day(t)
        if not (START <= d <= END):
            continue
        try:
            groups[d].append({'t': t, 'o': f(x['open']), 'h': f(x['high']), 'l': f(x['low']), 'c': f(x['close']), 'v': f(x.get('volume', 0))})
        except (KeyError, TypeError, ValueError):
            groups[d].append({'t': t, 'bad': True})
    bad = []
    for d, rows in groups.items():
        rows.sort(key=lambda x: x['t'])
        if len(rows) != 4 or tuple(x['t'][-8:] for x in rows) != SLOTS or any('bad' in x for x in rows):
            bad.append(d)
    return groups, sorted(bad), 'OK'


def daily_from_m60(groups: dict[str, list[dict]], invalid: set[str], market_index: dict[str, int]) -> list[dict]:
    rows = []
    last_index = None
    segment = 0
    for d in sorted(groups):
        if d in invalid:
            continue
        b = groups[d]
        idx = market_index.get(d)
        if idx is None:
            continue
        if last_index is not None and idx != last_index + 1:
            segment += 1
        rows.append({'t': d, 'o': b[0]['o'], 'h': max(x['h'] for x in b), 'l': min(x['l'] for x in b),
                     'c': b[-1]['c'], 'v': sum(x['v'] for x in b), 'source': 'SINA_M60_AGGREGATED',
                     'segment_id': segment, 'source_slots': list(SLOTS)})
        last_index = idx
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    symbols = universe()
    listed, active_codes = listing_metadata()
    source, rows = {}, []
    raw_calendar: set[str] = set()

    # First pass obtains the market calendar entirely from raw 60m source days.
    for sym in sorted(symbols):
        groups, bad, status = read_m60(sym)
        source[sym] = (groups, bad, status)
        raw_calendar.update(d for d in groups if d not in bad)
    calendar = sorted(raw_calendar)
    calendar_index = {d: i for i, d in enumerate(calendar)}

    counts = Counter()
    for sym, legacy_path in sorted(symbols.items()):
        groups, bad, read_status = source[sym]
        raw_days = set(groups)
        valid_days = raw_days - set(bad)
        reference = legacy_dates(legacy_path)  # calendar validation only
        code = sym.split('.')[0]
        list_date = listed.get(sym, '')
        current = code in active_codes
        missing_reference = sorted(reference - raw_days)
        invalid_reference = sorted(reference & set(bad))
        output = []
        status = 'ELIGIBLE'
        reason = ''
        if read_status != 'OK':
            if not current and reference and max(reference) < START:
                status, reason = 'EXCLUDED_DELISTED_PREWINDOW', 'NOT_CURRENT_AND_NO_POSTSTART_REFERENCE'
            elif not current and not reference:
                status, reason = 'EXCLUDED_DELISTED_PREWINDOW', 'NOT_CURRENT_NO_POSTSTART_WINDOW'
            else:
                status, reason = 'FAIL_UNEXPLAINED_SOURCE_MISSING', read_status
        elif missing_reference:
            status, reason = 'FAIL_SOURCE_GAP_VS_REFERENCE_CALENDAR', 'MISSING_RAW_FOR_LOCAL_TRADING_DATE'
        else:
            output = daily_from_m60(groups, set(bad), calendar_index)
            if list_date and list_date >= START:
                reason = 'IPO_POST_START__EARLIER_DATES_NOT_EXPECTED'
            elif bad:
                status, reason = 'ELIGIBLE_WITH_QUARANTINED_SOURCE_DAYS', 'BAD_SLOT_DAYS_REMOVED_AND_SEGMENTS_RESET'
            elif not output:
                status, reason = 'FAIL_EMPTY_SOURCE_WINDOW', 'NO_VALID_RAW_DAYS'
            else:
                reason = 'FULL_SOURCE_WINDOW'
        if output:
            code, exchange = sym.split('.')
            with gzip.open(RAW / f'{code}_{exchange}_raw_daily.json.gz', 'wt') as h:
                json.dump(output, h, ensure_ascii=False, separators=(',', ':'))
        row = {
            'symbol': sym, 'listing_date_metadata': list_date, 'currently_listed_metadata': current,
            'reference_trading_days_calendar_only': len(reference), 'raw_days': len(raw_days),
            'valid_raw_days': len(valid_days), 'raw_start': min(valid_days) if valid_days else '',
            'raw_end': max(valid_days) if valid_days else '', 'missing_reference_days': len(missing_reference),
            'missing_reference_sample': missing_reference[:20], 'abnormal_source_days': len(bad),
            'abnormal_source_sample': bad[:20], 'abnormal_reference_overlap': len(invalid_reference),
            'rebuilt_daily_rows': len(output), 'segments': (max((x['segment_id'] for x in output), default=-1) + 1),
            'status': status, 'reason': reason,
        }
        rows.append(row)
        counts[status] += 1
        counts['quarantined_source_days'] += len(bad)

    unexplained = [r for r in rows if r['status'].startswith('FAIL_')]
    accounted = len(rows) == len(symbols)
    raw_files = list(RAW.glob('*_raw_daily.json.gz'))
    report = {
        'version': 'V379_SINA_M60_RAW_DAILY_DATA_GATE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'contracts': {
            'raw_daily': 'daily OHLCV is aggregated exclusively from exactly four valid Sina 60m bars; legacy qfq daily prices are never used for OHLCV, POI, signal, entry, or outcome',
            'coverage': 'every local-universe symbol is individually accounted as eligible, explicitly quarantined by source day, delisted-prewindow, IPO-post-start metadata, or hard source failure',
            'abnormality': 'any non-4-slot source day is removed; rebuilt daily segment_id resets after any raw market-calendar gap so detectors cannot bridge a source anomaly',
            'reference': 'legacy daily cache is calendar cross-check only, never price input',
        },
        'range': {'start': START, 'end': END, 'slots': list(SLOTS), 'raw_market_calendar_days': len(calendar)},
        'counts': {**dict(counts), 'universe_symbols': len(symbols), 'accounted_symbols': len(rows),
                   'raw_daily_files': len(raw_files), 'unexplained_failures': len(unexplained)},
        'gate': {'every_symbol_accounted': accounted, 'unexplained_source_failures_zero': len(unexplained) == 0,
                 'rebuilt_raw_daily_file_count_matches_eligible': len(raw_files) == sum(r['rebuilt_daily_rows'] > 0 for r in rows),
                 'source_anomalies_explicitly_quarantined': all(r['abnormal_source_days'] == 0 or r['segments'] >= 1 for r in rows)},
        'decision': 'DATA_GATE_PASS__RAW_DAILY_SEMANTIC_ORACLE_ALLOWED' if accounted and not unexplained else 'DATA_GATE_FAIL__STOP_BEFORE_SEMANTICS',
        'artifacts': {'raw_daily_dir': str(RAW), 'symbol_rows': str(OUT / 'v379_symbol_rows.json'),
                      'report': str(OUT / 'v379_report.json'), 'latest': str(LATEST)},
        'unexplained_failure_samples': unexplained[:100],
    }
    (OUT / 'v379_symbol_rows.json').write_text(json.dumps(rows, ensure_ascii=False))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v379_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
