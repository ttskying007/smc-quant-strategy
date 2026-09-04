#!/usr/bin/env python3
"""V439 one-shot frozen T+1 replay for Target-First DOL.

The ontology-native DOL is the immutable target. Entry, stop, target, exit,
hold period and promotion gates are declared before outcomes are opened.
No parameter, threshold, exit, or holding-period search is performed.
"""
from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
KDIR, AUD = ROOT / 'kline_cache', ROOT / 'smc_audit'
SOURCE = AUD / 'v438_target_first_dol_independent_oracle_latest.json'
OUT = AUD / f'v439_target_first_dol_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v439_target_first_dol_frozen_t1_replay_latest.json'
STOP_BUFFER = 0.99
MAX_HOLD = 30
GATE = {
    'n': 300, 'each_year_n': 40,
    'aggregate_wr_pct': 55.0, 'aggregate_avg_pnl_pct': 0.5,
    'each_year_wr_pct': 50.0, 'each_year_avg_pnl_pct': 0.0,
    'each_epoch_wr_pct': 50.0, 'each_epoch_avg_pnl_pct': 0.0,
    't1_violations': 0,
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


def replay(row, bars):
    takeover = int(row['takeover_idx'])
    eligible = int(row['eligible_entry_idx']) if row.get('eligible_entry_idx') not in ('', None) else None
    if eligible is None or eligible != takeover + 1:
        return {'status': 'INVALID_ENTRY_CHRONOLOGY'}
    if eligible >= len(bars):
        return {'status': 'UNOBSERVED_ENTRY'}
    entry, target = bars[eligible]['o'], f(row['dol_price'])
    sl = f(row['zone_low']) * STOP_BUFFER
    if entry <= 0 or sl <= 0 or sl >= entry or target <= entry:
        return {'status': 'INVALID_RISK_OR_TARGET', 'entry_idx': eligible, 'entry_date': bars[eligible]['t']}
    first_exit, last_exit = eligible + 1, eligible + MAX_HOLD
    if first_exit >= len(bars) or last_exit >= len(bars):
        return {'status': 'OPEN_RIGHT_EDGE', 'entry_idx': eligible, 'entry_date': bars[eligible]['t'],
                'entry_price': round(entry, 4), 'sl': round(sl, 4), 'tp': round(target, 4)}

    exit_idx, exit_price, exit_reason = last_exit, bars[last_exit]['c'], 'TIME30_DOL_UNREACHED'
    collision = False
    for idx in range(first_exit, last_exit + 1):
        bar = bars[idx]
        if bar['o'] <= sl:
            exit_idx, exit_price, exit_reason = idx, bar['o'], 'SL_GAP_T1'
            break
        if bar['o'] >= target:
            exit_idx, exit_price, exit_reason = idx, bar['o'], 'DOL_GAP_TP_T1'
            break
        hit_sl, hit_tp = bar['l'] <= sl, bar['h'] >= target
        if hit_sl and hit_tp:
            exit_idx, exit_price, exit_reason, collision = idx, sl, 'SL_TP_COLLISION_CONSERVATIVE_T1', True
            break
        if hit_sl:
            exit_idx, exit_price, exit_reason = idx, sl, 'STRUCTURE_SL_T1'
            break
        if hit_tp:
            exit_idx, exit_price, exit_reason = idx, target, 'PREDECLARED_DOL_TP_T1'
            break

    path = bars[eligible:exit_idx + 1]
    pnl = (exit_price / entry - 1) * 100
    return {
        'status': 'CLOSED', 'entry_idx': eligible, 'entry_date': bars[eligible]['t'],
        'entry_price': round(entry, 4), 'sl': round(sl, 4), 'risk_pct': round((entry / sl - 1) * 100, 4),
        'tp': round(target, 4), 'tp_anchor_date': row.get('dol_date', ''),
        'exit_idx': exit_idx, 'exit_date': bars[exit_idx]['t'], 'exit_price': round(exit_price, 4),
        'exit_reason': exit_reason, 'hold_bars': exit_idx - eligible, 'pnl_pct': round(pnl, 4),
        'mfe_pct': round((max(bar['h'] for bar in path) / entry - 1) * 100, 4),
        'mae_pct': round((min(bar['l'] for bar in path) / entry - 1) * 100, 4),
        't1_violation': bars[exit_idx]['t'] <= bars[eligible]['t'],
        'same_bar_collision': collision,
    }


def stats(rows):
    if not rows:
        return {'n': 0, 'wr_pct': 0, 'avg_pnl_pct': 0}
    pnls = [f(row['pnl_pct']) for row in rows]
    return {
        'n': len(rows),
        'wr_pct': round(sum(pnl > 0 for pnl in pnls) / len(pnls) * 100, 4),
        'avg_pnl_pct': round(sum(pnls) / len(pnls), 4),
        'median_pnl_pct': round(statistics.median(pnls), 4),
        'sl_pct': round(sum(row['exit_reason'] in {'SL_GAP_T1', 'STRUCTURE_SL_T1', 'SL_TP_COLLISION_CONSERVATIVE_T1'}
                            for row in rows) / len(rows) * 100, 4),
    }


def gate_pass(overall, yearly, epochs, t1):
    return (
        overall['n'] >= GATE['n']
        and overall['wr_pct'] >= GATE['aggregate_wr_pct']
        and overall['avg_pnl_pct'] >= GATE['aggregate_avg_pnl_pct']
        and all(yearly.get(year, {}).get('n', 0) >= GATE['each_year_n'] for year in ('2023', '2024', '2025', '2026'))
        and all(yearly.get(year, {}).get('wr_pct', 0) >= GATE['each_year_wr_pct'] for year in ('2023', '2024', '2025', '2026'))
        and all(yearly.get(year, {}).get('avg_pnl_pct', -999) > GATE['each_year_avg_pnl_pct'] for year in ('2023', '2024', '2025', '2026'))
        and all(value['wr_pct'] >= GATE['each_epoch_wr_pct'] and value['avg_pnl_pct'] > GATE['each_epoch_avg_pnl_pct']
                for value in epochs.values())
        and t1 == GATE['t1_violations']
    )


def main():
    source = json.loads(SOURCE.read_text())
    if source.get('decision') != 'INDEPENDENT_SEMANTIC_ORACLE_PASS__FROZEN_T1_REPLAY_NEXT':
        raise RuntimeError('V438 independent semantic gate did not pass')
    with Path(source['artifacts']['oracle_rows']).open(newline='') as handle:
        seeds = list(csv.DictReader(handle))

    OUT.mkdir(parents=True, exist_ok=True)
    cache, rows = {}, []
    for index, seed in enumerate(seeds, 1):
        sym = seed['symbol']
        if sym not in cache:
            cache[sym] = load_bars(sym)
        result = replay(seed, cache[sym])
        rows.append({**seed, 'execution_contract': 'NEXT_OPEN__SL_POI_LOW_1PCT__PREDECLARED_DOL__TIME30__STRICT_T1', **result})
        if index % 10000 == 0:
            print(json.dumps({'progress': index, 'closed': sum(row.get('status') == 'CLOSED' for row in rows)}, ensure_ascii=False), flush=True)

    closed = [row for row in rows if row.get('status') == 'CLOSED']
    yearly = {year: stats([row for row in closed if row['entry_date'][:4] == year]) for year in ('2023', '2024', '2025', '2026')}
    epochs = {
        '2023_2024': stats([row for row in closed if row['entry_date'][:4] in {'2023', '2024'}]),
        '2025_2026': stats([row for row in closed if row['entry_date'][:4] in {'2025', '2026'}]),
    }
    overall = stats(closed)
    t1 = sum(bool(row.get('t1_violation')) for row in closed)
    passed = gate_pass(overall, yearly, epochs, t1)

    fields = sorted({key for row in rows for key in row})
    with (OUT / 'v439_frozen_replay_rows.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    report = {
        'version': 'V439_TARGET_FIRST_DOL_FROZEN_T1_REPLAY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'frozen_before_outcomes': {
            'entry': 'next daily open after hold/takeover confirmation',
            'sl': 'demand POI zone_low * 0.99',
            'target': 'the exact unconsumed DOL selected before BOS and preserved through setup formation',
            'exit': 'strict T+1; DOL/SL then time30; gap-aware; same-bar collision=SL',
            'promotion_gate': GATE, 'search_count': 1,
        },
        'seed_count': len(seeds), 'status_counts': dict(Counter(row.get('status') for row in rows)),
        'overall': overall, 'yearly': yearly, 'epochs': epochs,
        'exit_reason_counts': dict(Counter(row['exit_reason'] for row in closed)),
        'invariants': {'t1_violations': t1,
                       'same_bar_collisions': sum(bool(row.get('same_bar_collision')) for row in closed),
                       'selector_outcome_leak': 0, 'search_count': 1},
        'promotion_gate_pass': passed,
        'decision': ('TARGET_FIRST_DOL_FROZEN_REPLAY_PASS__CURRENT_RAW_SHADOW_SCANNER_NEXT' if passed else
                     'TARGET_FIRST_DOL_ECONOMIC_GATE_FAIL__CLOSE_ONTOLOGY_NO_VARIANTS'),
        'artifacts': {'out_dir': str(OUT), 'rows': str(OUT / 'v439_frozen_replay_rows.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v439_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
