#!/usr/bin/env python3
"""V407 no-write feasibility gate for historical transaction/tick data.

A source is usable only if its response is date-sensitive, contains actual trades,
and agrees with the daily OHLC close for fixed historical probes.  This tests data
availability only; it never opens V381 outcomes or writes production artifacts.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from mootdx.quotes import Quotes

ROOT = Path('/root/.hermes')
KDIR = ROOT / 'kline_cache'
AUD = ROOT / 'smc_audit'
OUT = AUD / f'v407_pit_tick_history_availability_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v407_pit_tick_history_availability_latest.json'
PROBES = [
    ('000001.SZ', '20230726'),
    ('000001.SZ', '20240125'),
    ('000001.SZ', '20250512'),
    ('600519.SH', '20230726'),
    ('600519.SH', '20240125'),
    ('600519.SH', '20250512'),
]


def ds(value: object) -> str:
    return ''.join(c for c in str(value or '') if c.isdigit())[:8]


def daily_close(symbol: str, date: str) -> float | None:
    path = KDIR / f'{symbol.replace(".", "_")}_daily_750.json'
    try:
        rows = json.loads(path.read_text())
    except Exception:
        return None
    for row in rows:
        if ds(row.get('t') or row.get('date')) == date:
            try:
                return float(row['c'])
            except (KeyError, TypeError, ValueError):
                return None
    return None


def fingerprint(df) -> str:
    columns = ['time', 'price', 'vol', 'num', 'buyorsell', 'volume']
    records = df.reindex(columns=columns, fill_value='').astype(str).to_dict('records')
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode()).hexdigest()


def inspect(client: Quotes, symbol: str, date: str) -> dict:
    code = symbol[:6]
    expected_close = daily_close(symbol, date)
    try:
        frame = client.transaction(symbol=code, date=date)
        numeric_volume = frame['volume'] if 'volume' in frame else frame.get('vol')
        positive_volume_rows = int((numeric_volume.astype(float) > 0).sum()) if numeric_volume is not None else 0
        prices = frame['price'].astype(float) if 'price' in frame else []
        last_price = float(prices.iloc[-1]) if len(prices) else None
        return {
            'symbol': symbol,
            'requested_date': date,
            'daily_close': expected_close,
            'response_rows': int(len(frame)),
            'positive_volume_rows': positive_volume_rows,
            'last_transaction_price': last_price,
            'response_fingerprint': fingerprint(frame),
            'query_error': '',
        }
    except Exception as exc:
        return {
            'symbol': symbol,
            'requested_date': date,
            'daily_close': expected_close,
            'response_rows': 0,
            'positive_volume_rows': 0,
            'last_transaction_price': None,
            'response_fingerprint': '',
            'query_error': f'{type(exc).__name__}:{exc}',
        }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    client = Quotes.factory(market='std')
    rows = [inspect(client, symbol, date) for symbol, date in PROBES]
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row['symbol'], []).append(row)
    date_sensitive = {
        symbol: len({r['response_fingerprint'] for r in items if r['response_fingerprint']}) == len(items)
        for symbol, items in groups.items()
    }
    expected_distinct = {
        symbol: len({r['daily_close'] for r in items if r['daily_close'] is not None}) == len(items)
        for symbol, items in groups.items()
    }
    price_matches = [
        r for r in rows
        if r['daily_close'] is not None and r['last_transaction_price'] is not None
        and abs(r['daily_close'] - r['last_transaction_price']) < 0.02
    ]
    gate = {
        'probe_count': len(rows),
        'query_failures': sum(bool(r['query_error']) for r in rows),
        'all_historical_daily_prices_distinct_within_symbol': all(expected_distinct.values()),
        'responses_date_sensitive_within_symbol': all(date_sensitive.values()),
        'all_responses_contain_actual_positive_volume': all(r['positive_volume_rows'] > 0 for r in rows),
        'last_transaction_matches_daily_close_count': len(price_matches),
        'outcome_fields_read_or_emitted': False,
    }
    passed = (
        gate['query_failures'] == 0
        and gate['all_historical_daily_prices_distinct_within_symbol']
        and gate['responses_date_sensitive_within_symbol']
        and gate['all_responses_contain_actual_positive_volume']
        and gate['last_transaction_matches_daily_close_count'] == len(rows)
        and not gate['outcome_fields_read_or_emitted']
    )
    result = {
        'version': 'V407_PIT_TICK_HISTORY_AVAILABILITY_GATE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'contract': 'Historical ticks must be date-sensitive, actual-volume-bearing, and daily-price-aligned before any full-history MTF/tick replay.',
        'gate': gate,
        'probes': rows,
        'decision': 'PIT_TICK_HISTORY_AVAILABILITY_PASS__SOURCE_CAN_BE_SCALED' if passed else 'PIT_TICK_HISTORY_AVAILABILITY_FAIL__STOP',
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST)},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v407_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
