#!/usr/bin/env python3
"""V673 source-only qualification of Eastmoney 15-minute A-share bars.

This script is deliberately not a signal generator. It reads only provider
metadata and bar timestamps: no OHLCV values, no outcomes, no candidates, and
no replay. It cannot authorize a strategy; a pass only authorizes a separate
canonical-universe/slot-coverage audit.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
OUT = AUDIT / f'v673_eastmoney_m15_source_qualification_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v673_eastmoney_m15_source_qualification_latest.json'

# Pre-registered source-only scope. A provider must meet every item before
# strategy design is allowed; no shortened date range or mixed-source fill.
REPRESENTATIVES = {
    '000001.SZ': '0.000001',
    '600519.SH': '1.600519',
    '920982.BJ': '0.920982',
}
REQUIRED_START = '2023-01-01'
REQUIRED_END_AT_LEAST = '2026-08-05'
SLOT_DATES = ('2024-01-02', '2025-01-02', '2026-01-05')
EXPECTED_SLOTS_PER_SESSION = 16


def request_rows(secid: str) -> list[str]:
    query = urlencode({
        'secid': secid, 'klt': '15', 'fqt': '1', 'beg': '20230101',
        'end': '20260805', 'lmt': '100000',
        # timestamp is field f51. No OHLCV fields are requested or parsed.
        'fields1': 'f1,f2,f3,f4,f5,f6', 'fields2': 'f51',
    })
    req = Request(
        f'https://push2his.eastmoney.com/api/qt/stock/kline/get?{query}',
        headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'},
    )
    with urlopen(req, timeout=45) as response:
        payload = json.loads(response.read().decode('utf-8'))
        if not isinstance(payload, dict) or payload.get('rc') != 0:
            raise RuntimeError(f'provider_rc={payload.get("rc") if isinstance(payload, dict) else "non_json"}')
        data = payload.get('data') or {}
        rows = data.get('klines') or []
        return [str(x).split(',', 1)[0] for x in rows if str(x)]


def day_slots(timestamps: list[str], day: str) -> int:
    return sum(1 for ts in timestamps if ts[:10] == day)


def probe(symbol: str, secid: str) -> dict:
    try:
        timestamps = request_rows(secid)
        dates = [x[:10] for x in timestamps if len(x) >= 10]
        return {
            'symbol': symbol,
            'secid': secid,
            'error': '',
            'bar_count': len(timestamps),
            'start': min(dates) if dates else None,
            'end': max(dates) if dates else None,
            'slot_counts': {d: day_slots(timestamps, d) for d in SLOT_DATES},
        }
    except Exception as exc:
        return {
            'symbol': symbol, 'secid': secid, 'error': f'{type(exc).__name__}:{exc}',
            'bar_count': 0, 'start': None, 'end': None,
            'slot_counts': {d: 0 for d in SLOT_DATES},
        }


def passes(row: dict) -> bool:
    return (
        not row['error']
        and row['start'] is not None and row['start'] <= REQUIRED_START
        and row['end'] is not None and row['end'] >= REQUIRED_END_AT_LEAST
        and all(n == EXPECTED_SLOTS_PER_SESSION for n in row['slot_counts'].values())
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    rows = [probe(symbol, secid) for symbol, secid in REPRESENTATIVES.items()]
    gate = all(passes(row) for row in rows)
    report = {
        'version': 'V673_EASTMONEY_M15_SOURCE_QUALIFICATION_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'scope': 'Provider capability only: timestamp coverage and session-slot completeness; no OHLCV values/outcomes/candidates/replay are read or produced.',
        'predeclared_gate': {
            'source': 'Eastmoney push2his 15-minute endpoint',
            'same_source_required': True,
            'required_start': REQUIRED_START,
            'required_end_at_least': REQUIRED_END_AT_LEAST,
            'representatives': list(REPRESENTATIVES),
            'slot_dates': list(SLOT_DATES),
            'expected_slots_per_session': EXPECTED_SLOTS_PER_SESSION,
            'pass_rule': 'Every SH/SZ/BJ representative must cover the entire requested range and each declared completed session must contain exactly 16 timestamps.',
            'failure_rule': 'Any failure closes this source for full-history intraday ontology; no date shortening, cache filling, or source mixing is authorized.',
        },
        'probes': rows,
        'gate': {
            'all_representatives_full_history_and_slots': gate,
            'canonical_universe_slot_audit_authorized': gate,
            'new_outcome_blind_ontology_authorized': False,
        },
        'decision': (
            'SOURCE_CAPABILITY_PASS__AUTHORIZE_SEPARATE_CANONICAL_UNIVERSE_SLOT_AUDIT_ONLY'
            if gate else
            'SOURCE_CAPABILITY_FAIL__NO_UNIVERSE_BUILD_NO_ONTOLOGY_NO_REPLAY'
        ),
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v673_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
