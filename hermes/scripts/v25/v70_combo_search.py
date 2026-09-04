#!/usr/bin/env python3
"""V70 interpretable SMC combo search over V68 trades.

Isolated research script. Does not modify production files.
"""
from __future__ import annotations

import itertools
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

ROOT = Path('/root/.hermes')
TRADES = ROOT / 'smc_opt_v68_directional/v68_trades.json'
OUT_JSON = ROOT / 'smc_audit/v70_combo_search.json'
OUT_MD = ROOT / 'smc_audit/v70_combo_search.md'

TARGET_WR = 90.0
TARGET_SL = 10.0
TARGET_RR = 5.0
MIN_N = 20


def f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        return float(x)
    except Exception:
        return default


def enrich(row: Dict[str, Any]) -> Dict[str, Any]:
    r = dict(row)
    d = int(f(r.get('entry_date')))
    r['regime'] = 'PRE_2024' if d < 20240101 else 'Y2024' if d < 20250101 else 'Y2025_H1' if d < 20250701 else 'Y2025_H2' if d < 20260101 else 'Y2026'
    r['month'] = str(d)[:6]
    r['zone_to_entry'] = int(f(r.get('entry_index')) - f(r.get('zone_idx')))
    r['sweep_to_entry'] = int(f(r.get('entry_index')) - f(r.get('ssl_sweep_idx')))
    r['confirm_to_retrace'] = int(f(r.get('retrace_index')) - f(r.get('conf_index')))
    r['zone_to_confirm'] = int(f(r.get('conf_index')) - f(r.get('zone_idx')))
    r['sweep_depth'] = f(r.get('ssl_sweep_depth_pct'))
    r['risk'] = f(r.get('risk_pct'))
    r['rrv'] = f(r.get('rr'))
    r['pnl'] = f(r.get('pnl_pct'))
    r['sl_hit'] = r.get('exit_reason') == 'SL_HIT'
    r['win'] = r['pnl'] > 0
    return r


def metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {'n': 0}
    pnl = [r['pnl'] for r in rows]
    wins = [x for x in pnl if x > 0]
    losses = [-x for x in pnl if x < 0]
    avg_win = statistics.mean(wins) if wins else 0.0
    avg_loss = statistics.mean(losses) if losses else 0.0
    rr_real = avg_win / avg_loss if avg_loss else 999.0
    return {
        'n': len(rows),
        'wr': round(len(wins) / len(rows) * 100, 2),
        'sl_rate': round(sum(r['sl_hit'] for r in rows) / len(rows) * 100, 2),
        'avg_pnl': round(statistics.mean(pnl), 4),
        'median_pnl': round(sorted(pnl)[(len(pnl) - 1) // 2], 4),
        'avg_win': round(avg_win, 4),
        'avg_loss': round(avg_loss, 4),
        'realized_rr': round(rr_real, 3),
        'planned_rr_median': round(statistics.median([r['rrv'] for r in rows]), 3),
        'max_loss': round(min(pnl), 4),
        'max_win': round(max(pnl), 4),
        'exit_counts': dict(Counter(r.get('exit_reason') for r in rows)),
        'confirm_counts': dict(Counter(r.get('entry_confirm_type') for r in rows)),
        'fvg_counts': dict(Counter(r.get('fvg_role') for r in rows)),
        'regime_counts': dict(Counter(r.get('regime') for r in rows)),
    }


def make_predicates() -> Dict[str, Callable[[Dict[str, Any]], bool]]:
    return {
        'regime_2025H2': lambda r: r['regime'] == 'Y2025_H2',
        'regime_2025H1H2': lambda r: r['regime'] in {'Y2025_H1', 'Y2025_H2'},
        'exclude_2026': lambda r: r['regime'] != 'Y2026',
        'rr_ge2': lambda r: r['rrv'] >= 2.0,
        'rr_ge2_5': lambda r: r['rrv'] >= 2.5,
        'rr_ge3': lambda r: r['rrv'] >= 3.0,
        'risk_le5': lambda r: r['risk'] <= 5.0,
        'risk_le4': lambda r: r['risk'] <= 4.0,
        'risk_2_5': lambda r: 2.0 <= r['risk'] <= 5.0,
        'zone_fresh_le5': lambda r: r['zone_to_entry'] <= 5,
        'zone_fresh_le8': lambda r: r['zone_to_entry'] <= 8,
        'zone_age_3_10': lambda r: 3 <= r['zone_to_entry'] <= 10,
        'sweep_story_8_15': lambda r: 8 <= r['sweep_to_entry'] <= 15,
        'sweep_story_5_20': lambda r: 5 <= r['sweep_to_entry'] <= 20,
        'reaction_2_7': lambda r: 2 <= r['confirm_to_retrace'] <= 7,
        'reaction_1_5': lambda r: 1 <= r['confirm_to_retrace'] <= 5,
        'confirm_idm': lambda r: r.get('entry_confirm_type') == 'IDM_RECLAIM',
        'confirm_pinbar': lambda r: r.get('entry_confirm_type') == 'PINBAR_BOUNCE',
        'confirm_bull': lambda r: r.get('entry_confirm_type') == 'BULL_RECLAIM',
        'confirm_not_bull': lambda r: r.get('entry_confirm_type') != 'BULL_RECLAIM',
        'fvg_absent': lambda r: r.get('fvg_role') == 'ABSENT',
        'fvg_context': lambda r: r.get('fvg_role') == 'CONTEXT_ONLY',
        'sweep_depth_ge1': lambda r: r['sweep_depth'] >= 1.0,
        'sweep_depth_ge2': lambda r: r['sweep_depth'] >= 2.0,
        'sweep_depth_0_3': lambda r: 0 <= r['sweep_depth'] <= 3.0,
        # pre-entry-only proxy: entry next day starts and closes above entry price; no exit info.
        'entry_bar_bullish_proxy': lambda r: f(r.get('price')) >= f(r.get('entry_price')),
    }


def combo_key_score(metric: Dict[str, Any]) -> Tuple[float, float, float, int]:
    return (metric.get('wr', 0), -metric.get('sl_rate', 100), metric.get('realized_rr', 0), metric.get('n', 0))


def main() -> None:
    rows = [enrich(r) for r in json.loads(TRADES.read_text())]
    preds = make_predicates()
    all_results = []
    # Two-stage search: core interpretable structures first, then controlled hard-gate expansion.
    core_names = [
        'regime_2025H2', 'regime_2025H1H2', 'exclude_2026',
        'rr_ge2', 'rr_ge2_5', 'rr_ge3',
        'zone_fresh_le5', 'zone_fresh_le8', 'zone_age_3_10',
        'sweep_story_8_15', 'sweep_story_5_20',
        'reaction_2_7', 'reaction_1_5',
        'confirm_idm', 'confirm_pinbar', 'confirm_bull', 'confirm_not_bull',
        'fvg_absent', 'fvg_context',
    ]
    expansion_names = ['risk_le5', 'risk_le4', 'risk_2_5', 'sweep_depth_ge1', 'sweep_depth_ge2', 'sweep_depth_0_3', 'entry_bar_bullish_proxy']
    candidate_combos = set()
    for size in range(1, 5):
        for combo in itertools.combinations(core_names, size):
            candidate_combos.add(combo)
    stage1 = []
    for combo in candidate_combos:
        combo_set = set(combo)
        if {'confirm_idm', 'confirm_pinbar'} <= combo_set or {'confirm_idm', 'confirm_bull'} <= combo_set or {'confirm_pinbar', 'confirm_bull'} <= combo_set:
            continue
        if {'fvg_absent', 'fvg_context'} <= combo_set:
            continue
        if {'regime_2025H2', 'regime_2025H1H2'} <= combo_set:
            continue
        subset = [r for r in rows if all(preds[name](r) for name in combo)]
        if len(subset) < MIN_N:
            continue
        m = metrics(subset)
        item = {'combo': list(combo), 'metrics': m}
        all_results.append(item)
        if m['wr'] >= 55 and m['sl_rate'] <= 45 and m['avg_pnl'] > 1:
            stage1.append(combo)
    for combo in stage1:
        for exp_size in range(1, 4):
            for extra in itertools.combinations(expansion_names, exp_size):
                full = tuple(dict.fromkeys(combo + extra))
                combo_set = set(full)
                subset = [r for r in rows if all(preds[name](r) for name in full)]
                if len(subset) < MIN_N:
                    continue
                all_results.append({'combo': list(full), 'metrics': metrics(subset)})
    qualified = [r for r in all_results if r['metrics']['wr'] >= TARGET_WR and r['metrics']['sl_rate'] <= TARGET_SL and r['metrics']['realized_rr'] >= TARGET_RR]
    near = [r for r in all_results if r['metrics']['wr'] >= 80 and r['metrics']['sl_rate'] <= 25 and r['metrics']['realized_rr'] >= 2]
    all_results.sort(key=lambda r: combo_key_score(r['metrics']), reverse=True)
    qualified.sort(key=lambda r: (r['metrics']['n'], r['metrics']['avg_pnl']), reverse=True)
    near.sort(key=lambda r: (r['metrics']['wr'], -r['metrics']['sl_rate'], r['metrics']['n']), reverse=True)
    out = {
        'source': str(TRADES),
        'base': metrics(rows),
        'targets': {'wr_gt': TARGET_WR, 'realized_rr_gt': TARGET_RR, 'sl_rate_lt': TARGET_SL, 'min_n': MIN_N},
        'qualified_count': len(qualified),
        'qualified_top': qualified[:50],
        'near_top': near[:50],
        'overall_top': all_results[:100],
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    lines = ['# V70 组合搜索报告', '', f"基线: `{out['base']}`", '', '## 达标组合 Top', '']
    if not qualified:
        lines.append('无满足 WR>90、RealizedRR>5、SL<10、n>=20 的组合。')
    else:
        lines.append('| 组合 | n | WR | SL | RealizedRR | AvgPnL |')
        lines.append('|---|---:|---:|---:|---:|---:|')
        for r in qualified[:30]:
            m = r['metrics']
            lines.append(f"| {' + '.join(r['combo'])} | {m['n']} | {m['wr']} | {m['sl_rate']} | {m['realized_rr']} | {m['avg_pnl']} |")
    lines += ['', '## 接近组合 Top', '', '| 组合 | n | WR | SL | RealizedRR | AvgPnL |', '|---|---:|---:|---:|---:|---:|']
    for r in near[:30]:
        m = r['metrics']
        lines.append(f"| {' + '.join(r['combo'])} | {m['n']} | {m['wr']} | {m['sl_rate']} | {m['realized_rr']} | {m['avg_pnl']} |")
    OUT_MD.write_text('\n'.join(lines))
    print(json.dumps({k: out[k] for k in ['base','targets','qualified_count']}, ensure_ascii=False, indent=2))
    print('top qualified', qualified[:3])
    print('top near', near[:5])


if __name__ == '__main__':
    main()
