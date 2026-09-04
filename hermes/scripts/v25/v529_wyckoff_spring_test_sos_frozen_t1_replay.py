#!/usr/bin/env python3
"""V529 one frozen strict-T+1 replay for the independently verified V527 ontology."""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
KDIR = ROOT / 'kline_cache'
V527 = AUD / 'v527_wyckoff_spring_test_sos_seed_gate_latest.json'
V528 = AUD / 'v528_wyckoff_spring_test_sos_independent_oracle_latest.json'
OUT = AUD / f'v529_wyckoff_spring_test_sos_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v529_wyckoff_spring_test_sos_frozen_t1_replay_latest.json'
LEFT = RIGHT = 3
STOP_BUFFER = 0.99
MAX_HOLD = 20
FEE_PCT = 0.20
YEARS = ('2023', '2024', '2025', '2026')
GATE = {
    'n_min': 300, 'year_n_min': 40, 'gross_wr_pct_min': 60.0,
    'avg_net_pnl_pct_min': 0.75, 'pf_min': 1.30, 'payoff_min': 1.00,
    'year_avg_net_pnl_pct_min': 0.0,
}


def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if result > 0 else None
    except (TypeError, ValueError):
        return None


def day(value: Any) -> str:
    digits = ''.join(char for char in str(value or '') if char.isdigit())
    return digits[:8] if len(digits) >= 8 else ''


def load_bars(symbol: str) -> list[dict[str, Any]]:
    code, exchange = symbol.split('.')
    try:
        raw = json.loads((KDIR / f'{code}_{exchange}_daily_750.json').read_text())
    except Exception:
        return []
    result = []
    for item in raw if isinstance(raw, list) else []:
        date = day(item.get('t') or item.get('date') or item.get('day'))
        values = [number(item.get(field)) for field in ('o', 'h', 'l', 'c')]
        if date and all(value is not None for value in values):
            result.append(dict(zip(('t', 'o', 'h', 'l', 'c'), (date, *values))))
    return sorted(result, key=lambda row: row['t'])


def confirmed_high(bars: list[dict[str, Any]], index: int) -> bool:
    if index < LEFT or index + RIGHT >= len(bars):
        return False
    high = bars[index]['h']
    return (high > max(bars[j]['h'] for j in range(index - LEFT, index))
            and high >= max(bars[j]['h'] for j in range(index + 1, index + RIGHT + 1)))


def visible_target(bars: list[dict[str, Any]], sos_index: int, entry: float) -> tuple[int, float] | None:
    for index in range(sos_index - RIGHT - 1, LEFT - 1, -1):
        if confirmed_high(bars, index) and bars[index]['h'] > entry:
            return index, bars[index]['h']
    return None


def percent(value: float, base: float) -> float:
    return (value / base - 1.0) * 100.0


def replay(seed: dict[str, str], bars: list[dict[str, Any]]) -> dict[str, Any]:
    entry_index, sos_index = int(seed['entry_eligible_idx']), int(seed['sos_idx'])
    if entry_index >= len(bars):
        return {'status': 'SKIP', 'reason': 'NO_ELIGIBLE_BAR'}
    entry = bars[entry_index]['o']
    stop = float(seed['spring_low']) * STOP_BUFFER
    if stop >= entry:
        return {'status': 'SKIP', 'reason': 'INVALID_STRUCTURAL_STOP'}
    target = visible_target(bars, sos_index, entry)
    if target is None:
        return {'status': 'SKIP', 'reason': 'NO_VISIBLE_UPSIDE_TARGET'}
    target_index, target_price = target
    path = bars[entry_index + 1:entry_index + 1 + MAX_HOLD]
    if len(path) < MAX_HOLD:
        return {'status': 'OPEN_DATA', 'reason': 'INSUFFICIENT_FORWARD_BARS'}
    reason, exit_bar, exit_price, hold = 'TIME20', path[-1], path[-1]['c'], MAX_HOLD
    for hold, bar in enumerate(path, 1):
        if bar['o'] <= stop:
            reason, exit_bar, exit_price = 'GAP_SL', bar, bar['o']
            break
        if bar['l'] <= stop:
            reason, exit_bar, exit_price = 'SL', bar, stop
            break
        if bar['h'] >= target_price:
            reason, exit_bar, exit_price = 'TP_STRUCTURAL', bar, target_price
            break
    gross = percent(exit_price, entry)
    risk = entry - stop
    return {
        'status': 'CLOSED', 'reason': reason, 'entry_date': bars[entry_index]['t'],
        'entry_price': round(entry, 6), 'exit_date': exit_bar['t'], 'exit_price': round(exit_price, 6),
        'stop': round(stop, 6), 'target': round(target_price, 6), 'target_swing_idx': target_index,
        'target_swing_date': bars[target_index]['t'], 'hold_bars': hold,
        'gross_pnl_pct': round(gross, 6), 'net_pnl_pct': round(gross - FEE_PCT, 6),
        'mfe_pct': round(percent(max(bar['h'] for bar in path), entry), 6),
        'mae_pct': round(percent(min(bar['l'] for bar in path), entry), 6),
        'mfe_r': round((max(bar['h'] for bar in path) - entry) / risk, 6),
        'mae_r': round((min(bar['l'] for bar in path) - entry) / risk, 6),
        'same_day_exit_violation': bars[entry_index]['t'] == exit_bar['t'],
    }


def measures(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnl = [row['net_pnl_pct'] for row in rows]
    wins, losses = [value for value in pnl if value > 0], [value for value in pnl if value < 0]
    return {
        'n': len(rows), 'gross_wr_pct': round(100 * len(wins) / len(rows), 4) if rows else 0.0,
        'avg_net_pnl_pct': round(sum(pnl) / len(rows), 4) if rows else 0.0,
        'avg_win_pct': round(sum(wins) / len(wins), 4) if wins else 0.0,
        'avg_loss_pct': round(sum(losses) / len(losses), 4) if losses else 0.0,
        'payoff_rr': round((sum(wins) / len(wins)) / abs(sum(losses) / len(losses)), 4) if wins and losses else 0.0,
        'profit_factor': round(sum(wins) / abs(sum(losses)), 4) if losses else 0.0,
        'total_net_pnl_pct': round(sum(pnl), 4), 'exit_counts': dict(Counter(row['reason'] for row in rows)),
    }


def main() -> None:
    source, oracle = json.loads(V527.read_text()), json.loads(V528.read_text())
    if not source.get('support_gate_pass') or not oracle.get('oracle_pass') or oracle.get('outcomes_opened'):
        raise RuntimeError('V527 support and V528 independent oracle must pass before replay')
    with Path(source['artifacts']['seeds']).open(newline='', encoding='utf-8') as handle:
        seeds = list(csv.DictReader(handle))
    seeds.sort(key=lambda row: (row['entry_eligible_date'], row['symbol'], int(row['spring_idx'])))
    cache: dict[str, list[dict[str, Any]]] = {}
    busy_until: dict[str, str] = {}
    closed, skipped, open_data = [], Counter(), []
    for seed in seeds:
        symbol = seed['symbol']
        if busy_until.get(symbol, '') >= seed['entry_eligible_date']:
            skipped['SYMBOL_ALREADY_OPEN'] += 1
            continue
        result = replay(seed, cache.setdefault(symbol, load_bars(symbol)))
        if result['status'] == 'SKIP':
            skipped[result['reason']] += 1
            continue
        if result['status'] == 'OPEN_DATA':
            open_data.append({**seed, **result})
            skipped[result['reason']] += 1
            continue
        record = {**seed, **result}
        closed.append(record)
        busy_until[symbol] = result['exit_date']
    overall = measures(closed)
    yearly = {year: measures([row for row in closed if row['entry_date'][:4] == year]) for year in YEARS}
    checks = {
        'n>=300': overall['n'] >= GATE['n_min'],
        'each_year_n>=40': all(yearly[year]['n'] >= GATE['year_n_min'] for year in YEARS),
        'gross_wr>=60': overall['gross_wr_pct'] >= GATE['gross_wr_pct_min'],
        'avg_net>=0.75': overall['avg_net_pnl_pct'] >= GATE['avg_net_pnl_pct_min'],
        'pf>=1.30': overall['profit_factor'] >= GATE['pf_min'],
        'payoff>=1.00': overall['payoff_rr'] >= GATE['payoff_min'],
        'each_year_avg_net>0': all(yearly[year]['avg_net_pnl_pct'] > GATE['year_avg_net_pnl_pct_min'] for year in YEARS),
        't1_violations==0': not any(row['same_day_exit_violation'] for row in closed),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    trade_path = OUT / 'v529_frozen_t1_trades.csv'
    if closed:
        with trade_path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(closed[0].keys()))
            writer.writeheader(); writer.writerows(closed)
    report = {
        'version': 'V529_WYCKOFF_SPRING_TEST_SOS_FROZEN_T1_REPLAY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'frozen_execution_contract': 'following eligible session open; stop=spring low*0.99; nearest prior visible confirmed swing high target; exits begin following session; SL-first collision; time20; round-trip fee0.20%; serial one-position-per-symbol',
        'source_contract': source['frozen_contract'], 'seed_count': len(seeds), 'closed_trade_count': len(closed),
        'open_data_count': len(open_data), 'skip_counts': dict(skipped), 'overall': overall, 'yearly': yearly,
        'promotion_gate': GATE, 'promotion_checks': checks,
        'invariants': {
            'seed_count_matches_oracle': len(seeds) == oracle['generator_seed_count'] == oracle['oracle_seed_count'],
            'all_entries_after_sos': all(int(row['entry_eligible_idx']) > int(row['sos_idx']) for row in closed),
            'all_targets_visible_pre_sos': all(row['target_swing_idx'] < int(row['sos_idx']) for row in closed),
            't1_violations': sum(bool(row['same_day_exit_violation']) for row in closed),
            'all_production_writes_false': True,
        },
        'promotion_gate_pass': all(checks.values()),
        'decision': 'V529_PROMOTION_GATE_PASS__INDEPENDENT_METRIC_AUDIT_REQUIRED' if all(checks.values()) else 'V529_FROZEN_REPLAY_FAIL__CLOSE_ONTOLOGY__NO_VARIANTS',
        'artifacts': {'out_dir': str(OUT), 'trades': str(trade_path), 'latest': str(LATEST), 'v527': str(V527), 'v528': str(V528)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v529_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
