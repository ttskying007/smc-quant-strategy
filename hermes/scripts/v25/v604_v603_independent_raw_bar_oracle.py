#!/usr/bin/env python3
"""Independent raw-bar semantic oracle for V603 lifecycle records.

This is deliberately read-only and recomputes the causal facts from the raw
Sina m15 bars; it does not import or call the V603 generator.
"""
from __future__ import annotations

import csv
import gzip
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/m15'
AUDIT = ROOT / 'smc_audit'
INPUT = AUDIT / 'v603_ssl_choch_displacement_pristine_state_machine_latest.json'
OUT = AUDIT / 'v604_v603_independent_raw_bar_oracle_latest.json'
LEFT = RIGHT = 3
SWEEP_PCT = 0.003


def bars_for(symbol: str) -> list[dict]:
    path = RAW / f'{symbol.replace(".", "_")}_m15.json.gz'
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return []
    bars = []
    for row in raw if isinstance(raw, list) else []:
        try:
            bars.append({
                't': str(row['t']), 'd': str(row.get('d') or str(row['t'])[:8])[:8],
                'o': float(row['o']), 'h': float(row['h']),
                'l': float(row['l']), 'c': float(row['c']),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(bars, key=lambda row: row['t'])


def is_low_pivot(bars: list[dict], i: int) -> bool:
    if i < LEFT or i + RIGHT >= len(bars):
        return False
    return (
        bars[i]['l'] < min(bar['l'] for bar in bars[i - LEFT:i])
        and bars[i]['l'] <= min(bar['l'] for bar in bars[i + 1:i + RIGHT + 1])
    )


def is_high_pivot(bars: list[dict], i: int) -> bool:
    if i < LEFT or i + RIGHT >= len(bars):
        return False
    return (
        bars[i]['h'] > max(bar['h'] for bar in bars[i - LEFT:i])
        and bars[i]['h'] >= max(bar['h'] for bar in bars[i + 1:i + RIGHT + 1])
    )


def touch(bar: dict, low: float, high: float) -> bool:
    return bar['l'] <= high and bar['h'] >= low


def check_common(row: dict, bars: list[dict], ix: dict[str, int]) -> list[str]:
    errors: list[str] = []
    try:
        pivot, sweep, ref = (ix[row[key]] for key in ('ssl_pivot_time', 'sweep_time', 'pre_sweep_reference_high_time'))
    except KeyError:
        return ['MISSING_L1_TIME']
    if not is_low_pivot(bars, pivot):
        errors.append('SSL_NOT_3L3R_PIVOT')
    if row['ssl_confirmation_time'] != bars[pivot + RIGHT]['t']:
        errors.append('SSL_CONFIRMATION_TIME_WRONG')
    if not (pivot + RIGHT < sweep and bars[sweep]['l'] <= bars[pivot]['l'] * (1 - SWEEP_PCT) and bars[sweep]['c'] > bars[pivot]['l']):
        errors.append('SWEEP_NOT_CONFIRMED_WICK_RECLAIM')
    if not (is_high_pivot(bars, ref) and pivot < ref and ref + RIGHT < sweep and bars[ref]['h'] > bars[pivot]['l']):
        errors.append('REFERENCE_HIGH_NOT_PRE_SWEEP_CONFIRMED')
    return errors


def check_complete_path(row: dict, bars: list[dict], ix: dict[str, int]) -> list[str]:
    errors = check_common(row, bars, ix)
    need = ['choch_time', 'displacement_start_time', 'displacement_end_time', 'ob_time', 'fvg_time', 'zone_low', 'zone_high']
    if any(not row[key] for key in need):
        return errors + ['MISSING_POST_L1_FIELD']
    try:
        sweep, ref, choch, middle, fvg, ob = (ix[row[key]] for key in (
            'sweep_time', 'pre_sweep_reference_high_time', 'choch_time',
            'displacement_start_time', 'fvg_time', 'ob_time'))
    except KeyError:
        return errors + ['MISSING_POST_L1_TIME']
    first = ix.get(row['first_touch_time']) if row['first_touch_time'] else None
    low, high = float(row['zone_low']), float(row['zone_high'])
    if not (sweep < choch and bars[choch]['c'] > bars[ref]['h']):
        errors.append('CHOCH_NOT_CLOSE_ABOVE_REFERENCE_HIGH')
    if any(bar['c'] > bars[ref]['h'] for bar in bars[sweep + 1:choch]):
        errors.append('CHOCH_NOT_FIRST_POST_SWEEP_BREAK')
    if not (middle > choch and fvg == middle + 1 and bars[fvg - 2]['d'] == bars[middle]['d'] == bars[fvg]['d']):
        errors.append('DISPLACEMENT_TIME_ORDER_WRONG')
    body = bars[middle]['c'] - bars[middle]['o']
    span = bars[middle]['h'] - bars[middle]['l']
    if not (bars[fvg - 2]['h'] < bars[fvg]['l'] and body > 0 and span > 0 and body >= span * 0.5 and bars[middle]['c'] > bars[ref]['h']):
        errors.append('DISPLACEMENT_FVG_CONTRACT_BROKEN')
    if not (low == round(bars[fvg - 2]['h'], 6) and high == round(bars[fvg]['l'], 6)):
        errors.append('FVG_ZONE_BOUNDARY_WRONG')
    expected_ob = next((i for i in range(middle - 1, sweep, -1) if i != choch and bars[i]['c'] < bars[i]['o']), None)
    if expected_ob is None or ob != expected_ob or ob == choch:
        errors.append('CAUSAL_OB_NOT_LAST_BEARISH_PRE_DISPLACEMENT')
    if first is not None:
        if any(touch(bar, low, high) for bar in bars[fvg + 1:first]):
            errors.append('ZONE_TOUCHED_BEFORE_RECORDED_FIRST_TOUCH')
        if not touch(bars[first], low, high):
            errors.append('RECORDED_FIRST_TOUCH_NOT_A_TOUCH')
    return errors


def check_terminal(row: dict, bars: list[dict], ix: dict[str, int]) -> list[str]:
    reason = row['cancel_reason']
    # Full FVG/OB checks apply only after that POI was actually created.
    # A chain that expires while waiting for displacement has a valid CHOCH
    # but deliberately has no FVG/OB fields to validate.
    errors = check_complete_path(row, bars, ix) if row['fvg_time'] else check_common(row, bars, ix)
    if row['choch_time'] and not errors:
        try:
            sweep = ix[row['sweep_time']]
            ref = ix[row['pre_sweep_reference_high_time']]
            choch = ix[row['choch_time']]
            if not (sweep < choch and bars[choch]['c'] > bars[ref]['h']):
                errors.append('CHOCH_NOT_CLOSE_ABOVE_REFERENCE_HIGH')
            if any(bar['c'] > bars[ref]['h'] for bar in bars[sweep + 1:choch]):
                errors.append('CHOCH_NOT_FIRST_POST_SWEEP_BREAK')
        except KeyError:
            errors.append('MISSING_CHOCH_TIME')
    if row['status'] == 'VALID_CHAIN':
        for key in ('reclaim_time', 'hold_time', 'entry_time'):
            if not row[key]:
                errors.append('VALID_MISSING_TERMINAL_TIME')
        if errors:
            return errors
        first, reclaim, hold, entry = (ix[row[key]] for key in ('first_touch_time', 'reclaim_time', 'hold_time', 'entry_time'))
        low, high = float(row['zone_low']), float(row['zone_high'])
        if not (first == reclaim and bars[first]['l'] >= low and bars[first]['c'] >= high):
            errors.append('VALID_FIRST_TOUCH_NOT_IMMEDIATE_RECLAIM')
        if not (hold == reclaim + 1 and bars[hold]['l'] >= low and bars[hold]['c'] >= high):
            errors.append('VALID_HOLD_CONTRACT_BROKEN')
        if entry != hold + 1:
            errors.append('VALID_ENTRY_NOT_NEXT_BAR')
    elif reason == 'CANCEL_FIRST_TOUCH_FAILED_RECLAIM':
        first = ix.get(row['first_touch_time'])
        if first is None or row['reclaim_time'] or bars[first]['l'] < float(row['zone_low']) or bars[first]['c'] >= float(row['zone_high']):
            errors.append('FIRST_TOUCH_FAILURE_REASON_WRONG')
    elif reason == 'CANCEL_ZONE_INVALIDATED_ON_FIRST_TOUCH':
        first = ix.get(row['first_touch_time'])
        if first is None or bars[first]['l'] >= float(row['zone_low']):
            errors.append('FIRST_TOUCH_INVALIDATION_REASON_WRONG')
    elif reason == 'CANCEL_ZONE_INVALIDATED_BEFORE_HOLD':
        reclaim = ix.get(row['reclaim_time'])
        invalid = ix.get(row['invalidated_time'])
        if reclaim is None or invalid != reclaim + 1 or bars[invalid]['l'] >= float(row['zone_low']):
            errors.append('HOLD_INVALIDATION_REASON_WRONG')
    elif reason == 'CANCEL_HOLD_FAILED':
        reclaim = ix.get(row['reclaim_time'])
        if reclaim is None or not (ix.get(row['hold_time'], -99) == -99):
            errors.append('HOLD_FAILURE_TIME_WRONG')
        elif not (bars[reclaim + 1]['l'] >= float(row['zone_low']) and bars[reclaim + 1]['c'] < float(row['zone_high'])):
            errors.append('HOLD_FAILURE_REASON_WRONG')
    return errors


def main() -> None:
    source = json.loads(INPUT.read_text())
    with Path(source['artifacts']['records']).open(encoding='utf-8', newline='') as handle:
        records = list(csv.DictReader(handle))
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in records:
        grouped[row['symbol']].append(row)

    failures: Counter[str] = Counter()
    samples: list[dict] = []
    checked = 0
    valid_entries: Counter[tuple[str, str]] = Counter()
    for symbol, rows in sorted(grouped.items()):
        bars = bars_for(symbol)
        ix = {bar['t']: i for i, bar in enumerate(bars)}
        for row in rows:
            checked += 1
            errors = check_terminal(row, bars, ix)
            for error in errors:
                failures[error] += 1
            if errors and len(samples) < 30:
                samples.append({'symbol': symbol, 'status': row['status'], 'reason': row['cancel_reason'], 'errors': errors})
            if row['status'] == 'VALID_CHAIN':
                valid_entries[(symbol, row['entry_time'])] += 1

    duplicate_entries = sum(count - 1 for count in valid_entries.values() if count > 1)
    report = {
        'version': 'V604_V603_INDEPENDENT_RAW_BAR_SEMANTIC_ORACLE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'input': source['artifacts']['records'],
        'method': 'Independent raw-bar validation of confirmed pivots, sweep/reclaim, pre-sweep reference-high CHOCH, post-CHOCH displacement/FVG, causal OB, pristine first-touch lifecycle, hold, and next-bar identity. No generator import and no return/exit data.',
        'records_checked': checked,
        'raw_bar_semantic_failures': dict(failures),
        'duplicate_valid_symbol_entry_time': duplicate_entries,
        'samples': samples,
        'decision': (
            'V604_RAW_BAR_SEMANTIC_ORACLE_PASS__STAGE2_MANUAL_REVIEW_REQUIRED__REPLAY_PROHIBITED'
            if not failures and duplicate_entries == 0 else
            'V604_RAW_BAR_SEMANTIC_ORACLE_FAIL__NO_REPLAY_OR_PROMOTION'
        ),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
