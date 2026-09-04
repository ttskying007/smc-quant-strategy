#!/usr/bin/env python3
"""Execute the single V606 frozen replay of V603 VALID_CHAIN records.

No candidate selector, timing, stop, target, or holding variant is implemented.
The script writes research-only artifacts and does not touch production surfaces.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/m15'
PREREG = AUDIT / 'v606_v603_strict_t1_replay_preregistration.json'
CLARIFICATION = AUDIT / 'v621_v606_execution_contract_clarification.json'
OUT = AUDIT / f'v624_v606_contract_complete_strict_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v624_v606_contract_complete_strict_t1_replay_latest.json'
LEFT = RIGHT = 3


def positive(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except (TypeError, ValueError):
        return None


def load(symbol):
    path = RAW / f'{symbol.replace(".", "_")}_m15.json.gz'
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        raw = json.load(handle)
    rows = []
    for row in raw:
        o, h, l, c = (positive(row.get(key)) for key in ('o', 'h', 'l', 'c'))
        t = str(row.get('t') or '')
        if len(t) == 14 and None not in (o, h, l, c):
            rows.append({'t': t, 'd': t[:8], 'o': o, 'h': h, 'l': l, 'c': c})
    return sorted(rows, key=lambda row: row['t'])


def confirmed_highs_before(rows, end_i):
    """Return only 3L/3R highs fully confirmed before the entry bar."""
    found = []
    for i in range(LEFT, end_i - RIGHT):
        before = rows[i - LEFT:i]
        after = rows[i + 1:i + RIGHT + 1]
        if rows[i]['h'] > max(x['h'] for x in before) and rows[i]['h'] >= max(x['h'] for x in after):
            found.append(i)
    return found


def structural_target(rows, entry_i, entry_open):
    choices = []
    for pivot_i in confirmed_highs_before(rows, entry_i):
        price = rows[pivot_i]['h']
        if price <= entry_open:
            continue
        if any(bar['h'] >= price for bar in rows[pivot_i + RIGHT + 1:entry_i]):
            continue
        choices.append(pivot_i)
    return min(choices, key=lambda i: rows[i]['h']) if choices else None


def replay_seed(seed, rows, fee_pct):
    by_time = {row['t']: i for i, row in enumerate(rows)}
    entry_i = by_time.get(seed['entry_time'])
    if entry_i is None or entry_i == 0:
        return None, 'EXCLUDED_MISSING_ENTRY_BAR'
    entry = rows[entry_i]
    ob_i = by_time.get(seed['ob_time'])
    if ob_i is None:
        return None, 'EXCLUDED_MISSING_CAUSAL_OB_BAR'
    stop_anchor = min(float(seed['sweep_low']), rows[ob_i]['l'])
    if stop_anchor >= entry['o']:
        return None, 'EXCLUDED_NONPOSITIVE_RISK'
    target_i = structural_target(rows, entry_i, entry['o'])
    if target_i is None:
        return None, 'EXCLUDED_NO_PREENTRY_STRUCTURAL_TARGET'
    target = rows[target_i]['h']
    planned_rr = (target - entry['o']) / (entry['o'] - stop_anchor)
    if planned_rr < 1.5:
        return None, 'EXCLUDED_PLANNED_RR_LT_1_5'

    later_dates = sorted({bar['d'] for bar in rows[entry_i + 1:] if bar['d'] > entry['d']})
    time_stop_date = later_dates[19] if len(later_dates) >= 20 else ''
    exit_row = None
    exit_price = None
    reason = 'OPEN_UNOBSERVED'
    for offset, bar in enumerate(rows[entry_i + 1:], start=entry_i + 1):
        if bar['d'] == entry['d']:
            continue
        if bar['o'] <= stop_anchor:
            exit_row, exit_price, reason = bar, bar['o'], 'SL_GAP_T1'
            break
        if bar['o'] >= target:
            exit_row, exit_price, reason = bar, bar['o'], 'TP_GAP_T1'
            break
        hit_stop = bar['l'] <= stop_anchor
        hit_target = bar['h'] >= target
        if hit_stop and hit_target:
            exit_row, exit_price, reason = bar, stop_anchor, 'SL_TP_COLLISION_STOP_FIRST'
            break
        if hit_stop:
            exit_row, exit_price, reason = bar, stop_anchor, 'SL_T1'
            break
        if hit_target:
            exit_row, exit_price, reason = bar, target, 'TP_T1'
            break
        if time_stop_date and bar['d'] == time_stop_date and (offset + 1 == len(rows) or rows[offset + 1]['d'] != time_stop_date):
            exit_row, exit_price, reason = bar, bar['c'], 'TIME20_T1'
            break

    result = {
        'symbol': seed['symbol'], 'entry_time': entry['t'], 'entry_date': entry['d'],
        'entry_price': entry['o'], 'stop_anchor': stop_anchor,
        'target_time': rows[target_i]['t'], 'target_price': target, 'planned_rr': planned_rr,
        'exit_time': '', 'exit_date': '', 'exit_price': '', 'exit_reason': reason,
        'net_pnl_pct': '',
    }
    if exit_row is not None:
        result.update({
            'exit_time': exit_row['t'], 'exit_date': exit_row['d'], 'exit_price': exit_price,
            'net_pnl_pct': (exit_price / entry['o'] - 1) * 100 - fee_pct,
        })
    return result, None


def main():
    prereg = json.loads(PREREG.read_text())
    clarification = json.loads(CLARIFICATION.read_text())
    if prereg['authorization'] != 'STAGE0_STAGE1_STAGE2_PASS__ONE_FROZEN_STRICT_T1_REPLAY_AUTHORIZED':
        raise RuntimeError('V606 replay is not authorized')
    if clarification['authorization'] != 'V606_ONE_FROZEN_REPLAY_MAY_USE_THIS_FIXED_ACCOUNTING_CLARIFICATION_ONLY':
        raise RuntimeError('V606 fee clarification is not authorized')
    fee_pct = float(clarification['clarified_execution_field']['round_trip_fee_pct'])
    source = Path(prereg['source_contract']['semantic_records'])
    all_rows = list(csv.DictReader(source.open(encoding='utf-8')))
    seeds = [row for row in all_rows if row['status'] == 'VALID_CHAIN']
    quality_gate = prereg['quality_gate']
    years = Counter(row['entry_time'][:4] for row in seeds)
    if len(seeds) < quality_gate['minimum_rows'] or min(years.values(), default=0) < quality_gate['minimum_each_available_calendar_year']:
        raise RuntimeError('outcome-blind support gate failed')

    OUT.mkdir(parents=True, exist_ok=False)
    executed, excluded = [], Counter()
    by_symbol = defaultdict(list)
    for seed in seeds:
        by_symbol[seed['symbol']].append(seed)
    for symbol, group in by_symbol.items():
        bars = load(symbol)
        last_exit_time = ''
        for seed in sorted(group, key=lambda row: row['entry_time']):
            if last_exit_time and seed['entry_time'] <= last_exit_time:
                excluded['EXCLUDED_SERIAL_POSITION_OPEN'] += 1
                continue
            trade, reason = replay_seed(seed, bars, fee_pct)
            if reason:
                excluded[reason] += 1
                continue
            executed.append(trade)
            if trade['exit_time']:
                last_exit_time = trade['exit_time']

    closed = [row for row in executed if row['exit_time']]
    pnl = [float(row['net_pnl_pct']) for row in closed]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value <= 0]
    yearly = {}
    for year in sorted({row['entry_date'][:4] for row in closed}):
        values = [float(row['net_pnl_pct']) for row in closed if row['entry_date'].startswith(year)]
        yearly[year] = {
            'n': len(values),
            'wr_pct': 100 * sum(value > 0 for value in values) / len(values),
            'avg_net_pct': sum(values) / len(values),
        }
    t1_violations = sum(bool(row['exit_time']) and row['exit_date'] <= row['entry_date'] for row in executed)
    duplicates = len(executed) - len({(row['symbol'], row['entry_time']) for row in executed})
    fields = list(executed[0]) if executed else ['symbol']
    with (OUT / 'v622_frozen_t1_trades.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(executed)
    report = {
        'version': 'V624_V606_CONTRACT_COMPLETE_STRICT_T1_REPLAY',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'preregistration': str(PREREG), 'clarification': str(CLARIFICATION),
        'seed_count': len(seeds), 'seed_year_counts': dict(years), 'unique_symbols': len(by_symbol),
        'executed_or_open_count': len(executed), 'closed_count': len(closed),
        'open_unobserved_count': len(executed) - len(closed), 'excluded': dict(excluded),
        'metrics': {
            'wr_pct': 100 * len(wins) / len(pnl) if pnl else None,
            'avg_net_pct': sum(pnl) / len(pnl) if pnl else None,
            'profit_factor': sum(wins) / abs(sum(losses)) if losses and sum(losses) else None,
            'payoff': (sum(wins) / len(wins)) / (abs(sum(losses)) / len(losses)) if wins and losses else None,
            'yearly': yearly, 'exit_reasons': dict(Counter(row['exit_reason'] for row in executed)),
        },
        't1_violations': t1_violations,
        'duplicate_symbol_entry_time': duplicates,
        'decision': 'V624_CONTRACT_COMPLETE_FROZEN_REPLAY__INDEPENDENT_AUDIT_REQUIRED__NO_VARIANTS_NO_PRODUCTION',
        'artifacts': {'dir': str(OUT), 'trades': str(OUT / 'v622_frozen_t1_trades.csv')},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v622_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
