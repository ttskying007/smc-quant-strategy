#!/usr/bin/env python3
"""Directional edge gate for SMC candidate trades.

A candidate that cannot beat same-symbol random entries must not be promoted,
even if its signal geometry is semantically valid.
"""
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
AUDIT.mkdir(parents=True, exist_ok=True)
DEFAULT_TRADES = ROOT / 'smc_opt_v67_strict/v67_trades.json'
OUT = AUDIT / 'v67_directional_edge_gate.json'

HORIZONS = [1, 2, 3, 5, 10, 20]
MIN_MEAN_EDGE = 0.10
MIN_POS_RATE_EDGE = 1.00
MIN_PASS_HORIZONS = 4


def f(x: Any, default: float = 0.0) -> float:
    try:
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


def main() -> None:
    trade_path = DEFAULT_TRADES
    trades = json.loads(trade_path.read_text())
    kline_cache: Dict[str, List[Dict[str, Any]]] = {}
    candidate_returns = {h: [] for h in HORIZONS}
    by_symbol = defaultdict(list)
    for trade in trades:
        symbol = trade.get('symbol')
        if not symbol:
            continue
        if symbol not in kline_cache:
            kline_cache[symbol] = load_klines(symbol)
        bars = kline_cache[symbol]
        entry_idx = int(trade.get('entry_index', -1))
        if not bars or entry_idx < 0:
            continue
        by_symbol[symbol].append(entry_idx)
        for h in HORIZONS:
            value = forward_return(bars, entry_idx, h)
            if value is not None:
                candidate_returns[h].append(value)

    random.seed(67)
    baseline_returns = {h: [] for h in HORIZONS}
    for symbol, entries in by_symbol.items():
        bars = kline_cache.get(symbol, [])
        valid = list(range(80, max(80, len(bars) - max(HORIZONS) - 1)))
        if not valid:
            continue
        for entry_idx in random.choices(valid, k=len(entries)):
            for h in HORIZONS:
                value = forward_return(bars, entry_idx, h)
                if value is not None:
                    baseline_returns[h].append(value)

    comparisons = {}
    pass_horizons = 0
    for h in HORIZONS:
        cand = summarize(candidate_returns[h])
        base = summarize(baseline_returns[h])
        mean_edge = round(cand['mean'] - base['mean'], 4)
        pos_edge = round(cand['pos_rate'] - base['pos_rate'], 4)
        horizon_pass = mean_edge >= MIN_MEAN_EDGE and pos_edge >= MIN_POS_RATE_EDGE
        if horizon_pass:
            pass_horizons += 1
        comparisons[str(h)] = {
            'candidate': cand,
            'same_symbol_random': base,
            'mean_edge': mean_edge,
            'pos_rate_edge': pos_edge,
            'pass': horizon_pass,
        }

    directional_edge_pass = pass_horizons >= MIN_PASS_HORIZONS
    out = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'trade_file': str(trade_path),
        'gate': 'directional_edge_vs_same_symbol_random',
        'thresholds': {
            'MIN_MEAN_EDGE': MIN_MEAN_EDGE,
            'MIN_POS_RATE_EDGE': MIN_POS_RATE_EDGE,
            'MIN_PASS_HORIZONS': MIN_PASS_HORIZONS,
            'HORIZONS': HORIZONS,
        },
        'pass_horizons': pass_horizons,
        'directional_edge_pass': directional_edge_pass,
        'decision': 'PASS' if directional_edge_pass else 'BLOCK_DIRECTIONAL_EDGE',
        'comparisons': comparisons,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
