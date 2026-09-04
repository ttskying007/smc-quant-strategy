#!/usr/bin/env python3
"""V400 no-write pilot: distinguish V399 metadata transport failure from real PIT gaps.

Reads only the failed V399 symbol list, requests public announcement metadata with
bounded concurrency and retries, and never reads trade outcomes or holder values.
"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
SRC = AUD / 'v399_pit_shareholder_holdings_feasibility_latest.json'
OUT = AUD / f'v400_announcement_metadata_recovery_pilot_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v400_announcement_metadata_recovery_pilot_latest.json'
API = 'https://np-anotice-stock.eastmoney.com/api/security/ann'
PILOT_N = 100
WORKERS = 4
REPORT_RE = re.compile(r'20\d{2}年(?:第一季度|半年度|第三季度|年度)报告')


def fetch_symbol(symbol: str) -> dict:
    code = symbol[:6]
    session = requests.Session()
    notices: list[dict] = []
    page = 1
    total = None
    while page <= 10:
        params = {
            'client_source': 'web', 'page_size': 100, 'page_index': page,
            'ann_type': 'A', 'stock_list': code,
            'begin_time': '2022-01-01', 'end_time': '2026-07-12',
        }
        response = None
        error = ''
        for attempt in range(3):
            try:
                response = session.get(API, params=params, timeout=30,
                                       headers={'User-Agent': 'Mozilla/5.0'})
                payload = response.json()
                if payload.get('success') != 1:
                    raise ValueError(f"api_success={payload.get('success')}")
                break
            except Exception as exc:
                error = f'{type(exc).__name__}: {exc}'
                response = None
                time.sleep(0.8 * (attempt + 1))
        if response is None:
            return {'symbol': symbol, 'ok': False, 'error': error, 'pages': page - 1, 'report_count': 0}
        data = payload.get('data') or {}
        items = data.get('list') or []
        total = int(data.get('total_hits') or 0)
        notices.extend(items)
        if page * 100 >= total or not items:
            break
        page += 1
        time.sleep(0.15)
    reports = []
    for item in notices:
        title = item.get('title') or ''
        if REPORT_RE.search(title) and '摘要' not in title and '提示' not in title and '预约' not in title:
            reports.append({
                'id': item.get('art_code', ''), 'title': title,
                'notice_date': item.get('notice_date', ''),
                'publication_time': item.get('eiTime', ''),
            })
    return {
        'symbol': symbol, 'ok': True, 'error': '', 'pages': page,
        'total_hits': total, 'report_count': len(reports), 'reports': reports,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads(SRC.read_text())
    symbols = list(source['errors']['announcement_metadata'])[:PILOT_N]
    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(fetch_symbol, symbol) for symbol in symbols]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda row: row['symbol'])
    successful = [row for row in results if row['ok']]
    usable = [row for row in successful if row['report_count'] > 0]
    report = {
        'version': 'V400_ANNOUNCEMENT_METADATA_RECOVERY_PILOT_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'input_contract': 'only V399 metadata-failed symbols; no outcome, holder-value, or trade-result fields read',
        'transport_contract': 'Eastmoney public announcement endpoint; page_size=100; max 10 pages; 3 retries; 4 workers',
        'pilot': {'symbols_requested': len(symbols), 'metadata_http_ok': len(successful),
                  'official_periodic_report_available': len(usable),
                  'http_ok_pct': round(100 * len(successful) / len(symbols), 2) if symbols else 0,
                  'report_available_pct': round(100 * len(usable) / len(symbols), 2) if symbols else 0},
        'decision': ('RECOVERY_PATH_VALID__RUN_FULL_METADATA_RECOVERY_NEXT'
                     if len(successful) >= int(len(symbols) * 0.95) else
                     'RECOVERY_PATH_UNRELIABLE__KEEP_V399_CLOSED'),
        'invariants': {'no_outcome_fields_read': True, 'no_production_write': True,
                       'no_frontend_write': True, 'no_watchlist_write': True},
        'artifacts': {'out_dir': str(OUT), 'results': str(OUT / 'v400_pilot_results.json'), 'latest': str(LATEST)},
    }
    (OUT / 'v400_pilot_results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v400_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
