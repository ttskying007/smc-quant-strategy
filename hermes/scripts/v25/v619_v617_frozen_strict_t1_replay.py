#!/usr/bin/env python3
"""V619: one frozen strict-T+1 replay for V617 after exact V618 Oracle equality."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from v579_v577_frozen_strict_t1_replay import bars, exit_trade, metrics, structural_target

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
SEED = AUDIT / 'v617_controlling_pledge_release_demand_retest_seed_latest.json'
ORACLE = AUDIT / 'v618_v617_independent_raw_oracle_latest.json'
LATEST = AUDIT / 'v619_v617_frozen_strict_t1_replay_latest.json'
OUT = AUDIT / f'v619_v617_frozen_strict_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
YEARS = ('2023', '2024', '2025')
FEE = 0.20
GATE = {'n_min': 1000, 'year_n_min': 300, 'wr_pct_min': 55.0, 'avg_net_pct_min': 0.50, 'pf_min': 1.15, 'payoff_min': 0.70, 'each_year_avg_net_positive': True, 't1_violations': 0}


def main() -> None:
    oracle, seed_report = json.loads(ORACLE.read_text()), json.loads(SEED.read_text())
    if oracle['decision'] != 'V618_ORACLE_PASS__ONE_FROZEN_STRICT_T1_REPLAY_AUTHORIZED':
        raise RuntimeError('V618 exact Oracle pass required')
    with Path(seed_report['artifacts']['seeds']).open(encoding='utf-8', newline='') as handle:
        seeds = list(csv.DictReader(handle))
    grouped = defaultdict(list)
    for seed in seeds:
        grouped[seed['symbol']].append(seed)
    OUT.mkdir(parents=True, exist_ok=False)
    trades, skipped = [], Counter()
    for count, (symbol, items) in enumerate(sorted(grouped.items()), 1):
        stock_bars = bars(symbol)
        index, busy_until = {row['d']: i for i, row in enumerate(stock_bars)}, -1
        for seed in sorted(items, key=lambda row: (row['planned_entry_date'], row['event_date'], row['announcement_id'])):
            signal_i, entry_i = index.get(seed['reclaim_date']), index.get(seed['planned_entry_date'])
            if signal_i is None or entry_i is None or entry_i != signal_i + 1:
                skipped['NO_EXACT_RECLAIM_NEXT_OPEN'] += 1
                continue
            if entry_i <= busy_until:
                skipped['SERIAL_SYMBOL_POSITION_OPEN'] += 1
                continue
            if entry_i + 1 >= len(stock_bars):
                skipped['NO_T1_FORWARD_BAR'] += 1
                continue
            entry, stop = stock_bars[entry_i]['o'], float(seed['zone_low']) * 0.99
            if not 0 < stop < entry:
                skipped['INVALID_STRUCTURAL_STOP'] += 1
                continue
            target = structural_target(stock_bars, signal_i, entry, stop)
            if target is None:
                skipped['NO_UNCONSUMED_PREENTRY_TARGET_RR_1P5'] += 1
                continue
            exit_i, exit_date, exit_price, reason = exit_trade(stock_bars, entry_i, entry, stop, target)
            if exit_i <= entry_i:
                raise RuntimeError('strict T+1 violation')
            busy_until = exit_i
            trades.append({
                'symbol': symbol,
                'announcement_id': seed['announcement_id'],
                'event_date': seed['event_date'],
                'signal_date': seed['reclaim_date'],
                'entry_date': stock_bars[entry_i]['d'],
                'entry_price': round(entry, 8),
                'stop_price': round(stop, 8),
                'target_price': round(target, 8),
                'planned_rr': round((target - entry) / (entry - stop), 6),
                'exit_date': exit_date,
                'exit_price': round(exit_price, 8),
                'exit_reason': reason,
                'hold_bars': exit_i - entry_i,
                'net_pnl_pct': round((exit_price / entry - 1) * 100 - FEE, 6),
                'execution_contract': 'PIT_CONTROLLING_HOLDER_PLEDGE_RELEASE_D_PRIOR>BSL_ACCEPTANCE>DEMAND_RECLAIM>D_PLUS_1_OPEN>STRICT_T1_STRUCTURE_SL_TP_TIME20_FEE0P2',
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
    path = OUT / 'v619_frozen_t1_trades.csv'
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(trades[0]) if trades else ['symbol'])
        writer.writeheader()
        writer.writerows(trades)
    passed = all(checks.values())
    report = {
        'version': 'V619_V617_ONE_FROZEN_STRICT_T1_REPLAY',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'input_contract': 'V617 outcome-blind controlling-holder pledge-release+SMC seeds after V618 exact independent raw Oracle identity equality.',
        'frozen_execution_contract': 'entry=first daily open after reclaim; stop=demand POI low*0.99; target=nearest unconsumed pre-entry right-confirmed daily swing high RR>=1.5; exits start entry+1 only; gap-aware conservative stop-first collision; time20; fee0.20%; serial positions.',
        'seed_count': len(seeds),
        'closed_trade_count': len(trades),
        'skip_counts': dict(skipped),
        'overall': overall,
        'yearly': yearly,
        'exit_reason_counts': dict(Counter(row['exit_reason'] for row in trades)),
        'promotion_gate': GATE,
        'promotion_checks': checks,
        'invariants': {'oracle_identity_pass': True, 'all_targets_preentry': all(row['planned_rr'] >= 1.5 for row in trades), 't1_violations': 0, 'all_writes_false': True, 'search_count': 1},
        'decision': 'V619_RESEARCH_GATE_PASS__INDEPENDENT_METRIC_AUDIT_REQUIRED' if passed else 'V619_FROZEN_REPLAY_GATE_FAIL__CLOSE_V617_ONTOLOGY_NO_VARIANTS',
        'artifacts': {'out_dir': str(OUT), 'trades': str(path), 'latest': str(LATEST), 'v617': str(SEED), 'v618': str(ORACLE)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v619_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
