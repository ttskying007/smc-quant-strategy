#!/usr/bin/env python3
"""Directional edge gate for V69 missing-gates filtered subsets."""
from __future__ import annotations

import json
import random
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path('/root/.hermes')
KLINE_DIR = ROOT / 'kline_cache'
AUDIT = ROOT / 'smc_audit'
TRADES = ROOT / 'smc_opt_v68_directional/v68_trades.json'
OUT = AUDIT / 'v69_missing_gates_directional_edge.json'
HORIZONS = [1, 2, 3, 5, 10, 20]
MIN_MEAN_EDGE = 0.10
MIN_POS_RATE_EDGE = 1.00
MIN_PASS_HORIZONS = 4


def f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        return float(x)
    except Exception:
        return default


def load_klines(symbol: str) -> List[Dict[str, Any]]:
    code, exchange = symbol.split('.')
    for name in (f'{code}_{exchange}_daily_750.json', f'{code}_{exchange}_daily_300.json'):
        path = KLINE_DIR / name
        if path.exists():
            return json.loads(path.read_text())
    return []


def forward_return(bars: List[Dict[str, Any]], entry_idx: int, horizon: int) -> Optional[float]:
    if entry_idx + horizon >= len(bars):
        return None
    entry = f(bars[entry_idx].get('o'))
    exit_close = f(bars[entry_idx + horizon].get('c'))
    if entry <= 0:
        return None
    return (exit_close - entry) / entry * 100


def summarize(vals: List[float]) -> Dict[str, Any]:
    if not vals:
        return {'n': 0, 'pos_rate': 0, 'mean': 0, 'median': 0}
    ordered = sorted(vals)
    return {
        'n': len(vals),
        'pos_rate': round(sum(v > 0 for v in vals) / len(vals) * 100, 2),
        'mean': round(statistics.mean(vals), 4),
        'median': round(ordered[(len(ordered) - 1) // 2], 4),
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
    r['confirm_to_retrace_bars'] = int(f(r.get('retrace_index')) - f(r.get('conf_index')))
    r['regime_switch_pass'] = regime == 'Y2025_H2'
    r['zone_age_pass'] = r['zone_to_entry_bars'] <= 5
    r['liquidity_story_pass'] = 8 <= r['sweep_to_entry_bars'] <= 15
    r['reaction_timing_pass'] = 2 <= r['confirm_to_retrace_bars'] <= 7
    r['mtf_proxy_pass'] = r.get('exit_reason') != 'SL_HIT' or int(f(r.get('hold_bars'))) >= 3
    r['rr_quality_pass'] = f(r.get('rr')) >= 2.0
    r['fvg_absent_pass'] = r.get('fvg_role') == 'ABSENT'
    r['idm_pass'] = r.get('entry_confirm_type') == 'IDM_RECLAIM'
    return r


def subset_predicates():
    return {
        'five_core_gates': lambda r: all([r['regime_switch_pass'], r['zone_age_pass'], r['liquidity_story_pass'], r['reaction_timing_pass'], r['mtf_proxy_pass']]),
        'best_regime_mtf_rr': lambda r: r['regime_switch_pass'] and r['mtf_proxy_pass'] and r['rr_quality_pass'],
        'best_regime_reaction_mtf_rr': lambda r: r['regime_switch_pass'] and r['reaction_timing_pass'] and r['mtf_proxy_pass'] and r['rr_quality_pass'],
        'best_sweep_mtf_rr_fvg_absent': lambda r: r['liquidity_story_pass'] and r['mtf_proxy_pass'] and r['rr_quality_pass'] and r['fvg_absent_pass'],
        'best_reaction_mtf_rr_idm': lambda r: r['reaction_timing_pass'] and r['mtf_proxy_pass'] and r['rr_quality_pass'] and r['idm_pass'],
        'no_mtf_regime_rr': lambda r: r['regime_switch_pass'] and r['rr_quality_pass'],
        'no_mtf_sweep_rr_fvg_absent': lambda r: r['liquidity_story_pass'] and r['rr_quality_pass'] and r['fvg_absent_pass'],
    }


def edge_for_subset(name: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    kline_cache: Dict[str, List[Dict[str, Any]]] = {}
    candidate_returns = {h: [] for h in HORIZONS}
    by_symbol = defaultdict(list)
    for trade in rows:
        symbol = trade.get('symbol')
        if not symbol:
            continue
        if symbol not in kline_cache:
            kline_cache[symbol] = load_klines(symbol)
        bars = kline_cache[symbol]
        entry_idx = int(f(trade.get('entry_index'), -1))
        if not bars or entry_idx < 0:
            continue
        by_symbol[symbol].append(entry_idx)
        for horizon in HORIZONS:
            value = forward_return(bars, entry_idx, horizon)
            if value is not None:
                candidate_returns[horizon].append(value)
    random.seed(6900 + len(rows))
    baseline_returns = {h: [] for h in HORIZONS}
    for symbol, entries in by_symbol.items():
        bars = kline_cache.get(symbol, [])
        valid = list(range(80, max(80, len(bars) - max(HORIZONS) - 1)))
        if not valid:
            continue
        for entry_idx in random.choices(valid, k=len(entries)):
            for horizon in HORIZONS:
                value = forward_return(bars, entry_idx, horizon)
                if value is not None:
                    baseline_returns[horizon].append(value)
    comparisons = {}
    pass_horizons = 0
    for horizon in HORIZONS:
        cand = summarize(candidate_returns[horizon])
        base = summarize(baseline_returns[horizon])
        mean_edge = round(cand['mean'] - base['mean'], 4)
        pos_edge = round(cand['pos_rate'] - base['pos_rate'], 4)
        horizon_pass = mean_edge >= MIN_MEAN_EDGE and pos_edge >= MIN_POS_RATE_EDGE
        pass_horizons += 1 if horizon_pass else 0
        comparisons[str(horizon)] = {
            'candidate': cand,
            'same_symbol_random': base,
            'mean_edge': mean_edge,
            'pos_rate_edge': pos_edge,
            'pass': horizon_pass,
        }
    return {
        'subset': name,
        'n_trades': len(rows),
        'pass_horizons': pass_horizons,
        'directional_edge_pass': pass_horizons >= MIN_PASS_HORIZONS,
        'comparisons': comparisons,
    }


def main() -> None:
    rows = [add_features(r) for r in json.loads(TRADES.read_text())]
    results = []
    for name, pred in subset_predicates().items():
        subset = [r for r in rows if pred(r)]
        if len(subset) < 20:
            results.append({'subset': name, 'n_trades': len(subset), 'directional_edge_pass': False, 'reason': 'TOO_FEW_TRADES'})
            continue
        results.append(edge_for_subset(name, subset))
    out = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'trade_file': str(TRADES),
        'gate': 'v69_filtered_subset_directional_edge_vs_same_symbol_random',
        'thresholds': {'MIN_MEAN_EDGE': MIN_MEAN_EDGE, 'MIN_POS_RATE_EDGE': MIN_POS_RATE_EDGE, 'MIN_PASS_HORIZONS': MIN_PASS_HORIZONS, 'HORIZONS': HORIZONS},
        'results': results,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
