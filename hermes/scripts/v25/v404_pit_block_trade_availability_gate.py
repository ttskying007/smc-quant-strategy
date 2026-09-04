#!/usr/bin/env python3
"""V404 no-write PIT block-trade availability gate for frozen V381 identities.

Uses Eastmoney A-share block-trade records from dates strictly earlier than the
completed 60-minute hold time. It emits source features only: no outcome,
entry/exit, PnL, or selector is read or created.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
V381 = AUD / 'v381_true_mtf_raw_daily_poi_m60_replay_latest.json'
OUT = AUD / f'v404_pit_block_trade_availability_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v404_pit_block_trade_availability_latest.json'
URL = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}
COLUMNS = 'TRADE_DATE,SECURITY_CODE,DEAL_AMT,PREMIUM_RATIO,BUYER_NAME,SELLER_NAME'
LOOKBACK_CALENDAR_DAYS = 30


def fetch_year(session: requests.Session, year: int) -> tuple[list[dict], str | None, int]:
    params = {
        'reportName': 'RPT_DATA_BLOCKTRADE', 'columns': COLUMNS,
        'filter': f"(SECURITY_TYPE_WEB=1)(TRADE_DATE>='{year}-01-01')(TRADE_DATE<='{year}-12-31')",
        'pageNumber': '1', 'pageSize': '5000', 'sortColumns': 'TRADE_DATE,SECURITY_CODE',
        'sortTypes': '-1,1', 'source': 'WEB', 'client': 'WEB',
    }
    try:
        response = session.get(URL, params=params, timeout=60)
        response.raise_for_status()
        result = response.json().get('result') or {}
        expected, pages = int(result.get('count') or 0), int(result.get('pages') or 0)
        rows = list(result.get('data') or [])
        if pages < 1:
            return rows, f'EMPTY_OR_MISSING_PAGES:{year}', 1
        for page in range(2, pages + 1):
            params['pageNumber'] = str(page)
            response = session.get(URL, params=params, timeout=60)
            response.raise_for_status()
            batch = (response.json().get('result') or {}).get('data') or []
            if not batch:
                return rows, f'EMPTY_PAGE:{year}:{page}', page
            rows.extend(batch)
        if len(rows) != expected:
            return rows, f'COUNT_MISMATCH:{year}:{len(rows)}!={expected}', pages
        return rows, None, pages
    except Exception as exc:
        return [], f'{type(exc).__name__}:{exc}', 0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads(V381.read_text())
    # Read only immutable identity and source cutoff; deliberately never load outcomes.
    with Path(report['artifacts']['trades']).open(newline='') as handle:
        targets = sorted({(row['symbol'], row['hold_time']) for row in csv.DictReader(handle)})
    years = range(min(int(hold[:4]) for _, hold in targets), max(int(hold[:4]) for _, hold in targets) + 1)

    session = requests.Session()
    session.trust_env = False
    session.headers.update(HEADERS)
    records, failures, request_pages = [], [], 0
    for year in years:
        rows, error, pages = fetch_year(session, year)
        records.extend(rows)
        request_pages += pages
        if error:
            failures.append({'year': year, 'error': error, 'rows': len(rows)})

    by_code: dict[str, list[dict]] = defaultdict(list)
    raw = []
    for row in records:
        code = str(row.get('SECURITY_CODE') or '').zfill(6)
        trade_date = str(row.get('TRADE_DATE') or '')[:10]
        if not (code.isdigit() and len(trade_date) == 10):
            continue
        amount = float(row.get('DEAL_AMT') or 0.0)
        premium = float(row.get('PREMIUM_RATIO') or 0.0)
        buyer, seller = str(row.get('BUYER_NAME') or ''), str(row.get('SELLER_NAME') or '')
        item = {
            'trade_date': trade_date, 'code': code, 'deal_amt': amount,
            'premium_ratio': premium, 'institution_buyer': '机构专用' in buyer,
            'institution_seller': '机构专用' in seller,
        }
        by_code[code].append(item)
        raw.append(item)
    for items in by_code.values():
        items.sort(key=lambda item: item['trade_date'])

    features = []
    for symbol, hold_time in targets:
        cutoff = hold_time[:10]
        start = (datetime.strptime(cutoff, '%Y-%m-%d') - timedelta(days=LOOKBACK_CALENDAR_DAYS)).date().isoformat()
        prior = [item for item in by_code.get(symbol[:6], []) if start <= item['trade_date'] < cutoff]
        features.append({
            'symbol': symbol, 'hold_time': hold_time, 'feature_cutoff': hold_time,
            'lookback_start': start, 'lookback_calendar_days': LOOKBACK_CALENDAR_DAYS,
            'block_prior_events': len(prior),
            'block_prior_amount': round(sum(item['deal_amt'] for item in prior), 2),
            'block_prior_discount_amount': round(sum(item['deal_amt'] for item in prior if item['premium_ratio'] < 0), 2),
            'block_prior_institution_buy_amount': round(sum(item['deal_amt'] for item in prior if item['institution_buyer']), 2),
            'block_prior_institution_sell_amount': round(sum(item['deal_amt'] for item in prior if item['institution_seller']), 2),
            'block_latest_prior_date': prior[-1]['trade_date'] if prior else '',
            'source_contract': 'Eastmoney block trades; TRADE_DATE strictly earlier than completed hold time',
        })

    feature_path = OUT / 'v404_block_trade_availability_features.csv'
    with feature_path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(features[0]))
        writer.writeheader(); writer.writerows(features)
    raw_path = OUT / 'v404_block_trade_raw_records.csv'
    with raw_path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['trade_date', 'code', 'deal_amt', 'premium_ratio', 'institution_buyer', 'institution_seller'])
        writer.writeheader(); writer.writerows(raw)

    gate = {
        'target_rows': len(targets), 'feature_rows': len(features), 'years_fetched': list(years),
        'request_pages': request_pages, 'raw_records': len(raw), 'query_failures': len(failures),
        'all_targets_accounted': len(features) == len(targets), 'all_year_queries_complete': not failures,
        'all_feature_cutoffs_equal_hold_time': all(row['feature_cutoff'] == row['hold_time'] for row in features),
        'all_block_dates_strictly_before_cutoff': all(not row['block_latest_prior_date'] or row['block_latest_prior_date'] < row['hold_time'][:10] for row in features),
        'outcome_fields_read_or_emitted': False,
    }
    passed = all((gate['all_targets_accounted'], gate['all_year_queries_complete'],
                  gate['all_feature_cutoffs_equal_hold_time'], gate['all_block_dates_strictly_before_cutoff'],
                  not gate['outcome_fields_read_or_emitted']))
    result = {
        'version': 'V404_PIT_BLOCK_TRADE_AVAILABILITY_GATE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'contract': 'strictly prior-date Eastmoney A-share block trades; frozen V381 identity/time only',
        'gate': gate,
        'decision': 'PIT_BLOCK_TRADE_AVAILABILITY_PASS__OUTCOME_BLIND_REPLAY_ALLOWED' if passed else 'PIT_BLOCK_TRADE_AVAILABILITY_FAIL__STOP',
        'artifacts': {'features': str(feature_path), 'raw_records': str(raw_path), 'latest': str(LATEST)},
        'failure_samples': failures,
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v404_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
