#!/usr/bin/env python3
"""V66 multi-retrace rank audit.

Computes retrace_rank for each V66 trade within its zone and reports rank-level
WR/avg pnl/SL rate. This answers first/second/Nth retrace quality explicitly.
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path('/root/.hermes')
TRADES = ROOT / 'smc_opt_v66' / 'v66_trades.json'
OUT_JSON = ROOT / 'smc_audit' / 'v66_multi_retrace_rank_audit.json'
OUT_MD = ROOT / 'smc_audit' / 'v66_multi_retrace_rank_audit.md'
KLINE_DIR = ROOT / 'kline_cache'


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def i(x: Any, default: int = -1) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def kpath(symbol: str) -> Path:
    stem = symbol.replace('.', '_')
    p = KLINE_DIR / f'{stem}_daily_750.json'
    return p if p.exists() else KLINE_DIR / f'{stem}_daily_300.json'


def touched_zone(bar: Dict[str, Any], low: float, high: float) -> bool:
    if low <= 0 or high <= 0:
        return False
    return f(bar.get('l')) <= high and f(bar.get('h')) >= low


def date_of(klines: List[Dict[str, Any]], idx: int) -> str:
    if 0 <= idx < len(klines):
        return str(klines[idx].get('t') or klines[idx].get('date') or '')[:8]
    return ''


def rank_trade(t: Dict[str, Any]) -> Dict[str, Any]:
    symbol = str(t.get('symbol') or '')
    klines = load(kpath(symbol), [])
    zi, ri, ci, ei = [i(t.get(k)) for k in ('zone_idx', 'retrace_index', 'conf_index', 'entry_index')]
    low = f(t.get('raw_zone_low') or t.get('zone_low') or t.get('dz_low'))
    high = f(t.get('raw_zone_high') or t.get('zone_high') or t.get('dz_high'))
    if not klines:
        return {'symbol': symbol, 'entry_date': t.get('entry_date'), 'fatal': 'MISSING_KLINE'}
    if (low <= 0 or high <= 0) and 0 <= zi < len(klines):
        low = f(klines[zi].get('l'))
        high = f(klines[zi].get('h'))
    retraces = []
    in_touch = False
    for idx in range(max(0, zi + 1), min(max(ei, ri, ci) + 1, len(klines))):
        touch = touched_zone(klines[idx], low, high)
        if touch and not in_touch:
            retraces.append({'idx': idx, 'date': date_of(klines, idx), 'low': f(klines[idx].get('l')), 'high': f(klines[idx].get('h'))})
        in_touch = touch
    rank = None
    anchor = ri if ri >= 0 else ci
    for n, r in enumerate(retraces, 1):
        if r['idx'] <= anchor:
            rank = n
    if rank is None and retraces:
        rank = len(retraces)
    elif rank is None:
        rank = 0
    invalid_before_entry = False
    for idx in range(max(0, zi + 1), min(ei, len(klines))):
        if low > 0 and f(klines[idx].get('c')) < low:
            invalid_before_entry = True
            break
    return {
        'symbol': symbol,
        'entry_date': t.get('entry_date'),
        'zone_type': t.get('zone_type'),
        'conf_type': t.get('conf_type'),
        'family': t.get('v59_setup_family'),
        'pnl_pct': f(t.get('pnl_pct')),
        'realized_r': f(t.get('realized_r')),
        'exit_reason': t.get('exit_reason'),
        'won': f(t.get('pnl_pct')) > 0,
        'idx': {'zone': zi, 'retrace': ri, 'confirm': ci, 'entry': ei},
        'zone': {'low': low, 'high': high},
        'retrace_rank': rank,
        'retrace_count_before_entry': len(retraces),
        'invalidated_before_entry': invalid_before_entry,
        'retraces': retraces[:10],
    }


def bucket(rows: List[Dict[str, Any]], key_fn):
    groups = defaultdict(list)
    for r in rows:
        groups[key_fn(r)].append(r)
    out = {}
    for k, vals in groups.items():
        n = len(vals)
        wins = sum(1 for r in vals if r.get('won'))
        sl = sum(1 for r in vals if 'SL' in str(r.get('exit_reason')))
        invalid = sum(1 for r in vals if r.get('invalidated_before_entry'))
        out[str(k)] = {
            'n': n,
            'wr_pct': round(wins / n * 100, 2) if n else 0,
            'avg_pnl': round(sum(f(r.get('pnl_pct')) for r in vals) / n, 3) if n else 0,
            'avg_r': round(sum(f(r.get('realized_r')) for r in vals) / n, 3) if n else 0,
            'sl_rate_pct': round(sl / n * 100, 2) if n else 0,
            'invalidated_before_entry_pct': round(invalid / n * 100, 2) if n else 0,
        }
    return dict(sorted(out.items(), key=lambda kv: (int(kv[0]) if kv[0].isdigit() else 999, kv[0])))


def main() -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    trades = load(TRADES, [])
    rows = [rank_trade(t) for t in trades]
    valid = [r for r in rows if not r.get('fatal')]
    fatal = [r for r in rows if r.get('fatal')]
    rank_summary = bucket(valid, lambda r: r.get('retrace_rank'))
    rank_zone_summary = bucket(valid, lambda r: f"{r.get('zone_type')}|rank{r.get('retrace_rank')}")
    summary = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'n_trades': len(rows),
        'fatal_count': len(fatal),
        'rank_summary': rank_summary,
        'rank_zone_summary': rank_zone_summary,
        'rank_counts': dict(Counter(r.get('retrace_rank') for r in valid)),
        'pass': len(fatal) == 0,
    }
    OUT_JSON.write_text(json.dumps({'summary': summary, 'rows': rows}, ensure_ascii=False, indent=2))
    md = ['# V66 Multi-Retrace Rank Audit\n\n', '```json\n', json.dumps(summary, ensure_ascii=False, indent=2), '\n```\n\n']
    OUT_MD.write_text(''.join(md))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
