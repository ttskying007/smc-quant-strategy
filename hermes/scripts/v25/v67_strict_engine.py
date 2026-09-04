#!/usr/bin/env python3
"""V67 strict-registry candidate engine.

Builds trades directly from strict_smc_registry, then decides promotion vs
rollback without touching V66 production files.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from strict_smc_registry import atr, detect_strict_registry, dt, f, normalize_klines, zone_retrace_rank

ROOT = Path('/root/.hermes')
KLINE_DIR = ROOT / 'kline_cache'
OUT = ROOT / 'smc_opt_v67_strict'
AUDIT = ROOT / 'smc_audit'
OUT.mkdir(parents=True, exist_ok=True)
AUDIT.mkdir(parents=True, exist_ok=True)

MIN_TRADES = 30
MIN_WR = 80.0
MAX_SL_RATE = 18.0
MIN_AVG_PNL = 2.0
MAX_SYMBOLS = 999999


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def symbol_from_path(path: Path) -> str:
    s = path.name.replace('_daily_750.json', '').replace('_daily_300.json', '')
    parts = s.split('_')
    return f'{parts[0]}.{parts[1]}' if len(parts) == 2 else s


def next_swing_target(klines: List[Dict[str, Any]], entry_idx: int, entry_price: float) -> float:
    target = entry_price * 1.06
    for j in range(entry_idx + 1, min(len(klines), entry_idx + 80)):
        if klines[j]['h'] > entry_price * 1.03:
            target = klines[j]['h']
            break
    return target


def strict_pinbar_or_reclaim(klines: List[Dict[str, Any]], idx: int, zone: Dict[str, Any]) -> str:
    if idx >= len(klines):
        return ''
    b = klines[idx]
    op, cl, hi, lo = b['o'], b['c'], b['h'], b['l']
    rng = max(hi - lo, 0.0001)
    body = abs(cl - op)
    lower_wick = min(op, cl) - lo
    zl, zh = f(zone.get('zone_low')), f(zone.get('zone_high'))
    touched = lo <= zh * 1.005 and hi >= zl * 0.995
    if not touched:
        return ''
    if body > 0 and lower_wick > body * 2.0 and lower_wick > rng * 0.45 and cl > op:
        return 'PINBAR_BOUNCE'
    if lo < zl and cl > zl and cl > op:
        return 'IDM_RECLAIM'
    if cl > op and cl > (zl + zh) / 2:
        return 'BULL_RECLAIM'
    return ''


def build_setups(symbol: str, raw_klines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    klines = normalize_klines(raw_klines)
    reg = detect_strict_registry(klines)
    sigs = reg['signals']
    structures = [s for s in sigs['structure'] if s['type'] in ('BOS_Bull', 'CHOCH_Bull')]
    structures_by_idx = {s['index']: s for s in structures}
    zones = []
    for ob in sigs['obs']:
        if ob.get('anchor_event_idx') in structures_by_idx:
            zones.append(ob)
    for fvg in sigs['fvgs']:
        for ev in structures:
            if fvg['index'] <= ev['index'] <= fvg['index'] + 8:
                z = dict(fvg)
                z['anchor_event_idx'] = ev['index']
                z['anchor_event_type'] = ev['type']
                z['confirm_index'] = ev['index']
                z['broken_swing_idx'] = ev.get('broken_swing_idx', -1)
                z['broken_swing_price'] = ev.get('broken_swing_price', 0)
                zones.append(z)
                break
    setups = []
    n = len(klines)
    for z in zones:
        zi = int(z['index'])
        ci = int(z.get('confirm_index') if z.get('confirm_index', -1) >= 0 else z.get('anchor_event_idx', -1))
        if zi < 0 or ci <= zi or ci >= n - 2:
            continue
        zl, zh = f(z.get('zone_low')), f(z.get('zone_high'))
        if zl <= 0 or zh <= zl:
            continue
        rank_at_confirm = zone_retrace_rank(klines, z, ci)
        if z['type'] == 'OB_Bull' and rank_at_confirm > 0:
            continue
        invalid = False
        for j in range(zi + 1, ci + 1):
            if klines[j]['c'] < zl * 0.99:
                invalid = True
                break
        if invalid:
            continue
        retrace_idx = -1
        conf_idx = -1
        conf_type = ''
        for j in range(ci + 1, min(ci + 35, n - 2)):
            if klines[j]['c'] < zl * 0.99:
                break
            if klines[j]['l'] <= zh * 1.005:
                ct = strict_pinbar_or_reclaim(klines, j, z)
                if ct:
                    retrace_idx = j
                    conf_idx = j
                    conf_type = ct
                    break
        if conf_idx < 0:
            continue
        entry_idx = conf_idx + 1
        entry_price = klines[entry_idx]['o'] or klines[entry_idx]['c']
        if entry_price <= 0:
            continue
        if z['type'] == 'OB_Bull' and entry_price > zh * 1.03:
            continue
        if z['type'] == 'FVG_Bull' and entry_price > zh * 1.06:
            continue
        a = atr(klines, entry_idx)
        sl = min(zl - a * 0.35, entry_price * 0.98)
        risk_pct = (entry_price - sl) / entry_price * 100
        if risk_pct < 1.5:
            sl = entry_price * 0.985
            risk_pct = 1.5
        if risk_pct > 8.0:
            continue
        tp = max(next_swing_target(klines, entry_idx, entry_price), entry_price * (1 + max(risk_pct * 1.5, 3.0) / 100))
        rr = (tp - entry_price) / (entry_price - sl) if entry_price > sl else 0
        if rr < 1.3:
            continue
        ev = structures_by_idx.get(int(z.get('anchor_event_idx')), {})
        setups.append({
            'symbol': symbol,
            'name': '',
            'engine': 'V67_STRICT_REGISTRY_CANDIDATE',
            'definition_version': 'V67_STRICT_REGISTRY',
            'zone_type': z['type'],
            'conf_type': ev.get('type', z.get('anchor_event_type', '')),
            'entry_confirm_type': conf_type,
            'source_event': ev.get('type', z.get('anchor_event_type', '')),
            'source_event_idx': int(z.get('anchor_event_idx', ci)),
            'signal_index': int(z.get('anchor_event_idx', ci)),
            'broken_swing_idx': int(z.get('broken_swing_idx', ev.get('broken_swing_idx', -1))),
            'broken_swing_price': round(f(z.get('broken_swing_price', ev.get('broken_swing_price', 0))), 4),
            'zone_idx': zi,
            'zone_date': z.get('date', dt(klines[zi]) if zi < n else ''),
            'conf_index': ci,
            'confirm_date': dt(klines[ci]),
            'retrace_index': retrace_idx,
            'entry_index': entry_idx,
            'entry_date': dt(klines[entry_idx]),
            'select_date': dt(klines[entry_idx]),
            'pick_date': dt(klines[entry_idx]),
            'entry_price': round(entry_price, 3),
            'price': round(entry_price, 3),
            'zone_low': round(zl, 3),
            'zone_high': round(zh, 3),
            'dz_low': round(zl, 3),
            'dz_high': round(zh, 3),
            'raw_zone_low': round(zl, 3),
            'raw_zone_high': round(zh, 3),
            'sl': round(sl, 3),
            'risk_pct': round(risk_pct, 3),
            'tp': round(tp, 3),
            'tp1': round(tp, 3),
            'rr': round(rr, 3),
            'smart_money_cost': round((zl + zh) / 2, 3),
            'v25_cost_line': round((zl + zh) / 2, 3),
            'atr': round(a, 4),
            'atr_pct': round(a / entry_price * 100, 3),
            'volatility_pct': round(a / entry_price * 100, 3),
            'retrace_rank': rank_at_confirm,
            'v59_setup_family': 'STRICT_OB_FIRST_TOUCH' if z['type'] == 'OB_Bull' else 'STRICT_FVG_RETRACE',
            'ctx_seq': f"{z['type']}→{ev.get('type', z.get('anchor_event_type',''))}→{conf_type}",
            'seq': f"{z['type']}-{ev.get('type', z.get('anchor_event_type',''))}-{conf_type}",
            'strict_semantic_expected': True,
        })
    return setups


def backtest(setups: List[Dict[str, Any]], klines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    bars = normalize_klines(klines)
    for st in setups:
        entry_idx = int(st['entry_index'])
        if entry_idx >= len(bars) - 2:
            continue
        entry = f(st['entry_price'])
        sl = f(st['sl'])
        tp = f(st['tp'])
        exit_idx = -1
        exit_price = 0.0
        reason = 'TIMEOUT'
        for j in range(entry_idx + 1, min(entry_idx + 60, len(bars))):
            if bars[j]['l'] <= sl:
                exit_idx = j
                exit_price = sl
                reason = 'SL_HIT'
                break
            if bars[j]['h'] >= tp:
                exit_idx = j
                exit_price = tp
                reason = 'TP_HIT'
                break
        if exit_idx < 0:
            exit_idx = min(entry_idx + 60, len(bars) - 1)
            exit_price = bars[exit_idx]['c']
        if exit_idx <= entry_idx:
            continue
        pnl = (exit_price - entry) / entry * 100 if entry else 0
        trade = dict(st)
        trade.update({
            'exit_index': exit_idx,
            'exit_date': dt(bars[exit_idx]),
            'exit_price': round(exit_price, 3),
            'exit_reason': reason,
            'pnl_pct': round(pnl, 3),
            'hold_bars': exit_idx - entry_idx,
            'won': pnl > 0,
        })
        out.append(trade)
    return out


def metrics(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not trades:
        return {'n_trades': 0}
    wins = [t for t in trades if f(t.get('pnl_pct')) > 0]
    losses = [t for t in trades if f(t.get('pnl_pct')) <= 0]
    sls = [t for t in trades if t.get('exit_reason') == 'SL_HIT']
    avg_win = statistics.mean([f(t['pnl_pct']) for t in wins]) if wins else 0
    avg_loss = abs(statistics.mean([f(t['pnl_pct']) for t in losses])) if losses else 0
    return {
        'n_trades': len(trades),
        'n_wins': len(wins),
        'n_losses': len(losses),
        'wr': round(len(wins) / len(trades) * 100, 2),
        'avg_pnl': round(statistics.mean([f(t['pnl_pct']) for t in trades]), 3),
        'avg_win': round(avg_win, 3),
        'avg_loss': round(avg_loss, 3),
        'rr': round(avg_win / avg_loss, 3) if avg_loss else 0,
        'sl_rate': round(len(sls) / len(trades) * 100, 2),
        'exit_counts': dict(Counter(t.get('exit_reason') for t in trades)),
        'zone_counts': dict(Counter(t.get('zone_type') for t in trades)),
        'conf_counts': dict(Counter(t.get('conf_type') for t in trades)),
    }


def main() -> None:
    trades: List[Dict[str, Any]] = []
    picks: List[Dict[str, Any]] = []
    scanned = 0
    errors = []
    files = sorted(KLINE_DIR.glob('*_daily_750.json'))[:MAX_SYMBOLS]
    for path in files:
        symbol = symbol_from_path(path)
        raw = load_json(path, [])
        if len(raw) < 120:
            continue
        scanned += 1
        try:
            setups = build_setups(symbol, raw)
            trs = backtest(setups, raw)
            trades.extend(trs)
            if setups:
                last = max(setups, key=lambda x: x['entry_index'])
                pick = dict(last)
                pick['is_active_pick'] = last.get('entry_index', 0) >= len(raw) - 5
                pick['pick_scope'] = 'ACTIVE_CANDIDATE' if pick['is_active_pick'] else 'HISTORICAL_STRICT_SIGNAL'
                picks.append(pick)
        except Exception as exc:
            errors.append({'symbol': symbol, 'error': repr(exc)})
            if len(errors) > 50:
                break
    m = metrics(trades)
    effect_pass = (
        m.get('n_trades', 0) >= MIN_TRADES and
        m.get('wr', 0) >= MIN_WR and
        m.get('sl_rate', 100) <= MAX_SL_RATE and
        m.get('avg_pnl', -999) >= MIN_AVG_PNL
    )
    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': 'V67_STRICT_REGISTRY_CANDIDATE',
        'scanned_symbols': scanned,
        'n_errors': len(errors),
        'errors_sample': errors[:20],
        'metrics': m,
        'thresholds': {'MIN_TRADES': MIN_TRADES, 'MIN_WR': MIN_WR, 'MAX_SL_RATE': MAX_SL_RATE, 'MIN_AVG_PNL': MIN_AVG_PNL},
        'effect_pass': effect_pass,
        'promotion_candidate': effect_pass,
        'rollback_to': None if effect_pass else 'V66_RECENT_REENTRY_RISK_OVERLAY',
    }
    for name, data in {
        'v67_trades.json': trades,
        'v67_picks.json': picks,
        'v67_report.json': report,
    }.items():
        (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
