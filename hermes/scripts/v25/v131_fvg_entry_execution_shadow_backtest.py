#!/usr/bin/env python3
"""V131 read-only FVG_Demand entry-execution shadow backtest.

Scope: V128 independent scanner-layer FVG_Demand rows only.
No production writes, no API/frontend/watchlist changes, no TP/SL tuning.

Tests requested:
- candidate downgrade/reject simulation for entry_chase_above_zone_pct > 3/5/8
- split RECOVERY as false-recovery risk bucket
- BEAR_RISK/MIXED only with real candle reaction
- compare current reclaim+next-open entry with zone limit / second pullback / reclaim distance / entry buffer mechanics
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter, defaultdict
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
OUT = ROOT / 'smc_audit' / 'v131_fvg_entry_execution_shadow_backtest_20260620'
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


def simulate_exit(row: Dict[str, Any], bars: List[Dict[str, Any]], entry_idx: int, entry_price: float, reason_prefix: str) -> Optional[Dict[str, Any]]:
    if entry_idx < 0 or entry_idx >= len(bars) or entry_price <= 0:
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
        b = horizon[local]
        exit_idx = entry_idx + local
        exit_date = date_key(b.get('t') or b.get('date'))
        exit_price = fbar(b, 'c')
        exit_reason = 'TIME_STOP_NO_SEMANTIC_EXIT'
    else:
        exit_idx = entry_idx + int(ex.get('exit_idx'))
        exit_date = date_key(ex.get('exit_date'))
        exit_price = num(ex.get('exit_price'))
        exit_reason = str(ex.get('exit_signal'))
    if date_key(exit_date) == date_key(bars[entry_idx].get('t') or bars[entry_idx].get('date')) and exit_idx + 1 < len(bars):
        exit_idx += 1
        b = bars[exit_idx]
        exit_date = date_key(b.get('t') or b.get('date'))
        exit_price = fbar(b, 'c')
        exit_reason = f'{exit_reason}_T1_SHIFTED'
    out = dict(row)
    out.update({
        'v131_entry_model': reason_prefix,
        'v131_entry_idx': int(entry_idx),
        'v131_entry_date': date_key(bars[entry_idx].get('t') or bars[entry_idx].get('date')),
        'v131_entry_price': round(float(entry_price), 6),
        'v131_entry_above_zone_high_pct': round(pct(float(entry_price), float(row.get('zone_high'))), 4),
        'v131_exit_idx': int(exit_idx),
        'v131_exit_date': date_key(exit_date),
        'v131_exit_price': round(float(exit_price), 6),
        'v131_exit_reason': exit_reason,
        'v131_pnl_pct': round((float(exit_price) / float(entry_price) - 1.0) * 100.0, 4),
        'v131_hold_bars': int(max(0, exit_idx - entry_idx)),
        'v131_valid': True,
    })
    return out


def find_limit_entry(row: Dict[str, Any], bars: List[Dict[str, Any]], limit_price: float, wait: int, label: str) -> Optional[Dict[str, Any]]:
    reclaim_idx = int(num(row.get('reclaim_idx'), -1))
    start = reclaim_idx + 1
    end = min(len(bars), reclaim_idx + wait + 1)
    for i in range(start, end):
        if fbar(bars[i], 'l') <= limit_price:
            # Conservative: fill at limit price, not better; this is a shadow execution model.
            return simulate_exit(row, bars, i, limit_price, label)
    return None


def has_real_reaction(row: Dict[str, Any], bars: List[Dict[str, Any]]) -> bool:
    reclaim_idx = int(num(row.get('reclaim_idx'), -1))
    touch_idx = int(num(row.get('touch_idx'), -1))
    if reclaim_idx < 0 or reclaim_idx >= len(bars) or touch_idx < 0 or touch_idx >= len(bars):
        return False
    rb = bars[reclaim_idx]
    tb = bars[touch_idx]
    zl = float(row.get('zone_low'))
    zh = float(row.get('zone_high'))
    body_ok = fbar(rb, 'c') > fbar(rb, 'o')
    reclaim_ok = fbar(rb, 'c') > zh and pct(fbar(rb, 'c'), zh) >= 0.5
    touch_ok = fbar(tb, 'l') <= zh and fbar(tb, 'l') >= zl * 0.985
    # Avoid counting gap-only reclaim with no actual intra-zone touch.
    return bool(body_ok and reclaim_ok and touch_ok)


def fake_recovery(row: Dict[str, Any], bars: List[Dict[str, Any]]) -> bool:
    if str(row.get('market_state')) != 'RECOVERY':
        return False
    event_idx = int(num(row.get('event_idx'), -1))
    reclaim_idx = int(num(row.get('reclaim_idx'), -1))
    if event_idx < 0 or event_idx >= len(bars) or reclaim_idx < 0 or reclaim_idx >= len(bars):
        return True
    evc = fbar(bars[event_idx], 'c')
    pre20 = pct(evc, fbar(bars[event_idx - 20], 'c')) if event_idx >= 20 else float('nan')
    pre60 = pct(evc, fbar(bars[event_idx - 60], 'c')) if event_idx >= 60 else float('nan')
    chase = float(row.get('entry_chase_above_zone_pct'))
    weak_gap = float(row.get('source_gap_atr')) < 0.8
    weak_mid = float(row.get('source_mid_body_atr')) < 0.65
    # False recovery = already bounced or still weak source, then entry chases above zone.
    return bool((pre20 > 5 or pre60 > 8 or weak_gap or weak_mid) and chase > 3)


def metrics(rows: Iterable[Dict[str, Any]], pnl_key='pnl_pct', exit_key='exit_reason') -> Dict[str, Any]:
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


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    fields = sorted({k for r in rows for k in r.keys()}) if rows else []
    with path.open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        if fields:
            w.writeheader()
            w.writerows(rows)


def bucket(rows: Iterable[Dict[str, Any]], keyfn: Callable[[Dict[str, Any]], str], pnl_key='pnl_pct', exit_key='exit_reason') -> Dict[str, Dict[str, Any]]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(keyfn(r))].append(r)
    return {k: metrics(v, pnl_key, exit_key) for k, v in sorted(g.items())}


def main() -> None:
    df = pd.read_csv(SRC)
    recent_df = pd.read_csv(RECENT_SRC)
    recent_keys = set(zip(recent_df['symbol'].astype(str), recent_df['entry_date'].astype(int), recent_df['poi_source'].astype(str)))
    fvg = df[(df['poi_source'] == 'FVG_Demand') & (df['valid_backtest'] == True)].copy()
    rows = fvg.to_dict('records')
    bar_cache: Dict[str, List[Dict[str, Any]]] = {}
    valid_rows: List[Dict[str, Any]] = []
    alt_rows: List[Dict[str, Any]] = []
    missing_kline = 0

    for r in rows:
        sym = str(r.get('symbol'))
        path = kline_path(sym)
        if sym not in bar_cache:
            if not path.exists():
                bar_cache[sym] = []
            else:
                bar_cache[sym] = load_json(path)
        bars = bar_cache[sym]
        if not bars:
            missing_kline += 1
            continue
        rr = dict(r)
        rr['is_recent45'] = (str(rr.get('symbol')), int(rr.get('entry_date')), str(rr.get('poi_source'))) in recent_keys
        rr['v131_real_reaction'] = has_real_reaction(rr, bars)
        rr['v131_fake_recovery'] = fake_recovery(rr, bars)
        valid_rows.append(rr)

        zl = float(rr.get('zone_low'))
        zh = float(rr.get('zone_high'))
        mid = (zl + zh) / 2.0
        limit_specs = [
            ('LIMIT_ZONE_HIGH_WAIT5', zh, 5),
            ('LIMIT_ZONE_HIGH_WAIT10', zh, 10),
            ('LIMIT_ZONE_MID_WAIT5', mid, 5),
            ('LIMIT_ZONE_MID_WAIT10', mid, 10),
            ('LIMIT_ZONE_HIGH_PLUS1_WAIT5', zh * 1.01, 5),
            ('LIMIT_ZONE_HIGH_PLUS2_WAIT5', zh * 1.02, 5),
        ]
        for label, price, wait in limit_specs:
            sim = find_limit_entry(rr, bars, price, wait, label)
            if sim:
                sim['is_recent45'] = rr['is_recent45']
                sim['v131_real_reaction'] = rr['v131_real_reaction']
                sim['v131_fake_recovery'] = rr['v131_fake_recovery']
                alt_rows.append(sim)

    recent = [r for r in valid_rows if r.get('is_recent45')]
    bm = [r for r in valid_rows if r.get('market_state') in ['BEAR_RISK', 'MIXED']]
    bm_real = [r for r in bm if r.get('v131_real_reaction')]
    no_recovery = [r for r in valid_rows if r.get('market_state') != 'RECOVERY']
    not_fake_recovery = [r for r in valid_rows if not r.get('v131_fake_recovery')]

    chase_reject = {}
    for th in [3, 5, 8]:
        kept = [r for r in valid_rows if num(r.get('entry_chase_above_zone_pct')) <= th]
        rejected = [r for r in valid_rows if num(r.get('entry_chase_above_zone_pct')) > th]
        chase_reject[f'chase_le_{th}'] = {
            'kept': metrics(kept),
            'rejected': metrics(rejected),
            'recent45_kept': metrics([r for r in kept if r.get('is_recent45')]),
            'recent45_rejected': metrics([r for r in rejected if r.get('is_recent45')]),
        }

    reclaim_distance = {}
    for th in [1, 2, 3, 5]:
        kept = [r for r in valid_rows if num(r.get('reclaim_close_above_zone_pct')) <= th]
        reclaim_distance[f'reclaim_close_le_{th}'] = {
            'kept': metrics(kept),
            'recent45_kept': metrics([r for r in kept if r.get('is_recent45')]),
        }

    entry_buffer = {}
    for th in [1, 2, 3, 5]:
        kept = [r for r in valid_rows if num(r.get('entry_chase_above_zone_pct')) <= th]
        entry_buffer[f'entry_le_zone_high_plus_{th}'] = {
            'kept': metrics(kept),
            'recent45_kept': metrics([r for r in kept if r.get('is_recent45')]),
        }

    alt_by_model = bucket(alt_rows, lambda r: r.get('v131_entry_model'), pnl_key='v131_pnl_pct', exit_key='v131_exit_reason')
    alt_recent_by_model = bucket([r for r in alt_rows if r.get('is_recent45')], lambda r: r.get('v131_entry_model'), pnl_key='v131_pnl_pct', exit_key='v131_exit_reason')
    alt_bm_real_by_model = bucket([r for r in alt_rows if r.get('market_state') in ['BEAR_RISK','MIXED'] and r.get('v131_real_reaction')], lambda r: r.get('v131_entry_model'), pnl_key='v131_pnl_pct', exit_key='v131_exit_reason')

    strict_shadow = [
        r for r in alt_rows
        if r.get('v131_entry_model') in ['LIMIT_ZONE_HIGH_WAIT5', 'LIMIT_ZONE_HIGH_PLUS1_WAIT5']
        and r.get('market_state') in ['BEAR_RISK', 'MIXED']
        and r.get('v131_real_reaction')
        and not r.get('v131_fake_recovery')
        and num(r.get('v131_entry_above_zone_high_pct')) <= 1
    ]
    strict_recent = [r for r in strict_shadow if r.get('is_recent45')]

    summary = {
        'decision': 'V131_FVG_ENTRY_EXECUTION_SHADOW_BACKTEST_DONE_NO_PRODUCTION_CHANGE',
        'run_at': datetime.now().isoformat(timespec='seconds'),
        'source': str(SRC),
        'recent_source': str(RECENT_SRC),
        'missing_kline': missing_kline,
        'baseline': metrics(valid_rows),
        'baseline_recent45': metrics(recent),
        'chase_reject_simulation': chase_reject,
        'reclaim_close_distance_simulation': reclaim_distance,
        'entry_buffer_simulation': entry_buffer,
        'recovery_split': {
            'recovery': metrics([r for r in valid_rows if r.get('market_state') == 'RECOVERY']),
            'fake_recovery': metrics([r for r in valid_rows if r.get('v131_fake_recovery')]),
            'non_recovery': metrics(no_recovery),
            'not_fake_recovery': metrics(not_fake_recovery),
            'recent45_recovery': metrics([r for r in recent if r.get('market_state') == 'RECOVERY']),
            'recent45_fake_recovery': metrics([r for r in recent if r.get('v131_fake_recovery')]),
            'recent45_not_fake_recovery': metrics([r for r in recent if not r.get('v131_fake_recovery')]),
        },
        'bear_mixed_reaction': {
            'bear_mixed_all': metrics(bm),
            'bear_mixed_real_reaction': metrics(bm_real),
            'bear_mixed_no_real_reaction': metrics([r for r in bm if not r.get('v131_real_reaction')]),
            'recent45_bear_mixed_real_reaction': metrics([r for r in recent if r.get('market_state') in ['BEAR_RISK','MIXED'] and r.get('v131_real_reaction')]),
        },
        'limit_entry_by_model': alt_by_model,
        'limit_entry_recent45_by_model': alt_recent_by_model,
        'limit_entry_bear_mixed_real_reaction_by_model': alt_bm_real_by_model,
        'strict_shadow_candidate': metrics(strict_shadow, 'v131_pnl_pct', 'v131_exit_reason'),
        'strict_shadow_candidate_recent45': metrics(strict_recent, 'v131_pnl_pct', 'v131_exit_reason'),
        'strict_shadow_n': len(strict_shadow),
        'strict_shadow_recent45_n': len(strict_recent),
        'by_market_state': bucket(valid_rows, lambda r: r.get('market_state')),
        'by_combo_family': bucket(valid_rows, lambda r: r.get('combo_family')),
        'no_production_change': True,
    }

    write_csv(OUT / 'v131_baseline_fvg_with_reaction_flags.csv', valid_rows)
    write_csv(OUT / 'v131_limit_entry_shadow_backtest.csv', alt_rows)
    write_csv(OUT / 'v131_strict_shadow_candidate.csv', strict_shadow)
    write_csv(OUT / 'v131_recent45_limit_entry_shadow_backtest.csv', [r for r in alt_rows if r.get('is_recent45')])
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = []
    lines.append('# V131 FVG_Demand Entry Execution Shadow Backtest')
    lines.append('')
    lines.append('Decision: `V131_FVG_ENTRY_EXECUTION_SHADOW_BACKTEST_DONE_NO_PRODUCTION_CHANGE`。只做 shadow/backtest，不接生产。')
    lines.append('')
    lines.append('## 1. Baseline')
    lines.append('|slice|n|WR|Avg|Loss|HardExit|Cum|')
    lines.append('|---|---:|---:|---:|---:|---:|---:|')
    for name, m in [('ALL', summary['baseline']), ('recent45', summary['baseline_recent45'])]:
        lines.append(f"|{name}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss_rate']}|{m['hard_exit_rate']}|{m['cum']}|")
    lines.append('')
    lines.append('## 2. Chase reject simulation')
    lines.append('|rule|kept_n|kept_WR|kept_Loss|rejected_n|rejected_WR|recent_kept_n|recent_kept_WR|')
    lines.append('|---|---:|---:|---:|---:|---:|---:|---:|')
    for name, d in chase_reject.items():
        k, rj, rk = d['kept'], d['rejected'], d['recent45_kept']
        lines.append(f"|{name}|{k['n']}|{k['wr']}|{k['loss_rate']}|{rj['n']}|{rj['wr']}|{rk['n']}|{rk['wr']}|")
    lines.append('')
    lines.append('## 3. Recovery split')
    lines.append('|slice|n|WR|Avg|Loss|HardExit|')
    lines.append('|---|---:|---:|---:|---:|---:|')
    for name, m in summary['recovery_split'].items():
        lines.append(f"|{name}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss_rate']}|{m['hard_exit_rate']}|")
    lines.append('')
    lines.append('## 4. BEAR_RISK/MIXED candle reaction')
    lines.append('|slice|n|WR|Avg|Loss|HardExit|')
    lines.append('|---|---:|---:|---:|---:|---:|')
    for name, m in summary['bear_mixed_reaction'].items():
        lines.append(f"|{name}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss_rate']}|{m['hard_exit_rate']}|")
    lines.append('')
    lines.append('## 5. Limit / second-pullback entry models')
    lines.append('|model|n|WR|Avg|Loss|HardExit|Cum|recent_n|recent_WR|')
    lines.append('|---|---:|---:|---:|---:|---:|---:|---:|---:|')
    for name, m in alt_by_model.items():
        rm = alt_recent_by_model.get(name, {'n':0,'wr':0})
        lines.append(f"|{name}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss_rate']}|{m['hard_exit_rate']}|{m['cum']}|{rm['n']}|{rm['wr']}|")
    lines.append('')
    lines.append('## 6. Strict shadow candidate')
    m = summary['strict_shadow_candidate']; rm = summary['strict_shadow_candidate_recent45']
    lines.append('|slice|n|WR|Avg|Loss|HardExit|Cum|')
    lines.append('|---|---:|---:|---:|---:|---:|---:|')
    lines.append(f"|strict_all|{m['n']}|{m['wr']}|{m['avg']}|{m['loss_rate']}|{m['hard_exit_rate']}|{m['cum']}|")
    lines.append(f"|strict_recent45|{rm['n']}|{rm['wr']}|{rm['avg']}|{rm['loss_rate']}|{rm['hard_exit_rate']}|{rm['cum']}|")
    lines.append('')
    lines.append('## 7. Conclusion')
    lines.append('V131 is a shadow execution test. If a limit/second-pullback model improves quality but kills coverage, keep it as research only. No production promotion.')
    (OUT / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    print(json.dumps({
        'out': str(OUT),
        'decision': summary['decision'],
        'baseline': summary['baseline'],
        'recent45': summary['baseline_recent45'],
        'strict_shadow_candidate': summary['strict_shadow_candidate'],
        'strict_shadow_candidate_recent45': summary['strict_shadow_candidate_recent45'],
        'best_limit_models': alt_by_model,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
