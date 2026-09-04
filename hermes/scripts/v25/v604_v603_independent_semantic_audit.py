#!/usr/bin/env python3
"""V604 independent no-outcome audit and inspectable chain samples for V603."""
from __future__ import annotations

import csv
import gzip
import json
from concurrent.futures import ProcessPoolExecutor
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/m15'
V603 = AUDIT / 'v603_reversal_state_machine_latest.json'
LATEST = AUDIT / 'v604_v603_independent_semantic_audit_latest.json'
OUT = AUDIT / f'v604_v603_independent_semantic_audit_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'


def load_bars(symbol: str) -> list[dict]:
    path = RAW / f'{symbol.replace(".", "_")}_m15.json.gz'
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return []
    output = []
    for row in raw if isinstance(raw, list) else []:
        try:
            t = str(row['t'])
            output.append({'t': t, 'd': str(row.get('d') or t[:8])[:8], 'o': float(row['o']), 'h': float(row['h']), 'l': float(row['l']), 'c': float(row['c'])})
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(output, key=lambda item: item['t'])


def first_intersection(bars: list[dict], start: int, end: int, low: float, high: float) -> int | None:
    for i in range(start, min(end + 1, len(bars))):
        if bars[i]['l'] <= high and bars[i]['h'] >= low:
            return i
    return None


def pick_samples(rows: list[dict], count: int = 5) -> list[dict]:
    selected, symbols = [], set()
    for row in sorted(rows, key=lambda item: (item['symbol'], item['sweep_time'], item['chain_key'])):
        if row['symbol'] in symbols:
            continue
        selected.append(row); symbols.add(row['symbol'])
        if len(selected) == count:
            break
    return selected


def window(row: dict, bars: list[dict]) -> dict:
    ix = {bar['t']: i for i, bar in enumerate(bars)}
    points = [row[key] for key in ('ssl_pivot_time', 'sweep_time', 'choch_time', 'ob_time', 'fvg_time', 'first_touch_time', 'reclaim_time', 'hold_time', 'entry_time', 'invalidated_time') if row.get(key)]
    indices = [ix[t] for t in points if t in ix]
    lo, hi = max(0, min(indices, default=0) - 5), min(len(bars), max(indices, default=0) + 2)
    return {
        'chain': {key: row.get(key, '') for key in row},
        'bars': bars[lo:hi],
        'window_start': bars[lo]['t'] if bars[lo:hi] else '',
        'window_end': bars[hi - 1]['t'] if bars[lo:hi] else '',
    }


def audit_symbol(task: tuple[str, list[dict]]) -> tuple[Counter, list[dict]]:
    """Independent per-symbol lifecycle reconstruction; safe for process pool."""
    symbol, rows = task
    bars = load_bars(symbol)
    ix = {bar['t']: i for i, bar in enumerate(bars)}
    checked, failures = Counter(), []
    for row in rows:
        fvg_i, touch_i = ix.get(row['fvg_time']), ix.get(row['first_touch_time'])
        if fvg_i is None or touch_i is None:
            checked['MISSING_IDENTITY'] += 1
            failures.append({'chain_key': row['chain_key'], 'reason': 'MISSING_IDENTITY'})
            continue
        low, high = float(row['zone_low']), float(row['zone_high'])
        actual = first_intersection(bars, fvg_i + 1, touch_i, low, high)
        checked['FIRST_TOUCH_REBUILT'] += 1
        if actual != touch_i:
            failures.append({'chain_key': row['chain_key'], 'reason': 'FIRST_TOUCH_NOT_RECORDED_FIRST', 'expected': bars[actual]['t'] if actual is not None else '', 'recorded': row['first_touch_time']})
        if row['terminal_status'] == 'VALID_CHAIN':
            checked['VALID_TEMPORAL'] += 1
            order = ['ssl_confirmation_time', 'sweep_time', 'choch_time', 'displacement_end_time', 'first_touch_time', 'hold_time', 'entry_time']
            if not all(row[order[i]] < row[order[i + 1]] for i in range(len(order) - 1)) or row['first_touch_time'] != row['reclaim_time']:
                failures.append({'chain_key': row['chain_key'], 'reason': 'VALID_TEMPORAL_ORDER'})
            if not row['ob_time'] < row['choch_time']:
                failures.append({'chain_key': row['chain_key'], 'reason': 'OB_IS_BREAK_OR_LATER'})
        elif row['cancel_reason'] == 'CANCEL_ZONE_INVALIDATED':
            invalid_i = ix.get(row['invalidated_time'])
            if invalid_i is None or not bars[invalid_i]['l'] < low:
                failures.append({'chain_key': row['chain_key'], 'reason': 'INVALIDATION_RULE_MISMATCH'})
        elif row['cancel_reason'] == 'CANCEL_FIRST_TOUCH_FAILED' and not (bars[touch_i]['l'] >= low and bars[touch_i]['c'] < high):
            failures.append({'chain_key': row['chain_key'], 'reason': 'FIRST_TOUCH_FAILED_RULE_MISMATCH'})
    return checked, failures


def main() -> None:
    report = json.loads(V603.read_text())
    with Path(report['artifacts']['chain_audit']).open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    valid = [row for row in rows if row['terminal_status'] == 'VALID_CHAIN']
    relevant_cancel = [row for row in rows if row['cancel_reason'] in {'CANCEL_FIRST_TOUCH_FAILED', 'CANCEL_ZONE_INVALIDATED_FIRST_TOUCH'}]
    by_symbol: defaultdict[str, list[dict]] = defaultdict(list)
    for row in valid + relevant_cancel:
        by_symbol[row['symbol']].append(row)
    checked, failures = Counter(), []
    # Each worker independently reads only OHLC for one symbol and reconstructs
    # first-touch identity; no worker receives or can read outcome data.
    with ProcessPoolExecutor(max_workers=8) as pool:
        for local_checked, local_failures in pool.map(audit_symbol, sorted(by_symbol.items()), chunksize=16):
            checked.update(local_checked)
            failures.extend(local_failures)
    bars_cache: dict[str, list[dict]] = {}

    identity_time = Counter((row['symbol'], row['entry_time']) for row in valid)
    identity_date = Counter((row['symbol'], row['entry_time'][:8]) for row in valid)
    sample_groups = {
        'VALID_CHAIN': pick_samples(valid),
        'CANCEL_FIRST_TOUCH_FAILED': pick_samples([row for row in rows if row['cancel_reason'] == 'CANCEL_FIRST_TOUCH_FAILED']),
        'CANCEL_ZONE_INVALIDATED': pick_samples([row for row in rows if row['cancel_reason'] == 'CANCEL_ZONE_INVALIDATED_FIRST_TOUCH']),
    }
    samples = {name: [window(row, bars_cache.setdefault(row['symbol'], load_bars(row['symbol']))) for row in group] for name, group in sample_groups.items()}
    OUT.mkdir(parents=True, exist_ok=False)
    samples_path = OUT / 'v604_inspectable_chain_samples.json'
    samples_path.write_text(json.dumps(samples, ensure_ascii=False, indent=2))
    output = {
        'version': 'V604_V603_INDEPENDENT_SEMANTIC_AUDIT_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'input_contract': 'V603 chain CSV + source-isolated Sina m15 OHLC. No PnL, trade, stop, target, exit, or forward-return inputs.',
        'checks': {
            'checked_first_touch_lifecycle_rows': checked['FIRST_TOUCH_REBUILT'],
            'checked_valid_temporal_rows': checked['VALID_TEMPORAL'],
            'valid_chain_count': len(valid),
            'cancel_first_touch_failed_count': sum(row['cancel_reason'] == 'CANCEL_FIRST_TOUCH_FAILED' for row in rows),
            'cancel_zone_invalidated_first_touch_count': sum(row['cancel_reason'] == 'CANCEL_ZONE_INVALIDATED_FIRST_TOUCH' for row in rows),
            'duplicate_valid_symbol_entry_time': sum(n - 1 for n in identity_time.values() if n > 1),
            'duplicate_valid_symbol_entry_date': sum(n - 1 for n in identity_date.values() if n > 1),
            'failure_count': len(failures),
            'failure_samples': failures[:30],
        },
        'invariants': {
            'independent_first_touch_equals_recorded_first_touch': not any(x['reason'] == 'FIRST_TOUCH_NOT_RECORDED_FIRST' for x in failures),
            'valid_temporal_order': not any(x['reason'] == 'VALID_TEMPORAL_ORDER' for x in failures),
            'causal_ob_precedes_choch': not any(x['reason'] == 'OB_IS_BREAK_OR_LATER' for x in failures),
            'cancel_rule_matches_first_touch_bar': not any(x['reason'].endswith('RULE_MISMATCH') for x in failures),
            'no_duplicate_valid_symbol_entry_time': all(n == 1 for n in identity_time.values()),
            'no_duplicate_valid_symbol_entry_date': all(n == 1 for n in identity_date.values()),
            'outcome_blind': True,
        },
        'decision': 'V604_INDEPENDENT_SEMANTIC_AUDIT_PASS__MANUAL_SAMPLE_REVIEW_REQUIRED__NO_REPLAY_AUTHORIZED_YET' if not failures and all(n == 1 for n in identity_time.values()) and all(n == 1 for n in identity_date.values()) else 'V604_SEMANTIC_AUDIT_FAIL__DO_NOT_REPLAY_OR_PROMOTE',
        'artifacts': {'out_dir': str(OUT), 'samples': str(samples_path), 'v603': str(V603), 'latest': str(LATEST)},
    }
    text = json.dumps(output, ensure_ascii=False, indent=2)
    (OUT / 'v604_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
