#!/usr/bin/env python3
"""V525 no-write causal feasibility audit for V517.

Hypothesis fixed before outcome read: V517's confirmed absorption sequence is only
tradeable when its *already visible* structural target gives at least 1.5R versus
its structural sweep-failure stop. This evaluates the pre-entry feasibility gate,
then replays the selected frozen seeds using the unmodified V519 execution rule.
It creates no picks, monitor rows, positions, or production state.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
V25 = ROOT / 'scripts/v25'
sys.path.insert(0, str(V25))
import v519_daily_effort_result_absorption_frozen_t1_replay as core

V517 = AUD / 'v517_daily_effort_result_absorption_seed_gate_latest.json'
V518 = AUD / 'v518_daily_effort_result_absorption_independent_oracle_latest.json'
OUT = AUD / f'v525_effort_result_structural_rr_gate_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v525_effort_result_structural_rr_gate_latest.json'
MIN_RR = 1.5
YEARS = ('2023', '2024', '2025', '2026')
SUPPORT = {'total_min': 300, 'year_min': 40}


def preentry_contract(seed: dict[str, str], bars: list[dict]) -> dict:
    """Uses only bars observable at entry open; no exit/outcome fields."""
    by_date = {bar['t']: index for index, bar in enumerate(bars)}
    entry_date, sweep_date = seed['entry_eligible_date'], seed['sweep_date']
    if entry_date not in by_date or sweep_date not in by_date:
        return {'eligible': False, 'reason': 'SEED_DATE_NOT_IN_CACHE'}
    idx, sweep_idx = by_date[entry_date], by_date[sweep_date]
    if not sweep_idx < idx:
        return {'eligible': False, 'reason': 'INVALID_SEED_DATE_ORDER'}
    entry = bars[idx]['o']
    stop = float(seed['sweep_low']) * core.STOP_BUFFER
    if stop >= entry:
        return {'eligible': False, 'reason': 'INVALID_STRUCTURAL_STOP'}
    target_info = core.visible_target(bars, sweep_idx, idx - 1, entry)
    if target_info is None:
        return {'eligible': False, 'reason': 'NO_VISIBLE_UPSIDE_TARGET'}
    target_idx, target = target_info
    rr = (target - entry) / (entry - stop)
    return {
        'eligible': rr >= MIN_RR,
        'reason': 'RR_GE_1P5' if rr >= MIN_RR else 'STRUCTURAL_TARGET_BELOW_1P5R',
        'entry_price': round(entry, 6), 'stop': round(stop, 6),
        'target': round(target, 6), 'target_swing_idx': target_idx,
        'target_swing_date': bars[target_idx]['t'], 'planned_rr': round(rr, 6),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    gate = json.loads(V517.read_text())
    oracle = json.loads(V518.read_text())
    if not gate.get('support_gate_pass') or not oracle.get('oracle_pass'):
        raise RuntimeError('V517/V518 source gates unavailable')
    with Path(gate['artifacts']['seeds']).open(newline='') as handle:
        seeds = list(csv.DictReader(handle))
    seeds.sort(key=lambda r: (r['entry_eligible_date'], r['symbol'], int(r['sweep_idx'])))

    cache, feasible, rejects, audit_rows = {}, [], Counter(), []
    for seed in seeds:
        symbol = seed['symbol']
        bars = cache.setdefault(symbol, core.load_bars(symbol))
        c = preentry_contract(seed, bars)
        audit_rows.append({**seed, **c})
        if c['eligible']:
            feasible.append({**seed, **c})
        else:
            rejects[c['reason']] += 1

    pre_year = Counter(x['entry_eligible_date'][:4] for x in feasible)
    support_checks = {
        'total>=300': len(feasible) >= SUPPORT['total_min'],
        'each_year>=40': all(pre_year[y] >= SUPPORT['year_min'] for y in YEARS),
    }

    # Outcomes are opened only after the pre-entry candidate set is frozen above.
    busy, executed, post_skips = {}, [], Counter()
    for seed in feasible:
        symbol, entry_date = seed['symbol'], seed['entry_eligible_date']
        if busy.get(symbol, '') >= entry_date:
            post_skips['SYMBOL_ALREADY_OPEN'] += 1
            continue
        result = core.replay(seed, cache[symbol])
        if result['status'] != 'CLOSED':
            post_skips[result['reason']] += 1
            continue
        record = {**seed, **result}
        executed.append(record)
        busy[symbol] = result['exit_date']
    overall = core.stats(executed)
    yearly = {y: core.stats([x for x in executed if x['entry_date'][:4] == y]) for y in YEARS}
    csv_path = OUT / 'v525_preentry_rr_feasibility_rows.csv'
    fields = sorted({k for r in audit_rows for k in r})
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(audit_rows)
    report = {
        'version': 'V525_EFFORT_RESULT_STRUCTURAL_RR_GATE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'hypothesis': 'Pre-entry V517 structural target feasibility >=1.5R may form a tradeable causal subset.',
        'source_ontology': gate.get('frozen_contract'),
        'predeclared_contract': 'entry=open on following eligible session; stop=sweep_low*0.99; target=nearest prior visible confirmed swing high; retain only planned RR>=1.5 before any exit/outcome read.',
        'source_seed_count': len(seeds), 'feasible_seed_count': len(feasible),
        'preentry_year_counts': dict(pre_year), 'preentry_rejects': dict(rejects),
        'support_gate': SUPPORT, 'support_checks': support_checks,
        'closed_trade_count': len(executed), 'post_execution_skips': dict(post_skips),
        'overall': overall, 'yearly': yearly,
        't1_violations': sum(bool(x.get('same_day_exit_violation')) for x in executed),
        'decision': 'V525_SUPPORT_FAIL__NO_REPLAY_PROMOTION' if not all(support_checks.values()) else 'V525_SUPPORT_PASS__INDEPENDENT_ORACLE_AND_FROZEN_REPLAY_REQUIRED',
        'artifacts': {'out_dir': str(OUT), 'preentry_rows': str(csv_path), 'latest': str(LATEST), 'source_v517': str(V517), 'source_v518': str(V518)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v525_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
