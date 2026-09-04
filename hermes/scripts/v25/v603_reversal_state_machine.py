#!/usr/bin/env python3
"""V603 outcome-blind 15m reversal SMC state machine.

This is a semantic reconstruction, not a strategy replay. It reads only raw
Sina 15m OHLC, never reads outcome/trade/PnL/risk data, and writes only a
research audit artifact. The frozen contract is:
SSL -> wick sweep/reclaim -> CHOCH -> displacement FVG + causal OB ->
pristine first touch/reclaim -> one hold bar -> next-bar identity.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/m15'
AUDIT = ROOT / 'smc_audit'
CONTRACT = AUDIT / 'v603_reversal_state_machine_semantic_contract.json'
OUT = AUDIT / f'v603_reversal_state_machine_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v603_reversal_state_machine_latest.json'
LEFT = RIGHT = 3
CHOCH_MAX_BARS = 12
FVG_MAX_BARS = 3
TOUCH_MAX_BARS = 20
SWEEP_PCT = 0.003
MIN_BODY_RATIO = 0.50

FIELDS = [
    'symbol', 'timeframe', 'terminal_status', 'cancel_reason',
    'ssl_pivot_time', 'ssl_confirmation_time', 'ssl_price',
    'sweep_time', 'sweep_low', 'pre_sweep_reference_high_time',
    'pre_sweep_reference_high_confirmation_time', 'pre_sweep_reference_high',
    'choch_time', 'choch_close', 'choch_body_ratio',
    'displacement_start_time', 'displacement_end_time',
    'ob_time', 'ob_low', 'ob_high', 'fvg_time', 'zone_low', 'zone_high',
    'first_touch_time', 'reclaim_time', 'hold_time', 'entry_time',
    'invalidated_time', 'chain_key',
]


def positive(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def load_rows(path: Path) -> list[dict[str, Any]]:
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return []
    rows = []
    for item in raw if isinstance(raw, list) else []:
        t = str(item.get('t') or '')
        d = str(item.get('d') or t[:8])[:8]
        values = [positive(item.get(key)) for key in ('o', 'h', 'l', 'c')]
        if len(t) == 14 and len(d) == 8 and all(value is not None for value in values):
            rows.append({'t': t, 'd': d, 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3]})
    return sorted(rows, key=lambda row: row['t'])


def pivots(rows: list[dict[str, Any]]) -> tuple[set[int], set[int]]:
    lows, highs = set(), set()
    for i in range(LEFT, len(rows) - RIGHT):
        before, after = rows[i - LEFT:i], rows[i + 1:i + RIGHT + 1]
        if rows[i]['l'] < min(row['l'] for row in before) and rows[i]['l'] <= min(row['l'] for row in after):
            lows.add(i)
        if rows[i]['h'] > max(row['h'] for row in before) and rows[i]['h'] >= max(row['h'] for row in after):
            highs.add(i)
    return lows, highs


def symbol_from_path(path: Path) -> str:
    return path.name.removesuffix('_m15.json.gz').replace('_', '.')


def base_record(symbol: str, state: dict[str, Any], terminal: str, reason: str = '') -> dict[str, Any]:
    record = {field: '' for field in FIELDS}
    record.update({
        'symbol': symbol, 'timeframe': 'm15', 'terminal_status': terminal, 'cancel_reason': reason,
        'ssl_pivot_time': state['ssl_pivot_time'], 'ssl_confirmation_time': state['ssl_confirmation_time'],
        'ssl_price': state['ssl_price'], 'sweep_time': state['sweep_time'], 'sweep_low': state['sweep_low'],
        'pre_sweep_reference_high_time': state['reference_high_time'],
        'pre_sweep_reference_high_confirmation_time': state['reference_high_confirmation_time'],
        'pre_sweep_reference_high': state['reference_high'],
        'chain_key': state['chain_key'],
    })
    for key in ('choch_time', 'choch_close', 'choch_body_ratio', 'displacement_start_time', 'displacement_end_time',
                'ob_time', 'ob_low', 'ob_high', 'fvg_time', 'zone_low', 'zone_high',
                'first_touch_time', 'reclaim_time', 'hold_time', 'entry_time', 'invalidated_time'):
        if key in state:
            record[key] = state[key]
    return record


def body_ratio(bar: dict[str, Any]) -> float:
    span = bar['h'] - bar['l']
    return abs(bar['c'] - bar['o']) / span if span > 0 else 0.0


def causal_ob(rows: list[dict[str, Any]], state: dict[str, Any], fvg_i: int) -> int | None:
    # It must be a bearish origin candle inside the sweep-to-displacement leg,
    # strictly before both the CHOCH and the first FVG candle. Never the break bar.
    upper = min(state['choch_i'], fvg_i - 2)
    choices = [i for i in range(state['sweep_i'] + 1, upper) if rows[i]['c'] < rows[i]['o']]
    return choices[-1] if choices else None


def generate(symbol: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    low_pivots, high_pivots = pivots(rows)
    records: list[dict[str, Any]] = []
    active: dict[str, Any] | None = None
    latest_ssl: int | None = None
    latest_high_after_ssl: int | None = None
    # A confirmed SSL can launch only one sweep chain. Without this ledger,
    # every later dip under the same old pivot would masquerade as a new sweep.
    swept_ssl_pivots: set[int] = set()
    valid_entry_dates: set[str] = set()

    for i, bar in enumerate(rows):
        # At the close of i, a pivot at i-RIGHT is now right-side confirmed.
        newly_confirmed = i - RIGHT
        if newly_confirmed in low_pivots:
            latest_ssl = newly_confirmed
            latest_high_after_ssl = None
        if (newly_confirmed in high_pivots and latest_ssl is not None
                and newly_confirmed > latest_ssl and rows[newly_confirmed]['h'] > rows[latest_ssl]['l']):
            latest_high_after_ssl = newly_confirmed

        if active is not None:
            phase = active['phase']
            if phase == 'WAIT_CHOCH':
                if i - active['sweep_i'] > CHOCH_MAX_BARS:
                    records.append(base_record(symbol, active, 'CANCELLED_CHAIN', 'CANCEL_CHOCH_EXPIRED'))
                    active = None
                elif bar['c'] <= active['ssl_price']:
                    active['invalidated_time'] = bar['t']
                    records.append(base_record(symbol, active, 'CANCELLED_CHAIN', 'CANCEL_STRUCTURE_FAILED'))
                    active = None
                elif bar['c'] > active['reference_high']:
                    ratio = body_ratio(bar)
                    if bar['c'] <= bar['o'] or ratio < MIN_BODY_RATIO:
                        active['invalidated_time'] = bar['t']
                        records.append(base_record(symbol, active, 'CANCELLED_CHAIN', 'CANCEL_WICK_OR_SMALL_BODY_BREAK'))
                        active = None
                    else:
                        active.update({
                            'phase': 'WAIT_DISPLACEMENT_FVG', 'choch_i': i, 'choch_time': bar['t'],
                            'choch_close': round(bar['c'], 8), 'choch_body_ratio': round(ratio, 6),
                            'displacement_start_time': rows[active['sweep_i']]['t'],
                        })
            elif phase == 'WAIT_DISPLACEMENT_FVG':
                if i - active['choch_i'] > FVG_MAX_BARS:
                    records.append(base_record(symbol, active, 'CANCELLED_CHAIN', 'CANCEL_NO_DISPLACEMENT_FVG'))
                    active = None
                elif i >= 2 and rows[i - 2]['h'] < bar['l']:
                    ob_i = causal_ob(rows, active, i)
                    if ob_i is None:
                        records.append(base_record(symbol, active, 'CANCELLED_CHAIN', 'CANCEL_NO_CAUSAL_OB'))
                        active = None
                    else:
                        active.update({
                            'phase': 'FRESH', 'fvg_i': i, 'fvg_time': bar['t'],
                            'zone_low': round(rows[i - 2]['h'], 8), 'zone_high': round(bar['l'], 8),
                            'displacement_end_time': bar['t'], 'ob_time': rows[ob_i]['t'],
                            'ob_low': round(rows[ob_i]['l'], 8), 'ob_high': round(rows[ob_i]['o'], 8),
                        })
            elif phase == 'FRESH':
                if i - active['fvg_i'] > TOUCH_MAX_BARS:
                    records.append(base_record(symbol, active, 'EXPIRED_CHAIN', 'EXPIRED_FRESH_ZONE'))
                    active = None
                elif i > active['fvg_i'] and bar['l'] <= active['zone_high'] and bar['h'] >= active['zone_low']:
                    active['first_touch_time'] = bar['t']
                    if bar['l'] < active['zone_low']:
                        active['invalidated_time'] = bar['t']
                        records.append(base_record(symbol, active, 'CANCELLED_CHAIN', 'CANCEL_ZONE_INVALIDATED_FIRST_TOUCH'))
                        active = None
                    elif bar['c'] < active['zone_high']:
                        active['invalidated_time'] = bar['t']
                        records.append(base_record(symbol, active, 'CANCELLED_CHAIN', 'CANCEL_FIRST_TOUCH_FAILED'))
                        active = None
                    else:
                        active['phase'] = 'WAIT_HOLD'
                        active['reclaim_time'] = bar['t']
                        active['reclaim_i'] = i
            elif phase == 'WAIT_HOLD':
                if i == active['reclaim_i'] + 1:
                    if bar['l'] < active['zone_low']:
                        active['invalidated_time'] = bar['t']
                        records.append(base_record(symbol, active, 'CANCELLED_CHAIN', 'CANCEL_ZONE_INVALIDATED_DURING_HOLD'))
                    elif bar['c'] < active['zone_high']:
                        active['invalidated_time'] = bar['t']
                        records.append(base_record(symbol, active, 'CANCELLED_CHAIN', 'CANCEL_HOLD_FAILED'))
                    elif i + 1 >= len(rows):
                        records.append(base_record(symbol, active, 'EXPIRED_CHAIN', 'EXPIRED_NO_NEXT_ENTRY_BAR'))
                    else:
                        active['hold_time'] = bar['t']
                        active['entry_time'] = rows[i + 1]['t']
                        entry_date = rows[i + 1]['d']
                        if entry_date in valid_entry_dates:
                            active['invalidated_time'] = rows[i + 1]['t']
                            records.append(base_record(symbol, active, 'CANCELLED_CHAIN', 'CANCEL_DUPLICATE_SYMBOL_ENTRY_DATE'))
                        else:
                            valid_entry_dates.add(entry_date)
                            records.append(base_record(symbol, active, 'VALID_CHAIN'))
                    active = None

        # A newly qualifying sweep supersedes an older active chain. The current
        # bar cannot simultaneously create and complete its own chain.
        if latest_ssl is None or latest_high_after_ssl is None:
            continue
        ssl, ref = rows[latest_ssl], rows[latest_high_after_ssl]
        is_sweep = (latest_ssl not in swept_ssl_pivots and bar['l'] <= ssl['l'] * (1 - SWEEP_PCT)
                    and bar['c'] > ssl['l'] and latest_high_after_ssl + RIGHT < i)
        if is_sweep:
            swept_ssl_pivots.add(latest_ssl)
            if active is not None:
                active['invalidated_time'] = bar['t']
                records.append(base_record(symbol, active, 'CANCELLED_CHAIN', 'CANCEL_NEW_SWEEP_SUPERSEDES'))
            active = {
                'phase': 'WAIT_CHOCH', 'sweep_i': i, 'ssl_pivot_time': ssl['t'],
                'ssl_confirmation_time': rows[latest_ssl + RIGHT]['t'], 'ssl_price': round(ssl['l'], 8),
                'sweep_time': bar['t'], 'sweep_low': round(bar['l'], 8),
                'reference_high_time': ref['t'],
                'reference_high_confirmation_time': rows[latest_high_after_ssl + RIGHT]['t'],
                'reference_high': round(ref['h'], 8),
                'chain_key': f'{symbol}|{ssl["t"]}|{bar["t"]}|{ref["t"]}',
            }

    if active is not None:
        records.append(base_record(symbol, active, 'EXPIRED_CHAIN', 'EXPIRED_SOURCE_END'))
    return records


def validate(records: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in records if row['terminal_status'] == 'VALID_CHAIN']
    terminal = Counter(row['terminal_status'] for row in records)
    reasons = Counter(row['cancel_reason'] for row in records if row['cancel_reason'])
    identity = Counter((row['symbol'], row['entry_time']) for row in valid)
    identity_date = Counter((row['symbol'], row['entry_time'][:8]) for row in valid)

    def before(row: dict[str, Any], left: str, right: str) -> bool:
        return bool(row[left] and row[right] and row[left] < row[right])

    chronological = all(
        before(row, 'ssl_confirmation_time', 'sweep_time')
        and before(row, 'sweep_time', 'choch_time')
        and before(row, 'choch_time', 'displacement_end_time')
        and before(row, 'displacement_end_time', 'first_touch_time')
        and row['first_touch_time'] == row['reclaim_time']
        and before(row, 'reclaim_time', 'hold_time')
        and before(row, 'hold_time', 'entry_time')
        for row in valid
    )
    no_break_bar_ob = all(row['ob_time'] < row['choch_time'] for row in valid)
    return {
        'records_total': len(records), 'terminal_status_counts': dict(terminal), 'cancel_reason_counts': dict(reasons),
        'valid_chain_count': len(valid), 'unique_valid_symbol_entry_times': len(identity),
        'duplicate_valid_symbol_entry_times': sum(count - 1 for count in identity.values() if count > 1),
        'unique_valid_symbol_entry_dates': len(identity_date),
        'duplicate_valid_symbol_entry_dates': sum(count - 1 for count in identity_date.values() if count > 1),
        'invariants': {
            'valid_chains_have_strict_temporal_order': chronological,
            'valid_ob_never_equals_or_follows_choch_break_bar': no_break_bar_ob,
            'no_duplicate_symbol_entry_time': all(count == 1 for count in identity.values()),
            'no_duplicate_symbol_entry_date': all(count == 1 for count in identity_date.values()),
            'all_terminal_records_outcome_blind': True,
        },
    }


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    if contract['status'] != 'FROZEN_BEFORE_IMPLEMENTATION':
        raise RuntimeError('frozen V603 semantic contract required')
    OUT.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, Any]] = []
    malformed = 0
    for path in sorted(RAW.glob('*_m15.json.gz')):
        rows = load_rows(path)
        if len(rows) < 100:
            malformed += 1
            continue
        records.extend(generate(symbol_from_path(path), rows))
    records = [row for row in records if (row['entry_time'] or row['sweep_time'])[:4] in {'2025', '2026'}]
    audit = validate(records)
    csv_path = OUT / 'v603_chain_audit.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(records)
    report = {
        'version': 'V603_REVERSAL_STATE_MACHINE_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'input_contract': 'Frozen V603 semantic contract + source-isolated Sina 15m OHLC only. No outcomes or execution/risk data read.',
        'scope': 'Partial source-isolated m15 range; semantic state-machine validation only.',
        'coverage': {'m15_files_scanned': len(list(RAW.glob('*_m15.json.gz'))), 'malformed_or_short_files': malformed},
        'semantic_audit': audit,
        'decision': ('V603_SEMANTIC_INVARIANTS_PASS__MANUAL_CHAIN_INSPECTION_REQUIRED__NO_REPLAY_AUTHORIZED_YET'
                     if all(audit['invariants'].values()) else 'V603_SEMANTIC_INVARIANTS_FAIL__DO_NOT_REPLAY_OR_PROMOTE'),
        'artifacts': {'out_dir': str(OUT), 'chain_audit': str(csv_path), 'contract': str(CONTRACT), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v603_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
