#!/usr/bin/env python3
"""V563 outcome-blind seeds: daily SSL reclaim -> midday industry expansion.

This is deliberately a different ontology from V562's scarce high-effort
leader cohort: a confirmed external sell-side liquidity raid is followed by
broad sector acceptance (not a rank-selected leader) and stock-level hold in
the next session's first 120 minutes.  No outcome or replay files are read.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

import v562_ssl_industry_midday_transmission_seed as common

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina'
AUDIT = ROOT / 'smc_audit'
OUT = AUDIT / f'v563_ssl_industry_expansion_midday_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v563_ssl_industry_expansion_midday_seed_latest.json'
YEARS = ('2025', '2026')
SUPPORT = {'total_min': 1000, 'year_min': 300}


def no_volume_ssl_seeds(symbol, rows):
    """A confirmed external SSL raid/reclaim; daily volume is descriptive only."""
    output = []
    for sweep_index in range(common.RIGHT + 1, len(rows) - 1):
        pivot_index = sweep_index - common.RIGHT - 1
        if not common.confirmed_swing_low(rows, pivot_index):
            continue
        pivot, sweep, next_day = rows[pivot_index], rows[sweep_index], rows[sweep_index + 1]
        if not (sweep['l'] <= pivot['l'] * (1 - common.SWEEP_PCT) and sweep['c'] > pivot['l']):
            continue
        output.append({
            'symbol': symbol,
            'pivot_date': pivot['d'],
            'pivot_low': round(pivot['l'], 6),
            'sweep_date': sweep['d'],
            'sweep_low': round(sweep['l'], 6),
            'sweep_close': round(sweep['c'], 6),
            'sweep_volume': round(sweep['v'], 6),
            'entry_date': next_day['d'],
            'causal_trace': 'confirmed_daily_3L3R_SSL -> wick_sweep_reclaim -> next_session_first120_industry_expansion -> earliest_1300_entry',
        })
    return output


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    mapping = common.industry_map()
    daily_paths = sorted((RAW / 'daily').glob('*_daily.json.gz'))
    base = []
    for number, path in enumerate(daily_paths, 1):
        base.extend(no_volume_ssl_seeds(common.symbol_from(path, 'daily'), common.daily(path)))
        if number % 1000 == 0:
            print(json.dumps({'daily_files': number, 'ssl_reclaim_seeds': len(base)}), flush=True)
    wanted = {row['entry_date'] for row in base if row['entry_date'][:4] in YEARS}
    features = []
    for number, path in enumerate(sorted((RAW / 'm15').glob('*_m15.json.gz')), 1):
        symbol = common.symbol_from(path, 'm15')
        features.extend(common.first120(path, wanted, symbol, mapping.get(symbol, 'UNKNOWN')))
        if number % 1000 == 0:
            print(json.dumps({'m15_files': number, 'first120_features': len(features)}), flush=True)

    feature_by_key = {(row['symbol'], row['entry_date']): row for row in features}
    members = defaultdict(list)
    for row in features:
        if row['industry'] != 'UNKNOWN':
            members[(row['entry_date'], row['industry'])].append(row)
    stats, by_date = {}, defaultdict(list)
    for key, rows in members.items():
        if len(rows) < common.MIN_INDUSTRY_MEMBERS:
            continue
        stat = {
            'industry_first120_ret_pct': median(row['stock_first120_ret_pct'] for row in rows),
            'industry_first120_up_pct': round(100 * sum(row['stock_first120_ret_pct'] >= 0 for row in rows) / len(rows), 6),
            'industry_member_count': len(rows),
        }
        stats[key] = stat
        by_date[key[0]].append((key[1], stat))

    chosen, missing = [], 0
    for seed in base:
        if seed['entry_date'][:4] not in YEARS:
            continue
        feature = feature_by_key.get((seed['symbol'], seed['entry_date']))
        stat = stats.get((seed['entry_date'], mapping.get(seed['symbol'], 'UNKNOWN')))
        if not feature or not stat:
            missing += 1
            continue
        # Semantic expansion: sector's median first120 return is non-negative and
        # at least half of observable constituents are positive; the candidate
        # itself must hold non-negative with no >1.5% early rejection.
        expands = stat['industry_first120_ret_pct'] >= 0 and stat['industry_first120_up_pct'] >= 50
        participates = feature['stock_first120_ret_pct'] >= 0 and feature['stock_first120_low_dd_pct'] >= common.MAX_FIRST120_DD_PCT
        if expands and participates:
            chosen.append({**seed, **feature, **stat,
                           'causal_identity': f"{seed['symbol']}|{seed['sweep_date']}|{seed['entry_date']}",
                           'contract_version': 'V563_SSL_SWEEP_MIDDAY_INDUSTRY_EXPANSION'})

    chosen.sort(key=lambda row: (row['entry_date'], row['symbol'], row['sweep_date']))
    years = Counter(row['entry_date'][:4] for row in chosen)
    unique = len({row['causal_identity'] for row in chosen})
    chronology = all(row['pivot_date'] < row['sweep_date'] < row['entry_date'] and row['m15_first120_end_time'] < row['m15_earliest_entry_time'] for row in chosen)
    no_outcomes = all(not any(token in key.lower() for key in row for token in ('pnl', 'exit', 'mfe', 'mae', 'target', 'stop', 'won')) for row in chosen)
    gate = {
        'same_source_daily_m15': len(daily_paths) == 5528,
        'daily_confirmation_before_sweep': all(row['pivot_date'] < row['sweep_date'] for row in chosen),
        'm15_observed_before_entry': chronology,
        'no_outcome_fields_read_or_written': no_outcomes,
        'unique_identities': unique == len(chosen),
        'total_n>=1000': len(chosen) >= SUPPORT['total_min'],
        '2025_n>=300': years['2025'] >= SUPPORT['year_min'],
        '2026_n>=300': years['2026'] >= SUPPORT['year_min'],
    }
    fields = sorted({key for row in chosen for key in row}) or ['symbol', 'entry_date']
    csv_path = OUT / 'v563_outcome_blind_seeds.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(chosen)
    report = {
        'version': 'V563_SSL_INDUSTRY_EXPANSION_MIDDAY_SEED_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source_contract': 'Sina source-isolated daily+m15 cache only; 5,528 symbols; available 2025-04..2026-07 range; no bar mixing.',
        'frozen_pre_outcome_contract': 'confirmed 3L/3R daily SSL wick sweep and close reclaim -> following session first120 sector median return>=0 plus sector up breadth>=50% -> candidate first120 return>=0 and drawdown>=-1.5% -> earliest post-lunch M15 open.',
        'support_gate': SUPPORT,
        'counts': {'daily_ssl_base': len(base), 'candidate_entry_dates': len(wanted), 'first120_features': len(features), 'missing_feature_or_industry_stat': missing, 'chosen_seeds': len(chosen), 'unique_identities': unique, 'year_counts': dict(years)},
        'invariants': gate,
        'decision': 'V563_SUPPORT_PASS__INDEPENDENT_RAW_ORACLE_REQUIRED' if all(gate.values()) else 'V563_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_OBJECT',
        'artifacts': {'out_dir': str(OUT), 'seeds': str(csv_path), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v563_report.json').write_text(text); LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
