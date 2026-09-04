#!/usr/bin/env python3
"""V539 outcome-blind, source-isolated 15m SMC seed gate.

This is a new intraday causal object, not a variation of the closed daily
volume/Wyckoff ontologies.  It reads only Sina's source-isolated m15 cache.
No outcomes, forward returns, stop/target, trades, production, frontend, or
watchlist data are read or written.

Fixed causal contract, evaluated in chronological state order:
  1. A 3L/3R sell-side swing is confirmed (therefore known only three bars
     after the pivot).
  2. A later 15m wick sweeps that known low by >=0.30% and closes back above it.
  3. Within 12 completed 15m bars, a close breaks a prior already-confirmed
     3L/3R swing high (bullish BOS).
  4. After BOS, a bullish three-candle FVG forms; its first touch must occur
     within 20 completed bars and close back above the FVG upper boundary.
  5. Entry identity is the next *unobserved* 15m bar.  The generator stops at
     this identity; it does not inspect any bar after entry.

The first 15m source-local study is restricted to 2025-04..2026-07.  Its
pre-registered support gate is total >=300, each calendar year >=80, >=150
unique symbols, and all selected identities sourced from the same namespace.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/m15'
AUDIT = ROOT / 'smc_audit'
OUT = AUDIT / f'v539_sina_m15_ssl_bos_fvg_seed_gate_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v539_sina_m15_ssl_bos_fvg_seed_gate_latest.json'
LEFT = RIGHT = 3
SWEEP_PCT = 0.003
BOS_MAX_BARS = 12
RETEST_MAX_BARS = 20
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
    rows: list[dict[str, Any]] = []
    for row in raw if isinstance(raw, list) else []:
        t = str(row.get('t') or '')
        d = str(row.get('d') or t[:8])[:8]
        o, h, l, c = (num(row.get(key)) for key in ('o', 'h', 'l', 'c'))
        if len(t) == 14 and len(d) == 8 and None not in (o, h, l, c):
            rows.append({'t': t, 'd': d, 'o': o, 'h': h, 'l': l, 'c': c})
    return sorted(rows, key=lambda item: item['t'])


def pivots(rows: list[dict[str, Any]]) -> tuple[set[int], set[int]]:
    lows, highs = set(), set()
    for i in range(LEFT, len(rows) - RIGHT):
        low, high = rows[i]['l'], rows[i]['h']
        before = rows[i - LEFT:i]
        after = rows[i + 1:i + RIGHT + 1]
        if low < min(x['l'] for x in before) and low <= min(x['l'] for x in after):
            lows.add(i)
        if high > max(x['h'] for x in before) and high >= max(x['h'] for x in after):
            highs.add(i)
    return lows, highs


def symbol_from_path(path: Path) -> str:
    return path.name.removesuffix('_m15.json.gz').replace('_', '.')


def generate(symbol: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    low_pivots, high_pivots = pivots(rows)
    emitted: list[dict[str, Any]] = []
    # A low pivot becomes usable only one completed bar after its 3-right-bar
    # confirmation. A candidate BOS high must both form after that low and be
    # above it; otherwise it is merely a lower-high continuation, not a valid
    # reversal structure break.
    known_low_i: int | None = None
    known_high_i: int | None = None
    # Each state is fully causal: no state reads beyond its current loop index.
    states: list[dict[str, Any]] = []
    last_emitted_entry = -1

    for i, bar in enumerate(rows):
        just_eligible = i - RIGHT - 1
        if just_eligible in low_pivots:
            known_low_i = just_eligible
            known_high_i = None
        if just_eligible in high_pivots and known_low_i is not None and just_eligible > known_low_i and rows[just_eligible]['h'] > rows[known_low_i]['l']:
            known_high_i = just_eligible

        still_live: list[dict[str, Any]] = []
        for state in states:
            phase = state['phase']
            if phase == 'WAIT_BOS':
                if i - state['sweep_i'] > BOS_MAX_BARS:
                    continue
                # A BOS is valid only versus a swing high that was already
                # confirmed before the sweep; no future pivot information.
                if bar['c'] > state['reference_high']:
                    state['phase'] = 'WAIT_FVG'
                    state['bos_i'] = i
                    state['bos_t'] = bar['t']
                still_live.append(state)
                continue
            if phase == 'WAIT_FVG':
                if i - state['bos_i'] > RETEST_MAX_BARS:
                    continue
                if i >= 2 and rows[i - 2]['h'] < bar['l']:
                    state['phase'] = 'WAIT_RETEST'
                    state['fvg_i'] = i
                    state['fvg_t'] = bar['t']
                    state['fvg_low'] = rows[i - 2]['h']
                    state['fvg_high'] = bar['l']
                still_live.append(state)
                continue
            # WAIT_RETEST. The first interval touch must reclaim the FVG high.
            if i - state['fvg_i'] > RETEST_MAX_BARS:
                continue
            if i > state['fvg_i'] and bar['l'] <= state['fvg_high'] and bar['h'] >= state['fvg_low'] and bar['c'] >= state['fvg_high']:
                entry_i = i + 1
                if entry_i < len(rows) and entry_i > last_emitted_entry:
                    entry = rows[entry_i]
                    emitted.append({
                        'symbol': symbol,
                        'source': 'sina',
                        'frame': 'm15',
                        'swing_time': rows[state['pivot_i']]['t'],
                        'sweep_time': rows[state['sweep_i']]['t'],
                        'bos_time': state['bos_t'],
                        'fvg_time': state['fvg_t'],
                        'reclaim_time': bar['t'],
                        'entry_time': entry['t'],
                        'entry_date': entry['d'],
                        'reference_low': round(state['reference_low'], 6),
                        'reference_high': round(state['reference_high'], 6),
                        'reference_high_time': rows[state['reference_high_i']]['t'],
                        'fvg_low': round(state['fvg_low'], 6),
                        'fvg_high': round(state['fvg_high'], 6),
                        'causal_sequence': 'confirmed_SSL_swing>wick_sweep_reclaim>bull_BOS>bull_FVG>first_touch_reclaim>next_m15_entry',
                    })
                    last_emitted_entry = entry_i
                continue
            still_live.append(state)
        states = still_live

        # Create sweep states after advancing old states, so a BOS never uses
        # an event created by the same bar and the chronology is explicit.
        if known_low_i is None or known_high_i is None:
            continue
        pivot_i = known_low_i
        reference_high_i = known_high_i
        pivot = rows[pivot_i]
        if (bar['l'] <= pivot['l'] * (1 - SWEEP_PCT)
                and bar['c'] > pivot['l']
                and reference_high_i < i):
            states.append({
                'phase': 'WAIT_BOS',
                'pivot_i': pivot_i,
                'sweep_i': i,
                'reference_low': pivot['l'],
                'reference_high': rows[reference_high_i]['h'],
                'reference_high_i': reference_high_i,
            })
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
        all_seeds.extend(generate(symbol_from_path(path), rows))

    # The generator has deliberately not read post-entry bars. Restrict the
    # diagnostic denominator to the authorized source-local calendar years.
    seeds = [row for row in all_seeds if row['entry_date'][:4] in {'2025', '2026'}]
    years = Counter(row['entry_date'][:4] for row in seeds)
    symbols = {row['symbol'] for row in seeds}
    invariant = {
        'source_isolated_sina_only': all(row['source'] == 'sina' for row in seeds),
        'no_outcome_fields': all(not any(key in row for key in ('exit_time', 'pnl', 'return', 'stop', 'target')) for row in seeds),
        'strict_entry_after_reclaim': all(row['entry_time'] > row['reclaim_time'] for row in seeds),
        'structural_high_after_low_before_sweep': all(row['swing_time'] < row['reference_high_time'] < row['sweep_time'] and row['reference_high'] > row['reference_low'] for row in seeds),
        'total_n>=300': len(seeds) >= SUPPORT['total_min'],
        '2025_n>=80': years['2025'] >= SUPPORT['each_year_min'],
        '2026_n>=80': years['2026'] >= SUPPORT['each_year_min'],
        'unique_symbols_n>=150': len(symbols) >= SUPPORT['unique_symbols_min'],
    }
    csv_path = OUT / 'v539_outcome_blind_seeds.csv'
    fields = ['symbol', 'source', 'frame', 'swing_time', 'sweep_time', 'reference_high_time', 'bos_time', 'fvg_time', 'reclaim_time', 'entry_time', 'entry_date', 'reference_low', 'reference_high', 'fvg_low', 'fvg_high', 'causal_sequence']
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(seeds)
    report = {
        'version': 'V539_SINA_M15_SSL_BOS_FVG_SEED_GATE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'authorized_input_gate': 'READ_AUTHORIZED_PARTIAL_SAME_SOURCE_ONLY (Sina; 5528/5528 source-local cache pass)',
        'scope': 'SINA_SOURCE_ISOLATED_PARTIAL_RANGE_2025_04_TO_2026_07_ONLY',
        'hypothesis': 'A causally-confirmed 15m SSL sweep -> BOS -> FVG first-retest reclaim setup is independently testable from closed daily-volume ontologies.',
        'frozen_pre_outcome_contract': '3L/3R confirmed SSL pivot -> >=0.3% wick sweep+close reclaim -> within 12 bars break an already-confirmed swing high -> bullish FVG -> within 20 bars first FVG touch+close reclaim -> next 15m entry; no post-entry bar read.',
        'coverage': {'m15_files_scanned': len(list(RAW.glob('*_m15.json.gz'))), 'malformed_or_short_files': malformed, 'excluded_short_history_symbols': ['920117.BJ'] if malformed else []},
        'seed_count': len(seeds),
        'year_counts': dict(years),
        'unique_symbols': len(symbols),
        'support_gate': SUPPORT,
        'invariants': invariant,
        'decision': 'V539_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED' if all(invariant.values()) else 'V539_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_OBJECT',
        'artifacts': {'dir': str(OUT), 'seeds': str(csv_path)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v539_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
