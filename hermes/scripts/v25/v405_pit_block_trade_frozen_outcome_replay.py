#!/usr/bin/env python3
"""V405 no-write replay of four predeclared V404 block-trade contexts.

The block-trade states are categorical and fixed before outcomes are opened.
There is no threshold, combination, or exit search.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
V381 = AUD / 'v381_true_mtf_raw_daily_poi_m60_replay_latest.json'
V404 = AUD / 'v404_pit_block_trade_availability_latest.json'
OUT = AUD / f'v405_pit_block_trade_frozen_outcome_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v405_pit_block_trade_frozen_outcome_replay_latest.json'
STATES = ('NO_BLOCK', 'INSTITUTION_NET_BUY', 'INSTITUTION_NET_SELL', 'NON_INSTITUTION_BLOCK')
GATE = {'n_min': 300, 'each_year_n_min': 40, 'wr_uplift_pp_min': 5.0,
        'avg_pnl_uplift_pp_min': 1.0, 'min_year_wr_uplift_pp_min': 3.0}


def metrics(rows: list[dict]) -> dict:
    yearly: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        yearly[row['entry_date'][:4]].append(float(row['pnl_pct']))
    by_year = {year: {'n': len(values), 'wr_pct': round(100 * sum(x > 0 for x in values) / len(values), 4),
                      'avg_pnl_pct': round(sum(values) / len(values), 4)} for year, values in sorted(yearly.items())}
    pnl = [float(row['pnl_pct']) for row in rows]
    return {'n': len(rows), 'wr_pct': round(100 * sum(x > 0 for x in pnl) / len(pnl), 4) if pnl else 0,
            'avg_pnl_pct': round(sum(pnl) / len(pnl), 4) if pnl else 0, 'yearly': by_year,
            'min_year_n': min((x['n'] for x in by_year.values()), default=0),
            'min_year_wr_pct': min((x['wr_pct'] for x in by_year.values()), default=0)}


def state(row: dict) -> str:
    events = int(row['block_prior_events'])
    buy = float(row['block_prior_institution_buy_amount'])
    sell = float(row['block_prior_institution_sell_amount'])
    if events == 0:
        return 'NO_BLOCK'
    if buy > sell:
        return 'INSTITUTION_NET_BUY'
    if sell > buy:
        return 'INSTITUTION_NET_SELL'
    return 'NON_INSTITUTION_BLOCK'


def uplift(item: dict, base: dict) -> dict:
    return {'wr_uplift_pp': round(item['wr_pct'] - base['wr_pct'], 4),
            'avg_pnl_uplift_pp': round(item['avg_pnl_pct'] - base['avg_pnl_pct'], 4),
            'min_year_wr_uplift_pp': round(item['min_year_wr_pct'] - base['min_year_wr_pct'], 4)}


def epoch_metrics(rows: list[dict], prefix: tuple[str, str]) -> dict:
    return metrics([row for row in rows if prefix[0] <= row['entry_date'][:4] <= prefix[1]])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads(V404.read_text())
    if source['decision'] != 'PIT_BLOCK_TRADE_AVAILABILITY_PASS__OUTCOME_BLIND_REPLAY_ALLOWED':
        raise RuntimeError('V404 availability gate did not pass')
    with Path(source['artifacts']['features']).open(newline='') as handle:
        features = {(row['symbol'], row['hold_time']): {**row, 'pit_block_state': state(row)} for row in csv.DictReader(handle)}
    v381 = json.loads(V381.read_text())
    with Path(v381['artifacts']['trades']).open(newline='') as handle:
        trades = [{**row, **features[(row['symbol'], row['hold_time'])]} for row in csv.DictReader(handle)]
    baseline = metrics(trades)
    early, late = epoch_metrics(trades, ('2023', '2024')), epoch_metrics(trades, ('2025', '2026'))
    results = []
    for name in STATES:
        rows = [row for row in trades if row['pit_block_state'] == name]
        item = metrics(rows)
        item['state'] = name
        item['uplift_vs_baseline'] = uplift(item, baseline)
        item['epoch_2023_24'] = {'metrics': epoch_metrics(rows, ('2023', '2024')), 'uplift': uplift(epoch_metrics(rows, ('2023', '2024')), early)}
        item['epoch_2025_26'] = {'metrics': epoch_metrics(rows, ('2025', '2026')), 'uplift': uplift(epoch_metrics(rows, ('2025', '2026')), late)}
        u = item['uplift_vs_baseline']
        item['discovery_gate_pass'] = (item['n'] >= GATE['n_min'] and item['min_year_n'] >= GATE['each_year_n_min'] and
                                       u['wr_uplift_pp'] >= GATE['wr_uplift_pp_min'] and u['avg_pnl_uplift_pp'] >= GATE['avg_pnl_uplift_pp_min'] and
                                       u['min_year_wr_uplift_pp'] >= GATE['min_year_wr_uplift_pp_min'] and
                                       item['epoch_2023_24']['uplift']['avg_pnl_uplift_pp'] > 0 and item['epoch_2025_26']['uplift']['avg_pnl_uplift_pp'] > 0)
        results.append(item)
    passes = [item['state'] for item in results if item['discovery_gate_pass']]
    row_path = OUT / 'v405_rows.csv'
    with row_path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(trades[0])); writer.writeheader(); writer.writerows(trades)
    report = {'version': 'V405_PIT_BLOCK_TRADE_FROZEN_OUTCOME_REPLAY_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
              'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
              'input_contract': 'V404 fixed strict-prior-date 30-calendar-day block-trade categories joined to frozen V381 completed rows only after availability passed',
              'state_schema': {'NO_BLOCK': 'no prior block-trade record', 'INSTITUTION_NET_BUY': 'institution-only buyer amount > seller amount',
                               'INSTITUTION_NET_SELL': 'institution-only seller amount > buyer amount', 'NON_INSTITUTION_BLOCK': 'prior record but no institution-only net direction'},
              'discovery_gate_predeclared': GATE, 'matched_baseline': baseline, 'feature_states': results,
              'decision': 'BLOCK_TRADE_CONTEXT_INFORMATION_FOUND__CANDIDATE_LEVEL_REPLAY_REQUIRED' if passes else 'NO_CONTEXT_INFORMATION__BLOCK_TRADE_BRANCH_CLOSED',
              'promising_states': passes,
              'audit': {'v381_rows': len(trades), 'feature_join_complete': len(trades) == 4832,
                        'cutoff_equal_hold_time': all(row['feature_cutoff'] == row['hold_time'] for row in trades),
                        'state_counts': dict(Counter(row['pit_block_state'] for row in trades))},
              'artifacts': {'rows': str(row_path), 'latest': str(LATEST)}}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v405_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__':
    main()
