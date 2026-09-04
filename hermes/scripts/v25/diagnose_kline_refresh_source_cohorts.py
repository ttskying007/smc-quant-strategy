#!/usr/bin/env python3
"""Outcome-free diagnosis of daily K-line provider/date cohorts."""
from __future__ import annotations

import concurrent.futures
import importlib.util
import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
MODULE_PATH = ROOT / 'scripts/v25/refresh_daily_750.py'
AUDIT = ROOT / 'smc_audit'
OUT = AUDIT / 'kline_refresh_source_cohort_diagnosis_latest.json'

spec = importlib.util.spec_from_file_location('refresh_daily_750', MODULE_PATH)
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)


def main() -> None:
    symbols = {}
    for pattern in ('*_daily_750.json', '*_daily_300.json'):
        for path in refresh.KLINE_DIR.glob(pattern):
            symbol = refresh.symbol_from_file(path)
            if symbol:
                symbols[symbol] = True
    items = sorted(symbols)
    run_id = datetime.now().strftime('%Y%m%dT%H%M%S_%f')
    stage = AUDIT / f'kline_refresh_source_probe_{run_id}'
    stage.mkdir(parents=True)
    results = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(refresh.fetch_one, item, stage) for item in items]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    buckets = Counter()
    errors = Counter()
    latest = Counter()
    source = Counter()
    market = Counter()
    source_market_latest = Counter()
    stale_samples = []
    for row in results:
        mkt = row.get('market', 'unknown')
        market[mkt] += 1
        if not row.get('ok'):
            error = row.get('error', 'UNKNOWN')
            errors[(mkt, error)] += 1
            buckets[('FAIL', mkt, error)] += 1
            if len(stale_samples) < 100:
                stale_samples.append(row)
            continue
        src = row.get('source', 'unknown')
        day = str(row.get('latest') or '')[:8]
        rows = int(row.get('rows') or 0)
        band = '<100' if rows < 100 else ('100-299' if rows < 300 else ('300-749' if rows < 750 else '750'))
        source[src] += 1
        latest[day] += 1
        source_market_latest[(src, mkt, day)] += 1
        buckets[(src, mkt, day, band)] += 1
        if day != max(latest.keys(), default=day) and len(stale_samples) < 100:
            stale_samples.append({k: row.get(k) for k in ('code', 'market', 'source', 'latest', 'rows')})

    newest = max(latest, default='')
    stale = [row for row in results if row.get('ok') and str(row.get('latest') or '')[:8] != newest]
    report = {
        'version': 'KLINE_REFRESH_SOURCE_COHORT_DIAGNOSIS_V1',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'outcome_fields_read': False,
        'requested': len(items),
        'accounted': len(results),
        'accounting_pass': len(items) == len(results),
        'ok': sum(bool(row.get('ok')) for row in results),
        'failed': sum(not row.get('ok') for row in results),
        'newest_observed_date': newest,
        'latest_counts': dict(sorted(latest.items())),
        'source_counts': dict(source),
        'market_counts': dict(market),
        'source_market_latest': [
            {'source': key[0], 'market': key[1], 'latest': key[2], 'count': count}
            for key, count in sorted(source_market_latest.items())
        ],
        'row_buckets': [
            {'bucket': list(key), 'count': count}
            for key, count in sorted(buckets.items(), key=lambda item: str(item[0]))
        ],
        'error_counts': [
            {'market': key[0], 'error': key[1], 'count': count}
            for key, count in sorted(errors.items())
        ],
        'non_newest_count': len(stale),
        'non_newest_by_source_market': dict(Counter(f"{row.get('source')}|{row.get('market')}" for row in stale)),
        'non_newest_samples': [
            {k: row.get(k) for k in ('code', 'market', 'source', 'latest', 'rows')}
            for row in stale[:100]
        ],
        'decision': 'DIAGNOSIS_ONLY__NO_PRODUCTION_WRITE',
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
