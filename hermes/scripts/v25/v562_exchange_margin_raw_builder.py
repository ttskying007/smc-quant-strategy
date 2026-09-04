#!/usr/bin/env python3
"""V562 resumable source-isolated SH/SZ stock-margin history builder.

Builds only raw prior-date capital information. It is not a signal generator and
reads neither trades nor outcomes. Each exchange/date is atomic and resumable.
"""
from __future__ import annotations

import argparse
import gzip
import json
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests

ROOT = Path('/root/.hermes')
KLINE = ROOT / 'kline_cache'
BASE = ROOT / 'pit_cache' / 'v562_exchange_margin_raw'
AUD = ROOT / 'smc_audit'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36'


def trading_dates() -> list[str]:
    dates: set[str] = set()
    for path in KLINE.glob('*_daily_750.json'):
        try:
            for row in json.loads(path.read_text()):
                d = str(row.get('t') or row.get('date') or '')[:8]
                if '20230101' <= d <= '20261231':
                    dates.add(d)
        except (OSError, ValueError, TypeError):
            continue
    return sorted(dates)


def sse(date: str) -> list[dict[str, Any]]:
    params = {'isPagination': 'true', 'tabType': 'mxtype', 'detailsDate': date, 'stockCode': '', 'beginDate': '', 'endDate': '',
              'pageHelp.pageSize': '5000', 'pageHelp.pageCount': '50', 'pageHelp.pageNo': '1', 'pageHelp.beginPage': '1',
              'pageHelp.cacheSize': '1', 'pageHelp.endPage': '21'}
    r = requests.get('https://query.sse.com.cn/marketdata/tradedata/queryMargin.do', params=params,
                     headers={'User-Agent': UA, 'Referer': 'https://www.sse.com.cn/'}, timeout=45)
    r.raise_for_status(); rows = r.json().get('result') or []
    if not rows or not all(str(x.get('opDate')) == date and x.get('stockCode') for x in rows):
        raise RuntimeError(f'SSE_SCHEMA_OR_DATE_INVALID:{date}:n={len(rows)}')
    return [{'code': str(x['stockCode']).zfill(6), 'name': str(x.get('securityAbbr') or ''),
             'financing_buy': float(x.get('rzmre') or 0), 'financing_repay': float(x.get('rzche') or 0),
             'financing_balance': float(x.get('rzye') or 0), 'lending_sell': float(x.get('rqmcl') or 0),
             'lending_balance': float(x.get('rqyl') or 0)} for x in rows]


def szse(date: str) -> list[dict[str, Any]]:
    iso = f'{date[:4]}-{date[4:6]}-{date[6:]}'
    params = {'SHOWTYPE': 'xlsx', 'CATALOGID': '1837_xxpl', 'txtDate': iso, 'tab2PAGENO': '1', 'random': '0.24279342734085696', 'TABKEY': 'tab2'}
    r = requests.get('https://www.szse.cn/api/report/ShowReport', params=params,
                     headers={'User-Agent': UA, 'Referer': 'https://www.szse.cn/disclosure/margin/margin/index.html'}, timeout=45)
    r.raise_for_status(); df = pd.read_excel(BytesIO(r.content), engine='openpyxl', dtype=str)
    code = next((x for x in df.columns if '证券代码' in str(x)), None)
    buy = next((x for x in df.columns if '融资买入额' in str(x)), None)
    bal = next((x for x in df.columns if '融资余额' in str(x)), None)
    if not code or not buy or not bal or len(df) < 500:
        raise RuntimeError(f'SZSE_SCHEMA_OR_DATE_INVALID:{date}:n={len(df)}')
    def num(x: Any) -> float:
        try: return float(str(x).replace(',', '').replace('&nbsp;', '').strip() or 0)
        except ValueError: return 0.0
    return [{'code': str(row[code]).zfill(6), 'name': str(row.get('证券简称') or '').replace('&nbsp;', '').strip(),
             'financing_buy': num(row[buy]), 'financing_repay': 0.0, 'financing_balance': num(row[bal]),
             'lending_sell': num(row.get('融券卖出量')), 'lending_balance': num(row.get('融券余量'))}
            for _, row in df.iterrows() if str(row[code]).strip().isdigit()]


def output(exchange: str, date: str) -> Path:
    return BASE / exchange / f'{date}.json.gz'


def valid(path: Path, date: str, exchange: str) -> bool:
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f: doc = json.load(f)
        return doc.get('date') == date and doc.get('exchange') == exchange and len(doc.get('rows') or []) >= 500
    except (OSError, ValueError, TypeError):
        return False


def store(exchange: str, date: str, rows: list[dict[str, Any]]) -> None:
    path = output(exchange, date); path.parent.mkdir(parents=True, exist_ok=True)
    doc = {'source': f'{exchange}_official_exchange', 'source_kind': 'provider_raw', 'exchange': exchange, 'date': date,
           'requested_range': date, 'received_range': date, 'provider_timestamp': datetime.now().isoformat(timespec='seconds'),
           'publication_timing_contract': 'feature may only be used on a later completed exchange session; never same-date',
           'rows': rows}
    tmp = path.with_suffix('.tmp')
    with gzip.open(tmp, 'wt', encoding='utf-8') as f: json.dump(doc, f, ensure_ascii=False, separators=(',', ':'))
    tmp.replace(path)


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument('--limit', type=int, default=20); ap.add_argument('--pause', type=float, default=0.20); args = ap.parse_args()
    dates = trading_dates()
    # The final daily-cache session is the current scanner tail.  Its official
    # exchange-margin report cannot be used until a later completed exchange
    # session anyway, so treating its not-yet-published file as a build failure
    # would both misstate PIT availability and make the durable builder retry a
    # non-actionable request forever.  On the next cache advance it becomes an
    # eligible prior session and is retried normally.
    pending_publication_tail = dates[-1:] if dates else []
    eligible_dates = dates[:-1]
    missing = [(d, ex) for d in eligible_dates for ex in ('SH', 'SZ') if not valid(output(ex, d), d, ex)]
    batch = missing[:max(args.limit, 1)]
    done = failed = 0; errors = []
    for pos, (date, ex) in enumerate(batch, 1):
        try:
            rows = sse(date) if ex == 'SH' else szse(date); store(ex, date, rows); done += 1
            print(f'OK {pos}/{len(batch)} {ex} {date} rows={len(rows)}', flush=True)
        except Exception as exc:
            failed += 1; errors.append({'exchange': ex, 'date': date, 'error': f'{type(exc).__name__}:{exc}'})
            print(f'FAIL {pos}/{len(batch)} {ex} {date} {errors[-1]["error"]}', flush=True)
        time.sleep(max(args.pause, 0))
    remaining = len(missing) - done
    report = {'version': 'V562_EXCHANGE_MARGIN_RAW_BUILD_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
              'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
              'contract': 'Raw exchange margin history only; no outcome/trade files read; only strictly prior-session use will ever be allowed.',
              'date_denominator_from_daily_cache': len(dates), 'eligible_prior_session_dates': len(eligible_dates),
              'pit_pending_publication_tail': pending_publication_tail,
              'missing_before': len(missing), 'requested': len(batch), 'completed': done,
              'failed': failed, 'remaining_estimate': remaining, 'errors': errors[:20],
              'decision': ('SOURCE_BUILD_IN_PROGRESS' if remaining
                           else 'SOURCE_BUILD_COMPLETE_FOR_AVAILABLE_PRIOR_SESSIONS__CURRENT_TAIL_PENDING_PUBLICATION')}
    latest = AUD / 'v562_exchange_margin_raw_build_latest.json'; latest.write_text(json.dumps(report, ensure_ascii=False, indent=2)); print(json.dumps(report, ensure_ascii=False))

if __name__ == '__main__': main()
