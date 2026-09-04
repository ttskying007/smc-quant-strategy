#!/usr/bin/env python3
"""V573 one frozen strict-T+1 replay for V566 industry-activation micro-BOS seeds."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
DAILY = ROOT / 'kline_cache'
SEED_LATEST = AUDIT / 'v566_industry_activation_m60_micro_continuation_seed_latest.json'
ORACLE_LATEST = AUDIT / 'v572_v566_industry_activation_independent_oracle_latest.json'
LATEST = AUDIT / 'v573_v566_industry_activation_frozen_strict_t1_replay_latest.json'
OUT = AUDIT / f'v573_v566_industry_activation_frozen_strict_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
FEE_PCT = 0.20
MAX_HOLD = 20


def num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


def date_of(value: Any) -> str:
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else ''


def daily_bars(symbol: str) -> list[dict[str, Any]]:
    path = DAILY / f'{symbol.replace(".", "_")}_daily_750.json'
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    rows = []
    for row in raw if isinstance(raw, list) else []:
        day = date_of(row.get('t') or row.get('date'))
        opening, high, low, close = (num(row.get(key)) for key in ('o', 'h', 'l', 'c'))
        if day and None not in (opening, high, low, close):
            rows.append({'d': day, 'o': opening, 'h': high, 'l': low, 'c': close})
    return sorted(rows, key=lambda row: row['d'])


def confirmed_highs(rows: list[dict[str, Any]], event_index: int) -> list[tuple[int, float]]:
    """Only 3L/3R daily highs whose right confirmation completed before event day."""
    output = []
    for index in range(3, event_index - 3):
        if rows[index]['h'] > max(row['h'] for row in rows[index - 3:index]) and rows[index]['h'] >= max(row['h'] for row in rows[index + 1:index + 4]):
            output.append((index, rows[index]['h']))
    return output


def target_for(rows: list[dict[str, Any]], event_index: int, entry: float, stop: float) -> float | None:
    risk = entry - stop
    if risk <= 0:
        return None
    candidates = []
    for high_index, price in confirmed_highs(rows, event_index):
        if price <= entry:
            continue
        # The target must still be unconsumed before the intraday event.
        if any(row['h'] >= price for row in rows[high_index + 1:event_index]):
            continue
        if (price - entry) / risk >= 1.5:
            candidates.append(price)
    return min(candidates) if candidates else None


def replay(seed_rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], Counter]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for seed in seed_rows:
        grouped[str(seed['symbol'])].append(seed)
    trades: list[dict[str, Any]] = []
    skipped: Counter = Counter()
    for symbol, seeds in grouped.items():
        rows = daily_bars(symbol)
        by_day = {row['d']: index for index, row in enumerate(rows)}
        position_until = -1
        for seed in sorted(seeds, key=lambda row: row['event_date']):
            event_day = str(seed['event_date'])
            event_index = by_day.get(event_day)
            entry, stop = num(seed.get('entry_pre_fee')), num(seed.get('stop_pre_entry'))
            if event_index is None or entry is None or stop is None or event_index + 1 >= len(rows):
                skipped['MISSING_EVENT_OR_T1_DAILY_BAR'] += 1
                continue
            if event_index <= position_until:
                skipped['SERIAL_SYMBOL_POSITION_OPEN'] += 1
                continue
            target = target_for(rows, event_index, entry, stop)
            if target is None:
                skipped['NO_UNCONSUMED_PRE_EVENT_TARGET_RR_1P5'] += 1
                continue
            exit_index = None
            exit_price = None
            reason = None
            # Event-day entry is allowed; all exits begin the following session.
            for index in range(event_index + 1, min(len(rows), event_index + 1 + MAX_HOLD)):
                bar = rows[index]
                if bar['o'] <= stop:
                    exit_index, exit_price, reason = index, bar['o'], 'SL_GAP_T1'
                elif bar['o'] >= target:
                    exit_index, exit_price, reason = index, bar['o'], 'TP_GAP_T1'
                elif bar['l'] <= stop and bar['h'] >= target:
                    exit_index, exit_price, reason = index, stop, 'SL_TP_COLLISION_CONSERVATIVE_T1'
                elif bar['l'] <= stop:
                    exit_index, exit_price, reason = index, stop, 'SL_T1'
                elif bar['h'] >= target:
                    exit_index, exit_price, reason = index, target, 'TP_STRUCTURAL_T1'
                if exit_index is not None:
                    break
            if exit_index is None:
                exit_index = min(len(rows) - 1, event_index + MAX_HOLD)
                exit_price, reason = rows[exit_index]['c'], 'TIME20'
            assert exit_index > event_index
            position_until = exit_index
            pnl = 100 * (exit_price / entry - 1) - FEE_PCT
            trades.append({
                'symbol': symbol,
                'event_date': event_day,
                'entry_date': event_day,
                'entry_price': round(entry, 8),
                'stop_price': round(stop, 8),
                'target_price': round(target, 8),
                'planned_rr': round((target - entry) / (entry - stop), 8),
                'exit_date': rows[exit_index]['d'],
                'exit_price': round(exit_price, 8),
                'exit_reason': reason,
                'hold_sessions': exit_index - event_index,
                'pnl_net_pct': round(pnl, 8),
                'strict_t1': True,
            })
    return sorted(trades, key=lambda row: (row['entry_date'], row['symbol'])), skipped


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    wins = [float(row['pnl_net_pct']) for row in rows if float(row['pnl_net_pct']) > 0]
    losses = [float(row['pnl_net_pct']) for row in rows if float(row['pnl_net_pct']) <= 0]
    gross_win, gross_loss = sum(wins), -sum(losses)
    return {
        'n': count,
        'wr_pct': round(100 * len(wins) / count, 4) if count else None,
        'avg_net_pct': round(sum(wins + losses) / count, 4) if count else None,
        'profit_factor': round(gross_win / gross_loss, 4) if gross_loss else None,
        'payoff': round((sum(wins) / len(wins)) / (-sum(losses) / len(losses)), 4) if wins and losses else None,
        'avg_win_pct': round(sum(wins) / len(wins), 4) if wins else None,
        'avg_loss_pct': round(sum(losses) / len(losses), 4) if losses else None,
        'exit_reason_counts': dict(Counter(str(row['exit_reason']) for row in rows)),
    }


def main() -> None:
    seed_meta = json.loads(SEED_LATEST.read_text())
    oracle = json.loads(ORACLE_LATEST.read_text())
    if not oracle.get('identity_match'):
        raise RuntimeError('V572 Oracle did not pass; frozen replay forbidden')
    with Path(seed_meta['artifacts']['rows']).open(newline='', encoding='utf-8') as handle:
        seeds = list(csv.DictReader(handle))
    forbidden = [field for field in (seeds[0] if seeds else {}) if any(token in field.lower() for token in ('pnl', 'outcome', 'exit', 'mfe', 'mae', 'win', 'loss'))]
    if forbidden:
        raise RuntimeError(f'forbidden outcome field in V566 seed: {forbidden}')
    trades, skipped = replay(seeds)
    yearly = {year: metrics([row for row in trades if row['entry_date'].startswith(year)]) for year in ('2025', '2026')}
    overall = metrics(trades)
    checks = {
        'n>=1000': len(trades) >= 1000,
        'each_available_year_n>=300': all(yearly[year]['n'] >= 300 for year in yearly),
        'wr>=55': (overall['wr_pct'] or -math.inf) >= 55,
        'avg_net>=0.50': (overall['avg_net_pct'] or -math.inf) >= 0.5,
        'pf>=1.15': (overall['profit_factor'] or -math.inf) >= 1.15,
        'payoff>=0.70': (overall['payoff'] or -math.inf) >= 0.7,
        'each_available_year_avg_net>0': all((yearly[year]['avg_net_pct'] or -math.inf) > 0 for year in yearly),
        't1_violations==0': all(row['exit_date'] > row['entry_date'] for row in trades),
    }
    OUT.mkdir(parents=True, exist_ok=False)
    trade_path = OUT / 'v573_frozen_t1_trades.csv'
    fields = list(trades[0]) if trades else ['symbol']
    with trade_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(trades)
    report = {
        'version': 'V573_V566_ONE_FROZEN_STRICT_T1_REPLAY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'input_contract': 'V566 outcome-blind seeds only after exact V572 independent identity pass.',
        'frozen_execution_contract': 'entry=event-day second-60m close; stop=first-60m low*0.99; target=nearest unconsumed, pre-event confirmed daily 3L/3R high with RR>=1.5; exits begin next daily session; gap-aware stop-first collision; fee=0.20%; time20; serial symbol positions.',
        'seed_count': len(seeds),
        'closed_trade_count': len(trades),
        'skip_counts': dict(skipped),
        'overall': overall,
        'yearly': yearly,
        'quality_gate': {'n_min': 1000, 'year_n_min': 300, 'wr_pct_min': 55.0, 'avg_net_pct_min': 0.5, 'pf_min': 1.15, 'payoff_min': 0.7, 'each_year_avg_net_positive': True, 't1_violations': 0},
        'quality_checks': checks,
        't1_violations': sum(row['exit_date'] <= row['entry_date'] for row in trades),
        'invariants': {'v572_identity_match': True, 'all_targets_pre_event_by_contract': True, 'no_parameter_or_selector_search': True, 'all_writes_false': True},
        'promotion_gate_pass': all(checks.values()),
        'decision': 'V573_FROZEN_REPLAY_GATE_PASS__INDEPENDENT_METRIC_AUDIT_REQUIRED' if all(checks.values()) else 'V573_FROZEN_REPLAY_GATE_FAIL__CLOSE_V566_ONTOLOGY_NO_VARIANTS',
        'artifacts': {'out_dir': str(OUT), 'trades': str(trade_path), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v573_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
