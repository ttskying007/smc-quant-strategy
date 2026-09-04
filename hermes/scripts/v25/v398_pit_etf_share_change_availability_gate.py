#!/usr/bin/env python3
"""V398 no-write feasibility gate for exchange ETF share-change data.

This is source discovery only.  It probes full-history SSE/SZSE ETF daily share
snapshots and asks whether the source can legally feed a 2023-2026 stock-level
outcome replay.  It never reads trades' PnL/exit/outcomes and never writes
production, frontend, or watchlist files.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import akshare as ak

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
OUT = AUD / f'v398_pit_etf_share_change_availability_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v398_pit_etf_share_change_availability_latest.json'
# One observed session per half-year plus the latest completed session.  These
# dates test history availability, not economic performance.
SAMPLES = ('20230103', '20230630', '20231229', '20240628', '20241231', '20250630', '20260710')


def probe_sse(day: str) -> dict:
    try:
        df = ak.fund_etf_scale_sse(day)
        dates = sorted({str(x) for x in df.get('统计日期', []).dropna()}) if len(df) else []
        return {'requested_date': day, 'ok': True, 'rows': int(len(df)), 'reported_dates': dates[:3]}
    except Exception as exc:
        return {'requested_date': day, 'ok': False, 'error': f'{type(exc).__name__}: {exc}'}


def probe_szse(day: str) -> dict:
    try:
        df = ak.fund_scale_daily_szse(day, day, 'ETF')
        dates = sorted({str(x) for x in df.get('日期', []).dropna()}) if len(df) else []
        return {'requested_date': day, 'ok': True, 'rows': int(len(df)), 'reported_dates': dates[:3]}
    except Exception as exc:
        return {'requested_date': day, 'ok': False, 'error': f'{type(exc).__name__}: {exc}'}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sse = [probe_sse(day) for day in SAMPLES]
    szse = [probe_szse(day) for day in SAMPLES]
    full_history = all(x.get('ok') and x.get('rows', 0) > 0 for x in sse + szse)
    report = {
        'version': 'V398_PIT_ETF_SHARE_CHANGE_AVAILABILITY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'input_contract': 'source availability probes only; no V381 trade outcome field read',
        'source_contract': {
            'sse': 'SSE ETF daily fund-share snapshot, queryable by STAT_DATE',
            'szse': 'SZSE ETF daily fund-share snapshot, queryable by date range',
            'candidate_information': 'ETF-level share outstanding change only; not stock-level constituent flow',
        },
        'history_probes': {'sse': sse, 'szse': szse},
        'availability_gate': {
            'full_2023_2026_snapshot_history': full_history,
            'stock_level_constituent_mapping_with_asof_timestamp': False,
            'provider_exact_publication_timestamp_available': False,
            'point_in_time_stock_feature_constructible': False,
            'outcome_replay_allowed': False,
        },
        'decision': (
            'ETF_SHARE_HISTORY_AVAILABLE_BUT_NOT_A_VERIFIABLE_PIT_STOCK_LEVEL_SOURCE__NO_REPLAY'
        ),
        'why_closed': [
            'Exchange responses expose a statistics date and ETF-level shares, but no per-snapshot publication timestamp.',
            'A historical ETF share change cannot be attributed to individual A-shares without historical constituent weights and their own as-of/publication timestamps.',
            'Using today\'s constituents, statutory assumptions, or outcome-period membership would create a point-in-time leak.',
        ],
        'next_eligible_source': (
            'full historical order-book/tick data, or a stock-level institutional/ETF-constituent provider '
            'with verifiable historical publication timestamps and complete 2023-2026 coverage'
        ),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v398_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
