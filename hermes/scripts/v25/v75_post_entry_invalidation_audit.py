#!/usr/bin/env python3
"""V75 post-entry structural invalidation audit for V74 SMC state machine.

Purpose: diagnose the remaining V74 failures without changing production.
This script only uses pre-entry structure for anchors and post-entry bar-by-bar
facts that would have been known at each bar close.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

KLINE_DIR = Path('/root/.hermes/kline_cache')
V74_DIR = Path('/root/.hermes/smc_opt_v74_env_state_machine')
OUT_DIR = Path('/root/.hermes/smc_opt_v75_post_entry_invalidation')
OUT_DIR.mkdir(parents=True, exist_ok=True)

RISK_ENV_STATES = {'DISTRIBUTION', 'BEAR_RISK'}
WEAK_ENV_STATES = {'DISTRIBUTION', 'BEAR_RISK', 'MIXED'}


def f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x if x is not None else default)
    except Exception:
        return default


def dt(bar: Dict[str, Any]) -> str:
    return str(bar.get('t') or bar.get('date') or '')[:8]


def sym_to_cache(symbol: str) -> Path:
    code, ex = symbol.split('.')
    return KLINE_DIR / f'{code}_{ex}_daily_750.json'


def load_klines(symbol: str) -> List[Dict[str, Any]]:
    p = sym_to_cache(symbol)
    if not p.exists():
        return []
    rows = json.loads(p.read_text())
    out = []
    for b in rows:
        nb = dict(b)
        for k in ('o', 'h', 'l', 'c'):
            nb[k] = f(nb.get(k))
        out.append(nb)
    return out


def metrics(rows: Iterable[Dict[str, Any]], pnl_key: str = 'pnl_pct') -> Dict[str, Any]:
    rs = list(rows)
    if not rs:
        return {'n': 0, 'wr': 0, 'sl_rate': 0, 'avg_pnl': 0, 'cum': 0, 'avg_win': 0, 'avg_loss': 0, 'payoff': 0, 'avg_hold': 0}
    wins = [r for r in rs if f(r.get(pnl_key)) > 0]
    losses = [r for r in rs if f(r.get(pnl_key)) <= 0]
    sl = [r for r in rs if r.get('exit_reason') == 'SL_HIT']
    avg = sum(f(r.get(pnl_key)) for r in rs) / len(rs)
    aw = sum(f(r.get(pnl_key)) for r in wins) / len(wins) if wins else 0
    al = sum(f(r.get(pnl_key)) for r in losses) / len(losses) if losses else 0
    return {
        'n': len(rs),
        'wr': round(len(wins) / len(rs) * 100, 2),
        'sl_rate': round(len(sl) / len(rs) * 100, 2),
        'avg_pnl': round(avg, 4),
        'cum': round(sum(f(r.get(pnl_key)) for r in rs), 2),
        'avg_win': round(aw, 4),
        'avg_loss': round(al, 4),
        'payoff': round(aw / abs(al), 3) if al else 0,
        'avg_hold': round(sum(f(r.get('hold_bars')) for r in rs) / len(rs), 2),
    }


def bucket(rows: Iterable[Dict[str, Any]], key, pnl_key: str = 'pnl_pct') -> Dict[str, Any]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(key(r))].append(r)
    return {k: metrics(v, pnl_key=pnl_key) for k, v in sorted(g.items())}


def confirmed_swings(ks: List[Dict[str, Any]], upto: int, left: int = 3, right: int = 3) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    highs, lows = [], []
    end = min(upto, len(ks) - right)
    for i in range(left, end):
        hi = ks[i]['h']; lo = ks[i]['l']
        if hi > 0 and all(j == i or ks[j]['h'] < hi for j in range(i-left, i+right+1)) and i + right < upto:
            highs.append({'idx': i, 'price': hi, 'date': dt(ks[i]), 'confirm_idx': i + right})
        if lo > 0 and all(j == i or ks[j]['l'] > lo for j in range(i-left, i+right+1)) and i + right < upto:
            lows.append({'idx': i, 'price': lo, 'date': dt(ks[i]), 'confirm_idx': i + right})
    return highs, lows


def prior_structure_anchors(ks: List[Dict[str, Any]], entry_idx: int, entry_price: float) -> Dict[str, Any]:
    highs, lows = confirmed_swings(ks, entry_idx)
    prior_low = lows[-1] if lows else {}
    higher_lows = [x for x in lows if x.get('price', 0) < entry_price]
    prior_hl = higher_lows[-1] if higher_lows else prior_low
    bsl_candidates = [x for x in highs[-12:] if x.get('price', 0) > entry_price]
    nearest_bsl = min(bsl_candidates, key=lambda x: x['price']) if bsl_candidates else {}
    return {'prior_swing_low': prior_low, 'prior_hl': prior_hl, 'nearest_bsl': nearest_bsl, 'n_prior_highs': len(highs), 'n_prior_lows': len(lows)}


def first_event_after_entry(
    ks: List[Dict[str, Any]],
    trade: Dict[str, Any],
    env_by_date: Dict[str, Dict[str, Any]],
    anchors: Dict[str, Any],
) -> Dict[str, Any]:
    entry_idx = int(f(trade.get('entry_idx'), -1))
    exit_idx = int(f(trade.get('exit_idx'), entry_idx))
    zone_low = f(trade.get('zone_low') or trade.get('dz_low'))
    zone_high = f(trade.get('zone_high') or trade.get('dz_high'))
    entry_price = f(trade.get('entry_price'))
    sl = f(trade.get('sl'))
    tp1 = f(trade.get('tp1'))
    prior_hl_price = f((anchors.get('prior_hl') or {}).get('price'))
    bsl_price = f((anchors.get('nearest_bsl') or {}).get('price'))
    out = {
        'close_below_poi_idx': None,
        'close_below_poi_date': None,
        'close_below_poi_pnl': None,
        'prior_hl_break_idx': None,
        'prior_hl_break_date': None,
        'prior_hl_break_pnl': None,
        'risk_env_idx': None,
        'risk_env_date': None,
        'risk_env_state': None,
        'weak_env_idx': None,
        'weak_env_date': None,
        'weak_env_state': None,
        'first_tp_idx': None,
        'first_sl_idx': None,
        'mfe_before_exit_pct': 0,
        'mae_before_exit_pct': 0,
        'bsl_available': bool(bsl_price),
        'bsl_distance_pct': round((bsl_price / entry_price - 1) * 100, 4) if bsl_price and entry_price else 0,
        'tp_above_nearest_bsl': bool(bsl_price and tp1 and tp1 > bsl_price * 1.002),
        'prior_hl_price': prior_hl_price,
        'nearest_bsl_price': bsl_price,
    }
    if entry_idx < 0 or not ks:
        return out
    end = min(exit_idx, len(ks) - 1)
    max_high = entry_price
    min_low = entry_price
    # A-share T+1: any discretionary close exit starts from entry_idx+1.
    for i in range(entry_idx + 1, end + 1):
        b = ks[i]
        max_high = max(max_high, b['h'])
        min_low = min(min_low, b['l'])
        date = dt(b)
        if out['first_tp_idx'] is None and tp1 and b['h'] >= tp1:
            out['first_tp_idx'] = i
        if out['first_sl_idx'] is None and sl and b['l'] <= sl:
            out['first_sl_idx'] = i
        if out['close_below_poi_idx'] is None and zone_low and b['c'] < zone_low:
            out['close_below_poi_idx'] = i
            out['close_below_poi_date'] = date
            out['close_below_poi_pnl'] = round((b['c'] / entry_price - 1) * 100, 4) if entry_price else 0
        if out['prior_hl_break_idx'] is None and prior_hl_price and b['c'] < prior_hl_price:
            out['prior_hl_break_idx'] = i
            out['prior_hl_break_date'] = date
            out['prior_hl_break_pnl'] = round((b['c'] / entry_price - 1) * 100, 4) if entry_price else 0
        env_state = str((env_by_date.get(date) or {}).get('market_state_v74') or '')
        if out['risk_env_idx'] is None and env_state in RISK_ENV_STATES:
            out['risk_env_idx'] = i
            out['risk_env_date'] = date
            out['risk_env_state'] = env_state
        if out['weak_env_idx'] is None and env_state in WEAK_ENV_STATES:
            out['weak_env_idx'] = i
            out['weak_env_date'] = date
            out['weak_env_state'] = env_state
    out['mfe_before_exit_pct'] = round((max_high / entry_price - 1) * 100, 4) if entry_price else 0
    out['mae_before_exit_pct'] = round((min_low / entry_price - 1) * 100, 4) if entry_price else 0
    return out


def classify_primary_post_entry_fail(row: Dict[str, Any]) -> str:
    if f(row.get('pnl_pct')) > 0:
        if row.get('tp_above_nearest_bsl'):
            return 'WIN_BUT_TP_ABOVE_NEAREST_BSL'
        return 'WIN_OK'
    cpoi = row.get('close_below_poi_idx')
    hl = row.get('prior_hl_break_idx')
    tp = row.get('first_tp_idx')
    risk = row.get('risk_env_idx')
    weak = row.get('weak_env_idx')
    if cpoi is not None and (tp is None or cpoi < tp):
        return 'LOSS_POI_CLOSE_BREAK_BEFORE_TP'
    if hl is not None and (tp is None or hl < tp):
        return 'LOSS_PRIOR_HL_BREAK_BEFORE_TP'
    if risk is not None and (tp is None or risk < tp):
        return 'LOSS_ENV_RISK_BEFORE_TP'
    if weak is not None and (tp is None or weak < tp):
        return 'LOSS_ENV_WEAK_BEFORE_TP'
    if not row.get('bsl_available'):
        return 'LOSS_NO_BSL_TARGET_ABOVE_ENTRY'
    if row.get('tp_above_nearest_bsl'):
        return 'LOSS_TP_OVERSHOOTS_NEAREST_BSL'
    if f(row.get('mfe_before_exit_pct')) < 0.8:
        return 'LOSS_NO_REACTION_MFE_LT_0P8'
    return 'LOSS_UNEXPLAINED_BY_V75'


def apply_early_exit(row: Dict[str, Any], rule: str) -> Dict[str, Any]:
    nt = dict(row)
    actual_exit_idx = int(f(row.get('exit_idx'), 10**9))
    candidates = []
    if rule in ('POI_BREAK', 'COMBINED') and row.get('close_below_poi_idx') is not None:
        candidates.append(('POI_BREAK_EXIT', int(row['close_below_poi_idx']), f(row.get('close_below_poi_pnl'))))
    if rule in ('HL_BREAK', 'COMBINED') and row.get('prior_hl_break_idx') is not None:
        candidates.append(('HL_BREAK_EXIT', int(row['prior_hl_break_idx']), f(row.get('prior_hl_break_pnl'))))
    # Environment exit needs close price; without cached close in annotation, use as a label-only diagnostic.
    candidates = [c for c in candidates if c[1] < actual_exit_idx]
    if candidates:
        reason, idx, pnl = min(candidates, key=lambda x: x[1])
        nt[f'pnl_{rule}'] = pnl
        nt[f'exit_reason_{rule}'] = reason
        nt[f'hold_bars_{rule}'] = max(1, idx - int(f(row.get('entry_idx'))))
    else:
        nt[f'pnl_{rule}'] = f(row.get('pnl_pct'))
        nt[f'exit_reason_{rule}'] = row.get('exit_reason')
        nt[f'hold_bars_{rule}'] = row.get('hold_bars')
    return nt


def main() -> None:
    trades = json.loads((V74_DIR / 'v74_selected_trades.json').read_text())
    env_by_date = json.loads((V74_DIR / 'v74_env_by_date.json').read_text())
    annotated = []
    missing_klines = 0
    for t in trades:
        ks = load_klines(str(t.get('symbol')))
        if not ks:
            missing_klines += 1
            continue
        entry_idx = int(f(t.get('entry_idx'), -1))
        anchors = prior_structure_anchors(ks, entry_idx, f(t.get('entry_price')))
        ev = first_event_after_entry(ks, t, env_by_date, anchors)
        nt = dict(t)
        for prefix, obj in anchors.items():
            if isinstance(obj, dict):
                for k, v in obj.items():
                    nt[f'{prefix}_{k}'] = v
            else:
                nt[prefix] = obj
        nt.update(ev)
        nt['v75_primary_post_entry_fail'] = classify_primary_post_entry_fail(nt)
        annotated.append(nt)

    sim_poi = [apply_early_exit(r, 'POI_BREAK') for r in annotated]
    sim_hl = [apply_early_exit(r, 'HL_BREAK') for r in annotated]
    sim_combined = [apply_early_exit(r, 'COMBINED') for r in annotated]

    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': 'V75_POST_ENTRY_INVALIDATION_AUDIT',
        'hypothesis': 'Remaining V74 failures should be explained by POI close-break, prior HL break, environment deterioration, or missing/over-shot liquidity targets.',
        'input': {'v74_selected': len(trades), 'annotated': len(annotated), 'missing_klines': missing_klines},
        'base_v74': metrics(annotated),
        'primary_post_entry_fail': bucket(annotated, lambda t: t.get('v75_primary_post_entry_fail')),
        'loss_fail_counts': dict(sorted({k: len([r for r in annotated if r.get('v75_primary_post_entry_fail') == k and f(r.get('pnl_pct')) <= 0]) for k in set(r.get('v75_primary_post_entry_fail') for r in annotated)}.items())),
        'buckets': {
            'year': bucket(annotated, lambda t: str(t.get('entry_date',''))[:4]),
            'setup_story_v74': bucket(annotated, lambda t: t.get('setup_story_v74')),
            'market_state_v74': bucket(annotated, lambda t: t.get('market_state_v74')),
            'poi_close_break_before_tp': bucket(annotated, lambda t: bool(t.get('close_below_poi_idx') is not None and (t.get('first_tp_idx') is None or t.get('close_below_poi_idx') < t.get('first_tp_idx')))),
            'prior_hl_break_before_tp': bucket(annotated, lambda t: bool(t.get('prior_hl_break_idx') is not None and (t.get('first_tp_idx') is None or t.get('prior_hl_break_idx') < t.get('first_tp_idx')))),
            'bsl_available': bucket(annotated, lambda t: bool(t.get('bsl_available'))),
            'tp_above_nearest_bsl': bucket(annotated, lambda t: bool(t.get('tp_above_nearest_bsl'))),
            'mfe_bin': bucket(annotated, lambda t: '<0.8' if f(t.get('mfe_before_exit_pct')) < 0.8 else ('0.8-2' if f(t.get('mfe_before_exit_pct')) < 2 else ('2-4' if f(t.get('mfe_before_exit_pct')) < 4 else '>=4'))),
        },
        'early_exit_sim': {
            'poi_close_break': metrics(sim_poi, pnl_key='pnl_POI_BREAK'),
            'prior_hl_break': metrics(sim_hl, pnl_key='pnl_HL_BREAK'),
            'combined_poi_or_hl_break': metrics(sim_combined, pnl_key='pnl_COMBINED'),
        },
        'files': {
            'annotated': str(OUT_DIR / 'v75_annotated_trades.json'),
            'report': str(OUT_DIR / 'v75_report.json'),
            'markdown': str(OUT_DIR / 'v75_report.md'),
        },
    }
    (OUT_DIR / 'v75_annotated_trades.json').write_text(json.dumps(annotated, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v75_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    md = ['# V75 Post-entry Structural Invalidation Audit\n\n']
    md.append('## Summary\n\n```json\n')
    md.append(json.dumps({k: report[k] for k in ('input','base_v74','primary_post_entry_fail','early_exit_sim')}, ensure_ascii=False, indent=2))
    md.append('\n```\n')
    md.append('\n## Buckets\n\n```json\n')
    md.append(json.dumps(report['buckets'], ensure_ascii=False, indent=2))
    md.append('\n```\n')
    (OUT_DIR / 'v75_report.md').write_text(''.join(md))
    print(json.dumps({k: report[k] for k in ('input','base_v74','primary_post_entry_fail','early_exit_sim','files')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
