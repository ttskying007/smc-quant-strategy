#!/usr/bin/env python3
"""V565 pre-outcome execution feasibility for the V563 causal seed set.

This is a source-side contract only: target/stop use structures confirmed before
entry.  It deliberately does not inspect any post-entry OHLC values or outcomes.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/daily'
AUDIT = ROOT / 'smc_audit'
SEED_REPORT = AUDIT / 'v563_ssl_industry_expansion_midday_seed_latest.json'
OUT = AUDIT / f'v565_v563_preentry_target_feasibility_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v565_v563_preentry_target_feasibility_latest.json'
MIN_RR = 1.5
STOP_BUFFER = 0.995
MAX_HOLD_DAYS = 20
SUPPORT = {'total_min': 1000, 'year_min': 300}


def number(value):
    try:
        value = float(value)
        return value if value > 0 and math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def bars(symbol):
    path = RAW / f'{symbol.replace(".", "_")}_daily.json.gz'
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        source = json.load(handle)
    output = []
    for raw in source:
        d = str(raw.get('d') or raw.get('t') or '')[:8]
        o, h, l, c = (number(raw.get(k)) for k in ('o', 'h', 'l', 'c'))
        if d and None not in (o, h, l, c):
            output.append({'d': d, 'o': o, 'h': h, 'l': l, 'c': c})
    return sorted(output, key=lambda row: row['d'])


def swing_high(rows, index):
    return (index >= 3 and index + 3 < len(rows) and
            rows[index]['h'] > max(rows[i]['h'] for i in range(index - 3, index)) and
            rows[index]['h'] >= max(rows[i]['h'] for i in range(index + 1, index + 4)))


def feasible(seed, rows):
    by_date = {row['d']: index for index, row in enumerate(rows)}
    sweep_index, entry_index = by_date.get(seed['sweep_date']), by_date.get(seed['entry_date'])
    entry = number(seed['m15_entry_open'])
    sweep_low = number(seed['sweep_low'])
    if sweep_index is None or entry_index is None or entry is None or sweep_low is None:
        return None, 'MISSING_SOURCE_ANCHOR'
    stop = sweep_low * STOP_BUFFER
    if entry <= stop:
        return None, 'ENTRY_NOT_ABOVE_STRUCTURE_STOP'
    candidates = []
    for index in range(3, sweep_index + 1):
        if index + 3 > sweep_index or not swing_high(rows, index):
            continue
        high = rows[index]['h']
        if high <= entry:
            continue
        # A liquidity target is only usable if it has not been traded through
        # after its right-side confirmation and before the entry date.
        confirmed = index + 3
        if any(rows[j]['h'] >= high for j in range(confirmed + 1, entry_index + 1)):
            continue
        candidates.append((high, rows[index]['d'], rows[confirmed]['d']))
    if not candidates:
        return None, 'NO_UNCONSUMED_PREENTRY_BSL'
    target, target_date, target_confirm_date = min(candidates, key=lambda item: item[0])
    rr = (target - entry) / (entry - stop)
    if rr < MIN_RR:
        return None, 'STRUCTURE_RR_BELOW_1P5'
    if len(rows) - entry_index - 1 < MAX_HOLD_DAYS:
        return None, 'INSUFFICIENT_FUTURE_DATES_FOR_FIXED_HORIZON'
    return {
        **seed,
        'entry_price': round(entry, 6),
        'structure_stop': round(stop, 6),
        'target_price': round(target, 6),
        'target_swing_date': target_date,
        'target_confirm_date': target_confirm_date,
        'planned_rr': round(rr, 6),
        'max_hold_trading_days': MAX_HOLD_DAYS,
    }, None


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    report = json.loads(SEED_REPORT.read_text())
    with Path(report['artifacts']['seeds']).open(newline='', encoding='utf-8') as handle:
        seeds = list(csv.DictReader(handle))
    grouped = defaultdict(list)
    for seed in seeds:
        grouped[seed['symbol']].append(seed)
    accepted, rejected = [], Counter()
    for number_index, (symbol, symbol_seeds) in enumerate(sorted(grouped.items()), 1):
        try:
            source = bars(symbol)
        except (OSError, ValueError):
            rejected['MISSING_DAILY_SOURCE'] += len(symbol_seeds)
            continue
        for seed in symbol_seeds:
            row, reason = feasible(seed, source)
            if row is not None:
                accepted.append(row)
            else:
                rejected[reason] += 1
        if number_index % 500 == 0:
            print(json.dumps({'symbols': number_index, 'accepted': len(accepted)}), flush=True)
    accepted.sort(key=lambda row: (row['entry_date'], row['symbol'], row['sweep_date']))
    years = Counter(row['entry_date'][:4] for row in accepted)
    no_outcomes = all(not any(token in key.lower() for key in row for token in ('pnl', 'exit', 'mfe', 'mae', 'realized', 'won')) for row in accepted)
    chronology = all(row['pivot_date'] < row['sweep_date'] < row['entry_date'] and row['target_confirm_date'] <= row['sweep_date'] for row in accepted)
    gate = {
        'only_preentry_prices_used': True,
        'no_outcome_fields_read_or_written': no_outcomes,
        'all_targets_confirmed_before_sweep': chronology,
        'all_planned_rr>=1.5': all(float(row['planned_rr']) >= MIN_RR for row in accepted),
        'total_n>=1000': len(accepted) >= SUPPORT['total_min'],
        '2025_n>=300': years['2025'] >= SUPPORT['year_min'],
        '2026_n>=300': years['2026'] >= SUPPORT['year_min'],
    }
    csv_path = OUT / 'v565_execution_feasible_seeds.csv'
    fields = sorted({key for row in accepted for key in row}) or ['symbol', 'entry_date']
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(accepted)
    payload = {
        'version': 'V565_V563_PREENTRY_TARGET_FEASIBILITY_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'source_contract': 'V563 raw Sina same-source seed identities plus raw daily bars only; no post-entry OHLC values or outcomes are inspected.',
        'frozen_execution_contract_for_next_stage': 'entry=following-session 13:00 M15 open; stop=sweep_low*0.995; target=nearest unconsumed pre-entry confirmed 3L/3R daily swing high; require planned RR>=1.5; exits may begin only next trading day; max hold=20 trading days; fee=0.20%; same-day stop/target conflict is stop-first.',
        'support_gate': SUPPORT,
        'counts': {'input_seeds': len(seeds), 'execution_feasible': len(accepted), 'year_counts': dict(years), 'rejected': dict(rejected)},
        'invariants': gate,
        'decision': 'V565_FEASIBILITY_PASS__ONE_FROZEN_T1_REPLAY_AUTHORIZED' if all(gate.values()) else 'V565_FEASIBILITY_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_OBJECT',
        'artifacts': {'out_dir': str(OUT), 'feasible_seeds': str(csv_path), 'latest': str(LATEST)},
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    (OUT / 'v565_report.json').write_text(text); LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
