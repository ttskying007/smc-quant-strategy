#!/usr/bin/env python3
"""V603 result-blind 15m reversal state machine.

This replaces neither V539 nor any production path. It materializes only
semantic lifecycle records from the same source-isolated Sina m15 OHLC cache.
It never reads returns, trades, stops, targets, PnL, watchlists, or frontend
artifacts, and it never writes to them.

Frozen semantic chain:
  confirmed SSL -> wick sweep/reclaim -> pre-sweep-high CHOCH ->
  post-CHOCH bullish displacement/FVG -> causal bearish OB ->
  FRESH -> FIRST_TOUCH -> RECLAIM -> HOLD -> next-bar identity.

The purpose is Stage 0 semantic validation, not a replay or an optimisation.
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
OUT = AUDIT / f'v603_ssl_choch_displacement_pristine_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v603_ssl_choch_displacement_pristine_state_machine_latest.json'

LEFT = RIGHT = 3
SWEEP_PCT = 0.003
CHOCH_MAX_BARS = 12
DISPLACEMENT_MAX_BARS = 20
TOUCH_MAX_BARS = 20

FIELDS = [
    'symbol', 'source', 'timeframe', 'status', 'cancel_reason',
    'ssl_pivot_time', 'ssl_confirmation_time', 'sweep_time', 'sweep_low',
    'pre_sweep_reference_high_time', 'pre_sweep_reference_high', 'choch_time',
    'displacement_start_time', 'displacement_end_time', 'ob_time', 'fvg_time',
    'zone_kind', 'zone_low', 'zone_high', 'first_touch_time', 'reclaim_time',
    'hold_time', 'entry_time', 'invalidated_time', 'causal_sequence',
]


def num(value: Any) -> float | None:
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
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
    return sorted(rows, key=lambda row: row['t'])


def pivots(rows: list[dict[str, Any]]) -> tuple[set[int], set[int]]:
    lows, highs = set(), set()
    for i in range(LEFT, len(rows) - RIGHT):
        before = rows[i - LEFT:i]
        after = rows[i + 1:i + RIGHT + 1]
        if rows[i]['l'] < min(row['l'] for row in before) and rows[i]['l'] <= min(row['l'] for row in after):
            lows.add(i)
        if rows[i]['h'] > max(row['h'] for row in before) and rows[i]['h'] >= max(row['h'] for row in after):
            highs.add(i)
    return lows, highs


def symbol_from_path(path: Path) -> str:
    return path.name.removesuffix('_m15.json.gz').replace('_', '.')


def blank_record(symbol: str, state: dict[str, Any], status: str, reason: str = '') -> dict[str, Any]:
    row = {
        'symbol': symbol,
        'source': 'sina',
        'timeframe': 'm15',
        'status': status,
        'cancel_reason': reason,
        'ssl_pivot_time': state.get('ssl_pivot_time', ''),
        'ssl_confirmation_time': state.get('ssl_confirmation_time', ''),
        'sweep_time': state.get('sweep_time', ''),
        'sweep_low': state.get('sweep_low', ''),
        'pre_sweep_reference_high_time': state.get('reference_high_time', ''),
        'pre_sweep_reference_high': state.get('reference_high', ''),
        'choch_time': state.get('choch_time', ''),
        'displacement_start_time': state.get('displacement_start_time', ''),
        'displacement_end_time': state.get('displacement_end_time', ''),
        'ob_time': state.get('ob_time', ''),
        'fvg_time': state.get('fvg_time', ''),
        'zone_kind': state.get('zone_kind', ''),
        'zone_low': state.get('zone_low', ''),
        'zone_high': state.get('zone_high', ''),
        'first_touch_time': state.get('first_touch_time', ''),
        'reclaim_time': state.get('reclaim_time', ''),
        'hold_time': state.get('hold_time', ''),
        'entry_time': state.get('entry_time', ''),
        'invalidated_time': state.get('invalidated_time', ''),
        'causal_sequence': 'confirmed_SSL>wick_sweep_reclaim>pre_sweep_high_CHOCH>post_CHOCH_displacement>causal_OB+FVG>FRESH>FIRST_TOUCH>RECLAIM>HOLD>next_bar',
    }
    return row


def causal_ob(rows: list[dict[str, Any]], state: dict[str, Any], displacement_i: int) -> int | None:
    # The OB is the final bearish candle before the displacement leg, after the
    # sweep, and is explicitly never the CHOCH/break bar itself.
    for i in range(displacement_i - 1, state['sweep_i'], -1):
        if i != state['choch_i'] and rows[i]['c'] < rows[i]['o']:
            return i
    return None


def is_displacement_fvg(rows: list[dict[str, Any]], state: dict[str, Any], i: int) -> bool:
    if i < 2 or i - 1 <= state['choch_i']:
        return False
    first, middle, last = rows[i - 2], rows[i - 1], rows[i]
    body = middle['c'] - middle['o']
    span = middle['h'] - middle['l']
    return (
        first['d'] == middle['d'] == last['d']
        and first['h'] < last['l']
        and body > 0
        and span > 0
        and body >= span * 0.5
        and middle['c'] > state['reference_high']
    )


def make_sweep_state(rows: list[dict[str, Any]], pivot_i: int, reference_high_i: int, sweep_i: int) -> dict[str, Any]:
    return {
        'phase': 'WAIT_CHOCH',
        'pivot_i': pivot_i,
        'sweep_i': sweep_i,
        'ssl_pivot_time': rows[pivot_i]['t'],
        'ssl_confirmation_time': rows[pivot_i + RIGHT]['t'],
        'sweep_time': rows[sweep_i]['t'],
        'sweep_low': round(rows[sweep_i]['l'], 6),
        'reference_high_time': rows[reference_high_i]['t'],
        'reference_high': round(rows[reference_high_i]['h'], 6),
    }


def generate(symbol: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    low_pivots, high_pivots = pivots(rows)
    records: list[dict[str, Any]] = []
    active: dict[str, Any] | None = None
    known_low_i: int | None = None
    known_high_i: int | None = None

    for i, bar in enumerate(rows):
        # A pivot becomes actionable only after all three right-side bars have
        # closed. The next loop iteration is the first eligible decision bar.
        just_confirmed = i - RIGHT - 1
        if just_confirmed in low_pivots:
            known_low_i = just_confirmed
            known_high_i = None
        if (
            just_confirmed in high_pivots
            and known_low_i is not None
            and just_confirmed > known_low_i
            and rows[just_confirmed]['h'] > rows[known_low_i]['l']
        ):
            known_high_i = just_confirmed

        is_new_sweep = (
            known_low_i is not None
            and known_high_i is not None
            and known_high_i < i
            and bar['l'] <= rows[known_low_i]['l'] * (1 - SWEEP_PCT)
            and bar['c'] > rows[known_low_i]['l']
        )
        if is_new_sweep:
            # Mutual exclusion: a new sweep starts a new reversal story and
            # explicitly cancels every unfinished prior story for this symbol.
            if active is not None:
                active['invalidated_time'] = bar['t']
                records.append(blank_record(symbol, active, 'CANCELLED_CHAIN', 'CANCELLED_BY_NEW_SWEEP'))
            active = make_sweep_state(rows, known_low_i, known_high_i, i)
            continue

        if active is None:
            continue

        if active['phase'] == 'WAIT_CHOCH':
            if i - active['sweep_i'] > CHOCH_MAX_BARS:
                records.append(blank_record(symbol, active, 'EXPIRED_CHAIN', 'EXPIRED_CHOCH_WINDOW'))
                active = None
            elif bar['c'] > active['reference_high']:
                active['phase'] = 'WAIT_DISPLACEMENT'
                active['choch_i'] = i
                active['choch_time'] = bar['t']
            continue

        if active['phase'] == 'WAIT_DISPLACEMENT':
            if i - active['choch_i'] > DISPLACEMENT_MAX_BARS:
                records.append(blank_record(symbol, active, 'EXPIRED_CHAIN', 'EXPIRED_DISPLACEMENT_WINDOW'))
                active = None
            elif is_displacement_fvg(rows, active, i):
                ob_i = causal_ob(rows, active, i - 1)
                if ob_i is None:
                    records.append(blank_record(symbol, active, 'CANCELLED_CHAIN', 'CANCELLED_NO_CAUSAL_OB'))
                    active = None
                else:
                    active.update({
                        'phase': 'FRESH',
                        'displacement_start_time': rows[i - 1]['t'],
                        'displacement_end_time': bar['t'],
                        'ob_time': rows[ob_i]['t'],
                        'fvg_time': bar['t'],
                        'zone_kind': 'BULL_FVG_FROM_POST_CHOCH_DISPLACEMENT',
                        'zone_low': round(rows[i - 2]['h'], 6),
                        'zone_high': round(bar['l'], 6),
                        'fvg_i': i,
                    })
            continue

        if active['phase'] == 'FRESH':
            if i - active['fvg_i'] > TOUCH_MAX_BARS:
                records.append(blank_record(symbol, active, 'EXPIRED_CHAIN', 'EXPIRED_PRISTINE_TOUCH_WINDOW'))
                active = None
                continue
            touched = bar['l'] <= active['zone_high'] and bar['h'] >= active['zone_low']
            if not touched:
                continue
            active['first_touch_time'] = bar['t']
            if bar['l'] < active['zone_low']:
                active['invalidated_time'] = bar['t']
                records.append(blank_record(symbol, active, 'CANCELLED_CHAIN', 'CANCEL_ZONE_INVALIDATED_ON_FIRST_TOUCH'))
                active = None
            elif bar['c'] >= active['zone_high']:
                active['phase'] = 'RECLAIM'
                active['reclaim_time'] = bar['t']
            else:
                records.append(blank_record(symbol, active, 'CANCELLED_CHAIN', 'CANCEL_FIRST_TOUCH_FAILED_RECLAIM'))
                active = None
            continue

        # RECLAIM has exactly one permitted next state: HOLD. The hold result
        # determines the identity of the following, still-unobserved entry bar.
        if bar['l'] < active['zone_low']:
            active['invalidated_time'] = bar['t']
            records.append(blank_record(symbol, active, 'CANCELLED_CHAIN', 'CANCEL_ZONE_INVALIDATED_BEFORE_HOLD'))
            active = None
        elif bar['c'] >= active['zone_high']:
            active['hold_time'] = bar['t']
            if i + 1 < len(rows):
                active['entry_time'] = rows[i + 1]['t']
                records.append(blank_record(symbol, active, 'VALID_CHAIN'))
            else:
                records.append(blank_record(symbol, active, 'EXPIRED_CHAIN', 'EXPIRED_NEXT_ENTRY_UNOBSERVED'))
            active = None
        else:
            records.append(blank_record(symbol, active, 'CANCELLED_CHAIN', 'CANCEL_HOLD_FAILED'))
            active = None

    if active is not None:
        records.append(blank_record(symbol, active, 'EXPIRED_CHAIN', 'EXPIRED_RIGHT_EDGE_UNOBSERVED'))
    return records


def validate(records: list[dict[str, Any]]) -> dict[str, int | bool]:
    valid = [row for row in records if row['status'] == 'VALID_CHAIN']
    entry_counts = Counter((row['symbol'], row['entry_time']) for row in valid)
    terminal = {'VALID_CHAIN', 'CANCELLED_CHAIN', 'EXPIRED_CHAIN'}
    ordered = 0
    for row in valid:
        sequence = [
            row['ssl_pivot_time'], row['ssl_confirmation_time'], row['sweep_time'],
            row['pre_sweep_reference_high_time'], row['choch_time'],
            row['displacement_start_time'], row['displacement_end_time'],
            row['ob_time'], row['fvg_time'], row['first_touch_time'],
            row['reclaim_time'], row['hold_time'], row['entry_time'],
        ]
        if all(sequence) and row['ssl_pivot_time'] < row['ssl_confirmation_time'] < row['sweep_time'] and row['pre_sweep_reference_high_time'] < row['sweep_time'] < row['choch_time'] < row['displacement_start_time'] < row['displacement_end_time'] <= row['fvg_time'] < row['first_touch_time'] <= row['reclaim_time'] < row['hold_time'] < row['entry_time'] and row['ob_time'] < row['displacement_start_time']:
            ordered += 1
    return {
        'all_records_terminal': all(row['status'] in terminal for row in records),
        'valid_chains': len(valid),
        'valid_chains_with_strict_chronology': ordered,
        'chronology_violations': len(valid) - ordered,
        'duplicate_symbol_entry_time': sum(count - 1 for count in entry_counts.values() if count > 1),
        'max_valid_per_symbol_entry_time': max(entry_counts.values(), default=0),
        'ob_on_choch_bar': sum(row['ob_time'] == row['choch_time'] for row in valid),
        'valid_with_multiple_touch_records': sum(bool(row['first_touch_time']) and row['first_touch_time'] != row['reclaim_time'] for row in valid),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, Any]] = []
    malformed = 0
    files = sorted(RAW.glob('*_m15.json.gz'))
    for path in files:
        rows = load_rows(path)
        if len(rows) < 100:
            malformed += 1
            continue
        records.extend(generate(symbol_from_path(path), rows))

    csv_path = OUT / 'v603_semantic_lifecycle_records.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)

    checks = validate(records)
    statuses = Counter(row['status'] for row in records)
    reasons = Counter(row['cancel_reason'] for row in records if row['cancel_reason'])
    semantic_pass = (
        checks['all_records_terminal']
        and checks['chronology_violations'] == 0
        and checks['duplicate_symbol_entry_time'] == 0
        and checks['ob_on_choch_bar'] == 0
        and checks['valid_with_multiple_touch_records'] == 0
    )
    report = {
        'version': 'V603_SSL_CHOCH_DISPLACEMENT_PRISTINE_STATE_MACHINE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'scope': 'SINA_SOURCE_ISOLATED_M15_PARTIAL_RANGE_ONLY',
        'purpose': 'Stage-0 semantic state-machine validation only. No replay, optimisation, or strategy quality conclusion.',
        'frozen_contract': {
            'l1': '3L/3R-confirmed SSL; later >=0.3% wick sweep and close reclaim; pre-sweep confirmed reference high required.',
            'l2': 'Close above that pre-sweep high within 12 bars; a later same-session bullish FVG with a body-dominant central candle above the reference high defines displacement; causal OB is the final bearish candle after sweep, before displacement, and never the CHOCH bar.',
            'l3': 'FRESH -> first interval touch -> immediate reclaim or permanent cancellation -> one next-bar HOLD -> next-bar entry identity. One active chain per symbol; a new sweep cancels the old chain.',
        },
        'files_scanned': len(files),
        'malformed_or_short_files': malformed,
        'record_count': len(records),
        'status_counts': dict(statuses),
        'terminal_reason_counts': dict(reasons),
        'semantic_invariants': checks,
        'semantic_decision': (
            'V603_STAGE0_SEMANTIC_PASS__MANUAL_CHAIN_REVIEW_REQUIRED__REPLAY_PROHIBITED'
            if semantic_pass else
            'V603_STAGE0_SEMANTIC_FAIL__NO_REPLAY_OR_PROMOTION'
        ),
        'artifacts': {'dir': str(OUT), 'records': str(csv_path)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v603_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
