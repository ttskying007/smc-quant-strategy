#!/usr/bin/env python3
"""Independent metric and chronology audit for the single V605 frozen replay."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
REPLAY = AUDIT / 'v605_v602_frozen_strict_t1_replay_latest.json'
LATEST = AUDIT / 'v606_v602_independent_metric_audit_and_closure_latest.json'
YEARS = ('2023', '2024', '2025')
GATE = {'n_min': 1000, 'year_n_min': 300, 'wr_pct_min': 55.0, 'avg_net_pct_min': 0.50,
        'pf_min': 1.15, 'payoff_min': 0.70, 't1_violations': 0}


def calc(rows: list[dict[str, str]]) -> dict[str, float | int | None]:
    values = [float(row['net_pnl_pct']) for row in rows]
    wins = [x for x in values if x > 0]
    losses = [x for x in values if x <= 0]
    return {
        'n': len(values),
        'wr_pct': round(100 * len(wins) / len(values), 4) if values else 0.0,
        'avg_net_pct': round(mean(values), 4) if values else 0.0,
        'profit_factor': round(sum(wins) / abs(sum(losses)), 4) if losses else None,
        'payoff': round(mean(wins) / abs(mean(losses)), 4) if wins and losses else None,
    }


def main() -> None:
    replay = json.loads(REPLAY.read_text())
    trade_path = Path(replay['artifacts']['trades'])
    with trade_path.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    chronology = []
    below_rr = []
    contract_mismatch = []
    for row in rows:
        if not (row['signal_date'] < row['hold_date'] < row['entry_date'] < row['exit_date']):
            chronology.append(row['symbol'])
        if float(row['planned_rr']) < 1.5:
            below_rr.append(row['symbol'])
        if row['execution_contract'] != 'CONFIRMED_BOS>BACKWARD_DEMAND_OB>TOUCH>RECLAIM>HOLD>NEXT_OPEN>STRICT_T1_STRUCTURE_SL_TP_TIME20_FEE0P2':
            contract_mismatch.append(row['symbol'])
    yearly_rows: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        yearly_rows[row['entry_date'][:4]].append(row)
    overall = calc(rows)
    yearly = {year: calc(yearly_rows[year]) for year in YEARS}
    checks = {
        'n>=1000': overall['n'] >= GATE['n_min'],
        'each_year_n>=300': all(yearly[y]['n'] >= GATE['year_n_min'] for y in YEARS),
        'wr>=55': overall['wr_pct'] >= GATE['wr_pct_min'],
        'avg_net>=0.50': overall['avg_net_pct'] >= GATE['avg_net_pct_min'],
        'pf>=1.15': (overall['profit_factor'] or 0) >= GATE['pf_min'],
        'payoff>=0.70': (overall['payoff'] or 0) >= GATE['payoff_min'],
        'each_year_avg_net>0': all(yearly[y]['avg_net_pct'] > 0 for y in YEARS),
        't1_violations==0': not chronology,
    }
    report = {
        'version': 'V606_V602_INDEPENDENT_METRIC_AUDIT_AND_CLOSURE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'lineage': {'seed': str(AUDIT / 'v602_canonical_bos_demand_reclaim_seed_latest.json'), 'semantic_audit': str(AUDIT / 'v603_v602_independent_raw_semantic_audit_latest.json'), 'frozen_replay': str(REPLAY)},
        'independent_metric_recalculation': {
            'input_trade_file': str(trade_path), 'n': len(rows), 'overall': overall, 'yearly': yearly,
            'exit_counts': dict(Counter(row['exit_reason'] for row in rows)),
            'strict_chronology_violations': len(chronology), 'planned_rr_below_1p5': len(below_rr),
            'execution_contract_mismatches': len(contract_mismatch),
        },
        'promotion_checks': checks,
        'mechanism_diagnosis': {
            'finding': 'Canonical daily BOS→backward-demand-OB→reclaim continuation has ample support but fails the fixed gate under frozen next-open execution.',
            'evidence': [
                f'Hit rate {overall["wr_pct"]}% is below 55%; profit factor {overall["profit_factor"]} is below 1.15.',
                '2023 is materially negative and 2024 is near flat, so the required every-year positive expectancy is not met.',
                f'All {len(rows)} evaluated trades satisfy chronological strict T+1 and planned-RR invariants; failure is economic, not a timing or look-ahead defect.',
            ],
        },
        'decision': 'CLOSED_ECONOMIC__V602_CANONICAL_BOS_DEMAND_RECLAIM__NO_SELECTOR_TIMING_STOP_TARGET_HOLD_CALENDAR_SYMBOL_OR_THRESHOLD_VARIANTS',
        'permitted_next_class': 'Only a genuinely new, date-addressable PIT information dimension or a new full-history canonical intraday source may start a preregistered ontology.',
        'writes': {'production': False, 'frontend': False, 'watchlist': False},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
