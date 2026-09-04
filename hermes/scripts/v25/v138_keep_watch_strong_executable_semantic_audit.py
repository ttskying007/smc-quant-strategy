#!/usr/bin/env python3
"""V138 KEEP_WATCH_STRONG executable entry/exit semantic audit.

Research-only. Reads V134/V137 artifacts and kline cache; writes audit files only.
No production scanner/API/frontend/watchlist changes.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path('/root/.hermes')
V134 = ROOT / 'smc_audit' / 'v134_candidate_timing_lifecycle_shadow_audit_20260620' / 'v134_lifecycle_features.csv'
OUT = ROOT / 'smc_audit' / 'v138_keep_watch_strong_executable_semantic_audit_20260620'
KLINE_DIR = ROOT / 'kline_cache'
OUT.mkdir(parents=True, exist_ok=True)


def num(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, float) and math.isnan(x):
            return default
        return float(x)
    except Exception:
        return default


def date_key(x: Any) -> int:
    s = str(x or '').replace('-', '')[:8]
    try:
        return int(s)
    except Exception:
        return 0


def pct(a: float, b: float) -> float:
    if a <= 0 or b <= 0:
        return 0.0
    return (a / b - 1.0) * 100.0


def fbar(b: Dict[str, Any], k: str) -> float:
    return num(b.get(k))


def load_rows(path: Path) -> List[Dict[str, Any]]:
    with path.open(newline='', encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    fields = sorted({k for r in rows for k in r.keys()}) if rows else []
    with path.open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        if fields:
            w.writeheader()
            w.writerows(rows)


def kline_path(symbol: str) -> Path:
    return KLINE_DIR / f"{symbol.replace('.', '_')}_daily_750.json"


def metrics(rows: Iterable[Dict[str, Any]], pnl_key: str = 'v138_pnl_pct') -> Dict[str, Any]:
    rs = list(rows)
    if not rs:
        return {'n': 0, 'wr': 0, 'avg_pnl': 0, 'median_pnl': 0, 'loss_rate': 0, 'avg_mfe': 0, 'avg_mae': 0}
    vals = sorted(num(r.get(pnl_key)) for r in rs)
    mfes = [num(r.get('v138_mfe_pct')) for r in rs]
    maes = [num(r.get('v138_mae_pct')) for r in rs]
    return {
        'n': len(rs),
        'wr': round(sum(v > 0 for v in vals) / len(vals) * 100, 2),
        'avg_pnl': round(sum(vals) / len(vals), 4),
        'median_pnl': round(vals[len(vals) // 2], 4),
        'loss_rate': round(sum(v <= 0 for v in vals) / len(vals) * 100, 2),
        'avg_mfe': round(sum(mfes) / len(mfes), 4),
        'avg_mae': round(sum(maes) / len(maes), 4),
    }


def bucket(rows: Iterable[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(r.get(key, ''))].append(r)
    return {k: metrics(v) for k, v in sorted(g.items())}


def is_bool_true(v: Any) -> bool:
    return str(v).lower() == 'true'


def is_strong_shadow(r: Dict[str, Any]) -> bool:
    return (
        str(r.get('v134_lifecycle_status')) == 'KEEP_WATCH_TAKEOVER_QUALITY_KNOWN_NO_BUY'
        and is_bool_true(r.get('v134_watch_strict_t0'))
        and is_bool_true(r.get('v132_true_takeover_2'))
        and is_bool_true(r.get('v133_entry_chase_le_5'))
        and is_bool_true(r.get('v133_risk_le_8'))
        and is_bool_true(r.get('v133_reclaim_close_above_zone_le_8'))
    )


def tp_levels(row: Dict[str, Any], bars: List[Dict[str, Any]], entry_idx: int) -> Dict[str, Any]:
    zh = num(row.get('zone_high'))
    zl = num(row.get('zone_low'))
    risk_low = min(zl, min(fbar(b, 'l') for b in bars[max(0, entry_idx - 10):entry_idx] or [{'l': zl}]))
    pre = bars[max(0, entry_idx - 60):entry_idx]
    prev_high_20 = max((fbar(b, 'h') for b in pre[-20:]), default=0.0)
    prev_high_60 = max((fbar(b, 'h') for b in pre), default=0.0)
    rr1_price = 0.0
    return {'zone_low': zl, 'zone_high': zh, 'risk_low': risk_low, 'prev_high_20': prev_high_20, 'prev_high_60': prev_high_60, 'rr1_price': rr1_price}


def simulate(row: Dict[str, Any], bars: List[Dict[str, Any]], mode: str) -> Optional[Dict[str, Any]]:
    # Modes are ex-ante and use only reclaim/takeover-confirmed bars.
    ri = int(num(row.get('reclaim_idx'), -1))
    if ri < 0 or ri >= len(bars) - 2:
        return None
    if mode == 'T2_NEXT_OPEN':
        entry_idx = int(num(row.get('v132_entry_after_confirm_idx_2'), -1))
        entry_kind = 'after_true_takeover_2_next_open'
    elif mode == 'T3_NEXT_OPEN':
        if not is_bool_true(row.get('v132_true_takeover_3_strict')):
            return None
        entry_idx = int(num(row.get('v132_entry_after_confirm_idx_3'), -1))
        entry_kind = 'after_true_takeover_3_strict_next_open'
    elif mode == 'RECLAIM_NEXT_OPEN':
        entry_idx = ri + 1
        entry_kind = 'after_reclaim_next_open'
    else:
        return None
    if entry_idx <= 0 or entry_idx >= len(bars):
        return None

    entry_date = date_key(bars[entry_idx].get('t') or bars[entry_idx].get('date'))
    event_date = date_key(row.get('event_date'))
    if entry_date <= event_date:
        return None

    entry = fbar(bars[entry_idx], 'o')
    if entry <= 0:
        return None

    zl = num(row.get('zone_low'))
    zh = num(row.get('zone_high'))
    levels = tp_levels(row, bars, entry_idx)
    sl = min(zl * 0.985, levels['risk_low'] * 0.995)
    risk_pct = max(0.01, pct(entry, sl))
    rr1 = entry + (entry - sl)
    targets = [x for x in [levels['prev_high_20'], levels['prev_high_60'], rr1] if x > entry * 1.005]
    tp = min(targets) if targets else entry * 1.08
    tp_type = 'STRUCTURE_OR_1R' if targets else 'FALLBACK_8PCT'

    horizon_end = min(len(bars), entry_idx + 22)
    horizon = bars[entry_idx:horizon_end]
    mfe = max((pct(fbar(b, 'h'), entry) for b in horizon), default=0.0)
    mae = min((pct(fbar(b, 'l'), entry) for b in horizon), default=0.0)

    exit_idx = horizon_end - 1
    exit_price = fbar(bars[exit_idx], 'c')
    exit_reason = 'TIME_STOP_21BARS'
    for j in range(entry_idx + 1, horizon_end):  # strict T+1: no same-day exit bar
        b = bars[j]
        lo, hi, close = fbar(b, 'l'), fbar(b, 'h'), fbar(b, 'c')
        if lo <= sl:
            exit_idx, exit_price, exit_reason = j, sl, 'STRUCTURE_SL_T1'
            break
        if hi >= tp:
            exit_idx, exit_price, exit_reason = j, tp, f'{tp_type}_TP_T1'
            break
        if close < zl:
            exit_idx, exit_price, exit_reason = j, close, 'ZONE_CLOSE_DEAD_T1'
            break

    exit_date = date_key(bars[exit_idx].get('t') or bars[exit_idx].get('date'))
    out = dict(row)
    out.update({
        'v138_mode': mode,
        'v138_entry_kind': entry_kind,
        'v138_entry_idx': entry_idx,
        'v138_entry_date': entry_date,
        'v138_entry_price': round(entry, 6),
        'v138_entry_above_zone_high_pct': round(pct(entry, zh), 4),
        'v138_entry_above_reclaim_close_pct': round(pct(entry, num(row.get('reclaim_close'))), 4),
        'v138_sl': round(sl, 6),
        'v138_tp': round(tp, 6),
        'v138_tp_type': tp_type,
        'v138_risk_pct': round(risk_pct, 4),
        'v138_exit_idx': exit_idx,
        'v138_exit_date': exit_date,
        'v138_exit_price': round(exit_price, 6),
        'v138_exit_reason': exit_reason,
        'v138_hold_bars': max(0, exit_idx - entry_idx),
        'v138_pnl_pct': round(pct(exit_price, entry), 4),
        'v138_mfe_pct': round(mfe, 4),
        'v138_mae_pct': round(mae, 4),
        'v138_t1_violation': exit_date == entry_date,
        'v138_chase_gt_5': pct(entry, zh) > 5,
        'v138_mixed': str(row.get('market_state')) == 'MIXED',
    })
    return out


def main() -> None:
    rows = load_rows(V134)
    strong = [r for r in rows if is_strong_shadow(r)]
    bars_cache: Dict[str, List[Dict[str, Any]]] = {}
    sims: List[Dict[str, Any]] = []
    missing = 0
    for r in strong:
        sym = str(r.get('symbol'))
        if sym not in bars_cache:
            p = kline_path(sym)
            bars_cache[sym] = json.loads(p.read_text(encoding='utf-8')) if p.exists() else []
        bars = bars_cache[sym]
        if not bars:
            missing += 1
            continue
        for mode in ['RECLAIM_NEXT_OPEN', 'T2_NEXT_OPEN', 'T3_NEXT_OPEN']:
            sim = simulate(r, bars, mode)
            if sim:
                sims.append(sim)

    recent = [r for r in sims if is_bool_true(r.get('is_recent45'))]
    no_mixed = [r for r in sims if not r.get('v138_mixed')]
    no_chase = [r for r in sims if not r.get('v138_chase_gt_5')]
    no_mixed_no_chase = [r for r in sims if (not r.get('v138_mixed')) and (not r.get('v138_chase_gt_5'))]

    summary = {
        'decision': 'V138_KEEP_WATCH_STRONG_EXECUTABLE_SEMANTIC_AUDIT_DONE_NO_PRODUCTION_CHANGE',
        'run_at': datetime.now().isoformat(timespec='seconds'),
        'input': str(V134),
        'out': str(OUT),
        'strong_shadow_rows': len(strong),
        'missing_kline': missing,
        'sim_rows': len(sims),
        'by_mode': bucket(sims, 'v138_mode'),
        'recent_by_mode': bucket(recent, 'v138_mode'),
        'no_mixed_by_mode': bucket(no_mixed, 'v138_mode'),
        'no_chase_by_mode': bucket(no_chase, 'v138_mode'),
        'no_mixed_no_chase_by_mode': bucket(no_mixed_no_chase, 'v138_mode'),
        'by_exit_reason': bucket(sims, 'v138_exit_reason'),
        'by_market_state': bucket(sims, 'market_state'),
        't1_violation_count': sum(1 for r in sims if r.get('v138_t1_violation')),
        'chase_gt_5_count': sum(1 for r in sims if r.get('v138_chase_gt_5')),
        'mixed_count': sum(1 for r in sims if r.get('v138_mixed')),
        'production_write': False,
        'buy_enabled': False,
    }

    write_csv(OUT / 'v138_executable_entry_exit_shadow_backtest.csv', sims)
    write_csv(OUT / 'v138_no_mixed_no_chase_rows.csv', no_mixed_no_chase)
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = [
        '# V138 KEEP_WATCH_STRONG Executable Semantic Audit',
        '',
        'Decision: `V138_KEEP_WATCH_STRONG_EXECUTABLE_SEMANTIC_AUDIT_DONE_NO_PRODUCTION_CHANGE`。只做可执行 entry/exit 语义审计，不接生产。',
        '',
        f"Strong shadow rows: {len(strong)}; simulated rows: {len(sims)}; T+1 violations: {summary['t1_violation_count']}.",
        '',
        '## By entry mode',
        '|mode|n|WR|AvgPnL|Median|Loss|AvgMFE|AvgMAE|',
        '|---|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for mode, m in summary['by_mode'].items():
        lines.append(f"|{mode}|{m['n']}|{m['wr']}|{m['avg_pnl']}|{m['median_pnl']}|{m['loss_rate']}|{m['avg_mfe']}|{m['avg_mae']}|")
    lines += ['', '## No MIXED + no chase>5 by mode', '|mode|n|WR|AvgPnL|Median|Loss|AvgMFE|AvgMAE|', '|---|---:|---:|---:|---:|---:|---:|---:|']
    for mode, m in summary['no_mixed_no_chase_by_mode'].items():
        lines.append(f"|{mode}|{m['n']}|{m['wr']}|{m['avg_pnl']}|{m['median_pnl']}|{m['loss_rate']}|{m['avg_mfe']}|{m['avg_mae']}|")
    lines += ['', '## Exit reason', '|reason|n|WR|AvgPnL|Loss|AvgMFE|AvgMAE|', '|---|---:|---:|---:|---:|---:|---:|']
    for reason, m in summary['by_exit_reason'].items():
        lines.append(f"|{reason}|{m['n']}|{m['wr']}|{m['avg_pnl']}|{m['loss_rate']}|{m['avg_mfe']}|{m['avg_mae']}|")
    (OUT / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    print(json.dumps({
        'out': str(OUT),
        'decision': summary['decision'],
        'strong_shadow_rows': len(strong),
        'sim_rows': len(sims),
        'by_mode': summary['by_mode'],
        'no_mixed_no_chase_by_mode': summary['no_mixed_no_chase_by_mode'],
        't1_violation_count': summary['t1_violation_count'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
