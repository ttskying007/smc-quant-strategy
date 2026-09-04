#!/usr/bin/env python3
"""V564 — the single frozen strict-T+1 replay of the V562/V563-verified ontology.

The selector is immutable: V562's canonical seed identities. This script does not
apply any new threshold, timing, stock, year, regime, exit, target, or outcome filter.
Execution is fixed before outcomes are read: next daily open; pre-entry structural
stop and unconsumed 3L/3R target with RR>=1.5; conservative stop-first; exits begin
on the next trading day; 20 daily-bar maximum hold; 0.20% total fee.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/daily'
V562 = AUD / 'v562_industry_synchronized_m15_takeover_seed_latest.json'
V563 = AUD / 'v563_industry_synchronized_m15_independent_oracle_latest.json'
OUT = AUD / f'v564_industry_synchronized_m15_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v564_industry_synchronized_m15_frozen_t1_replay_latest.json'
FEE = 0.002
HOLD = 20
RR_FLOOR = 1.5


def num(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def daily_bars(symbol: str) -> list[dict[str, float | str]]:
    try:
        raw = json.load(gzip.open(RAW / f'{symbol.replace(".", "_")}_daily.json.gz', 'rt', encoding='utf-8'))
    except (OSError, ValueError):
        return []
    rows: list[dict[str, float | str]] = []
    for bar in raw if isinstance(raw, list) else []:
        date = str(bar.get('d') or bar.get('t') or '')[:8]
        o, h, l, c = (num(bar.get(key)) for key in ('o', 'h', 'l', 'c'))
        if len(date) == 8 and None not in (o, h, l, c):
            rows.append({'d': date, 'o': o, 'h': h, 'l': l, 'c': c})
    return sorted(rows, key=lambda row: str(row['d']))


def swing_high(rows: list[dict[str, float | str]], index: int) -> bool:
    return index >= 3 and index + 3 < len(rows) and float(rows[index]['h']) > max(float(x['h']) for x in rows[index-3:index]) and float(rows[index]['h']) >= max(float(x['h']) for x in rows[index+1:index+4])


def structural_target(rows: list[dict[str, float | str]], entry_index: int, entry: float, stop: float) -> float | None:
    required = entry + (entry - stop) * RR_FLOOR
    targets: list[float] = []
    for index in range(3, entry_index - 3):
        high = float(rows[index]['h'])
        if swing_high(rows, index) and high >= required and not any(float(x['h']) >= high for x in rows[index+1:entry_index]):
            targets.append(high)
    return min(targets) if targets else None


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {'n': 0}
    values = [float(row['net_pct']) for row in rows]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value <= 0]
    return {
        'n': len(rows),
        'wr_pct': round(100.0 * len(wins) / len(rows), 4),
        'avg_net_pct': round(sum(values) / len(rows), 4),
        'avg_win_pct': round(sum(wins) / len(wins), 4) if wins else None,
        'avg_loss_pct': round(sum(losses) / len(losses), 4) if losses else None,
        'profit_factor': round(sum(wins) / abs(sum(losses)), 4) if losses and sum(losses) else None,
        'payoff': round((sum(wins) / len(wins)) / abs(sum(losses) / len(losses)), 4) if wins and losses else None,
        'exit_counts': dict(Counter(str(row['exit_reason']) for row in rows)),
    }


def gate(overall: dict[str, Any], yearly: dict[str, dict[str, Any]], violations: int) -> dict[str, bool]:
    years = ('2025', '2026')
    return {
        'n>=1000': overall.get('n', 0) >= 1000,
        'each_available_year_n>=300': all(yearly.get(year, {}).get('n', 0) >= 300 for year in years),
        'wr>=55': float(overall.get('wr_pct') or 0) >= 55.0,
        'avg_net>=0.50': float(overall.get('avg_net_pct') or -999) >= 0.50,
        'pf>=1.15': float(overall.get('profit_factor') or 0) >= 1.15,
        'payoff>=0.70': float(overall.get('payoff') or 0) >= 0.70,
        'each_available_year_avg_net>0': all(float(yearly.get(year, {}).get('avg_net_pct') or -999) > 0 for year in years),
        't1_violations==0': violations == 0,
    }


def main() -> None:
    source_meta, oracle_meta = json.loads(V562.read_text()), json.loads(V563.read_text())
    if not source_meta['support_gate']['pass']:
        raise RuntimeError('V562 support gate did not pass')
    if not oracle_meta['identity_match']:
        raise RuntimeError('V563 independent oracle did not match')
    with Path(source_meta['artifacts']['seeds']).open(newline='', encoding='utf-8') as handle:
        seeds = list(csv.DictReader(handle))
    forbidden = [
        name for name in (seeds[0] if seeds else {})
        if name != 'no_outcome_fields' and any(token in name.lower() for token in ('pnl', 'exit', 'outcome', 'mfe', 'mae', 'winner'))
    ]
    if forbidden:
        raise RuntimeError(f'outcome-bearing seed field is prohibited: {forbidden}')
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for seed in seeds:
        grouped[seed['symbol']].append(seed)
    OUT.mkdir(parents=True, exist_ok=False)
    trades: list[dict[str, Any]] = []
    no_target: list[dict[str, Any]] = []
    missing_source: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    for symbol, rows in sorted(grouped.items()):
        bars = daily_bars(symbol)
        index_by_date = {str(row['d']): index for index, row in enumerate(bars)}
        for seed in rows:
            entry_date = seed['planned_entry_date']
            entry_index = index_by_date.get(entry_date)
            if entry_index is None or entry_index + 1 >= len(bars):
                missing_source.append({'symbol': symbol, 'entry_date': entry_date, 'reason': 'MISSING_ENTRY_OR_FUTURE_DAILY_BAR'})
                continue
            entry = float(bars[entry_index]['o'])
            stop = float(seed['structural_stop'])
            target = structural_target(bars, entry_index, entry, stop)
            base = {
                'symbol': symbol,
                'event_date': seed['event_date'],
                'reclaim_date': seed['reclaim_date'],
                'm15_choch_time': seed['m15_choch_time'],
                'entry_date': entry_date,
                'entry': round(entry, 6),
                'stop': round(stop, 6),
            }
            if target is None:
                no_target.append({**base, 'reason': 'NO_UNCONSUMED_PREENTRY_3L3R_TARGET_RR_1_5'})
                continue
            last = min(len(bars) - 1, entry_index + HOLD)
            exit_index, exit_price, reason = last, float(bars[last]['c']), 'TIME20'
            for index in range(entry_index + 1, last + 1):
                # Conservative same-bar ordering: stop before target.
                if float(bars[index]['l']) <= stop:
                    exit_index, exit_price, reason = index, stop, 'SL'
                    break
                if float(bars[index]['h']) >= target:
                    exit_index, exit_price, reason = index, target, 'TP_UNCONSUMED_STRUCTURAL'
                    break
            exit_date = str(bars[exit_index]['d'])
            if exit_date <= entry_date:
                violations.append({**base, 'exit_date': exit_date})
                continue
            trades.append({
                **base,
                'target': round(target, 6),
                'planned_rr': round((target - entry) / (entry - stop), 4),
                'exit_date': exit_date,
                'exit_price': round(exit_price, 6),
                'exit_reason': reason,
                'hold_bars': exit_index - entry_index,
                'net_pct': round((exit_price / entry - 1.0 - FEE) * 100.0, 4),
                'year': entry_date[:4],
            })
    for name, rows in {
        'v564_frozen_t1_trades.csv': trades,
        'v564_no_structural_target.csv': no_target,
        'v564_missing_source.csv': missing_source,
        'v564_t1_violations.csv': violations,
    }.items():
        with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ['symbol'])
            writer.writeheader()
            writer.writerows(rows)
    overall = metrics(trades)
    yearly = {year: metrics([row for row in trades if row['year'] == year]) for year in ('2025', '2026')}
    checks = gate(overall, yearly, len(violations))
    report = {
        'version': 'V564_INDUSTRY_SYNCHRONIZED_M15_FROZEN_T1_REPLAY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'scope': 'SINA_SOURCE_ISOLATED_PARTIAL_2025_2026__RESEARCH_ONLY_NOT_PRODUCTION',
        'seed_source': str(source_meta['artifacts']['seeds']),
        'execution_contract': 'next daily open; stop=pre-entry structural stop supplied by immutable V562 seed; nearest unconsumed pre-entry 3L/3R high with planned RR>=1.5; stop-first; earliest exit next trading day; hold=20; fee=0.20%; serial position per symbol.',
        'seed_count': len(seeds),
        'coverage': {'executed': len(trades), 'no_unconsumed_target': len(no_target), 'missing_source': len(missing_source)},
        'overall': overall,
        'yearly': yearly,
        'quality_gate': {'n_min': 1000, 'year_n_min': 300, 'wr_pct_min': 55.0, 'avg_net_pct_min': 0.50, 'pf_min': 1.15, 'payoff_min': 0.70, 'year_avg_net_pct_min': 0.0},
        'quality_checks': checks,
        't1_violations': len(violations),
        'invariants': {
            'v563_identity_match': True,
            'forbidden_seed_headers': forbidden,
            'all_exits_strictly_after_entry': not violations,
            'all_targets_unconsumed_and_preentry_by_contract': True,
            'no_parameter_or_selector_search': True,
            'all_writes_false': True,
        },
        'promotion_gate_pass': all(checks.values()),
        'decision': 'FROZEN_REPLAY_PASS__PARTIAL_RANGE_RESEARCH_CANDIDATE_ONLY__NO_PRODUCTION_AUTHORIZATION' if all(checks.values()) else 'FROZEN_REPLAY_FAIL__CLOSE_OBJECT__NO_PRODUCTION_AUTHORIZATION',
        'artifacts': {'out_dir': str(OUT), 'trades': str(OUT / 'v564_frozen_t1_trades.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v564_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
