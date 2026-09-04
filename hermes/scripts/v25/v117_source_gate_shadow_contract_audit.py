#!/usr/bin/env python3
"""V117 source gate shadow contract audit.

Research-only next stage after V116:
- Do not tune TP/SL.
- Do not alter production/API/frontend/monitor/watchlist.
- Recompute the exact V116 weak-source gate from stored V104 rows.
- Decide whether the gate is production-contract ready or blocked by scope/field contracts.
"""
from __future__ import annotations

import importlib.util
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path('/root/.hermes')
SCRIPT_DIR = ROOT / 'scripts' / 'v25'
AUDIT_DIR = ROOT / 'smc_audit'
OUT_JSON = AUDIT_DIR / 'v117_source_gate_shadow_contract_audit_20260619.json'
OUT_MD = AUDIT_DIR / 'v117_source_gate_shadow_contract_audit_20260619.md'
V104_TRADES = ROOT / 'smc_opt_v104_strict_reclaim' / 'v104_trades.json'
V116_JSON = AUDIT_DIR / 'v116_source_quality_gate_simulation_20260619.json'
PROD_FILES = {
    'v102_active': ROOT / 'smc_opt_v102_balanced_volume_gate' / 'v102_active_picks.json',
    'v102_candidate': ROOT / 'smc_opt_v102_balanced_volume_gate' / 'v102_candidate_picks.json',
    'v104_picks': ROOT / 'smc_opt_v104_strict_reclaim' / 'v104_picks.json',
}
NET_SUCCESS = 0.8
REQUIRED_GATE_FIELDS = ['family', 'retrace_pct', 'fvg_mid_body_atr']
ALT_FAMILY_FIELDS = ['family', 'combo_family']


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot import {path}')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


v115 = load_module('v115_fvg_source_label_fullsample_audit_v117', SCRIPT_DIR / 'v115_fvg_source_label_fullsample_audit.py')


def f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        v = float(x)
        return v if v == v else default
    except Exception:
        return default


def pct(num: float, den: float) -> float:
    return round(num * 100.0 / den, 2) if den else 0.0


def metric(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    vals = [f(r.get('net_pnl_pct')) for r in rows]
    wins = sum(v >= NET_SUCCESS for v in vals)
    sl = sum(r.get('exit_reason') == 'SL_HIT' for r in rows)
    return {
        'n': len(rows),
        'wins': wins,
        'wr': pct(wins, len(rows)),
        'sl_n': sl,
        'sl': pct(sl, len(rows)),
        'avg': round(statistics.mean(vals), 4) if vals else 0.0,
        'median': round(statistics.median(vals), 4) if vals else 0.0,
        'cum': round(sum(vals), 4),
        'months': len({str(r.get('entry_date', ''))[:6] for r in rows if r.get('entry_date')}),
    }


def gate_hit(row: Dict[str, Any]) -> bool:
    return (
        row.get('family') == 'CONTINUATION'
        and f(row.get('retrace_pct')) >= 95.0
        and f(row.get('fvg_mid_body_atr')) < 0.65
    )


def enrich(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        rr = v115.add_source_context(v115.enrich_indices(dict(r)))
        rr['v117_shadow_gate'] = 'REJECT_OR_DOWNGRADE' if gate_hit(rr) else 'KEEP'
        out.append(rr)
    return out


def dedup(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return v115.dedup_v110([v115.enrich_indices(dict(r)) for r in rows])


def gate_sim(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    keep = [r for r in rows if not gate_hit(r)]
    rej = [r for r in rows if gate_hit(r)]
    base_m, keep_m, rej_m = metric(rows), metric(keep), metric(rej)
    return {
        'baseline': base_m,
        'kept': keep_m,
        'rejected': rej_m,
        'delta': {
            'removed': base_m['n'] - keep_m['n'],
            'wr_pp': round(keep_m['wr'] - base_m['wr'], 2),
            'sl_pp': round(keep_m['sl'] - base_m['sl'], 2),
            'avg_pct': round(keep_m['avg'] - base_m['avg'], 4),
            'cum_delta_pct': round(keep_m['cum'] - base_m['cum'], 4),
        },
    }


def group_sim(rows: List[Dict[str, Any]], field: str) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[str(r.get(field, ''))].append(r)
    return {k: gate_sim(v) for k, v in sorted(groups.items())}


def month_check(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[str(r.get('entry_date', ''))[:6]].append(r)
    months = []
    for month, rs in sorted(groups.items()):
        sim = gate_sim(rs)
        months.append({'month': month, **sim})
    elig = [m for m in months if m['baseline']['n'] >= 3]
    hit_elig = [m for m in elig if m['rejected']['n'] > 0]
    improved = [m for m in hit_elig if m['delta']['wr_pp'] > 0 or m['delta']['avg_pct'] > 0]
    worsened = [m for m in hit_elig if m['delta']['wr_pp'] < 0 or m['delta']['avg_pct'] < 0]
    return {
        'months': len(months),
        'months_n_ge_3': len(elig),
        'gate_hit_months_n_ge_3': len(hit_elig),
        'improved_hit_months_n_ge_3': len(improved),
        'worsened_hit_months_n_ge_3': len(worsened),
        'worsened_months': [
            {
                'month': m['month'],
                'baseline_n': m['baseline']['n'],
                'rejected_n': m['rejected']['n'],
                'rejected_wr': m['rejected']['wr'],
                'rejected_avg': m['rejected']['avg'],
                'delta_wr_pp': m['delta']['wr_pp'],
                'delta_avg_pct': m['delta']['avg_pct'],
            }
            for m in worsened
        ],
    }


def rows_from_file(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return data
    for key in ['picks', 'data', 'rows', 'items']:
        if isinstance(data.get(key), list):
            return data[key]
    return []


def field_contract(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    present_counts = {field: sum(1 for r in rows if r.get(field) not in (None, '')) for field in REQUIRED_GATE_FIELDS}
    family_any = sum(1 for r in rows if any(r.get(k) not in (None, '') for k in ALT_FAMILY_FIELDS))
    computable = 0
    shadow_hits = 0
    for r in rows:
        fam = r.get('family') or r.get('combo_family')
        has_fields = fam not in (None, '') and r.get('retrace_pct') not in (None, '') and r.get('fvg_mid_body_atr') not in (None, '')
        if has_fields:
            computable += 1
            if fam == 'CONTINUATION' and f(r.get('retrace_pct')) >= 95.0 and f(r.get('fvg_mid_body_atr')) < 0.65:
                shadow_hits += 1
    return {
        'rows': n,
        'family_or_combo_family_present': family_any,
        'field_present_counts': present_counts,
        'computable_rows': computable,
        'shadow_gate_hits': shadow_hits,
        'contract_ready': n > 0 and computable == n,
        'missing_blocker': [field for field, c in present_counts.items() if c < n] + ([] if family_any == n else ['family/combo_family']),
    }


def t1_audit(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    same_day = [r for r in rows if r.get('entry_date') and r.get('exit_date') and r.get('entry_date') == r.get('exit_date')]
    bad_idx = [r for r in rows if r.get('entry_idx') is not None and r.get('exit_idx') is not None and int(r.get('exit_idx')) <= int(r.get('entry_idx'))]
    return {
        'same_day_exit_n': len(same_day),
        'exit_idx_lte_entry_idx_n': len(bad_idx),
        'ok': len(same_day) == 0 and len(bad_idx) == 0,
        'examples': [{'symbol': r.get('symbol'), 'entry_date': r.get('entry_date'), 'exit_date': r.get('exit_date')} for r in same_day[:5]],
    }


def fmt_metric(m: Dict[str, Any]) -> str:
    return f"{m['n']} / {m['wr']}% / {m['sl']}% / {m['avg']}% / {m['cum']}%"


def main() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    raw = json.loads(V104_TRADES.read_text())
    unique_all = enrich(dedup(raw))
    unique_range = [r for r in unique_all if r.get('trend_state') == 'RANGE_TRANSITION']
    unique_trend_up = [r for r in unique_all if r.get('trend_state') == 'TREND_UP']

    sims = {
        'all_unique': gate_sim(unique_all),
        'range_transition': gate_sim(unique_range),
        'trend_up': gate_sim(unique_trend_up),
        'by_trend_state': group_sim(unique_all, 'trend_state'),
        'by_mature': {
            'mature': gate_sim([r for r in unique_all if r.get('mature')]),
            'not_mature': gate_sim([r for r in unique_all if not r.get('mature')]),
        },
        'range_months': month_check(unique_range),
        'all_months': month_check(unique_all),
    }

    production_contract = {name: field_contract(rows_from_file(path)) for name, path in PROD_FILES.items()}
    prod_paths = {name: str(path) for name, path in PROD_FILES.items()}

    strong_full_retrace_kept = [
        r for r in unique_all
        if f(r.get('retrace_pct')) >= 95.0 and not gate_hit(r) and r.get('source_label') == 'STRONG_IMBALANCE_FULL_RETRACE'
    ]
    weak_body_other_kept = [
        r for r in unique_all
        if not gate_hit(r) and r.get('source_label') == 'WEAK_DISPLACEMENT_OTHER'
    ]

    blockers = []
    if production_contract['v102_candidate']['contract_ready'] is False:
        blockers.append('V102 candidate/active picks do not carry fvg_mid_body_atr, so exact gate cannot be computed in production contract yet.')
    if sims['trend_up']['rejected']['n'] and sims['trend_up']['rejected']['wr'] >= 40:
        blockers.append('Global hard-reject is unsafe: TREND_UP rejected bucket is not uniformly toxic; scope must remain RANGE_TRANSITION/shadow until source fields are propagated.')
    if sims['all_months']['worsened_hit_months_n_ge_3'] > 0:
        blockers.append('Monthly stability is not perfect; use downgrade/shadow first, not production hard reject.')
    if not t1_audit(unique_all)['ok']:
        blockers.append('T+1 audit failed.')

    decision = 'RESEARCH_ONLY_SHADOW_CONTRACT_BLOCKED_FIELD_PROPAGATION_REQUIRED' if blockers else 'SHADOW_READY_NOT_PROMOTED'

    report = {
        'version': 'V117_SOURCE_GATE_SHADOW_CONTRACT_AUDIT',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_files_touched': False,
        'tp_sl_tuning': False,
        'gate_rule': {
            'family': 'CONTINUATION',
            'retrace_pct_gte': 95.0,
            'fvg_mid_body_atr_lt': 0.65,
            'action': 'shadow reject/downgrade only',
        },
        'inputs': {
            'v104_trades': str(V104_TRADES),
            'v116_json': str(V116_JSON),
            'production_files_checked': prod_paths,
            'unique_all_rows': len(unique_all),
            'unique_range_transition_rows': len(unique_range),
            'unique_trend_up_rows': len(unique_trend_up),
        },
        'sims': sims,
        'production_field_contract': production_contract,
        't1_audit': t1_audit(unique_all),
        'not_global_full_retrace_ban': {
            'strong_full_retrace_kept_n': len(strong_full_retrace_kept),
            'strong_full_retrace_kept_metric': metric(strong_full_retrace_kept),
            'weak_body_other_kept_n': len(weak_body_other_kept),
            'weak_body_other_kept_metric': metric(weak_body_other_kept),
        },
        'blockers': blockers,
        'decision': decision,
        'next_required_work': [
            'Propagate source-quality fields into scanner/pick candidate rows: family, retrace_pct, fvg_mid_body_atr, source_label/v116_gate_reason.',
            'Keep gate in shadow/downgrade mode first; do not hard reject TREND_UP until scoped validation separates trend regimes.',
            'After field propagation, run one full daily scan dry-run and compare active/candidate/watch-only diffs before any production promotion.',
        ],
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = [
        '# V117 Source Gate Shadow Contract Audit',
        '',
        f'Decision: **{decision}**',
        '',
        'Research-only: no TP/SL tuning; no production/API/frontend/monitor writes.',
        '',
        'Gate:',
        '`family == CONTINUATION AND retrace_pct >= 95 AND fvg_mid_body_atr < 0.65`',
        '',
        '## Shadow metrics',
        '| Scope | Baseline n/WR/SL/Avg/Cum | Kept n/WR/SL/Avg/Cum | Rejected n/WR/SL/Avg/Cum | ΔWR | ΔSL | ΔAvg |',
        '|---|---:|---:|---:|---:|---:|---:|',
    ]
    for name in ['range_transition', 'trend_up', 'all_unique']:
        sim = sims[name]
        lines.append(f"| {name} | {fmt_metric(sim['baseline'])} | {fmt_metric(sim['kept'])} | {fmt_metric(sim['rejected'])} | {sim['delta']['wr_pp']} | {sim['delta']['sl_pp']} | {sim['delta']['avg_pct']} |")
    lines += [
        '',
        '## Monthly stability',
        '| Scope | months | n>=3 | gate-hit n>=3 | improved hit n>=3 | worsened hit n>=3 |',
        '|---|---:|---:|---:|---:|---:|',
        f"| RANGE_TRANSITION | {sims['range_months']['months']} | {sims['range_months']['months_n_ge_3']} | {sims['range_months']['gate_hit_months_n_ge_3']} | {sims['range_months']['improved_hit_months_n_ge_3']} | {sims['range_months']['worsened_hit_months_n_ge_3']} |",
        f"| ALL | {sims['all_months']['months']} | {sims['all_months']['months_n_ge_3']} | {sims['all_months']['gate_hit_months_n_ge_3']} | {sims['all_months']['improved_hit_months_n_ge_3']} | {sims['all_months']['worsened_hit_months_n_ge_3']} |",
        '',
        '## Production field contract',
        '| File | rows | computable rows | shadow hits | contract ready | missing blocker |',
        '|---|---:|---:|---:|---:|---|',
    ]
    for name, c in production_contract.items():
        lines.append(f"| {name} | {c['rows']} | {c['computable_rows']} | {c['shadow_gate_hits']} | {c['contract_ready']} | {', '.join(c['missing_blocker'])} |")
    lines += [
        '',
        '## Not global full-retrace ban check',
        f"- Strong full-retrace kept: n={len(strong_full_retrace_kept)}, metric={fmt_metric(metric(strong_full_retrace_kept))}",
        f"- Weak-body other kept: n={len(weak_body_other_kept)}, metric={fmt_metric(metric(weak_body_other_kept))}",
        '',
        '## T+1 audit',
        f"- same_day_exit_n={report['t1_audit']['same_day_exit_n']}",
        f"- exit_idx_lte_entry_idx_n={report['t1_audit']['exit_idx_lte_entry_idx_n']}",
        f"- ok={report['t1_audit']['ok']}",
        '',
        '## Blockers',
    ]
    lines += [f'- {b}' for b in blockers] if blockers else ['- None']
    lines += ['', '## Next required work']
    lines += [f"- {x}" for x in report['next_required_work']]
    OUT_MD.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    print(json.dumps({
        'ok': True,
        'out_json': str(OUT_JSON),
        'out_md': str(OUT_MD),
        'decision': decision,
        'range_delta': sims['range_transition']['delta'],
        'trend_up_delta': sims['trend_up']['delta'],
        'all_delta': sims['all_unique']['delta'],
        'production_contract_ready': {k: v['contract_ready'] for k, v in production_contract.items()},
        't1_ok': report['t1_audit']['ok'],
        'blocker_count': len(blockers),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
