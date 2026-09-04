#!/usr/bin/env python3
"""V295 no-write: root-cause weak months in V294 second60 persistence.

Input is the V294 best executable k2 persistence rows.  This audit does not
promote or write production.  It isolates why 202602-202604 remain weak and
searches only entry-time available fields for a possible stabilizer.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
V294 = json.loads((AUDIT / 'v294_entry60_persistence_latest.json').read_text())
BEST_ROWS = Path(V294['artifacts']['best_rows'])
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v295_v294_weak_month_root_cause_no_write_{TS}'
LATEST = AUDIT / 'v295_v294_weak_month_root_cause_latest.json'
WEAK_MONTHS = {'202602', '202603', '202604'}


def sf(x: Any, d: float = math.nan) -> float:
    try:
        if x is None or x == '':
            return d
        v = float(x)
        return v if not math.isnan(v) else d
    except Exception:
        return d


def blank() -> dict[str, Any]:
    return {
        'n': 0, 'wins': 0, 'sum': 0.0, 'loss': 0, 'micro': 0,
        'tp': 0, 'sl': 0, 'gap_sl': 0, 'time': 0,
        'years': defaultdict(lambda: [0, 0]),
        'months': defaultdict(lambda: [0, 0]),
        'symbols': set(),
    }


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'), 0.0)
    reason = str(r.get('reason', ''))
    a['n'] += 1
    a['wins'] += pnl > 0
    a['sum'] += pnl
    a['loss'] += pnl <= 0
    a['micro'] += 0 < pnl < 1
    a['tp'] += reason == 'TP'
    a['sl'] += reason == 'SL'
    a['gap_sl'] += reason == 'GAP_SL'
    a['time'] += reason.startswith('TIME')
    y = str(r.get('entry_date', ''))[:4]
    m = str(r.get('entry_date', ''))[:6]
    a['years'][y][0] += 1
    a['years'][y][1] += pnl > 0
    a['months'][m][0] += 1
    a['months'][m][1] += pnl > 0
    a['symbols'].add(r.get('symbol', ''))


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    a = blank()
    for r in rows:
        add(a, r)
    n = a['n']
    if not n:
        return {'n': 0}
    yc = {y: int(v[0]) for y, v in sorted(a['years'].items()) if v[0]}
    ywr = {y: round(v[1] / v[0] * 100, 2) for y, v in sorted(a['years'].items()) if v[0]}
    mc = {m: int(v[0]) for m, v in sorted(a['months'].items()) if v[0]}
    mwr = {m: round(v[1] / v[0] * 100, 2) for m, v in sorted(a['months'].items()) if v[0]}
    return {
        'n': n,
        'wr': round(a['wins'] / n * 100, 4),
        'avg': round(a['sum'] / n, 4),
        'loss': int(a['loss']),
        'micro': round(a['micro'] / n * 100, 2),
        'tp_pct': round(a['tp'] / n * 100, 2),
        'sl_pct': round(a['sl'] / n * 100, 2),
        'gap_sl_pct': round(a['gap_sl'] / n * 100, 2),
        'time_pct': round(a['time'] / n * 100, 2),
        'symbols': len(a['symbols']),
        'year_counts': yc,
        'year_wr': ywr,
        'month_counts': mc,
        'month_wr': mwr,
        'min_month_n': min(mc.values()) if mc else 0,
        'min_month_wr': round(min(mwr.values()) if mwr else 0, 2),
    }


def q(vals: list[float], p: float) -> float:
    xs = sorted(v for v in vals if not math.isnan(v))
    if not xs:
        return math.nan
    k = min(len(xs) - 1, max(0, int(round((len(xs) - 1) * p))))
    return round(xs[k], 4)


def profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = [
        'risk_after_persist', 'risk_after_fill', 'open_to_confirm_pct',
        'persist_stock_ret', 'persist_mkt_ret', 'persist_ind_ret',
        'persist_mkt_up', 'persist_ind_up', 'persist_mkt_decay', 'persist_ind_decay',
        'entry60_mkt_up', 'entry60_ind_up', 'entry60_ind_vs_mkt_up',
        'stock60_pos', 'stock60_volx', 'acc_range_pct', 'sweep_depth2', 'mss_impulse',
        'post_hold_min_pct', 'gap_from_zone', 'risk', 'vol_ratio',
    ]
    out: dict[str, Any] = {}
    for f in fields:
        vals = [sf(r.get(f)) for r in rows]
        vals = [v for v in vals if not math.isnan(v)]
        if vals:
            out[f] = {
                'median': round(median(vals), 4),
                'p25': q(vals, 0.25),
                'p75': q(vals, 0.75),
                'min': round(min(vals), 4),
                'max': round(max(vals), 4),
            }
    return out


def group(rows: list[dict[str, Any]], field: str, min_n: int = 5) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        buckets[str(r.get(field, ''))].append(r)
    res = []
    for k, rs in buckets.items():
        if len(rs) >= min_n:
            m = metrics(rs)
            m['value'] = k
            res.append(m)
    return sorted(res, key=lambda x: (-x['n'], x.get('wr', 0)))


def pass_rule(r: dict[str, Any], rule: tuple[str, str, float]) -> bool:
    f, op, val = rule
    x = sf(r.get(f))
    if math.isnan(x):
        return False
    if op == '<=':
        return x <= val
    if op == '>=':
        return x >= val
    if op == '<':
        return x < val
    if op == '>':
        return x > val
    raise ValueError(op)


def rule_label(rule: tuple[str, str, float]) -> str:
    f, op, val = rule
    return f'{f}{op}{val:g}'


def search_rules(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[tuple[str, str, float]] = []
    grids = {
        'risk_after_persist': [4, 5, 6, 7, 8],
        'risk_after_fill': [4, 5, 6, 7, 8],
        'open_to_confirm_pct': [0.5, 1, 1.5, 2, 2.5, 3],
        'persist_stock_ret': [0.5, 1, 1.5, 2, 2.5],
        'persist_mkt_ret': [0.5, 0.8, 1.0, 1.2, 1.5],
        'persist_ind_ret': [0.3, 0.5, 0.8, 1.0, 1.2],
        'persist_mkt_up': [68, 70, 72, 75, 78, 80],
        'persist_ind_up': [55, 60, 65, 70, 75],
        'persist_mkt_decay': [-10, -5, 0, 5],
        'persist_ind_decay': [-10, -5, 0, 5],
        'stock60_pos': [50, 60, 70, 80],
        'stock60_volx': [0.8, 1.0, 1.2, 1.5, 2.0],
        'acc_range_pct': [3, 4, 5, 6, 7, 8],
        'sweep_depth2': [0.5, 1, 1.5, 2, 3, 4],
        'mss_impulse': [0.5, 1, 1.5, 2, 3],
        'post_hold_min_pct': [0, 1, 2, 3, 4],
        'gap_from_zone': [1, 2, 3, 4],
        'vol_ratio': [0.8, 1.0, 1.2, 1.5, 2.0],
    }
    for f, vals in grids.items():
        for v in vals:
            candidates.append((f, '<=', v))
            candidates.append((f, '>=', v))
    scored = []
    # single rules
    for r1 in candidates:
        rs = [r for r in rows if pass_rule(r, r1)]
        if len(rs) >= 80:
            m = metrics(rs)
            m['rule'] = rule_label(r1)
            scored.append(m)
    # pairs: keep small and interpretable, combine best singles only
    singles = sorted(scored, key=lambda x: (x.get('min_month_wr', 0), x.get('wr', 0), x.get('n', 0)), reverse=True)[:40]
    single_rules = []
    for s in singles:
        label = s['rule']
        for c in candidates:
            if rule_label(c) == label:
                single_rules.append(c)
                break
    for i, r1 in enumerate(single_rules):
        for r2 in single_rules[i + 1:]:
            if r1[0] == r2[0]:
                continue
            rs = [r for r in rows if pass_rule(r, r1) and pass_rule(r, r2)]
            if len(rs) >= 80:
                m = metrics(rs)
                m['rule'] = rule_label(r1) + ' & ' + rule_label(r2)
                scored.append(m)
    return sorted(scored, key=lambda x: (x.get('min_month_wr', 0), x.get('wr', 0), x.get('avg', 0), x.get('n', 0)), reverse=True)[:30]


def main() -> None:
    rows = list(csv.DictReader(BEST_ROWS.open()))
    weak = [r for r in rows if str(r.get('entry_date', ''))[:6] in WEAK_MONTHS]
    strong = [r for r in rows if str(r.get('entry_date', ''))[:6] not in WEAK_MONTHS]
    losses = [r for r in rows if sf(r.get('pnl'), 0) <= 0]
    weak_losses = [r for r in weak if sf(r.get('pnl'), 0) <= 0]

    monthly: dict[str, Any] = {}
    for m in sorted({str(r.get('entry_date', ''))[:6] for r in rows}):
        monthly[m] = metrics([r for r in rows if str(r.get('entry_date', ''))[:6] == m])

    top_rules = search_rules(rows)
    summary = {
        'version': 'V295_V294_WEAK_MONTH_ROOT_CAUSE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'source': str(BEST_ROWS),
        'hypothesis': 'Weak months after V294 may be caused by entry-session breadth decay, industry retreat, chase risk after persistence, or lifecycle buckets.',
        'baseline': metrics(rows),
        'weak_months': sorted(WEAK_MONTHS),
        'weak_metrics': metrics(weak),
        'strong_metrics': metrics(strong),
        'loss_metrics': metrics(losses),
        'weak_loss_metrics': metrics(weak_losses),
        'monthly': monthly,
        'profiles': {
            'weak': profile(weak),
            'strong': profile(strong),
            'weak_losses': profile(weak_losses),
            'all_losses': profile(losses),
        },
        'weak_groups': {
            'industry': group(weak, 'industry', 2)[:20],
            'lifecycle_combo': group(weak, 'lifecycle_combo', 2)[:20],
            'risk_bucket': group(weak, 'risk_bucket', 2),
            'gap_bucket': group(weak, 'gap_bucket', 2),
            'vol_bucket': group(weak, 'vol_bucket', 2),
            'acc_bucket': group(weak, 'acc_bucket', 2),
            'sweep_bucket': group(weak, 'sweep_bucket', 2),
            'impulse_bucket': group(weak, 'impulse_bucket', 2),
        },
        'candidate_entry_time_rules': top_rules,
        'interpretation': [],
    }

    # deterministic interpretation from measured deltas
    wp = summary['profiles']['weak']; sp = summary['profiles']['strong']
    interp = summary['interpretation']
    for f, label in [
        ('risk_after_persist', '弱月 persistence 后风险距离更高'),
        ('open_to_confirm_pct', '弱月 second60 确认追价更高'),
        ('persist_ind_decay', '弱月行业扩散衰减更明显'),
        ('persist_mkt_decay', '弱月市场扩散衰减更明显'),
        ('stock60_pos', '弱月个股第二根60m位置更高/更追价'),
    ]:
        if f in wp and f in sp:
            diff = wp[f]['median'] - sp[f]['median']
            interp.append({'field': f, 'weak_median': wp[f]['median'], 'strong_median': sp[f]['median'], 'diff': round(diff, 4), 'note': label})

    OUT.mkdir(parents=True, exist_ok=True)
    summary_path = OUT / 'v295_summary.json'
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({
        'summary': str(summary_path),
        'latest': str(LATEST),
        'baseline': summary['baseline'],
        'weak': summary['weak_metrics'],
        'best_rule': top_rules[0] if top_rules else None,
        'no_write': True,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
