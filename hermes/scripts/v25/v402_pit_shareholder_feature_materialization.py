#!/usr/bin/env python3
"""V402 no-write PIT shareholder feature materialization from feasible V399 mappings.

The feature schema is fixed before any outcome file is opened. This job reads only
PIT-eligible mapping identities and the corresponding structured Top-10 holder
snapshots; it never opens V381 trade outcomes or production files.
"""
from __future__ import annotations

import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
V399 = AUD / 'v399_pit_shareholder_holdings_feasibility_latest.json'
OUT = AUD / f'v402_pit_shareholder_feature_materialization_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v402_pit_shareholder_feature_materialization_latest.json'
URL = 'https://emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/PageSDGD'
HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64)'}
WORKERS = 12

# Fixed before outcome access.  These are descriptive ownership structures, not tuned thresholds.
SCHEMA = {
    'top10_concentrated': 'sum of Top-10 reported share ratios >=50%',
    'top1_controller': 'largest reported holder ratio >=30%',
    'fund_present': 'any holder name contains 基金 or 社保基金',
    'institutional_present': 'any holder name contains 保险/证券/信托/银行/基金/社保基金/中央结算',
    'northbound_nominee_present': 'any holder name contains 香港中央结算',
}
INSTITUTION_WORDS = ('保险', '证券', '信托', '银行', '基金', '社保基金', '中央结算')


def prefix(symbol: str) -> str:
    code, market = symbol.split('.')
    return ('SH' if market == 'SH' else 'SZ') + code


def f(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def snapshot(key: tuple[str, str]) -> tuple[tuple[str, str], list[dict]]:
    symbol, period = key
    params = {'code': prefix(symbol), 'date': f'{period[:4]}-{period[4:6]}-{period[6:]}' }
    error = ''
    for attempt in range(5):
        try:
            response = requests.get(URL, params=params, headers=HEADERS, timeout=30)
            data = response.json()
            rows = data.get('sdgd') or []
            if not isinstance(rows, list):
                raise ValueError('sdgd is not a list')
            return key, rows
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
            time.sleep(0.7 * (attempt + 1))
    raise RuntimeError(error)


def features(rows: list[dict]) -> dict:
    holders = [str(row.get('HOLDER_NAME') or '') for row in rows]
    ratios = [f(row.get('HOLD_NUM_RATIO')) for row in rows]
    top1 = max(ratios, default=0.0)
    top10 = sum(ratios)
    return {
        'holder_count': len(rows), 'top1_ratio_pct': round(top1, 6), 'top10_ratio_pct': round(top10, 6),
        'top10_concentrated': top10 >= 50.0, 'top1_controller': top1 >= 30.0,
        'fund_present': any(('基金' in name or '社保基金' in name) for name in holders),
        'institutional_present': any(any(word in name for word in INSTITUTION_WORDS) for name in holders),
        'northbound_nominee_present': any('香港中央结算' in name for name in holders),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads(V399.read_text())
    mapping_path = Path(report['artifacts']['mapping'])
    with mapping_path.open(newline='', encoding='utf-8') as handle:
        eligible = [row for row in csv.DictReader(handle) if row['mapping_status'] == 'PIT_HOLDER_SNAPSHOT_READY']
    keys = sorted({(row['symbol'], row['report_end']) for row in eligible})
    data: dict[tuple[str, str], dict] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(snapshot, key): key for key in keys}
        for future in as_completed(futures):
            key = futures[future]
            try:
                got, rows = future.result()
                data[got] = features(rows)
            except Exception as exc:
                errors['|'.join(key)] = f'{type(exc).__name__}: {exc}'
    materialized = []
    for row in eligible:
        feature = data.get((row['symbol'], row['report_end']))
        if feature:
            materialized.append({
                'symbol': row['symbol'], 'entry_date': row['entry_date'], 'report_end': row['report_end'],
                'notice_date': row['notice_date'], 'publication_time': row['publication_time'],
                'announcement_id': row['announcement_id'], **feature,
            })
    fields = list(materialized[0]) if materialized else ['symbol']
    with (OUT / 'v402_pit_shareholder_features.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(materialized)
    yearly = {}
    for year in ('2023', '2024', '2025', '2026'):
        subset = [row for row in materialized if row['entry_date'].startswith(year)]
        yearly[year] = {'n': len(subset)}
    result = {
        'version': 'V402_PIT_SHAREHOLDER_FEATURE_MATERIALIZATION_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'input_contract': 'V399 PIT_HOLDER_SNAPSHOT_READY rows only; mapping had report_end and notice_date strictly before entry',
        'fixed_feature_schema': SCHEMA,
        'counts': {'eligible_identities': len(eligible), 'unique_snapshots': len(keys),
                   'snapshots_materialized': len(data), 'snapshot_errors': len(errors),
                   'materialized_identities': len(materialized)},
        'yearly': yearly,
        'outcome_replay_allowed_next': len(errors) == 0 and len(materialized) == len(eligible),
        'invariants': {'outcome_fields_read': False, 'no_production_write': True,
                       'no_frontend_write': True, 'no_watchlist_write': True},
        'artifacts': {'out_dir': str(OUT), 'features': str(OUT / 'v402_pit_shareholder_features.csv'),
                      'latest': str(LATEST), 'errors': errors},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v402_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
