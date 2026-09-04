#!/usr/bin/env python3
"""V669: source-only PIT qualification for institutional survey disclosures."""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import hashlib
import json
import pathlib
import tempfile
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

ROOT = pathlib.Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
BASE = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
REPORT = 'RPT_ORG_SURVEYNEW'
YEARS = (2023, 2024, 2025)
PAGE_SIZE = 500
WORKERS = 8
COLUMNS = ','.join([
    'SECUCODE', 'SECURITY_CODE', 'SECURITY_NAME_ABBR', 'NOTICE_DATE',
    'RECEIVE_START_DATE', 'RECEIVE_END_DATE', 'RECEIVE_OBJECT', 'OBJECT_CODE',
    'RECEIVE_OBJECT_TYPE', 'ORG_TYPE', 'ORG_TYPE_CODE', 'RECEIVE_WAY',
    'RECEIVE_WAY_EXPLAIN', 'IS_MAX_REPORT', 'IS_SOURCE', 'SOURCE',
])
FILTER = "(NOTICE_DATE>='2023-01-01')(NOTICE_DATE<='2025-12-31')"
FORBIDDEN = {'price', 'volume', 'return', 'pnl', 'entry', 'exit', 'stop', 'target', 'trade'}


def request_page(page: int) -> dict:
    params = {
        'reportName': REPORT, 'columns': COLUMNS, 'pageNumber': str(page),
        'pageSize': str(PAGE_SIZE), 'sortColumns': 'NOTICE_DATE,SECURITY_CODE',
        'sortTypes': '1,1', 'source': 'WEB', 'client': 'WEB', 'filter': FILTER,
    }
    req = urllib.request.Request(
        BASE + '?' + urllib.parse.urlencode(params),
        headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'},
    )
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                payload = json.loads(response.read())
            if payload.get('success') is not True:
                raise RuntimeError(payload.get('message') or 'provider success=false')
            result = payload.get('result') or {}
            return {'page': page, 'count': result.get('count'), 'pages': result.get('pages'),
                    'rows': result.get('data') or []}
        except Exception as exc:
            last = exc
            time.sleep(0.4 * (2 ** attempt))
    raise RuntimeError(f'page={page}: {last}')


def atomic_write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, prefix=path.name + '.', suffix='.tmp', delete=False) as handle:
        temp = pathlib.Path(handle.name)
        handle.write(text)
    temp.replace(path)


def day(value) -> str:
    return str(value or '')[:10]


def event_key(row: dict) -> tuple[str, ...]:
    return (str(row.get('SECUCODE') or ''), day(row.get('NOTICE_DATE')),
            day(row.get('RECEIVE_START_DATE')), day(row.get('RECEIVE_END_DATE')),
            str(row.get('RECEIVE_WAY') or ''))


def participant_key(row: dict) -> tuple[str, ...]:
    return event_key(row) + (str(row.get('RECEIVE_OBJECT') or '').strip(),
                             str(row.get('OBJECT_CODE') or ''),
                             str(row.get('ORG_TYPE_CODE') or ''))


def main() -> None:
    first = request_page(1)
    expected_count = int(first['count'])
    expected_pages = int(first['pages'])
    page_results = {1: first}
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(request_page, page): page for page in range(2, expected_pages + 1)}
        for future in concurrent.futures.as_completed(futures):
            page = futures[future]
            try:
                page_results[page] = future.result()
            except Exception as exc:
                failures.append({'page': page, 'error': str(exc)[:300]})

    rows = []
    page_shape_errors = []
    for page in range(1, expected_pages + 1):
        result = page_results.get(page)
        if result is None:
            continue
        if int(result.get('count') or -1) != expected_count or int(result.get('pages') or -1) != expected_pages:
            page_shape_errors.append(page)
        rows.extend(result['rows'])

    participant_rows = {}
    participant_duplicate_count = 0
    for row in rows:
        key = participant_key(row)
        if key in participant_rows:
            participant_duplicate_count += 1
        participant_rows.setdefault(key, row)

    grouped = defaultdict(list)
    for row in participant_rows.values():
        grouped[event_key(row)].append(row)

    events = []
    for key, members in sorted(grouped.items()):
        secucode, notice_date, receive_start, receive_end, receive_way = key
        objects = sorted({str(x.get('RECEIVE_OBJECT') or '').strip() for x in members if str(x.get('RECEIVE_OBJECT') or '').strip()})
        org_types = sorted({str(x.get('ORG_TYPE') or '').strip() for x in members if str(x.get('ORG_TYPE') or '').strip()})
        events.append({
            'secucode': secucode,
            'security_code': str(members[0].get('SECURITY_CODE') or ''),
            'security_name': str(members[0].get('SECURITY_NAME_ABBR') or ''),
            'notice_date': notice_date,
            'receive_start_date': receive_start,
            'receive_end_date': receive_end,
            'receive_way': receive_way,
            'receive_way_explain': str(members[0].get('RECEIVE_WAY_EXPLAIN') or ''),
            'participant_count': len(objects),
            'org_type_count': len(org_types),
            'org_types': org_types,
            'participants_sha256': hashlib.sha256('\n'.join(objects).encode()).hexdigest(),
        })

    year_events = Counter(x['notice_date'][:4] for x in events)
    symbols = {x['secucode'] for x in events}
    notice_complete = sum(bool(x['notice_date']) for x in events)
    valid_code = sum(len(x['security_code']) == 6 and x['security_code'].isdigit() and x['secucode'].endswith(('.SH', '.SZ', '.BJ')) for x in events)
    emitted_keys = {k.lower() for row in events for k in row}
    forbidden_emitted = sorted(k for k in emitted_keys if any(token in k for token in FORBIDDEN))
    checks = {
        'all_pages_fetched': len(page_results) == expected_pages,
        'query_failures==0': len(failures) == 0,
        'page_shape_errors==0': len(page_shape_errors) == 0,
        'raw_row_count_equals_provider_count': len(rows) == expected_count,
        'notice_date_complete_pct==100': notice_complete == len(events),
        'security_code_valid_pct==100': valid_code == len(events),
        'canonical_identity_collision_count==0': len(events) == len(grouped),
        'unique_event_count>=3000': len(events) >= 3000,
        'each_year_unique_event_count>=500': all(year_events[str(y)] >= 500 for y in YEARS),
        'unique_symbol_count>=1000': len(symbols) >= 1000,
        'no_outcome_fields_read_or_emitted': not forbidden_emitted,
    }
    gate_pass = all(checks.values())
    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = AUDIT / f'v669_institutional_survey_pit_source_qualification_no_outcome_{stamp}'
    out_dir.mkdir(parents=True)
    event_path = out_dir / 'v669_events.jsonl'
    raw_path = out_dir / 'v669_participant_rows.jsonl'
    atomic_write(event_path, ''.join(json.dumps(x, ensure_ascii=False, sort_keys=True) + '\n' for x in events))
    atomic_write(raw_path, ''.join(json.dumps(x, ensure_ascii=False, sort_keys=True) + '\n' for x in participant_rows.values()))
    report = {
        'version': 'V669_INSTITUTIONAL_SURVEY_PIT_SOURCE_QUALIFICATION_NO_OUTCOME',
        'generated_at': dt.datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False,
        'watchlist_write': False, 'positions_write': False,
        'source': {'provider': 'Eastmoney datacenter public endpoint', 'report_name': REPORT,
                   'filter': FILTER, 'page_size': PAGE_SIZE, 'expected_pages': expected_pages,
                   'pages_fetched': len(page_results), 'expected_raw_rows': expected_count,
                   'raw_rows_received': len(rows), 'participant_unique_rows': len(participant_rows),
                   'participant_duplicate_count': participant_duplicate_count,
                   'query_failures': failures, 'page_shape_errors': page_shape_errors},
        'catalog': {'unique_events': len(events), 'unique_symbols': len(symbols),
                    'events_by_notice_year': dict(sorted(year_events.items())),
                    'notice_date_complete_pct': round(notice_complete / len(events) * 100, 4) if events else 0,
                    'security_code_valid_pct': round(valid_code / len(events) * 100, 4) if events else 0},
        'checks': checks, 'source_research_gate_pass': gate_pass,
        'production_source_authorized': False,
        'production_source_blockers': ['independent publication timestamp or official-document validation',
                                       'canonical current-universe coverage audit'],
        'decision': ('V669_SOURCE_RESEARCH_GATE_PASS__AUTHORIZE_ONE_NEW_OUTCOME_BLIND_EVENT_FIRST_ONTOLOGY__NO_PRODUCTION'
                     if gate_pass else 'V669_SOURCE_GATE_FAIL__CLOSE_WITHOUT_ONTOLOGY_OR_REPLAY'),
        'artifacts': {'out_dir': str(out_dir), 'events': str(event_path), 'participant_rows': str(raw_path)},
    }
    report_path = out_dir / 'v669_report.json'
    atomic_write(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    atomic_write(AUDIT / 'v669_institutional_survey_pit_source_qualification_latest.json', json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if gate_pass else 1)


if __name__ == '__main__':
    main()
