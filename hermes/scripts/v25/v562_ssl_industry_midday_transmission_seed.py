#!/usr/bin/env python3
"""V562 outcome-blind seeds: daily SSL sweep -> next-session midday industry transmission.

Fixed research contract, using only the already available same-source Sina
2025-04..2026-07 daily/M15 cache.  It reads no trade outcomes and writes only
research artifacts.  A daily 3L/3R-confirmed swing low must be swept and
reclaimed on volume; on the *following* session, the first 120 minutes must
show both industry leadership and stock participation before a 13:00 entry
can be considered by a later frozen replay.
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
OUT = AUDIT / f'v562_ssl_industry_midday_transmission_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v562_ssl_industry_midday_transmission_seed_latest.json'

LEFT = RIGHT = 3
VOLUME_LOOKBACK = 20
SWEEP_PCT = 0.003
FIRST120_BARS = 8
MIN_INDUSTRY_MEMBERS = 5
LEADER_TOP_PCT = 20.0
MAX_FIRST120_DD_PCT = -1.5
YEARS = ('2025', '2026')
SUPPORT = {'total_min': 1000, 'year_min': 300}


def positive(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


def load(path: Path) -> list[dict[str, Any]]:
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, list) else []
    except (OSError, ValueError):
        return []


def symbol_from(path: Path, frame: str) -> str:
    return path.name.removesuffix(f'_{frame}.json.gz').replace('_', '.')


def industry_map() -> dict[str, str]:
    payload = json.loads(INDUSTRY.read_text())
    return {
        str(row['symbol']): str(row.get('industry') or 'UNKNOWN').strip() or 'UNKNOWN'
        for row in payload if isinstance(row, dict) and row.get('symbol')
    }


def daily(path: Path) -> list[dict[str, Any]]:
    rows = []
    for raw in load(path):
        d = str(raw.get('d') or raw.get('t') or '')[:8]
        o, h, l, c, v = (positive(raw.get(key)) for key in ('o', 'h', 'l', 'c', 'v'))
        if d and None not in (o, h, l, c, v):
            rows.append({'d': d, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v})
    return sorted(rows, key=lambda row: row['d'])


def confirmed_swing_low(rows: list[dict[str, Any]], index: int) -> bool:
    if index < LEFT or index + RIGHT >= len(rows):
        return False
    return (rows[index]['l'] < min(row['l'] for row in rows[index - LEFT:index]) and
            rows[index]['l'] <= min(row['l'] for row in rows[index + 1:index + RIGHT + 1]))


def daily_ssl_seeds(symbol: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """All information here is fixed by each sweep-day close."""
    output = []
    for sweep_index in range(VOLUME_LOOKBACK + RIGHT + 1, len(rows) - 1):
        pivot_index = sweep_index - RIGHT - 1
        if not confirmed_swing_low(rows, pivot_index):
            continue
        pivot, sweep, next_day = rows[pivot_index], rows[sweep_index], rows[sweep_index + 1]
        prior_volumes = [row['v'] for row in rows[sweep_index - VOLUME_LOOKBACK:sweep_index]]
        if not (sweep['l'] <= pivot['l'] * (1 - SWEEP_PCT) and sweep['c'] > pivot['l'] and
                sweep['v'] >= median(prior_volumes)):
            continue
        output.append({
            'symbol': symbol,
            'pivot_date': pivot['d'],
            'pivot_low': round(pivot['l'], 6),
            'sweep_date': sweep['d'],
            'sweep_low': round(sweep['l'], 6),
            'sweep_close': round(sweep['c'], 6),
            'sweep_volume': round(sweep['v'], 6),
            'prior20_median_volume': round(median(prior_volumes), 6),
            'entry_date': next_day['d'],
            'causal_trace': 'confirmed_daily_3L3R_SSL -> volume_supported_wick_sweep_reclaim -> next_session_first120_industry_transmission -> earliest_1300_entry',
        })
    return output


def first120(path: Path, wanted: set[str], symbol: str, industry: str) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in load(path):
        date = str(raw.get('d') or raw.get('t') or '')[:8]
        if date in wanted:
            by_date[date].append(raw)
    output = []
    for date, session in by_date.items():
        session.sort(key=lambda row: str(row.get('t') or ''))
        if len(session) != 16:
            continue
        first = session[:FIRST120_BARS]
        future = session[FIRST120_BARS:]
        o = positive(first[0].get('o'))
        close = positive(first[-1].get('c'))
        lows = [positive(row.get('l')) for row in first]
        if o is None or close is None or any(value is None for value in lows) or not future:
            continue
        entry_open = positive(future[0].get('o'))
        if entry_open is None:
            continue
        amount = sum((positive(row.get('v')) or 0) * (positive(row.get('c')) or 0) for row in first)
        output.append({
            'symbol': symbol,
            'industry': industry,
            'entry_date': date,
            'm15_first120_end_time': str(first[-1].get('t') or ''),
            'm15_earliest_entry_time': str(future[0].get('t') or ''),
            'm15_entry_open': round(entry_open, 6),
            'stock_first120_ret_pct': round((close / o - 1) * 100, 6),
            'stock_first120_low_dd_pct': round((min(lows) / o - 1) * 100, 6),
            'stock_first120_amount': round(amount, 6),
        })
    return output


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    mapping = industry_map()
    daily_paths = sorted((RAW / 'daily').glob('*_daily.json.gz'))
    base = []
    for number, path in enumerate(daily_paths, 1):
        base.extend(daily_ssl_seeds(symbol_from(path, 'daily'), daily(path)))
        if number % 1000 == 0:
            print(json.dumps({'daily_files': number, 'ssl_seeds': len(base)}), flush=True)
    wanted = {row['entry_date'] for row in base if row['entry_date'][:4] in YEARS}
    features = []
    m15_paths = sorted((RAW / 'm15').glob('*_m15.json.gz'))
    for number, path in enumerate(m15_paths, 1):
        symbol = symbol_from(path, 'm15')
        features.extend(first120(path, wanted, symbol, mapping.get(symbol, 'UNKNOWN')))
        if number % 1000 == 0:
            print(json.dumps({'m15_files': number, 'first120_features': len(features)}), flush=True)

    feature_by_key = {(row['symbol'], row['entry_date']): row for row in features}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in features:
        if row['industry'] != 'UNKNOWN':
            grouped[(row['entry_date'], row['industry'])].append(row)
    stats: dict[tuple[str, str], dict[str, float]] = {}
    per_date = defaultdict(list)
    for key, members in grouped.items():
        if len(members) < MIN_INDUSTRY_MEMBERS:
            continue
        stat = {
            'industry_first120_ret_pct': median(row['stock_first120_ret_pct'] for row in members),
            'industry_first120_up_pct': 100 * sum(row['stock_first120_ret_pct'] >= 0 for row in members) / len(members),
            'industry_member_count': len(members),
        }
        stats[key] = stat
        per_date[key[0]].append((key[1], stat))
    for date, rows in per_date.items():
        for rank, (industry, stat) in enumerate(sorted(rows, key=lambda pair: pair[1]['industry_first120_ret_pct'], reverse=True), 1):
            stats[(date, industry)]['industry_return_rank_pct'] = round(100 * rank / len(rows), 6)

    chosen, missing_feature = [], 0
    for seed in base:
        if seed['entry_date'][:4] not in YEARS:
            continue
        feature = feature_by_key.get((seed['symbol'], seed['entry_date']))
        industry_stat = stats.get((seed['entry_date'], mapping.get(seed['symbol'], 'UNKNOWN')))
        if not feature or not industry_stat:
            missing_feature += 1
            continue
        leader = industry_stat['industry_return_rank_pct'] <= LEADER_TOP_PCT
        participates = (feature['stock_first120_ret_pct'] >= 0 and
                        feature['stock_first120_low_dd_pct'] >= MAX_FIRST120_DD_PCT)
        if leader and participates:
            chosen.append({**seed, **feature, **industry_stat,
                           'causal_identity': f"{seed['symbol']}|{seed['sweep_date']}|{seed['entry_date']}",
                           'contract_version': 'V562_SSL_SWEEP_MIDDAY_INDUSTRY_TRANSMISSION'})

    chosen.sort(key=lambda row: (row['entry_date'], row['symbol'], row['sweep_date']))
    years = Counter(row['entry_date'][:4] for row in chosen)
    chronology = all(row['pivot_date'] < row['sweep_date'] < row['entry_date'] and
                     row['m15_first120_end_time'] < row['m15_earliest_entry_time'] for row in chosen)
    no_outcome_fields = all(not any(token in key.lower() for key in row for token in ('pnl', 'exit', 'mfe', 'mae', 'target', 'stop', 'won')) for row in chosen)
    unique_identities = len({row['causal_identity'] for row in chosen})
    gate = {
        'same_source_daily_m15': len(daily_paths) == len(m15_paths),
        'daily_confirmation_before_sweep': all(row['pivot_date'] < row['sweep_date'] for row in chosen),
        'm15_observed_before_entry': chronology,
        'no_outcome_fields_read_or_written': no_outcome_fields,
        'unique_identities': unique_identities == len(chosen),
        'total_n>=1000': len(chosen) >= SUPPORT['total_min'],
        '2025_n>=300': years['2025'] >= SUPPORT['year_min'],
        '2026_n>=300': years['2026'] >= SUPPORT['year_min'],
    }
    fields = sorted({key for row in chosen for key in row}) or ['symbol', 'entry_date']
    csv_path = OUT / 'v562_outcome_blind_seeds.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(chosen)
    report = {
        'version': 'V562_SSL_INDUSTRY_MIDDAY_TRANSMISSION_SEED_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'source_contract': 'Sina source-isolated daily+m15 cache only; complete 5,528-symbol universe in available 2025-04..2026-07 range; no bar mixing.',
        'frozen_pre_outcome_contract': '3L/3R-confirmed daily SSL -> >=0.3% wick sweep -> close reclaim + volume >= prior20 median -> following session first120 industry median-return top20% + stock return>=0 and drawdown>=-1.5% -> earliest post-lunch M15 open.',
        'support_gate': SUPPORT,
        'counts': {'daily_ssl_base': len(base), 'candidate_entry_dates': len(wanted), 'first120_features': len(features), 'missing_feature_or_industry_stat': missing_feature, 'chosen_seeds': len(chosen), 'unique_identities': unique_identities, 'year_counts': dict(years)},
        'invariants': gate,
        'decision': 'V562_SUPPORT_PASS__INDEPENDENT_RAW_ORACLE_REQUIRED' if all(gate.values()) else 'V562_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_OBJECT',
        'artifacts': {'out_dir': str(OUT), 'seeds': str(csv_path), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v562_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
