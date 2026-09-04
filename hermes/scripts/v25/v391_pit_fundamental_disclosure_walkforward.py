#!/usr/bin/env python3
"""V391 no-write walk-forward audit of the predeclared V389 FUNDAMENTAL_POSITIVE state.

No event title, event window, entry, stop, target, or outcome rule is fitted here.
It only tests whether the already-frozen V389 five-day disclosure state remains
useful in chronological out-of-sample slices of the V381 true-MTF replay.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
V390 = AUD / 'v390_pit_disclosure_exact_window_outcome_replay_latest.json'
OUT = AUD / f'v391_pit_fundamental_disclosure_walkforward_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v391_pit_fundamental_disclosure_walkforward_latest.json'
STATE = 'FUNDAMENTAL_POSITIVE'
SPLITS = (
    ('WF_2023_TO_2024', ('2023',), ('2024',)),
    ('WF_2023_2024_TO_2025', ('2023', '2024'), ('2025',)),
    ('WF_2023_2025_TO_2026', ('2023', '2024', '2025'), ('2026',)),
)


def stats(rows: list[dict]) -> dict:
    pnl = [float(row['pnl_pct']) for row in rows]
    return {
        'n': len(rows),
        'wr': round(100 * sum(value > 0 for value in pnl) / len(pnl), 4) if pnl else 0,
        'avg_pnl': round(sum(pnl) / len(pnl), 4) if pnl else 0,
        'sl_pct': round(100 * sum(row['exit_reason'] == 'SL_HIT' for row in rows) / len(rows), 4) if rows else 0,
    }


def select(rows: list[dict], years: tuple[str, ...], state: str | None = None) -> list[dict]:
    return [row for row in rows if row['entry_date'][:4] in years and (state is None or row['pit_disclosure_state'] == state)]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads(V390.read_text())
    if report['decision'] != 'NO_CONTEXT_INFORMATION__EXACT_WINDOW_DISCLOSURE_BRANCH_CLOSED':
        raise RuntimeError('V390 exact-window context decision changed; inspect it before this audit')
    with Path(report['artifacts']['rows']).open(newline='') as handle:
        rows = list(csv.DictReader(handle))
    fundamental = [row for row in rows if row['pit_disclosure_state'] == STATE]
    walk_forward = []
    for label, train_years, test_years in SPLITS:
        train_all, test_all = select(rows, train_years), select(rows, test_years)
        train_state, test_state = select(rows, train_years, STATE), select(rows, test_years, STATE)
        train_base, test_base = stats(train_all), stats(test_all)
        train_candidate, test_candidate = stats(train_state), stats(test_state)
        checks = {
            'test_n>=40': test_candidate['n'] >= 40,
            'test_wr_uplift>=5pp': test_candidate['wr'] - test_base['wr'] >= 5,
            'test_avg_uplift>=1pp': test_candidate['avg_pnl'] - test_base['avg_pnl'] >= 1,
            'test_minimum_economic_positive': test_candidate['avg_pnl'] > 0,
        }
        walk_forward.append({
            'label': label, 'train_years': list(train_years), 'test_years': list(test_years),
            'train_baseline': train_base, 'train_fundamental_positive': train_candidate,
            'test_baseline': test_base, 'test_fundamental_positive': test_candidate,
            'test_uplift': {
                'wr_pp': round(test_candidate['wr'] - test_base['wr'], 4),
                'avg_pnl_pp': round(test_candidate['avg_pnl'] - test_base['avg_pnl'], 4),
                'sl_pp': round(test_candidate['sl_pct'] - test_base['sl_pct'], 4),
            },
            'checks': checks,
            'passes_research_stability': all(checks.values()),
        })
    gate = {
        'total_n>=300': len(fundamental) >= 300,
        'each_year_n>=40': all(len(select(rows, (year,), STATE)) >= 40 for year in ('2023', '2024', '2025', '2026')),
        'all_predeclared_walkforward_splits_pass': all(item['passes_research_stability'] for item in walk_forward),
        'source_state_is_exact_window_pit': all(row['feature_cutoff'] == row['hold_time'] and row['window_days'] == '5' for row in fundamental),
    }
    result = {
        'version': 'V391_PIT_FUNDAMENTAL_DISCLOSURE_WALKFORWARD_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'contract': 'V389 exact five-day FUNDAMENTAL_POSITIVE state, frozen before outcomes; chronological evaluation only; no fitted thresholds or candidate regeneration',
        'baseline_all': stats(rows),
        'fundamental_positive_all': stats(fundamental),
        'fundamental_by_year': {year: stats(select(rows, (year,), STATE)) for year in ('2023', '2024', '2025', '2026')},
        'walk_forward': walk_forward,
        'research_gate': gate,
        'decision': 'DISCLOSURE_CONTEXT_RESEARCH_STABLE__SEPARATE_CANDIDATE_GENERATOR_REQUIRED' if all(gate.values()) else 'FUNDAMENTAL_DISCLOSURE_ASSOCIATION_REAL_BUT_INSUFFICIENT_FOR_PROMOTION__BRANCH_CLOSED',
        'artifacts': {'rows_source': report['artifacts']['rows'], 'latest': str(LATEST)},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v391_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
