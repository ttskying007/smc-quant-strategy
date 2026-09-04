#!/usr/bin/env python3
"""V274 no-write: walk-forward stock-DNA selector for time-ordered SMC sequences.

Purpose:
- V272 proved broad BOS -> Demand -> Retest sequences have enough volume but poor global quality.
- V273 proved in-sample per-stock DNA can rescue quality, but may be overfit.
- V274 tests whether a stock's prior-year DNA can select a sequence family for the next year
  without using future outcomes.

No production/frontend/watchlist writes.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

BASE = Path('/root/.hermes')
KLINE_DIR = BASE / 'kline_cache'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = BASE / f'smc_audit/v274_walkforward_stock_dna_sequence_no_write_{TS}'
LATEST = BASE / 'smc_audit/v274_walkforward_stock_dna_sequence_latest.json'

BOS_LBS = [10, 20, 40]
DEMAND_LBS = [3, 5, 8, 12]
WAITS = [3, 5, 8, 12, 20]
MODES = ['strict_v262', 'soft_mid', 'touch_bull', 'support_hold']
EVAL_YEARS = ['2024', '2025', '2026']
SELECTOR_GRIDS = [
    {'name': 'loose_n3_wr55_avgpos', 'min_train_n': 3, 'min_train_wr': 55.0, 'min_train_avg': 0.0},
    {'name': 'base_n4_wr60_avgpos', 'min_train_n': 4, 'min_train_wr': 60.0, 'min_train_avg': 0.0},
    {'name': 'strict_n6_wr65_avgpos', 'min_train_n': 6, 'min_train_wr': 65.0, 'min_train_avg': 0.0},
    {'name': 'quality_n4_wr65_avg1', 'min_train_n': 4, 'min_train_wr': 65.0, 'min_train_avg': 1.0},
]


def fnum(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return d


def date_s(b: dict[str, Any]) -> str:
    return str(b.get('t', b.get('date', ''))).replace('.0', '')[:8]


def symbol_from_path(p: Path) -> str:
    s = p.stem.replace('_daily_750', '')
    code, exch = s.split('_', 1)
    return f'{code}.{exch}'


def mode_ok(mode: str, b: dict[str, Any], zl: float, zh: float) -> bool:
    o = fnum(b.get('o')); c = fnum(b.get('c')); h = fnum(b.get('h')); l = fnum(b.get('l'))
    rng = max(h - l, 1e-9)
    if l > zh * 1.005:
        return False
    if mode == 'strict_v262':
        return c >= zh and c > o and (c - l) / rng >= 0.55
    if mode == 'soft_mid':
        return c >= (zl + zh) / 2 and (c - l) / rng >= 0.45
    if mode == 'touch_bull':
        return c > o and c >= zl
    if mode == 'support_hold':
        return c >= zl
    return False


def replay(bars: list[dict[str, Any]], entry_i: int, entry: float, sl: float) -> tuple[float, str] | None:
    first = entry_i + 1
    if first >= len(bars):
        return None
    tp = entry + (entry - sl) * 1.5
    last = min(len(bars) - 1, entry_i + 10)
    exit_i = last
    exit_p = fnum(bars[last].get('c'))
    for i in range(first, last + 1):
        # A-share T+1: starts from entry_i+1, so same-date exit is impossible on daily bars.
        if fnum(bars[i].get('l')) <= sl:
            exit_i = i; exit_p = sl; break
        if fnum(bars[i].get('h')) >= tp:
            exit_i = i; exit_p = tp; break
    return (exit_p / entry - 1) * 100, date_s(bars[exit_i])


def variant_key(bos: int, demand: int, wait: int, mode: str) -> str:
    return f'bos{bos}_demand{demand}_wait{wait}_{mode}'


def scan_symbol(path: Path) -> list[dict[str, Any]]:
    try:
        bars = json.loads(path.read_text())
    except Exception:
        return []
    if len(bars) < 90:
        return []
    symbol = symbol_from_path(path)
    rows = []
    seen = defaultdict(set)
    for event_i in range(40, len(bars) - 2):
        e = bars[event_i]
        o = fnum(e.get('o')); c = fnum(e.get('c')); h = fnum(e.get('h')); l = fnum(e.get('l'))
        if c <= o or h <= l:
            continue
        demand_i = None
        for k in range(event_i - 1, max(event_i - max(DEMAND_LBS) - 1, -1), -1):
            if fnum(bars[k].get('c')) < fnum(bars[k].get('o')):
                demand_i = k
                break
        if demand_i is None:
            continue
        demand_dist = event_i - demand_i
        zl = fnum(bars[demand_i].get('l'))
        zh = max(fnum(bars[demand_i].get('o')), fnum(bars[demand_i].get('c')))
        if zl <= 0 or zh <= zl:
            continue
        first_by_mode = {}
        max_last = min(event_i + max(WAITS), len(bars) - 2)
        for mode in MODES:
            for ri in range(event_i + 1, max_last + 1):
                if mode_ok(mode, bars[ri], zl, zh):
                    first_by_mode[mode] = ri
                    break
        if not first_by_mode:
            continue
        for bos_lb in BOS_LBS:
            ph = max(fnum(x.get('h')) for x in bars[event_i - bos_lb:event_i])
            if c <= ph:
                continue
            for demand_lb in DEMAND_LBS:
                if demand_dist > demand_lb:
                    continue
                for mode, ri in first_by_mode.items():
                    delay = ri - event_i
                    entry_i = ri + 1
                    if entry_i >= len(bars):
                        continue
                    entry = fnum(bars[entry_i].get('o'))
                    sl = zl * 0.99
                    risk = (entry / sl - 1) * 100
                    if not (0.8 <= risk <= 12.0):
                        continue
                    rep = replay(bars, entry_i, entry, sl)
                    if rep is None:
                        continue
                    pnl, exit_date = rep
                    entry_date = date_s(bars[entry_i])
                    for wait in WAITS:
                        if delay > wait:
                            continue
                        key = variant_key(bos_lb, demand_lb, wait, mode)
                        if entry_i in seen[key]:
                            continue
                        seen[key].add(entry_i)
                        rows.append({
                            'symbol': symbol, 'entry_date': entry_date, 'year': entry_date[:4],
                            'exit_date': exit_date, 'pnl': pnl, 'win': pnl > 0,
                            'variant': key, 'bos_lookback': bos_lb, 'demand_lookback': demand_lb,
                            'wait_max': wait, 'reclaim_mode': mode,
                            'event_i': event_i, 'demand_i': demand_i, 'retest_i': ri, 'entry_i': entry_i,
                            'risk_pct': risk,
                        })
    return rows


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {'n': 0}
    n = len(rows)
    wins = sum(1 for r in rows if r['pnl'] > 0)
    micro = sum(1 for r in rows if 0 < r['pnl'] < 1)
    years = defaultdict(list)
    for r in rows:
        years[r['year']].append(r['pnl'])
    return {
        'n': n,
        'wr': round(wins / n * 100, 4),
        'avg': round(sum(r['pnl'] for r in rows) / n, 4),
        'loss': n - wins,
        'micro': round(micro / n * 100, 4),
        'year_counts': {y: len(v) for y, v in sorted(years.items())},
        'year_wr': {y: round(sum(p > 0 for p in v) / len(v) * 100, 2) for y, v in sorted(years.items())},
    }


def train_stats(rows: list[dict[str, Any]], eval_year: str) -> dict[tuple[str, str], dict[str, Any]]:
    bucket = defaultdict(list)
    for r in rows:
        if r['year'] < eval_year:
            bucket[(r['symbol'], r['variant'])].append(r)
    return {k: metrics(v) for k, v in bucket.items()}


def selected_variants(rows: list[dict[str, Any]], eval_year: str, grid: dict[str, Any]) -> dict[str, dict[str, Any]]:
    stats = train_stats(rows, eval_year)
    by_symbol = defaultdict(list)
    for (symbol, var), m in stats.items():
        if (m.get('n', 0) >= grid['min_train_n'] and m.get('wr', 0) >= grid['min_train_wr'] and m.get('avg', -999) > grid['min_train_avg']):
            by_symbol[symbol].append({'symbol': symbol, 'variant': var, **m})
    selected = {}
    for symbol, candidates in by_symbol.items():
        candidates.sort(key=lambda x: (x['wr'], x['avg'], x['n']), reverse=True)
        selected[symbol] = candidates[0]
    return selected


def walk_forward(rows: list[dict[str, Any]], grid: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    eval_rows = []
    selections = []
    for y in EVAL_YEARS:
        selected = selected_variants(rows, y, grid)
        for s, sel in selected.items():
            selections.append({'eval_year': y, **sel})
        for r in rows:
            sel = selected.get(r['symbol'])
            if r['year'] == y and sel and r['variant'] == sel['variant']:
                nr = dict(r)
                nr['selector'] = grid['name']
                nr['train_n'] = sel['n']; nr['train_wr'] = sel['wr']; nr['train_avg'] = sel['avg']
                eval_rows.append(nr)
    return eval_rows, selections


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    paths = sorted(KLINE_DIR.glob('*_daily_750.json'))
    rows = []
    for i, p in enumerate(paths, 1):
        rows.extend(scan_symbol(p))
        if i % 500 == 0:
            print(f'scanned {i}/{len(paths)} rows={len(rows)}', flush=True)
    # Keep full candidate rows in memory only; writing ~9M variant-expanded rows is slow
    # and not needed for the walk-forward conclusion. Persist only selector eval rows below.
    all_path = None

    summary = {
        'version': 'V274_WALKFORWARD_STOCK_DNA_SEQUENCE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'out_dir': str(OUT),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'inputs': {'kline_dir': str(KLINE_DIR), 'kline_files': len(paths), 'variant_rows': len(rows)},
        'baseline_all_variants': metrics(rows),
        'selectors': {},
        'artifacts': {'all_variant_rows': None},
    }

    for grid in SELECTOR_GRIDS:
        eval_rows, selections = walk_forward(rows, grid)
        eval_path = OUT / f"{grid['name']}_eval_rows.csv"
        sel_path = OUT / f"{grid['name']}_selections.csv"
        pd.DataFrame(eval_rows).to_csv(eval_path, index=False)
        pd.DataFrame(selections).to_csv(sel_path, index=False)
        per_year = {y: metrics([r for r in eval_rows if r['year'] == y]) for y in EVAL_YEARS}
        active_symbols_by_year = {y: len({r['symbol'] for r in eval_rows if r['year'] == y}) for y in EVAL_YEARS}
        summary['selectors'][grid['name']] = {
            'grid': grid,
            'walk_forward': metrics(eval_rows),
            'per_year': per_year,
            'selected_symbol_count_by_year': {y: sum(1 for s in selections if s['eval_year'] == y) for y in EVAL_YEARS},
            'traded_symbol_count_by_year': active_symbols_by_year,
            'artifacts': {'eval_rows': str(eval_path), 'selections': str(sel_path)},
        }

    # In-sample oracle upper bound: best stock+variant over the same 2024-2026 period.
    eval_period = [r for r in rows if r['year'] in EVAL_YEARS]
    by_sv = defaultdict(list)
    for r in eval_period:
        by_sv[(r['symbol'], r['variant'])].append(r)
    oracle_keys = {k for k, v in by_sv.items() if metrics(v).get('n', 0) >= 4 and metrics(v).get('wr', 0) >= 60 and metrics(v).get('avg', -999) > 0}
    oracle_rows = [r for r in eval_period if (r['symbol'], r['variant']) in oracle_keys]
    summary['in_sample_oracle_upper_bound_2024_2026'] = {
        'filter': 'per symbol+variant n>=4 wr>=60 avg>0 using eval-period outcomes (leaky upper bound only)',
        'qualified_symbol_variant_count': len(oracle_keys),
        'metrics': metrics(oracle_rows),
    }

    (OUT / 'v274_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:12000])


if __name__ == '__main__':
    main()
