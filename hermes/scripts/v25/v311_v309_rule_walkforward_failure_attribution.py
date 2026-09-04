#!/usr/bin/env python3
"""V311 no-write: V309/V310 rule stability failure attribution.

Next concrete research step after V310: instead of trusting headline high-WR
intraday pockets, run leave-one-month-out and weak-month attribution on the
same V309 scanner-time rows. This deliberately writes audit artifacts only.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
V309_LATEST = AUDIT / 'v309_scanner_time_intraday_continuation_latest.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v311_v309_rule_walkforward_failure_attribution_no_write_{TS}'
LATEST = AUDIT / 'v311_v309_rule_walkforward_failure_attribution_latest.json'

MODE_RANK = {'STRONG_TAKEOVER': 4, 'TAKEOVER': 3, 'HOLD_ZONE': 2, 'CONT_NO_FADE': 1}
MIN_RULE_N = 50


def sf(x: Any, d: float = math.nan) -> float:
    try:
        if x is None or x == '':
            return d
        v = float(x)
        return v if not math.isnan(v) else d
    except Exception:
        return d


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def blank() -> dict[str, Any]:
    return {
        'n': 0, 'win': 0, 'sum': 0.0, 'loss': 0, 'micro': 0,
        'tp': 0, 'sl': 0, 'gap': 0, 'time': 0, 'symbols': set(),
        'mc': defaultdict(int), 'mw': defaultdict(int), 'reason': Counter(),
        'prefix': defaultdict(int), 't1': 0,
    }


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'))
    a['n'] += 1
    a['sum'] += pnl
    sym = str(r.get('symbol') or '')
    if sym:
        a['symbols'].add(sym)
        a['prefix'][sym[:3]] += 1
    month = str(r.get('month') or '')
    a['mc'][month] += 1
    if pnl > 0:
        a['win'] += 1
        a['mw'][month] += 1
    else:
        a['loss'] += 1
    if 0 < abs(pnl) < 0.6:
        a['micro'] += 1
    reason = str(r.get('reason') or '')
    a['reason'][reason] += 1
    if reason == 'TP':
        a['tp'] += 1
    elif reason == 'SL':
        a['sl'] += 1
    elif reason == 'GAP_SL':
        a['gap'] += 1
    elif reason.startswith('TIME'):
        a['time'] += 1
    if str(r.get('t1_violation')).lower() == 'true':
        a['t1'] += 1


def metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    a = blank()
    for r in rows:
        add(a, r)
    n = a['n']
    if not n:
        return {'n': 0, 'wr': 0, 'avg': 0, 'loss': 0}
    mwr = {k: round(a['mw'][k] / v * 100, 2) for k, v in sorted(a['mc'].items()) if v}
    return {
        'n': n,
        'wr': round(a['win'] / n * 100, 4),
        'avg': round(a['sum'] / n, 4),
        'loss': a['loss'],
        'micro': round(a['micro'] / n * 100, 2),
        'tp_pct': round(a['tp'] / n * 100, 2),
        'sl_pct': round(a['sl'] / n * 100, 2),
        'gap_sl_pct': round(a['gap'] / n * 100, 2),
        'time_pct': round(a['time'] / n * 100, 2),
        'symbols': len(a['symbols']),
        'month_count': len(a['mc']),
        'month_counts': dict(sorted(a['mc'].items())),
        'month_wr': mwr,
        'min_month_n': min(a['mc'].values()) if a['mc'] else 0,
        'min_month_wr': min(mwr.values()) if mwr else 0,
        'reason_counts': dict(a['reason'].most_common()),
        'top_prefix': sorted(a['prefix'].items(), key=lambda x: x[1], reverse=True)[:8],
        't1_violations': a['t1'],
    }


def dedup_candidate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in rows:
        key = (str(r.get('symbol') or ''), str(r.get('signal_date') or ''), str(r.get('entry_date') or ''))
        old = best.get(key)
        if old is None:
            best[key] = r
            continue
        cur_rank = MODE_RANK.get(str(r.get('entry_mode')), 0)
        old_rank = MODE_RANK.get(str(old.get('entry_mode')), 0)
        if (cur_rank, sf(r.get('pnl'))) > (old_rank, sf(old.get('pnl'))):
            best[key] = r
    return list(best.values())


def labels(r: dict[str, Any]) -> list[str]:
    h = str(r.get('horizon') or '')
    return [
        f"h={h}|mode={r.get('entry_mode')}",
        f"h={h}|mode={r.get('entry_mode')}|trans={r.get(f'{h}_leader_transmission')}",
        f"h={h}|mode={r.get('entry_mode')}|trans={r.get(f'{h}_leader_transmission')}|risk={r.get('risk2_bucket')}",
        f"h={h}|mode={r.get('entry_mode')}|trans={r.get(f'{h}_leader_transmission')}|gap={r.get('gap_source')}|risk={r.get('risk2_bucket')}",
        f"h={h}|mode={r.get('entry_mode')}|iup={r.get(f'{h}_iup_bucket')}|mup={r.get(f'{h}_mup_bucket')}|rel={r.get(f'{h}_srel_bucket')}",
        f"h={h}|mode={r.get('entry_mode')}|irank={r.get(f'{h}_irank_bucket')}|urank={r.get(f'{h}_urank_bucket')}|part={r.get(f'{h}_candidate_participation')}",
        f"h={h}|mode={r.get('entry_mode')}|acc={r.get('acc_bucket')}|sweep={r.get('sweep_bucket')}|risk={r.get('risk2_bucket')}",
    ]


def row_matches_rule(r: dict[str, Any], rule: str) -> bool:
    return rule in labels(r)


def build_rule_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        for label in labels(r):
            groups[label].append(r)
    out = []
    for rule, rs in groups.items():
        m = metrics(rs)
        if m['n'] < MIN_RULE_N:
            continue
        m['rule'] = rule
        m['stable_gate'] = bool(
            m['n'] >= 300 and m['month_count'] >= 4 and m['min_month_n'] >= 30
            and m['min_month_wr'] >= 60 and m['wr'] >= 65 and m['avg'] >= 3
            and m['sl_pct'] <= 30 and m['t1_violations'] == 0
        )
        out.append(m)
    return sorted(out, key=lambda x: (x['stable_gate'], x['min_month_wr'], x['wr'], x['avg'], x['n']), reverse=True)


def leave_one_month_out(rows: list[dict[str, Any]], all_rules: list[dict[str, Any]]) -> dict[str, Any]:
    months = sorted({str(r.get('month') or '') for r in rows if r.get('month')})
    selected_all: list[dict[str, Any]] = []
    steps = []
    for test_month in months:
        train = [r for r in rows if str(r.get('month')) != test_month]
        test = [r for r in rows if str(r.get('month')) == test_month]
        train_rules = build_rule_table(train)
        passed = {
            r['rule'] for r in train_rules
            if r['n'] >= 200 and r['month_count'] >= 3 and r['min_month_n'] >= 25
            and r['min_month_wr'] >= 65 and r['wr'] >= 70 and r['avg'] >= 3 and r['sl_pct'] <= 28
        }
        picked = [r for r in test if any(row_matches_rule(r, rule) for rule in passed)]
        selected_all.extend(picked)
        steps.append({
            'test_month': test_month,
            'train_rules_selected': len(passed),
            'top_train_rules': train_rules[:8],
            'test_rows': len(test),
            'picked_metrics': metrics(picked),
        })
    return {'steps': steps, 'combined': metrics(selected_all)}


def weak_month_attribution(rows: list[dict[str, Any]], month: str) -> dict[str, Any]:
    weak = [r for r in rows if str(r.get('month')) == month]
    losses = [r for r in weak if sf(r.get('pnl')) <= 0]
    dims = ['horizon', 'entry_mode', 'risk2_bucket', 'gap_source', 'acc_bucket', 'sweep_bucket']
    out: dict[str, Any] = {'month': month, 'month_metrics': metrics(weak), 'loss_count': len(losses)}
    for dim in dims:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in weak:
            groups[str(r.get(dim) or '')].append(r)
        out[f'by_{dim}'] = sorted(
            [{'value': k, **metrics(v)} for k, v in groups.items() if len(v) >= 20],
            key=lambda x: (x['wr'], x['avg'], -x['n'])
        )[:12]
    reason_counter = Counter(str(r.get('reason') or '') for r in losses)
    out['loss_reason_counts'] = dict(reason_counter.most_common())
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    latest = load_json(V309_LATEST)
    rows_path = Path(latest['artifacts']['rows'])
    needed = {'symbol', 'signal_date', 'entry_date', 'horizon', 'entry_mode', 'month', 'pnl', 'reason', 't1_violation', 'risk2_bucket', 'gap_source', 'acc_bucket', 'sweep_bucket'}
    for h in ('m15', 'm30', 'm60', 'm120'):
        needed.update({f'{h}_leader_transmission', f'{h}_iup_bucket', f'{h}_mup_bucket', f'{h}_srel_bucket', f'{h}_irank_bucket', f'{h}_urank_bucket', f'{h}_candidate_participation'})
    rows: list[dict[str, Any]] = []
    with rows_path.open() as f:
        for r in csv.DictReader(f):
            rows.append({k: r.get(k, '') for k in needed})
    dedup = dedup_candidate(rows)
    rule_table = build_rule_table(dedup)
    loo = leave_one_month_out(dedup, rule_table)
    months = sorted({str(r.get('month') or '') for r in dedup if r.get('month')})
    weak_months = sorted(months, key=lambda m: metrics([r for r in dedup if str(r.get('month')) == m])['wr'])[:2]
    weak = [weak_month_attribution(dedup, m) for m in weak_months]
    stable = [r for r in rule_table if r.get('stable_gate')]
    summary = {
        'version': 'V311_V309_RULE_WALKFORWARD_FAILURE_ATTRIBUTION_NO_WRITE',
        'created_at': TS,
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'hypothesis': 'High headline scanner-time intraday rules are not enough; require leave-one-month-out stability and weak-month loss attribution.',
        'source': {'v309_rows': str(rows_path), 'v309_latest': str(V309_LATEST)},
        'coverage': {'raw_rows': len(rows), 'dedup_candidate_rows': len(dedup), 'months': months},
        'baseline_dedup_candidate': metrics(dedup),
        'stable_rules_count': len(stable),
        'top_stable_rules': stable[:20],
        'top_rules_after_stability_sort': rule_table[:30],
        'leave_one_month_out': loo,
        'weak_month_attribution': weak,
        'closure': {
            'production_candidate_found': bool(stable and loo['combined'].get('wr', 0) >= 65 and loo['combined'].get('n', 0) >= 300),
            'decision': 'PROMOTE_NONE__INTRADAY_LEADERSHIP_BRANCH_REJECTED_FOR_NOW' if not stable else 'REQUIRES_MANUAL_GATE_REVIEW',
            'next_direction': 'Return to V185/V246 daily production shadow; do not promote V309/V310 pockets until longer 15m history or real walk-forward passes.',
        },
        'artifacts': {'summary': str(OUT / 'v311_summary.json'), 'rules_csv': str(OUT / 'v311_rules.csv')},
    }
    (OUT / 'v311_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    with (OUT / 'v311_rules.csv').open('w', newline='') as f:
        fields = ['rule', 'stable_gate', 'n', 'wr', 'avg', 'loss', 'tp_pct', 'sl_pct', 'gap_sl_pct', 'time_pct', 'symbols', 'month_count', 'min_month_n', 'min_month_wr', 'month_counts', 'month_wr']
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader(); w.writerows(rule_table)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
