#!/usr/bin/env python3
"""One and only frozen strict-T+1 replay for the V602 canonical daily SMC ontology.

This consumes outcome-blind V602 seeds only after the V603 raw semantic audit.
It neither scans alternatives nor writes any production/frontend/watchlist state.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from v579_v577_frozen_strict_t1_replay import bars, exit_trade, metrics, structural_target

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
SEED_LATEST = AUDIT / 'v602_canonical_bos_demand_reclaim_seed_latest.json'
SEMANTIC_AUDIT = AUDIT / 'v603_v602_independent_raw_semantic_audit_latest.json'
LATEST = AUDIT / 'v605_v602_frozen_strict_t1_replay_latest.json'
OUT = AUDIT / f'v605_v602_frozen_strict_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
YEARS = ('2023', '2024', '2025')
FEE_PCT = 0.20
GATE = {
    'n_min': 1000, 'year_n_min': 300, 'wr_pct_min': 55.0,
    'avg_net_pct_min': 0.50, 'pf_min': 1.15, 'payoff_min': 0.70,
    'each_year_avg_net_positive': True, 't1_violations': 0,
}


def require_authorization() -> None:
    audit = json.loads(SEMANTIC_AUDIT.read_text())
    if not audit.get('pass') or audit.get('checked_seeds') != 49256:
        raise RuntimeError('V603 independent raw semantic audit must pass for all V602 seeds')
    seed_report = json.loads(SEED_LATEST.read_text())
    if seed_report.get('decision') != 'V602_SUPPORT_PASS__INDEPENDENT_RAW_ORACLE_REQUIRED':
        raise RuntimeError('V602 support gate must pass before frozen replay')


def main() -> None:
    require_authorization()
    seed_report = json.loads(SEED_LATEST.read_text())
    with Path(seed_report['artifacts']['seeds']).open(encoding='utf-8', newline='') as handle:
        seeds = [row for row in csv.DictReader(handle) if row['eligible_entry_date'][:4] in YEARS]

    by_symbol: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for seed in seeds:
        by_symbol[seed['symbol']].append(seed)

    OUT.mkdir(parents=True, exist_ok=False)
    trades: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for count, (symbol, symbol_seeds) in enumerate(sorted(by_symbol.items()), 1):
        stock_bars = bars(symbol)
        index = {bar['d']: i for i, bar in enumerate(stock_bars)}
        busy_until = -1
        for seed in sorted(symbol_seeds, key=lambda row: (row['eligible_entry_date'], row['signal_date'])):
            hold_i = index.get(seed['hold_date'])
            entry_i = index.get(seed['eligible_entry_date'])
            if hold_i is None or entry_i is None or entry_i != hold_i + 1:
                skipped['NO_EXACT_HOLD_NEXT_OPEN'] += 1
                continue
            if entry_i <= busy_until:
                skipped['SERIAL_SYMBOL_POSITION_OPEN'] += 1
                continue
            if entry_i + 1 >= len(stock_bars):
                skipped['NO_T1_FORWARD_BAR'] += 1
                continue
            entry = stock_bars[entry_i]['o']
            stop = float(seed['zone_low']) * 0.99
            if not 0 < stop < entry:
                skipped['INVALID_STRUCTURAL_STOP'] += 1
                continue
            target = structural_target(stock_bars, hold_i, entry, stop)
            if target is None:
                skipped['NO_PREENTRY_STRUCTURAL_TARGET_RR_1P5'] += 1
                continue
            exit_i, exit_date, exit_price, reason = exit_trade(stock_bars, entry_i, entry, stop, target)
            if exit_i <= entry_i:
                raise RuntimeError(f'strict T+1 violation: {symbol} {stock_bars[entry_i]["d"]}')
            busy_until = exit_i
            trades.append({
                'symbol': symbol,
                'signal_date': seed['signal_date'],
                'hold_date': seed['hold_date'],
                'entry_date': stock_bars[entry_i]['d'],
                'entry_price': round(entry, 8),
                'stop_price': round(stop, 8),
                'target_price': round(target, 8),
                'planned_rr': round((target - entry) / (entry - stop), 6),
                'exit_date': exit_date,
                'exit_price': round(exit_price, 8),
                'exit_reason': reason,
                'hold_bars': exit_i - entry_i,
                'net_pnl_pct': round((exit_price / entry - 1) * 100 - FEE_PCT, 6),
                'execution_contract': 'CONFIRMED_BOS>BACKWARD_DEMAND_OB>TOUCH>RECLAIM>HOLD>NEXT_OPEN>STRICT_T1_STRUCTURE_SL_TP_TIME20_FEE0P2',
            })
        if count % 500 == 0:
            print(json.dumps({'symbols': count, 'trades': len(trades)}, ensure_ascii=False), flush=True)

    overall = metrics(trades)
    yearly = {year: metrics([row for row in trades if row['entry_date'].startswith(year)]) for year in YEARS}
    checks = {
        'n>=1000': overall['n'] >= GATE['n_min'],
        'each_year_n>=300': all(yearly[year]['n'] >= GATE['year_n_min'] for year in YEARS),
        'wr>=55': overall['wr_pct'] >= GATE['wr_pct_min'],
        'avg_net>=0.5': overall['avg_net_pct'] >= GATE['avg_net_pct_min'],
        'pf>=1.15': (overall['profit_factor'] or 0) >= GATE['pf_min'],
        'payoff>=0.7': (overall['payoff'] or 0) >= GATE['payoff_min'],
        'each_year_avg_net>0': all(yearly[year]['avg_net_pct'] > 0 for year in YEARS),
        't1_violations==0': True,
    }
    trade_path = OUT / 'v605_frozen_t1_trades.csv'
    with trade_path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(trades[0]) if trades else ['symbol'])
        writer.writeheader()
        writer.writerows(trades)

    passed = all(checks.values())
    report = {
        'version': 'V605_V602_ONE_FROZEN_STRICT_T1_REPLAY',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'input_contract': 'V602 outcome-blind canonical daily BOS/backward-demand-OB/reclaim seeds after V603 independent raw semantic audit.',
        'frozen_execution_contract': 'entry=eligible next daily open after hold; stop=demand OB low*0.99; target=nearest unconsumed pre-entry right-confirmed swing high with planned RR>=1.5; exits start entry+1 only; gap-aware conservative stop-first collision; time20; fee0.20%; one serial position per symbol.',
        'seed_count': len(seeds), 'closed_trade_count': len(trades), 'skip_counts': dict(skipped),
        'overall': overall, 'yearly': yearly, 'exit_reason_counts': dict(Counter(row['exit_reason'] for row in trades)),
        'promotion_gate': GATE, 'promotion_checks': checks,
        'invariants': {
            'semantic_audit_pass': True,
            'all_targets_preentry': all(row['planned_rr'] >= 1.5 for row in trades),
            't1_violations': 0, 'all_writes_false': True, 'search_count': 1,
        },
        'decision': 'V605_RESEARCH_GATE_PASS__INDEPENDENT_METRIC_AUDIT_REQUIRED' if passed else 'V605_FROZEN_REPLAY_GATE_FAIL__CLOSE_V602_ONTOLOGY_NO_VARIANTS',
        'artifacts': {'out_dir': str(OUT), 'trades': str(trade_path), 'latest': str(LATEST), 'v602': str(SEED_LATEST), 'v603': str(SEMANTIC_AUDIT)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v605_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
