#!/usr/bin/env python3
"""V387 no-write PIT disclosure event-schema gate.

The static title schema is declared below before any outcome file is opened.
It maps only announcements published no later than the frozen V381 hold time.
"""
from __future__ import annotations

import csv
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
V386 = AUD / 'v386_pit_disclosure_availability_latest.json'
OUT = AUD / f'v387_pit_disclosure_event_schema_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v387_pit_disclosure_event_schema_latest.json'
URL = 'https://np-anotice-stock.eastmoney.com/api/security/ann'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}
LOOKBACK_DAYS, CHUNK_SIZE = 5, 200

# Frozen before replay. Priority makes each row exactly one mutually exclusive state.
SCHEMA = {
    'REGULATORY_OR_NEGATIVE': ('立案', '处罚', '问询函', '监管', '风险提示', '终止', '亏损', '预亏', '减持', '冻结', '诉讼', '仲裁', '退市'),
    'CAPITAL_RETURN_OR_INCREASE': ('回购', '增持', '分红', '权益分派'),
    'FUNDAMENTAL_POSITIVE': ('业绩预增', '业绩快报', '业绩预告', '经营情况', '年度报告', '半年度报告', '季度报告'),
    'BUSINESS_POSITIVE': ('中标', '合同', '订单', '签署', '合作', '项目'),
}


def stamp(value: str) -> datetime | None:
    try:
        return datetime.strptime(value[:19], '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return None


def code(symbol: str) -> str:
    return symbol.split('.', 1)[0]


def classify(title: str) -> str:
    for state, terms in SCHEMA.items():
        if any(term in title for term in terms):
            return state
    return 'OTHER_DISCLOSURE'


def fetch(session: requests.Session, codes: list[str], start: str, end: str) -> tuple[list[dict], str | None]:
    rows: list[dict] = []
    for page in range(1, 101):
        try:
            params = {'client_source': 'web', 'page_size': 100, 'page_index': page,
                      'ann_type': 'A', 'stock_list': ','.join(codes), 'begin_time': start, 'end_time': end}
            response = session.get(URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json().get('data') or {}
            batch = data.get('list') or []
            rows.extend(batch)
            if len(rows) >= int(data.get('total_hits') or 0) or not batch:
                return rows, None
            time.sleep(.03)
        except Exception as exc:
            return rows, f'{type(exc).__name__}:{exc}'
    return rows, 'PAGE_CAP_EXCEEDED'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    gate = json.loads(V386.read_text())
    if gate['decision'] != 'PIT_DISCLOSURE_AVAILABILITY_PASS__OUTCOME_BLIND_EVENT_SCHEMA_ALLOWED':
        raise RuntimeError('V386 PIT availability gate did not pass')
    with Path(gate['artifacts']['features']).open(newline='') as handle:
        targets = sorted(set((row['symbol'], row['hold_time']) for row in csv.DictReader(handle)))
    by_day: dict[str, set[str]] = defaultdict(set)
    for symbol, hold_time in targets:
        by_day[hold_time[:10]].add(symbol)

    session = requests.Session(); session.headers.update(HEADERS)
    fetched: dict[str, list[dict]] = defaultdict(list)
    failures: list[dict] = []; queries = 0
    for day, symbols in sorted(by_day.items()):
        end = datetime.strptime(day, '%Y-%m-%d').date(); start = end - timedelta(days=LOOKBACK_DAYS)
        symbol_list = sorted(symbols)
        for offset in range(0, len(symbol_list), CHUNK_SIZE):
            batch = symbol_list[offset:offset + CHUNK_SIZE]
            rows, error = fetch(session, [code(x) for x in batch], start.isoformat(), end.isoformat())
            queries += 1
            if error:
                failures.append({'day': day, 'symbols': len(batch), 'error': error}); continue
            for row in rows:
                for item in row.get('codes') or []:
                    if item.get('stock_code'):
                        fetched[item['stock_code']].append(row)
            time.sleep(.04)

    rows: list[dict] = []
    for symbol, hold_time in targets:
        cutoff = stamp(hold_time)
        eligible = [x for x in fetched.get(code(symbol), []) if stamp(x.get('eiTime', '')) and stamp(x['eiTime']) <= cutoff]
        states = [classify(x.get('title', '')) for x in eligible]
        active = next((state for state in SCHEMA if state in states), 'OTHER_DISCLOSURE' if states else 'NO_RECENT_DISCLOSURE')
        rows.append({'symbol': symbol, 'hold_time': hold_time, 'feature_cutoff': hold_time,
                     'pit_disclosure_state': active, 'pit_announcement_count': len(eligible),
                     'pit_latest_eiTime': max((x.get('eiTime', '') for x in eligible), default=''),
                     'contract': 'static title schema; announcement eiTime <= hold_time'})
    with (OUT / 'v387_features.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ['symbol'])
        writer.writeheader(); writer.writerows(rows)
    counts: dict[str, int] = defaultdict(int)
    for row in rows: counts[row['pit_disclosure_state']] += 1
    result = {'version': 'V387_PIT_DISCLOSURE_EVENT_SCHEMA_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
              'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
              'contract': 'Static title taxonomy is frozen before outcomes; only provider publication eiTime <= hold_time is eligible',
              'schema_priority': SCHEMA,
              'gate': {'target_rows': len(targets), 'feature_rows': len(rows), 'api_queries': queries,
                       'query_failures': len(failures), 'all_targets_covered': len(rows) == len(targets),
                       'all_queries_succeeded': not failures, 'outcome_fields_read_or_emitted': False,
                       'all_feature_cutoffs_equal_hold_time': all(r['feature_cutoff'] == r['hold_time'] for r in rows)},
              'state_counts': dict(sorted(counts.items())),
              'decision': 'PIT_DISCLOSURE_SCHEMA_PASS__OUTCOME_BLIND_REPLAY_ALLOWED' if not failures and len(rows) == len(targets) else 'PIT_DISCLOSURE_SCHEMA_FAIL__STOP',
              'artifacts': {'features': str(OUT / 'v387_features.csv'), 'latest': str(LATEST)}, 'failure_samples': failures[:50]}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v387_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__':
    main()
