#!/usr/bin/env python3
"""V397 no-write PIT feasibility gate for Eastmoney aggregate fund-holdings history.

It checks only source history and time availability for the fixed V381 identities.
It intentionally does not read PnL, exits, or construct a trading rule.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

import akshare as ak

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
SRC = AUD / 'v381_true_mtf_raw_daily_poi_m60_replay_no_write_20260712_110522/v381_trades.csv'
STAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUD / f'v397_pit_fund_holdings_availability_no_write_{STAMP}'
LATEST = AUD / 'v397_pit_fund_holdings_availability_latest.json'

# Conservative statutory availability watermarks, later than the reporting-period
# deadline. They are deliberately not treated as verified source publication times.
def watermark(period: str) -> str:
    year, month = int(period[:4]), int(period[4:6])
    if month == 3:
        return f'{year}0501'  # Q1: deliberately later than the 15-working-day deadline
    if month == 6:
        return f'{year}0901'  # H1: deliberately later than the 60-day deadline
    if month == 9:
        return f'{year}1101'  # Q3: deliberately later than the 15-working-day deadline
    return f'{year + 1}0401'  # annual: deliberately later than the 90-day deadline


def d8(value: str) -> str:
    return ''.join(c for c in str(value) if c.isdigit())[:8]


def periods() -> list[str]:
    # Fixed V381 holds run from 2023-02-22 through 2026-07-09.  Only snapshots
    # whose conservative watermark can precede that range are required; querying
    # future report periods would turn an otherwise valid historical gate false.
    return ['20220930', '20221231', '20230331', '20230630', '20230930', '20231231',
            '20240331', '20240630', '20240930', '20241231', '20250331', '20250630',
            '20250930', '20251231', '20260331']


def select_period(hold_date: str, available: dict[str, dict]) -> str:
    candidates = [p for p, meta in available.items() if meta['watermark'] < hold_date and meta['rows']]
    return max(candidates) if candidates else ''


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with SRC.open(newline='') as source:
        identities = [{'symbol': row['symbol'], 'hold_date': d8(row['hold_time'])}
                      for row in csv.DictReader(source)]

    snapshots: dict[str, dict] = {}
    for period in periods():
        try:
            frame = ak.stock_report_fund_hold(symbol='基金持仓', date=period)
            codes = {str(x).zfill(6) for x in frame['股票代码'].tolist()}
            snapshots[period] = {'rows': len(frame), 'unique_symbols': len(codes),
                                 'watermark': watermark(period), 'fetch_ok': True, 'codes': codes}
        except Exception as exc:
            snapshots[period] = {'rows': 0, 'unique_symbols': 0, 'watermark': watermark(period),
                                 'fetch_ok': False, 'error': type(exc).__name__, 'codes': set()}

    output = []
    for row in identities:
        period = select_period(row['hold_date'], snapshots)
        meta = snapshots.get(period, {})
        output.append({**row, 'feature_period': period,
                       'conservative_watermark': meta.get('watermark', ''),
                       'source_snapshot_available': str(bool(period)).lower(),
                       'fund_held_at_snapshot': str(row['symbol'][:6] in meta.get('codes', set())).lower()})

    fields = list(output[0]) if output else []
    with (OUT / 'v397_identity_coverage.csv').open('w', newline='') as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)

    coverage = sum(r['source_snapshot_available'] == 'true' for r in output)
    report = {
        'version': 'V397_PIT_AGGREGATE_FUND_HOLDINGS_AVAILABILITY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'input_contract': 'fixed V381 identities and hold times only; no PnL, exit, or outcome fields read',
        'source': 'Eastmoney aggregate fund-holdings snapshots through akshare.stock_report_fund_hold',
        'pit_requirement': 'provider must expose verifiable publication timestamp no later than each hold cutoff',
        'watermark_contract': 'conservative statutory-period watermark is a safe theoretical upper-bound, not evidence that this aggregate provider published that snapshot then',
        'snapshot_periods': {p: {k: v for k, v in m.items() if k != 'codes'} for p, m in snapshots.items()},
        'identity_count': len(output), 'identity_coverage_pct': round(coverage / len(output) * 100, 4) if output else 0,
        'invariants': {
            'all_feature_periods_strictly_before_hold': all(not r['feature_period'] or r['conservative_watermark'] < r['hold_date'] for r in output),
            'no_outcome_field_read': True,
            'full_snapshot_history_available': all(m['fetch_ok'] for m in snapshots.values()),
            'provider_exact_publication_timestamp_available': False,
        },
        'availability_gate': {
            'full_2023_2026_history': all(m['fetch_ok'] for m in snapshots.values()),
            'fixed_identity_coverage_ge_95pct': coverage / len(output) >= 0.95 if output else False,
            'verified_provider_pit_timestamp': False,
            'outcome_replay_allowed': False,
        },
        'decision': 'AGGREGATE_FUND_HOLDINGS_HISTORY_COMPLETE__STRICT_PROVIDER_PIT_TIMESTAMP_UNPROVEN__NO_REPLAY',
        'artifacts': {'out_dir': str(OUT), 'identity_coverage': str(OUT / 'v397_identity_coverage.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v397_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
