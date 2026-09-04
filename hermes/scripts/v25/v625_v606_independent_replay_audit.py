#!/usr/bin/env python3
"""Independent raw-bar and metrics audit for the one V606/V624 replay."""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/m15'
REPLAY = AUDIT / 'v624_v606_contract_complete_strict_t1_replay_latest.json'
SEEDS = AUDIT / 'v603_ssl_choch_displacement_pristine_no_write_20260726_054038/v603_semantic_lifecycle_records.csv'
OUT = AUDIT / 'v625_v606_independent_replay_audit_and_closure.json'
FEE = 0.20
LEFT = RIGHT = 3


def load(symbol):
    with gzip.open(RAW / f'{symbol.replace(".", "_")}_m15.json.gz', 'rt', encoding='utf-8') as handle:
        raw = json.load(handle)
    rows = []
    for row in raw:
        try:
            o, h, l, c = (float(row[key]) for key in ('o', 'h', 'l', 'c'))
            t = str(row['t'])
        except (KeyError, TypeError, ValueError):
            continue
        if len(t) == 14 and all(math.isfinite(value) and value > 0 for value in (o, h, l, c)):
            rows.append({'t': t, 'd': t[:8], 'o': o, 'h': h, 'l': l, 'c': c})
    return sorted(rows, key=lambda row: row['t'])


def target(rows, entry_i, entry_price):
    candidates = []
    for i in range(LEFT, entry_i - RIGHT):
        if not (rows[i]['h'] > max(row['h'] for row in rows[i - LEFT:i]) and rows[i]['h'] >= max(row['h'] for row in rows[i + 1:i + RIGHT + 1])):
            continue
        if rows[i]['h'] <= entry_price:
            continue
        if any(row['h'] >= rows[i]['h'] for row in rows[i + RIGHT + 1:entry_i]):
            continue
        candidates.append(i)
    return min(candidates, key=lambda i: rows[i]['h']) if candidates else None


def expected_exit(rows, entry_i, stop, take):
    entry_date = rows[entry_i]['d']
    later = sorted({row['d'] for row in rows[entry_i + 1:] if row['d'] > entry_date})
    time_date = later[19] if len(later) >= 20 else ''
    for i in range(entry_i + 1, len(rows)):
        row = rows[i]
        if row['d'] == entry_date:
            continue
        if row['o'] <= stop:
            return row, row['o'], 'SL_GAP_T1'
        if row['o'] >= take:
            return row, row['o'], 'TP_GAP_T1'
        if row['l'] <= stop and row['h'] >= take:
            return row, stop, 'SL_TP_COLLISION_STOP_FIRST'
        if row['l'] <= stop:
            return row, stop, 'SL_T1'
        if row['h'] >= take:
            return row, take, 'TP_T1'
        if time_date and row['d'] == time_date and (i + 1 == len(rows) or rows[i + 1]['d'] != time_date):
            return row, row['c'], 'TIME20_T1'
    return None, None, 'OPEN_UNOBSERVED'


def close(audit, reason):
    gate = audit['quality_gate']
    m = audit['recomputed_metrics']
    yearly = m['yearly']
    gate['pass'] = (
        audit['source_and_execution_invariants']['pass']
        and m['closed_count'] >= 1000
        and all(row['n'] >= 300 and row['avg_net_pct'] > 0 for row in yearly.values())
        and m['wr_pct'] >= 55.0 and m['avg_net_pct'] >= 0.5
        and m['profit_factor'] >= 1.15 and m['payoff'] >= 0.7
    )
    audit['decision'] = reason
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2))


def main():
    report = json.loads(REPLAY.read_text())
    trade_path = Path(report['artifacts']['trades'])
    trades = list(csv.DictReader(trade_path.open(encoding='utf-8')))
    seeds = {(row['symbol'], row['entry_time']): row for row in csv.DictReader(SEEDS.open(encoding='utf-8')) if row['status'] == 'VALID_CHAIN'}
    failures = []
    checked_symbols = {}
    for trade in trades:
        key = (trade['symbol'], trade['entry_time'])
        seed = seeds.get(key)
        if seed is None:
            failures.append({'key': key, 'failure': 'MISSING_VALID_SEED'})
            continue
        rows = checked_symbols.setdefault(trade['symbol'], load(trade['symbol']))
        by_time = {row['t']: i for i, row in enumerate(rows)}
        entry_i, ob_i = by_time.get(trade['entry_time']), by_time.get(seed['ob_time'])
        if entry_i is None or ob_i is None:
            failures.append({'key': key, 'failure': 'MISSING_RAW_ANCHOR'})
            continue
        stop = min(float(seed['sweep_low']), rows[ob_i]['l'])
        target_i = target(rows, entry_i, rows[entry_i]['o'])
        if target_i is None:
            failures.append({'key': key, 'failure': 'NO_INDEPENDENT_TARGET'})
            continue
        take = rows[target_i]['h']
        expected_row, expected_price, expected_reason = expected_exit(rows, entry_i, stop, take)
        actual_exit = trade['exit_time']
        if (expected_row['t'] if expected_row else '') != actual_exit or expected_reason != trade['exit_reason']:
            failures.append({'key': key, 'failure': 'EXIT_REPLAY_MISMATCH'})
            continue
        if expected_row is not None:
            expected_net = (expected_price / rows[entry_i]['o'] - 1) * 100 - FEE
            if abs(expected_net - float(trade['net_pnl_pct'])) > 1e-9:
                failures.append({'key': key, 'failure': 'NET_PNL_MISMATCH'})
        if abs(stop - float(trade['stop_anchor'])) > 1e-9 or abs(take - float(trade['target_price'])) > 1e-9:
            failures.append({'key': key, 'failure': 'STRUCTURAL_ANCHOR_MISMATCH'})

    closed = [row for row in trades if row['exit_time']]
    pnl = [float(row['net_pnl_pct']) for row in closed]
    wins, losses = [x for x in pnl if x > 0], [x for x in pnl if x <= 0]
    yearly = {}
    for year in sorted({row['entry_date'][:4] for row in closed}):
        values = [float(row['net_pnl_pct']) for row in closed if row['entry_date'].startswith(year)]
        yearly[year] = {'n': len(values), 'wr_pct': 100 * sum(x > 0 for x in values) / len(values), 'avg_net_pct': sum(values) / len(values)}
    audit = {
        'version': 'V625_V606_INDEPENDENT_REPLAY_AUDIT_AND_CLOSURE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'lineage': {'replay': str(REPLAY), 'trades': str(trade_path), 'semantic_records': str(SEEDS), 'preliminary_quarantine': str(AUDIT / 'v623_v622_preliminary_replay_quarantine.json')},
        'source_and_execution_invariants': {
            'seed_count_matches': len(seeds) == report['seed_count'],
            'executed_or_open_count_matches': len(trades) == report['executed_or_open_count'],
            'strict_t1_violations': sum(bool(row['exit_time']) and row['exit_date'] <= row['entry_date'] for row in trades),
            'duplicate_symbol_entry_time': len(trades) - len({(row['symbol'], row['entry_time']) for row in trades}),
            'independent_raw_bar_replay_failures': len(failures),
            'failure_samples': failures[:20],
            'pass': not failures and len(seeds) == report['seed_count'] and len(trades) == report['executed_or_open_count'] and sum(bool(row['exit_time']) and row['exit_date'] <= row['entry_date'] for row in trades) == 0,
        },
        'recomputed_metrics': {
            'closed_count': len(closed), 'open_unobserved_count': len(trades) - len(closed),
            'wr_pct': 100 * len(wins) / len(pnl), 'avg_net_pct': sum(pnl) / len(pnl),
            'profit_factor': sum(wins) / abs(sum(losses)), 'payoff': (sum(wins) / len(wins)) / (abs(sum(losses)) / len(losses)),
            'yearly': yearly, 'exit_reasons': dict(Counter(row['exit_reason'] for row in trades)),
        },
        'quality_gate': {'minimum_rows': 1000, 'minimum_each_year': 300, 'wr_pct_min': 55.0, 'avg_net_pct_min': 0.5, 'pf_min': 1.15, 'payoff_min': 0.7, 'every_year_avg_net_positive': True},
    }
    close(audit, 'V606_SEMANTIC_STATE_MACHINE_PASS__V624_CONTRACT_COMPLETE_FROZEN_REPLAY_NOT_PROMOTABLE__CLOSE_ECONOMIC_BRANCH_NO_VARIANTS_NO_PRODUCTION')
    print(OUT.read_text())


if __name__ == '__main__':
    main()
