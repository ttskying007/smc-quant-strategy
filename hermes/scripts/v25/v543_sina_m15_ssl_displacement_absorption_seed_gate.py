#!/usr/bin/env python3
"""V543 outcome-blind absorption/displacement m15 seed gate.

New causal ontology, fixed before any V543 trade outcome is read:
  SSL sweep with exceptional local participation
  -> bullish displacement BOS and FVG with exceptional participation
  -> first FVG retest on contracted participation and close reclaim
  -> next unobserved m15 entry.

The mechanism targets V542's observed failure mode (the prior price-only chain
was stopped before meaningful expansion too often). This script reads only raw
Sina m15 OHLCV and writes only outcome-blind identities.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/m15'
AUDIT = ROOT / 'smc_audit'
OUT = AUDIT / f'v543_sina_m15_ssl_displacement_absorption_seed_gate_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v543_sina_m15_ssl_displacement_absorption_seed_gate_latest.json'
LEFT = RIGHT = 3
LOOKBACK = 20
SWEEP_PCT = 0.003
SWEEP_VOL_Q = 0.80
BOS_MAX_BARS = 12
RETEST_MAX_BARS = 20
DISPLACEMENT_RANGE_MULT = 1.20
DISPLACEMENT_VOL_MULT = 1.20
FVG_WIDTH_RANGE_MULT = 0.50
RETEST_VOL_MAX_MULT = 1.00
SUPPORT = {'total_min': 300, 'each_year_min': 80, 'unique_symbols_min': 150}


def num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


def load_rows(path: Path) -> list[dict[str, Any]]:
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return []
    result: list[dict[str, Any]] = []
    for row in raw if isinstance(raw, list) else []:
        t = str(row.get('t') or '')
        values = [num(row.get(key)) for key in ('o', 'h', 'l', 'c', 'v')]
        if len(t) == 14 and all(value is not None for value in values):
            result.append({'t': t, 'd': str(row.get('d') or t[:8])[:8], 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3], 'v': values[4]})
    return sorted(result, key=lambda row: row['t'])


def pivots(rows: list[dict[str, Any]]) -> tuple[set[int], set[int]]:
    lows, highs = set(), set()
    for i in range(LEFT, len(rows) - RIGHT):
        before, after = rows[i - LEFT:i], rows[i + 1:i + RIGHT + 1]
        if rows[i]['l'] < min(row['l'] for row in before) and rows[i]['l'] <= min(row['l'] for row in after):
            lows.add(i)
        if rows[i]['h'] > max(row['h'] for row in before) and rows[i]['h'] >= max(row['h'] for row in after):
            highs.add(i)
    return lows, highs


def baseline(rows: list[dict[str, Any]], i: int) -> tuple[float, float, float] | None:
    if i < LOOKBACK:
        return None
    prior = rows[i - LOOKBACK:i]
    ranges = [row['h'] - row['l'] for row in prior]
    volumes = sorted(row['v'] for row in prior)
    quantile_index = math.ceil(SWEEP_VOL_Q * len(volumes)) - 1
    return median(ranges), volumes[quantile_index], median(volumes)


def symbol(path: Path) -> str:
    return path.name.removesuffix('_m15.json.gz').replace('_', '.')


def generate(ticker: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lows, highs = pivots(rows)
    bases = [baseline(rows, i) for i in range(len(rows))]
    known_low: int | None = None
    known_high: int | None = None
    states: list[dict[str, Any]] = []
    emitted: list[dict[str, Any]] = []
    last_entry = -1
    for i, bar in enumerate(rows):
        eligible = i - RIGHT - 1
        if eligible in lows:
            known_low, known_high = eligible, None
        if eligible in highs and known_low is not None and eligible > known_low and rows[eligible]['h'] > rows[known_low]['l']:
            known_high = eligible
        still: list[dict[str, Any]] = []
        for state in states:
            phase = state['phase']
            if phase == 'WAIT_BOS':
                if i - state['sweep_i'] > BOS_MAX_BARS:
                    continue
                base = bases[i]
                if base is not None:
                    range_med, _, volume_median = base
                    body = bar['c'] - bar['o']
                    if bar['c'] > state['reference_high'] and body >= range_med * DISPLACEMENT_RANGE_MULT and bar['v'] >= volume_median * DISPLACEMENT_VOL_MULT:
                        state.update({'phase': 'WAIT_FVG', 'bos_i': i, 'bos_t': bar['t'], 'bos_body': body, 'bos_vol': bar['v']})
                still.append(state)
                continue
            if phase == 'WAIT_FVG':
                if i - state['bos_i'] > RETEST_MAX_BARS:
                    continue
                base = bases[i]
                if base is not None and i >= 2:
                    range_med, _, volume_median = base
                    gap = bar['l'] - rows[i - 2]['h']
                    if rows[i - 2]['h'] < bar['l'] and gap >= range_med * FVG_WIDTH_RANGE_MULT and bar['v'] >= volume_median * DISPLACEMENT_VOL_MULT:
                        state.update({'phase': 'WAIT_RETEST', 'fvg_i': i, 'fvg_t': bar['t'], 'fvg_low': rows[i - 2]['h'], 'fvg_high': bar['l'], 'fvg_gap': gap, 'fvg_vol': bar['v']})
                still.append(state)
                continue
            if i - state['fvg_i'] > RETEST_MAX_BARS:
                continue
            base = bases[i]
            if base is not None:
                _, _, volume_median = base
                touch = i > state['fvg_i'] and bar['l'] <= state['fvg_high'] and bar['h'] >= state['fvg_low']
                if touch and bar['c'] >= state['fvg_high'] and bar['v'] <= volume_median * RETEST_VOL_MAX_MULT:
                    entry_i = i + 1
                    if entry_i < len(rows) and entry_i > last_entry:
                        entry = rows[entry_i]
                        emitted.append({'symbol': ticker, 'source': 'sina', 'frame': 'm15', 'swing_time': rows[state['pivot_i']]['t'], 'sweep_time': rows[state['sweep_i']]['t'], 'reference_high_time': rows[state['reference_high_i']]['t'], 'bos_time': state['bos_t'], 'fvg_time': state['fvg_t'], 'reclaim_time': bar['t'], 'entry_time': entry['t'], 'entry_date': entry['d'], 'reference_low': round(state['reference_low'], 6), 'reference_high': round(state['reference_high'], 6), 'fvg_low': round(state['fvg_low'], 6), 'fvg_high': round(state['fvg_high'], 6), 'sweep_vol_rank_threshold': SWEEP_VOL_Q, 'sweep_vol': round(state['sweep_vol'], 6), 'sweep_vol_q80': round(state['sweep_vol_q80'], 6), 'bos_vol': round(state['bos_vol'], 6), 'fvg_vol': round(state['fvg_vol'], 6), 'retest_vol': round(bar['v'], 6), 'retest_vol_median20': round(volume_median, 6), 'causal_sequence': 'confirmed_SSL>high_participation_sweep>high_participation_displacement_BOS_FVG>low_participation_first_retest_reclaim>next_m15_entry'})
                        last_entry = entry_i
                else:
                    still.append(state)
            else:
                still.append(state)
        states = still
        if known_low is None or known_high is None or i < LOOKBACK:
            continue
        range_med, vol_q80, volume_median = bases[i] or (0.0, math.inf, math.inf)
        pivot = rows[known_low]
        if bar['l'] <= pivot['l'] * (1 - SWEEP_PCT) and bar['c'] > pivot['l'] and bar['v'] >= vol_q80 and known_high < i:
            states.append({'phase': 'WAIT_BOS', 'pivot_i': known_low, 'sweep_i': i, 'reference_low': pivot['l'], 'reference_high': rows[known_high]['h'], 'reference_high_i': known_high, 'sweep_vol': bar['v'], 'sweep_vol_q80': vol_q80, 'sweep_vol_median': volume_median})
    return emitted


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    all_seeds: list[dict[str, Any]] = []
    malformed = 0
    for path in sorted(RAW.glob('*_m15.json.gz')):
        rows = load_rows(path)
        if len(rows) < 100:
            malformed += 1
            continue
        all_seeds.extend(generate(symbol(path), rows))
    seeds = [row for row in all_seeds if row['entry_date'][:4] in {'2025', '2026'}]
    years = Counter(row['entry_date'][:4] for row in seeds)
    symbols = {row['symbol'] for row in seeds}
    invariant = {'source_isolated_sina_only': all(row['source'] == 'sina' for row in seeds), 'ohlcv_available_for_every_seed': all(row['sweep_vol'] > 0 and row['bos_vol'] > 0 and row['fvg_vol'] > 0 and row['retest_vol'] > 0 for row in seeds), 'no_outcome_fields': all(not any(key in row for key in ('exit_time', 'pnl', 'return', 'stop', 'target')) for row in seeds), 'strict_entry_after_reclaim': all(row['entry_time'] > row['reclaim_time'] for row in seeds), 'total_n>=300': len(seeds) >= SUPPORT['total_min'], '2025_n>=80': years['2025'] >= SUPPORT['each_year_min'], '2026_n>=80': years['2026'] >= SUPPORT['each_year_min'], 'unique_symbols_n>=150': len(symbols) >= SUPPORT['unique_symbols_min']}
    fields = list(seeds[0]) if seeds else ['symbol']
    csv_path = OUT / 'v543_outcome_blind_seeds.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(seeds)
    report = {'version': 'V543_SINA_M15_SSL_DISPLACEMENT_ABSORPTION_SEED_GATE_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False, 'authorized_input_gate': 'READ_AUTHORIZED_PARTIAL_SAME_SOURCE_ONLY (Sina OHLCV)', 'scope': 'SINA_SOURCE_ISOLATED_PARTIAL_RANGE_2025_04_TO_2026_07_ONLY', 'hypothesis': 'The price-only V539 failure is a participation-quality defect: require high-participation stop sweep plus volume/range displacement, then a low-participation FVG retest reclaim.', 'frozen_pre_outcome_contract': f'confirmed 3L/3R SSL; wick sweep >=0.3% with volume >= prior20 q80; <=12 bars bullish BOS with body >=1.2x prior20 median range and volume >=1.2x prior20 median volume; bullish FVG width >=0.5x median range and volume >=1.2x median volume; <=20 bars first interval touch/reclaim with volume <=1.0x prior20 median; next unobserved m15 entry.', 'parameters_fixed_before_outcomes': {'lookback': LOOKBACK, 'sweep_vol_quantile': SWEEP_VOL_Q, 'sweep_pct': SWEEP_PCT, 'bos_max_bars': BOS_MAX_BARS, 'displacement_range_mult': DISPLACEMENT_RANGE_MULT, 'displacement_vol_mult': DISPLACEMENT_VOL_MULT, 'fvg_width_range_mult': FVG_WIDTH_RANGE_MULT, 'retest_vol_max_mult': RETEST_VOL_MAX_MULT, 'retest_max_bars': RETEST_MAX_BARS}, 'coverage': {'m15_files_scanned': len(list(RAW.glob('*_m15.json.gz'))), 'malformed_or_short_files': malformed}, 'seed_count': len(seeds), 'year_counts': dict(years), 'unique_symbols': len(symbols), 'support_gate': SUPPORT, 'invariants': invariant, 'decision': 'V543_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED' if all(invariant.values()) else 'V543_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_OBJECT', 'artifacts': {'dir': str(OUT), 'seeds': str(csv_path)}}
    text = json.dumps(report, ensure_ascii=False, indent=2); (OUT / 'v543_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__':
    main()
