#!/usr/bin/env python3
"""V383 no-write outcome replay of V382's frozen PIT participation states.

This is a diagnostic information test, not a selector search: all three states
predeclared by V382 are reported without parameter fitting.
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
V382 = AUD / 'v382_pit_cross_sectional_participation_gate_latest.json'
OUT = AUD / f'v383_pit_participation_outcome_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v383_pit_participation_outcome_replay_latest.json'
STATES = ('BROAD_RISK_ON', 'BROAD_MIXED', 'BROAD_RISK_OFF')


def metrics(rows: list[dict]) -> dict:
    by_year = defaultdict(list)
    for r in rows:
        by_year[r['entry_date'][:4]].append(float(r['pnl_pct']))
    yearly = {year: {'n': len(x), 'wr': round(sum(v > 0 for v in x) / len(x) * 100, 4),
                     'avg_pnl': round(sum(x) / len(x), 4)} for year, x in sorted(by_year.items())}
    pnl = [float(r['pnl_pct']) for r in rows]
    return {'n': len(rows), 'wr': round(sum(v > 0 for v in pnl) / len(pnl) * 100, 4) if pnl else 0,
            'avg_pnl': round(sum(pnl) / len(pnl), 4) if pnl else 0,
            'sl_pct': round(sum(r['exit_reason'] == 'SL_HIT' for r in rows) / len(rows) * 100, 4) if rows else 0,
            'yearly': yearly, 'min_year_n': min((x['n'] for x in yearly.values()), default=0),
            'min_year_wr': min((x['wr'] for x in yearly.values()), default=0)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    gate = json.loads(V382.read_text())
    if gate['decision'] != 'PIT_CONTEXT_DATA_GATE_PASS__OUTCOME_BLIND_REPLAY_ALLOWED':
        raise RuntimeError('V382 PIT data gate did not pass')
    snapshots = {}
    with open(gate['artifacts']['snapshots'], newline='') as h:
        for r in csv.DictReader(h):
            snapshots[r['hold_time']] = r
    report381 = json.loads(V381.read_text())
    with open(report381['artifacts']['trades'], newline='') as h:
        trades = list(csv.DictReader(h))
    rows = []
    for r in trades:
        s = snapshots.get(r['hold_time'])
        if s:
            rows.append({**r, **{k: s[k] for k in ('coverage', 'prior_close_up_pct', 'prior_close_median_pct',
                                                     'prior_close_p80_pct', 'intraday_up_pct',
                                                     'pit_participation_state', 'feature_cutoff')}})
    groups = {state: [r for r in rows if r['pit_participation_state'] == state] for state in STATES}
    result = {state: metrics(groups[state]) for state in STATES}
    baseline = metrics(rows)
    # This is deliberately lower than production promotion. It merely detects a
    # genuine context signal worth re-running at candidate level.
    discovery_gate = {}
    for state, m in result.items():
        discovery_gate[state] = {'n>=300': m['n'] >= 300, 'each_year_n>=40': m['min_year_n'] >= 40,
                                 'wr_uplift>=5pp': m['wr'] - baseline['wr'] >= 5,
                                 'avg_pnl_uplift>=1pp': m['avg_pnl'] - baseline['avg_pnl'] >= 1,
                                 'min_year_wr_uplift>=3pp': m['min_year_wr'] - baseline['min_year_wr'] >= 3}
    promising = [state for state, checks in discovery_gate.items() if all(checks.values())]
    fields = list(rows[0]) if rows else ['symbol']
    with (OUT / 'v383_rows.csv').open('w', newline='') as h:
        w = csv.DictWriter(h, fieldnames=fields); w.writeheader(); w.writerows(rows)
    report = {'version': 'V383_PIT_PARTICIPATION_OUTCOME_REPLAY_NO_WRITE',
              'generated_at': datetime.now().isoformat(timespec='seconds'),
              'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
              'contract': 'V382 predeclared equal-weighted market participation state frozen at hold close; V381 next-60m-open executions are only bucketed afterward; no threshold fitting or candidate creation',
              'baseline': baseline, 'states': result, 'discovery_gate': discovery_gate,
              'decision': 'CONTEXT_INFORMATION_FOUND__CANDIDATE_LEVEL_REPLAY_REQUIRED' if promising else 'NO_CONTEXT_INFORMATION__CROSS_SECTIONAL_STATE_BRANCH_CLOSED',
              'promising_states': promising,
              'audit': {'v381_rows': len(trades), 'joined_rows': len(rows), 'unjoined_rows': len(trades) - len(rows),
                        'feature_time_not_after_hold': all(r['feature_cutoff'] == r['hold_time'] for r in rows),
                        'predeclared_state_counts': dict(Counter(r['pit_participation_state'] for r in rows))},
              'artifacts': {'rows': str(OUT / 'v383_rows.csv'), 'latest': str(LATEST)}}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v383_report.json').write_text(text); LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
