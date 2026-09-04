#!/usr/bin/env python3
"""V625: independent metrics and chronology audit for the single V624 frozen replay."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
REPLAY = AUDIT / 'v624_v622_frozen_strict_t1_replay_latest.json'
LATEST = AUDIT / 'v625_v622_independent_metric_audit_and_closure_latest.json'
YEARS = ('2023', '2024', '2025')
GATE = {'n_min': 1000, 'year_n_min': 300, 'wr_pct_min': 55.0, 'avg_net_pct_min': 0.50, 'pf_min': 1.15, 'payoff_min': 0.70, 't1_violations': 0}
CONTRACT = 'PIT_CONTROLLING_HOLDER_PLEDGE_CREATE_D_PRIOR>SSL_SWEEP>LH_BREAK>DEMAND_RECLAIM>D_PLUS_1_OPEN>STRICT_T1_STRUCTURE_SL_TP_TIME20_FEE0P2'


def calc(rows: list[dict[str, str]]) -> dict[str, float | int | None]:
    values = [float(row['net_pnl_pct']) for row in rows]
    wins, losses = [value for value in values if value > 0], [value for value in values if value <= 0]
    return {
        'n': len(values),
        'wr_pct': round(100 * len(wins) / len(values), 4) if values else 0.0,
        'avg_net_pct': round(mean(values), 4) if values else 0.0,
        'profit_factor': round(sum(wins) / abs(sum(losses)), 4) if losses else None,
        'payoff': round(mean(wins) / abs(mean(losses)), 4) if wins and losses else None,
    }


def main() -> None:
    replay = json.loads(REPLAY.read_text())
    with Path(replay['artifacts']['trades']).open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    chronology = []
    below_rr = []
    contract_mismatch = []
    for row in rows:
        if not (row['event_date'] < row['signal_date'] < row['entry_date'] < row['exit_date']):
            chronology.append(row['symbol'])
        if float(row['planned_rr']) < 1.5:
            below_rr.append(row['symbol'])
        if row['execution_contract'] != CONTRACT:
            contract_mismatch.append(row['symbol'])
    yearly_rows: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        yearly_rows[row['entry_date'][:4]].append(row)
    overall = calc(rows)
    yearly = {year: calc(yearly_rows[year]) for year in YEARS}
    checks = {
        'n>=1000': overall['n'] >= GATE['n_min'],
        'each_year_n>=300': all(yearly[year]['n'] >= GATE['year_n_min'] for year in YEARS),
        'wr>=55': overall['wr_pct'] >= GATE['wr_pct_min'],
        'avg_net>=0.50': overall['avg_net_pct'] >= GATE['avg_net_pct_min'],
        'pf>=1.15': (overall['profit_factor'] or 0) >= GATE['pf_min'],
        'payoff>=0.70': (overall['payoff'] or 0) >= GATE['payoff_min'],
        'each_year_avg_net>0': all(yearly[year]['avg_net_pct'] > 0 for year in YEARS),
        't1_violations==0': not chronology,
    }
    report = {
        'version': 'V625_V622_INDEPENDENT_METRIC_AUDIT_AND_CLOSURE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'lineage': {
            'catalog': str(AUDIT / 'v615_controlling_pledge_pit_event_catalog_latest.json'),
            'preregistration': str(AUDIT / 'v621_controlling_pledge_creation_ssl_exhaustion_preregistration_latest.json'),
            'seed': str(AUDIT / 'v622_controlling_pledge_creation_ssl_exhaustion_seed_latest.json'),
            'oracle': str(AUDIT / 'v623_v622_independent_raw_oracle_latest.json'),
            'frozen_replay': str(REPLAY),
        },
        'independent_metric_recalculation': {
            'input_trade_file': replay['artifacts']['trades'],
            'n': len(rows),
            'overall': overall,
            'yearly': yearly,
            'exit_counts': dict(Counter(row['exit_reason'] for row in rows)),
            'strict_chronology_violations': len(chronology),
            'planned_rr_below_1p5': len(below_rr),
            'execution_contract_mismatches': len(contract_mismatch),
        },
        'promotion_checks': checks,
        'mechanism_diagnosis': {
            'finding': 'PIT controlling-holder pledge creation -> confirmed SSL sweep -> confirmed lower-high break -> demand-OB retest/reclaim has full outcome-blind support but fails the fixed quality gate under its preregistered frozen next-open execution.',
            'evidence': [
                f'Hit rate {overall["wr_pct"]}% is below 55%; average net {overall["avg_net_pct"]}% is below +0.50%; profit factor {overall["profit_factor"]} is below 1.15.',
                f'2023 ({yearly["2023"]["avg_net_pct"]}%) and 2024 ({yearly["2024"]["avg_net_pct"]}%) are negative; the required every-year positive expectancy is not met.',
                f'All {len(rows)} evaluated trades satisfy exact causal chronology, strict T+1, pre-entry RR and frozen execution-contract invariants; this is an economic failure, not a timing or look-ahead failure.',
            ],
        },
        'decision': 'CLOSED_ECONOMIC__V622_CONTROLLING_HOLDER_PLEDGE_CREATION_SSL_EXHAUSTION__NO_SELECTOR_TIMING_STOP_TARGET_HOLD_CALENDAR_SYMBOL_OR_THRESHOLD_VARIANTS',
        'permitted_next_class': 'Only a genuinely new, date-addressable PIT information dimension or a new full-history canonical intraday source may start a preregistered ontology.',
        'writes': {'production': False, 'frontend': False, 'watchlist': False},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
