#!/usr/bin/env python3
"""V68 directional-classifier candidate.

Strict registry is used only as a geometry classifier.  The trade layer adds a
separate direction classifier and only trades OB demand zones after a liquidity
sweep / CHOCH / discount-retrace sequence.  FVG is context only, never a
standalone retrace-buy setup.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from strict_smc_registry import atr, detect_strict_registry, dt, f, normalize_klines, zone_retrace_rank
from v67_strict_engine import strict_pinbar_or_reclaim

ROOT = Path('/root/.hermes')
KLINE_DIR = ROOT / 'kline_cache'
OUT = ROOT / 'smc_opt_v68_directional'
AUDIT = ROOT / 'smc_audit'
OUT.mkdir(parents=True, exist_ok=True)
AUDIT.mkdir(parents=True, exist_ok=True)

MIN_TRADES = 30
MIN_WR = 70.0
MAX_SL_RATE = 30.0
MIN_AVG_PNL = 1.0
MAX_SYMBOLS = 999999


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def symbol_from_path(path: Path) -> str:
    stem = path.name.replace('_daily_750.json', '').replace('_daily_300.json', '')
    parts = stem.split('_')
    return f'{parts[0]}.{parts[1]}' if len(parts) == 2 else stem


def prior_swing_low(swings: List[Dict[str, Any]], idx: int) -> Optional[Dict[str, Any]]:
    lows = [s for s in swings if int(s.get('confirm_idx', 999999)) < idx]
    return lows[-1] if lows else None


def find_ssl_sweep(klines: List[Dict[str, Any]], swing_lows: List[Dict[str, Any]], start: int, end: int) -> Optional[Dict[str, Any]]:
    best = None
    for j in range(max(10, start), min(end + 1, len(klines))):
        ref = prior_swing_low(swing_lows, j)
        if not ref:
            continue
        ref_price = f(ref.get('price'))
        if ref_price <= 0:
            continue
        low = f(klines[j].get('l'))
        close = f(klines[j].get('c'))
        open_ = f(klines[j].get('o'))
        pierced = low < ref_price * 0.997
        reclaimed = close > ref_price * 0.998 or (close > open_ and close > low * 1.015)
        if pierced and reclaimed:
            depth = (ref_price - low) / ref_price * 100
            row = {'idx': j, 'date': dt(klines[j]), 'ref_idx': int(ref['idx']), 'ref_price': ref_price, 'low': low, 'depth_pct': depth}
            if best is None or row['depth_pct'] > best['depth_pct']:
                best = row
    return best


def has_fvg_context(fvgs: List[Dict[str, Any]], sweep_idx: int, confirm_idx: int) -> bool:
    return any(sweep_idx <= int(f.get('index', -1)) <= confirm_idx for f in fvgs)


def classify_direction(klines: List[Dict[str, Any]], reg: Dict[str, Any], zone: Dict[str, Any], ev: Dict[str, Any]) -> Dict[str, Any]:
    ci = int(ev.get('index', -1))
    zi = int(zone.get('index', -1))
    if ci <= 0 or zi < 0:
        return {'pass': False, 'reason': 'BAD_INDEX'}
    if zone.get('type') != 'OB_Bull':
        return {'pass': False, 'reason': 'FVG_CONTEXT_ONLY'}
    if ev.get('type') != 'CHOCH_Bull':
        return {'pass': False, 'reason': 'BOS_CONTINUATION_BLOCKED'}

    swing_lows = reg['signals']['swings']['lows']
    sweep = find_ssl_sweep(klines, swing_lows, ci - 30, ci)
    if not sweep:
        return {'pass': False, 'reason': 'NO_SSL_SWEEP'}
    if not (sweep['idx'] <= zi <= ci):
        return {'pass': False, 'reason': 'OB_NOT_AFTER_SWEEP'}

    impulse_low = f(sweep['low'])
    impulse_high = f(klines[ci].get('c'))
    if impulse_low <= 0 or impulse_high <= impulse_low:
        return {'pass': False, 'reason': 'BAD_IMPULSE'}
    zl, zh = f(zone.get('zone_low')), f(zone.get('zone_high'))
    zone_mid = (zl + zh) / 2
    discount_ceiling = impulse_low + (impulse_high - impulse_low) * 0.62
    if zone_mid > discount_ceiling:
        return {'pass': False, 'reason': 'ZONE_NOT_DISCOUNT'}

    fvg_ctx = has_fvg_context(reg['signals']['fvgs'], sweep['idx'], ci)
    return {
        'pass': True,
        'reason': 'SSL_SWEEP_CHOCH_DISCOUNT_OB',
        'sweep': sweep,
        'impulse_low': impulse_low,
        'impulse_high': impulse_high,
        'discount_ceiling': discount_ceiling,
        'fvg_context': fvg_ctx,
    }


def next_target(klines: List[Dict[str, Any]], entry_idx: int, entry_price: float, broken_swing: float) -> float:
    target = max(broken_swing, entry_price * 1.04)
    for j in range(entry_idx + 1, min(len(klines), entry_idx + 80)):
        if f(klines[j].get('h')) > entry_price * 1.035:
            target = max(target, f(klines[j].get('h')))
            break
    return target


def build_setups(symbol: str, raw_klines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    klines = normalize_klines(raw_klines)
    reg = detect_strict_registry(klines)
    structures = [s for s in reg['signals']['structure'] if s['type'] in ('BOS_Bull', 'CHOCH_Bull')]
    structures_by_idx = {int(s['index']): s for s in structures}
    setups: List[Dict[str, Any]] = []
    n = len(klines)

    for z in reg['signals']['obs']:
        ci = int(z.get('confirm_index', z.get('anchor_event_idx', -1)))
        ev = structures_by_idx.get(ci, {})
        direction = classify_direction(klines, reg, z, ev)
        if not direction.get('pass'):
            continue
        zi = int(z['index'])
        if ci <= zi or ci >= n - 3:
            continue
        zl, zh = f(z.get('zone_low')), f(z.get('zone_high'))
        if zl <= 0 or zh <= zl:
            continue
        rank_at_confirm = zone_retrace_rank(klines, z, ci)
        if rank_at_confirm > 0:
            continue
        invalid = False
        for j in range(zi + 1, ci + 1):
            if f(klines[j].get('c')) < zl * 0.99:
                invalid = True
                break
        if invalid:
            continue

        retrace_idx = -1
        conf_idx = -1
        conf_type = ''
        sweep = direction['sweep']
        impulse_low = f(direction['impulse_low'])
        impulse_high = f(direction['impulse_high'])
        discount_ceiling = f(direction['discount_ceiling'])
        for j in range(ci + 1, min(ci + 45, n - 2)):
            if f(klines[j].get('c')) < zl * 0.985:
                break
            if f(klines[j].get('l')) <= zh * 1.005 and f(klines[j].get('l')) <= discount_ceiling:
                ct = strict_pinbar_or_reclaim(klines, j, z)
                if ct:
                    retrace_idx = j
                    conf_idx = j
                    conf_type = ct
                    break
        if conf_idx < 0:
            continue

        entry_idx = conf_idx + 1
        entry_price = f(klines[entry_idx].get('o')) or f(klines[entry_idx].get('c'))
        if entry_price <= 0 or entry_price > zh * 1.03 or entry_price > discount_ceiling * 1.025:
            continue
        a = atr(klines, entry_idx)
        sl = min(zl - a * 0.25, f(sweep['low']) * 0.995, entry_price * 0.98)
        risk_pct = (entry_price - sl) / entry_price * 100
        if risk_pct < 1.5:
            sl = entry_price * 0.985
            risk_pct = 1.5
        if risk_pct > 7.0:
            continue
        tp = max(next_target(klines, entry_idx, entry_price, f(ev.get('broken_swing_price'))), entry_price * (1 + max(risk_pct * 1.8, 4.0) / 100))
        rr = (tp - entry_price) / (entry_price - sl) if entry_price > sl else 0
        if rr < 1.5:
            continue

        setups.append({
            'symbol': symbol,
            'name': '',
            'engine': 'V68_DIRECTION_CLASSIFIER_CANDIDATE',
            'definition_version': 'V68_STRICT_GEOMETRY_DIRECTION_LAYER',
            'zone_type': z['type'],
            'trade_signal_type': 'DIRECTIONAL_OB_DEMAND',
            'fvg_role': 'CONTEXT_ONLY' if direction.get('fvg_context') else 'ABSENT',
            'conf_type': ev.get('type', z.get('anchor_event_type', '')),
            'entry_confirm_type': conf_type,
            'direction_classifier': direction['reason'],
            'source_event': ev.get('type', z.get('anchor_event_type', '')),
            'source_event_idx': ci,
            'signal_index': ci,
            'broken_swing_idx': int(ev.get('broken_swing_idx', z.get('broken_swing_idx', -1))),
            'broken_swing_price': round(f(ev.get('broken_swing_price', z.get('broken_swing_price', 0))), 4),
            'zone_idx': zi,
            'zone_date': z.get('date', dt(klines[zi])),
            'conf_index': ci,
            'confirm_date': dt(klines[ci]),
            'ssl_sweep_idx': int(sweep['idx']),
            'ssl_sweep_date': sweep['date'],
            'ssl_ref_idx': int(sweep['ref_idx']),
            'ssl_ref_price': round(f(sweep['ref_price']), 4),
            'ssl_sweep_low': round(f(sweep['low']), 4),
            'ssl_sweep_depth_pct': round(f(sweep['depth_pct']), 3),
            'impulse_low': round(impulse_low, 4),
            'impulse_high': round(impulse_high, 4),
            'discount_ceiling': round(discount_ceiling, 4),
            'retrace_index': retrace_idx,
            'entry_index': entry_idx,
            'entry_date': dt(klines[entry_idx]),
            'select_date': dt(klines[entry_idx]),
            'pick_date': dt(klines[entry_idx]),
            'join_date': dt(klines[entry_idx]),
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
            'cost_line': round((zl + zh) / 2, 3),
            'atr': round(a, 4),
            'atr_pct': round(a / entry_price * 100, 3),
            'volatility_pct': round(a / entry_price * 100, 3),
            'retrace_rank': rank_at_confirm,
            'v59_setup_family': 'V68_SSL_CHOCH_OB_DISCOUNT',
            'ctx_seq': f"SSL_SWEEP→{ev.get('type')}→OB_Bull→{conf_type}",
            'seq': f"SSL-CHOCH-OB-{conf_type}",
            'strict_semantic_expected': True,
        })
    return setups


def backtest(setups: List[Dict[str, Any]], klines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bars = normalize_klines(klines)
    out = []
    for st in setups:
        entry_idx = int(st['entry_index'])
        if entry_idx >= len(bars) - 2:
            continue
        entry, sl, tp = f(st['entry_price']), f(st['sl']), f(st['tp'])
        exit_idx = -1
        exit_price = 0.0
        reason = 'TIMEOUT'
        for j in range(entry_idx + 1, min(entry_idx + 60, len(bars))):
            if f(bars[j].get('l')) <= sl:
                exit_idx, exit_price, reason = j, sl, 'SL_HIT'
                break
            if f(bars[j].get('h')) >= tp:
                exit_idx, exit_price, reason = j, tp, 'TP_HIT'
                break
        if exit_idx < 0:
            exit_idx = min(entry_idx + 60, len(bars) - 1)
            exit_price = f(bars[exit_idx].get('c'))
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
        'entry_confirm_counts': dict(Counter(t.get('entry_confirm_type') for t in trades)),
        'fvg_role_counts': dict(Counter(t.get('fvg_role') for t in trades)),
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
                pick['pick_scope'] = 'ACTIVE_CANDIDATE' if pick['is_active_pick'] else 'HISTORICAL_V68_SIGNAL'
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
        'engine': 'V68_DIRECTION_CLASSIFIER_CANDIDATE',
        'scanned_symbols': scanned,
        'n_errors': len(errors),
        'errors_sample': errors[:20],
        'metrics': m,
        'thresholds': {'MIN_TRADES': MIN_TRADES, 'MIN_WR': MIN_WR, 'MAX_SL_RATE': MAX_SL_RATE, 'MIN_AVG_PNL': MIN_AVG_PNL},
        'architecture_checks': {
            'strict_registry_geometry_only': True,
            'fvg_retrace_standalone_blocked': True,
            'bos_continuation_standalone_blocked': True,
            'direction_classifier_required': True,
        },
        'effect_pass': effect_pass,
        'promotion_candidate': effect_pass,
        'rollback_to': None if effect_pass else 'V66_RECENT_REENTRY_RISK_OVERLAY',
    }
    for name, data in {
        'v68_trades.json': trades,
        'v68_picks.json': picks,
        'v68_report.json': report,
    }.items():
        (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
