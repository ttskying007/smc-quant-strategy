#!/usr/bin/env python3
"""V606: independent raw identity Oracle for V605; outcome data is prohibited."""
from __future__ import annotations

import csv
import json
import math
from bisect import bisect_right
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT, DAILY = ROOT / 'smc_audit', ROOT / 'kline_cache'
CATALOG = AUDIT / 'v603_equity_incentive_event_catalog_latest.json'
SEED = AUDIT / 'v605_equity_incentive_demand_retest_seed_latest.json'
LATEST = AUDIT / 'v606_v605_independent_raw_oracle_latest.json'
OUT = AUDIT / f'v606_v605_independent_raw_oracle_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
YEARS = ('2023', '2024', '2025')
INCLUDE = ('股权激励计划', '限制性股票激励计划', '股票期权激励计划')
EXCLUDE = ('摘要', '注销', '自查', '名单', '公示', '调整', '实施', '解除限售', '归属', '授予', '行权', '回购注销', '作废', '完成', '结果', '进展', '终止', '修订', '更正', '法律意见书', '独立财务顾问')


def date8(value: object) -> str:
    text = ''.join(char for char in str(value or '') if char.isdigit())
    return text[:8] if len(text) >= 8 else ''


def number(value: object) -> float | None:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) and parsed > 0 else None
    except (TypeError, ValueError):
        return None


def source_events(catalog: dict) -> dict[str, set[str]]:
    result, canonical = {}, set()
    with Path(catalog['artifacts']['events']).open(encoding='utf-8') as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            symbol, day, title = str(item.get('symbol') or ''), date8(item.get('notice_date')), str(item.get('title') or '')
            if (len(symbol) == 9 and day[:4] in YEARS and '草案' in title and any(term in title for term in INCLUDE) and not any(term in title for term in EXCLUDE)):
                canonical.add((symbol, day))
    for symbol, day in canonical:
        result.setdefault(symbol, set()).add(day)
    return result


def daily(symbol: str) -> list[dict]:
    try:
        raw = json.loads((DAILY / f'{symbol.replace(".", "_")}_daily_750.json').read_text())
    except (OSError, ValueError):
        return []
    rows = []
    for item in raw if isinstance(raw, list) else []:
        values = [number(item.get(key)) for key in ('o', 'h', 'l', 'c')]
        day = date8(item.get('t') or item.get('date'))
        if len(day) == 8 and all(value is not None for value in values):
            rows.append({'d': day, 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3]})
    return sorted(rows, key=lambda row: row['d'])


def identity(symbol: str, event_day: str, rows: list[dict]) -> tuple[str, str] | None:
    dates, start = [row['d'] for row in rows], bisect_right([row['d'] for row in rows], event_day)
    for break_i in range(start, min(start + 30, len(rows))):
        pivots = []
        for pivot_i in range(3, break_i - 3):
            left = max(row['h'] for row in rows[pivot_i - 3:pivot_i])
            right = max(row['h'] for row in rows[pivot_i + 1:pivot_i + 4])
            if rows[pivot_i]['h'] > left and rows[pivot_i]['h'] >= right:
                pivots.append(pivot_i)
        valid = [pivot_i for pivot_i in pivots if rows[pivot_i]['h'] < rows[break_i]['c']]
        bearish = [i for i in range(start, break_i + 1) if rows[i]['c'] < rows[i]['o']]
        if not valid or not bearish:
            continue
        poi = bearish[-1]
        low, high = rows[poi]['l'], rows[poi]['o']
        for reclaim_i in range(break_i + 1, min(break_i + 16, len(rows))):
            bar = rows[reclaim_i]
            if bar['l'] <= high and bar['h'] >= low and bar['c'] >= high and reclaim_i + 1 < len(rows):
                return symbol, rows[reclaim_i + 1]['d']
    return None


def main() -> None:
    catalog, seed_report = json.loads(CATALOG.read_text()), json.loads(SEED.read_text())
    with Path(seed_report['artifacts']['seeds']).open(newline='', encoding='utf-8') as handle:
        expected = {(row['symbol'], row['planned_entry_date']) for row in csv.DictReader(handle)}
    actual = set()
    for count, (symbol, days) in enumerate(sorted(source_events(catalog).items()), 1):
        rows = daily(symbol)
        for event_day in days:
            value = identity(symbol, event_day, rows)
            if value and value[1][:4] in YEARS:
                actual.add(value)
        if count % 500 == 0:
            print(json.dumps({'symbols': count, 'oracle_identities': len(actual)}, ensure_ascii=False), flush=True)
    missing, extra = expected - actual, actual - expected
    OUT.mkdir(parents=True, exist_ok=False)
    identities = OUT / 'v606_oracle_identities.csv'
    with identities.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['symbol', 'planned_entry_date'])
        writer.writeheader(); writer.writerows({'symbol': symbol, 'planned_entry_date': day} for symbol, day in sorted(actual))
    matched = expected == actual
    report = {'version': 'V606_V605_INDEPENDENT_RAW_ORACLE_NO_OUTCOME', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'input_contract': 'V605 expected identities plus immutable V603 catalog and daily OHLC only; no outcome, trade, PnL, exit, target, stop, or replay file read.', 'independent_rebuild': 'Separately rebuilds canonical original-plan event dates and post-event BSL acceptance -> demand-OB retest identities without importing V605 code.', 'expected_identities': len(expected), 'oracle_identities': len(actual), 'missing': len(missing), 'extra': len(extra), 'missing_sample': [{'symbol': s, 'planned_entry_date': d} for s, d in sorted(missing)[:20]], 'extra_sample': [{'symbol': s, 'planned_entry_date': d} for s, d in sorted(extra)[:20]], 'identity_match': matched, 'invariants': {'no_outcome_files_read': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False}, 'decision': 'V606_ORACLE_PASS__ONE_FROZEN_STRICT_T1_REPLAY_AUTHORIZED' if matched else 'V606_ORACLE_FAIL__NO_REPLAY_ALLOWED', 'artifacts': {'out_dir': str(OUT), 'oracle_identities': str(identities), 'latest': str(LATEST)}}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v606_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__':
    main()
