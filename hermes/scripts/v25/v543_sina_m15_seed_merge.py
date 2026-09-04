#!/usr/bin/env python3
"""Merge all audited V543 outcome-blind shards; no replay/outcome data is read."""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
SHARDS = AUDIT / 'v543_shards_20260723'
OUT = AUDIT / f'v543_sina_m15_ssl_displacement_absorption_seed_gate_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v543_sina_m15_ssl_displacement_absorption_seed_gate_latest.json'
SUPPORT = {'total_min': 300, 'each_year_min': 80, 'unique_symbols_min': 150}


def main() -> None:
    paths = [SHARDS / f'v543_seed_shard_{i:02d}_of_03.csv' for i in range(3)]
    if not all(path.exists() for path in paths):
        raise RuntimeError('all three outcome-blind shards are required')
    seeds: list[dict[str, str]] = []
    for path in paths:
        with path.open(newline='', encoding='utf-8') as handle:
            seeds.extend(csv.DictReader(handle))
    seeds.sort(key=lambda row: (row['symbol'], row['entry_time'], row['sweep_time']))
    identity = lambda row: (row['symbol'], row['swing_time'], row['sweep_time'], row['reference_high_time'], row['bos_time'], row['fvg_time'], row['reclaim_time'], row['entry_time'])
    unique = {identity(row) for row in seeds}
    years = Counter(row['entry_date'][:4] for row in seeds)
    symbols = {row['symbol'] for row in seeds}
    invariant = {'exactly_three_required_shards_present': len(paths) == 3, 'shard_file_total': sum(1 for _ in ROOT.glob('intraday_cache/raw_multitf_v536/source_raw/sina/m15/*_m15.json.gz')) == 5528, 'source_isolated_sina_only': all(row['source'] == 'sina' for row in seeds), 'no_duplicate_identities': len(unique) == len(seeds), 'no_outcome_fields': all(not any(key in row for key in ('exit_time', 'pnl', 'return', 'stop', 'target')) for row in seeds), 'strict_entry_after_reclaim': all(row['entry_time'] > row['reclaim_time'] for row in seeds), 'total_n>=300': len(seeds) >= SUPPORT['total_min'], '2025_n>=80': years['2025'] >= SUPPORT['each_year_min'], '2026_n>=80': years['2026'] >= SUPPORT['each_year_min'], 'unique_symbols_n>=150': len(symbols) >= SUPPORT['unique_symbols_min']}
    OUT.mkdir(parents=True, exist_ok=False)
    seed_path = OUT / 'v543_outcome_blind_seeds.csv'
    with seed_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(seeds[0])); writer.writeheader(); writer.writerows(seeds)
    report = {'version': 'V543_SINA_M15_SSL_DISPLACEMENT_ABSORPTION_SEED_GATE_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False, 'authorized_input_gate': 'READ_AUTHORIZED_PARTIAL_SAME_SOURCE_ONLY (Sina OHLCV)', 'scope': 'SINA_SOURCE_ISOLATED_PARTIAL_RANGE_2025_04_TO_2026_07_ONLY', 'hypothesis': 'The price-only V539 failure is a participation-quality defect: require high-participation stop sweep plus volume/range displacement, then a low-participation FVG retest reclaim.', 'frozen_pre_outcome_contract': 'confirmed 3L/3R SSL; wick sweep >=0.3% with volume >= prior20 q80; <=12 bars bullish BOS with body >=1.2x prior20 median range and volume >=1.2x prior20 median volume; bullish FVG width >=0.5x median range and volume >=1.2x median volume; <=20 bars first interval touch/reclaim with volume <=1.0x prior20 median; next unobserved m15 entry.', 'parameters_fixed_before_outcomes': {'lookback': 20, 'sweep_vol_quantile': 0.8, 'sweep_pct': 0.003, 'bos_max_bars': 12, 'displacement_range_mult': 1.2, 'displacement_vol_mult': 1.2, 'fvg_width_range_mult': 0.5, 'retest_vol_max_mult': 1.0, 'retest_max_bars': 20}, 'coverage': {'m15_files_scanned': 5528, 'malformed_or_short_files': 1, 'shards': [str(path) for path in paths]}, 'seed_count': len(seeds), 'year_counts': dict(years), 'unique_symbols': len(symbols), 'support_gate': SUPPORT, 'invariants': invariant, 'decision': 'V543_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED' if all(invariant.values()) else 'V543_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_OBJECT', 'artifacts': {'dir': str(OUT), 'seeds': str(seed_path)}}
    text = json.dumps(report, ensure_ascii=False, indent=2); (OUT / 'v543_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__':
    main()
