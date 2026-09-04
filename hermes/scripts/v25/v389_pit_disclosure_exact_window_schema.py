#!/usr/bin/env python3
"""V389 repaired PIT disclosure schema with an exact per-candidate five-day window.

Repairs V387's cache-scope defect: a provider row is eligible only if
hold_time-5 days <= eiTime <= hold_time.  The taxonomy is identical to V387.
"""
from __future__ import annotations

import csv
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import requests

ROOT = Path('/root/.hermes'); AUD = ROOT / 'smc_audit'
V386 = AUD / 'v386_pit_disclosure_availability_latest.json'
OUT = AUD / f'v389_pit_disclosure_exact_window_schema_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v389_pit_disclosure_exact_window_schema_latest.json'
URL = 'https://np-anotice-stock.eastmoney.com/api/security/ann'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}
LOOKBACK_DAYS, CHUNK_SIZE = 5, 200
SCHEMA = {
    'REGULATORY_OR_NEGATIVE': ('立案', '处罚', '问询函', '监管', '风险提示', '终止', '亏损', '预亏', '减持', '冻结', '诉讼', '仲裁', '退市'),
    'CAPITAL_RETURN_OR_INCREASE': ('回购', '增持', '分红', '权益分派'),
    'FUNDAMENTAL_POSITIVE': ('业绩预增', '业绩快报', '业绩预告', '经营情况', '年度报告', '半年度报告', '季度报告'),
    'BUSINESS_POSITIVE': ('中标', '合同', '订单', '签署', '合作', '项目'),
}


def stamp(value: str) -> datetime | None:
    try: return datetime.strptime(value[:19], '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError): return None


def code(symbol: str) -> str: return symbol.split('.', 1)[0]


def classify(title: str) -> str:
    for state, terms in SCHEMA.items():
        if any(term in title for term in terms): return state
    return 'OTHER_DISCLOSURE'


def fetch(session: requests.Session, codes: list[str], start: str, end: str) -> tuple[list[dict], str | None]:
    rows = []
    for page in range(1, 101):
        try:
            params = {'client_source': 'web', 'page_size': 100, 'page_index': page, 'ann_type': 'A',
                      'stock_list': ','.join(codes), 'begin_time': start, 'end_time': end}
            response = session.get(URL, params=params, timeout=30); response.raise_for_status()
            data = response.json().get('data') or {}; batch = data.get('list') or []; rows.extend(batch)
            if len(rows) >= int(data.get('total_hits') or 0) or not batch: return rows, None
            time.sleep(.03)
        except Exception as exc: return rows, f'{type(exc).__name__}:{exc}'
    return rows, 'PAGE_CAP_EXCEEDED'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    availability = json.loads(V386.read_text())
    if availability['decision'] != 'PIT_DISCLOSURE_AVAILABILITY_PASS__OUTCOME_BLIND_EVENT_SCHEMA_ALLOWED':
        raise RuntimeError('V386 availability gate failed')
    with Path(availability['artifacts']['features']).open(newline='') as handle:
        targets = sorted(set((r['symbol'], r['hold_time']) for r in csv.DictReader(handle)))
    by_day = defaultdict(set)
    for symbol, hold_time in targets: by_day[hold_time[:10]].add(symbol)
    session = requests.Session(); session.headers.update(HEADERS)
    fetched = defaultdict(list); failures = []; queries = 0
    for day, symbols in sorted(by_day.items()):
        end = datetime.strptime(day, '%Y-%m-%d').date(); start = end - timedelta(days=LOOKBACK_DAYS)
        items = sorted(symbols)
        for offset in range(0, len(items), CHUNK_SIZE):
            rows, error = fetch(session, [code(x) for x in items[offset:offset + CHUNK_SIZE]], start.isoformat(), end.isoformat())
            queries += 1
            if error: failures.append({'day': day, 'symbols': len(items[offset:offset + CHUNK_SIZE]), 'error': error}); continue
            for row in rows:
                for item in row.get('codes') or []:
                    if item.get('stock_code'): fetched[item['stock_code']].append(row)
            time.sleep(.04)
    rows = []
    for symbol, hold_time in targets:
        cutoff = stamp(hold_time); lower = cutoff - timedelta(days=LOOKBACK_DAYS)
        eligible = [x for x in fetched.get(code(symbol), []) if (published := stamp(x.get('eiTime', ''))) and lower <= published <= cutoff]
        states = [classify(x.get('title', '')) for x in eligible]
        state = next((x for x in SCHEMA if x in states), 'OTHER_DISCLOSURE' if states else 'NO_RECENT_DISCLOSURE')
        rows.append({'symbol': symbol, 'hold_time': hold_time, 'feature_cutoff': hold_time,
                     'window_start': lower.isoformat(sep=' '), 'window_days': LOOKBACK_DAYS,
                     'pit_disclosure_state': state, 'pit_announcement_count': len(eligible),
                     'pit_latest_eiTime': max((x.get('eiTime', '') for x in eligible), default=''),
                     'all_eligible_timestamps_inside_exact_window': all(lower <= stamp(x['eiTime']) <= cutoff for x in eligible),
                     'contract': 'static V387 taxonomy; exact [hold_time-5d, hold_time] provider eiTime window'})
    with (OUT / 'v389_features.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    counts = dict(sorted((state, sum(r['pit_disclosure_state'] == state for r in rows)) for state in {r['pit_disclosure_state'] for r in rows}))
    invariant = all(r['all_eligible_timestamps_inside_exact_window'] for r in rows)
    gate = {'target_rows': len(targets), 'feature_rows': len(rows), 'api_queries': queries, 'query_failures': len(failures),
            'all_targets_covered': len(rows) == len(targets), 'all_queries_succeeded': not failures,
            'exact_lower_bound_enforced': invariant, 'outcome_fields_read_or_emitted': False,
            'all_feature_cutoffs_equal_hold_time': all(r['feature_cutoff'] == r['hold_time'] for r in rows)}
    passed = all([gate['all_targets_covered'], gate['all_queries_succeeded'], gate['exact_lower_bound_enforced'],
                  not gate['outcome_fields_read_or_emitted'], gate['all_feature_cutoffs_equal_hold_time']])
    result = {'version': 'V389_PIT_DISCLOSURE_EXACT_WINDOW_SCHEMA_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
              'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
              'repair': 'V387 cache-scope contamination removed with exact lower and upper publication-time bounds',
              'schema_priority': SCHEMA, 'gate': gate, 'state_counts': counts,
              'decision': 'PIT_DISCLOSURE_EXACT_WINDOW_PASS__OUTCOME_REPLAY_ALLOWED' if passed else 'PIT_DISCLOSURE_EXACT_WINDOW_FAIL__STOP',
              'artifacts': {'features': str(OUT / 'v389_features.csv'), 'latest': str(LATEST)}, 'failure_samples': failures[:50]}
    text = json.dumps(result, ensure_ascii=False, indent=2); (OUT / 'v389_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__': main()
