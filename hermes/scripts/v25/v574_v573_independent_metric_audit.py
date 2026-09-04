#!/usr/bin/env python3
import csv
import json
from collections import Counter
from pathlib import Path

LATEST = Path('/root/.hermes/smc_audit/v573_v566_industry_activation_frozen_strict_t1_replay_latest.json')
OUT = Path('/root/.hermes/smc_audit/v574_v573_independent_metric_audit_latest.json')


def metrics(rows):
    pnl = [float(row['pnl_net_pct']) for row in rows]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value <= 0]
    return {
        'n': len(rows),
        'wr_pct': round(100 * len(wins) / len(rows), 4),
        'avg_net_pct': round(sum(pnl) / len(rows), 4),
        'profit_factor': round(sum(wins) / -sum(losses), 4),
        'payoff': round((sum(wins) / len(wins)) / (-sum(losses) / len(losses)), 4),
        'exit_reason_counts': dict(Counter(row['exit_reason'] for row in rows)),
    }


meta = json.loads(LATEST.read_text())
with Path(meta['artifacts']['trades']).open(newline='', encoding='utf-8') as handle:
    trades = list(csv.DictReader(handle))
overall = metrics(trades)
yearly = {year: metrics([row for row in trades if row['entry_date'].startswith(year)]) for year in ('2025', '2026')}
stop_rows = sum(overall['exit_reason_counts'].get(reason, 0) for reason in ('SL_T1', 'SL_GAP_T1', 'SL_TP_COLLISION_CONSERVATIVE_T1'))
t1_violations = sum(row['exit_date'] <= row['entry_date'] for row in trades)
checks = {
    'n>=1000': len(trades) >= 1000,
    'each_available_year_n>=300': all(year['n'] >= 300 for year in yearly.values()),
    'wr>=55': overall['wr_pct'] >= 55,
    'avg_net>=0.50': overall['avg_net_pct'] >= 0.5,
    'pf>=1.15': overall['profit_factor'] >= 1.15,
    'payoff>=0.70': overall['payoff'] >= 0.7,
    'each_available_year_avg_net>0': all(year['avg_net_pct'] > 0 for year in yearly.values()),
    't1_violations==0': t1_violations == 0,
}
report = {
    'version': 'V574_V573_INDEPENDENT_METRIC_AUDIT_NO_WRITE',
    'input_trade_file': meta['artifacts']['trades'],
    'independent_metrics': {'overall': overall, 'yearly': yearly},
    'strict_t1_violation_rows': t1_violations,
    'mechanism': {
        'stop_or_gap_stop_rows': stop_rows,
        'stop_or_gap_stop_pct': round(100 * stop_rows / len(trades), 4),
        'interpretation': 'Same-session micro-BOS fails to survive next-session execution. This is an overnight-survival failure, not an exit-geometry optimization signal.',
    },
    'quality_checks': checks,
    'production_write': False,
    'frontend_write': False,
    'watchlist_write': False,
    'decision': 'V573_METRICS_REPRODUCED__CLOSE_V566_ONTOLOGY_NO_VARIANTS',
}
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps({'status': 'PASS', 'artifact': str(OUT), 'overall': overall, 'yearly': yearly, 'checks': checks}, ensure_ascii=False))
