#!/usr/bin/env python3
"""Report V536 Sina source-local coverage against its dated canonical universe.

This is a gate report only.  It explicitly does not convert Sina's recent
partial range into a 2023-2026 full-market authorization.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina'
AUDIT = ROOT / 'smc_audit'
CANONICAL = AUDIT / 'v536_sina_canonical_universe_latest.json'
FRAMES = ('daily', 'weekly', 'm60', 'm15')


def symbols(frame: str) -> set[str]:
    suffix = f'_{frame}.json.gz'
    return {path.name.removesuffix(suffix).replace('_', '.') for path in (RAW / frame).glob(f'*{suffix}')}


def main() -> None:
    ledger = json.loads(CANONICAL.read_text())
    universe = set(ledger['symbols'])
    by_frame = {frame: symbols(frame) for frame in FRAMES}
    complete = set.intersection(*(by_frame[frame] for frame in FRAMES))
    covered = universe & complete
    missing = sorted(universe - complete)
    payload = {
        'version': 'V536_SINA_PARTIAL_RANGE_UNIVERSE_COVERAGE_V1',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'source': 'sina', 'research_only': True, 'production_write': False,
        'canonical_universe_source': str(CANONICAL),
        'canonical_universe_generated_at': ledger.get('generated_at'),
        'canonical_count': len(universe),
        'frame_file_counts': {frame: len(by_frame[frame]) for frame in FRAMES},
        'complete_multitf_source_local': len(covered),
        'missing': len(missing),
        'coverage_pct': round(100 * len(covered) / len(universe), 4) if universe else 0.0,
        'by_exchange': {exchange: {'canonical': sum(s.endswith(f'.{exchange}') for s in universe), 'complete': sum(s.endswith(f'.{exchange}') for s in covered)} for exchange in ('SH', 'SZ', 'BJ')},
        'missing_samples': missing[:100],
        'scope': 'SINA_SOURCE_ISOLATED_RECENT_PARTIAL_RANGE',
        'full_market_2023_2026_research': 'BLOCKED__SINA_M15_HISTORY_STARTS_2025',
        'promotion': 'BLOCKED__PARTIAL_RANGE_NEVER_REPAIRS_OR_AUGMENTS_BAOSTOCK',
        'decision': 'PARTIAL_RANGE_CACHE_COMPLETE' if len(covered) == len(universe) else 'PARTIAL_RANGE_CACHE_BUILD_IN_PROGRESS',
    }
    for path in (AUDIT / f"v536_sina_partial_coverage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", AUDIT / 'v536_sina_partial_coverage_latest.json'):
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        tmp.replace(path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
