#!/usr/bin/env python3
"""V388 no-write outcome replay for V387's frozen PIT disclosure states."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
V381 = AUD / 'v381_true_mtf_raw_daily_poi_m60_replay_latest.json'
V387 = AUD / 'v387_pit_disclosure_event_schema_latest.json'
OUT = AUD / f'v388_pit_disclosure_outcome_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v388_pit_disclosure_outcome_replay_latest.json'


def stats(rows: list[dict]) -> dict:
    values = [float(row['pnl_pct']) for row in rows]
    yearly: dict[str, list[float]] = defaultdict(list)
    for row, value in zip(rows, values):
        yearly[row['entry_date'][:4]].append(value)
    by_year = {year: {'n': len(v), 'wr': round(100 * sum(x > 0 for x in v) / len(v), 4),
                      'avg_pnl': round(sum(v) / len(v), 4)} for year, v in sorted(yearly.items())}
    return {'n': len(rows), 'wr': round(100 * sum(x > 0 for x in values) / len(values), 4) if values else 0,
            'avg_pnl': round(sum(values) / len(values), 4) if values else 0,
            'sl_pct': round(100 * sum(row['exit_reason'] == 'SL_HIT' for row in rows) / len(rows), 4) if rows else 0,
            'yearly': by_year, 'min_year_n': min((item['n'] for item in by_year.values()), default=0),
            'min_year_wr': min((item['wr'] for item in by_year.values()), default=0)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    schema = json.loads(V387.read_text())
    if schema['decision'] != 'PIT_DISCLOSURE_SCHEMA_PASS__OUTCOME_BLIND_REPLAY_ALLOWED':
        raise RuntimeError('V387 PIT event schema did not pass')
    with Path(schema['artifacts']['features']).open(newline='') as handle:
        features = {(row['symbol'], row['hold_time']): row for row in csv.DictReader(handle)}
    report = json.loads(V381.read_text())
    with Path(report['artifacts']['trades']).open(newline='') as handle:
        trades = list(csv.DictReader(handle))
    joined = [{**trade, **features[(trade['symbol'], trade['hold_time'])]} for trade in trades]
    baseline = stats(joined)
    states = sorted({row['pit_disclosure_state'] for row in joined})
    buckets = {state: stats([row for row in joined if row['pit_disclosure_state'] == state]) for state in states}
    # Frozen discovery bar: no candidate rebuild unless effect is broad, economic, and stable.
    gate = {state: {'n>=300': value['n'] >= 300, 'each_year_n>=40': value['min_year_n'] >= 40,
                    'wr_uplift>=5pp': value['wr'] - baseline['wr'] >= 5,
                    'avg_uplift>=1pp': value['avg_pnl'] - baseline['avg_pnl'] >= 1,
                    'min_year_wr_uplift>=3pp': value['min_year_wr'] - baseline['min_year_wr'] >= 3}
            for state, value in buckets.items()}
    promising = [state for state, checks in gate.items() if all(checks.values())]
    with (OUT / 'v388_rows.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(joined[0])); writer.writeheader(); writer.writerows(joined)
    result = {'version': 'V388_PIT_DISCLOSURE_OUTCOME_REPLAY_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
              'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
              'contract': 'V387 frozen disclosure state at hold time; V381 trades bucketed only afterward; no title/window/threshold fitting',
              'baseline': baseline, 'states': buckets, 'discovery_gate': gate, 'promising_states': promising,
              'decision': 'DISCLOSURE_CONTEXT_INFORMATION_FOUND__CANDIDATE_LEVEL_REPLAY_REQUIRED' if promising else 'NO_CONTEXT_INFORMATION__DISCLOSURE_BRANCH_CLOSED',
              'audit': {'v381_rows': len(trades), 'feature_join_complete': len(joined) == len(trades),
                        'feature_time_not_after_hold': all(row['feature_cutoff'] == row['hold_time'] for row in joined),
                        'state_counts': dict(Counter(row['pit_disclosure_state'] for row in joined))},
              'artifacts': {'rows': str(OUT / 'v388_rows.csv'), 'latest': str(LATEST)}}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v388_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__':
    main()
