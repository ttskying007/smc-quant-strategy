#!/usr/bin/env python3
"""V390 no-write outcome replay for V389's repaired exact-window disclosure states."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes'); AUD = ROOT / 'smc_audit'
V381 = AUD / 'v381_true_mtf_raw_daily_poi_m60_replay_latest.json'
V389 = AUD / 'v389_pit_disclosure_exact_window_schema_latest.json'
OUT = AUD / f'v390_pit_disclosure_exact_window_outcome_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v390_pit_disclosure_exact_window_outcome_replay_latest.json'


def stats(rows: list[dict]) -> dict:
    values = [float(r['pnl_pct']) for r in rows]; yearly = defaultdict(list)
    for row, value in zip(rows, values): yearly[row['entry_date'][:4]].append(value)
    y = {k: {'n': len(v), 'wr': round(100 * sum(x > 0 for x in v) / len(v), 4), 'avg_pnl': round(sum(v) / len(v), 4)} for k, v in sorted(yearly.items())}
    return {'n': len(rows), 'wr': round(100 * sum(x > 0 for x in values) / len(values), 4) if values else 0,
            'avg_pnl': round(sum(values) / len(values), 4) if values else 0,
            'sl_pct': round(100 * sum(r['exit_reason'] == 'SL_HIT' for r in rows) / len(rows), 4) if rows else 0,
            'yearly': y, 'min_year_n': min((v['n'] for v in y.values()), default=0), 'min_year_wr': min((v['wr'] for v in y.values()), default=0)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads(V389.read_text())
    if source['decision'] != 'PIT_DISCLOSURE_EXACT_WINDOW_PASS__OUTCOME_REPLAY_ALLOWED': raise RuntimeError('V389 gate failed')
    with Path(source['artifacts']['features']).open(newline='') as h: features = {(r['symbol'], r['hold_time']): r for r in csv.DictReader(h)}
    base_report = json.loads(V381.read_text())
    with Path(base_report['artifacts']['trades']).open(newline='') as h: trades = list(csv.DictReader(h))
    joined = [{**row, **features[(row['symbol'], row['hold_time'])]} for row in trades]
    base = stats(joined); states = sorted({r['pit_disclosure_state'] for r in joined})
    buckets = {state: stats([r for r in joined if r['pit_disclosure_state'] == state]) for state in states}
    gate = {state: {'n>=300': v['n'] >= 300, 'each_year_n>=40': v['min_year_n'] >= 40,
                    'wr_uplift>=5pp': v['wr'] - base['wr'] >= 5, 'avg_uplift>=1pp': v['avg_pnl'] - base['avg_pnl'] >= 1,
                    'min_year_wr_uplift>=3pp': v['min_year_wr'] - base['min_year_wr'] >= 3} for state, v in buckets.items()}
    promising = [state for state, checks in gate.items() if all(checks.values())]
    with (OUT / 'v390_rows.csv').open('w', newline='') as h:
        w = csv.DictWriter(h, fieldnames=list(joined[0])); w.writeheader(); w.writerows(joined)
    result = {'version': 'V390_PIT_DISCLOSURE_EXACT_WINDOW_OUTCOME_REPLAY_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
              'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
              'contract': 'V389 exact [hold-5d, hold] static disclosure state; V381 outcomes bucketed afterward only; no fitting',
              'baseline': base, 'states': buckets, 'discovery_gate': gate, 'promising_states': promising,
              'decision': 'EXACT_WINDOW_DISCLOSURE_INFORMATION_FOUND__CANDIDATE_LEVEL_REPLAY_REQUIRED' if promising else 'NO_CONTEXT_INFORMATION__EXACT_WINDOW_DISCLOSURE_BRANCH_CLOSED',
              'audit': {'v381_rows': len(trades), 'feature_join_complete': len(joined) == len(trades),
                        'feature_time_not_after_hold': all(r['feature_cutoff'] == r['hold_time'] for r in joined),
                        'state_counts': dict(Counter(r['pit_disclosure_state'] for r in joined))},
              'artifacts': {'rows': str(OUT / 'v390_rows.csv'), 'latest': str(LATEST)}}
    text = json.dumps(result, ensure_ascii=False, indent=2); (OUT / 'v390_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__': main()
