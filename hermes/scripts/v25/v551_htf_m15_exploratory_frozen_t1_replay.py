#!/usr/bin/env python3
"""V551 one frozen strict-T+1 exploratory replay for frozen V548/V550 HTF->m15 identities.

Frozen before opening outcomes:
- entry = the V548 identity's next 15m bar open;
- stop = sweep-bar low * 0.997 (the sweep reclaim fails with a 0.30% buffer);
- target = the nearest already-confirmed, unconsumed 3L/3R swing high above
  entry that gives planned structural RR >= 1.50;
- no same-day exit: evaluate only bars whose trade date is after entry date;
- stop-first collision, 80 post-entry 15m bars maximum, 0.20% round-trip fee;
- one serial position per symbol; later overlapping identities are skipped.

This is one no-write partial-range (2025-04..2026-07) evaluation, not a
production test. It imports no historical trades and writes no state outside
its timestamped audit directory and latest research report.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from bisect import bisect_left, bisect_right, insort
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/m15'
AUDIT = ROOT / 'smc_audit'
V548 = AUDIT / 'v548_htf_trend_m15_entry_seed_gate_latest.json'
V550 = AUDIT / 'v550_htf_m15_independent_oracle_latest.json'
OUT = AUDIT / f'v551_htf_m15_exploratory_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v551_htf_m15_exploratory_frozen_t1_replay_latest.json'
LEFT = RIGHT = 3
STOP_BUFFER = 0.997
MIN_RR = 1.50
MAX_POST_ENTRY_BARS = 80
FEE_PCT = 0.20
GATE = {'n_min': 1000, 'year_n_min': 300, 'gross_wr_pct_min': 55.0, 'avg_net_pnl_pct_min': 0.50, 'pf_min': 1.15, 'payoff_min': 0.70, 'year_avg_net_pnl_pct_min': 0.0}
IDENTITY = ('symbol', 'weekly_trend_confirm_date', 'weekly_latest_hl_date', 'weekly_structure_high_date', 'daily_trend_confirm_date', 'daily_latest_hl_date', 'daily_structure_high_date', 'm15_ssl_pivot_time', 'm15_sweep_time', 'm15_bos_time', 'm15_fvg_time', 'm15_reclaim_time', 'entry_time')


def positive(value: Any) -> float | None:
    try:
        result = float(value)
        return result if result > 0 and math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def load_bars(symbol: str) -> list[dict[str, Any]]:
    path = RAW / f'{symbol.replace(".", "_")}_m15.json.gz'
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            source = json.load(handle)
    except (OSError, ValueError):
        return []
    rows: list[dict[str, Any]] = []
    for row in source if isinstance(source, list) else []:
        stamp = str(row.get('t') or '')
        values = [positive(row.get(key)) for key in ('o', 'h', 'l', 'c')]
        if len(stamp) == 14 and all(value is not None for value in values):
            rows.append({'t': stamp, 'd': stamp[:8], 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3]})
    return sorted(rows, key=lambda row: row['t'])


def high_pivots(rows: list[dict[str, Any]]) -> set[int]:
    out: set[int] = set()
    for index in range(LEFT, len(rows) - RIGHT):
        high = rows[index]['h']
        if high > max(row['h'] for row in rows[index - LEFT:index]) and high >= max(row['h'] for row in rows[index + 1:index + RIGHT + 1]):
            out.add(index)
    return out


def pct(value: float, base: float) -> float:
    return (value / base - 1.0) * 100.0


def range_max(table: list[list[float]], left: int, right: int) -> float:
    """Inclusive O(1) max query over a precomputed sparse table."""
    width = right - left + 1
    power = width.bit_length() - 1
    return max(table[power][left], table[power][right - (1 << power) + 1])


def high_table(rows: list[dict[str, Any]]) -> list[list[float]]:
    table = [[row['h'] for row in rows]]
    width = 1
    while width * 2 <= len(rows):
        previous = table[-1]
        table.append([max(previous[i], previous[i + width]) for i in range(len(previous) - width)])
        width *= 2
    return table


def target_cache(rows: list[dict[str, Any]], pivots: set[int], index: dict[str, int], seeds: list[dict[str, str]], highs: list[list[float]]) -> dict[tuple[str, str], tuple[int, float] | None]:
    """Resolve all frozen target queries in one forward O(n log n) pass.

    A confirmed high enters the active pool only after its confirmation. It is
    dropped permanently the first time price trades through it. This is exactly
    the old per-seed 'unconsumed through entry' rule, without repeatedly
    rescanning every historical pivot and range for tens of thousands of seeds.
    """
    queries: dict[int, list[tuple[tuple[str, str], float]]] = defaultdict(list)
    for seed in seeds:
        if seed['entry_time'] not in index or seed['m15_sweep_time'] not in index:
            continue
        entry_i, sweep_i = index[seed['entry_time']], index[seed['m15_sweep_time']]
        entry, stop = rows[entry_i]['o'], rows[sweep_i]['l'] * STOP_BUFFER
        key = (seed['m15_sweep_time'], seed['entry_time'])
        if stop < entry:
            queries[entry_i].append((key, entry + MIN_RR * (entry - stop)))
    result: dict[tuple[str, str], tuple[int, float] | None] = {}
    active: list[tuple[float, int]] = []
    for now, row in enumerate(rows):
        pivot = now - RIGHT - 2
        if pivot in pivots:
            price = rows[pivot]['h']
            start = pivot + RIGHT + 1
            if start >= now or range_max(highs, start, now - 1) < price:
                insort(active, (price, pivot))
        consumed = bisect_right(active, (row['h'], len(rows)))
        if consumed:
            del active[:consumed]
        for key, minimum in queries.get(now, []):
            candidate = bisect_left(active, (minimum, -1))
            result[key] = (active[candidate][1], active[candidate][0]) if candidate < len(active) else None
    return result


def replay(seed: dict[str, str], rows: list[dict[str, Any]], index: dict[str, int], target_choice: tuple[int, float] | None) -> dict[str, Any]:
    needed = (seed['m15_sweep_time'], seed['entry_time'])
    if any(stamp not in index for stamp in needed):
        return {'status': 'SKIP', 'reason': 'SEED_TIME_NOT_IN_SOURCE_CACHE'}
    sweep_index, entry_index = index[seed['m15_sweep_time']], index[seed['entry_time']]
    if not sweep_index < entry_index:
        return {'status': 'SKIP', 'reason': 'INVALID_SEED_TIME_ORDER'}
    entry = rows[entry_index]['o']
    stop = rows[sweep_index]['l'] * STOP_BUFFER
    if stop >= entry:
        return {'status': 'SKIP', 'reason': 'INVALID_STRUCTURAL_STOP'}
    selected = target_choice
    if selected is None:
        return {'status': 'SKIP', 'reason': 'NO_UNCONSUMED_STRUCTURAL_TARGET_RR_1_5'}
    target_index, target = selected
    risk = entry - stop
    post = [row for row in rows[entry_index + 1:] if row['d'] > rows[entry_index]['d']][:MAX_POST_ENTRY_BARS]
    if not post:
        return {'status': 'OPEN_DATA', 'reason': 'NO_T1_POST_ENTRY_BAR', 'entry_date': rows[entry_index]['d'], 'entry_time': rows[entry_index]['t'], 'entry_price': entry, 'stop': stop, 'target': target}
    best, worst = max(row['h'] for row in post), min(row['l'] for row in post)
    for hold, bar in enumerate(post, 1):
        if bar['o'] <= stop:
            exit_price, reason = bar['o'], 'GAP_SL'
            break
        if bar['l'] <= stop:
            exit_price, reason = stop, 'SL'
            break
        if bar['h'] >= target:
            exit_price, reason = target, 'TP_STRUCTURAL'
            break
    else:
        if len(post) < MAX_POST_ENTRY_BARS:
            return {'status': 'OPEN_DATA', 'reason': 'INSUFFICIENT_T1_FORWARD_BARS', 'entry_date': rows[entry_index]['d'], 'entry_time': rows[entry_index]['t'], 'entry_price': entry, 'stop': stop, 'target': target, 'hold_bars': len(post), 'mark_time': post[-1]['t'], 'mark_price': post[-1]['c']}
        bar, hold, exit_price, reason = post[-1], MAX_POST_ENTRY_BARS, post[-1]['c'], 'TIME80'
    gross = pct(exit_price, entry)
    return {
        'status': 'CLOSED', 'reason': reason, 'entry_date': rows[entry_index]['d'], 'entry_time': rows[entry_index]['t'], 'entry_price': round(entry, 6), 'exit_date': bar['d'], 'exit_time': bar['t'], 'exit_price': round(exit_price, 6), 'stop': round(stop, 6), 'target': round(target, 6), 'target_pivot_time': rows[target_index]['t'], 'planned_rr': round((target - entry) / risk, 6), 'hold_bars': hold, 'gross_pnl_pct': round(gross, 6), 'net_pnl_pct': round(gross - FEE_PCT, 6), 'mfe_pct': round(pct(best, entry), 6), 'mae_pct': round(pct(worst, entry), 6), 'same_day_exit_violation': rows[entry_index]['d'] == bar['d'],
    }


def stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(row['net_pnl_pct']) for row in rows]
    wins, losses = [value for value in values if value > 0], [value for value in values if value < 0]
    win_sum, loss_abs = sum(wins), abs(sum(losses))
    return {'n': len(rows), 'gross_wr_pct': round(100 * len(wins) / len(rows), 4) if rows else 0.0, 'avg_net_pnl_pct': round(sum(values) / len(rows), 4) if rows else 0.0, 'avg_win_pct': round(sum(wins) / len(wins), 4) if wins else 0.0, 'avg_loss_pct': round(sum(losses) / len(losses), 4) if losses else 0.0, 'payoff_rr': round((sum(wins) / len(wins)) / abs(sum(losses) / len(losses)), 4) if wins and losses else 0.0, 'profit_factor': round(win_sum / loss_abs, 4) if loss_abs else 0.0, 'total_net_pnl_pct': round(sum(values), 4), 'exit_counts': dict(Counter(row['reason'] for row in rows))}


def main() -> None:
    gate, oracle = json.loads(V548.read_text()), json.loads(V550.read_text())
    # User-authorized research-only partial-history protocol. It does not alter
    # V548's production-support failure; it permits one frozen diagnostic replay.
    exploratory_support = (gate.get('seed_count', 0) >= 200 and gate.get('year_counts', {}).get('2025', 0) >= 40 and gate.get('year_counts', {}).get('2026', 0) >= 120 and gate.get('unique_symbols', 0) >= 150)
    if gate.get('decision') != 'V548_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_OBJECT' or not exploratory_support or oracle.get('decision') != 'V550_ORACLE_PASS__EXPLORATORY_FROZEN_T1_REPLAY_AUTHORIZED':
        raise RuntimeError('V548/V550 exploratory preregistration or Oracle gate failed')
    OUT.mkdir(parents=True, exist_ok=False)
    with Path(gate['artifacts']['seeds']).open(newline='', encoding='utf-8') as handle:
        seeds = list(csv.DictReader(handle))
    seeds.sort(key=lambda row: (row['symbol'], row['entry_time'], row['m15_sweep_time']))
    by_symbol: dict[str, list[dict[str, str]]] = defaultdict(list)
    for seed in seeds:
        by_symbol[seed['symbol']].append(seed)
    closed: list[dict[str, Any]] = []
    open_data: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    # Positions are serial only within a symbol. Processing one symbol at a
    # time preserves that contract while releasing its raw bars and sparse
    # table before the next symbol, instead of retaining 5,528 full caches.
    for symbol, symbol_seeds in by_symbol.items():
        rows = load_bars(symbol)
        index = {row['t']: i for i, row in enumerate(rows)}
        pivots, highs = high_pivots(rows), high_table(rows)
        targets = target_cache(rows, pivots, index, symbol_seeds, highs)
        busy_until = ''
        for seed in symbol_seeds:
            if busy_until >= seed['entry_time']:
                skipped['SYMBOL_ALREADY_OPEN'] += 1
                continue
            result = replay(seed, rows, index, targets.get((seed['m15_sweep_time'], seed['entry_time'])))
            if result['status'] == 'SKIP':
                skipped[result['reason']] += 1
                continue
            record = {**seed, **result}
            if result['status'] == 'OPEN_DATA':
                skipped[result['reason']] += 1
                open_data.append(record)
                continue
            closed.append(record)
            busy_until = result['exit_time']
    yearly = {year: stats([row for row in closed if row['entry_date'].startswith(year)]) for year in ('2025', '2026')}
    overall = stats(closed)
    invariant = {'frozen_seed_count_matches_oracle': len(seeds) == oracle['expected_identities'] == oracle['oracle_identities'], 'all_entries_after_reclaim': all(row['entry_time'] > row['m15_reclaim_time'] for row in closed), 'all_targets_visible_pre_entry': all(row['target_pivot_time'] < row['entry_time'] for row in closed), 'all_planned_rr_gte_1_5': all(float(row['planned_rr']) >= MIN_RR for row in closed), 't1_violations': sum(bool(row['same_day_exit_violation']) for row in closed), 'all_writes_false': True}
    checks = {'n>=1000': overall['n'] >= GATE['n_min'], 'each_year_n>=300': all(yearly[year]['n'] >= GATE['year_n_min'] for year in yearly), 'gross_wr>=55': overall['gross_wr_pct'] >= GATE['gross_wr_pct_min'], 'avg_net>=0.5': overall['avg_net_pnl_pct'] >= GATE['avg_net_pnl_pct_min'], 'pf>=1.15': overall['profit_factor'] >= GATE['pf_min'], 'payoff>=0.7': overall['payoff_rr'] >= GATE['payoff_min'], 'each_year_avg_net>0': all(yearly[year]['avg_net_pnl_pct'] > GATE['year_avg_net_pnl_pct_min'] for year in yearly), 't1_violations==0': invariant['t1_violations'] == 0}
    trade_file = OUT / 'v551_frozen_t1_trades.csv'
    if closed:
        with trade_file.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(closed[0].keys()))
            writer.writeheader(); writer.writerows(closed)
    report = {'version': 'V551_HTF_M15_EXPLORATORY_FROZEN_T1_REPLAY_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False, 'scope': 'SINA_SOURCE_ISOLATED_PARTIAL_RANGE_2025_04_TO_2026_07__USER_AUTHORIZED_ONE_TO_TWO_YEAR_EXPLORATORY_ONLY__NOT_PRODUCTION', 'source_contract': 'Sina source-isolated m15 only; no Baostock/Tencent substitution.', 'frozen_execution_contract': 'next-15m open; stop=sweep low*0.997; nearest visible unconsumed 3L/3R high with planned RR>=1.5; exits only next trade date onward; stop-first; time80; fee0.20%; serial symbol position.', 'seed_count': len(seeds), 'closed_trade_count': len(closed), 'open_data_count': len(open_data), 'skip_counts': dict(skipped), 'overall': overall, 'yearly': yearly, 'exploratory_support_contract': {'seed_total_min': 200, 'seed_2025_min': 40, 'seed_2026_min': 120, 'unique_symbols_min': 150}, 'exploratory_support_pass': exploratory_support, 'quality_gate': GATE, 'quality_checks': checks, 'invariants': invariant, 'partial_research_gate_pass': all(checks.values()), 'decision': 'V551_EXPLORATORY_ECONOMIC_SIGNAL__NOT_PRODUCTION__FULL_HISTORY_BLOCKED' if all(checks.values()) else 'V551_EXPLORATORY_REPLAY_FAIL__CLOSE_OBJECT', 'artifacts': {'out_dir': str(OUT), 'trades': str(trade_file), 'latest': str(LATEST), 'v548': str(V548), 'v550': str(V550)}}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v541_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
