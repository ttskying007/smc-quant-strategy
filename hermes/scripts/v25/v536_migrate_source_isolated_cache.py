#!/usr/bin/env python3
"""Migrate legacy V536 cache into immutable, source-isolated research storage.

This is a COPY-ONLY migration. Legacy files remain untouched.  No signal,
trade, watchlist, frontend, or production artifact is read or written.

Every emitted bar carries the provenance contract required for future research:
source, adjustment, requested_range, received_range, provider_timestamp,
coverage_audit, and cross_source_validation.  The latter two begin as
PENDING_LEGACY_AUDIT and are promoted only by the separate audit process.
"""
from __future__ import annotations

import argparse
import gzip
import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
LEGACY = ROOT / 'intraday_cache/raw_multitf_v536'
TARGET = LEGACY / 'source_raw/baostock'
AUDIT = ROOT / 'smc_audit'
FRAMES = ('daily', 'weekly', 'm60', 'm15')
RANGE = {'start': '2023-01-01', 'end': '2026-07-17'}
SOURCE = 'baostock'
SCHEMA = 'V536_SOURCE_ISOLATED_BAR_V1'


def load(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        rows = json.load(handle)
    if not isinstance(rows, list) or not rows:
        raise ValueError('empty_or_invalid_legacy_rows')
    return rows


def write_gzip(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with gzip.open(temporary, 'wt', encoding='utf-8') as handle:
        json.dump(rows, handle, ensure_ascii=False, separators=(',', ':'))
    temporary.replace(path)


def source_kind(frame: str) -> str:
    return 'provider_raw' if frame in {'daily', 'm15'} else 'same_source_deterministic_aggregation'


def migrate_rows(rows: list[dict[str, Any]], frame: str) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        timestamp = str(row.get('t', ''))
        if not timestamp:
            raise ValueError('legacy_bar_without_timestamp')
        output.append({
            **row,
            'source': SOURCE,
            'adjustment': 'raw_unadjusted_adjustflag_3',
            'requested_range': RANGE,
            'received_range': RANGE,
            'provider_timestamp': timestamp,
            'coverage_audit': 'PENDING_LEGACY_SOURCE_ISOLATION_AUDIT',
            'cross_source_validation': 'PENDING_INDEPENDENT_OVERLAP_AUDIT',
            'source_kind': source_kind(frame),
            'provenance_schema': SCHEMA,
        })
    return output


def output_path(frame: str, source_file: Path) -> Path:
    return TARGET / frame / source_file.name


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=0, help='maximum symbols, for a bounded resumable migration')
    parser.add_argument('--symbol', default='', help='one exact symbol, e.g. 000001.SZ')
    parser.add_argument('--shard-count', type=int, default=1, help='independent deterministic migration shards')
    parser.add_argument('--shard-index', type=int, default=0, help='zero-based shard index')
    args = parser.parse_args()
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise SystemExit('invalid shard configuration')

    symbols = sorted({p.name.replace('_daily.json.gz', '').replace('_', '.')
                      for p in (LEGACY / 'daily').glob('*_daily.json.gz')})
    if args.symbol:
        symbols = [s for s in symbols if s == args.symbol]
        if not symbols:
            raise SystemExit('requested symbol absent from legacy daily cache')
    else:
        symbols = [symbol for index, symbol in enumerate(symbols) if index % args.shard_count == args.shard_index]
    if args.limit:
        symbols = symbols[:args.limit]

    started = datetime.now().isoformat(timespec='seconds')
    completed, skipped, failed = [], [], []
    for symbol in symbols:
        base = symbol.replace('.', '_')
        try:
            files = {frame: LEGACY / frame / f'{base}_{frame}.json.gz' for frame in FRAMES}
            if not all(path.exists() for path in files.values()):
                raise ValueError('legacy_symbol_missing_required_frame')
            destinations = {frame: output_path(frame, path) for frame, path in files.items()}
            if all(path.exists() for path in destinations.values()):
                skipped.append(symbol)
                continue
            migrated = {frame: migrate_rows(load(path), frame) for frame, path in files.items()}
            # Commit all frames only after every source file has parsed and been normalized.
            for frame in FRAMES:
                write_gzip(destinations[frame], migrated[frame])
            completed.append(symbol)
        except Exception as exc:
            failed.append({'symbol': symbol, 'error': repr(exc)})

    report = {
        'version': 'V536_SOURCE_ISOLATED_MIGRATION_V1',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'started_at': started,
        'mode': 'COPY_ONLY_LEGACY_PRESERVED',
        'research_only': True,
        'production_write': False,
        'source': SOURCE,
        'source_root': str(TARGET),
        'legacy_root': str(LEGACY),
        'bar_provenance_schema': SCHEMA,
        'requested_range': RANGE,
        'symbols_requested': len(symbols),
        'completed': len(completed),
        'already_migrated': len(skipped),
        'failed': len(failed),
        'failed_samples': failed[:50],
        'decision': 'MIGRATION_PASS' if not failed else 'MIGRATION_PARTIAL_RETRY_REQUIRED',
    }
    AUDIT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    for path in (AUDIT / f'v536_source_isolated_migration_{stamp}.json', AUDIT / 'v536_source_isolated_migration_latest.json'):
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        temp.replace(path)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
