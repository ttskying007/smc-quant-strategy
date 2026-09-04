#!/usr/bin/env python3
"""Read-only mechanism attribution for the single closed V545 replay."""
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
V545 = AUDIT / 'v545_sina_m15_ssl_displacement_absorption_frozen_t1_replay_latest.json'
OUT = AUDIT / f'v546_sina_m15_v545_failure_attribution_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v546_sina_m15_v545_failure_attribution_latest.json'
MIN_N = 300


def value(row: dict[str, Any], name: str) -> float:
    return float(row[name])


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnl = [value(row, 'net_pnl_pct') for row in rows]
    wins, losses = [x for x in pnl if x > 0], [x for x in pnl if x < 0]
    return {'n': len(rows), 'wr_pct': round(100 * len(wins) / len(rows), 4) if rows else 0.0, 'avg_net_pct': round(mean(pnl), 4) if pnl else 0.0, 'pf': round(sum(wins) / abs(sum(losses)), 4) if losses else 0.0, 'payoff': round(mean(wins) / abs(mean(losses)), 4) if wins and losses else 0.0, 'avg_mfe_pct': round(mean(value(row, 'mfe_pct') for row in rows), 4) if rows else 0.0, 'avg_mae_pct': round(mean(value(row, 'mae_pct') for row in rows), 4) if rows else 0.0, 'exits': dict(Counter(row['reason'] for row in rows))}


def bucket(rows: list[dict[str, Any]], key: Callable[[dict[str, Any]], str]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[key(row)].append(row)
    return [{'bucket': label, **metrics(group)} for label, group in sorted(grouped.items()) if len(group) >= MIN_N]


def band(x: float, cuts: tuple[float, ...], names: tuple[str, ...]) -> str:
    for cut, name in zip(cuts, names):
        if x < cut:
            return name
    return names[-1]


def main() -> None:
    source = json.loads(V545.read_text())
    if source['decision'] != 'V545_PARTIAL_RANGE_RESEARCH_FAIL__CLOSE_OBJECT':
        raise RuntimeError('V545 must be a closed failed research object before attribution')
    with Path(source['artifacts']['trades']).open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        entry = value(row, 'entry_price')
        row['_risk_pct'] = (entry - value(row, 'stop')) / entry * 100.0
        row['_target_pct'] = (value(row, 'target') - entry) / entry * 100.0
        row['_mfe_r'] = value(row, 'mfe_pct') / row['_risk_pct']
        row['_mae_r'] = value(row, 'mae_pct') / row['_risk_pct']
    panels = {
        'year': bucket(rows, lambda row: row['entry_date'][:4]),
        'exit_reason': bucket(rows, lambda row: row['reason']),
        'entry_clock': bucket(rows, lambda row: row['entry_time'][8:12]),
        'planned_rr': bucket(rows, lambda row: band(value(row, 'planned_rr'), (2, 3, 5, 8), ('1.5-2R', '2-3R', '3-5R', '5-8R', '>=8R'))),
        'risk_pct': bucket(rows, lambda row: band(row['_risk_pct'], (1, 2, 3, 5), ('<1%', '1-2%', '2-3%', '3-5%', '>=5%'))),
        'target_distance_pct': bucket(rows, lambda row: band(row['_target_pct'], (2, 4, 6, 10), ('<2%', '2-4%', '4-6%', '6-10%', '>=10%'))),
    }
    mechanics = {'mfe_ge_1R_pct': round(100 * sum(row['_mfe_r'] >= 1 for row in rows) / len(rows), 4), 'mfe_ge_1_5R_pct': round(100 * sum(row['_mfe_r'] >= 1.5 for row in rows) / len(rows), 4), 'mfe_ge_target_pct': round(100 * sum(value(row, 'mfe_pct') >= row['_target_pct'] for row in rows) / len(rows), 4), 'mae_le_minus_1R_pct': round(100 * sum(row['_mae_r'] <= -1 for row in rows) / len(rows), 4), 'time80_positive_pct': round(100 * sum(row['reason'] == 'TIME80' and value(row, 'net_pnl_pct') > 0 for row in rows) / max(1, sum(row['reason'] == 'TIME80' for row in rows)), 4)}
    OUT.mkdir(parents=True, exist_ok=False)
    result = {'version': 'V546_SINA_M15_V545_FAILURE_ATTRIBUTION_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False, 'source_v545': str(V545), 'trade_source': source['artifacts']['trades'], 'closed_trade_count': len(rows), 'overall': metrics(rows), 'mechanics': mechanics, 'panels_min_n': MIN_N, 'panels': panels, 'interpretation_guard': 'Descriptive diagnostics only. No winning bucket may become a selector; V545 is closed and no variants are authorized.', 'decision': 'V546_ATTRIBUTION_COMPLETE__CLOSE_VOLUME_DISPLACEMENT_ONTOLOGY__NO_EX_POST_BUCKET'}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v546_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
