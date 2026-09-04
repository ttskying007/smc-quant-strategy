#!/usr/bin/env python3
"""V403 frozen no-write outcome replay for the predeclared V402 holder features."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
V402 = AUD / 'v402_pit_shareholder_feature_materialization_latest.json'
TRADES = ROOT / 'smc_audit/v381_true_mtf_raw_daily_poi_m60_replay_no_write_20260712_110522/v381_trades.csv'
OUT = AUD / f'v403_pit_shareholder_frozen_outcome_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v403_pit_shareholder_frozen_outcome_replay_latest.json'
FEATURES = ('top10_concentrated', 'top1_controller', 'fund_present', 'institutional_present', 'northbound_nominee_present')
# Written before reading trade PnL: a discovery gate, never a production promotion gate.
DISCOVERY_GATE = {'n_min': 300, 'each_year_n_min': 40, 'wr_uplift_pp_min': 5.0,
                  'avg_pnl_uplift_pp_min': 1.0, 'min_year_wr_uplift_pp_min': 3.0}


def truth(value: str) -> bool:
    return str(value).strip().lower() == 'true'


def stats(rows: list[dict]) -> dict:
    pnl = [float(row['pnl_pct']) for row in rows]
    yearly: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        yearly[row['entry_date'][:4]].append(float(row['pnl_pct']))
    def one(values: list[float]) -> dict:
        return {'n': len(values), 'wr_pct': round(100 * sum(x > 0 for x in values) / len(values), 4) if values else 0,
                'avg_pnl_pct': round(sum(values) / len(values), 4) if values else 0}
    years = {year: one(values) for year, values in sorted(yearly.items())}
    return {**one(pnl), 'yearly': years,
            'min_year_n': min((item['n'] for item in years.values()), default=0),
            'min_year_wr_pct': min((item['wr_pct'] for item in years.values()), default=0)}


def uplift(candidate: dict, baseline: dict) -> dict:
    return {'wr_uplift_pp': round(candidate['wr_pct'] - baseline['wr_pct'], 4),
            'avg_pnl_uplift_pp': round(candidate['avg_pnl_pct'] - baseline['avg_pnl_pct'], 4),
            'min_year_wr_uplift_pp': round(candidate['min_year_wr_pct'] - baseline['min_year_wr_pct'], 4)}


def passes(candidate: dict, diff: dict) -> bool:
    return (candidate['n'] >= DISCOVERY_GATE['n_min'] and candidate['min_year_n'] >= DISCOVERY_GATE['each_year_n_min']
            and diff['wr_uplift_pp'] >= DISCOVERY_GATE['wr_uplift_pp_min']
            and diff['avg_pnl_uplift_pp'] >= DISCOVERY_GATE['avg_pnl_uplift_pp_min']
            and diff['min_year_wr_uplift_pp'] >= DISCOVERY_GATE['min_year_wr_uplift_pp_min'])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    material = json.loads(V402.read_text())
    feature_path = Path(material['artifacts']['features'])
    with feature_path.open(newline='', encoding='utf-8') as handle:
        feature_rows = list(csv.DictReader(handle))
    keyed = {(row['symbol'], row['entry_date']): row for row in feature_rows}
    with TRADES.open(newline='', encoding='utf-8') as handle:
        trades = list(csv.DictReader(handle))
    joined = [{**trade, **keyed[(trade['symbol'], trade['entry_date'])]} for trade in trades if (trade['symbol'], trade['entry_date']) in keyed]
    baseline = stats(joined)
    states = []
    for feature in FEATURES:
        for value in (True, False):
            group = [row for row in joined if truth(row[feature]) == value]
            current = stats(group)
            diff = uplift(current, baseline)
            # Fixed chronological stress: no training/tuning. Each feature state must work in both epochs.
            epoch_a, epoch_b = stats([r for r in group if r['entry_date'][:4] in ('2023', '2024')]), stats([r for r in group if r['entry_date'][:4] in ('2025', '2026')])
            base_a, base_b = stats([r for r in joined if r['entry_date'][:4] in ('2023', '2024')]), stats([r for r in joined if r['entry_date'][:4] in ('2025', '2026')])
            diff_a, diff_b = uplift(epoch_a, base_a), uplift(epoch_b, base_b)
            epoch_pass = (epoch_a['n'] >= 150 and epoch_b['n'] >= 150 and diff_a['wr_uplift_pp'] >= 3.0 and diff_b['wr_uplift_pp'] >= 3.0
                          and diff_a['avg_pnl_uplift_pp'] >= 0.5 and diff_b['avg_pnl_uplift_pp'] >= 0.5)
            states.append({'feature': feature, 'state': value, 'metrics': current, 'uplift_vs_matched_baseline': diff,
                           'epoch_2023_24': {'metrics': epoch_a, 'uplift': diff_a},
                           'epoch_2025_26': {'metrics': epoch_b, 'uplift': diff_b},
                           'discovery_gate_pass': passes(current, diff) and epoch_pass})
    result = {
        'version': 'V403_PIT_SHAREHOLDER_FROZEN_OUTCOME_REPLAY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'input_contract': 'V402 fixed pre-outcome shareholder feature schema joined by symbol+entry_date to V381 completed trades',
        'schema': material['fixed_feature_schema'], 'discovery_gate_predeclared': DISCOVERY_GATE,
        'matched_baseline': baseline, 'feature_states': states,
        'passing_states': [f'{row["feature"]}={row["state"]}' for row in states if row['discovery_gate_pass']],
        'decision': ('PIT_HOLDER_DISCOVERY_SIGNAL_FOUND__INDEPENDENT_REPLICATION_REQUIRED'
                     if any(row['discovery_gate_pass'] for row in states) else
                     'PIT_HOLDER_FEATURES_NO_DISCOVERY_PASS__CLOSE_HOLDER_BRANCH'),
        'invariants': {'feature_schema_read_before_outcomes': True, 'only_pre_entry_PIT_features': True,
                       'no_production_write': True, 'no_frontend_write': True, 'no_watchlist_write': True},
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST)},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v403_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
