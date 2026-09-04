#!/usr/bin/env python3
"""V603: resumable 2023-2025 PIT equity-incentive catalog; no market data or outcomes."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
OUT = AUDIT / 'v603_equity_incentive_event_catalog_no_outcome'
EVENTS = OUT / 'v603_events.jsonl'
STATE = OUT / 'v603_state.json'
LATEST = AUDIT / 'v603_equity_incentive_event_catalog_latest.json'
URL = 'https://np-anotice-stock.eastmoney.com/api/security/ann'
START, END, WORKERS = date(2023, 1, 1), date(2025, 12, 31), 4
INCLUDE = ('股权激励计划', '限制性股票激励计划', '股票期权激励计划')
EXCLUDE = ('调整', '实施', '解除限售', '归属', '授予', '行权', '回购注销', '作废', '完成', '结果', '进展', '终止', '修订', '更正', '法律意见书', '独立财务顾问')


def calendar_days() -> list[str]:
    current, result = START, []
    while current <= END:
        result.append(current.isoformat())
        current += timedelta(days=1)
    return result


def classify(title: str) -> list[str]:
    if any(term in title for term in EXCLUDE):
        return []
    return [term for term in INCLUDE if term in title]


def fetch_one(day: str) -> dict:
    session, events, page = requests.Session(), [], 1
    for attempt in range(3):
        try:
            while True:
                response = session.get(
                    URL,
                    params={
                        'client_source': 'web', 'page_size': 100, 'page_index': page,
                        'ann_type': 'A', 'begin_time': day, 'end_time': day,
                    },
                    headers={'User-Agent': 'Mozilla/5.0'}, timeout=40,
                )
                data = (response.json().get('data') or {})
                batch, total = data.get('list') or [], int(data.get('total_hits') or 0)
                for item in batch:
                    title = str(item.get('title') or '')
                    matched = classify(title)
                    if not matched:
                        continue
                    for code in item.get('codes') or []:
                        stock = str(code.get('stock_code') or '')
                        if len(stock) == 6 and stock.isdigit():
                            suffix = '.SH' if stock.startswith(('5', '6', '9')) else '.SZ'
                            events.append({
                                'symbol': stock + suffix,
                                'announcement_id': str(item.get('art_code') or ''),
                                'notice_date': str(item.get('notice_date') or '')[:10],
                                'publication_time': str(item.get('eiTime') or ''),
                                'title': title,
                                'matched_terms': matched,
                                'source_day': day,
                            })
                if page * 100 >= total or not batch:
                    return {'day': day, 'ok': True, 'error': '', 'events': events, 'total_hits': total}
                page += 1
        except Exception as exc:
            if attempt == 2:
                return {'day': day, 'ok': False, 'error': f'{type(exc).__name__}:{exc}', 'events': [], 'total_hits': 0}
            time.sleep(attempt + 1)
    raise RuntimeError('unreachable')


def load_state() -> dict:
    if not STATE.exists():
        return {'completed_days': {}, 'failed_days': {}}
    return json.loads(STATE.read_text())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    state = load_state()
    pending = [day for day in calendar_days() if day not in state['completed_days']]
    if pending:
        with EVENTS.open('a', encoding='utf-8') as handle, ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(fetch_one, day): day for day in pending}
            for number, future in enumerate(as_completed(futures), 1):
                result = future.result()
                if result['ok']:
                    state['completed_days'][result['day']] = {
                        'total_hits': result['total_hits'], 'event_count': len(result['events']),
                    }
                    for event in result['events']:
                        handle.write(json.dumps(event, ensure_ascii=False) + '\n')
                else:
                    state['failed_days'][result['day']] = result['error']
                if number % 10 == 0:
                    handle.flush()
                    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
                    print(json.dumps({'completed': len(state['completed_days']), 'failed': len(state['failed_days']), 'pending': len(pending) - number}), flush=True)
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    canonical = {}
    if EVENTS.exists():
        for line in EVENTS.open(encoding='utf-8'):
            try:
                event = json.loads(line)
                canonical[(event['symbol'], event['announcement_id'])] = event
            except (ValueError, KeyError):
                continue
    events = list(canonical.values())
    years = ('2023', '2024', '2025')
    complete = len(state['completed_days']) == len(calendar_days()) and not state['failed_days']
    report = {
        'version': 'V603_PIT_EQUITY_INCENTIVE_EVENT_CATALOG_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'source_contract': {
            'provider': 'Eastmoney public announcement metadata endpoint',
            'date_range': [START.isoformat(), END.isoformat()],
            'fields': ['symbol', 'announcement_id', 'notice_date', 'publication_time', 'title'],
            'include_terms': list(INCLUDE),
            'exclude_terms': list(EXCLUDE),
            'prohibited': ['price', 'volume', 'SMC seed', 'outcome', 'trade', 'PnL'],
        },
        'coverage': {
            'calendar_days_expected': len(calendar_days()),
            'calendar_days_completed': len(state['completed_days']),
            'calendar_days_failed': len(state['failed_days']),
            'all_days_complete': complete,
        },
        'canonical_candidate_events': len(events),
        'candidate_events_by_year': {year: sum(event['notice_date'].startswith(year) for event in events) for year in years},
        'decision': 'SOURCE_CATALOG_COMPLETE__SEMANTIC_PREREGISTRATION_NEXT' if complete else 'SOURCE_CATALOG_IN_PROGRESS__NO_STRATEGY_OR_OUTCOME_AUTHORIZED',
        'artifacts': {'out_dir': str(OUT), 'events': str(EVENTS), 'state': str(STATE), 'latest': str(LATEST)},
    }
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
