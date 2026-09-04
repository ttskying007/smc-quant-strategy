#!/usr/bin/env python3
"""V69 missing-gates audit over V68 directional trades.

This is an isolated diagnostic: it does not change production or frontend files.
It tests the five suspected missing layers:
1) market/regime switch, 2) zone freshness, 3) liquidity-story freshness,
4) follow-through confirmation, 5) MTF proxy readiness.
"""
from __future__ import annotations

import itertools
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Tuple

ROOT = Path('/root/.hermes')
SRC = ROOT / 'smc_opt_v68_directional' / 'v68_trades.json'
OUT_DIR = ROOT / 'smc_audit'
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT = OUT_DIR / 'v69_missing_gates_audit.json'
MD = OUT_DIR / 'v69_missing_gates_audit.md'

MIN_N = 30
PROD_WR = 70.0
MAX_SL = 30.0
MIN_AVG = 1.0


def f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == '':
            return default
        return float(value)
    except Exception:
        return default


def pct(n: int, d: int) -> float:
    return round(n / d * 100, 2) if d else 0.0


def metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {'n': 0}
    pnls = [f(r.get('pnl_pct')) for r in rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    sls = [r for r in rows if r.get('exit_reason') == 'SL_HIT']
    return {
        'n': len(rows),
        'wr': round(len(wins) / len(rows) * 100, 2),
        'avg_pnl': round(statistics.mean(pnls), 3),
        'median_pnl': round(statistics.median(pnls), 3),
        'sl_rate': round(len(sls) / len(rows) * 100, 2),
        'avg_win': round(statistics.mean(wins), 3) if wins else 0,
        'avg_loss_abs': round(abs(statistics.mean(losses)), 3) if losses else 0,
        'exit_counts': dict(Counter(r.get('exit_reason') for r in rows)),
    }


def add_features(row: Dict[str, Any]) -> Dict[str, Any]:
    r = dict(row)
    entry_date = int(f(r.get('entry_date')))
    if entry_date < 20240101:
        regime = 'PRE_2024'
    elif entry_date < 20250101:
        regime = 'Y2024'
    elif entry_date < 20250701:
        regime = 'Y2025_H1'
    elif entry_date < 20260101:
        regime = 'Y2025_H2'
    else:
        regime = 'Y2026'
    r['regime_bucket'] = regime
    r['zone_to_entry_bars'] = int(f(r.get('entry_index')) - f(r.get('zone_idx')))
    r['sweep_to_entry_bars'] = int(f(r.get('entry_index')) - f(r.get('ssl_sweep_idx')))
    r['confirm_to_entry_bars'] = int(f(r.get('entry_index')) - f(r.get('conf_index')))
    r['confirm_to_retrace_bars'] = int(f(r.get('retrace_index')) - f(r.get('conf_index')))
    r['zone_age_pass'] = r['zone_to_entry_bars'] <= 5
    r['liquidity_story_pass'] = 8 <= r['sweep_to_entry_bars'] <= 15
    r['reaction_timing_pass'] = 2 <= r['confirm_to_retrace_bars'] <= 7
    r['rr_quality_pass'] = f(r.get('rr')) >= 2.0
    r['fvg_absent_pass'] = r.get('fvg_role') == 'ABSENT'
    r['idm_pass'] = r.get('entry_confirm_type') == 'IDM_RECLAIM'
    r['regime_switch_pass'] = regime == 'Y2025_H2'
    # MTF proxy only: with daily data, later holds and no immediate SL are the closest
    # available proxy for lower-timeframe confirmation. It must not be treated as true 60m validation.
    r['mtf_proxy_pass'] = r.get('exit_reason') != 'SL_HIT' or int(f(r.get('hold_bars'))) >= 3
    r['five_gate_pass'] = all([
        r['regime_switch_pass'],
        r['zone_age_pass'],
        r['liquidity_story_pass'],
        r['reaction_timing_pass'],
        r['mtf_proxy_pass'],
    ])
    return r


def bucket(rows: List[Dict[str, Any]], field: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for value in sorted({str(r.get(field)) for r in rows}):
        out[value] = metrics([r for r in rows if str(r.get(field)) == value])
    return out


def test_filter(rows: List[Dict[str, Any]], name: str, fn: Callable[[Dict[str, Any]], bool]) -> Dict[str, Any]:
    passed = [r for r in rows if fn(r)]
    rejected = [r for r in rows if not fn(r)]
    m = metrics(passed)
    base = metrics(rows)
    return {
        'name': name,
        'passed': m,
        'rejected': metrics(rejected),
        'delta_wr_vs_base': round(m.get('wr', 0) - base.get('wr', 0), 2),
        'delta_avg_vs_base': round(m.get('avg_pnl', 0) - base.get('avg_pnl', 0), 3),
        'effect_pass': m.get('n', 0) >= MIN_N and m.get('wr', 0) >= PROD_WR and m.get('sl_rate', 100) <= MAX_SL and m.get('avg_pnl', -999) >= MIN_AVG,
    }


def combo_tests(rows: List[Dict[str, Any]], filters: List[Tuple[str, Callable[[Dict[str, Any]], bool]]]) -> List[Dict[str, Any]]:
    results = []
    for size in range(2, min(6, len(filters)) + 1):
        for combo in itertools.combinations(filters, size):
            names = [c[0] for c in combo]
            selected = [r for r in rows if all(fn(r) for _, fn in combo)]
            if len(selected) < MIN_N:
                continue
            m = metrics(selected)
            results.append({
                'combo': names,
                'metrics': m,
                'effect_pass': m.get('wr', 0) >= PROD_WR and m.get('sl_rate', 100) <= MAX_SL and m.get('avg_pnl', -999) >= MIN_AVG,
            })
    results.sort(key=lambda x: (x['effect_pass'], x['metrics'].get('wr', 0), x['metrics'].get('avg_pnl', 0), x['metrics'].get('n', 0)), reverse=True)
    return results


def same_symbol_random_edge_note(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Use previous V68 directional edge result as authoritative if present.
    path = OUT_DIR / 'v68_directional_edge_gate.json'
    if path.exists():
        data = json.loads(path.read_text())
        return {
            'source': str(path),
            'v68_pass_horizons': data.get('pass_horizons'),
            'v68_directional_edge_pass': data.get('directional_edge_pass'),
            'v68_decision': data.get('decision'),
            'note': 'Filtered subset directional edge still needs a same-symbol random rerun before promotion.',
        }
    return {'source': None, 'note': 'No prior directional edge file found.'}


def main() -> None:
    raw = json.loads(SRC.read_text())
    rows = [add_features(r) for r in raw]
    base = metrics(rows)
    filters: List[Tuple[str, Callable[[Dict[str, Any]], bool]]] = [
        ('regime_2025H2_only', lambda r: r['regime_switch_pass']),
        ('zone_age_le5', lambda r: r['zone_age_pass']),
        ('sweep_to_entry_8_15', lambda r: r['liquidity_story_pass']),
        ('confirm_retrace_2_7', lambda r: r['reaction_timing_pass']),
        ('mtf_daily_proxy_not_immediate_sl', lambda r: r['mtf_proxy_pass']),
        ('rr_ge2', lambda r: r['rr_quality_pass']),
        ('fvg_absent', lambda r: r['fvg_absent_pass']),
        ('idm_reclaim', lambda r: r['idm_pass']),
    ]
    single = [test_filter(rows, name, fn) for name, fn in filters]
    combos = combo_tests(rows, filters)
    five_gate_rows = [r for r in rows if r['five_gate_pass']]
    best = combos[:20]
    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'source': str(SRC),
        'audit': 'V69_MISSING_GATES_ISOLATED_DIAGNOSTIC',
        'production_unchanged': True,
        'base': base,
        'buckets': {
            'regime_bucket': bucket(rows, 'regime_bucket'),
            'entry_confirm_type': bucket(rows, 'entry_confirm_type'),
            'fvg_role': bucket(rows, 'fvg_role'),
        },
        'single_gate_tests': single,
        'five_core_gate_metrics': metrics(five_gate_rows),
        'five_core_gate_n': len(five_gate_rows),
        'best_combinations_top20': best,
        'directional_edge_context': same_symbol_random_edge_note(rows),
        'decision': 'NO_PROMOTION_CANDIDATE' if not any(x['effect_pass'] for x in combos) else 'NEEDS_FULL_ENGINE_AND_EDGE_RERUN',
        'hard_findings': [],
        'limitations': [
            'The fifth item is only a daily-data MTF proxy; real 60min/15min confirmation was not available in the detected cache.',
            'These are filtered V68 trades, not a regenerated engine scan; a passing subset must be rebuilt as an engine and rerun against same-symbol random baseline.',
        ],
    }
    if report['five_core_gate_metrics'].get('n', 0) < MIN_N:
        report['hard_findings'].append('All five core gates together produce fewer than 30 trades; too sparse for production.')
    if report['five_core_gate_metrics'].get('wr', 0) < PROD_WR:
        report['hard_findings'].append('Five core gates do not reach production win-rate threshold.')
    if report['five_core_gate_metrics'].get('sl_rate', 100) > MAX_SL:
        report['hard_findings'].append('Five core gates do not reduce SL rate enough.')
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    lines = []
    lines.append('# V69 Missing Gates Audit')
    lines.append('')
    lines.append(f"Generated: {report['generated_at']}")
    lines.append('')
    lines.append('## Base')
    lines.append(f"- n={base['n']} WR={base['wr']} avg={base['avg_pnl']} SL={base['sl_rate']}")
    lines.append('')
    lines.append('## Single Gates')
    for item in single:
        p = item['passed']
        lines.append(f"- {item['name']}: n={p.get('n',0)} WR={p.get('wr',0)} avg={p.get('avg_pnl',0)} SL={p.get('sl_rate',0)} ΔWR={item['delta_wr_vs_base']}")
    lines.append('')
    lines.append('## Five Core Gates')
    fg = report['five_core_gate_metrics']
    lines.append(f"- n={fg.get('n',0)} WR={fg.get('wr',0)} avg={fg.get('avg_pnl',0)} SL={fg.get('sl_rate',0)}")
    lines.append('')
    lines.append('## Best Combinations')
    for item in best[:10]:
        m = item['metrics']
        lines.append(f"- {' + '.join(item['combo'])}: n={m.get('n',0)} WR={m.get('wr',0)} avg={m.get('avg_pnl',0)} SL={m.get('sl_rate',0)} pass={item['effect_pass']}")
    lines.append('')
    lines.append('## Decision')
    lines.append(f"- {report['decision']}")
    lines.append('')
    lines.append('## Limitations')
    for item in report['limitations']:
        lines.append(f"- {item}")
    MD.write_text('\n'.join(lines) + '\n')
    print(json.dumps({
        'output': str(OUT),
        'markdown': str(MD),
        'decision': report['decision'],
        'base': base,
        'five_core_gate_metrics': report['five_core_gate_metrics'],
        'best': best[:5],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
