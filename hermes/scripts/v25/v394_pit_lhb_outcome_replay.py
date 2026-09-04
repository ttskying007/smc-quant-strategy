#!/usr/bin/env python3
"""V394 no-write replay of the predeclared V393 PIT 龙虎榜 states."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
V381 = AUD / 'v381_true_mtf_raw_daily_poi_m60_replay_latest.json'
V393 = AUD / 'v393_pit_lhb_availability_latest.json'
OUT = AUD / f'v394_pit_lhb_outcome_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v394_pit_lhb_outcome_replay_latest.json'
STATES = ('LHB_POSITIVE', 'LHB_NEGATIVE', 'NO_LHB')


def stats(rows: list[dict]) -> dict:
    years: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        years[row['entry_date'][:4]].append(float(row['pnl_pct']))
    yearly = {year: {'n': len(values), 'wr': round(sum(x > 0 for x in values) * 100 / len(values), 4),
                     'avg_pnl': round(sum(values) / len(values), 4)} for year, values in sorted(years.items())}
    pnl = [float(row['pnl_pct']) for row in rows]
    return {
        'n': len(rows), 'wr': round(sum(x > 0 for x in pnl) * 100 / len(pnl), 4) if pnl else 0,
        'avg_pnl': round(sum(pnl) / len(pnl), 4) if pnl else 0,
        'sl_pct': round(sum(row['exit_reason'] == 'SL_HIT' for row in rows) * 100 / len(rows), 4) if rows else 0,
        'yearly': yearly, 'min_year_n': min((x['n'] for x in yearly.values()), default=0),
        'min_year_wr': min((x['wr'] for x in yearly.values()), default=0),
    }


def state(row: dict) -> str:
    events, net = int(row['lhb_prior_events']), float(row['lhb_prior_net_amt'])
    if events == 0:
        return 'NO_LHB'
    return 'LHB_POSITIVE' if net > 0 else 'LHB_NEGATIVE'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads(V393.read_text())
    if source['decision'] != 'PIT_LHB_AVAILABILITY_PASS__OUTCOME_BLIND_REPLAY_ALLOWED':
        raise RuntimeError('V393 availability gate failed')
    with Path(source['artifacts']['features']).open(newline='') as handle:
        features = {(row['symbol'], row['hold_time']): {**row, 'pit_lhb_state': state(row)} for row in csv.DictReader(handle)}
    v381 = json.loads(V381.read_text())
    with Path(v381['artifacts']['trades']).open(newline='') as handle:
        trades = [{**row, **features[(row['symbol'], row['hold_time'])]} for row in csv.DictReader(handle)]
    baseline = stats(trades)
    groups = {name: [row for row in trades if row['pit_lhb_state'] == name] for name in STATES}
    results = {name: stats(rows) for name, rows in groups.items()}
    checks = {name: {
        'n>=300': item['n'] >= 300,
        'each_year_n>=40': item['min_year_n'] >= 40,
        'wr_uplift>=5pp': item['wr'] - baseline['wr'] >= 5,
        'avg_uplift>=1pp': item['avg_pnl'] - baseline['avg_pnl'] >= 1,
        'min_year_wr_uplift>=3pp': item['min_year_wr'] - baseline['min_year_wr'] >= 3,
    } for name, item in results.items()}
    promising = [name for name, item in checks.items() if all(item.values())]
    row_path = OUT / 'v394_rows.csv'
    with row_path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(trades[0])); writer.writeheader(); writer.writerows(trades)
    report = {
        'version': 'V394_PIT_LHB_OUTCOME_REPLAY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'contract': 'V393 frozen strictly-prior-day 30-calendar-day LHB state; V381 executions bucketed only afterward; no threshold fitting',
        'baseline': baseline, 'states': results, 'discovery_gate': checks,
        'decision': 'LHB_CONTEXT_INFORMATION_FOUND__CANDIDATE_LEVEL_REPLAY_REQUIRED' if promising else 'NO_CONTEXT_INFORMATION__LHB_BRANCH_CLOSED',
        'promising_states': promising,
        'audit': {'v381_rows': len(trades), 'feature_join_complete': len(trades) == 4832,
                  'feature_time_not_after_hold': all(row['feature_cutoff'] == row['hold_time'] for row in trades),
                  'state_counts': dict(Counter(row['pit_lhb_state'] for row in trades))},
        'artifacts': {'rows': str(row_path), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v394_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__':
    main()
