#!/usr/bin/env python3
"""
V94 post-exit TP/SL autopsy for V88 production trades.

Purpose: after each historical sell/exit, replay the next N daily bars to see
whether price continued strongly upward or downward. This directly tests whether
TP exits are too early, SL exits are too tight/late, and TIME_STOP exits miss
runners.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List, Optional

ROOT = Path('/root/.hermes')
TRADES = ROOT / 'smc_opt_v88_production_contract' / 'v88_trades.json'
KLINE_DIR = ROOT / 'kline_cache'
OUT_DIR = ROOT / 'smc_opt_v94_post_exit_tp_sl_autopsy'
OUT_DIR.mkdir(parents=True, exist_ok=True)

WINDOWS = [1, 3, 5, 10, 20, 40, 60]


def num(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def kline_path(symbol: str) -> Path:
    code, ex = symbol.split('.')
    return KLINE_DIR / f'{code}_{ex}_daily_750.json'


def load_kline(symbol: str) -> List[Dict[str, Any]]:
    p = kline_path(symbol)
    if not p.exists():
        p = KLINE_DIR / f"{symbol.replace('.', '_')}_daily_300.json"
    if not p.exists():
        return []
    rows = json.loads(p.read_text())
    # Tencent cache rows have t/o/h/l/c fields.
    out = []
    for i, b in enumerate(rows):
        out.append({
            'idx': i,
            'date': str(b.get('t') or b.get('date') or ''),
            'open': num(b.get('o') or b.get('open')),
            'high': num(b.get('h') or b.get('high')),
            'low': num(b.get('l') or b.get('low')),
            'close': num(b.get('c') or b.get('close')),
        })
    return out


def index_by_date(ks: List[Dict[str, Any]]) -> Dict[str, int]:
    return {b['date']: i for i, b in enumerate(ks) if b.get('date')}


def trade_exit_idx(tr: Dict[str, Any], ks: List[Dict[str, Any]]) -> Optional[int]:
    by_date = index_by_date(ks)
    d = str(tr.get('exit_date') or '')
    if d in by_date:
        return by_date[d]
    ei = tr.get('exit_idx')
    if isinstance(ei, int) and 0 <= ei < len(ks):
        return ei
    return None


def close_at_entry(tr: Dict[str, Any], ks: List[Dict[str, Any]]) -> Optional[int]:
    by_date = index_by_date(ks)
    d = str(tr.get('entry_date') or '')
    if d in by_date:
        return by_date[d]
    ei = tr.get('entry_idx')
    if isinstance(ei, int) and 0 <= ei < len(ks):
        return ei
    return None


def calc_post_exit(tr: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    symbol = tr.get('symbol')
    if not symbol:
        return None
    ks = load_kline(symbol)
    if not ks:
        return None
    xidx = trade_exit_idx(tr, ks)
    eidx = close_at_entry(tr, ks)
    if xidx is None or eidx is None:
        return None
    entry = num(tr.get('entry_price'))
    exit_price = num(tr.get('exit_price'))
    sl = num(tr.get('sl') or tr.get('sl_price'))
    risk_abs = max(entry - sl, entry * num(tr.get('risk_pct')) / 100.0, entry * 0.0001)
    risk_pct = risk_abs / entry * 100.0
    after = ks[xidx + 1: xidx + 1 + max(WINDOWS)]
    if not after or entry <= 0 or exit_price <= 0:
        return None

    row: Dict[str, Any] = {
        'symbol': symbol,
        'entry_date': tr.get('entry_date'),
        'exit_date': tr.get('exit_date'),
        'exit_reason': tr.get('exit_reason'),
        'signal_type': tr.get('signal_type'),
        'market_state': tr.get('market_state'),
        'v85_path': tr.get('v85_path'),
        'entry_price': round(entry, 4),
        'exit_price': round(exit_price, 4),
        'sl': round(sl, 4),
        'risk_pct': round(risk_pct, 4),
        'pnl_pct': round(num(tr.get('pnl_pct')), 4),
        'hold_bars': tr.get('hold_bars'),
        'mfe_r_in_trade': round(num(tr.get('mfe_r')), 4),
        'mae_r_in_trade': round(num(tr.get('mae_r')), 4),
        'post_bars_available': len(after),
    }
    for w in WINDOWS:
        seg = after[:w]
        if not seg:
            continue
        hi_bar = max(seg, key=lambda b: b['high'])
        lo_bar = min(seg, key=lambda b: b['low'])
        end_bar = seg[-1]
        max_after = hi_bar['high']
        min_after = lo_bar['low']
        row[f'post{w}_max_pct_from_exit'] = round((max_after / exit_price - 1) * 100, 4)
        row[f'post{w}_min_pct_from_exit'] = round((min_after / exit_price - 1) * 100, 4)
        row[f'post{w}_close_pct_from_exit'] = round((end_bar['close'] / exit_price - 1) * 100, 4)
        row[f'post{w}_max_r_from_exit'] = round((max_after - exit_price) / risk_abs, 4)
        row[f'post{w}_min_r_from_exit'] = round((min_after - exit_price) / risk_abs, 4)
        row[f'post{w}_max_date'] = hi_bar['date']
        row[f'post{w}_min_date'] = lo_bar['date']
        row[f'post{w}_close_date'] = end_bar['date']
    # Diagnostic tags.
    row['sold_early_20d_gt_1r'] = row.get('post20_max_r_from_exit', 0) >= 1.0
    row['sold_early_20d_gt_2r'] = row.get('post20_max_r_from_exit', 0) >= 2.0
    row['sold_early_40d_gt_2r'] = row.get('post40_max_r_from_exit', 0) >= 2.0
    row['post_exit_drawdown_20d_gt_1r'] = row.get('post20_min_r_from_exit', 0) <= -1.0
    row['post_exit_drawdown_40d_gt_2r'] = row.get('post40_min_r_from_exit', 0) <= -2.0
    if row['exit_reason'] == 'SL_HIT':
        row['sl_shakeout_20d_rebound_gt_2r'] = row.get('post20_max_r_from_exit', 0) >= 2.0
        row['sl_protective_20d_fell_gt_1r'] = row.get('post20_min_r_from_exit', 0) <= -1.0
    else:
        row['sl_shakeout_20d_rebound_gt_2r'] = False
        row['sl_protective_20d_fell_gt_1r'] = False
    return row


def pct(part: int, total: int) -> float:
    return round(part / total * 100, 2) if total else 0.0


def summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    if not n:
        return {'n': 0}
    def avg(k: str) -> float:
        vals = [num(r.get(k)) for r in rows if r.get(k) is not None]
        return round(mean(vals), 4) if vals else 0.0
    def med(k: str) -> float:
        vals = [num(r.get(k)) for r in rows if r.get(k) is not None]
        return round(median(vals), 4) if vals else 0.0
    return {
        'n': n,
        'avg_pnl_pct': avg('pnl_pct'),
        'avg_mfe_r_in_trade': avg('mfe_r_in_trade'),
        'avg_post20_max_r_from_exit': avg('post20_max_r_from_exit'),
        'median_post20_max_r_from_exit': med('post20_max_r_from_exit'),
        'avg_post40_max_r_from_exit': avg('post40_max_r_from_exit'),
        'median_post40_max_r_from_exit': med('post40_max_r_from_exit'),
        'avg_post20_min_r_from_exit': avg('post20_min_r_from_exit'),
        'sold_early_20d_gt_1r': {'n': sum(r['sold_early_20d_gt_1r'] for r in rows), 'rate': pct(sum(r['sold_early_20d_gt_1r'] for r in rows), n)},
        'sold_early_20d_gt_2r': {'n': sum(r['sold_early_20d_gt_2r'] for r in rows), 'rate': pct(sum(r['sold_early_20d_gt_2r'] for r in rows), n)},
        'sold_early_40d_gt_2r': {'n': sum(r['sold_early_40d_gt_2r'] for r in rows), 'rate': pct(sum(r['sold_early_40d_gt_2r'] for r in rows), n)},
        'post_exit_drawdown_20d_gt_1r': {'n': sum(r['post_exit_drawdown_20d_gt_1r'] for r in rows), 'rate': pct(sum(r['post_exit_drawdown_20d_gt_1r'] for r in rows), n)},
        'post_exit_drawdown_40d_gt_2r': {'n': sum(r['post_exit_drawdown_40d_gt_2r'] for r in rows), 'rate': pct(sum(r['post_exit_drawdown_40d_gt_2r'] for r in rows), n)},
    }


def bucket(rows: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    out = {}
    for val in sorted(set(str(r.get(key)) for r in rows)):
        part = [r for r in rows if str(r.get(key)) == val]
        out[val] = summary(part)
    return out


def main() -> None:
    trades = json.loads(TRADES.read_text())
    rows = []
    missing = []
    for tr in trades:
        r = calc_post_exit(tr)
        if r is None:
            missing.append({'symbol': tr.get('symbol'), 'entry_date': tr.get('entry_date'), 'exit_date': tr.get('exit_date'), 'reason': 'missing_kline_or_index'})
        else:
            rows.append(r)

    sl_rows = [r for r in rows if r.get('exit_reason') == 'SL_HIT']
    time_rows = [r for r in rows if r.get('exit_reason') == 'TIME_STOP']
    tp_rows = [r for r in rows if 'TP' in str(r.get('exit_reason'))]

    report = {
        'engine': 'V94_POST_EXIT_TP_SL_AUTOPSY',
        'source': str(TRADES),
        'trade_count': len(trades),
        'analyzed_count': len(rows),
        'missing_count': len(missing),
        'windows_bars_after_exit': WINDOWS,
        'definition': {
            'sold_early_20d_gt_1r': 'after sell, next 20 daily bars make a high at least +1 original risk above exit price',
            'sold_early_20d_gt_2r': 'after sell, next 20 daily bars make a high at least +2 original risk above exit price',
            'sl_shakeout_20d_rebound_gt_2r': 'SL exit then rebounds at least +2R within 20 bars, indicating potentially too-tight stop or wrong invalidation point',
            'post_exit_drawdown': 'price continued down after exit; exit was protective rather than too early',
        },
        'overall': summary(rows),
        'by_exit_reason': bucket(rows, 'exit_reason'),
        'by_market_state': bucket(rows, 'market_state'),
        'sl_hit_autopsy': {
            **summary(sl_rows),
            'shakeout_rebound_20d_gt_2r': {'n': sum(r['sl_shakeout_20d_rebound_gt_2r'] for r in sl_rows), 'rate': pct(sum(r['sl_shakeout_20d_rebound_gt_2r'] for r in sl_rows), len(sl_rows))},
            'protective_fell_20d_gt_1r': {'n': sum(r['sl_protective_20d_fell_gt_1r'] for r in sl_rows), 'rate': pct(sum(r['sl_protective_20d_fell_gt_1r'] for r in sl_rows), len(sl_rows))},
        },
        'time_stop_autopsy': summary(time_rows),
        'tp_exit_autopsy': summary(tp_rows),
        'top_sold_early_20d': sorted(rows, key=lambda r: r.get('post20_max_r_from_exit', -999), reverse=True)[:50],
        'top_sl_shakeout_20d': sorted(sl_rows, key=lambda r: r.get('post20_max_r_from_exit', -999), reverse=True)[:50],
        'top_protective_exits_20d': sorted(rows, key=lambda r: r.get('post20_min_r_from_exit', 999))[:50],
        'missing': missing[:50],
    }

    (OUT_DIR / 'v94_post_exit_rows.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v94_post_exit_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({
        'out': str(OUT_DIR),
        'trade_count': len(trades),
        'analyzed_count': len(rows),
        'missing_count': len(missing),
        'overall': report['overall'],
        'sl_hit_autopsy': report['sl_hit_autopsy'],
        'time_stop_autopsy': report['time_stop_autopsy'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
