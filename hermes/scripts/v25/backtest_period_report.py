#!/usr/bin/env python3
"""Reusable, outcome-only reporting for frozen backtest ledgers.

This module never selects signals or changes a replay. It consumes an already
materialized closed-trade ledger and emits reproducible yearly/monthly metrics.
Use it after every future frozen replay so aggregation is visible without
turning period performance into a selector.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

METRIC_SCHEMA = 'SMC_BACKTEST_PERIOD_REPORT_V1'


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _date(value: Any) -> str:
    return ''.join(ch for ch in str(value or '') if ch.isdigit())[:8]


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnl = [_num(row.get('net_pnl_pct', row.get('pnl_pct'))) for row in rows]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    gross_profit, gross_loss = sum(wins), abs(sum(losses))
    return {
        'trade_count': len(rows),
        'symbol_count': len({str(row.get('symbol') or '') for row in rows if row.get('symbol')}),
        'win_count': len(wins),
        'loss_count': len(losses),
        'flat_count': len(rows) - len(wins) - len(losses),
        'gross_wr_pct': round(100 * len(wins) / len(rows), 4) if rows else 0.0,
        'avg_net_pnl_pct': round(sum(pnl) / len(rows), 4) if rows else 0.0,
        'total_net_pnl_pct': round(sum(pnl), 4),
        'avg_win_pct': round(sum(wins) / len(wins), 4) if wins else 0.0,
        'avg_loss_pct': round(sum(losses) / len(losses), 4) if losses else 0.0,
        'payoff_rr': round((sum(wins) / len(wins)) / abs(sum(losses) / len(losses)), 4) if wins and losses else 0.0,
        'profit_factor': round(gross_profit / gross_loss, 4) if gross_loss else 0.0,
        'avg_hold_bars': round(sum(_num(row.get('hold_bars')) for row in rows) / len(rows), 4) if rows else 0.0,
        't1_violation_count': sum(str(row.get('same_day_exit_violation', row.get('t1_violation', ''))).lower() == 'true' for row in rows),
        'exit_counts': dict(sorted(Counter(str(row.get('reason') or row.get('exit_reason') or 'UNKNOWN') for row in rows).items())),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(rows[0]) if rows else ['period']
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_period_report(rows: list[dict[str, Any]], *, engine: str, input_ledger: str, contract: str = '') -> dict[str, Any]:
    closed = [row for row in rows if str(row.get('status') or 'CLOSED') == 'CLOSED']
    dated = [row for row in closed if _date(row.get('entry_date'))]
    by_year: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in dated:
        entry_day = _date(row.get('entry_date'))
        by_year[entry_day[:4]].append(row)
        by_month[entry_day[:6]].append(row)

    yearly_rows = [{'entry_year': key, **metrics(value)} for key, value in sorted(by_year.items())]
    monthly_rows = [{'entry_month': key, **metrics(value)} for key, value in sorted(by_month.items())]
    negative_months = [row['entry_month'] for row in monthly_rows if row['avg_net_pnl_pct'] < 0]
    return {
        'schema_version': METRIC_SCHEMA,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': engine,
        'report_only': True,
        'production_write': False,
        'watchlist_write': False,
        'input_ledger': input_ledger,
        'entry_date_metric_contract': 'Every closed row is grouped by strict executable entry_date; no period result may be used as a selector or replay parameter.',
        'frozen_execution_contract': contract,
        'closed_rows_read': len(closed),
        'dated_closed_rows': len(dated),
        'overall': metrics(dated),
        'yearly': yearly_rows,
        'monthly': monthly_rows,
        'monthly_stability': {
            'months_observed': len(monthly_rows),
            'negative_avg_net_month_count': len(negative_months),
            'negative_avg_net_months': negative_months,
            'lowest_avg_net_month': min(monthly_rows, key=lambda row: row['avg_net_pnl_pct']) if monthly_rows else None,
            'highest_avg_net_month': max(monthly_rows, key=lambda row: row['avg_net_pnl_pct']) if monthly_rows else None,
        },
        'invariants': {
            'closed_rows_only': len(closed) == len(rows),
            'all_rows_have_entry_date': len(dated) == len(closed),
            'periods_derived_after_replay_only': True,
            'no_period_filtering_or_parameter_search': True,
        },
    }


def write_period_reports(rows: list[dict[str, Any]], *, out_dir: Path, stem: str, engine: str, input_ledger: str, contract: str = '') -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_period_report(rows, engine=engine, input_ledger=input_ledger, contract=contract)
    yearly_path = out_dir / f'{stem}_yearly_metrics.csv'
    monthly_path = out_dir / f'{stem}_monthly_metrics.csv'
    json_path = out_dir / f'{stem}_period_metrics.json'
    _write_csv(yearly_path, report['yearly'])
    _write_csv(monthly_path, report['monthly'])
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return {'json': str(json_path), 'yearly_csv': str(yearly_path), 'monthly_csv': str(monthly_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate immutable yearly/monthly metrics from a closed trade CSV ledger.')
    parser.add_argument('--trades-csv', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--stem', default='backtest')
    parser.add_argument('--engine', required=True)
    parser.add_argument('--contract', default='')
    args = parser.parse_args()
    source = Path(args.trades_csv)
    with source.open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    artifacts = write_period_reports(rows, out_dir=Path(args.out_dir), stem=args.stem, engine=args.engine, input_ledger=str(source), contract=args.contract)
    print(json.dumps({'ok': True, 'artifacts': artifacts, 'summary': build_period_report(rows, engine=args.engine, input_ledger=str(source), contract=args.contract)['monthly_stability']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
