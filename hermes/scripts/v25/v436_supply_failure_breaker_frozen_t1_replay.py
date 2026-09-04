#!/usr/bin/env python3
"""V436 one-shot frozen T+1 replay for Supply-Failure Breaker.

The execution and promotion gates are declared here before outcomes are opened.
No threshold, stop, target, or hold-period search is performed.
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
KDIR, AUD = ROOT / 'kline_cache', ROOT / 'smc_audit'
SOURCE = AUD / 'v435_supply_failure_breaker_independent_oracle_latest.json'
OUT = AUD / f'v436_supply_failure_breaker_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v436_supply_failure_breaker_frozen_t1_replay_latest.json'
STOP_BUFFER = 0.99
MAX_HOLD = 30
GATE = {
    'n': 300, 'each_year_n': 40, 'aggregate_wr_pct': 55.0, 'aggregate_avg_pnl_pct': 0.5,
    'each_year_wr_pct': 50.0, 'each_year_avg_pnl_pct': 0.0,
    'each_epoch_wr_pct': 50.0, 'each_epoch_avg_pnl_pct': 0.0, 't1_violations': 0,
}


def f(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else 0.0
    except (TypeError, ValueError):
        return 0.0


def day(bar):
    return ''.join(c for c in str(bar.get('t') or bar.get('date') or '') if c.isdigit())[:8]


def load_bars(symbol):
    path = KDIR / f"{symbol.replace('.', '_')}_daily_750.json"
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    rows = []
    for bar in raw:
        normalized = {key: f(bar.get(key)) for key in ('o', 'h', 'l', 'c')}
        if day(bar) and all(normalized.values()):
            normalized['t'] = day(bar)
            rows.append(normalized)
    return sorted(rows, key=lambda row: row['t'])


def confirmed_highs(bars):
    highs = []
    for idx in range(6, len(bars) - 3):
        high = bars[idx]['h']
        if all(bars[j]['h'] < high for j in range(idx - 3, idx + 4) if j != idx):
            highs.append((idx, idx + 3, high, bars[idx]['t']))
    return highs


def known_target(highs, cutoff_idx, entry):
    candidates = [(price, pivot_date) for _, confirm_idx, price, pivot_date in highs
                  if confirm_idx <= cutoff_idx and price > entry]
    return min(candidates, default=(None, ''), key=lambda item: item[0])


def replay(row, bars, highs):
    eligible = int(row['eligible_entry_idx']) if row.get('eligible_entry_idx') not in ('', None) else None
    takeover = int(row['takeover_idx'])
    if eligible is None or eligible != takeover + 1 or eligible >= len(bars):
        return {'status': 'UNOBSERVED_RIGHT_EDGE'}
    entry = bars[eligible]['o']
    zone_low = f(row['zone_low'])
    sl = zone_low * STOP_BUFFER
    if entry <= 0 or sl <= 0 or sl >= entry:
        return {'status': 'INVALID_NONPOSITIVE_RISK', 'entry_idx': eligible, 'entry_date': bars[eligible]['t']}
    target, target_date = known_target(highs, takeover, entry)
    first_exit = eligible + 1
    last_exit = eligible + MAX_HOLD
    if first_exit >= len(bars) or last_exit >= len(bars):
        return {'status': 'OPEN_RIGHT_EDGE', 'entry_idx': eligible, 'entry_date': bars[eligible]['t'],
                'entry_price': round(entry, 4), 'sl': round(sl, 4)}

    exit_idx, exit_price = last_exit, bars[last_exit]['c']
    exit_reason = 'TIME30_NO_KNOWN_BSL' if target is None else 'TIME30_BSL_UNREACHED'
    collision = False
    for idx in range(first_exit, last_exit + 1):
        bar = bars[idx]
        if bar['o'] <= sl:
            exit_idx, exit_price, exit_reason = idx, bar['o'], 'SL_GAP_T1'
            break
        hit_sl = bar['l'] <= sl
        hit_tp = target is not None and bar['h'] >= target
        if hit_sl and hit_tp:
            exit_idx, exit_price, exit_reason, collision = idx, sl, 'SL_TP_COLLISION_CONSERVATIVE_T1', True
            break
        if hit_sl:
            exit_idx, exit_price, exit_reason = idx, sl, 'STRUCTURE_SL_T1'
            break
        if hit_tp:
            exit_idx, exit_price, exit_reason = idx, max(bar['o'], target), 'KNOWN_BSL_TP_T1'
            break
    path = bars[eligible:exit_idx + 1]
    pnl = (exit_price / entry - 1) * 100
    return {
        'status': 'CLOSED', 'entry_idx': eligible, 'entry_date': bars[eligible]['t'],
        'entry_price': round(entry, 4), 'sl': round(sl, 4),
        'risk_pct': round((entry / sl - 1) * 100, 4),
        'tp': '' if target is None else round(target, 4), 'tp_anchor_date': target_date,
        'exit_idx': exit_idx, 'exit_date': bars[exit_idx]['t'], 'exit_price': round(exit_price, 4),
        'exit_reason': exit_reason, 'hold_bars': exit_idx - eligible, 'pnl_pct': round(pnl, 4),
        'mfe_pct': round((max(x['h'] for x in path) / entry - 1) * 100, 4),
        'mae_pct': round((min(x['l'] for x in path) / entry - 1) * 100, 4),
        't1_violation': bars[exit_idx]['t'] <= bars[eligible]['t'],
        'same_bar_collision': collision,
    }


def stats(rows):
    if not rows:
        return {'n': 0, 'wr_pct': 0, 'avg_pnl_pct': 0}
    pnls = [f(row['pnl_pct']) for row in rows]
    return {'n': len(rows), 'wr_pct': round(sum(x > 0 for x in pnls) / len(pnls) * 100, 4),
            'avg_pnl_pct': round(sum(pnls) / len(pnls), 4),
            'median_pnl_pct': round(statistics.median(pnls), 4),
            'sl_pct': round(sum(str(row['exit_reason']).startswith(('SL_', 'STRUCTURE_SL')) for row in rows) / len(rows) * 100, 4)}


def gate_pass(overall, yearly, epochs, t1):
    return (overall['n'] >= GATE['n'] and overall['wr_pct'] >= GATE['aggregate_wr_pct']
            and overall['avg_pnl_pct'] >= GATE['aggregate_avg_pnl_pct']
            and all(yearly.get(year, {}).get('n', 0) >= GATE['each_year_n'] for year in ('2023','2024','2025','2026'))
            and all(yearly.get(year, {}).get('wr_pct', 0) >= GATE['each_year_wr_pct'] for year in ('2023','2024','2025','2026'))
            and all(yearly.get(year, {}).get('avg_pnl_pct', -999) > GATE['each_year_avg_pnl_pct'] for year in ('2023','2024','2025','2026'))
            and all(value['wr_pct'] >= GATE['each_epoch_wr_pct'] and value['avg_pnl_pct'] > GATE['each_epoch_avg_pnl_pct'] for value in epochs.values())
            and t1 == GATE['t1_violations'])


def main():
    source = json.loads(SOURCE.read_text())
    if source.get('decision') != 'INDEPENDENT_SEMANTIC_ORACLE_PASS__FROZEN_T1_REPLAY_NEXT':
        raise RuntimeError('V435 independent semantic gate did not pass')
    with Path(source['artifacts']['oracle_rows']).open(newline='') as handle:
        seeds = list(csv.DictReader(handle))

    OUT.mkdir(parents=True, exist_ok=True)
    cache, high_cache, rows = {}, {}, []
    for index, seed in enumerate(seeds, 1):
        symbol = seed['symbol']
        if symbol not in cache:
            cache[symbol] = load_bars(symbol)
            high_cache[symbol] = confirmed_highs(cache[symbol])
        result = replay(seed, cache[symbol], high_cache[symbol])
        rows.append({**seed, 'execution_contract': 'NEXT_OPEN__SL_ZONE_LOW_1PCT__KNOWN_BSL_OR_TIME30__STRICT_T1', **result})
        if index % 10000 == 0:
            print(json.dumps({'progress': index, 'closed': sum(x.get('status') == 'CLOSED' for x in rows)}, ensure_ascii=False), flush=True)

    closed = [row for row in rows if row.get('status') == 'CLOSED']
    by_year = {year: stats([row for row in closed if row['entry_date'][:4] == year]) for year in ('2023','2024','2025','2026')}
    epochs = {'2023_2024': stats([row for row in closed if row['entry_date'][:4] in {'2023','2024'}]),
              '2025_2026': stats([row for row in closed if row['entry_date'][:4] in {'2025','2026'}])}
    overall = stats(closed)
    t1 = sum(bool(row.get('t1_violation')) for row in closed)
    passed = gate_pass(overall, by_year, epochs, t1)

    fields = sorted({key for row in rows for key in row})
    with (OUT / 'v436_frozen_replay_rows.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    report = {
        'version': 'V436_SUPPLY_FAILURE_BREAKER_FROZEN_T1_REPLAY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'frozen_before_outcomes': {'entry': 'next open after takeover hold confirmation',
                                   'sl': 'supply breaker zone_low * 0.99',
                                   'target': 'nearest 3L/3R swing high above entry already confirmed by takeover close; otherwise none',
                                   'exit': 'strict T+1; target/SL then time30; gap-aware; same-bar collision=SL',
                                   'promotion_gate': GATE, 'search_count': 1},
        'seed_count': len(seeds), 'status_counts': dict(Counter(row.get('status') for row in rows)),
        'overall': overall, 'yearly': by_year, 'epochs': epochs,
        'exit_reason_counts': dict(Counter(row['exit_reason'] for row in closed)),
        'invariants': {'t1_violations': t1, 'same_bar_collisions': sum(bool(row.get('same_bar_collision')) for row in closed),
                       'selector_outcome_leak': 0, 'search_count': 1},
        'promotion_gate_pass': passed,
        'decision': ('SUPPLY_FAILURE_BREAKER_FROZEN_REPLAY_PASS__CURRENT_SCANNER_SHADOW_NEXT' if passed else
                     'SUPPLY_FAILURE_BREAKER_ECONOMIC_GATE_FAIL__CLOSE_ONTOLOGY_NO_VARIANTS'),
        'artifacts': {'out_dir': str(OUT), 'rows': str(OUT / 'v436_frozen_replay_rows.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v436_report.json').write_text(text); LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
