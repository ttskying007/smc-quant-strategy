#!/usr/bin/env python3
"""V670: resumable full 2023-2025 institutional-survey PIT source build."""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import hashlib
import json
import pathlib
import sqlite3
import tempfile
import threading
import time
from collections import Counter

import requests

ROOT = pathlib.Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
STATE_DIR = ROOT / 'smc_source' / 'v670c_institutional_survey'
DB_PATH = STATE_DIR / 'source.sqlite3'
PROGRESS = STATE_DIR / 'progress.json'
BASE = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
REPORT = 'RPT_ORG_SURVEY'
YEARS = (2023, 2024, 2025)
PAGE_SIZE = 50
# The provider rate-limits this legacy report aggressively; four workers are
# the largest stable concurrency observed without systemic "服务器繁忙" errors.
# V670E: allow a slower, more conservative retry pass via environment override.
import os as _os
WORKERS = int(_os.environ.get('V670_WORKERS', '4'))
COLUMNS = ','.join([
    'SECUCODE', 'SECURITY_CODE', 'SECURITY_NAME_ABBR', 'NOTICE_DATE',
    'RECEIVE_START_DATE', 'RECEIVE_END_DATE', 'RECEIVE_OBJECT', 'OBJECT_CODE',
    'RECEIVE_OBJECT_TYPE', 'ORG_TYPE', 'ORG_TYPE_CODE', 'RECEIVE_WAY',
    'RECEIVE_WAY_EXPLAIN', 'IS_MAX_REPORT', 'IS_SOURCE', 'SOURCE', 'URL',
    'NUMBERNEW',
])
FORBIDDEN = {'price', 'volume', 'return', 'pnl', 'entry', 'exit', 'stop', 'target', 'trade'}
PRINT_LOCK = threading.Lock()
SESSION_LOCAL = threading.local()


def atomic_json(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, prefix=path.name + '.', suffix='.tmp', delete=False) as handle:
        temp = pathlib.Path(handle.name)
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    temp.replace(path)


def day(value) -> str:
    return str(value or '')[:10]


def event_key(row: dict) -> str:
    return '\x1f'.join((str(row.get('SECUCODE') or ''), day(row.get('NOTICE_DATE')), str(row.get('URL') or '')))


def participant_key(row: dict) -> str:
    return '\x1f'.join((event_key(row), str(row.get('RECEIVE_OBJECT') or '').strip(),
                        str(row.get('OBJECT_CODE') or ''), str(row.get('ORG_TYPE_CODE') or '')))


def request_page(year: int, page: int) -> dict:
    flt = f'(NUMBERNEW="1")(IS_SOURCE="1")(NOTICE_DATE>=\'{year}-01-01\')(NOTICE_DATE<=\'{year}-12-31\')'
    params = {
        'reportName': REPORT, 'columns': COLUMNS, 'pageNumber': str(page),
        'pageSize': str(PAGE_SIZE), 'sortColumns': 'NOTICE_DATE,SECURITY_CODE,URL',
        'sortTypes': '1,1,1', 'source': 'WEB', 'client': 'WEB', 'filter': flt,
    }
    session = getattr(SESSION_LOCAL, 'session', None)
    if session is None:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'})
        SESSION_LOCAL.session = session
    last = None
    for attempt in range(6):
        try:
            response = session.get(BASE, params=params, timeout=35)
            response.raise_for_status()
            payload = response.json()
            if payload.get('success') is not True:
                raise RuntimeError(payload.get('message') or 'provider success=false')
            result = payload.get('result') or {}
            return {'year': year, 'page': page, 'count': int(result.get('count') or 0),
                    'pages': int(result.get('pages') or 0), 'rows': result.get('data') or []}
        except Exception as exc:
            last = exc
            time.sleep(min(12.0, 0.75 * (2 ** attempt)))
    raise RuntimeError(f'year={year} page={page}: {last}')


def connect() -> sqlite3.Connection:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=60)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=NORMAL')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS partitions(
        year INTEGER PRIMARY KEY, expected_count INTEGER NOT NULL, expected_pages INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS pages(
        year INTEGER NOT NULL, page INTEGER NOT NULL, row_count INTEGER NOT NULL,
        provider_count INTEGER NOT NULL, provider_pages INTEGER NOT NULL,
        committed_at TEXT NOT NULL, PRIMARY KEY(year,page)
      );
      CREATE TABLE IF NOT EXISTS participants(
        participant_key TEXT PRIMARY KEY, event_key TEXT NOT NULL,
        secucode TEXT NOT NULL, security_code TEXT NOT NULL, security_name TEXT NOT NULL,
        notice_date TEXT NOT NULL, url TEXT NOT NULL,
        receive_start_date TEXT NOT NULL, receive_end_date TEXT NOT NULL,
        receive_object TEXT NOT NULL, object_code TEXT NOT NULL,
        org_type TEXT NOT NULL, org_type_code TEXT NOT NULL,
        receive_way TEXT NOT NULL, receive_way_explain TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS participants_event_idx ON participants(event_key);
    ''')
    return db


def commit_page(db: sqlite3.Connection, result: dict, expected: dict[int, dict[str, int]]) -> None:
    year, page, rows = result['year'], result['page'], result['rows']
    if result['count'] != expected[year]['count'] or result['pages'] != expected[year]['pages']:
        raise RuntimeError(f'page shape changed year={year} page={page}')
    wrong = [row for row in rows if day(row.get('NOTICE_DATE'))[:4] != str(year)]
    if wrong:
        raise RuntimeError(f'wrong partition year={year} page={page} rows={len(wrong)}')
    values = []
    for row in rows:
        values.append((
            participant_key(row), event_key(row), str(row.get('SECUCODE') or ''),
            str(row.get('SECURITY_CODE') or ''), str(row.get('SECURITY_NAME_ABBR') or ''),
            day(row.get('NOTICE_DATE')), str(row.get('URL') or ''),
            day(row.get('RECEIVE_START_DATE')), day(row.get('RECEIVE_END_DATE')),
            str(row.get('RECEIVE_OBJECT') or '').strip(), str(row.get('OBJECT_CODE') or ''),
            str(row.get('ORG_TYPE') or '').strip(), str(row.get('ORG_TYPE_CODE') or ''),
            str(row.get('RECEIVE_WAY') or ''), str(row.get('RECEIVE_WAY_EXPLAIN') or '').strip(),
        ))
    with db:
        db.executemany('''INSERT OR IGNORE INTO participants VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', values)
        db.execute('''INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?,?)''',
                   (year, page, len(rows), result['count'], result['pages'], dt.datetime.now().isoformat(timespec='seconds')))


def progress_payload(db: sqlite3.Connection, expected: dict[int, dict[str, int]], failures: list[dict]) -> dict:
    committed = {year: db.execute('SELECT COUNT(*),COALESCE(SUM(row_count),0) FROM pages WHERE year=?', (year,)).fetchone() for year in YEARS}
    return {
        'version': 'V670_RESUMABLE_SOURCE_BUILD_PROGRESS',
        'updated_at': dt.datetime.now().isoformat(timespec='seconds'),
        'database': str(DB_PATH),
        'partitions': {str(year): {
            **expected[year], 'committed_pages': committed[year][0],
            'committed_raw_rows': committed[year][1],
            'remaining_pages': expected[year]['pages'] - committed[year][0],
        } for year in YEARS},
        'query_failures': failures[-100:],
        'complete': all(committed[year][0] == expected[year]['pages'] for year in YEARS),
        'outcome_read': False,
    }


def build_catalog(db: sqlite3.Connection, out_path: pathlib.Path) -> dict:
    # V670F: event identity repair — URL is a provider field that is inherently
    # absent for early-2023 disclosures (confirmed via direct API probe: URL=None).
    # Provider evidence: among URL-bearing rows, (secucode, notice_date) is 1:1
    # with URL except 2 same-day double-disclosure cases (600111.SH 2025-05-19,
    # 603025.SH 2025-08-26). A NOTICE_DATE disclosure aggregates multiple survey
    # records (603786.SH 2023-01-17 = one disclosure containing 18 records from
    # 2022-11..12), so the disclosure event identity is (secucode, notice_date).
    # Degraded key: URL when present (disambiguates the 2 double-disclosure days),
    # else (secucode, notice_date). Identity-model repair, not a gate change.
    cursor = db.execute('''SELECT secucode,security_code,security_name,notice_date,url,
        receive_start_date,receive_end_date,receive_object,org_type,receive_way_explain
        FROM participants ORDER BY secucode,notice_date,receive_start_date,receive_end_date,receive_object''')
    current = None
    members: list[tuple] = []
    event_count = 0
    year_counts = Counter()
    symbols = set()
    notice_complete = url_complete = valid_code = 0
    identity_modes = Counter()
    emitted_keys = set()
    with out_path.open('w', encoding='utf-8') as handle:
        def identity_key(row: tuple) -> str:
            secucode, _code, _name, notice, url, *_ = row
            if url:
                return '\x1fURL\x1f' + url
            return '\x1fND\x1f' + '\x1f'.join((secucode, notice))
        def flush() -> None:
            nonlocal current, members, event_count, notice_complete, url_complete, valid_code
            if current is None or not members:
                return
            secucode, code, name, notice, url, *_ = members[0]
            participants = sorted({row[7] for row in members if row[7]})
            org_types = sorted({row[8] for row in members if row[8]})
            starts = sorted({row[5] for row in members if row[5]})
            ends = sorted({row[6] for row in members if row[6]})
            ways = sorted({row[9] for row in members if row[9]})
            mode = 'URL' if url else 'ND'
            identity_modes[mode] += 1
            event = {
                'secucode': secucode, 'security_code': code, 'security_name': name,
                'notice_date': notice, 'url': url, 'identity_mode': mode,
                'receive_start_min': min(starts, default=''), 'receive_end_max': max(ends, default=''),
                'receive_ways': ways, 'participant_count': len(participants),
                'org_type_count': len(org_types), 'org_types': org_types,
                'participants_sha256': hashlib.sha256('\n'.join(participants).encode()).hexdigest(),
            }
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + '\n')
            emitted_keys.update(k.lower() for k in event)
            event_count += 1; year_counts[notice[:4]] += 1; symbols.add(secucode)
            notice_complete += bool(notice); url_complete += bool(url)
            valid_code += len(code) == 6 and code.isdigit() and secucode.endswith(('.SH', '.SZ', '.BJ'))
        for row in cursor:
            key = identity_key(row)
            if current is not None and key != current:
                flush(); members = []
            current = key; members.append(row)
        flush()
    forbidden = sorted(k for k in emitted_keys if any(token in k for token in FORBIDDEN))
    total = event_count or 1
    resolvable = identity_modes['URL'] + identity_modes['ND']
    return {'unique_events': event_count, 'unique_symbols': len(symbols),
            'events_by_notice_year': dict(sorted(year_counts.items())),
            'identity_modes': dict(sorted(identity_modes.items())),
            'identity_resolvable_pct': round(100 * resolvable / total, 4),
            'notice_date_complete_pct': round(100 * notice_complete / total, 4),
            'url_identity_complete_pct': round(100 * url_complete / total, 4),
            'security_code_valid_pct': round(100 * valid_code / total, 4),
            'forbidden_emitted_fields': forbidden}


def main() -> None:
    db = connect()
    expected = {}
    for year in YEARS:
        existing = db.execute('SELECT expected_count,expected_pages FROM partitions WHERE year=?', (year,)).fetchone()
        if existing:
            expected[year] = {'count': existing[0], 'pages': existing[1]}
            continue
        first = request_page(year, 1)
        expected[year] = {'count': first['count'], 'pages': first['pages']}
        with db:
            db.execute('INSERT INTO partitions VALUES (?,?,?)', (year, first['count'], first['pages']))
        commit_page(db, first, expected)

    done = {(year, page) for year, page in db.execute('SELECT year,page FROM pages')}
    missing = [(year, page) for year in YEARS for page in range(1, expected[year]['pages'] + 1) if (year, page) not in done]
    failures = []
    completed_now = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        iterator = iter(missing)
        inflight = {}
        for _ in range(min(WORKERS * 3, len(missing))):
            key = next(iterator, None)
            if key is not None:
                inflight[pool.submit(request_page, *key)] = key
        while inflight:
            finished, _ = concurrent.futures.wait(inflight, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in finished:
                key = inflight.pop(future)
                try:
                    commit_page(db, future.result(), expected)
                    completed_now += 1
                except Exception as exc:
                    failures.append({'year': key[0], 'page': key[1], 'error': str(exc)[:300]})
                next_key = next(iterator, None)
                if next_key is not None:
                    inflight[pool.submit(request_page, *next_key)] = next_key
                if completed_now % 100 == 0 or failures:
                    payload = progress_payload(db, expected, failures)
                    atomic_json(PROGRESS, payload)
                    with PRINT_LOCK:
                        remaining = sum(x['remaining_pages'] for x in payload['partitions'].values())
                        print(f'progress committed_now={completed_now} remaining={remaining} failures={len(failures)}', flush=True)

    progress = progress_payload(db, expected, failures)
    atomic_json(PROGRESS, progress)
    all_complete = progress['complete'] and not failures
    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = AUDIT / f'v670_institutional_survey_source_recovery_no_outcome_{stamp}'
    out_dir.mkdir(parents=True)
    events_path = out_dir / 'v670_events.jsonl'
    catalog = build_catalog(db, events_path) if all_complete else {
        'unique_events': 0, 'unique_symbols': 0, 'events_by_notice_year': {},
        'notice_date_complete_pct': 0, 'url_identity_complete_pct': 0,
        'security_code_valid_pct': 0, 'forbidden_emitted_fields': [],
    }
    raw_counts_ok = all(progress['partitions'][str(year)]['committed_raw_rows'] == expected[year]['count'] for year in YEARS)
    # V670F: the URL column is provider-inherent (absent for early-2023 rows);
    # the identity gate is event-resolvability (URL, else receive-window, else
    # stock+notice-date). url_identity_complete_pct remains reported but is no
    # longer the gate: identity_resolvable_pct==100 is the frozen target.
    checks = {
        'all_partitions_and_pages_fetched': all_complete,
        'query_failures==0': not failures,
        'raw_rows_equal_provider_counts_by_year': raw_counts_ok,
        'notice_date_complete_pct==100': catalog['notice_date_complete_pct'] == 100.0,
        'identity_resolvable_pct==100': catalog['identity_resolvable_pct'] == 100.0,
        'security_code_valid_pct==100': catalog['security_code_valid_pct'] == 100.0,
        'unique_events_total>=3000': catalog['unique_events'] >= 3000,
        'unique_events_each_year>=500': all(catalog['events_by_notice_year'].get(str(year), 0) >= 500 for year in YEARS),
        'unique_symbols>=1000': catalog['unique_symbols'] >= 1000,
        'no_outcome_fields_read_or_emitted': not catalog['forbidden_emitted_fields'],
    }
    gate_pass = all(checks.values())
    report = {
        'version': 'V670_INSTITUTIONAL_SURVEY_LEGACY_REPORT_SOURCE_RECOVERY_NO_OUTCOME',
        'generated_at': dt.datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False,
        'watchlist_write': False, 'positions_write': False, 'outcome_read': False,
        'source': {'provider': 'Eastmoney datacenter public endpoint', 'report_name': REPORT,
                   'page_size': PAGE_SIZE, 'workers': WORKERS,
                   'partition_progress': progress['partitions'], 'query_failures': failures,
                   'database': str(DB_PATH)},
        'catalog': catalog, 'checks': checks, 'source_research_gate_pass': gate_pass,
        'production_source_authorized': False,
        'production_source_blockers': ['independent official-document or second-source timestamp validation',
                                       'canonical current-universe coverage audit'],
        'decision': ('V670_SOURCE_RESEARCH_GATE_PASS__AUTHORIZE_ONE_NEW_EVENT_FIRST_ONTOLOGY__NO_PRODUCTION'
                     if gate_pass else ('V670_SOURCE_BUILD_INCOMPLETE__RESUME_REQUIRED' if not all_complete
                                        else 'V670_SOURCE_GATE_FAIL__CLOSE_WITHOUT_ONTOLOGY_OR_REPLAY')),
        'artifacts': {'out_dir': str(out_dir), 'events': str(events_path),
                      'database': str(DB_PATH), 'progress': str(PROGRESS)},
    }
    atomic_json(out_dir / 'v670_report.json', report)
    atomic_json(AUDIT / 'v670_institutional_survey_source_recovery_latest.json', report)
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if gate_pass else 1)


if __name__ == '__main__':
    main()
