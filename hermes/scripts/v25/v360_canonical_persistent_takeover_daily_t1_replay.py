#!/usr/bin/env python3
"""V360: replay only canonical, fresh, persistent daily continuation paths.

This corrects V358's cohort mismatch: V358 read V354 identity rows rather than
V357's one-physical-OB, fresh-at-BOS canonical paths.  It is a fixed no-write
research replay, not a parameter search or production selector.
"""
from __future__ import annotations

import csv
import importlib.util
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
KDIR = ROOT / 'kline_cache'
SRC = AUD / 'v357_canonical_continuation_lifecycle_latest.json'
STAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUD / f'v360_canonical_persistent_takeover_daily_t1_replay_no_write_{STAMP}'
LATEST = AUD / 'v360_canonical_persistent_takeover_daily_t1_replay_latest.json'

# Fixed promotion gate from the V316-V319 closure.  All four current years
# must be represented; passing this gate is required before any future review.
GATE = {
    'n': 300,
    'min_year_n': 40,
    'wr_pct': 87.0,
    'avg_pnl_pct': 6.8,
    'all_year_wr_min': 84.0,
    't1_violations': 0,
}

spec = importlib.util.spec_from_file_location(
    'v358_replay', ROOT / 'scripts/v25/v358_unique_persistent_takeover_daily_t1_replay.py'
)
assert spec and spec.loader
v358 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v358)


def date_of(bar: dict) -> str:
    return ''.join(c for c in str(bar.get('t') or bar.get('date') or '') if c.isdigit())[:8]


def load_bars(symbol: str) -> list[dict]:
    try:
        bars = json.loads((KDIR / f'{symbol.replace(".", "_")}_daily_750.json').read_text())
    except Exception:
        return []
    return sorted((bar for bar in bars if date_of(bar)), key=date_of)


def persistent(bars: list[dict], row: dict) -> str:
    """Two post-takeover closes above the zone; no future bars are inspected."""
    by_date = {date_of(bar): i for i, bar in enumerate(bars)}
    takeover_idx = by_date.get(row.get('takeover_date', ''))
    low, high = v358.f(row.get('zone_low')), v358.f(row.get('zone_high'))
    if takeover_idx is None or takeover_idx + 2 >= len(bars):
        return 'PERSISTENCE_UNOBSERVED'
    for idx in range(takeover_idx + 1, takeover_idx + 3):
        close = v358.f(bars[idx].get('c'))
        if close < low:
            return 'PERSISTENCE_ZONE_INVALIDATED'
        if close <= high:
            return 'PERSISTENCE_REENTERED_ZONE'
    return 'PERSISTENT_TAKEOVER'


def brief(rows: list[dict]) -> dict:
    if not rows:
        return {'n': 0, 'wr_pct': 0.0, 'avg_pnl_pct': 0.0}
    pnls = [v358.f(row.get('pnl_pct')) for row in rows]
    stops = {'SL_GAP_T1', 'STRUCTURE_SL_T1', 'SL_TP_SAME_BAR_CONSERVATIVE_SL_T1'}
    return {
        'n': len(rows),
        'wr_pct': round(sum(pnl > 0 for pnl in pnls) / len(rows) * 100, 4),
        'avg_pnl_pct': round(sum(pnls) / len(rows), 4),
        'median_pnl_pct': round(sorted(pnls)[len(pnls) // 2], 4),
        'sl_pct': round(sum(row.get('exit_reason') in stops for row in rows) / len(rows) * 100, 4),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads(SRC.read_text())
    with Path(report['artifacts']['rows']).open() as handle:
        canonical = list(csv.DictReader(handle))

    cache: dict[str, list[dict]] = {}
    rows: list[dict] = []
    statuses = Counter()
    for source in canonical:
        state = source.get('lifecycle_state')
        if state != 'TAKEOVER_CONFIRMED':
            statuses[state] += 1
            continue
        symbol = source['symbol']
        if symbol not in cache:
            cache[symbol] = load_bars(symbol)
        status = persistent(cache[symbol], source)
        statuses[status] += 1
        if status != 'PERSISTENT_TAKEOVER':
            continue
        result = v358.replay(cache[symbol], source)
        rows.append({
            'symbol': symbol,
            'ob_idx': source.get('ob_idx', ''),
            'ob_date': source.get('ob_date', ''),
            'event_idx': source.get('event_idx', ''),
            'event_date': source.get('event_date', ''),
            'touch_date': source.get('touch_date', ''),
            'reclaim_date': source.get('reclaim_date', ''),
            'takeover_date': source.get('takeover_date', ''),
            'zone_low': source.get('zone_low', ''),
            'zone_high': source.get('zone_high', ''),
            'canonical_contract': source.get('semantic_contract', ''),
            'persistence_contract': 'two next daily closes > zone_high; any close < zone_low rejects',
            'execution_contract': 'entry after persistence at next open; structural target; strict T+1 exit',
            'tradable': 'false',
            'buy_enabled': 'false',
            **result,
        })

    fields = sorted({key for row in rows for key in row})
    row_path = OUT / 'v360_canonical_persistent_daily_t1_replay_rows.csv'
    with row_path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    closed = [row for row in rows if row.get('status') == 'CLOSED']
    by_year: dict[str, list[dict]] = defaultdict(list)
    for row in closed:
        by_year[row['entry_date'][:4]].append(row)
    all_metrics = brief(closed)
    yearly = {year: brief(group) for year, group in sorted(by_year.items())}
    current_years = {year: yearly.get(year, {'n': 0, 'wr_pct': 0.0}) for year in ('2023', '2024', '2025', '2026')}
    min_year_n = min(item['n'] for item in current_years.values())
    all_year_wr_min = min(item['wr_pct'] for item in current_years.values())
    t1 = sum(bool(row.get('t1_violation')) for row in closed)
    gate = {
        'n': all_metrics['n'] >= GATE['n'],
        'min_year_n': min_year_n >= GATE['min_year_n'],
        'wr_pct': all_metrics['wr_pct'] >= GATE['wr_pct'],
        'avg_pnl_pct': all_metrics['avg_pnl_pct'] >= GATE['avg_pnl_pct'],
        'all_year_wr_min': all_year_wr_min >= GATE['all_year_wr_min'],
        't1_violations': t1 == GATE['t1_violations'],
    }
    result = {
        'version': 'V360_CANONICAL_PERSISTENT_TAKEOVER_DAILY_T1_REPLAY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'input_contract': 'V357 only: one physical OB, earliest BOS, fresh at BOS, post-BOS takeover',
        'persistence_contract': 'two additional closes above zone_high; any close below zone_low rejects',
        'execution_contract': 'next-open after persistence; zone_low*0.99 stop; known swing-high target; strict T+1; conservative same-bar collision',
        'canonical_input_rows': len(canonical),
        'stage_counts': dict(statuses),
        'replay_status_counts': dict(Counter(row.get('status') for row in rows)),
        'metrics': {**all_metrics, 'yearly': yearly, 't1_violations': t1},
        'production_gate_definition': GATE,
        'production_gate_values': {'min_year_n': min_year_n, 'all_year_wr_min': all_year_wr_min},
        'production_gate_passes': gate,
        'decision': 'CANONICAL_CONTINUATION_PROMOTION_PASS' if all(gate.values()) else 'CANONICAL_CONTINUATION_FAIL__NO_PROMOTION',
        'invariants': {
            'all_rows_canonical_fresh_persistent': True,
            'no_future_input_tags': True,
            'all_rows_non_tradable': all(row['tradable'] == 'false' and row['buy_enabled'] == 'false' for row in rows),
            't1_violations': t1,
            'no_production_writes': True,
        },
        'artifacts': {'out_dir': str(OUT), 'rows': str(row_path), 'latest': str(LATEST)},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v360_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
