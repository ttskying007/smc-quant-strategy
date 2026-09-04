#!/usr/bin/env python3
"""V358 research-only daily executable replay for V354 identity-collapsed persistent takeovers.

Fixed, source-safe contract (not a parameter search):
- input only V354 identity-collapsed PERSISTENT_TAKEOVER rows;
- persistence is known at the close of takeover + 2 daily bars;
- buy at the following daily open; this is necessarily after confirmation;
- structural stop = OB zone_low with a fixed 1% execution buffer;
- target = nearest already-confirmed swing high above entry, otherwise TIME30;
- first legal exit is the next daily bar (A-share T+1 hard gate);
- stop gaps exit at the opening price, and ambiguous same-bar SL/TP is conservative SL.

This produces an individual-setup replay, not a capital-constrained portfolio.
It writes only timestamped research artifacts under smc_audit.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
KDIR = ROOT / 'kline_cache'
SRC = AUD / 'v354_lifecycle_setup_identity_latest.json'
STAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUD / f'v358_unique_persistent_takeover_daily_t1_replay_no_write_{STAMP}'
LATEST = AUD / 'v358_unique_persistent_takeover_daily_t1_replay_latest.json'
HOLD_BARS = 30
STOP_BUFFER = 0.99


def f(x: object) -> float:
    try:
        value = float(x)
        return value if math.isfinite(value) else 0.0
    except (TypeError, ValueError):
        return 0.0


def date_of(bar: dict) -> str:
    return ''.join(c for c in str(bar.get('t') or bar.get('date') or '') if c.isdigit())[:8]


def load_bars(symbol: str) -> list[dict]:
    path = KDIR / f"{symbol.replace('.', '_')}_daily_750.json"
    try:
        rows = json.loads(path.read_text())
    except Exception:
        return []
    return sorted((row for row in rows if date_of(row)), key=date_of)


def confirmed_swing_high_target(bars: list[dict], confirmation_idx: int, entry: float) -> tuple[float | None, str]:
    """Nearest high that was confirmed by the information cutoff, never future data."""
    candidates: list[tuple[float, str]] = []
    # 3-left / 3-right confirmation means a swing at i is known only at i+3.
    for i in range(3, max(3, confirmation_idx - 2)):
        if i + 3 > confirmation_idx:
            break
        high = f(bars[i].get('h'))
        if high <= entry:
            continue
        if all(high > f(bars[j].get('h')) for j in range(i - 3, i)) and all(high >= f(bars[j].get('h')) for j in range(i + 1, i + 4)):
            candidates.append((high, date_of(bars[i])))
    return min(candidates, key=lambda item: item[0]) if candidates else (None, '')


def replay(bars: list[dict], row: dict) -> dict:
    by_date = {date_of(bar): i for i, bar in enumerate(bars)}
    takeover_idx = by_date.get(row.get('takeover_date', ''))
    if takeover_idx is None:
        return {'status': 'UNREPLAYABLE_TAKEOVER_DATE_MISSING'}
    confirmation_idx = takeover_idx + 2
    entry_idx = confirmation_idx + 1
    if entry_idx >= len(bars):
        return {'status': 'UNREPLAYABLE_ENTRY_UNOBSERVED'}

    entry = f(bars[entry_idx].get('o'))
    zone_low, zone_high = f(row.get('zone_low')), f(row.get('zone_high'))
    sl = zone_low * STOP_BUFFER
    if entry <= 0 or sl <= 0 or sl >= entry:
        return {'status': 'UNREPLAYABLE_NONPOSITIVE_RISK', 'entry_price': entry, 'sl': sl}

    target, target_date = confirmed_swing_high_target(bars, confirmation_idx, entry)
    first_exit = entry_idx + 1  # strict T+1: never inspect entry-day H/L/C for exit
    if first_exit >= len(bars):
        return {'status': 'OPEN_RIGHT_EDGE', 'entry_idx': entry_idx, 'entry_date': date_of(bars[entry_idx]), 'entry_price': entry, 'sl': sl}
    last_idx = min(len(bars) - 1, entry_idx + HOLD_BARS)
    if last_idx < entry_idx + HOLD_BARS:
        return {'status': 'OPEN_RIGHT_EDGE', 'entry_idx': entry_idx, 'entry_date': date_of(bars[entry_idx]), 'entry_price': entry, 'sl': sl}

    exit_idx, exit_price, exit_reason = last_idx, f(bars[last_idx].get('c')), 'TIME30_NO_CONFIRMED_BSL' if target is None else 'TIME30_BSL_UNREACHED'
    collision = False
    for i in range(first_exit, last_idx + 1):
        bar = bars[i]
        op, low, high = f(bar.get('o')), f(bar.get('l')), f(bar.get('h'))
        if op <= sl:
            exit_idx, exit_price, exit_reason = i, op, 'SL_GAP_T1'
            break
        hit_sl, hit_tp = low <= sl, target is not None and high >= target
        if hit_sl and hit_tp:
            exit_idx, exit_price, exit_reason, collision = i, sl, 'SL_TP_SAME_BAR_CONSERVATIVE_SL_T1', True
            break
        if hit_sl:
            exit_idx, exit_price, exit_reason = i, sl, 'STRUCTURE_SL_T1'
            break
        if hit_tp:
            exit_idx, exit_price, exit_reason = i, max(op, target), 'CONFIRMED_BSL_TP_T1'
            break

    path = bars[entry_idx:exit_idx + 1]
    mfe = (max(f(b.get('h')) for b in path) / entry - 1) * 100
    mae = (min(f(b.get('l')) for b in path) / entry - 1) * 100
    pnl = (exit_price / entry - 1) * 100
    exit_date = date_of(bars[exit_idx])
    return {
        'status': 'CLOSED',
        'confirmation_idx': confirmation_idx,
        'confirmation_date': date_of(bars[confirmation_idx]),
        'entry_idx': entry_idx,
        'entry_date': date_of(bars[entry_idx]),
        'entry_price': round(entry, 4),
        'sl': round(sl, 4),
        'risk_pct': round((entry / sl - 1) * 100, 4),
        'tp': round(target, 4) if target is not None else None,
        'tp_anchor_date': target_date,
        'exit_idx': exit_idx,
        'exit_date': exit_date,
        'exit_price': round(exit_price, 4),
        'exit_reason': exit_reason,
        'hold_bars': exit_idx - entry_idx,
        'pnl_pct': round(pnl, 4),
        'mfe_pct': round(mfe, 4),
        'mae_pct': round(mae, 4),
        'rr_realized': round(pnl / ((entry / sl - 1) * 100), 4),
        't1_violation': exit_date <= date_of(bars[entry_idx]),
        'same_bar_sl_tp_collision': collision,
    }


def metrics(rows: list[dict]) -> dict:
    closed = [r for r in rows if r.get('status') == 'CLOSED']
    if not closed:
        return {'n': 0}
    pnls = [f(r['pnl_pct']) for r in closed]
    wins = [p for p in pnls if p > 0]
    by_year: dict[str, list[dict]] = defaultdict(list)
    by_month: dict[str, list[dict]] = defaultdict(list)
    for row in closed:
        by_year[row['entry_date'][:4]].append(row)
        by_month[row['entry_date'][:6]].append(row)
    def brief(group: list[dict]) -> dict:
        ps = [f(x['pnl_pct']) for x in group]
        stop_reasons = {'SL_GAP_T1', 'STRUCTURE_SL_T1', 'SL_TP_SAME_BAR_CONSERVATIVE_SL_T1'}
        return {'n': len(group), 'wr_pct': round(sum(p > 0 for p in ps) / len(ps) * 100, 4), 'avg_pnl_pct': round(sum(ps) / len(ps), 4), 'median_pnl_pct': round(sorted(ps)[len(ps)//2], 4), 'sl_pct': round(sum(x['exit_reason'] in stop_reasons for x in group) / len(group) * 100, 4)}
    return {
        'n': len(closed),
        'wr_pct': round(len(wins) / len(closed) * 100, 4),
        'avg_pnl_pct': round(sum(pnls) / len(pnls), 4),
        'median_pnl_pct': round(sorted(pnls)[len(pnls)//2], 4),
        'avg_mfe_pct': round(sum(f(r['mfe_pct']) for r in closed) / len(closed), 4),
        'avg_mae_pct': round(sum(f(r['mae_pct']) for r in closed) / len(closed), 4),
        'yearly': {key: brief(value) for key, value in sorted(by_year.items())},
        'monthly': {key: brief(value) for key, value in sorted(by_month.items())},
        'exit_reason_counts': dict(Counter(r['exit_reason'] for r in closed)),
        't1_violations': sum(bool(r.get('t1_violation')) for r in closed),
        'same_bar_sl_tp_collisions': sum(bool(r.get('same_bar_sl_tp_collision')) for r in closed),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads(SRC.read_text())
    # V354 materializes setup identity under `unique_paths`, not generic `rows`.
    with Path(report['artifacts']['unique_paths']).open() as handle:
        source_rows = [r for r in csv.DictReader(handle) if r.get('lifecycle_state') == 'PERSISTENT_TAKEOVER']
    cache: dict[str, list[dict]] = {}
    rows: list[dict] = []
    for row in source_rows:
        symbol = row['symbol']
        if symbol not in cache:
            cache[symbol] = load_bars(symbol)
        result = replay(cache[symbol], row)
        rows.append({
            'symbol': symbol, 'event_date': row.get('event_date', ''), 'event_idx': row.get('event_idx', ''),
            'ob_idx': row.get('ob_idx', ''), 'ob_date': row.get('ob_date', ''), 'zone_low': row.get('zone_low', ''), 'zone_high': row.get('zone_high', ''),
            'touch_date': row.get('touch_date', ''), 'reclaim_date': row.get('reclaim_date', ''), 'takeover_date': row.get('takeover_date', ''),
            'lifecycle_state': row.get('lifecycle_state', ''), 'execution_contract': 'V358_UNIQUE_PERSISTENT_TAKEOVER_DAILY_T1',
            'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False, **result,
        })
    fields = sorted({key for row in rows for key in row})
    with (OUT / 'v358_unique_daily_t1_replay_rows.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    result = {
        'version': 'V358_UNIQUE_PERSISTENT_TAKEOVER_DAILY_T1_REPLAY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'input_contract': 'V354 identity-collapsed PERSISTENT_TAKEOVER only',
        'execution_contract': {'confirmation': 'takeover close plus two additional closes > zone_high', 'entry': 'next daily open after confirmation', 'stop': 'zone_low * 0.99', 'target': 'nearest already-confirmed 3-left/3-right swing high above entry; otherwise time exit', 'exit': 'first legal bar is entry+1, 30 daily bars maximum, gap-aware stop, same-bar collision uses conservative stop'},
        'source_rows': len(source_rows),
        'status_counts': dict(Counter(r.get('status') for r in rows)),
        'metrics': metrics(rows),
        'invariants': {'t1_violations': sum(bool(r.get('t1_violation')) for r in rows), 'all_source_rows_persistent': all(r['lifecycle_state'] == 'PERSISTENT_TAKEOVER' for r in rows), 'no_production_writes': True},
        'artifacts': {'out_dir': str(OUT), 'rows': str(OUT / 'v358_unique_daily_t1_replay_rows.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v358_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
