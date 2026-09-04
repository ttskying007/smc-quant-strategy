#!/usr/bin/env python3
"""V609 independent raw-bar semantic witness for V603.

Audits V603 terminal records only from its chain identities and source-isolated
Sina m15 OHLC. It never imports the V603 generator and never opens outcome,
trade, PnL, stop, target, or exit artifacts.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/m15'
V603 = AUDIT / 'v603_reversal_state_machine_latest.json'
LATEST = AUDIT / 'v609_v603_full_raw_semantic_witness_latest.json'
OUT = AUDIT / f'v609_v603_full_raw_semantic_witness_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LEFT = RIGHT = 3
SWEEP_PCT = 0.003
MIN_BODY_RATIO = 0.50
CHOCH_MAX_BARS = 12
FVG_MAX_BARS = 3


def load_bars(symbol: str) -> list[dict]:
    path = RAW / f'{symbol.replace(".", "_")}_m15.json.gz'
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return []
    bars = []
    for item in raw if isinstance(raw, list) else []:
        try:
            t = str(item['t'])
            values = [float(item[key]) for key in ('o', 'h', 'l', 'c')]
            if len(t) == 14 and all(math.isfinite(value) and value > 0 for value in values):
                bars.append({'t': t, 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3]})
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(bars, key=lambda bar: bar['t'])


def pivot_sets(bars: list[dict]) -> tuple[set[int], set[int]]:
    lows, highs = set(), set()
    for i in range(LEFT, len(bars) - RIGHT):
        before, after = bars[i - LEFT:i], bars[i + 1:i + RIGHT + 1]
        if bars[i]['l'] < min(bar['l'] for bar in before) and bars[i]['l'] <= min(bar['l'] for bar in after):
            lows.add(i)
        if bars[i]['h'] > max(bar['h'] for bar in before) and bars[i]['h'] >= max(bar['h'] for bar in after):
            highs.add(i)
    return lows, highs


def ratio(bar: dict) -> float:
    span = bar['h'] - bar['l']
    return abs(bar['c'] - bar['o']) / span if span > 0 else 0.0


def num(row: dict, key: str) -> float:
    return float(row[key])


def check_valid(row: dict, bars: list[dict], ix: dict[str, int], low_pivots: set[int], high_pivots: set[int]) -> list[str]:
    required = ('ssl_pivot_time', 'ssl_confirmation_time', 'sweep_time', 'pre_sweep_reference_high_time',
                'pre_sweep_reference_high_confirmation_time', 'choch_time', 'ob_time', 'fvg_time',
                'first_touch_time', 'reclaim_time', 'hold_time', 'entry_time')
    if any(not row[key] or row[key] not in ix for key in required):
        return ['MISSING_VALID_IDENTITY']
    p, sweep, ref, choch, ob, fvg, touch, hold, entry = (ix[row[key]] for key in (
        'ssl_pivot_time', 'sweep_time', 'pre_sweep_reference_high_time', 'choch_time', 'ob_time',
        'fvg_time', 'first_touch_time', 'hold_time', 'entry_time'))
    failures = []
    ssl, reference, zone_low, zone_high = num(row, 'ssl_price'), num(row, 'pre_sweep_reference_high'), num(row, 'zone_low'), num(row, 'zone_high')
    if p not in low_pivots or bars[p]['t'] != row['ssl_pivot_time'] or abs(bars[p]['l'] - ssl) > 1e-8:
        failures.append('SSL_NOT_INDEPENDENTLY_CONFIRMED_PIVOT')
    if ix.get(row['ssl_confirmation_time']) != p + RIGHT or not p + RIGHT < sweep:
        failures.append('SSL_USED_BEFORE_RIGHT_CONFIRMATION')
    if not (bars[sweep]['l'] <= ssl * (1 - SWEEP_PCT) and bars[sweep]['c'] > ssl):
        failures.append('SWEEP_NOT_WICK_PIERCE_AND_RECLAIM')
    if not (ref in high_pivots and p < ref < sweep and abs(bars[ref]['h'] - reference) <= 1e-8):
        failures.append('REFERENCE_HIGH_NOT_CONFIRMED_PRE_SWEEP_PIVOT')
    if ix.get(row['pre_sweep_reference_high_confirmation_time']) != ref + RIGHT or not ref + RIGHT < sweep:
        failures.append('REFERENCE_HIGH_USED_BEFORE_RIGHT_CONFIRMATION')
    later_highs = [j for j in high_pivots if p < j < sweep and j + RIGHT < sweep]
    if later_highs and ref != max(later_highs):
        failures.append('REFERENCE_HIGH_NOT_LATEST_CONFIRMED_BEFORE_SWEEP')
    if not (sweep < choch <= sweep + CHOCH_MAX_BARS and bars[choch]['c'] > reference and bars[choch]['c'] > bars[choch]['o'] and ratio(bars[choch]) >= MIN_BODY_RATIO):
        failures.append('CHOCH_NOT_QUALIFIED_CLOSE_ACCEPTANCE')
    if any(bars[j]['c'] > reference and bars[j]['c'] > bars[j]['o'] and ratio(bars[j]) >= MIN_BODY_RATIO for j in range(sweep + 1, choch)):
        failures.append('CHOCH_NOT_FIRST_QUALIFIED_ACCEPTANCE')
    if not (choch < fvg <= choch + FVG_MAX_BARS and fvg >= 2 and bars[fvg - 2]['h'] < bars[fvg]['l']):
        failures.append('FVG_NOT_POST_CHOCH_BULLISH_DISPLACEMENT')
    if abs(zone_low - bars[fvg - 2]['h']) > 1e-8 or abs(zone_high - bars[fvg]['l']) > 1e-8:
        failures.append('ZONE_NOT_EQUAL_TO_CAUSAL_FVG')
    bearish = [j for j in range(sweep + 1, min(choch, fvg - 2)) if bars[j]['c'] < bars[j]['o']]
    if not bearish or ob != bearish[-1] or not (sweep < ob < choch):
        failures.append('OB_NOT_LAST_BEARISH_CANDLE_BEFORE_DISPLACEMENT')
    actual_touch = next((j for j in range(fvg + 1, touch + 1) if bars[j]['l'] <= zone_high and bars[j]['h'] >= zone_low), None)
    if actual_touch != touch:
        failures.append('RECORDED_TOUCH_NOT_FIRST_ZONE_INTERSECTION')
    if not (bars[touch]['l'] >= zone_low and bars[touch]['c'] >= zone_high and row['first_touch_time'] == row['reclaim_time']):
        failures.append('FIRST_TOUCH_NOT_VALID_RECLAIM')
    if hold != touch + 1 or entry != hold + 1:
        failures.append('HOLD_OR_ENTRY_NOT_STRICTLY_NEXT_BAR')
    elif not (bars[hold]['l'] >= zone_low and bars[hold]['c'] >= zone_high):
        failures.append('HOLD_NOT_ABOVE_VALID_ZONE')
    return failures


def check_terminal(row: dict, bars: list[dict], ix: dict[str, int]) -> list[str]:
    """Audit the two L3 rejection states against their first touch alone."""
    reason = row['cancel_reason']
    if reason not in {'CANCEL_FIRST_TOUCH_FAILED', 'CANCEL_ZONE_INVALIDATED_FIRST_TOUCH'}:
        return []
    needed = ('fvg_time', 'first_touch_time', 'zone_low', 'zone_high')
    if any(not row[key] or row[key] not in ix for key in needed[:2]):
        return ['MISSING_CANCEL_IDENTITY']
    fvg, touch = ix[row['fvg_time']], ix[row['first_touch_time']]
    low, high = num(row, 'zone_low'), num(row, 'zone_high')
    actual = next((j for j in range(fvg + 1, touch + 1) if bars[j]['l'] <= high and bars[j]['h'] >= low), None)
    if actual != touch:
        return ['CANCEL_RECORDED_TOUCH_NOT_FIRST_ZONE_INTERSECTION']
    if reason == 'CANCEL_ZONE_INVALIDATED_FIRST_TOUCH' and not bars[touch]['l'] < low:
        return ['CANCEL_INVALIDATION_NOT_LOW_BREACH']
    if reason == 'CANCEL_FIRST_TOUCH_FAILED' and not (bars[touch]['l'] >= low and bars[touch]['c'] < high):
        return ['CANCEL_FIRST_TOUCH_FAILURE_RULE_MISMATCH']
    return []


def audit_symbol(task: tuple[str, list[dict]]) -> tuple[Counter, list[dict]]:
    symbol, rows = task
    bars = load_bars(symbol)
    ix = {bar['t']: i for i, bar in enumerate(bars)}
    low_pivots, high_pivots = pivot_sets(bars)
    checks, failures = Counter(), []
    for row in rows:
        if row['terminal_status'] == 'VALID_CHAIN':
            checks['valid_rows'] += 1
            found = check_valid(row, bars, ix, low_pivots, high_pivots)
        else:
            checks['l3_cancel_rows'] += 1
            found = check_terminal(row, bars, ix)
        checks['failure_count'] += len(found)
        for failure in found:
            checks[f'failure::{failure}'] += 1
            if len(failures) < 20:
                failures.append({'symbol': symbol, 'chain_key': row['chain_key'], 'terminal_status': row['terminal_status'], 'cancel_reason': row['cancel_reason'], 'failure': failure})
    return checks, failures


def main() -> None:
    source = json.loads(V603.read_text())
    with Path(source['artifacts']['chain_audit']).open(encoding='utf-8', newline='') as handle:
        all_rows = list(csv.DictReader(handle))
    selected = [row for row in all_rows if row['terminal_status'] == 'VALID_CHAIN' or row['cancel_reason'] in {'CANCEL_FIRST_TOUCH_FAILED', 'CANCEL_ZONE_INVALIDATED_FIRST_TOUCH'}]
    by_symbol: defaultdict[str, list[dict]] = defaultdict(list)
    for row in selected:
        by_symbol[row['symbol']].append(row)
    checks, failures = Counter(), []
    with ProcessPoolExecutor(max_workers=8) as pool:
        for local_checks, local_failures in pool.map(audit_symbol, sorted(by_symbol.items()), chunksize=16):
            checks.update(local_checks)
            failures.extend(local_failures)
    duplicate_time = Counter((row['symbol'], row['entry_time']) for row in selected if row['terminal_status'] == 'VALID_CHAIN')
    duplicate_date = Counter((row['symbol'], row['entry_time'][:8]) for row in selected if row['terminal_status'] == 'VALID_CHAIN')
    invariants = {
        'all_valid_nodes_independently_qualified': checks['failure_count'] == 0,
        'all_l3_cancellations_match_first_touch_rule': not any(key.startswith('failure::CANCEL_') for key in checks),
        'no_duplicate_valid_symbol_entry_time': all(value == 1 for value in duplicate_time.values()),
        'no_duplicate_valid_symbol_entry_date': all(value == 1 for value in duplicate_date.values()),
        'outcome_blind': True,
    }
    OUT.mkdir(parents=True, exist_ok=False)
    report = {
        'version': 'V609_V603_FULL_RAW_SEMANTIC_WITNESS_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'input_contract': 'V603 terminal chain identities + source-isolated Sina m15 OHLC only. No performance or execution-outcome data are opened.',
        'scope': 'Independent checks: confirmed SSL/reference pivots, sweep/reclaim, first qualified CHOCH acceptance, post-CHOCH FVG, causal OB anchor, pristine first touch, reclaim, hold, next-bar identity, and L3 cancellation rules.',
        'counts': {'selected_terminal_rows': len(selected), 'valid_rows': checks['valid_rows'], 'l3_cancel_rows': checks['l3_cancel_rows'], 'failure_count': checks['failure_count'], 'failure_by_type': {key.removeprefix('failure::'): value for key, value in checks.items() if key.startswith('failure::')}, 'failure_samples': failures[:50]},
        'invariants': invariants,
        'decision': 'V609_FULL_RAW_SEMANTIC_WITNESS_PASS__STAGE2_EVIDENCE_COMPLETE__REPLAY_STILL_REQUIRES_SEPARATE_FROZEN_EXECUTION_CONTRACT' if all(invariants.values()) else 'V609_FULL_RAW_SEMANTIC_WITNESS_FAIL__DO_NOT_REPLAY_OR_PROMOTE',
        'artifacts': {'out_dir': str(OUT), 'v603': str(V603), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v609_report.json').write_text(text, encoding='utf-8')
    LATEST.write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
