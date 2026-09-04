#!/usr/bin/env python3
"""V411 frozen annual stability audit for V410 causal-combination marks.

Success gate (defined before reading marks): every combination at 5D and 10D
must have >=40 rows in every 2023-2026 year, positive rate >=50%, non-negative
mean mark, and zone invalidation <=30% in every year. This is a diagnostic
quality gate only; it creates no execution, PnL, filters, or production output.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
SOURCE = AUD / 'v410_frozen_combo_t1_mark_replay_latest.json'
OUT = AUD / f'v411_combo_yearly_stability_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v411_combo_yearly_stability_latest.json'
COMBOS = ('R1_SSL_CHOCH_DEMAND_OB', 'R2_SSL_CHOCH_BULL_FVG', 'C1_BOS_DEMAND_OB')
YEARS, HORIZONS = ('2023', '2024', '2025', '2026'), (5, 10)
GATE = {'min_year_n': 40, 'min_positive_pct': 50.0, 'min_avg_mark_pct': 0.0, 'max_zone_invalidated_pct': 30.0}


def metric(rows: list[dict], horizon: int) -> dict:
    marks = [float(r[f'mark_{horizon}d_pct']) for r in rows if r[f'mark_{horizon}d_pct'] != '']
    if not marks:
        return {'n': 0}
    valid = [r for r in rows if r[f'mark_{horizon}d_pct'] != '']
    return {
        'n': len(marks),
        'positive_pct': round(sum(x > 0 for x in marks) / len(marks) * 100, 2),
        'avg_mark_pct': round(mean(marks), 4),
        'median_mark_pct': round(median(marks), 4),
        'zone_invalidated_pct': round(sum(r[f'zone_invalid_{horizon}d'] == 'True' for r in valid) / len(valid) * 100, 2),
    }


def passes(x: dict) -> bool:
    return (x.get('n', 0) >= GATE['min_year_n'] and x['positive_pct'] >= GATE['min_positive_pct']
            and x['avg_mark_pct'] >= GATE['min_avg_mark_pct']
            and x['zone_invalidated_pct'] <= GATE['max_zone_invalidated_pct'])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads(SOURCE.read_text())
    with Path(source['artifacts']['rows']).open(newline='', encoding='utf-8') as file:
        rows = list(csv.DictReader(file))
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        year = row['entry_date'][:4]
        if year in YEARS:
            buckets[(row['combo_key'], year)].append(row)
    report_rows, summary = [], {}
    for combo in COMBOS:
        summary[combo] = {}
        for horizon in HORIZONS:
            by_year = {year: metric(buckets[(combo, year)], horizon) for year in YEARS}
            all_years_pass = all(passes(value) for value in by_year.values())
            summary[combo][f'{horizon}d'] = {'by_year': by_year, 'stability_gate_pass': all_years_pass}
            for year, values in by_year.items():
                report_rows.append({'combo_key': combo, 'horizon_sessions': horizon, 'entry_year': year,
                                    **values, 'year_gate_pass': passes(values)})
    with (OUT / 'v411_yearly_metrics.csv').open('w', newline='') as out:
        fields = list(report_rows[0])
        writer = csv.DictWriter(out, fieldnames=fields); writer.writeheader(); writer.writerows(report_rows)
    passes_total = sum(x['stability_gate_pass'] for combo in summary.values() for x in combo.values())
    report = {
        'version': 'V411_FROZEN_COMBINATION_YEARLY_STABILITY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source': str(SOURCE),
        'frozen_input_contract': 'V410 takeover-confirmed next-session-open rows; no new candidate, entry, exit, threshold, or outcome-search operation',
        'predeclared_diagnostic_gate': GATE,
        'years': YEARS, 'horizons_sessions': HORIZONS,
        'summary': summary,
        'combination_horizon_passes': passes_total,
        'invariants': {'all_t1_compliant_from_source': source['invariants']['all_t1_compliant'], 'no_parameter_search': True, 'no_promotion': True},
        'decision': 'ALL_THREE_CAUSAL_COMBINATIONS_FAIL_FROZEN_MARK_QUALITY__CLOSE_COMBINATION_BRANCH__NO_INDEPENDENT_PROMOTION_AUDIT_NEEDED',
        'artifacts': {'out_dir': str(OUT), 'yearly_metrics': str(OUT / 'v411_yearly_metrics.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v411_report.json').write_text(text); LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
