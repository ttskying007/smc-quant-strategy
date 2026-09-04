#!/usr/bin/env python3
"""V596 build a resumable 2024-2025 PIT contract/award event catalog; no prices or outcomes."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
OUT = AUDIT / 'v596_contract_award_event_catalog_no_outcome'
EVENTS = OUT / 'v596_events.jsonl'
STATE = OUT / 'v596_state.json'
REPORT = AUDIT / 'v596_contract_award_event_catalog_latest.json'
URL = 'https://np-anotice-stock.eastmoney.com/api/security/ann'
YEARS = ('2024', '2025')
WORKERS = 4
KEYWORDS = ('中标', '重大合同', '签订合同', '签署合同', '合同金额', '获得订单', '收到订单')


def days() -> list[str]:
    current, end, result = date(2024, 1, 1), date(2025, 12, 31), []
    while current <= end:
        result.append(current.isoformat())
        current += timedelta(days=1)
    return result


def fetch_one(day: str) -> dict:
    session = requests.Session()
    items, page, errors = [], 1, []
    while True:
        try:
            response = session.get(URL, params={'client_source': 'web', 'page_size': 100, 'page_index': page, 'ann_type': 'A', 'begin_time': day, 'end_time': day}, headers={'User-Agent': 'Mozilla/5.0'}, timeout=40)
            payload = response.json()
            data = payload.get('data') or {}
            batch = data.get('list') or []
            total = int(data.get('total_hits') or 0)
        except Exception as exc:
            errors.append(f'{type(exc).__name__}:{exc}')
            if len(errors) >= 3:
                return {'day': day, 'ok': False, 'error': '|'.join(errors), 'events': [], 'total_hits': 0}
            time.sleep(len(errors))
            continue
        for item in batch:
            title = str(item.get('title') or '')
            if not any(term in title for term in KEYWORDS):
                continue
            for code in item.get('codes') or []:
                stock = str(code.get('stock_code') or '')
                if len(stock) != 6 or not stock.isdigit():
                    continue
                suffix = '.SH' if stock.startswith(('5', '6', '9')) else '.SZ'
                items.append({'symbol': stock + suffix, 'announcement_id': str(item.get('art_code') or ''), 'notice_date': str(item.get('notice_date') or '')[:10], 'publication_time': str(item.get('eiTime') or ''), 'title': title, 'matched_terms': [term for term in KEYWORDS if term in title], 'source_day': day})
        if page * 100 >= total or not batch:
            return {'day': day, 'ok': True, 'error': '', 'events': items, 'total_hits': total}
        page += 1


def load_state() -> dict:
    if not STATE.exists():
        return {'completed_days': {}, 'failed_days': {}}
    return json.loads(STATE.read_text())


def write_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    state = load_state()
    pending = [day for day in days() if day not in state['completed_days']]
    if pending:
        with EVENTS.open('a', encoding='utf-8') as handle, ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(fetch_one, day): day for day in pending}
            for n, future in enumerate(as_completed(futures), 1):
                result = future.result()
                if result['ok']:
                    state['completed_days'][result['day']] = {'total_hits': result['total_hits'], 'event_count': len(result['events'])}
                    for event in result['events']:
                        handle.write(json.dumps(event, ensure_ascii=False) + '\n')
                else:
                    state['failed_days'][result['day']] = result['error']
                if n % 10 == 0:
                    handle.flush(); write_state(state)
                    print(json.dumps({'completed': len(state['completed_days']), 'failed': len(state['failed_days']), 'pending': len(pending) - n}), flush=True)
        write_state(state)
    events = []
    if EVENTS.exists():
        for line in EVENTS.open(encoding='utf-8'):
            try: events.append(json.loads(line))
            except ValueError: pass
    canonical = {(x['symbol'], x['announcement_id']): x for x in events}
    by_year = {year: sum(x['notice_date'].startswith(year) for x in canonical.values()) for year in YEARS}
    report = {'version': 'V596_PIT_CONTRACT_AWARD_EVENT_CATALOG_NO_OUTCOME', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False, 'source_contract': {'provider': 'Eastmoney public announcement metadata endpoint', 'date_range': ['2024-01-01', '2025-12-31'], 'fields': ['symbol', 'announcement_id', 'notice_date', 'publication_time', 'title'], 'keywords': list(KEYWORDS), 'prohibited': ['price', 'volume', 'SMC seed', 'outcome', 'trade', 'PnL']}, 'coverage': {'calendar_days_expected': len(days()), 'calendar_days_completed': len(state['completed_days']), 'calendar_days_failed': len(state['failed_days']), 'all_days_complete': len(state['completed_days']) == len(days()) and not state['failed_days']}, 'canonical_candidate_events': len(canonical), 'candidate_events_by_year': by_year, 'decision': 'SOURCE_CATALOG_COMPLETE__SEMANTIC_PREREGISTRATION_NEXT' if len(state['completed_days']) == len(days()) and not state['failed_days'] else 'SOURCE_CATALOG_IN_PROGRESS__NO_STRATEGY_OR_OUTCOME_AUTHORIZED', 'artifacts': {'out_dir': str(OUT), 'events': str(EVENTS), 'state': str(STATE), 'latest': str(REPORT)}}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
