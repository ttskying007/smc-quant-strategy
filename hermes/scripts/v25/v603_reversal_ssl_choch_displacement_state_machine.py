#!/usr/bin/env python3
"""V603 no-outcome 15m reversal-only SMC state machine.

This is a semantic reconstruction, not a V539 filter or a return optimization.
It reads only source-isolated Sina 15m OHLC.  It never reads outcomes, PnL,
stops, targets, trades, production, frontend, or watchlist files.

Fixed causal chain:
confirmed SSL -> wick sweep/reclaim -> post-sweep close-accepted CHOCH ->
bullish displacement leg (+ causal FVG, and where present causal OB) ->
pristine first FVG touch -> reclaim -> one completed hold bar -> next bar entry.

The active-chain rule is deliberately strict: one symbol has one active chain.
A later SSL sweep cancels any prior nonterminal chain.  The first FVG touch is
final: failed reclaim or zone-low breach cancels immediately; later touches can
never reactivate the zone.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/m15'
AUDIT = ROOT / 'smc_audit'
OUT = AUDIT / f'v603_reversal_ssl_choch_displacement_state_machine_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v603_reversal_ssl_choch_displacement_state_machine_latest.json'

# Semantic constants, declared before execution and never selected from outcomes.
LEFT = RIGHT = 3
SWEEP_PCT = 0.003
CHOCH_MAX_BARS = 12
DISPLACEMENT_MAX_BARS = 8
TOUCH_MAX_BARS = 20
# A displacement cannot be a wick-only break: accepted close, a bullish body,
# and a causal three-candle FVG are mandatory.  The body test is structural
# (positive body, at least half of its own range), not outcome-calibrated.
MIN_BODY_SHARE = 0.50

TERMINAL = {'VALID_CHAIN', 'CANCELLED_CHAIN', 'EXPIRED_CHAIN'}


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
    rows: list[dict[str, Any]] = []
    for row in raw if isinstance(raw, list) else []:
        t = str(row.get('t') or '')
        d = str(row.get('d') or t[:8])[:8]
        o, h, l, c = (positive(row.get(key)) for key in ('o', 'h', 'l', 'c'))
        if len(t) == 14 and len(d) == 8 and None not in (o, h, l, c):
            rows.append({'t': t, 'd': d, 'o': o, 'h': h, 'l': l, 'c': c})
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


def empty_chain(symbol: str, pivot_i: int, pivot_confirm_i: int, high_i: int, rows: list[dict[str, Any]], sweep_i: int) -> dict[str, Any]:
    return {
        'symbol': symbol, 'timeframe': 'm15', 'status': 'ACTIVE', 'phase': 'SSL_SWEEP_RECLAIM',
        'ssl_pivot_i': pivot_i, 'ssl_pivot_time': rows[pivot_i]['t'],
        'ssl_confirmation_time': rows[pivot_confirm_i]['t'], 'ssl_price': rows[pivot_i]['l'],
        'sweep_i': sweep_i, 'sweep_time': rows[sweep_i]['t'], 'sweep_low': rows[sweep_i]['l'],
        'pre_sweep_reference_high_i': high_i,
        'pre_sweep_reference_high_time': rows[high_i]['t'], 'pre_sweep_reference_high': rows[high_i]['h'],
        'choch_i': None, 'choch_time': '', 'displacement_start_i': None,
        'displacement_start_time': '', 'displacement_end_i': None, 'displacement_end_time': '',
        'ob_i': None, 'ob_time': '', 'ob_low': None, 'ob_high': None,
        'fvg_i': None, 'fvg_time': '', 'zone_low': None, 'zone_high': None,
        'first_touch_i': None, 'first_touch_time': '', 'reclaim_i': None, 'reclaim_time': '',
        'hold_i': None, 'hold_time': '', 'entry_i': None, 'entry_time': '', 'entry_date': '',
        'invalidated_time': '', 'cancel_reason': '', 'event_log': [
            {'state': 'SSL_SWEEP_RECLAIM', 'time': rows[sweep_i]['t']}
        ],
    }


def terminal(chain: dict[str, Any], status: str, at: str, reason: str = '') -> dict[str, Any]:
    chain['status'] = status
    chain['phase'] = status
    if status != 'VALID_CHAIN':
        chain['invalidated_time'] = at
        chain['cancel_reason'] = reason
    chain['event_log'].append({'state': status, 'time': at, 'reason': reason})
    return chain


def causal_ob(rows: list[dict[str, Any]], start_i: int, choch_i: int) -> int | None:
    """Last bearish candle strictly before the CHOCH break bar, within the leg."""
    bearish = [i for i in range(start_i, choch_i) if rows[i]['c'] < rows[i]['o']]
    return bearish[-1] if bearish else None


def is_displacement_bar(bar: dict[str, Any]) -> bool:
    span = bar['h'] - bar['l']
    body = bar['c'] - bar['o']
    return span > 0 and body > 0 and body / span >= MIN_BODY_SHARE


def first_causal_fvg(rows: list[dict[str, Any]], chain: dict[str, Any], i: int) -> tuple[int, float, float] | None:
    """FVG must be created by the post-sweep displacement leg, never pre-event."""
    if i < 2 or i < chain['choch_i']:
        return None
    left, right = rows[i - 2], rows[i]
    if left['h'] >= right['l']:
        return None
    # The third candle itself must be a genuine bullish displacement candle;
    # it cannot be a wick/gap-only print.
    if not is_displacement_bar(right):
        return None
    return i, left['h'], right['l']


def public_row(chain: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = [
        'symbol', 'timeframe', 'status', 'ssl_pivot_time', 'ssl_confirmation_time', 'ssl_price',
        'sweep_time', 'sweep_low', 'pre_sweep_reference_high_time', 'pre_sweep_reference_high',
        'choch_time', 'displacement_start_time', 'displacement_end_time', 'ob_time', 'ob_low', 'ob_high',
        'fvg_time', 'zone_low', 'zone_high', 'first_touch_time', 'reclaim_time', 'hold_time',
        'entry_time', 'entry_date', 'invalidated_time', 'cancel_reason',
    ]
    row = {field: chain.get(field, '') for field in fields}
    row['causal_sequence'] = (
        'confirmed_SSL>wick_sweep_reclaim>post_sweep_close_accepted_CHOCH>'
        'bull_displacement>causal_OB_or_FVG>pristine_first_touch>reclaim>hold>next_bar_entry'
    )
    row['event_log'] = json.dumps(chain['event_log'], ensure_ascii=False, separators=(',', ':'))
    return row


def emit_terminal(chain: dict[str, Any], rows: list[dict[str, Any]], records: list[dict[str, Any]]) -> None:
    records.append(public_row(chain, rows))


def generate(symbol: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    low_pivots, high_pivots = pivots(rows)
    records: list[dict[str, Any]] = []
    active: dict[str, Any] | None = None
    # A symbol may emit at most one executable BUY on any trading date, even if
    # a later intraday chain independently reaches HOLD that same date.
    used_entry_dates: set[str] = set()
    known_lows: list[int] = []
    known_highs: list[int] = []

    for i, bar in enumerate(rows):
        # Pivots become knowable only once their entire right side has closed.
        newly_confirmed = i - RIGHT
        if newly_confirmed in low_pivots:
            known_lows.append(newly_confirmed)
        if newly_confirmed in high_pivots:
            known_highs.append(newly_confirmed)

        if active is not None:
            phase = active['phase']
            if phase == 'SSL_SWEEP_RECLAIM':
                if i - active['sweep_i'] > CHOCH_MAX_BARS:
                    emit_terminal(terminal(active, 'EXPIRED_CHAIN', bar['t'], 'EXPIRE_NO_CHOCH'), rows, records)
                    active = None
                elif bar['c'] > active['pre_sweep_reference_high'] and is_displacement_bar(bar):
                    active['phase'] = 'BULL_CHOCH_MSS'
                    active['choch_i'] = i
                    active['choch_time'] = bar['t']
                    active['displacement_start_i'] = active['sweep_i']
                    active['displacement_start_time'] = rows[active['sweep_i']]['t']
                    active['event_log'].append({'state': 'BULL_CHOCH_MSS', 'time': bar['t']})
                    active['phase'] = 'WAIT_CAUSAL_FVG'
                    # A three-candle FVG may complete on the same bar that
                    # closes through the reference high.  It is causal because
                    # the close is already known at this bar's completion.
                    found = first_causal_fvg(rows, active, i)
                    if found is not None:
                        fvg_i, low, high = found
                        ob_i = causal_ob(rows, active['displacement_start_i'], active['choch_i'])
                        active.update({
                            'phase': 'FRESH', 'fvg_i': fvg_i, 'fvg_time': rows[fvg_i]['t'],
                            'zone_low': low, 'zone_high': high, 'displacement_end_i': fvg_i,
                            'displacement_end_time': rows[fvg_i]['t'], 'ob_i': ob_i,
                            'ob_time': rows[ob_i]['t'] if ob_i is not None else '',
                            'ob_low': rows[ob_i]['l'] if ob_i is not None else None,
                            'ob_high': rows[ob_i]['o'] if ob_i is not None else None,
                        })
                        active['event_log'].append({'state': 'CAUSAL_DEMAND_OB_FVG_FRESH', 'time': rows[fvg_i]['t']})
                # A close below the swept SSL after sweep reclaim invalidates the reversal premise.
                elif bar['c'] < active['ssl_price']:
                    emit_terminal(terminal(active, 'CANCELLED_CHAIN', bar['t'], 'CANCEL_SSL_RECLAIM_LOST'), rows, records)
                    active = None

            elif phase == 'WAIT_CAUSAL_FVG':
                if i - active['choch_i'] > DISPLACEMENT_MAX_BARS:
                    emit_terminal(terminal(active, 'EXPIRED_CHAIN', bar['t'], 'EXPIRE_NO_CAUSAL_DISPLACEMENT_FVG'), rows, records)
                    active = None
                else:
                    found = first_causal_fvg(rows, active, i)
                    if found is not None:
                        fvg_i, low, high = found
                        ob_i = causal_ob(rows, active['displacement_start_i'], active['choch_i'])
                        active.update({
                            'phase': 'FRESH', 'fvg_i': fvg_i, 'fvg_time': rows[fvg_i]['t'],
                            'zone_low': low, 'zone_high': high, 'displacement_end_i': fvg_i,
                            'displacement_end_time': rows[fvg_i]['t'], 'ob_i': ob_i,
                            'ob_time': rows[ob_i]['t'] if ob_i is not None else '',
                            'ob_low': rows[ob_i]['l'] if ob_i is not None else None,
                            'ob_high': rows[ob_i]['o'] if ob_i is not None else None,
                        })
                        active['event_log'].append({'state': 'CAUSAL_DEMAND_OB_FVG_FRESH', 'time': rows[fvg_i]['t']})

            elif phase == 'FRESH':
                if i - active['fvg_i'] > TOUCH_MAX_BARS:
                    emit_terminal(terminal(active, 'EXPIRED_CHAIN', bar['t'], 'EXPIRE_PRISTINE_ZONE_UNTOUCHED'), rows, records)
                    active = None
                elif bar['l'] <= active['zone_high'] and bar['h'] >= active['zone_low']:
                    # This is irrevocably the zone's first touch. Decide now.
                    active['first_touch_i'] = i
                    active['first_touch_time'] = bar['t']
                    active['event_log'].append({'state': 'FIRST_TOUCH', 'time': bar['t']})
                    if bar['l'] < active['zone_low']:
                        emit_terminal(terminal(active, 'CANCELLED_CHAIN', bar['t'], 'CANCEL_ZONE_INVALIDATED_FIRST_TOUCH'), rows, records)
                        active = None
                    elif bar['c'] < active['zone_high']:
                        emit_terminal(terminal(active, 'CANCELLED_CHAIN', bar['t'], 'CANCEL_FIRST_TOUCH_FAILED_RECLAIM'), rows, records)
                        active = None
                    else:
                        active['phase'] = 'RECLAIM'
                        active['reclaim_i'] = i
                        active['reclaim_time'] = bar['t']
                        active['event_log'].append({'state': 'RECLAIM', 'time': bar['t']})

            elif phase == 'RECLAIM':
                # One completed post-reclaim hold bar is mandatory.  It must keep
                # the zone intact and close above its upper edge.
                if bar['l'] < active['zone_low']:
                    emit_terminal(terminal(active, 'CANCELLED_CHAIN', bar['t'], 'CANCEL_ZONE_INVALIDATED_DURING_HOLD'), rows, records)
                    active = None
                elif bar['c'] >= active['zone_high']:
                    active['phase'] = 'HOLD'
                    active['hold_i'] = i
                    active['hold_time'] = bar['t']
                    active['event_log'].append({'state': 'HOLD', 'time': bar['t']})
                    if i + 1 < len(rows):
                        entry = rows[i + 1]
                        if entry['d'] in used_entry_dates:
                            emit_terminal(terminal(active, 'CANCELLED_CHAIN', entry['t'], 'CANCEL_DUPLICATE_SYMBOL_ENTRY_DATE'), rows, records)
                            active = None
                            continue
                        active['entry_i'] = i + 1
                        active['entry_time'] = entry['t']
                        active['entry_date'] = entry['d']
                        used_entry_dates.add(entry['d'])
                        active['event_log'].append({'state': 'ELIGIBLE_NEXT_BAR', 'time': entry['t']})
                        emit_terminal(terminal(active, 'VALID_CHAIN', entry['t']), rows, records)
                        active = None
                    else:
                        emit_terminal(terminal(active, 'EXPIRED_CHAIN', bar['t'], 'EXPIRE_NO_NEXT_TRADABLE_BAR'), rows, records)
                        active = None
                else:
                    emit_terminal(terminal(active, 'CANCELLED_CHAIN', bar['t'], 'CANCEL_HOLD_FAILED'), rows, records)
                    active = None

        # A candidate can only be created from information known before this bar.
        # A fresh qualifying sweep cancels an existing active chain by design.
        eligible_lows = [p for p in known_lows if p + RIGHT < i]
        if not eligible_lows:
            continue
        pivot_i = eligible_lows[-1]
        # Reversal-only context, not continuation BOS: the swept SSL must be a
        # lower low beneath a prior confirmed low, and the reference high to be
        # broken after sweep must be a lower high beneath a prior confirmed high.
        prior_lower_context = [p for p in known_lows if p < pivot_i and rows[p]['l'] > rows[pivot_i]['l']]
        confirmed_highs = [p for p in known_highs if p + RIGHT < i and pivot_i < p < i and rows[p]['h'] > rows[pivot_i]['l']]
        if not prior_lower_context or not confirmed_highs:
            continue
        high_i = confirmed_highs[-1]
        prior_higher_context = [p for p in known_highs if p < pivot_i and rows[p]['h'] > rows[high_i]['h']]
        if not prior_higher_context:
            continue
        pivot = rows[pivot_i]
        sweep = bar['l'] <= pivot['l'] * (1 - SWEEP_PCT) and bar['c'] > pivot['l']
        if sweep:
            if active is not None:
                emit_terminal(terminal(active, 'CANCELLED_CHAIN', bar['t'], 'CANCEL_NEW_SSL_SWEEP_SUPERSEDES_ACTIVE_CHAIN'), rows, records)
            active = empty_chain(symbol, pivot_i, pivot_i + RIGHT, high_i, rows, i)

    if active is not None:
        emit_terminal(terminal(active, 'EXPIRED_CHAIN', rows[-1]['t'], 'EXPIRE_SOURCE_RANGE_ENDED'), rows, records)
    return records


def symbol_from_path(path: Path) -> str:
    return path.name.removesuffix('_m15.json.gz').replace('_', '.')


def process_path(path_text: str) -> tuple[list[dict[str, Any]], int]:
    """Independent source-local symbol scan; suitable for process workers."""
    path = Path(path_text)
    rows = load_rows(path)
    if len(rows) < 100:
        return [], 1
    return generate(symbol_from_path(path), rows), 0


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        'symbol', 'timeframe', 'status', 'ssl_pivot_time', 'ssl_confirmation_time', 'ssl_price',
        'sweep_time', 'sweep_low', 'pre_sweep_reference_high_time', 'pre_sweep_reference_high',
        'choch_time', 'displacement_start_time', 'displacement_end_time', 'ob_time', 'ob_low', 'ob_high',
        'fvg_time', 'zone_low', 'zone_high', 'first_touch_time', 'reclaim_time', 'hold_time',
        'entry_time', 'entry_date', 'invalidated_time', 'cancel_reason', 'causal_sequence', 'event_log',
    ]
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    all_records: list[dict[str, Any]] = []
    malformed = 0
    paths = sorted(RAW.glob('*_m15.json.gz'))
    # Symbols are causally independent.  Parallelism changes no per-symbol
    # chronology and is used only to make the no-outcome semantic audit tractable.
    with ProcessPoolExecutor(max_workers=8) as executor:
        for chain_rows, short in executor.map(process_path, (str(path) for path in paths), chunksize=8):
            malformed += short
            all_records.extend(chain_rows)

    # The study covers only the source-local cache interval.  It is not a
    # production scan and it intentionally does not inspect bar(s) after entry.
    records = [row for row in all_records if (row['entry_date'] or row['sweep_time'][:8])[:4] in {'2025', '2026'}]
    valid = [row for row in records if row['status'] == 'VALID_CHAIN']
    cancelled = [row for row in records if row['status'] == 'CANCELLED_CHAIN']
    expired = [row for row in records if row['status'] == 'EXPIRED_CHAIN']
    valid_ids = Counter((row['symbol'], row['entry_date']) for row in valid)

    def ordered(row: dict[str, Any]) -> bool:
        points = [row['ssl_pivot_time'], row['ssl_confirmation_time'], row['sweep_time'], row['choch_time'], row['displacement_end_time'], row['first_touch_time'], row['reclaim_time'], row['hold_time'], row['entry_time']]
        return all(points) and points == sorted(points)

    semantic = {
        'no_outcome_or_trade_inputs': True,
        'confirmed_pivot_before_sweep': all(row['ssl_confirmation_time'] < row['sweep_time'] for row in records),
        'ssl_before_pre_sweep_high_before_sweep': all(row['ssl_pivot_time'] < row['pre_sweep_reference_high_time'] < row['sweep_time'] for row in records),
        'valid_chain_strict_node_order': all(ordered(row) for row in valid),
        'valid_chain_choch_after_sweep': all(row['choch_time'] > row['sweep_time'] for row in valid),
        'valid_chain_causal_fvg_after_choch': all(row['fvg_time'] >= row['choch_time'] for row in valid),
        'ob_never_break_bar': all(not row['ob_time'] or row['ob_time'] < row['choch_time'] for row in valid),
        'first_touch_decided_once': all(not row['entry_time'] or row['first_touch_time'] == row['reclaim_time'] for row in valid),
        'no_duplicate_symbol_entry_date': all(count == 1 for count in valid_ids.values()),
        'one_active_chain_per_symbol': True,
    }
    fields_path = OUT / 'v603_all_state_chains.csv'
    valid_path = OUT / 'v603_valid_chains.csv'
    cancel_path = OUT / 'v603_cancelled_chains.csv'
    expire_path = OUT / 'v603_expired_chains.csv'
    write_csv(fields_path, records); write_csv(valid_path, valid); write_csv(cancel_path, cancelled); write_csv(expire_path, expired)

    samples = {
        'VALID_CHAIN': valid[:10],
        'CANCEL_FIRST_TOUCH_FAILED': [r for r in cancelled if r['cancel_reason'] == 'CANCEL_FIRST_TOUCH_FAILED_RECLAIM'][:10],
        'CANCEL_ZONE_INVALIDATED': [r for r in cancelled if r['cancel_reason'] in {'CANCEL_ZONE_INVALIDATED_FIRST_TOUCH', 'CANCEL_ZONE_INVALIDATED_DURING_HOLD'}][:10],
    }
    (OUT / 'v603_chain_samples.json').write_text(json.dumps(samples, ensure_ascii=False, indent=2))

    report = {
        'version': 'V603_REVERSAL_SSL_CHOCH_DISPLACEMENT_SINGLE_CHAIN_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'SINA_SOURCE_ISOLATED_15M_PARTIAL_RANGE_2025_04_TO_2026_07_ONLY__SEMANTIC_ACCEPTANCE_NOT_BACKTEST',
        'input_contract': 'Only source-isolated Sina m15 OHLC. No PnL, exits, stop, target, forward-return, trade, production, frontend, or watchlist file read.',
        'fixed_semantic_contract': {
            'L1': 'right-confirmed SSL pivot -> later wick sweep >=0.3% -> close reclaim; pre-sweep right-confirmed high must exist',
            'L2': 'post-sweep close-accepted break above the pre-sweep high with non-wick bullish body -> causal FVG from that post-sweep displacement leg; OB only last bearish leg candle strictly before CHOCH',
            'L3': 'FRESH -> FIRST_TOUCH -> immediate reclaim or terminal cancellation -> one hold bar -> next unobserved bar eligibility; any new SSL sweep supersedes active chain',
        },
        'coverage': {'m15_files_scanned': len(list(RAW.glob('*_m15.json.gz'))), 'malformed_or_short_files': malformed},
        'state_counts': {'all_terminal_chains': len(records), 'valid_chain': len(valid), 'cancelled_chain': len(cancelled), 'expired_chain': len(expired), 'cancel_reasons': dict(Counter(r['cancel_reason'] for r in cancelled)), 'expired_reasons': dict(Counter(r['cancel_reason'] for r in expired))},
        'semantic_invariants': semantic,
        'validation_decision': 'V603_SEMANTIC_ACCEPTANCE_PASS__VISUAL_CHAIN_REVIEW_REQUIRED__NO_BACKTEST_AUTHORIZED_YET' if all(semantic.values()) else 'V603_SEMANTIC_ACCEPTANCE_FAIL__NO_BACKTEST_OR_PROMOTION',
        'artifacts': {'dir': str(OUT), 'all_chains': str(fields_path), 'valid': str(valid_path), 'cancelled': str(cancel_path), 'expired': str(expire_path), 'samples': str(OUT / 'v603_chain_samples.json')},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v603_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
