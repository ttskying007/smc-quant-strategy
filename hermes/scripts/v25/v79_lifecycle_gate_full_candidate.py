#!/usr/bin/env python3
"""V79 lifecycle gate on full V71 candidate layer.

This is the first executable gate aligned with the user's decomposition:
trend regime -> SMC event -> POI -> entry -> invalidation/target.
It does NOT promote production; it tests a stricter smart-money combination on
all 9,931 V71/V73 candidates.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from v71_smart_money_position_engine import simulate
from v78_full_candidate_lifecycle_audit import OUT_DIR as V78_AUDIT_DIR, f, load_klines, metrics, bucket

OUT_DIR = Path('/root/.hermes/smc_opt_v79_lifecycle_gate_full_candidate')
OUT_DIR.mkdir(parents=True, exist_ok=True)


def v(x: Any) -> float:
    return f(x)


def passes_v79_gate(r: Dict[str, Any]) -> bool:
    if r.get('lifecycle_audit_status') != 'OK':
        return False
    if not r.get('lc_entry_valid'):
        return False
    if r.get('lc_exit_signal') in {'EXIT_POI_CLOSE_BREAK', 'EXIT_TREND_HL_BREAK'}:
        return False
    if r.get('market_state_v74') not in {'RECOVERY', 'BULL_CONTINUATION', 'ACCUMULATION'}:
        return False
    if v(r.get('lc_prior5_distribution_days')) > 0 or v(r.get('lc_prior10_distribution_days')) > 3:
        return False
    if v(r.get('lc_prior10_demand_days')) < 3:
        return False
    if v(r.get('lc_bull_breadth')) > 0.50:
        return False
    if not (2.0 <= v(r.get('risk_pct')) <= 5.5):
        return False
    # Reject ambiguous structure-low-risk labels in early years: they were not true POI tests.
    if r.get('pd_zone') == 'STRUCTURE_LOW_RISK':
        return False
    # Reversal must come from genuine weak/down/range stock context, not an already-up stock falsely called reversal.
    if r.get('lc_entry_story') == 'REVERSAL_LIQUIDITY_TO_DEMAND':
        if r.get('stock_trend_state') not in {'DOWN_CONTINUATION', 'BEAR_TRANSITION', 'COMPRESSION_RANGE', 'EXPANSION_RANGE', 'RANGE'}:
            return False
        if r.get('stock_last_event') not in {'BULL_CHOCH', 'BULL_MSS'}:
            return False
    # Continuation needs real bull structure and bullish event.
    if r.get('lc_entry_story') == 'CONTINUATION_BOS_PULLBACK_TO_DEMAND':
        if r.get('stock_trend_state') != 'UP_CONTINUATION':
            return False
        if r.get('stock_last_event') not in {'BULL_BOS', 'BULL_CHOCH'}:
            return False
    return True


def reject_reason(r: Dict[str, Any]) -> str:
    reasons = []
    if r.get('lifecycle_audit_status') != 'OK': reasons.append('BAD_AUDIT')
    if not r.get('lc_entry_valid'): reasons.append('BAD_ENTRY')
    if r.get('lc_exit_signal') == 'EXIT_POI_CLOSE_BREAK': reasons.append('POI_CLOSE_BREAK')
    if r.get('lc_exit_signal') == 'EXIT_TREND_HL_BREAK': reasons.append('TREND_HL_BREAK')
    if r.get('market_state_v74') not in {'RECOVERY', 'BULL_CONTINUATION', 'ACCUMULATION'}: reasons.append('BAD_ENV')
    if v(r.get('lc_prior5_distribution_days')) > 0: reasons.append('PRIOR5_DIST')
    if v(r.get('lc_prior10_distribution_days')) > 3: reasons.append('PRIOR10_DIST')
    if v(r.get('lc_prior10_demand_days')) < 3: reasons.append('NO_DEMAND_HISTORY')
    if v(r.get('lc_bull_breadth')) > 0.50: reasons.append('BREADTH_HIGH')
    if not (2.0 <= v(r.get('risk_pct')) <= 5.5): reasons.append('BAD_RISK')
    if r.get('pd_zone') == 'STRUCTURE_LOW_RISK': reasons.append('STRUCTURE_LOW_RISK')
    if r.get('lc_entry_story') == 'REVERSAL_LIQUIDITY_TO_DEMAND':
        if r.get('stock_trend_state') not in {'DOWN_CONTINUATION', 'BEAR_TRANSITION', 'COMPRESSION_RANGE', 'EXPANSION_RANGE', 'RANGE'}: reasons.append('BAD_REVERSAL_CONTEXT')
        if r.get('stock_last_event') not in {'BULL_CHOCH', 'BULL_MSS'}: reasons.append('BAD_REVERSAL_EVENT')
    if r.get('lc_entry_story') == 'CONTINUATION_BOS_PULLBACK_TO_DEMAND':
        if r.get('stock_trend_state') != 'UP_CONTINUATION': reasons.append('BAD_CONTINUATION_CONTEXT')
        if r.get('stock_last_event') not in {'BULL_BOS', 'BULL_CHOCH'}: reasons.append('BAD_CONTINUATION_EVENT')
    return '+'.join(reasons) if reasons else 'PASS'


def resimulate_selected(r: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(r)
    ks = load_klines(str(r.get('symbol')))
    entry_idx = int(r.get('entry_idx') or -1)
    ep = v(r.get('entry_price'))
    zl = v(r.get('lc_poi_zone_low') or r.get('zone_low'))
    sl = min(v(r.get('sl')), zl * 0.995) if zl else v(r.get('sl'))
    tp1 = v(r.get('tp1'))
    if not ks or entry_idx < 0 or not ep or not sl or not tp1:
        return out
    sim = simulate(ks, entry_idx, ep, sl, tp1)
    if sim:
        out.update({f'v79_{k}': val for k, val in sim.items()})
        out['v79_pnl_pct'] = sim['pnl_pct']
        out['v79_exit_reason'] = sim['exit_reason']
    return out


def metrics_v79(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    xs = []
    for r in rows:
        nr = dict(r)
        if 'v79_pnl_pct' in nr:
            nr['pnl_pct'] = nr['v79_pnl_pct']
            nr['exit_reason'] = nr.get('v79_exit_reason')
        xs.append(nr)
    return metrics(xs)


def bucket_v79(rows: Iterable[Dict[str, Any]], key) -> Dict[str, Any]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[str(key(r))].append(r)
    return {k: metrics_v79(vs) for k, vs in sorted(groups.items())}


def main() -> None:
    annotated = json.loads((V78_AUDIT_DIR / 'v78_full_lifecycle_annotated.json').read_text())
    for r in annotated:
        r['v79_gate'] = passes_v79_gate(r)
        r['v79_reject_reason'] = reject_reason(r)
    selected = [resimulate_selected(r) for r in annotated if r.get('v79_gate')]
    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': 'V79_LIFECYCLE_GATE_FULL_CANDIDATE',
        'input': {'annotated': len(annotated), 'selected': len(selected)},
        'selected_original_exit': metrics([r for r in annotated if r.get('v79_gate')]),
        'selected_v79_resimulated': metrics_v79(selected),
        'buckets': {
            'year': bucket_v79(selected, lambda r: str(r.get('entry_date', ''))[:4]),
            'story': bucket_v79(selected, lambda r: r.get('lc_entry_story')),
            'market_state': bucket_v79(selected, lambda r: r.get('market_state_v74')),
            'pd_zone': bucket_v79(selected, lambda r: r.get('pd_zone')),
            'exit_reason': bucket_v79(selected, lambda r: r.get('v79_exit_reason', r.get('exit_reason'))),
        },
        'reject_counts': dict(Counter(r.get('v79_reject_reason') for r in annotated)),
        'production_ready': False,
        'production_blocker': 'Need stable 2023/2024 coverage and full 4905-stock fresh generation before production.',
        'files': {
            'annotated': str(OUT_DIR / 'v79_annotated.json'),
            'selected': str(OUT_DIR / 'v79_selected.json'),
            'report': str(OUT_DIR / 'v79_report.json'),
            'markdown': str(OUT_DIR / 'v79_report.md'),
        },
    }
    (OUT_DIR / 'v79_annotated.json').write_text(json.dumps(annotated, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v79_selected.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v79_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    md = ['# V79 全量候选生命周期门禁', '', '|口径|笔数|WR|均盈亏|SL率|累计|', '|---|---:|---:|---:|---:|---:|']
    for name in ['selected_original_exit', 'selected_v79_resimulated']:
        m = report[name]
        md.append(f"|{name}|{m['n']}|{m['wr']}%|{m['avg_pnl']}%|{m['sl_rate']}%|{m['cum']}|")
    md += ['', '## 分年', '', '|年份|笔数|WR|均盈亏|SL率|累计|', '|---|---:|---:|---:|---:|---:|']
    for y, m in report['buckets']['year'].items():
        md.append(f"|{y}|{m['n']}|{m['wr']}%|{m['avg_pnl']}%|{m['sl_rate']}%|{m['cum']}|")
    md.append('\n结论：V79 是全量候选层生命周期门禁验证，不接生产。')
    (OUT_DIR / 'v79_report.md').write_text('\n'.join(md))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
