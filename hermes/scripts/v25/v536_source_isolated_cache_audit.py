#!/usr/bin/env python3
"""No-write audit of V536 source-isolated multi-timeframe research cache.

Checks one provider namespace at a time. It never compares or substitutes bars
across providers and never writes any market/production artifact.
"""
from __future__ import annotations

import argparse
import gzip
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
CACHE = ROOT / 'intraday_cache/raw_multitf_v536/source_raw'
AUDIT = ROOT / 'smc_audit'
FRAMES = ('daily', 'weekly', 'm60', 'm15')
M15 = {'0945', '1000', '1015', '1030', '1045', '1100', '1115', '1130', '1315', '1330', '1345', '1400', '1415', '1430', '1445', '1500'}
M60 = {'1030', '1130', '1400', '1500'}
PROVENANCE = {'source', 'adjustment', 'requested_range', 'received_range', 'provider_timestamp', 'coverage_audit', 'cross_source_validation', 'source_kind', 'provenance_schema'}


def load(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        rows = json.load(handle)
    if not isinstance(rows, list) or not rows:
        raise ValueError('empty_or_non_list')
    return rows


def slots(rows: list[dict[str, Any]], expected: set[str], wanted: set[str]) -> tuple[int, int]:
    day_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        day_rows[row['d']].append(row)
    actual = set(day_rows)
    missing = expected - actual
    bad = sum(len(day_rows[d]) != len(wanted) or {r['t'][8:12] for r in day_rows[d]} != wanted for d in expected & actual)
    return len(missing), bad


def weekly_from_daily(daily: list[dict[str, Any]]) -> list[tuple]:
    buckets: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in daily:
        buckets[datetime.strptime(row['t'], '%Y%m%d').isocalendar()[:2]].append(row)
    return [(r[-1]['t'], r[0]['o'], max(x['h'] for x in r), min(x['l'] for x in r), r[-1]['c'], sum(x['v'] for x in r), sum(x.get('a', 0) for x in r)) for r in buckets.values()]


def m60_from_m15(rows: list[dict[str, Any]]) -> list[tuple]:
    slot_end = {'0945': '1030', '1000': '1030', '1015': '1030', '1030': '1030', '1045': '1130', '1100': '1130', '1115': '1130', '1130': '1130', '1315': '1400', '1330': '1400', '1345': '1400', '1400': '1400', '1415': '1500', '1430': '1500', '1445': '1500', '1500': '1500'}
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        end = slot_end.get(row['t'][8:12])
        if end:
            buckets[(row['d'], end)].append(row)
    return [(f'{d}{end}00', r[0]['o'], max(x['h'] for x in r), min(x['l'] for x in r), r[-1]['c'], sum(x['v'] for x in r), sum(x.get('a', 0) for x in r)) for (d, end), r in sorted(buckets.items()) if len(r) == 4]


def values(rows: list[dict[str, Any]]) -> list[tuple]:
    return [(x['t'], x['o'], x['h'], x['l'], x['c'], x['v'], x.get('a', 0)) for x in rows]


def ohlcva_equal(left: list[tuple], right: list[tuple]) -> bool:
    """Exact timestamp/order, numerically tolerant only for float accumulation noise."""
    if len(left) != len(right):
        return False
    for a, b in zip(left, right):
        if a[0] != b[0]:
            return False
        if any(abs(float(x) - float(y)) > max(1e-6, 1e-12 * max(abs(float(x)), abs(float(y)))) for x, y in zip(a[1:], b[1:])):
            return False
    return True


def audit_symbol(root: Path, symbol: str) -> dict[str, Any]:
    base = symbol.replace('.', '_')
    try:
        all_rows = {frame: load(root / frame / f'{base}_{frame}.json.gz') for frame in FRAMES}
        daily, weekly, m60, m15 = (all_rows[x] for x in FRAMES)
        provenance_missing = {frame: sum(not PROVENANCE <= set(row) for row in rows) for frame, rows in all_rows.items()}
        source_consistent = all({row['source'] for row in rows} == {root.name} for rows in all_rows.values())
        source_kind_ok = all(all(row['source_kind'] == ('provider_raw' if frame in {'daily', 'm15'} else 'same_source_deterministic_aggregation') for row in rows) for frame, rows in all_rows.items())
        dates = [row['t'] for row in daily]
        daily_valid = all(row['o'] > 0 and row['h'] >= max(row['o'], row['c']) and row['l'] <= min(row['o'], row['c']) for row in daily)
        daily_ordered = all(dates[i] < dates[i + 1] for i in range(len(dates) - 1))
        expected = set(dates)
        m15_missing, m15_bad = slots(m15, expected, M15)
        m60_missing, m60_bad = slots(m60, expected, M60)
        weekly_exact = ohlcva_equal(weekly_from_daily(daily), values(weekly))
        m60_exact = ohlcva_equal(m60_from_m15(m15), values(m60))
        ok = all(not n for n in provenance_missing.values()) and source_consistent and source_kind_ok and daily_valid and daily_ordered and not m15_missing and not m15_bad and not m60_missing and not m60_bad and weekly_exact and m60_exact
        return {'symbol': symbol, 'ok': ok, 'daily_bars': len(daily), 'm15_bars': len(m15), 'm60_bars': len(m60), 'weekly_bars': len(weekly), 'provenance_missing': provenance_missing, 'source_consistent': source_consistent, 'source_kind_ok': source_kind_ok, 'daily_valid': daily_valid, 'daily_ordered': daily_ordered, 'm15_missing_days': m15_missing, 'm15_bad_slot_days': m15_bad, 'm60_missing_days': m60_missing, 'm60_bad_slot_days': m60_bad, 'weekly_exact_from_same_source_daily': weekly_exact, 'm60_exact_from_same_source_m15': m60_exact}
    except Exception as exc:
        return {'symbol': symbol, 'ok': False, 'error': repr(exc)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default='baostock')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--symbol', default='')
    parser.add_argument('--shard-count', type=int, default=1, help='deterministic independent audit shards')
    parser.add_argument('--shard-index', type=int, default=0, help='zero-based shard index')
    args = parser.parse_args()
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise SystemExit('invalid shard configuration')
    root = CACHE / args.source
    frame_symbols = []
    for frame in FRAMES:
        suffix = f'_{frame}.json.gz'
        frame_symbols.append({p.name.removesuffix(suffix).replace('_', '.') for p in (root / frame).glob(f'*{suffix}')})
    symbols = sorted(set.intersection(*frame_symbols) if frame_symbols else set())
    if args.symbol:
        symbols = [s for s in symbols if s == args.symbol]
    else:
        symbols = [symbol for index, symbol in enumerate(symbols) if index % args.shard_count == args.shard_index]
    if args.limit:
        symbols = symbols[:args.limit]
    rows = [audit_symbol(root, symbol) for symbol in symbols]
    failed = [row for row in rows if not row['ok']]
    report = {'version': 'V536_SOURCE_ISOLATED_CACHE_AUDIT_V1', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'research_only': True, 'production_write': False, 'source': args.source, 'source_root': str(root), 'shard_count': args.shard_count, 'shard_index': args.shard_index, 'symbols': len(rows), 'passed': len(rows) - len(failed), 'failed': len(failed), 'decision': 'SOURCE_ISOLATED_CACHE_PASS' if not failed else 'SOURCE_ISOLATED_CACHE_FAIL', 'failure_samples': failed[:50]}
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    shard_tag = f'shard{args.shard_index:02d}_of_{args.shard_count:02d}'
    out = AUDIT / f'v536_source_isolated_cache_audit_{args.source}_{shard_tag}_{stamp}.json'
    temporary = out.with_suffix('.tmp'); temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2)); temporary.replace(out)
    if args.shard_count == 1 and not args.symbol and not args.limit:
        latest = AUDIT / f'v536_source_isolated_cache_audit_{args.source}_latest.json'
        temporary = latest.with_suffix('.tmp'); temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2)); temporary.replace(latest)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
