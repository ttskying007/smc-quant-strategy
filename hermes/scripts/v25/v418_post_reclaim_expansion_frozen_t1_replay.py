#!/usr/bin/env python3
"""V418 one-shot frozen T+1 replay for V417 post-reclaim expansion.

Execution is fixed before outcomes: next-session open after expansion; no exit on
entry day; SL 0.5% below the flip-zone low; TP at the nearest higher confirmed
swing liquidity visible by expansion; 20-session time exit. Per-symbol execution
is serial within each combination. No parameter, threshold, or exit search.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median

ROOT = Path('/root/.hermes')
AUD, KDIR = ROOT / 'smc_audit', ROOT / 'kline_cache'
SOURCE = AUD / 'v417_post_reclaim_expansion_lifecycle_latest.json'
OUT = AUD / f'v418_post_reclaim_expansion_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v418_post_reclaim_expansion_frozen_t1_replay_latest.json'
MAX_HOLD = 20
FEE_PCT = 0.15

spec = importlib.util.spec_from_file_location('v27', ROOT / 'scripts/v25/smc_core_v27.py')
v27 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v27)


def f(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else 0.0
    except (TypeError, ValueError):
        return 0.0


def day(bar):
    return ''.join(c for c in str(bar.get('t') or bar.get('date') or '') if c.isdigit())[:8]


def load(symbol):
    path = KDIR / f"{symbol.replace('.', '_')}_daily_750.json"
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return []
    bars = [b for b in raw if day(b) and all(f(b.get(k)) > 0 for k in ('o', 'h', 'l', 'c'))]
    return sorted(bars, key=day)


def target_before_entry(swings, signal_idx, entry_price):
    candidates = [(f(x['price']), int(x['confirm_idx'])) for x in swings.get('highs', [])
                  if int(x['confirm_idx']) <= signal_idx and f(x['price']) > entry_price]
    return min(candidates, key=lambda x: x[0]) if candidates else (0.0, None)


def simulate(seed, bars, swings):
    signal_idx = int(seed['expansion_idx'])
    entry_idx = signal_idx + 1
    if entry_idx >= len(bars):
        return None, 'NO_T1_ENTRY_BAR'
    if entry_idx + 1 >= len(bars):
        return None, 'NO_T1_EXIT_WINDOW'
    entry = f(bars[entry_idx].get('o'))
    zone_low = f(seed['zone_low'])
    if entry <= 0 or zone_low <= 0:
        return None, 'INVALID_ENTRY_OR_ZONE'
    sl = zone_low * 0.995
    if sl >= entry:
        return None, 'SL_NOT_BELOW_ENTRY'
    tp, target_confirm_idx = target_before_entry(swings, signal_idx, entry)
    risk = entry - sl
    planned_rr = (tp - entry) / risk if tp > entry else None
    exit_idx = min(len(bars) - 1, entry_idx + MAX_HOLD)
    exit_price = f(bars[exit_idx].get('c'))
    exit_reason = 'TIME_EXIT_20B' if exit_idx == entry_idx + MAX_HOLD else 'DATA_END_EXIT'
    mfe = 0.0
    mae = 0.0
    # Entry day is deliberately excluded: A-share T+1.
    for idx in range(entry_idx + 1, exit_idx + 1):
        high, low = f(bars[idx].get('h')), f(bars[idx].get('l'))
        mfe = max(mfe, (high / entry - 1) * 100)
        mae = min(mae, (low / entry - 1) * 100)
        hit_sl = low <= sl
        hit_tp = tp > entry and high >= tp
        if hit_sl or hit_tp:
            # Pessimistic same-bar ordering avoids optimistic OHLC ambiguity.
            if hit_sl:
                exit_price, exit_reason = sl, 'SL_HIT'
            else:
                exit_price, exit_reason = tp, 'STRUCTURAL_TP_HIT'
            exit_idx = idx
            break
    gross = (exit_price / entry - 1) * 100
    pnl = gross - FEE_PCT
    row = {
        **seed,
        'entry_idx': entry_idx,
        'entry_date': day(bars[entry_idx]),
        'entry_price': round(entry, 6),
        'sl_price': round(sl, 6),
        'tp_price': round(tp, 6) if tp > 0 else '',
        'target_confirm_idx': '' if target_confirm_idx is None else target_confirm_idx,
        'planned_rr': round(planned_rr, 6) if planned_rr is not None else '',
        'exit_idx': exit_idx,
        'exit_date': day(bars[exit_idx]),
        'exit_price': round(exit_price, 6),
        'exit_reason': exit_reason,
        'hold_bars': exit_idx - entry_idx,
        'gross_pnl_pct': round(gross, 6),
        'fee_pct': FEE_PCT,
        'pnl_pct': round(pnl, 6),
        'realized_r': round((exit_price - entry) / risk, 6),
        'mfe_pct': round(mfe, 6),
        'mae_pct': round(mae, 6),
        't1_violation': False,
    }
    return row, None


def metrics(rows):
    if not rows:
        return {'n': 0}
    pnl = [f(r['pnl_pct']) for r in rows]
    wins = [x for x in pnl if x > 0]
    losses = [x for x in pnl if x <= 0]
    planned = [f(r['planned_rr']) for r in rows if str(r.get('planned_rr', '')).strip()]
    realized = [f(r['realized_r']) for r in rows]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        'n': len(rows),
        'win_rate_pct': round(len(wins) / len(rows) * 100, 4),
        'net_success_ge_0_8_pct': round(sum(x >= 0.8 for x in pnl) / len(rows) * 100, 4),
        'avg_pnl_pct': round(mean(pnl), 4),
        'median_pnl_pct': round(median(pnl), 4),
        'sum_pnl_pct': round(sum(pnl), 4),
        'profit_factor': round(gross_profit / gross_loss, 4) if gross_loss else None,
        'avg_win_pct': round(mean(wins), 4) if wins else None,
        'avg_loss_pct': round(mean(losses), 4) if losses else None,
        'payoff_ratio': round(mean(wins) / abs(mean(losses)), 4) if wins and losses and mean(losses) else None,
        'planned_rr_median': round(median(planned), 4) if planned else None,
        'realized_r_avg': round(mean(realized), 4),
        'sl_rate_pct': round(sum(r['exit_reason'] == 'SL_HIT' for r in rows) / len(rows) * 100, 4),
        'tp_rate_pct': round(sum(r['exit_reason'] == 'STRUCTURAL_TP_HIT' for r in rows) / len(rows) * 100, 4),
        'time_exit_rate_pct': round(sum('EXIT' in r['exit_reason'] for r in rows) / len(rows) * 100, 4),
        'avg_hold_bars': round(mean(int(r['hold_bars']) for r in rows), 4),
        't1_violations': sum(bool(r['t1_violation']) for r in rows),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads(SOURCE.read_text())
    with open(source['artifacts']['rows'], newline='', encoding='utf-8') as handle:
        seeds = [r for r in csv.DictReader(handle) if r['lifecycle_state'] == 'TAKEOVER_CONFIRMED']

    cache, swing_cache = {}, {}
    grouped = defaultdict(list)
    for seed in seeds:
        grouped[(seed['combo_key'], seed['symbol'])].append(seed)

    rows, skipped = [], Counter()
    for (combo, symbol), group in grouped.items():
        if symbol not in cache:
            cache[symbol] = load(symbol)
            swing_cache[symbol] = v27.confirmed_swings([dict(x) for x in cache[symbol]]) if cache[symbol] else {'highs': [], 'lows': []}
        bars, swings = cache[symbol], swing_cache[symbol]
        busy_until = -1
        for seed in sorted(group, key=lambda x: int(x['expansion_idx'])):
            prospective_entry = int(seed['expansion_idx']) + 1
            if prospective_entry <= busy_until:
                skipped['SERIAL_OVERLAP'] += 1
                continue
            row, reason = simulate(seed, bars, swings)
            if row is None:
                skipped[reason] += 1
                continue
            rows.append(row)
            busy_until = int(row['exit_idx'])

    fields = list(rows[0]) if rows else ['symbol', 'combo_key']
    rows_path = OUT / 'v418_trade_rows.csv'
    with rows_path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    summary, yearly = {}, {}
    for combo in ('R3_SSL_CHOCH_STRUCTURE_FLIP', 'C2_BOS_STRUCTURE_FLIP'):
        subset = [r for r in rows if r['combo_key'] == combo]
        summary[combo] = metrics(subset)
        yearly[combo] = {year: metrics([r for r in subset if r['entry_date'].startswith(year)])
                         for year in ('2023', '2024', '2025', '2026')}

    report = {
        'version': 'V418_POST_RECLAIM_EXPANSION_FROZEN_T1_REPLAY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'source': str(SOURCE),
        'execution_contract': 'post-reclaim expansion -> next-session open; entry-day exit forbidden; SL=zone_low*0.995; TP=nearest higher confirmed swing visible by expansion; SL-first on ambiguous bar; time exit=20 sessions; fee=0.15%; serial per symbol/combo',
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'expansion_seeds': len(seeds),
        'trades': len(rows),
        'skipped': dict(skipped),
        'summary': summary,
        'yearly': yearly,
        'exit_reasons': dict(Counter(r['exit_reason'] for r in rows)),
        'invariants': {
            't1_violations': sum(r['entry_date'] == r['exit_date'] for r in rows),
            'negative_time_order': sum(not (int(r['event_idx']) < int(r['touch_idx']) <= int(r['reclaim_idx']) < int(r['takeover_idx']) < int(r['expansion_idx']) < int(r['entry_idx']) <= int(r['exit_idx'])) for r in rows),
            'future_target_violation': sum(bool(str(r['target_confirm_idx']).strip()) and int(r['target_confirm_idx']) > int(r['expansion_idx']) for r in rows),
            'outcome_parameter_search': False,
            'serial_overlap_remaining': 0,
        },
        'decision': 'REPLAY_COMPLETE__RUN_STABILITY_AND_MECHANISM_AUDIT',
        'artifacts': {'out_dir': str(OUT), 'rows': str(rows_path), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v418_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
