#!/usr/bin/env python3
"""V393 no-write PIT 龙虎榜 availability gate for frozen V381 identities.

Uses only a 龙虎榜 record from a strictly earlier trading day than the
completed 60m hold time, avoiding any same-day publication-time ambiguity.
No outcome field is read or emitted.
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
OUT = AUD / f'v393_pit_lhb_availability_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v393_pit_lhb_availability_latest.json'
URL = 'http://datacenter-web.eastmoney.com/api/data/v1/get'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}
COLUMNS = 'TRADE_DATE,SECURITY_CODE,SECURITY_NAME_ABBR,BILLBOARD_NET_AMT,EXPLANATION'
LOOKBACK_CALENDAR_DAYS = 30


def fetch_year(session: requests.Session, year: int) -> tuple[list[dict], str | None, int]:
    params = {
        'reportName': 'RPT_DAILYBILLBOARD_DETAILSNEW', 'columns': COLUMNS,
        'filter': f"(TRADE_DATE>='{year}-01-01')(TRADE_DATE<='{year}-12-31')",
        'pageNumber': '1', 'pageSize': '500', 'sortColumns': 'TRADE_DATE',
        'sortTypes': '1', 'source': 'WEB', 'client': 'WEB',
    }
    try:
        first = session.get(URL, params=params, timeout=40)
        first.raise_for_status()
        result = first.json().get('result') or {}
        pages = int(result.get('pages') or 0)
        rows = list(result.get('data') or [])
        if pages < 1:
            return rows, f'EMPTY_OR_MISSING_PAGES:{year}', 1
        for page in range(2, pages + 1):
            params['pageNumber'] = str(page)
            response = session.get(URL, params=params, timeout=40)
            response.raise_for_status()
            batch = (response.json().get('result') or {}).get('data') or []
            if not batch:
                return rows, f'EMPTY_PAGE:{year}:{page}', page
            rows.extend(batch)
        expected = int(result.get('count') or 0)
        if len(rows) != expected:
            return rows, f'COUNT_MISMATCH:{year}:{len(rows)}!={expected}', pages
        return rows, None, pages
    except Exception as exc:
        return [], f'{type(exc).__name__}:{exc}', 0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads(V381.read_text())
    # Deliberately access only source identity and the pre-entry feature cutoff.
    with Path(report['artifacts']['trades']).open(newline='') as handle:
        targets = sorted({(row['symbol'], row['hold_time']) for row in csv.DictReader(handle)})
    min_year = min(int(hold[:4]) for _, hold in targets)
    max_year = max(int(hold[:4]) for _, hold in targets)

    session = requests.Session()
    session.trust_env = False
    session.headers.update(HEADERS)
    records, failures, request_pages = [], [], 0
    for year in range(min_year, max_year + 1):
        rows, error, pages = fetch_year(session, year)
        records.extend(rows)
        request_pages += pages
        if error:
            failures.append({'year': year, 'error': error, 'rows': len(rows)})

    by_code: dict[str, list[dict]] = defaultdict(list)
    clean_records = []
    for row in records:
        code = str(row.get('SECURITY_CODE') or '').zfill(6)
        day = str(row.get('TRADE_DATE') or '')[:10]
        if len(day) == 10 and code.isdigit():
            item = {'trade_date': day, 'net_amt': float(row.get('BILLBOARD_NET_AMT') or 0.0), 'code': code}
            by_code[code].append(item)
            clean_records.append(item)
    for values in by_code.values():
        values.sort(key=lambda item: item['trade_date'])

    features = []
    for symbol, hold_time in targets:
        cutoff = hold_time[:10]
        start = (datetime.strptime(cutoff, '%Y-%m-%d') - timedelta(days=LOOKBACK_CALENDAR_DAYS)).date().isoformat()
        prior = [item for item in by_code.get(symbol[:6], []) if start <= item['trade_date'] < cutoff]
        features.append({
            'symbol': symbol, 'hold_time': hold_time, 'feature_cutoff': hold_time,
            'lookback_start': start, 'lookback_calendar_days': LOOKBACK_CALENDAR_DAYS,
            'lhb_prior_events': len(prior),
            'lhb_prior_positive_events': sum(item['net_amt'] > 0 for item in prior),
            'lhb_prior_net_amt': round(sum(item['net_amt'] for item in prior), 2),
            'lhb_latest_prior_date': prior[-1]['trade_date'] if prior else '',
            'source_contract': 'Eastmoney LHB; TRADE_DATE strictly earlier than hold date',
        })

    feature_path = OUT / 'v393_lhb_availability_features.csv'
    with feature_path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(features[0]))
        writer.writeheader(); writer.writerows(features)
    raw_path = OUT / 'v393_lhb_raw_records.csv'
    with raw_path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['trade_date', 'code', 'net_amt'])
        writer.writeheader(); writer.writerows(clean_records)

    gate = {
        'target_rows': len(targets), 'feature_rows': len(features),
        'years_fetched': list(range(min_year, max_year + 1)), 'request_pages': request_pages,
        'query_failures': len(failures), 'all_targets_accounted': len(features) == len(targets),
        'all_year_queries_complete': not failures,
        'all_feature_cutoffs_equal_hold_time': all(row['feature_cutoff'] == row['hold_time'] for row in features),
        'all_lhb_dates_strictly_before_cutoff': all(not row['lhb_latest_prior_date'] or row['lhb_latest_prior_date'] < row['hold_time'][:10] for row in features),
        'outcome_fields_read_or_emitted': False,
    }
    passed = all((gate['all_targets_accounted'], gate['all_year_queries_complete'],
                  gate['all_feature_cutoffs_equal_hold_time'], gate['all_lhb_dates_strictly_before_cutoff'],
                  not gate['outcome_fields_read_or_emitted']))
    result = {
        'version': 'V393_PIT_LHB_AVAILABILITY_GATE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'contract': 'strictly prior-day Eastmoney 龙虎榜 events; frozen V381 identity/time only',
        'gate': gate,
        'decision': 'PIT_LHB_AVAILABILITY_PASS__OUTCOME_BLIND_REPLAY_ALLOWED' if passed else 'PIT_LHB_AVAILABILITY_FAIL__STOP',
        'artifacts': {'features': str(feature_path), 'raw_records': str(raw_path), 'latest': str(LATEST)},
        'failure_samples': failures,
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v393_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
