#!/usr/bin/env python3
"""V536A outcome-blind seed gate: Sina-source daily absorption plus first120 industry leadership.

Scope is explicitly limited to the independently audited Sina interval (about
2025-04..2026-07).  This script never reads outcomes, opens no replay, and
never writes production/frontend/watchlist state.  It only establishes whether
an expanded same-source intraday leadership study has sufficient causal seeds.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina'
AUDIT = ROOT / 'smc_audit'
INDUSTRY = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
OUT = AUDIT / f'v536a_sina_industry_leadership_seed_gate_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v536a_sina_industry_leadership_seed_gate_latest.json'
LEFT = RIGHT = 3
VOL_LOOKBACK = 20
SWEEP_PCT = 0.003
VOL_TOP_QUINTILE = 0.80
YEARS = ('2025', '2026')
SUPPORT = {'total_min': 300, 'year_min': 40}


def number(value: Any) -> float | None:
    try:
        out = float(value)
        return out if out > 0 and math.isfinite(out) else None
    except (TypeError, ValueError):
        return None


def load_gzip(path: Path) -> list[dict[str, Any]]:
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def symbol_from_path(path: Path, frame: str) -> str:
    return path.name.removesuffix(f'_{frame}.json.gz').replace('_', '.')


def industry_map() -> dict[str, str]:
    try:
        raw = json.loads(INDUSTRY.read_text())
    except (OSError, ValueError):
        return {}
    return {str(row.get('symbol')): str(row.get('industry') or 'UNKNOWN').strip() or 'UNKNOWN'
            for row in raw if isinstance(row, dict) and row.get('symbol')}


def daily_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    for row in load_gzip(path):
        date = str(row.get('d') or row.get('t') or '')[:8]
        o, h, l, c, v = (number(row.get(key)) for key in ('o', 'h', 'l', 'c', 'v'))
        if date and None not in (o, h, l, c, v):
            rows.append({'d': date, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v})
    return sorted(rows, key=lambda row: row['d'])


def swing_low(rows: list[dict[str, Any]], idx: int) -> bool:
    if idx < LEFT or idx + RIGHT >= len(rows):
        return False
    low = rows[idx]['l']
    return low < min(rows[i]['l'] for i in range(idx - LEFT, idx)) and low <= min(rows[i]['l'] for i in range(idx + 1, idx + RIGHT + 1))


def daily_candidates(symbol: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seeds = []
    for sweep_idx in range(max(VOL_LOOKBACK, LEFT + RIGHT + 1), len(rows) - 2):
        pivot_idx = sweep_idx - RIGHT - 1
        if not swing_low(rows, pivot_idx):
            continue
        pivot, sweep, response, entry = rows[pivot_idx], rows[sweep_idx], rows[sweep_idx + 1], rows[sweep_idx + 2]
        prior = rows[sweep_idx - VOL_LOOKBACK:sweep_idx]
        volume_rank = sum(row['v'] <= sweep['v'] for row in prior) / len(prior)
        if not (sweep['l'] <= pivot['l'] * (1 - SWEEP_PCT) and sweep['c'] > pivot['l'] and volume_rank >= VOL_TOP_QUINTILE and response['c'] > sweep['h']):
            continue
        seeds.append({'symbol': symbol, 'swing_date': pivot['d'], 'swing_low': pivot['l'], 'sweep_date': sweep['d'],
                      'sweep_low': sweep['l'], 'sweep_high': sweep['h'], 'response_date': response['d'],
                      'entry_date': entry['d'], 'causal_trace': 'confirmed_daily_swing_low -> high_effort_ssl_sweep_reclaim -> next_daily_response_break -> entry_session_first120_observation'})
    return seeds


def first120_features(symbol: str, industry: str, path: Path, wanted: set[str]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in load_gzip(path):
        date = str(row.get('d') or row.get('t') or '')[:8]
        if date in wanted:
            grouped[date].append(row)
    out = []
    for date, bars in grouped.items():
        bars.sort(key=lambda row: str(row.get('t') or ''))
        if len(bars) != 16:
            continue
        part = bars[:8]
        o = number(part[0].get('o'))
        close = number(part[-1].get('c'))
        lows = [number(row.get('l')) for row in part]
        amount = sum((number(row.get('v')) or 0) * (number(row.get('c')) or 0) for row in part)
        if not o or not close or any(v is None for v in lows):
            continue
        out.append({'symbol': symbol, 'industry': industry, 'entry_date': date, 'stock_first120_ret_pct': (close / o - 1) * 100,
                    'stock_first120_low_dd_pct': (min(lows) / o - 1) * 100, 'stock_first120_amount': amount})
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    mapping = industry_map()
    daily_paths = sorted((RAW / 'daily').glob('*_daily.json.gz'))
    base: list[dict[str, Any]] = []
    for index, path in enumerate(daily_paths, 1):
        symbol = symbol_from_path(path, 'daily')
        base.extend(daily_candidates(symbol, daily_rows(path)))
        if index % 1000 == 0:
            print(f'daily_scan={index}/{len(daily_paths)} causal_candidates={len(base)}', flush=True)
    wanted = {row['entry_date'] for row in base if row['entry_date'][:4] in YEARS}
    features: list[dict[str, Any]] = []
    m15_paths = sorted((RAW / 'm15').glob('*_m15.json.gz'))
    for index, path in enumerate(m15_paths, 1):
        symbol = symbol_from_path(path, 'm15')
        features.extend(first120_features(symbol, mapping.get(symbol, 'UNKNOWN'), path, wanted))
        if index % 1000 == 0:
            print(f'm15_scan={index}/{len(m15_paths)} first120_rows={len(features)}', flush=True)
    by_date_industry: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    feature_map: dict[tuple[str, str], dict[str, Any]] = {}
    for feature in features:
        feature_map[(feature['symbol'], feature['entry_date'])] = feature
        if feature['industry'] != 'UNKNOWN':
            by_date_industry[(feature['entry_date'], feature['industry'])].append(feature)
    industry_stats: dict[tuple[str, str], dict[str, float]] = {}
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (date, industry), members in by_date_industry.items():
        if len(members) < 5:
            continue
        stats = {'industry_first120_ret_pct': median(row['stock_first120_ret_pct'] for row in members),
                 'industry_first120_up_pct': 100 * sum(row['stock_first120_ret_pct'] >= 0 for row in members) / len(members),
                 'industry_first120_amount': sum(row['stock_first120_amount'] for row in members), 'industry_members': len(members)}
        industry_stats[(date, industry)] = stats
        by_date[date].append({'industry': industry, **stats})
    for date, rows in by_date.items():
        for rank, row in enumerate(sorted(rows, key=lambda x: x['industry_first120_ret_pct'], reverse=True), 1):
            row['industry_ret_rank_pct'] = 100 * rank / len(rows)
        for rank, row in enumerate(sorted(rows, key=lambda x: x['industry_first120_up_pct'], reverse=True), 1):
            row['industry_up_rank_pct'] = 100 * rank / len(rows)
        for row in rows:
            industry_stats[(date, row['industry'])].update({key: row[key] for key in ('industry_ret_rank_pct', 'industry_up_rank_pct')})
    seeds = []
    missing_feature = 0
    for row in base:
        if row['entry_date'][:4] not in YEARS:
            continue
        feature = feature_map.get((row['symbol'], row['entry_date']))
        stats = industry_stats.get((row['entry_date'], mapping.get(row['symbol'], 'UNKNOWN')))
        if not feature or not stats:
            missing_feature += 1
            continue
        leader = stats['industry_ret_rank_pct'] <= 20 or stats['industry_up_rank_pct'] <= 20
        participate = feature['stock_first120_ret_pct'] >= 0 and feature['stock_first120_low_dd_pct'] > -1.5
        seeds.append({**row, **feature, **stats, 'industry_leader_top20': leader, 'stock_participates': participate,
                      'leadership_transmission': leader and participate})
    seeds.sort(key=lambda row: (row['entry_date'], row['symbol'], row['sweep_date']))
    years = Counter(row['entry_date'][:4] for row in seeds)
    transmission = [row for row in seeds if row['leadership_transmission']]
    transmission_years = Counter(row['entry_date'][:4] for row in transmission)
    chronology = all(row['swing_date'] < row['sweep_date'] < row['response_date'] < row['entry_date'] for row in seeds)
    no_outcomes = all(not any(key in row for key in ('pnl', 'exit', 'mfe', 'mae', 'target', 'stop', 'entry_price')) for row in seeds)
    gate = {'all_symbols_source_local': len(daily_paths) == len(m15_paths), 'strict_daily_chronology': chronology,
            'no_outcome_fields': no_outcomes, 'base_total_n>=300': len(seeds) >= SUPPORT['total_min'],
            'base_each_year_n>=40': all(years[year] >= SUPPORT['year_min'] for year in YEARS),
            'transmission_total_n>=300': len(transmission) >= SUPPORT['total_min'],
            'transmission_each_year_n>=40': all(transmission_years[year] >= SUPPORT['year_min'] for year in YEARS)}
    path = OUT / 'v536a_outcome_blind_seeds.csv'
    fields = list(seeds[0]) if seeds else ['symbol', 'entry_date']
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(seeds)
    report = {'version': 'V536A_SINA_FIRST120_INDUSTRY_LEADERSHIP_SEED_GATE_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
              'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
              'source_contract': 'Sina source-isolated daily+m15 only; no Baostock/Tencent bars; research range limited by same-source m15 availability.',
              'hypothesis': 'A causal daily high-effort SSL sweep/reclaim response followed by entry-session first120 industry TOP20 leadership with stock participation is a stronger same-source takeover object than daily price-only context.',
              'frozen_pre_outcome_contract': 'confirmed 3L/3R swing low -> >=0.3% wick sweep and close reclaim with top-quintile prior20 volume -> next daily close breaks sweep high -> following session first120 observes industry leadership/participation; no outcome read.',
              'coverage': {'daily_files': len(daily_paths), 'm15_files': len(m15_paths), 'candidate_entry_dates': len(wanted), 'industry_mapped_symbols': len(mapping), 'first120_features': len(features), 'missing_feature_for_daily_candidate': missing_feature},
              'base_seed_count': len(seeds), 'base_year_counts': dict(years), 'leadership_transmission_seed_count': len(transmission), 'leadership_transmission_year_counts': dict(transmission_years),
              'support_gate': SUPPORT, 'invariants': gate,
              'decision': 'V536A_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED' if all(gate.values()) else 'V536A_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_OR_REDESIGN_OBJECT',
              'artifacts': {'dir': str(OUT), 'seeds': str(path)}}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v536a_report.json').write_text(text); LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
