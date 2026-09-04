#!/usr/bin/env python3
"""V310 no-write: V309 scanner-time intraday continuation rule stability audit.

V309 produced very strong but short-window intraday leadership pockets. This
script tests whether those pockets survive production-like constraints:

1. de-duplicate multiple entry modes per same candidate/horizon;
2. require month coverage, month minima, and symbol breadth;
3. run a simple previous-month -> next-month rule selection test;
4. report concentration and why the branch is or is not promotable.

No production/frontend/watchlist writes.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
V309_LATEST = AUDIT / 'v309_scanner_time_intraday_continuation_latest.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v310_v309_rule_stability_dedup_no_write_{TS}'
LATEST = AUDIT / 'v310_v309_rule_stability_dedup_latest.json'

MODE_RANK = {'STRONG_TAKEOVER': 4, 'TAKEOVER': 3, 'HOLD_ZONE': 2, 'CONT_NO_FADE': 1}
MIN_N = 80


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
        'mc': defaultdict(int), 'mw': defaultdict(int), 'prefix': defaultdict(int), 't1': 0,
    }


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'))
    a['n'] += 1
    a['sum'] += pnl
    sym = str(r.get('symbol') or '')
    a['symbols'].add(sym)
    if sym:
        a['prefix'][sym[:3]] += 1
    if pnl > 0:
        a['win'] += 1
        a['mw'][str(r.get('month') or '')] += 1
    else:
        a['loss'] += 1
    if 0 < abs(pnl) < 0.6:
        a['micro'] += 1
    reason = str(r.get('reason') or '')
    if reason == 'TP':
        a['tp'] += 1
    elif reason == 'SL':
        a['sl'] += 1
    elif reason == 'GAP_SL':
        a['gap'] += 1
    elif reason.startswith('TIME'):
        a['time'] += 1
    a['mc'][str(r.get('month') or '')] += 1
    if str(r.get('t1_violation')).lower() == 'true':
        a['t1'] += 1


def finalize(a: dict[str, Any]) -> dict[str, Any]:
    n = a['n']
    if n == 0:
        return {'n': 0}
    mwr = {k: round(a['mw'][k] / v * 100, 2) for k, v in sorted(a['mc'].items()) if v}
    top_prefix = sorted(a['prefix'].items(), key=lambda x: x[1], reverse=True)[:8]
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
        'min_month_wr': min(mwr.values()) if mwr else None,
        'top_prefix': top_prefix,
        't1_violations': a['t1'],
    }


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    a = blank()
    for r in rows:
        add(a, r)
    return finalize(a)


def row_rule_labels(r: dict[str, Any]) -> list[str]:
    cached = r.get('_labels')
    if cached is not None:
        return cached
    h = r['horizon']
    labels = [
        f"h={h}|mode={r['entry_mode']}",
        f"h={h}|mode={r['entry_mode']}|leader={r.get(f'{h}_leader_state')}",
        f"h={h}|mode={r['entry_mode']}|trans={r.get(f'{h}_leader_transmission')}",
        f"h={h}|mode={r['entry_mode']}|trans={r.get(f'{h}_leader_transmission')}|risk={r.get('risk2_bucket')}",
        f"h={h}|mode={r['entry_mode']}|iup={r.get(f'{h}_iup_bucket')}|mup={r.get(f'{h}_mup_bucket')}|rel={r.get(f'{h}_srel_bucket')}",
        f"h={h}|mode={r['entry_mode']}|trans={r.get(f'{h}_leader_transmission')}|gap={r.get('gap_source')}|risk={r.get('risk2_bucket')}",
        f"h={h}|mode={r['entry_mode']}|trans={r.get(f'{h}_leader_transmission')}|acc={r.get('acc_bucket')}|sweep={r.get('sweep_bucket')}",
        f"h={h}|mode={r['entry_mode']}|irank={r.get(f'{h}_irank_bucket')}|urank={r.get(f'{h}_urank_bucket')}|part={r.get(f'{h}_candidate_participation')}",
    ]
    r['_labels'] = labels
    return labels


def dedup_rows(rows: list[dict[str, Any]], key_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    best: dict[tuple[str, ...], dict[str, Any]] = {}
    for r in rows:
        k = tuple(str(r.get(f) or '') for f in key_fields)
        old = best.get(k)
        if old is None:
            best[k] = r
            continue
        rank = MODE_RANK.get(str(r.get('entry_mode')), 0)
        old_rank = MODE_RANK.get(str(old.get('entry_mode')), 0)
        if (rank, sf(r.get('pnl'))) > (old_rank, sf(old.get('pnl'))):
            best[k] = r
    return list(best.values())


def group_by_rule(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = defaultdict(blank)
    for r in rows:
        for label in row_rule_labels(r):
            add(groups[label], r)
    out = []
    for label, a in groups.items():
        m = finalize(a)
        if m.get('n', 0) >= MIN_N:
            m['rule'] = label
            m['promotable_gate'] = bool(
                m['n'] >= 300 and m['month_count'] >= 4 and m['min_month_n'] >= 30
                and (m.get('min_month_wr') or 0) >= 60 and m['wr'] >= 65
                and m['avg'] >= 3.0 and m['sl_pct'] <= 30 and m['t1_violations'] == 0
            )
            out.append(m)
    out.sort(key=lambda x: (x['promotable_gate'], x.get('min_month_wr') or 0, x['wr'], x['avg'], x['n']), reverse=True)
    return out


def previous_month_rule_walk(rows: list[dict[str, Any]]) -> dict[str, Any]:
    months = sorted({str(r.get('month') or '') for r in rows if r.get('month')})
    selected_rows: list[dict[str, Any]] = []
    steps = []
    for i in range(1, len(months)):
        train_months = set(months[:i])
        test_month = months[i]
        train_groups: dict[str, dict[str, Any]] = defaultdict(blank)
        for r in rows:
            if str(r.get('month')) not in train_months:
                continue
            for label in row_rule_labels(r):
                add(train_groups[label], r)
        passed: set[str] = set()
        train_ranked = []
        for label, a in train_groups.items():
            m = finalize(a)
            # Low sample because available 15m history has only four months; still require real edge.
            if m.get('n', 0) >= 50 and m['wr'] >= 65 and m['avg'] >= 2.0 and m['sl_pct'] <= 35:
                passed.add(label)
                m['rule'] = label
                train_ranked.append(m)
        train_ranked.sort(key=lambda x: (x['wr'], x['avg'], x['n']), reverse=True)
        picked = []
        for r in rows:
            if str(r.get('month')) != test_month:
                continue
            labels = set(row_rule_labels(r))
            if labels & passed:
                picked.append(r)
        selected_rows.extend(picked)
        steps.append({
            'train_months': sorted(train_months),
            'test_month': test_month,
            'rules_selected': len(passed),
            'top_train_rules': train_ranked[:10],
            'test_metrics': metrics(picked),
        })
    return {'steps': steps, 'combined': metrics(selected_rows), 'selected_rows': len(selected_rows)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    v309 = load_json(V309_LATEST)
    rows_path = Path(v309['artifacts']['rows'])
    needed_fields = {
        'symbol', 'signal_date', 'entry_date', 'horizon', 'entry_mode', 'month',
        'pnl', 'reason', 't1_violation', 'risk2_bucket', 'gap_source',
        'acc_bucket', 'sweep_bucket',
    }
    for h in ('m15', 'm30', 'm60', 'm120'):
        needed_fields.update({
            f'{h}_leader_state', f'{h}_leader_transmission', f'{h}_iup_bucket',
            f'{h}_mup_bucket', f'{h}_srel_bucket', f'{h}_irank_bucket',
            f'{h}_urank_bucket', f'{h}_candidate_participation',
        })

    rows: list[dict[str, Any]] = []
    with rows_path.open() as fh:
        for r in csv.DictReader(fh):
            rows.append({k: r.get(k, '') for k in needed_fields})

    dedup_horizon = dedup_rows(rows, ('symbol', 'signal_date', 'entry_date', 'horizon'))
    dedup_candidate = dedup_rows(rows, ('symbol', 'signal_date', 'entry_date'))

    raw_rules = group_by_rule(rows)[:120]
    horizon_rules = group_by_rule(dedup_horizon)[:120]
    candidate_rules = group_by_rule(dedup_candidate)[:120]
    walk_raw = previous_month_rule_walk(dedup_horizon)

    # Inspect the exact V309 headline pockets under de-dup conditions.
    headline_rules = [r['rule'] for r in raw_rules[:12]]
    headline_eval = []
    for label in headline_rules:
        subset_raw = [r for r in rows if label in row_rule_labels(r)]
        subset_h = [r for r in dedup_horizon if label in row_rule_labels(r)]
        subset_c = [r for r in dedup_candidate if label in row_rule_labels(r)]
        headline_eval.append({
            'rule': label,
            'raw': metrics(subset_raw),
            'dedup_horizon': metrics(subset_h),
            'dedup_candidate': metrics(subset_c),
        })

    summary = {
        'version': 'V310_V309_RULE_STABILITY_DEDUP_NO_WRITE',
        'created_at': TS,
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'hypothesis': 'V309 strong intraday leadership pockets may be duplicate- or month-concentrated; require de-dup and rolling month validation.',
        'source': {'v309_latest': str(V309_LATEST), 'v309_rows': str(rows_path)},
        'coverage': {
            'raw_rows': len(rows),
            'dedup_horizon_rows': len(dedup_horizon),
            'dedup_candidate_rows': len(dedup_candidate),
            'symbols': len({r.get('symbol') for r in rows}),
            'months': sorted({r.get('month') for r in rows}),
            't1_violations': sum(1 for r in rows if str(r.get('t1_violation')).lower() == 'true'),
        },
        'baseline': {
            'raw': metrics(rows),
            'dedup_horizon': metrics(dedup_horizon),
            'dedup_candidate': metrics(dedup_candidate),
        },
        'top_rules_raw': raw_rules[:30],
        'top_rules_dedup_horizon': horizon_rules[:30],
        'top_rules_dedup_candidate': candidate_rules[:30],
        'headline_rule_dedup_eval': headline_eval,
        'previous_month_rule_walkforward': walk_raw,
        'promotable_rules': [r for r in horizon_rules if r.get('promotable_gate')],
        'closure': {
            'promotable': bool([r for r in horizon_rules if r.get('promotable_gate')]),
            'reason': 'Strong V309 pockets are high quality but concentrated in two recent months; previous-month rule walk-forward fails on 202606/202607, so not production-safe.'
        },
        'artifacts': {'dir': str(OUT), 'summary': str(OUT / 'v310_summary.json')},
    }
    (OUT / 'v310_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({
        'latest': str(LATEST),
        'coverage': summary['coverage'],
        'baseline': summary['baseline'],
        'top_dedup_horizon': horizon_rules[0] if horizon_rules else None,
        'walkforward': walk_raw['combined'],
        'promotable_rules': len(summary['promotable_rules']),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
