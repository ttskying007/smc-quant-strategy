#!/usr/bin/env python3
"""V459 one-shot frozen strict-T+1 replay for V457/V458.

No parameter, stop, target, holding-period, or feature search is performed.
"""
from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
KDIR = ROOT / 'kline_cache'
AUD = ROOT / 'smc_audit'
SRC = AUD / 'v458_weekly_rejection_block_independent_oracle_latest.json'
OUT = AUD / f"v459_weekly_rejection_block_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST = AUD / 'v459_weekly_rejection_block_frozen_t1_replay_latest.json'
YEARS = ('2023', '2024', '2025', '2026')
STOP_BUFFER = 0.99
MAX_HOLD = 30
FEE_PCT = 0.2
GATE = {
    'n': 300,
    'each_year_n': 40,
    'gross_wr_pct': 55.0,
    'avg_net_pnl_pct': 0.5,
    'each_year_gross_wr_pct': 50.0,
    'each_year_avg_net_pnl_pct': 0.0,
    'profit_factor': 1.15,
    't1_violations': 0,
}
STOP_REASONS = {'WEEKLY_REJECTION_LOW_SL_T1', 'SL_GAP_T1', 'SL_TP_COLLISION_CONSERVATIVE_T1'}


def f(value: object) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else 0.0
    except (TypeError, ValueError):
        return 0.0


def integer(value: object) -> int:
    return int(float(value))


def ds(value: object) -> str:
    return ''.join(char for char in str(value or '') if char.isdigit())[:8]


def load_daily(sym: str) -> list[dict]:
    try:
        raw = json.loads((KDIR / f"{sym.replace('.', '_')}_daily_750.json").read_text())
    except (OSError, json.JSONDecodeError):
        return []
    rows = []
    for bar in raw:
        values = {key: f(bar.get(key)) for key in ('o', 'h', 'l', 'c')}
        date = ds(bar.get('t') or bar.get('date'))
        if date and all(values.values()):
            values['t'] = date
            rows.append(values)
    return sorted(rows, key=lambda row: row['t'])


def completed_weeks(daily: list[dict]) -> list[dict]:
    groups: list[list[dict]] = []
    current = None
    for bar in daily:
        key = datetime.strptime(bar['t'], '%Y%m%d').date().isocalendar()[:2]
        if key != current:
            groups.append([])
            current = key
        groups[-1].append(bar)
    groups = groups[:-1]
    return [
        {'end_date': group[-1]['t'], 'h': max(bar['h'] for bar in group)}
        for group in groups if group
    ]


def confirmed_weekly_highs(weeks: list[dict]) -> list[tuple[int, int, float, str]]:
    return [
        (idx, idx + 2, weeks[idx]['h'], weeks[idx]['end_date'])
        for idx in range(2, len(weeks) - 2)
        if all(weeks[j]['h'] < weeks[idx]['h'] for j in range(idx - 2, idx + 3) if j != idx)
    ]


def target_at(highs: list[tuple[int, int, float, str]], weeks: list[dict], cutoff_date: str, entry: float) -> tuple[float | None, str]:
    candidates = [
        (price, pivot_date)
        for _, visible_idx, price, pivot_date in highs
        if weeks[visible_idx]['end_date'] <= cutoff_date and price > entry
    ]
    return min(candidates, default=(None, ''), key=lambda item: item[0])


def replay(seed: dict, daily: list[dict], weeks: list[dict], highs: list[tuple[int, int, float, str]]) -> dict:
    eligible = integer(seed['eligible_entry_idx'])
    hold = integer(seed['hold_idx'])
    if eligible != hold + 1 or eligible >= len(daily):
        return {'status': 'UNOBSERVED_ENTRY'}
    entry = daily[eligible]['o']
    sl = f(seed['zone_low']) * STOP_BUFFER
    if entry <= 0 or sl <= 0 or sl >= entry:
        return {'status': 'INVALID_RISK', 'entry_date': daily[eligible]['t']}
    target, target_date = target_at(highs, weeks, daily[hold]['t'], entry)
    first = eligible + 1
    last = eligible + MAX_HOLD
    if first >= len(daily) or last >= len(daily):
        return {'status': 'OPEN_RIGHT_EDGE', 'entry_date': daily[eligible]['t']}
    exit_idx = last
    exit_price = daily[last]['c']
    reason = 'TIME30_NO_KNOWN_WEEKLY_BSL' if target is None else 'TIME30_WEEKLY_BSL_UNREACHED'
    collision = False
    for idx in range(first, last + 1):
        bar = daily[idx]
        if bar['o'] <= sl:
            exit_idx, exit_price, reason = idx, bar['o'], 'SL_GAP_T1'
            break
        if target is not None and bar['o'] >= target:
            exit_idx, exit_price, reason = idx, bar['o'], 'WEEKLY_BSL_GAP_TP_T1'
            break
        hit_sl = bar['l'] <= sl
        hit_tp = target is not None and bar['h'] >= target
        if hit_sl and hit_tp:
            exit_idx, exit_price, reason, collision = idx, sl, 'SL_TP_COLLISION_CONSERVATIVE_T1', True
            break
        if hit_sl:
            exit_idx, exit_price, reason = idx, sl, 'WEEKLY_REJECTION_LOW_SL_T1'
            break
        if hit_tp:
            exit_idx, exit_price, reason = idx, target, 'KNOWN_WEEKLY_BSL_TP_T1'
            break
    gross = (exit_price / entry - 1) * 100
    net = gross - FEE_PCT
    risk = (entry / sl - 1) * 100
    return {
        'status': 'CLOSED',
        'entry_idx': eligible,
        'entry_date': daily[eligible]['t'],
        'entry_price': round(entry, 6),
        'sl': round(sl, 6),
        'risk_pct': round(risk, 4),
        'tp': '' if target is None else round(target, 6),
        'tp_anchor_date': target_date,
        'exit_idx': exit_idx,
        'exit_date': daily[exit_idx]['t'],
        'exit_price': round(exit_price, 6),
        'exit_reason': reason,
        'hold_bars': exit_idx - eligible,
        'gross_pnl_pct': round(gross, 4),
        'net_pnl_pct': round(net, 4),
        'realized_r': round(gross / risk, 4) if risk else 0.0,
        't1_violation': daily[exit_idx]['t'] <= daily[eligible]['t'],
        'same_bar_collision': collision,
    }


def stats(rows: list[dict]) -> dict:
    if not rows:
        return {'n': 0}
    gross = [f(row['gross_pnl_pct']) for row in rows]
    net = [f(row['net_pnl_pct']) for row in rows]
    wins = [value for value in net if value > 0]
    losses = [value for value in net if value <= 0]
    average_win = sum(wins) / len(wins) if wins else 0.0
    average_loss = sum(losses) / len(losses) if losses else 0.0
    profit_factor = sum(wins) / abs(sum(losses)) if losses and sum(losses) else 0.0
    return {
        'n': len(rows),
        'gross_wr_pct': round(sum(value > 0 for value in gross) / len(rows) * 100, 4),
        'net_wr_ge_0_8_pct': round(sum(value >= 0.8 for value in net) / len(rows) * 100, 4),
        'avg_gross_pnl_pct': round(sum(gross) / len(rows), 4),
        'avg_net_pnl_pct': round(sum(net) / len(rows), 4),
        'median_net_pnl_pct': round(statistics.median(net), 4),
        'avg_win_pct': round(average_win, 4),
        'avg_loss_pct': round(average_loss, 4),
        'payoff_rr': round(average_win / abs(average_loss), 4) if average_loss else 0.0,
        'profit_factor': round(profit_factor, 4),
        'cum_net_pnl_pct': round(sum(net), 4),
        'avg_realized_r': round(sum(f(row['realized_r']) for row in rows) / len(rows), 4),
        'sl_pct': round(sum(row['exit_reason'] in STOP_REASONS for row in rows) / len(rows) * 100, 4),
    }


def promotion_pass(overall: dict, yearly: dict[str, dict], t1_violations: int) -> bool:
    return (
        overall.get('n', 0) >= GATE['n']
        and overall.get('gross_wr_pct', 0) >= GATE['gross_wr_pct']
        and overall.get('avg_net_pnl_pct', -999) >= GATE['avg_net_pnl_pct']
        and overall.get('profit_factor', 0) >= GATE['profit_factor']
        and all(
            yearly[year].get('n', 0) >= GATE['each_year_n']
            and yearly[year].get('gross_wr_pct', 0) >= GATE['each_year_gross_wr_pct']
            and yearly[year].get('avg_net_pnl_pct', -999) > GATE['each_year_avg_net_pnl_pct']
            for year in YEARS
        )
        and t1_violations == GATE['t1_violations']
    )


def main() -> None:
    source = json.loads(SRC.read_text())
    if source.get('decision') != 'WEEKLY_REJECTION_BLOCK_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED':
        raise RuntimeError('V458 oracle gate not passed')
    with open(source['artifacts']['passed_seeds']) as handle:
        seeds = list(csv.DictReader(handle))
    OUT.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for seed in seeds:
        grouped[seed['symbol']].append(seed)
    rows: list[dict] = []
    for idx, (sym, items) in enumerate(grouped.items(), 1):
        daily = load_daily(sym)
        weeks = completed_weeks(daily)
        highs = confirmed_weekly_highs(weeks)
        for seed in items:
            result = replay(seed, daily, weeks, highs)
            rows.append({**seed, 'execution_contract': 'NEXT_OPEN__WEEKLY_REJECTION_LOW_1PCT_SL__KNOWN_WEEKLY_BSL_OR_TIME30__STRICT_T1__FEE0P2', **result})
        if idx % 500 == 0:
            print(json.dumps({'symbols': idx, 'rows': len(rows)}), flush=True)
    closed = [row for row in rows if row.get('status') == 'CLOSED' and row['entry_date'][:4] in YEARS]
    yearly = {year: stats([row for row in closed if row['entry_date'][:4] == year]) for year in YEARS}
    overall = stats(closed)
    t1_violations = sum(bool(row.get('t1_violation')) for row in closed)
    passed = promotion_pass(overall, yearly, t1_violations)
    fields = sorted({key for row in rows for key in row})
    row_file = OUT / 'v459_frozen_t1_rows.csv'
    with row_file.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    result = {
        'version': 'V459_WEEKLY_REJECTION_BLOCK_FROZEN_T1_REPLAY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'frozen_before_outcomes': {
            'entry': 'next daily open after post-week touch, later reclaim, later hold',
            'sl': 'weekly raid/rejection low * 0.99',
            'target': 'nearest pre-entry confirmed weekly 2L/2R BSL above entry',
            'exit': 'strict T+1, target/SL/time30, gap-aware, collision=SL',
            'fee_pct': FEE_PCT,
            'search_count': 1,
            'promotion_gate': GATE,
        },
        'seed_count': len(seeds),
        'status_counts': dict(Counter(row.get('status') for row in rows)),
        'research_window_closed_n': len(closed),
        'overall': overall,
        'yearly': yearly,
        'exit_reason_counts': dict(Counter(row['exit_reason'] for row in closed)),
        'invariants': {
            't1_violations': t1_violations,
            'same_bar_collisions': sum(bool(row.get('same_bar_collision')) for row in closed),
            'search_count': 1,
            'source_oracle_pass': True,
        },
        'promotion_gate_pass': passed,
        'decision': 'WEEKLY_REJECTION_BLOCK_FROZEN_REPLAY_PASS__SHADOW_NEXT' if passed else 'WEEKLY_REJECTION_BLOCK_ECONOMIC_GATE_FAIL__CLOSE_ONTOLOGY_NO_VARIANTS',
        'artifacts': {'out_dir': str(OUT), 'rows': str(row_file), 'latest': str(LATEST)},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v459_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
