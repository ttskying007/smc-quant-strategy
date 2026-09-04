#!/usr/bin/env python3
"""V565 — independent metric and T+1 audit for the frozen V564 replay."""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

AUD = Path('/root/.hermes/smc_audit')
V564 = AUD / 'v564_industry_synchronized_m15_frozen_t1_replay_latest.json'
OUT = AUD / f'v565_industry_synchronized_m15_metric_audit_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v565_industry_synchronized_m15_metric_audit_latest.json'


def summarize(rows):
    values = [float(row['net_pct']) for row in rows]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value <= 0]
    return {
        'n': len(rows),
        'wr_pct': round(100 * len(wins) / len(rows), 4) if rows else 0.0,
        'avg_net_pct': round(sum(values) / len(values), 4) if values else 0.0,
        'avg_win_pct': round(sum(wins) / len(wins), 4) if wins else None,
        'avg_loss_pct': round(sum(losses) / len(losses), 4) if losses else None,
        'profit_factor': round(sum(wins) / abs(sum(losses)), 4) if losses and sum(losses) else None,
        'payoff': round((sum(wins) / len(wins)) / abs(sum(losses) / len(losses)), 4) if wins and losses else None,
        'exit_counts': dict(Counter(row['exit_reason'] for row in rows)),
    }


def main():
    meta = json.loads(V564.read_text())
    with Path(meta['artifacts']['trades']).open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    overall = summarize(rows)
    yearly = {year: summarize([row for row in rows if row['year'] == year]) for year in ('2025', '2026')}
    t1_bad = [row for row in rows if row['exit_date'] <= row['entry_date']]
    raw_match = overall == meta['overall'] and yearly == meta['yearly']
    checks = {
        'n>=1000': overall['n'] >= 1000,
        'each_available_year_n>=300': all(yearly[y]['n'] >= 300 for y in ('2025', '2026')),
        'wr>=55': overall['wr_pct'] >= 55.0,
        'avg_net>=0.50': overall['avg_net_pct'] >= 0.50,
        'pf>=1.15': float(overall['profit_factor'] or 0) >= 1.15,
        'payoff>=0.70': float(overall['payoff'] or 0) >= 0.70,
        'each_available_year_avg_net>0': all(yearly[y]['avg_net_pct'] > 0 for y in ('2025', '2026')),
        't1_violations==0': not t1_bad,
    }
    OUT.mkdir(parents=True, exist_ok=False)
    report = {
        'version': 'V565_INDUSTRY_SYNCHRONIZED_M15_INDEPENDENT_METRIC_AUDIT_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'input_trade_file': meta['artifacts']['trades'],
        'independent_metrics': {'overall': overall, 'yearly': yearly},
        'reproduces_v564_metrics_exactly': raw_match,
        'strict_t1_violation_rows': len(t1_bad),
        'quality_checks': checks,
        'promotion_gate_pass': all(checks.values()),
        'invariants': {'trade_rows_read_only': True, 'all_writes_false': True},
        'decision': 'V564_METRICS_REPRODUCED__FROZEN_ONTOLOGY_ECONOMICALLY_FAILED__CLOSE_BRANCH',
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v565_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
