#!/usr/bin/env python3
"""V545 single frozen strict-T+1 replay of V543's verified m15 ontology.

Execution is fixed before reading outcomes: next-m15 open; stop at sweep low
*0.997; nearest already-visible unconsumed confirmed 3L/3R high with planned
RR >=1.5; exits begin only on the next trade date; stop-first collision;
80 post-entry m15 bars; 0.20% round-trip fee; one serial position per symbol.
This is source-isolated partial-range research only and writes no live state.
"""
from __future__ import annotations

import csv
import importlib.util
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
V543 = AUDIT / 'v543_sina_m15_ssl_displacement_absorption_seed_gate_latest.json'
V544 = AUDIT / 'v544_sina_m15_ssl_displacement_absorption_independent_oracle_latest.json'
V541_SOURCE = ROOT / 'scripts/v25/v541_sina_m15_ssl_bos_fvg_frozen_t1_replay.py'
OUT = AUDIT / f'v545_sina_m15_ssl_displacement_absorption_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v545_sina_m15_ssl_displacement_absorption_frozen_t1_replay_latest.json'
GATE = {'n_min': 1000, 'year_n_min': 300, 'gross_wr_pct_min': 55.0, 'avg_net_pnl_pct_min': 0.50, 'pf_min': 1.15, 'payoff_min': 0.70, 'year_avg_net_pnl_pct_min': 0.0}

spec = importlib.util.spec_from_file_location('v541_execution_contract', V541_SOURCE)
if not spec or not spec.loader:
    raise RuntimeError('cannot load frozen execution helper')
v541 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v541)


def main() -> None:
    seed_gate, oracle = json.loads(V543.read_text()), json.loads(V544.read_text())
    if seed_gate.get('decision') != 'V543_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED':
        raise RuntimeError('V543 support gate did not authorize replay')
    if oracle.get('decision') != 'V544_ORACLE_PASS__ONE_FROZEN_PARTIAL_RANGE_REPLAY_AUTHORIZED':
        raise RuntimeError('V544 independent oracle did not authorize replay')
    OUT.mkdir(parents=True, exist_ok=False)
    with Path(seed_gate['artifacts']['seeds']).open(newline='', encoding='utf-8') as handle:
        seeds = list(csv.DictReader(handle))
    seeds.sort(key=lambda row: (row['symbol'], row['entry_time'], row['sweep_time']))
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for seed in seeds:
        grouped[seed['symbol']].append(seed)
    closed: list[dict[str, Any]] = []
    open_data: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for symbol, rows_of_symbol in grouped.items():
        bars = v541.load_bars(symbol)
        index = {row['t']: i for i, row in enumerate(bars)}
        pivots, highs = v541.high_pivots(bars), v541.high_table(bars)
        targets = v541.target_cache(bars, pivots, index, rows_of_symbol, highs)
        busy_until = ''
        for seed in rows_of_symbol:
            if busy_until >= seed['entry_time']:
                skipped['SYMBOL_ALREADY_OPEN'] += 1
                continue
            result = v541.replay(seed, bars, index, targets.get((seed['sweep_time'], seed['entry_time'])))
            if result['status'] == 'SKIP':
                skipped[result['reason']] += 1
                continue
            record = {**seed, **result}
            if result['status'] == 'OPEN_DATA':
                skipped[result['reason']] += 1
                open_data.append(record)
                continue
            closed.append(record)
            busy_until = result['exit_time']
    yearly = {year: v541.stats([row for row in closed if row['entry_date'].startswith(year)]) for year in ('2025', '2026')}
    overall = v541.stats(closed)
    invariants = {
        'frozen_seed_count_matches_oracle': len(seeds) == oracle['expected_identities'] == oracle['oracle_identities'],
        'all_entries_after_reclaim': all(row['entry_time'] > row['reclaim_time'] for row in closed),
        'all_targets_visible_pre_entry': all(row['target_pivot_time'] < row['entry_time'] for row in closed),
        'all_planned_rr_gte_1_5': all(float(row['planned_rr']) >= v541.MIN_RR for row in closed),
        't1_violations': sum(bool(row['same_day_exit_violation']) for row in closed),
        'all_writes_false': True,
    }
    checks = {
        'n>=1000': overall['n'] >= GATE['n_min'],
        'each_year_n>=300': all(yearly[year]['n'] >= GATE['year_n_min'] for year in yearly),
        'gross_wr>=55': overall['gross_wr_pct'] >= GATE['gross_wr_pct_min'],
        'avg_net>=0.5': overall['avg_net_pnl_pct'] >= GATE['avg_net_pnl_pct_min'],
        'pf>=1.15': overall['profit_factor'] >= GATE['pf_min'],
        'payoff>=0.7': overall['payoff_rr'] >= GATE['payoff_min'],
        'each_year_avg_net>0': all(yearly[year]['avg_net_pnl_pct'] > GATE['year_avg_net_pnl_pct_min'] for year in yearly),
        't1_violations==0': invariants['t1_violations'] == 0,
    }
    trades = OUT / 'v545_frozen_t1_trades.csv'
    if closed:
        with trades.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(closed[0])); writer.writeheader(); writer.writerows(closed)
    result = {
        'version': 'V545_SINA_M15_SSL_DISPLACEMENT_ABSORPTION_FROZEN_T1_REPLAY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'SINA_SOURCE_ISOLATED_PARTIAL_RANGE_2025_04_TO_2026_07_ONLY__NOT_PRODUCTION',
        'source_contract': 'Sina source-isolated m15 only; no Baostock/Tencent substitution.',
        'frozen_execution_contract': 'next-15m open; stop=sweep low*0.997; nearest visible unconsumed 3L/3R high with planned RR>=1.5; exits only next trade date onward; stop-first; time80; fee0.20%; serial symbol position.',
        'seed_count': len(seeds), 'closed_trade_count': len(closed), 'open_data_count': len(open_data), 'skip_counts': dict(skipped),
        'overall': overall, 'yearly': yearly, 'promotion_gate': GATE, 'promotion_checks': checks, 'invariants': invariants,
        'partial_research_gate_pass': all(checks.values()),
        'decision': 'V545_PARTIAL_RANGE_RESEARCH_PASS__FULL_HISTORY_AND_PRODUCTION_STILL_BLOCKED' if all(checks.values()) else 'V545_PARTIAL_RANGE_RESEARCH_FAIL__CLOSE_OBJECT',
        'artifacts': {'out_dir': str(OUT), 'trades': str(trades), 'latest': str(LATEST), 'v543': str(V543), 'v544': str(V544), 'execution_helper': str(V541_SOURCE)},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v545_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
