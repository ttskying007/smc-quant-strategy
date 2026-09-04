#!/usr/bin/env python3
"""One frozen strict-T+1 replay for V577 after independent V578 identity equality."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
DAILY = ROOT / 'kline_cache'
SEED_LATEST = AUDIT / 'v577_lending_short_pressure_smc_squeeze_seed_latest.json'
ORACLE_LATEST = AUDIT / 'v578_v577_independent_raw_oracle_latest.json'
LATEST = AUDIT / 'v579_v577_frozen_strict_t1_replay_latest.json'
OUT = AUDIT / f'v579_v577_frozen_strict_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
YEARS = ('2023', '2024', '2025')
FEE_PCT, HOLD = 0.20, 20
GATE = {'n_min': 1000, 'year_n_min': 300, 'wr_pct_min': 55.0, 'avg_net_pct_min': 0.5,
        'pf_min': 1.15, 'payoff_min': 0.7, 'each_year_avg_net_positive': True, 't1_violations': 0}


def num(value: Any) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) and x > 0 else None
    except (TypeError, ValueError):
        return None


def bars(symbol: str) -> list[dict[str, Any]]:
    try:
        raw = json.loads((DAILY / f'{symbol.replace(".", "_")}_daily_750.json').read_text())
    except (OSError, ValueError):
        return []
    output = []
    for row in raw if isinstance(raw, list) else []:
        date = str(row.get('t') or row.get('date') or '')[:8]
        values = [num(row.get(key)) for key in ('o', 'h', 'l', 'c')]
        if len(date) == 8 and date.isdigit() and all(value is not None for value in values):
            output.append({'d': date, 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3]})
    return sorted(output, key=lambda row: row['d'])


def confirmed_highs(rows: list[dict[str, Any]]) -> list[tuple[int, int, float]]:
    return [
        (i, i + 3, rows[i]['h']) for i in range(3, len(rows) - 3)
        if rows[i]['h'] > max(x['h'] for x in rows[i - 3:i])
        and rows[i]['h'] >= max(x['h'] for x in rows[i + 1:i + 4])
    ]


def structural_target(rows: list[dict[str, Any]], signal_i: int, entry: float, stop: float) -> float | None:
    minimum = entry + (entry - stop) * 1.5
    candidates = []
    for _, confirmed_i, high in confirmed_highs(rows):
        if confirmed_i > signal_i or high < minimum:
            continue
        if any(row['h'] >= high for row in rows[confirmed_i + 1:signal_i + 1]):
            continue
        candidates.append(high)
    return min(candidates) if candidates else None


def exit_trade(rows: list[dict[str, Any]], entry_i: int, entry: float, stop: float, target: float) -> tuple[int, str, float, str]:
    last = min(entry_i + HOLD, len(rows) - 1)
    for i in range(entry_i + 1, last + 1):
        bar = rows[i]
        if bar['o'] <= stop:
            return i, bar['d'], bar['o'], 'SL_GAP_T1'
        if bar['o'] >= target:
            return i, bar['d'], bar['o'], 'TP_GAP_T1'
        if bar['l'] <= stop and bar['h'] >= target:
            return i, bar['d'], stop, 'SL_TP_COLLISION_CONSERVATIVE_T1'
        if bar['l'] <= stop:
            return i, bar['d'], stop, 'SL_T1'
        if bar['h'] >= target:
            return i, bar['d'], target, 'TP_STRUCTURAL_T1'
    return last, rows[last]['d'], rows[last]['c'], 'TIME20'


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnl = [row['net_pnl_pct'] for row in rows]
    wins, losses = [x for x in pnl if x > 0], [x for x in pnl if x <= 0]
    return {
        'n': len(pnl),
        'wr_pct': round(100 * len(wins) / len(pnl), 4) if pnl else 0.0,
        'avg_net_pct': round(mean(pnl), 4) if pnl else 0.0,
        'profit_factor': round(sum(wins) / abs(sum(losses)), 4) if losses else None,
        'payoff': round(mean(wins) / abs(mean(losses)), 4) if wins and losses else None,
        'total_net_pct': round(sum(pnl), 4),
        'avg_win_pct': round(mean(wins), 4) if wins else None,
        'avg_loss_pct': round(mean(losses), 4) if losses else None,
    }


def main() -> None:
    oracle = json.loads(ORACLE_LATEST.read_text())
    if oracle['decision'] != 'V578_ORACLE_PASS__ONE_FROZEN_STRICT_T1_REPLAY_AUTHORIZED':
        raise RuntimeError('V578 exact Oracle equality is required before replay')
    meta = json.loads(SEED_LATEST.read_text())
    with Path(meta['artifacts']['seeds']).open(newline='', encoding='utf-8') as handle:
        seeds = list(csv.DictReader(handle))
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for seed in seeds:
        grouped[seed['symbol']].append(seed)
    OUT.mkdir(parents=True, exist_ok=False)
    trades: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for count, (symbol, items) in enumerate(sorted(grouped.items()), 1):
        xs = bars(symbol)
        index = {row['d']: i for i, row in enumerate(xs)}
        busy_until = -1
        for seed in sorted(items, key=lambda row: (row['planned_entry_date'], row['lending_date'])):
            signal_i, entry_i = index.get(seed['reclaim_date']), index.get(seed['planned_entry_date'])
            if signal_i is None or entry_i is None or entry_i != signal_i + 1:
                skipped['NO_EXACT_RECLAIM_NEXT_OPEN'] += 1
                continue
            if entry_i <= busy_until:
                skipped['SERIAL_SYMBOL_POSITION_OPEN'] += 1
                continue
            if entry_i + 1 >= len(xs):
                skipped['NO_T1_FORWARD_BAR'] += 1
                continue
            entry, stop = xs[entry_i]['o'], float(seed['zone_low']) * 0.99
            if not 0 < stop < entry:
                skipped['INVALID_STRUCTURAL_STOP'] += 1
                continue
            target = structural_target(xs, signal_i, entry, stop)
            if target is None:
                skipped['NO_UNCONSUMED_PREENTRY_TARGET_RR_1P5'] += 1
                continue
            exit_i, exit_date, exit_price, reason = exit_trade(xs, entry_i, entry, stop, target)
            if exit_i <= entry_i:
                raise RuntimeError('strict T+1 violation')
            busy_until = exit_i
            trades.append({
                'symbol': symbol, 'lending_date': seed['lending_date'], 'signal_date': seed['reclaim_date'],
                'entry_date': xs[entry_i]['d'], 'entry_price': round(entry, 8), 'stop_price': round(stop, 8),
                'target_price': round(target, 8), 'planned_rr': round((target - entry) / (entry - stop), 6),
                'exit_date': exit_date, 'exit_price': round(exit_price, 8), 'exit_reason': reason,
                'hold_bars': exit_i - entry_i, 'net_pnl_pct': round((exit_price / entry - 1) * 100 - FEE_PCT, 6),
                'execution_contract': 'PIT_LENDING_D_PRIOR>BSL_ACCEPTANCE>DEMAND_RECLAIM>D_PLUS_1_OPEN>STRICT_T1_STRUCTURE_SL_TP_TIME20_FEE0P2',
            })
        if count % 500 == 0:
            print(json.dumps({'symbols': count, 'trades': len(trades)}), flush=True)
    overall = metrics(trades)
    yearly = {year: metrics([row for row in trades if row['entry_date'].startswith(year)]) for year in YEARS}
    exits = Counter(row['exit_reason'] for row in trades)
    checks = {
        'n>=1000': overall['n'] >= GATE['n_min'],
        'each_year_n>=300': all(yearly[year]['n'] >= GATE['year_n_min'] for year in YEARS),
        'wr>=55': overall['wr_pct'] >= GATE['wr_pct_min'],
        'avg_net>=0.5': overall['avg_net_pct'] >= GATE['avg_net_pct_min'],
        'pf>=1.15': (overall['profit_factor'] or 0) >= GATE['pf_min'],
        'payoff>=0.7': (overall['payoff'] or 0) >= GATE['payoff_min'],
        'each_year_avg_net>0': all(yearly[year]['avg_net_pct'] > 0 for year in YEARS),
        't1_violations==0': True,
    }
    trades_path = OUT / 'v579_frozen_t1_trades.csv'
    with trades_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(trades[0]) if trades else ['symbol'])
        writer.writeheader()
        writer.writerows(trades)
    passed = all(checks.values())
    report = {
        'version': 'V579_V577_ONE_FROZEN_STRICT_T1_REPLAY', 'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'input_contract': 'V577 outcome-blind lending+SMC seeds after V578 exact independent raw Oracle identity equality.',
        'frozen_execution_contract': 'entry=first daily open after reclaim; stop=demand POI low*0.99; target=nearest unconsumed pre-entry right-confirmed daily swing high with RR>=1.5; exits start entry+1 only; gap-aware conservative stop-first collision; time20; fee0.20%; serial positions.',
        'seed_count': len(seeds), 'closed_trade_count': len(trades), 'skip_counts': dict(skipped),
        'overall': overall, 'yearly': yearly, 'exit_reason_counts': dict(exits), 'promotion_gate': GATE,
        'promotion_checks': checks,
        'invariants': {'oracle_identity_pass': True, 'all_targets_preentry': all(row['planned_rr'] >= 1.5 for row in trades), 't1_violations': 0, 'all_writes_false': True, 'search_count': 1},
        'decision': 'V579_RESEARCH_GATE_PASS__INDEPENDENT_METRIC_AUDIT_REQUIRED' if passed else 'V579_FROZEN_REPLAY_GATE_FAIL__CLOSE_V577_ONTOLOGY_NO_VARIANTS',
        'artifacts': {'out_dir': str(OUT), 'trades': str(trades_path), 'latest': str(LATEST), 'v577': str(SEED_LATEST), 'v578': str(ORACLE_LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v579_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
