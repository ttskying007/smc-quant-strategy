#!/usr/bin/env python3
"""Read-only attribution of the single frozen V541 replay failure.

This script does not select a strategy or retest alternatives. It partitions the
already-frozen V541 closed trades to determine whether failure sits in execution
risk, structural target distance, time regime, causal delay, or a small group of
symbols. All panels are descriptive and retain every closed trade.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Callable

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
V541 = AUDIT / 'v541_sina_m15_ssl_bos_fvg_frozen_t1_replay_latest.json'
OUT = AUDIT / f'v542_sina_m15_v541_failure_attribution_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v542_sina_m15_v541_failure_attribution_latest.json'
MIN_PANEL_N = 300


def number(value: str) -> float:
    return float(value)


def stamp(value: str) -> datetime:
    return datetime.strptime(value, '%Y%m%d%H%M%S')


def metric(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnl = [number(row['net_pnl_pct']) for row in rows]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    return {
        'n': len(rows),
        'wr_pct': round(100 * len(wins) / len(rows), 3) if rows else 0.0,
        'avg_net_pct': round(mean(pnl), 4) if pnl else 0.0,
        'pf': round(sum(wins) / abs(sum(losses)), 4) if losses else 0.0,
        'payoff': round(mean(wins) / abs(mean(losses)), 4) if wins and losses else 0.0,
        'avg_mfe_pct': round(mean(number(row['mfe_pct']) for row in rows), 4) if rows else 0.0,
        'avg_mae_pct': round(mean(number(row['mae_pct']) for row in rows), 4) if rows else 0.0,
        'exits': dict(Counter(row['reason'] for row in rows)),
    }


def interval_hours(row: dict[str, str], start: str, end: str) -> float:
    return (stamp(row[end]) - stamp(row[start])).total_seconds() / 3600.0


def binned(rows: list[dict[str, Any]], name: str, key: Callable[[dict[str, Any]], str]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[key(row)].append(row)
    report = [{'bucket': bucket, **metric(group)} for bucket, group in sorted(groups.items())]
    return [row for row in report if row['n'] >= MIN_PANEL_N]


def quantile_bucket(value: float, cuts: tuple[float, ...], labels: tuple[str, ...]) -> str:
    for cut, label in zip(cuts, labels):
        if value < cut:
            return label
    return labels[-1]


def main() -> None:
    source = json.loads(V541.read_text())
    if source['decision'] != 'V541_PARTIAL_RANGE_RESEARCH_FAIL__CLOSE_OBJECT':
        raise RuntimeError('V541 must be a closed failed research object before attribution')
    trade_path = Path(source['artifacts']['trades'])
    with trade_path.open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        entry = number(row['entry_price'])
        row['_stop_risk_pct'] = (entry - number(row['stop'])) / entry * 100.0
        row['_target_dist_pct'] = (number(row['target']) - entry) / entry * 100.0
        row['_mfe_r'] = number(row['mfe_pct']) / row['_stop_risk_pct']
        row['_mae_r'] = number(row['mae_pct']) / row['_stop_risk_pct']
        row['_sweep_to_bos_h'] = interval_hours(row, 'sweep_time', 'bos_time')
        row['_bos_to_fvg_h'] = interval_hours(row, 'bos_time', 'fvg_time')
        row['_fvg_to_reclaim_h'] = interval_hours(row, 'fvg_time', 'reclaim_time')
        row['_sweep_to_entry_h'] = interval_hours(row, 'sweep_time', 'entry_time')
    OUT.mkdir(parents=True, exist_ok=False)
    panels = {
        'year': binned(rows, 'year', lambda row: row['entry_date'][:4]),
        'entry_clock': binned(rows, 'entry_clock', lambda row: row['entry_time'][8:12]),
        'exit_reason': binned(rows, 'exit_reason', lambda row: row['reason']),
        'stop_risk_pct': binned(rows, 'stop_risk_pct', lambda row: quantile_bucket(row['_stop_risk_pct'], (1.0, 2.0, 3.0, 5.0), ('<1%', '1-2%', '2-3%', '3-5%', '>=5%'))),
        'target_distance_pct': binned(rows, 'target_distance_pct', lambda row: quantile_bucket(row['_target_dist_pct'], (2.0, 4.0, 6.0, 10.0), ('<2%', '2-4%', '4-6%', '6-10%', '>=10%'))),
        'planned_rr': binned(rows, 'planned_rr', lambda row: quantile_bucket(number(row['planned_rr']), (2.0, 3.0, 5.0, 8.0), ('1.5-2R', '2-3R', '3-5R', '5-8R', '>=8R'))),
        'sweep_to_bos_hours': binned(rows, 'sweep_to_bos_hours', lambda row: quantile_bucket(row['_sweep_to_bos_h'], (1.0, 4.0, 24.0, 72.0), ('<1h', '1-4h', '4-24h', '1-3d', '>=3d'))),
        'fvg_to_reclaim_hours': binned(rows, 'fvg_to_reclaim_hours', lambda row: quantile_bucket(row['_fvg_to_reclaim_h'], (1.0, 4.0, 24.0, 72.0), ('<1h', '1-4h', '4-24h', '1-3d', '>=3d'))),
    }
    symbol_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        symbol_groups[row['symbol']].append(row)
    symbol_panel = [{'symbol': symbol, **metric(group)} for symbol, group in symbol_groups.items() if len(group) >= 20]
    symbol_panel.sort(key=lambda row: row['avg_net_pct'])
    worst_symbols = symbol_panel[:30]
    best_symbols = list(reversed(symbol_panel[-30:]))
    top100 = sorted(symbol_groups.items(), key=lambda item: len(item[1]), reverse=True)[:100]
    top100_rows = [row for _, group in top100 for row in group]
    concentration = {
        'eligible_symbols_n20': len(symbol_panel),
        'worst30_trade_share_pct': round(100 * sum(row['n'] for row in worst_symbols) / len(rows), 4),
        'worst30_net_pnl_contribution_pct': round(100 * sum(row['n'] * row['avg_net_pct'] for row in worst_symbols) / sum(number(row['net_pnl_pct']) for row in rows), 4),
        'top100_frequency_trade_share_pct': round(100 * len(top100_rows) / len(rows), 4),
        'top100_frequency_metrics': metric(top100_rows),
    }
    mechanics = {
        'mfe_ge_1R_pct': round(100 * sum(row['_mfe_r'] >= 1 for row in rows) / len(rows), 4),
        'mfe_ge_1_5R_pct': round(100 * sum(row['_mfe_r'] >= 1.5 for row in rows) / len(rows), 4),
        'mfe_ge_planned_target_pct': round(100 * sum(number(row['mfe_pct']) >= row['_target_dist_pct'] for row in rows) / len(rows), 4),
        'mae_below_minus_1R_pct': round(100 * sum(row['_mae_r'] <= -1 for row in rows) / len(rows), 4),
        'time80_positive_pct': round(100 * sum(row['reason'] == 'TIME80' and number(row['net_pnl_pct']) > 0 for row in rows) / max(1, sum(row['reason'] == 'TIME80' for row in rows)), 4),
    }
    report = {
        'version': 'V542_SINA_M15_V541_FAILURE_ATTRIBUTION_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'source_v541': str(V541),
        'trade_source': str(trade_path),
        'source_scope': source['scope'],
        'closed_trade_count': len(rows),
        'overall': metric(rows),
        'mechanics': mechanics,
        'panels_min_n': MIN_PANEL_N,
        'panels': panels,
        'concentration': concentration,
        'worst_eligible_symbols': worst_symbols,
        'best_eligible_symbols': best_symbols,
        'interpretation_guard': 'Descriptive partitions only. No winning bucket may be promoted without a separately preregistered, outcome-blind seed/oracle/replay chain.',
        'decision': 'V542_ATTRIBUTION_COMPLETE__HYPOTHESIS_MUST_TARGET_MECHANISM_NOT_EX_POST_BUCKET',
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v542_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
