#!/usr/bin/env python3
"""V132 read-only FVG_Demand reclaim takeover / failed-reclaim shadow backtest.

Scope: V128 independent scanner-layer FVG_Demand rows only.
No production writes, no API/frontend/watchlist changes, no TP/SL tuning.

Assumptions / success criteria:
- Classifier uses only ex-ante candle fields from reclaim and the next 1-3 bars before a delayed shadow entry.
- RECOVERY is reported separately and excluded from canonical non-recovery takeover candidates.
- A-share T+1 is enforced by shifting same-day exits to the next bar.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

sys.path.insert(0, '/root/.hermes/scripts/v25')

import pandas as pd

from v81_contextual_smc_generator import next_exit_semantic
from v90_daily_full_market_scanner import date_key, num

ROOT = Path('/root/.hermes')
SRC = ROOT / 'smc_audit' / 'v128_parallel_scanner_candidate_audit_20260620' / 'v128_parallel_shadow_backtest_all.csv'
RECENT_SRC = ROOT / 'smc_audit' / 'v128_parallel_scanner_candidate_audit_20260620' / 'v128_parallel_shadow_recent45.csv'
KLINE_DIR = ROOT / 'kline_cache'
OUT = ROOT / 'smc_audit' / 'v132_fvg_reclaim_takeover_shadow_backtest_20260620'
OUT.mkdir(parents=True, exist_ok=True)


def kline_path(symbol: str) -> Path:
    return KLINE_DIR / f"{symbol.replace('.', '_')}_daily_750.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def fbar(b: Dict[str, Any], key: str) -> float:
    return num(b.get(key))


def pct(a: float, b: float) -> float:
    if not a or not b or pd.isna(a) or pd.isna(b):
        return float('nan')
    return (a / b - 1.0) * 100.0


def metrics(rows: Iterable[Dict[str, Any]], pnl_key: str = 'pnl_pct', exit_key: str = 'exit_reason') -> Dict[str, Any]:
    rs = list(rows)
    if not rs:
        return {'n': 0, 'wr': 0, 'avg': 0, 'loss_rate': 0, 'hard_exit_rate': 0, 'cum': 0}
    vals = [num(r.get(pnl_key)) for r in rs]
    hard = [r for r in rs if any(x in str(r.get(exit_key)) for x in ['SL', 'DAMAGE', 'ZONE_DEAD', 'STRUCTURE', 'BREAK'])]
    return {
        'n': len(rs),
        'wr': round(sum(v > 0 for v in vals) / len(vals) * 100, 2),
        'avg': round(sum(vals) / len(vals), 4),
        'loss_rate': round(sum(v <= 0 for v in vals) / len(vals) * 100, 2),
        'hard_exit_rate': round(len(hard) / len(rs) * 100, 2),
        'cum': round(sum(vals), 4),
    }


def bucket(rows: Iterable[Dict[str, Any]], keyfn: Callable[[Dict[str, Any]], str], pnl_key='pnl_pct', exit_key='exit_reason') -> Dict[str, Dict[str, Any]]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(keyfn(r))].append(r)
    return {k: metrics(v, pnl_key, exit_key) for k, v in sorted(g.items())}


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    fields = sorted({k for r in rows for k in r.keys()}) if rows else []
    with path.open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        if fields:
            w.writeheader()
            w.writerows(rows)


def calc_reclaim_features(row: Dict[str, Any], bars: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    ri = int(num(row.get('reclaim_idx'), -1))
    if ri < 0 or ri >= len(bars):
        return None
    zl = float(row.get('zone_low'))
    zh = float(row.get('zone_high'))
    if zl <= 0 or zh <= 0 or zh <= zl:
        return None

    rb = bars[ri]
    ro, rh, rl, rc = fbar(rb, 'o'), fbar(rb, 'h'), fbar(rb, 'l'), fbar(rb, 'c')
    rrng = max(rh - rl, 1e-9)
    out: Dict[str, Any] = {
        'v132_reclaim_body_range_pct': round(abs(rc - ro) / rrng * 100.0, 4),
        'v132_reclaim_bull_body_pct': round(max(0.0, rc - ro) / rrng * 100.0, 4),
        'v132_reclaim_close_pos_pct': round((rc - rl) / rrng * 100.0, 4),
        'v132_reclaim_low_below_zone_high_pct': round(pct(rl, zh), 4),
        'v132_reclaim_close_above_zone_high_pct': round(pct(rc, zh), 4),
    }

    for n in [1, 2, 3]:
        seq = bars[ri + 1:min(len(bars), ri + 1 + n)]
        if len(seq) < n:
            out.update({
                f'v132_hold_close_above_zone_high_{n}': False,
                f'v132_no_break_reclaim_low_{n}': False,
                f'v132_bull_count_{n}': -1,
                f'v132_post_min_low_pullback_pct_{n}': float('nan'),
                f'v132_post_zone_pullback_depth_pct_{n}': float('nan'),
                f'v132_entry_after_confirm_idx_{n}': -1,
            })
            continue
        closes = [fbar(b, 'c') for b in seq]
        lows = [fbar(b, 'l') for b in seq]
        bull_count = sum(fbar(b, 'c') > fbar(b, 'o') for b in seq)
        min_low = min(lows)
        depth = max(0.0, (zh - min_low) / (zh - zl) * 100.0)
        out.update({
            f'v132_hold_close_above_zone_high_{n}': all(c >= zh for c in closes),
            f'v132_no_break_reclaim_low_{n}': min_low >= rl,
            f'v132_bull_count_{n}': int(bull_count),
            f'v132_post_min_low_pullback_pct_{n}': round(pct(min_low, zh), 4),
            f'v132_post_zone_pullback_depth_pct_{n}': round(depth, 4),
            f'v132_post_close1_above_zone_high_{n}': closes[0] >= zh,
            f'v132_entry_after_confirm_idx_{n}': ri + n + 1,
        })
    return out


def true_takeover(row: Dict[str, Any], n: int, strict: bool = False) -> bool:
    if row.get('market_state') == 'RECOVERY':
        return False
    if num(row.get('entry_chase_above_zone_pct')) > 5:
        return False
    body = num(row.get('v132_reclaim_bull_body_pct'))
    depth = num(row.get(f'v132_post_zone_pullback_depth_pct_{n}'), 999)
    bull_count = int(num(row.get(f'v132_bull_count_{n}'), -1))
    hold = bool(row.get(f'v132_hold_close_above_zone_high_{n}'))
    no_break = bool(row.get(f'v132_no_break_reclaim_low_{n}'))
    if strict:
        return hold and no_break and body >= 35 and depth <= 25 and bull_count >= max(1, n - 1)
    return hold and no_break and body >= 25 and depth <= 40 and bull_count >= 1


def failed_reclaim(row: Dict[str, Any], n: int) -> bool:
    depth = num(row.get(f'v132_post_zone_pullback_depth_pct_{n}'), 999)
    hold = bool(row.get(f'v132_hold_close_above_zone_high_{n}'))
    no_break = bool(row.get(f'v132_no_break_reclaim_low_{n}'))
    return (not hold) or (not no_break) or depth > 100


def classify(row: Dict[str, Any]) -> str:
    if row.get('market_state') == 'RECOVERY':
        return 'RECOVERY_SEPARATE'
    if true_takeover(row, 3, strict=True):
        return 'TRUE_TAKEOVER_3_STRICT'
    if true_takeover(row, 2, strict=False):
        return 'TRUE_TAKEOVER_2'
    if true_takeover(row, 1, strict=False):
        return 'TRUE_TAKEOVER_1'
    if failed_reclaim(row, 1):
        return 'FAILED_RECLAIM_1'
    if failed_reclaim(row, 3):
        return 'FAILED_RECLAIM_3'
    return 'UNCLEAR_RECLAIM'


def simulate_delayed_entry(row: Dict[str, Any], bars: List[Dict[str, Any]], n: int, label: str) -> Optional[Dict[str, Any]]:
    entry_idx = int(num(row.get(f'v132_entry_after_confirm_idx_{n}'), -1))
    if entry_idx <= 0 or entry_idx >= len(bars):
        return None
    entry_price = fbar(bars[entry_idx], 'o')
    if entry_price <= 0:
        return None
    horizon = bars[entry_idx:min(len(bars), entry_idx + 21)]
    if len(horizon) <= 1:
        return None
    poi = {
        'zone_low': row.get('zone_low'),
        'zone_high': row.get('zone_high'),
        'prior_structure_low': row.get('zone_low'),
        'liquidity_target': '',
    }
    ex = next_exit_semantic(horizon, poi, 1)
    if ex.get('exit_idx') is None:
        local = len(horizon) - 1
        exit_idx = entry_idx + local
        exit_date = date_key(horizon[local].get('t') or horizon[local].get('date'))
        exit_price = fbar(horizon[local], 'c')
        exit_reason = 'TIME_STOP_NO_SEMANTIC_EXIT'
    else:
        exit_idx = entry_idx + int(ex.get('exit_idx'))
        exit_date = date_key(ex.get('exit_date'))
        exit_price = num(ex.get('exit_price'))
        exit_reason = str(ex.get('exit_signal'))
    if date_key(exit_date) == date_key(bars[entry_idx].get('t') or bars[entry_idx].get('date')) and exit_idx + 1 < len(bars):
        exit_idx += 1
        exit_date = date_key(bars[exit_idx].get('t') or bars[exit_idx].get('date'))
        exit_price = fbar(bars[exit_idx], 'c')
        exit_reason = f'{exit_reason}_T1_SHIFTED'
    out = dict(row)
    out.update({
        'v132_delayed_model': label,
        'v132_delayed_entry_idx': entry_idx,
        'v132_delayed_entry_date': date_key(bars[entry_idx].get('t') or bars[entry_idx].get('date')),
        'v132_delayed_entry_price': round(entry_price, 6),
        'v132_delayed_entry_above_zone_high_pct': round(pct(entry_price, float(row.get('zone_high'))), 4),
        'v132_delayed_exit_idx': exit_idx,
        'v132_delayed_exit_date': date_key(exit_date),
        'v132_delayed_exit_price': round(exit_price, 6),
        'v132_delayed_exit_reason': exit_reason,
        'v132_delayed_pnl_pct': round((exit_price / entry_price - 1.0) * 100.0, 4),
        'v132_delayed_hold_bars': max(0, exit_idx - entry_idx),
    })
    return out


def main() -> None:
    df = pd.read_csv(SRC)
    recent_df = pd.read_csv(RECENT_SRC)
    recent_keys = set(zip(recent_df['symbol'].astype(str), recent_df['entry_date'].astype(int), recent_df['poi_source'].astype(str)))
    fvg = df[(df['poi_source'] == 'FVG_Demand') & (df['valid_backtest'] == True)].copy()

    bar_cache: Dict[str, List[Dict[str, Any]]] = {}
    rows: List[Dict[str, Any]] = []
    delayed_rows: List[Dict[str, Any]] = []
    missing_kline = 0

    for r in fvg.to_dict('records'):
        sym = str(r.get('symbol'))
        if sym not in bar_cache:
            path = kline_path(sym)
            bar_cache[sym] = load_json(path) if path.exists() else []
        bars = bar_cache[sym]
        if not bars:
            missing_kline += 1
            continue
        feats = calc_reclaim_features(r, bars)
        if not feats:
            continue
        rr = dict(r)
        rr.update(feats)
        rr['is_recent45'] = (str(rr.get('symbol')), int(rr.get('entry_date')), str(rr.get('poi_source'))) in recent_keys
        rr['v132_reclaim_class'] = classify(rr)
        rr['v132_true_takeover_1'] = true_takeover(rr, 1)
        rr['v132_true_takeover_2'] = true_takeover(rr, 2)
        rr['v132_true_takeover_3_strict'] = true_takeover(rr, 3, strict=True)
        rr['v132_failed_reclaim_1'] = failed_reclaim(rr, 1)
        rr['v132_failed_reclaim_3'] = failed_reclaim(rr, 3)
        rows.append(rr)

        for n, flag, label in [
            (1, rr['v132_true_takeover_1'], 'DELAY_CONFIRM_1_TRUE_TAKEOVER'),
            (2, rr['v132_true_takeover_2'], 'DELAY_CONFIRM_2_TRUE_TAKEOVER'),
            (3, rr['v132_true_takeover_3_strict'], 'DELAY_CONFIRM_3_STRICT_TAKEOVER'),
        ]:
            if flag:
                sim = simulate_delayed_entry(rr, bars, n, label)
                if sim:
                    delayed_rows.append(sim)

    recent = [r for r in rows if r.get('is_recent45')]
    non_recovery = [r for r in rows if r.get('market_state') != 'RECOVERY']
    recovery = [r for r in rows if r.get('market_state') == 'RECOVERY']
    bm = [r for r in rows if r.get('market_state') in ['BEAR_RISK', 'MIXED']]

    candidate_slices = {
        'true_takeover_1_non_recovery': [r for r in rows if r.get('v132_true_takeover_1')],
        'true_takeover_2_non_recovery': [r for r in rows if r.get('v132_true_takeover_2')],
        'true_takeover_3_strict_non_recovery': [r for r in rows if r.get('v132_true_takeover_3_strict')],
        'failed_reclaim_1': [r for r in rows if r.get('v132_failed_reclaim_1') and r.get('market_state') != 'RECOVERY'],
        'failed_reclaim_3': [r for r in rows if r.get('v132_failed_reclaim_3') and r.get('market_state') != 'RECOVERY'],
        'bear_mixed_true_takeover_2': [r for r in bm if r.get('v132_true_takeover_2')],
        'bear_mixed_failed_reclaim_1': [r for r in bm if r.get('v132_failed_reclaim_1')],
        'recovery_separate': recovery,
    }

    summary = {
        'decision': 'V132_FVG_RECLAIM_TAKEOVER_SHADOW_BACKTEST_DONE_NO_PRODUCTION_CHANGE',
        'run_at': datetime.now().isoformat(timespec='seconds'),
        'source': str(SRC),
        'recent_source': str(RECENT_SRC),
        'missing_kline': missing_kline,
        'baseline': metrics(rows),
        'baseline_recent45': metrics(recent),
        'non_recovery': metrics(non_recovery),
        'recovery_separate': metrics(recovery),
        'by_market_state': bucket(rows, lambda r: r.get('market_state')),
        'by_reclaim_class': bucket(rows, lambda r: r.get('v132_reclaim_class')),
        'by_reclaim_class_recent45': bucket(recent, lambda r: r.get('v132_reclaim_class')),
        'candidate_slices': {k: metrics(v) for k, v in candidate_slices.items()},
        'candidate_slices_recent45': {k: metrics([r for r in v if r.get('is_recent45')]) for k, v in candidate_slices.items()},
        'delayed_entry_by_model': bucket(delayed_rows, lambda r: r.get('v132_delayed_model'), 'v132_delayed_pnl_pct', 'v132_delayed_exit_reason'),
        'delayed_entry_recent45_by_model': bucket([r for r in delayed_rows if r.get('is_recent45')], lambda r: r.get('v132_delayed_model'), 'v132_delayed_pnl_pct', 'v132_delayed_exit_reason'),
        'no_production_change': True,
    }

    write_csv(OUT / 'v132_reclaim_takeover_features.csv', rows)
    write_csv(OUT / 'v132_true_takeover_candidates.csv', [r for r in rows if str(r.get('v132_reclaim_class')).startswith('TRUE_TAKEOVER')])
    write_csv(OUT / 'v132_failed_reclaim_rows.csv', [r for r in rows if str(r.get('v132_reclaim_class')).startswith('FAILED_RECLAIM')])
    write_csv(OUT / 'v132_delayed_entry_shadow_backtest.csv', delayed_rows)
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = [
        '# V132 FVG_Demand Reclaim Takeover Shadow Backtest',
        '',
        'Decision: `V132_FVG_RECLAIM_TAKEOVER_SHADOW_BACKTEST_DONE_NO_PRODUCTION_CHANGE`。只做 shadow/backtest，不接生产。',
        '',
        '## 1. Baseline / Recovery split',
        '|slice|n|WR|Avg|Loss|HardExit|Cum|',
        '|---|---:|---:|---:|---:|---:|---:|',
    ]
    for name in ['baseline', 'baseline_recent45', 'non_recovery', 'recovery_separate']:
        m = summary[name]
        lines.append(f"|{name}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss_rate']}|{m['hard_exit_rate']}|{m['cum']}|")
    lines += ['', '## 2. Reclaim class by current baseline outcome', '|class|n|WR|Avg|Loss|HardExit|Cum|', '|---|---:|---:|---:|---:|---:|---:|']
    for name, m in summary['by_reclaim_class'].items():
        lines.append(f"|{name}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss_rate']}|{m['hard_exit_rate']}|{m['cum']}|")
    lines += ['', '## 3. Candidate slices', '|slice|n|WR|Avg|Loss|HardExit|recent_n|recent_WR|', '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name, m in summary['candidate_slices'].items():
        rm = summary['candidate_slices_recent45'].get(name, {'n': 0, 'wr': 0})
        lines.append(f"|{name}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss_rate']}|{m['hard_exit_rate']}|{rm['n']}|{rm['wr']}|")
    lines += ['', '## 4. Delayed entry after takeover confirmation', '|model|n|WR|Avg|Loss|HardExit|Cum|recent_n|recent_WR|', '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for name, m in summary['delayed_entry_by_model'].items():
        rm = summary['delayed_entry_recent45_by_model'].get(name, {'n': 0, 'wr': 0})
        lines.append(f"|{name}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss_rate']}|{m['hard_exit_rate']}|{m['cum']}|{rm['n']}|{rm['wr']}|")
    lines += ['', '## 5. Conclusion', 'V132 tests the correct next hypothesis: after reclaim, identify true takeover impulse vs failed reclaim. RECOVERY is isolated. The result remains shadow-only unless full-market and recent slices both show production-grade quality.']
    (OUT / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    print(json.dumps({
        'out': str(OUT),
        'decision': summary['decision'],
        'baseline': summary['baseline'],
        'recovery_separate': summary['recovery_separate'],
        'by_reclaim_class': summary['by_reclaim_class'],
        'delayed_entry_by_model': summary['delayed_entry_by_model'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
