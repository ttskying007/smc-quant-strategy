#!/usr/bin/env python3
"""V566 one frozen strict-T+1 replay for the pre-registered V563/V565 contract."""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/daily'
AUDIT = ROOT / 'smc_audit'
FEASIBILITY = AUDIT / 'v565_v563_preentry_target_feasibility_latest.json'
OUT = AUDIT / f'v566_v563_frozen_strict_t1_replay_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v566_v563_frozen_strict_t1_replay_latest.json'
FEE_PCT = 0.20
MAX_HOLD = 20
PROMOTION = {'total_min': 1000, 'year_min': 300, 'wr_min': 55.0, 'avg_net_min': 0.50, 'pf_min': 1.15, 'payoff_min': 0.70}


def number(value):
    try:
        value = float(value)
        return value if value > 0 and math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def daily(symbol):
    path = RAW / f'{symbol.replace(".", "_")}_daily.json.gz'
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        payload = json.load(handle)
    rows = []
    for raw in payload:
        d = str(raw.get('d') or raw.get('t') or '')[:8]
        values = [number(raw.get(k)) for k in ('o', 'h', 'l', 'c')]
        if d and all(value is not None for value in values):
            rows.append(dict(zip(('d', 'o', 'h', 'l', 'c'), (d, *values))))
    return sorted(rows, key=lambda row: row['d'])


def replay(seed, rows):
    entry_date = seed['entry_date']
    entry = float(seed['entry_price'])
    stop, target = float(seed['structure_stop']), float(seed['target_price'])
    index = next((i for i, row in enumerate(rows) if row['d'] == entry_date), None)
    if index is None or index + MAX_HOLD >= len(rows):
        return None
    # T+1: daily exits begin strictly on entry_date's next trading day.
    for hold, row in enumerate(rows[index + 1:index + 1 + MAX_HOLD], 1):
        if row['o'] <= stop:
            price, reason = row['o'], 'GAP_STOP'
        elif row['o'] >= target:
            price, reason = row['o'], 'GAP_TARGET'
        elif row['l'] <= stop and row['h'] >= target:
            price, reason = stop, 'SAME_BAR_STOP_FIRST'
        elif row['l'] <= stop:
            price, reason = stop, 'STOP'
        elif row['h'] >= target:
            price, reason = target, 'TARGET'
        else:
            continue
        gross = (price / entry - 1) * 100
        return {**seed, 'exit_date': row['d'], 'exit_price': round(price, 6), 'exit_reason': reason,
                'hold_trading_days': hold, 'gross_pct': round(gross, 6), 'net_pct': round(gross - FEE_PCT, 6)}
    row = rows[index + MAX_HOLD]
    gross = (row['c'] / entry - 1) * 100
    return {**seed, 'exit_date': row['d'], 'exit_price': round(row['c'], 6), 'exit_reason': 'TIME_STOP',
            'hold_trading_days': MAX_HOLD, 'gross_pct': round(gross, 6), 'net_pct': round(gross - FEE_PCT, 6)}


def metrics(rows):
    if not rows:
        return {'n': 0}
    wins = [row['net_pct'] for row in rows if row['net_pct'] > 0]
    losses = [-row['net_pct'] for row in rows if row['net_pct'] <= 0]
    profit = sum(wins)
    loss = sum(losses)
    return {
        'n': len(rows),
        'wr_pct': round(100 * len(wins) / len(rows), 4),
        'avg_net_pct': round(mean(row['net_pct'] for row in rows), 4),
        'profit_factor': round(profit / loss, 4) if loss else None,
        'payoff': round(mean(wins) / mean(losses), 4) if wins and losses else None,
        'avg_win_pct': round(mean(wins), 4) if wins else None,
        'avg_loss_pct': round(-mean(losses), 4) if losses else None,
        'exit_counts': dict(Counter(row['exit_reason'] for row in rows)),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    feasibility = json.loads(FEASIBILITY.read_text())
    if feasibility['decision'] != 'V565_FEASIBILITY_PASS__ONE_FROZEN_T1_REPLAY_AUTHORIZED':
        raise RuntimeError('pre-outcome execution-feasibility gate did not authorize replay')
    with Path(feasibility['artifacts']['feasible_seeds']).open(newline='', encoding='utf-8') as handle:
        seeds = list(csv.DictReader(handle))
    by_symbol = defaultdict(list)
    for seed in seeds:
        by_symbol[seed['symbol']].append(seed)
    trades, skipped = [], 0
    for number_index, (symbol, symbol_seeds) in enumerate(sorted(by_symbol.items()), 1):
        source = daily(symbol)
        for seed in symbol_seeds:
            result = replay(seed, source)
            if result is None:
                skipped += 1
            else:
                trades.append(result)
        if number_index % 500 == 0:
            print(json.dumps({'symbols': number_index, 'trades': len(trades)}), flush=True)
    trades.sort(key=lambda row: (row['entry_date'], row['symbol'], row['sweep_date']))
    years = {year: metrics([row for row in trades if row['entry_date'].startswith(year)]) for year in ('2025', '2026')}
    overall = metrics(trades)
    t1_violations = sum(row['exit_date'] <= row['entry_date'] for row in trades)
    gate = {
        'n>=1000': overall['n'] >= PROMOTION['total_min'],
        '2025_n>=300': years['2025']['n'] >= PROMOTION['year_min'],
        '2026_n>=300': years['2026']['n'] >= PROMOTION['year_min'],
        'wr>=55': overall['wr_pct'] >= PROMOTION['wr_min'],
        'avg_net>=0.50': overall['avg_net_pct'] >= PROMOTION['avg_net_min'],
        'pf>=1.15': overall['profit_factor'] is not None and overall['profit_factor'] >= PROMOTION['pf_min'],
        'payoff>=0.70': overall['payoff'] is not None and overall['payoff'] >= PROMOTION['payoff_min'],
        'every_year_avg_net_positive': all(years[year]['avg_net_pct'] > 0 for year in years),
        't1_violations=0': t1_violations == 0,
    }
    trade_path = OUT / 'v566_frozen_t1_trades.csv'
    fields = sorted({key for row in trades for key in row}) or ['symbol', 'entry_date']
    with trade_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(trades)
    report = {
        'version': 'V566_V563_ONE_FROZEN_STRICT_T1_REPLAY',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'input_contract': feasibility['frozen_execution_contract_for_next_stage'],
        'no_selector_or_parameter_search_after_outcomes': True,
        'execution': {'input_feasible_seeds': len(seeds), 'executed': len(trades), 'skipped': skipped, 'fee_pct': FEE_PCT, 't1_violations': t1_violations},
        'overall': overall,
        'yearly': years,
        'promotion_gate': PROMOTION,
        'gate_evaluation': gate,
        'pass': all(gate.values()),
        'decision': 'V566_PROMOTION_GATE_PASS__REQUIRES_SEPARATE_CURRENT_SCANNER_CONTRACT' if all(gate.values()) else 'V566_FROZEN_REPLAY_GATE_FAILED__CLOSE_V563_CONTRACT_NO_VARIANTS',
        'artifacts': {'out_dir': str(OUT), 'trades': str(trade_path), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v566_report.json').write_text(text); LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
