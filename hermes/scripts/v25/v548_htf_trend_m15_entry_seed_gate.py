#!/usr/bin/env python3
"""V548 outcome-blind same-source HTF trend -> m15 entry seed gate.

This is a new architecture, not an exit/threshold variant of V543:
  completed weekly trend regime -> completed daily continuation regime
  -> m15 SSL sweep -> displacement BOS/FVG -> first retest/reclaim -> next m15.

Every parent condition is known strictly before the entry session.  This file
only emits causal identities; it neither loads nor derives trade outcomes.
"""
from __future__ import annotations

import csv
import gzip
from concurrent.futures import ProcessPoolExecutor
import json
import math
from bisect import bisect_right
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina'
AUDIT = ROOT / 'smc_audit'
OUT = AUDIT / f'v548_htf_trend_m15_entry_seed_gate_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v548_htf_trend_m15_entry_seed_gate_latest.json'
LEFT = RIGHT = 3
LOOKBACK = 20
SWEEP_PCT = 0.003
VOL_Q = 0.80
BOS_MAX = 12
RETEST_MAX = 20
DISP_RANGE = 1.20
DISP_VOL = 1.20
FVG_RANGE = 0.50
RETEST_VOL = 1.00
YEARS = ('2025', '2026')
SUPPORT = {'total_min': 300, 'each_year_min': 80, 'unique_symbols_min': 150}


def number(value: Any) -> float | None:
    try:
        value = float(value)
        return value if value > 0 and math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def read_gzip(path: Path, frame: str) -> list[dict[str, Any]]:
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return []
    rows = []
    for row in raw if isinstance(raw, list) else []:
        stamp = str(row.get('t') or '')
        date = str(row.get('d') or stamp[:8])[:8]
        values = [number(row.get(key)) for key in ('o', 'h', 'l', 'c', 'v')]
        valid_stamp = len(stamp) == 14 if frame == 'm15' else len(date) == 8
        if valid_stamp and len(date) == 8 and all(value is not None for value in values):
            rows.append({'t': stamp if frame == 'm15' else date, 'd': date,
                         'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3], 'v': values[4]})
    return sorted(rows, key=lambda row: row['t'])


def pivots(rows: list[dict[str, Any]]) -> tuple[list[tuple[int, int, float]], list[tuple[int, int, float]]]:
    lows, highs = [], []
    for index in range(LEFT, len(rows) - RIGHT):
        before, after = rows[index - LEFT:index], rows[index + 1:index + RIGHT + 1]
        if rows[index]['l'] < min(row['l'] for row in before) and rows[index]['l'] <= min(row['l'] for row in after):
            lows.append((index, index + RIGHT, rows[index]['l']))
        if rows[index]['h'] > max(row['h'] for row in before) and rows[index]['h'] >= max(row['h'] for row in after):
            highs.append((index, index + RIGHT, rows[index]['h']))
    return lows, highs


def completed_weeks(daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[list[dict[str, Any]]] = []
    current = None
    for row in daily:
        week = datetime.strptime(row['d'], '%Y%m%d').date().isocalendar()[:2]
        if week != current:
            groups.append([])
            current = week
        groups[-1].append(row)
    return [{'d': group[-1]['d'], 'o': group[0]['o'], 'h': max(row['h'] for row in group),
             'l': min(row['l'] for row in group), 'c': group[-1]['c'], 'v': sum(row['v'] for row in group)}
            for group in groups[:-1] if group]


def trend_state(rows: list[dict[str, Any]], lows: list[tuple[int, int, float]], highs: list[tuple[int, int, float]], asof: str) -> dict[str, Any] | None:
    """Resolve a trend from pivots whose right-side confirmation is pre-entry."""
    dates = [row['d'] for row in rows]
    last_index = bisect_right(dates, asof) - 1
    if last_index < 2 * RIGHT + 8 or rows[last_index]['d'] >= asof:
        last_index -= 1
    low_count = bisect_right([item[1] for item in lows], last_index)
    high_count = bisect_right([item[1] for item in highs], last_index)
    if low_count < 2 or high_count < 1:
        return None
    prior_low, latest_low = lows[low_count - 2], lows[low_count - 1]
    known_highs = highs[:high_count]
    structure_high = next((item for item in reversed(known_highs) if item[0] > latest_low[0]), known_highs[-1])
    last = rows[last_index]
    if not (latest_low[2] > prior_low[2] and last['c'] > structure_high[2]):
        return None
    return {'trend_confirm_date': last['d'], 'prior_low_date': rows[prior_low[0]]['d'],
            'latest_low_date': rows[latest_low[0]]['d'], 'structure_high_date': rows[structure_high[0]]['d'],
            'protected_low': latest_low[2], 'break_level': structure_high[2]}


def rolling_baseline(rows: list[dict[str, Any]], index: int) -> tuple[float, float, float] | None:
    if index < LOOKBACK:
        return None
    prior = rows[index - LOOKBACK:index]
    ranges = [row['h'] - row['l'] for row in prior]
    volumes = sorted(row['v'] for row in prior)
    return median(ranges), volumes[math.ceil(VOL_Q * len(volumes)) - 1], median(volumes)


def m15_entries(symbol: str, rows: list[dict[str, Any]], weekly: list[dict[str, Any]], daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lows, highs = pivots(rows)
    weekly_lows, weekly_highs = pivots(weekly)
    daily_lows, daily_highs = pivots(daily)
    low_indices = {index for index, _, _ in lows}
    high_indices = {index for index, _, _ in highs}
    baselines = [rolling_baseline(rows, index) for index in range(len(rows))]
    known_low = known_high = None
    states: list[dict[str, Any]] = []
    emitted: list[dict[str, Any]] = []
    last_entry = -1
    for index, bar in enumerate(rows):
        eligible = index - RIGHT - 1
        if eligible in low_indices:
            known_low, known_high = eligible, None
        if eligible in high_indices and known_low is not None and eligible > known_low and rows[eligible]['h'] > rows[known_low]['l']:
            known_high = eligible
        still = []
        for state in states:
            if state['phase'] == 'BOS':
                if index - state['sweep_i'] <= BOS_MAX:
                    base = baselines[index]
                    if base is not None:
                        range_med, _, volume_med = base
                        body = bar['c'] - bar['o']
                        if bar['c'] > state['reference_high'] and body >= range_med * DISP_RANGE and bar['v'] >= volume_med * DISP_VOL:
                            state.update({'phase': 'FVG', 'bos_i': index, 'bos_time': bar['t'], 'bos_vol': bar['v']})
                    still.append(state)
                continue
            if state['phase'] == 'FVG':
                if index - state['bos_i'] <= RETEST_MAX:
                    base = baselines[index]
                    if base is not None and index >= 2:
                        range_med, _, volume_med = base
                        gap = bar['l'] - rows[index - 2]['h']
                        if gap > 0 and gap >= range_med * FVG_RANGE and bar['v'] >= volume_med * DISP_VOL:
                            state.update({'phase': 'RETEST', 'fvg_i': index, 'fvg_time': bar['t'],
                                          'fvg_low': rows[index - 2]['h'], 'fvg_high': bar['l'], 'fvg_vol': bar['v']})
                    still.append(state)
                continue
            if index - state['fvg_i'] <= RETEST_MAX:
                base = baselines[index]
                if base is not None:
                    _, _, volume_med = base
                    touch = index > state['fvg_i'] and bar['l'] <= state['fvg_high'] and bar['h'] >= state['fvg_low']
                    if touch and bar['c'] >= state['fvg_high'] and bar['v'] <= volume_med * RETEST_VOL:
                        entry_i = index + 1
                        if entry_i < len(rows) and entry_i > last_entry:
                            entry = rows[entry_i]
                            weekly_state = trend_state(weekly, weekly_lows, weekly_highs, entry['d'])
                            daily_state = trend_state(daily, daily_lows, daily_highs, entry['d'])
                            if weekly_state and daily_state:
                                emitted.append({'symbol': symbol, 'source': 'sina', 'entry_frame': 'm15',
                                    'entry_time': entry['t'], 'entry_date': entry['d'],
                                    'weekly_trend_confirm_date': weekly_state['trend_confirm_date'],
                                    'weekly_latest_hl_date': weekly_state['latest_low_date'],
                                    'weekly_structure_high_date': weekly_state['structure_high_date'],
                                    'daily_trend_confirm_date': daily_state['trend_confirm_date'],
                                    'daily_latest_hl_date': daily_state['latest_low_date'],
                                    'daily_structure_high_date': daily_state['structure_high_date'],
                                    'm15_ssl_pivot_time': rows[state['pivot_i']]['t'], 'm15_sweep_time': rows[state['sweep_i']]['t'],
                                    'm15_bos_time': state['bos_time'], 'm15_fvg_time': state['fvg_time'],
                                    'm15_reclaim_time': bar['t'], 'm15_fvg_low': round(state['fvg_low'], 6),
                                    'm15_fvg_high': round(state['fvg_high'], 6),
                                    'causal_sequence': 'completed_weekly_HL_BOS_trend>completed_daily_HL_BOS_trend>confirmed_m15_SSL>m15_high_participation_sweep>m15_displacement_BOS_FVG>m15_low_participation_first_retest_reclaim>next_m15_entry'})
                                last_entry = entry_i
                    else:
                        still.append(state)
                else:
                    still.append(state)
        states = still
        if known_low is None or known_high is None or index < LOOKBACK:
            continue
        base = baselines[index]
        if base is None:
            continue
        _, q80, _ = base
        pivot = rows[known_low]
        if bar['l'] <= pivot['l'] * (1 - SWEEP_PCT) and bar['c'] > pivot['l'] and bar['v'] >= q80:
            states.append({'phase': 'BOS', 'pivot_i': known_low, 'sweep_i': index, 'reference_high': rows[known_high]['h']})
    return emitted


def process_symbol(m15_path: Path) -> tuple[list[dict[str, Any]], str | None]:
    symbol = m15_path.name.removesuffix('_m15.json.gz').replace('_', '.')
    daily_path = RAW / 'daily' / m15_path.name.replace('_m15.json.gz', '_daily.json.gz')
    m15, daily = read_gzip(m15_path, 'm15'), read_gzip(daily_path, 'daily')
    weekly = completed_weeks(daily)
    if len(m15) < 100 or len(daily) < 40 or len(weekly) < 12:
        return [], 'missing_or_short_source'
    return m15_entries(symbol, m15, weekly, daily), None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    all_rows = []
    incomplete = Counter()
    m15_paths = sorted((RAW / 'm15').glob('*_m15.json.gz'))
    with ProcessPoolExecutor(max_workers=8) as pool:
        for position, (seeds, reason) in enumerate(pool.map(process_symbol, m15_paths, chunksize=16), 1):
            if reason:
                incomplete[reason] += 1
            all_rows.extend(seeds)
            if position % 500 == 0:
                print(json.dumps({'symbols': position, 'seeds': len(all_rows)}), flush=True)
    rows = [row for row in all_rows if row['entry_date'][:4] in YEARS]
    dedup = {(row['symbol'], row['entry_time']): row for row in rows}
    rows = sorted(dedup.values(), key=lambda row: (row['entry_time'], row['symbol']))
    years = Counter(row['entry_date'][:4] for row in rows)
    invariants = {
        'source_isolated_sina_only': all(row['source'] == 'sina' for row in rows),
        'all_parent_states_before_entry': all(row['weekly_trend_confirm_date'] < row['entry_date'] and row['daily_trend_confirm_date'] < row['entry_date'] for row in rows),
        'strict_intraday_order': all(row['m15_ssl_pivot_time'] < row['m15_sweep_time'] < row['m15_bos_time'] <= row['m15_fvg_time'] < row['m15_reclaim_time'] < row['entry_time'] for row in rows),
        'no_outcome_fields': all(not any(key in row for key in ('pnl', 'return', 'exit', 'mfe', 'mae', 'target', 'stop')) for row in rows),
        'total_n>=300': len(rows) >= SUPPORT['total_min'],
        'each_year_n>=80': all(years[year] >= SUPPORT['each_year_min'] for year in YEARS),
        'unique_symbols_n>=150': len({row['symbol'] for row in rows}) >= SUPPORT['unique_symbols_min'],
    }
    seed_path = OUT / 'v548_outcome_blind_seeds.csv'
    fields = list(rows[0]) if rows else ['symbol', 'entry_time']
    with seed_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    report = {
        'version': 'V548_HTF_TREND_M15_ENTRY_SEED_GATE_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'SINA_SOURCE_ISOLATED_PARTIAL_RANGE_2025_04_TO_2026_07_ONLY__NOT_PRODUCTION',
        'hypothesis': 'The missing information is not a lower-timeframe threshold but parent trend alignment: require completed weekly and daily higher-low/bullish-BOS regimes before the m15 takeover lifecycle can be eligible.',
        'frozen_pre_outcome_contract': 'Completed weekly HL+BOS trend strictly before session; completed daily HL+BOS trend strictly before session; then confirmed m15 SSL -> high-participation sweep -> displacement BOS/FVG -> low-participation first touch/reclaim -> next m15 open identity. No execution outcome is read.',
        'parameters_fixed_before_outcomes': {'pivot_left_right': [LEFT, RIGHT], 'volume_lookback': LOOKBACK, 'sweep_pct': SWEEP_PCT, 'sweep_vol_quantile': VOL_Q, 'm15_bos_max_bars': BOS_MAX, 'm15_retest_max_bars': RETEST_MAX, 'displacement_range_mult': DISP_RANGE, 'displacement_volume_mult': DISP_VOL, 'fvg_range_mult': FVG_RANGE, 'retest_volume_max_mult': RETEST_VOL},
        'coverage': {'m15_files_scanned': len(m15_paths), 'incomplete': dict(incomplete)}, 'seed_count': len(rows),
        'year_counts': dict(years), 'unique_symbols': len({row['symbol'] for row in rows}), 'support_gate': SUPPORT,
        'invariants': invariants,
        'decision': 'V548_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED' if all(invariants.values()) else 'V548_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_OBJECT',
        'artifacts': {'out_dir': str(OUT), 'seeds': str(seed_path), 'latest': str(LATEST)}}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v548_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__':
    main()
