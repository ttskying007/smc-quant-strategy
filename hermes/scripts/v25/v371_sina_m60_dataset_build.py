#!/usr/bin/env python3
"""V371: build a resumable, research-only Sina 60-minute OHLCV cache.

The script is deliberately a data-layer operation only. It writes compressed raw
source bars and a manifest under intraday_cache; it never creates signals, trades,
watchlists, production files, or frontend data.
"""
from __future__ import annotations

import gzip
import json
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import requests

ROOT = Path('/root/.hermes')
DAILY = ROOT / 'kline_cache'
CACHE = ROOT / 'intraday_cache' / 'sina_m60_v1'
AUDIT = ROOT / 'smc_audit'
MANIFEST = CACHE / 'manifest.jsonl'
LATEST = AUDIT / 'v371_sina_m60_dataset_build_latest.json'
URL = 'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData'
HEADERS = {'User-Agent': 'Mozilla/5.0'}
START_YEAR = '2023'
WORKERS = 6
RETRIES = 3


def universe() -> list[tuple[str, str]]:
    rows = []
    for path in DAILY.glob('*_daily_750.json'):
        match = re.fullmatch(r'(\d+)_(SH|SZ)_daily_750\.json', path.name)
        if match:
            rows.append((match.group(1), match.group(2)))
    return sorted(set(rows))


def output_path(code: str, exchange: str) -> Path:
    return CACHE / f'{code}_{exchange}_m60_sina.json.gz'


def usable_existing(path: Path) -> bool:
    try:
        with gzip.open(path, 'rt') as handle:
            rows = json.load(handle)
        return isinstance(rows, list) and len(rows) >= 100
    except Exception:
        return False


def quality(rows: list[dict]) -> dict:
    dates = [str(row.get('day') or '') for row in rows]
    years = Counter(d[:4] for d in dates if len(d) >= 4)
    days = Counter(d[:10] for d in dates if len(d) >= 10)
    # The first source date is allowed to be truncated; all later non-4-slot
    # dates are retained as source facts rather than silently repaired.
    first_day = min(days) if days else ''
    non_first_bad_days = sum(1 for day, count in days.items() if day != first_day and count != 4)
    return {
        'bars': len(rows),
        'first': dates[0] if dates else '',
        'last': dates[-1] if dates else '',
        'year_bars': dict(years),
        'days': len(days),
        'non_first_bad_day_count': non_first_bad_days,
        'has_2023': years.get(START_YEAR, 0) > 0,
    }


def fetch(item: tuple[str, str]) -> dict:
    code, exchange = item
    path = output_path(code, exchange)
    symbol = ('sh' if exchange == 'SH' else 'sz') + code
    if usable_existing(path):
        with gzip.open(path, 'rt') as handle:
            rows = json.load(handle)
        return {'symbol': f'{code}.{exchange}', 'source': 'cache', 'status': 'OK', **quality(rows)}
    params = {'symbol': symbol, 'scale': '60', 'ma': 'no', 'datalen': '10000'}
    err = ''
    for attempt in range(RETRIES):
        try:
            response = requests.get(URL, params=params, headers=HEADERS, timeout=30)
            response.raise_for_status()
            rows = response.json()
            if not isinstance(rows, list) or not rows:
                raise ValueError('empty_or_non_list_response')
            info = quality(rows)
            if not info['has_2023'] and info['first'] < '2023':
                raise ValueError('missing_2023_despite_pre2023_history')
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(path.suffix + '.tmp')
            with gzip.open(temp, 'wt') as handle:
                json.dump(rows, handle, ensure_ascii=False, separators=(',', ':'))
            temp.replace(path)
            return {'symbol': f'{code}.{exchange}', 'source': 'network', 'status': 'OK', **info}
        except Exception as exc:
            err = f'{type(exc).__name__}: {exc}'
            time.sleep(1 + attempt)
    return {'symbol': f'{code}.{exchange}', 'source': 'network', 'status': 'FAIL', 'error': err}


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out = AUDIT / f'v371_sina_m60_dataset_build_no_write_{timestamp}'
    out.mkdir(parents=True, exist_ok=True)
    symbols = universe()
    results: list[dict] = []
    started = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(fetch, item): item for item in symbols}
        for index, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if index % 100 == 0 or index == len(symbols):
                ok = sum(row['status'] == 'OK' for row in results)
                print(json.dumps({'progress': index, 'total': len(symbols), 'ok': ok,
                                  'elapsed_s': round(time.time() - started, 1)}, ensure_ascii=False), flush=True)
    results.sort(key=lambda row: row['symbol'])
    with MANIFEST.open('w') as handle:
        for row in results:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    failures = [row for row in results if row['status'] != 'OK']
    low_coverage = [row for row in results if row['status'] == 'OK' and not row['has_2023']]
    report = {
        'version': 'V371_SINA_M60_DATASET_BUILD_RESEARCH_ONLY',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'source': URL,
        'contract': 'raw 60-minute OHLCV only; entry-model research is prohibited until this dataset audit passes',
        'universe_symbols': len(symbols),
        'success_count': len(results) - len(failures),
        'failure_count': len(failures),
        'missing_2023_count': len(low_coverage),
        'quality': {
            'total_non_first_bad_day_count': sum(row.get('non_first_bad_day_count', 0) for row in results),
            'year_symbols': {year: sum(row.get('year_bars', {}).get(year, 0) > 0 for row in results if row['status'] == 'OK') for year in ('2023', '2024', '2025', '2026')},
        },
        'decision': 'DATASET_READY_FOR_CAUSAL_MTF_GENERATOR' if not failures else 'DATASET_INCOMPLETE__RETRY_OR_REPAIR_BEFORE_MTF_RESEARCH',
        'artifacts': {'manifest': str(MANIFEST), 'rows': str(out / 'v371_source_rows.json'), 'latest': str(LATEST)},
        'failures_sample': failures[:100],
    }
    (out / 'v371_source_rows.json').write_text(json.dumps(results, ensure_ascii=False))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (out / 'v371_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
