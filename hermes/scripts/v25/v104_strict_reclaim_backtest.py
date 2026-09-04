#!/usr/bin/env python3
"""V104 strict reclaim-confirmed entry rebuild.

Purpose:
- Rebuild strategy rows from raw K-line data, not historical completed-trade artifacts.
- Enforce touch -> reclaim_confirm -> next-open entry, i.e. entry_idx > reclaim_idx.
- Split reversal and continuation pools before evaluating metrics.
- Emit full-market artifacts plus semantic/monthly/entry/SLTP gates.

This script is research/backtest only. It does not promote frontend/live routing.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path('/root/.hermes')
KLINE_DIR = ROOT / 'kline_cache'
OUT_DIR = ROOT / 'smc_opt_v104_strict_reclaim'
OUT_DIR.mkdir(parents=True, exist_ok=True)

ENGINE = 'V104_STRICT_RECLAIM_CONFIRMED'
START_DATE = '20230101'
MAX_HOLD = 60
FEE_PCT = 0.12
NET_SUCCESS_PCT = 0.8


def f(x: Any, default: float = 0.0) -> float:
    try:
        if x in (None, ''):
            return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def d(b: Dict[str, Any]) -> str:
    return str(b.get('t') or b.get('date') or b.get('day') or '')[:8]


def symbol_from_path(p: Path) -> str:
    stem = p.stem.replace('_daily_750', '').replace('_daily_300', '')
    return stem.replace('_SH', '.SH').replace('_SZ', '.SZ').replace('_BJ', '.BJ')


def atr(ks: List[Dict[str, Any]], idx: int, n: int = 14) -> float:
    trs = []
    for i in range(max(1, idx - n + 1), idx + 1):
        h, l, pc = f(ks[i].get('h')), f(ks[i].get('l')), f(ks[i - 1].get('c'))
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 0.0


def ma(vals: List[float], n: int) -> Optional[float]:
    return sum(vals[-n:]) / n if len(vals) >= n else None


def pct(a: float, b: float) -> float:
    return (a / b - 1) * 100 if b else 0.0


def is_sw_low(ks: List[Dict[str, Any]], i: int, L: int = 3, R: int = 3) -> bool:
    if i - L < 0 or i + R >= len(ks):
        return False
    lo = f(ks[i].get('l'))
    return all(f(ks[j].get('l')) > lo for j in range(i - L, i)) and all(f(ks[j].get('l')) >= lo for j in range(i + 1, i + R + 1))


def is_sw_high(ks: List[Dict[str, Any]], i: int, L: int = 3, R: int = 3) -> bool:
    if i - L < 0 or i + R >= len(ks):
        return False
    hi = f(ks[i].get('h'))
    return all(f(ks[j].get('h')) < hi for j in range(i - L, i)) and all(f(ks[j].get('h')) <= hi for j in range(i + 1, i + R + 1))


def swings_until(ks: List[Dict[str, Any]], upto: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    lows, highs = [], []
    last = min(upto - 3, len(ks) - 4)
    for i in range(3, max(3, last) + 1):
        if is_sw_low(ks, i):
            lows.append({'bar': i, 'price': f(ks[i].get('l'))})
        if is_sw_high(ks, i):
            highs.append({'bar': i, 'price': f(ks[i].get('h'))})
    return lows, highs


def confirmed_swings(ks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    lows, highs = [], []
    for i in range(3, len(ks) - 3):
        if is_sw_low(ks, i):
            lows.append({'bar': i, 'price': f(ks[i].get('l'))})
        if is_sw_high(ks, i):
            highs.append({'bar': i, 'price': f(ks[i].get('h'))})
    return lows, highs


def trend_context(ks: List[Dict[str, Any]], idx: int) -> Dict[str, Any]:
    closes = [f(b.get('c')) for b in ks[:idx + 1]]
    c = closes[-1]
    m20, m60 = ma(closes, 20), ma(closes, 60)
    ret20 = pct(c, closes[-21]) if len(closes) > 21 else 0.0
    ret60 = pct(c, closes[-61]) if len(closes) > 61 else 0.0
    hi60 = max(f(b.get('h')) for b in ks[max(0, idx - 60):idx + 1])
    lo60 = min(f(b.get('l')) for b in ks[max(0, idx - 60):idx + 1])
    pos60 = (c - lo60) / max(hi60 - lo60, 1e-9) * 100
    if m20 and m60 and c > m20 > m60 and ret20 > 0:
        state = 'TREND_UP'
    elif m20 and m60 and c < m20 < m60 and ret20 < 0:
        state = 'TREND_DOWN'
    elif ret60 < -8:
        state = 'DOWN_60'
    elif ret20 > 8 and pos60 > 85:
        state = 'EXTENDED_UP'
    else:
        state = 'RANGE_TRANSITION'
    return {
        'trend_state': state,
        'ret20': round(ret20, 3),
        'ret60': round(ret60, 3),
        'pos60': round(pos60, 3),
        'above_ma20': bool(m20 and c > m20),
        'above_ma60': bool(m60 and c > m60),
    }


def find_ssl_sweeps(ks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out, lows = [], []
    for i in range(8, len(ks) - MAX_HOLD - 5):
        cand = i - 3
        if cand >= 3 and is_sw_low(ks, cand):
            lows.append({'bar': cand, 'price': f(ks[cand].get('l'))})
        recent = [x for x in lows if 3 <= i - x['bar'] <= 60]
        if not recent:
            continue
        lo, cl, op, a = f(ks[i].get('l')), f(ks[i].get('c')), f(ks[i].get('o')), atr(ks, i)
        target = min(recent, key=lambda x: (abs(lo - x['price']) / max(x['price'], 1e-9), i - x['bar']))
        pierce = target['price'] - lo
        if pierce >= max(a * 0.05, target['price'] * 0.0015) and cl > target['price'] and cl > op:
            out.append({'bar': i, 'liq_price': target['price'], 'sweep_low': lo, 'pierce_atr': pierce / max(a, 1e-9)})
    return out


def find_bull_bos(ks: List[Dict[str, Any]], highs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    hi_pos = 0
    active: List[Dict[str, Any]] = []
    for i in range(80, len(ks) - MAX_HOLD - 5):
        while hi_pos < len(highs) and highs[hi_pos]['bar'] <= i - 3:
            active.append(highs[hi_pos])
            hi_pos += 1
        while active and i - active[0]['bar'] > 80:
            active.pop(0)
        recent = [h for h in active if i - h['bar'] >= 5]
        if not recent:
            continue
        sh = recent[-1]
        op, cl, a = f(ks[i].get('o')), f(ks[i].get('c')), atr(ks, i)
        if cl > sh['price'] and cl > op and (cl - op) >= a * 0.35:
            out.append({'bar': i, 'broken_high': sh['price'], 'broken_high_bar': sh['bar'], 'disp_atr': (cl - op) / max(a, 1e-9)})
    return out


def displacement_after_sweep(ks: List[Dict[str, Any]], highs_all: List[Dict[str, Any]], lbar: int, max_wait: int = 12) -> Optional[Dict[str, Any]]:
    highs = [h for h in highs_all if h['bar'] <= lbar - 3]
    highs = [h for h in highs if 3 <= lbar - h['bar'] <= 80]
    if not highs:
        return None
    sh = highs[-1]
    for j in range(lbar + 1, min(len(ks) - MAX_HOLD - 4, lbar + max_wait + 1)):
        op, cl, a = f(ks[j].get('o')), f(ks[j].get('c')), atr(ks, j)
        if cl > sh['price'] and cl > op and (cl - op) >= a * 0.35:
            return {'bar': j, 'broken_high': sh['price'], 'broken_high_bar': sh['bar'], 'disp_atr': (cl - op) / max(a, 1e-9)}
    return None


def demand_fvg_near(ks: List[Dict[str, Any]], start_bar: int, event_bar: int) -> List[Dict[str, Any]]:
    out = []
    lo = max(start_bar + 2, event_bar - 2)
    hi = min(event_bar + 3, len(ks))
    for i in range(lo, hi):
        h0, l2, a = f(ks[i - 2].get('h')), f(ks[i].get('l')), atr(ks, i)
        if h0 > 0 and l2 > h0 and (l2 - h0) >= a * 0.20:
            out.append({'bar': i - 1, 'low': h0, 'high': l2, 'type': 'FVG_Demand'})
    return out


def reclaim_after_touch(ks: List[Dict[str, Any]], poi: Dict[str, Any], event_bar: int, max_wait: int = 20) -> Optional[Dict[str, Any]]:
    zl, zh = f(poi.get('low')), f(poi.get('high'))
    touch = None
    invalidated = False
    start = max(event_bar + 1, int(poi['bar']) + 1)
    stop = min(len(ks) - MAX_HOLD - 3, event_bar + max_wait)
    for i in range(start, stop + 1):
        op, cl, hi, lo = f(ks[i].get('o')), f(ks[i].get('c')), f(ks[i].get('h')), f(ks[i].get('l'))
        if touch is None:
            if lo <= zh and hi >= zl:
                touch = i
                if cl < zl:
                    invalidated = True
                    break
            continue
        if cl < zl:
            invalidated = True
            break
        # strict reclaim confirmation: enter next open only after a post-touch close above zone high.
        if cl > zh and cl > op:
            eidx = i + 1
            if eidx < len(ks):
                entry_price = f(ks[eidx].get('o'))
                if entry_price <= zh:
                    # Gap-down next open cancels this reclaim; wait for a fresh post-touch reclaim.
                    continue
                return {
                    'touch_idx': touch,
                    'reclaim_idx': i,
                    'entry_idx': eidx,
                    'entry_price': entry_price,
                    'entry_rule': 'NEXT_OPEN_AFTER_POST_TOUCH_ZONE_HIGH_RECLAIM',
                    'invalidated_before_reclaim': False,
                }
    if invalidated:
        return None
    return None


def recent_swing_low(ks: List[Dict[str, Any]], lows_all: List[Dict[str, Any]], idx: int, fallback: float) -> float:
    lows = [x for x in lows_all if x['bar'] <= idx - 3]
    candidates = [x for x in lows if 3 <= idx - x['bar'] <= 40]
    return min(candidates[-5:], key=lambda x: x['price'])['price'] if candidates else fallback


def simulate_exit(ks: List[Dict[str, Any]], eidx: int, ep: float, sl: float, tp1: float, tp2: float, tp3: float) -> Optional[Dict[str, Any]]:
    if not (0 < sl < ep < tp1):
        return None
    hit1 = False
    hit2 = False
    for j in range(eidx + 1, min(len(ks), eidx + MAX_HOLD + 1)):
        lo, hi, cl = f(ks[j].get('l')), f(ks[j].get('h')), f(ks[j].get('c'))
        if lo <= sl:
            return {'exit_idx': j, 'exit_date': d(ks[j]), 'exit_reason': 'SL_HIT', 'exit_price': round(sl, 4), 'hold_bars': j - eidx, 'pnl_pct': round(pct(sl, ep), 4), 'tp1_hit': hit1, 'tp2_hit': hit2}
        if tp3 and hi >= tp3:
            return {'exit_idx': j, 'exit_date': d(ks[j]), 'exit_reason': 'TP3_HIT', 'exit_price': round(tp3, 4), 'hold_bars': j - eidx, 'pnl_pct': round(pct(tp3, ep), 4), 'tp1_hit': True, 'tp2_hit': True}
        if tp2 and hi >= tp2:
            hit2 = True
        if tp1 and hi >= tp1:
            hit1 = True
            return {'exit_idx': j, 'exit_date': d(ks[j]), 'exit_reason': 'TP1_HIT', 'exit_price': round(tp1, 4), 'hold_bars': j - eidx, 'pnl_pct': round(pct(tp1, ep), 4), 'tp1_hit': True, 'tp2_hit': hit2}
    last = min(len(ks) - 1, eidx + MAX_HOLD)
    px = f(ks[last].get('c'))
    return {'exit_idx': last, 'exit_date': d(ks[last]), 'exit_reason': 'TIME_STOP', 'exit_price': round(px, 4), 'hold_bars': last - eidx, 'pnl_pct': round(pct(px, ep), 4), 'tp1_hit': hit1, 'tp2_hit': hit2}


def make_row(symbol: str, ks: List[Dict[str, Any]], lows_all: List[Dict[str, Any]], family: str, event: Dict[str, Any], poi: Dict[str, Any], ent: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    eidx, ep = int(ent['entry_idx']), f(ent['entry_price'])
    if eidx >= len(ks) - 2 or ep <= 0 or d(ks[eidx]) < START_DATE:
        return None
    tr = trend_context(ks, eidx)
    if tr['trend_state'] in ('TREND_DOWN', 'DOWN_60', 'EXTENDED_UP') or not tr['above_ma20']:
        return None
    zl, zh = f(poi['low']), f(poi['high'])
    chase_pct = pct(ep, zh)
    if chase_pct > 4.0:
        return None
    retrace_pct = max(0.0, min(100.0, (zh - f(ks[int(ent['touch_idx'])].get('l'))) / max(zh - zl, 1e-9) * 100))
    if not (20.0 <= retrace_pct < 120.0):
        return None
    fallback_low = min(f(event.get('sweep_low')), zl) if family == 'REVERSAL' else zl
    base_sl = recent_swing_low(ks, lows_all, eidx, fallback_low)
    a = atr(ks, eidx)
    sl = min(base_sl * 0.995, base_sl - a * 0.15)
    if not (0 < sl < ep):
        return None
    risk_pct = pct(ep, sl)
    if not (0.7 <= risk_pct <= 8.0):
        return None
    tp1 = ep + (ep - sl) * 1.0
    tp2 = ep + (ep - sl) * 5.0
    tp3 = ep + (ep - sl) * 8.0
    sim = simulate_exit(ks, eidx, ep, sl, tp1, tp2, tp3)
    if not sim:
        return None
    net = f(sim['pnl_pct']) - FEE_PCT
    event_bar = int(event['bar'])
    poi_bar = int(poi['bar'])
    reclaim_idx = int(ent['reclaim_idx'])
    touch_idx = int(ent['touch_idx'])
    source_atr = atr(ks, min(max(poi_bar + 1, 1), len(ks) - 1))
    mid = ks[poi_bar] if 0 <= poi_bar < len(ks) else {}
    row = {
        'symbol': symbol,
        'engine': ENGINE,
        'family': family,
        'combo': 'REVERSAL_SSL_CHOCH_FVG_RECLAIM' if family == 'REVERSAL' else 'CONTINUATION_BOS_FVG_RETEST_RECLAIM',
        'sequence': ('SSL_SWEEP -> BULLISH_DISPLACEMENT/BOS -> DEMAND_FVG_TOUCH -> ZONE_HIGH_RECLAIM -> NEXT_OPEN_ENTRY' if family == 'REVERSAL' else 'BULLISH_BOS -> DEMAND_FVG_RETEST -> ZONE_HIGH_RECLAIM -> NEXT_OPEN_ENTRY'),
        'entry_model': 'STRICT_RECLAIM_NEXT_OPEN',
        'entry_semantic': 'POST_RECLAIM_NEXT_OPEN_CONFIRMED',
        'source_event_idx': event_bar,
        'event_idx': event_bar,
        'zone_idx': int(poi['bar']),
        'touch_idx': touch_idx,
        'reclaim_idx': reclaim_idx,
        'entry_idx': eidx,
        'source_event_date': d(ks[event_bar]),
        'event_date': d(ks[event_bar]),
        'zone_date': d(ks[int(poi['bar'])]),
        'touch_date': d(ks[touch_idx]),
        'reclaim_date': d(ks[reclaim_idx]),
        'entry_date': d(ks[eidx]),
        'pick_date': d(ks[eidx]),
        'join_date': d(ks[eidx]),
        'zone_type': 'FVG_Demand',
        'signal_type': 'FVG_Demand',
        'zone_low': round(zl, 4),
        'zone_high': round(zh, 4),
        'entry_price': round(ep, 4),
        'price': round(ep, 4),
        'smart_money_cost': round(ep, 4),
        'cost_line': round(ep, 4),
        'sl': round(sl, 4),
        'tp1': round(tp1, 4),
        'tp2': round(tp2, 4),
        'tp3': round(tp3, 4),
        'risk_pct': round(risk_pct, 3),
        'volatility_pct': round(risk_pct, 3),
        'tp1_rr': 1.0,
        'tp2_rr': 5.0,
        'tp3_rr': 8.0,
        'retrace_pct': round(retrace_pct, 2),
        'chase_pct': round(chase_pct, 3),
        'zone_width_pct': round((zh - zl) * 100.0 / zl, 4) if zl else 0.0,
        'zone_width_atr': round((zh - zl) / source_atr, 4) if source_atr else 0.0,
        'fvg_mid_body_atr': round((f(mid.get('c')) - f(mid.get('o'))) / source_atr, 4) if source_atr else 0.0,
        'fvg_mid_range_atr': round((f(mid.get('h')) - f(mid.get('l'))) / source_atr, 4) if source_atr else 0.0,
        'fvg_mid_bull': f(mid.get('c')) > f(mid.get('o')),
        'v116_shadow_mode': True,
        'disp_atr': round(f(event.get('disp_atr')), 3),
        'pierce_atr': round(f(event.get('pierce_atr')), 3),
        'broken_high': round(f(event.get('broken_high')), 4),
        'net_pnl_pct': round(net, 4),
        'net_success': net >= NET_SUCCESS_PCT,
        'fee_pct': FEE_PCT,
        **tr,
        **sim,
    }
    row['source_label'] = fvg_source_label(row)
    row['v116_gate_reason'] = v116_gate_reason(row)
    row['v116_shadow_action'] = 'DOWNGRADE_ONLY' if row['v116_gate_reason'] else 'KEEP'
    return row


def rows_for(symbol: str, ks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows, used = [], set()
    lows_all, highs_all = confirmed_swings(ks)
    for sweep in find_ssl_sweeps(ks):
        disp = displacement_after_sweep(ks, highs_all, int(sweep['bar']))
        if not disp or f(disp.get('disp_atr')) < 0.8:
            continue
        event = {**sweep, **disp}
        for poi in demand_fvg_near(ks, int(sweep['bar']), int(disp['bar'])):
            ent = reclaim_after_touch(ks, poi, int(disp['bar']))
            if not ent:
                continue
            key = ('REVERSAL', ent['entry_idx'], poi['bar'])
            if key in used:
                continue
            used.add(key)
            row = make_row(symbol, ks, lows_all, 'REVERSAL', event, poi, ent)
            if row:
                rows.append(row)
    for bos in find_bull_bos(ks, highs_all):
        if f(bos.get('disp_atr')) < 0.8:
            continue
        for poi in demand_fvg_near(ks, int(bos['broken_high_bar']), int(bos['bar'])):
            ent = reclaim_after_touch(ks, poi, int(bos['bar']))
            if not ent:
                continue
            key = ('CONTINUATION', ent['entry_idx'], poi['bar'])
            if key in used:
                continue
            used.add(key)
            row = make_row(symbol, ks, lows_all, 'CONTINUATION', bos, poi, ent)
            if row:
                rows.append(row)
    return rows


def replay_file(path: Path) -> List[Dict[str, Any]]:
    try:
        ks = json.loads(path.read_text())
    except Exception:
        return []
    if not isinstance(ks, list) or len(ks) < 180:
        return []
    for b in ks:
        for k in ('o', 'h', 'l', 'c', 'v'):
            if k in b:
                b[k] = f(b[k])
    return rows_for(symbol_from_path(path), ks)


def metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {'n': 0}
    n = len(rows)
    wins = [r for r in rows if f(r.get('net_pnl_pct')) >= NET_SUCCESS_PCT]
    gross_wins = [r for r in rows if f(r.get('pnl_pct')) > 0]
    sl = [r for r in rows if r.get('exit_reason') == 'SL_HIT']
    return {
        'n': n,
        'net_wr_ge_0_8': round(len(wins) / n * 100, 2),
        'gross_wr_gt_0': round(len(gross_wins) / n * 100, 2),
        'sl_rate': round(len(sl) / n * 100, 2),
        'avg_net_pnl': round(sum(f(r.get('net_pnl_pct')) for r in rows) / n, 4),
        'median_net_pnl': round(sorted(f(r.get('net_pnl_pct')) for r in rows)[n // 2], 4),
        'cum_net_pnl': round(sum(f(r.get('net_pnl_pct')) for r in rows), 4),
        'avg_risk_pct': round(sum(f(r.get('risk_pct')) for r in rows) / n, 4),
        'avg_hold_bars': round(sum(f(r.get('hold_bars')) for r in rows) / n, 2),
    }


def fvg_source_label(row: Dict[str, Any]) -> str:
    full_retrace = f(row.get('retrace_pct')) >= 95.0
    strong_mid = f(row.get('fvg_mid_body_atr')) >= 0.65
    demand_retest = (not full_retrace) and f(row.get('fvg_mid_body_atr')) >= 0.35
    if demand_retest:
        return 'TRUE_DEMAND_RETEST_CANDIDATE'
    if full_retrace and strong_mid:
        return 'STRONG_IMBALANCE_FULL_RETRACE'
    if full_retrace and not strong_mid and row.get('family') == 'CONTINUATION':
        return 'WEAK_CONTINUATION_FULL_RETRACE_FVG'
    return 'WEAK_DISPLACEMENT_OTHER'


def v116_gate_reason(row: Dict[str, Any]) -> str:
    if (
        row.get('family') == 'CONTINUATION'
        and f(row.get('retrace_pct')) >= 95.0
        and f(row.get('fvg_mid_body_atr')) < 0.65
    ):
        return 'WEAK_CONTINUATION_FULL_RETRACE_FVG_SHADOW_DOWNGRADE'
    return ''


def bucket(rows: List[Dict[str, Any]], fn) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[str(fn(r))].append(r)
    return {k: metrics(v) for k, v in sorted(groups.items())}


def semantic_audit(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    fails = []
    for r in rows:
        issues = []
        if not (int(r['source_event_idx']) < int(r['touch_idx']) <= int(r['reclaim_idx']) < int(r['entry_idx'])):
            issues.append('event_touch_reclaim_entry_order')
        if not (int(r['zone_idx']) <= int(r['touch_idx'])):
            issues.append('zone_after_touch')
        if int(r.get('exit_idx', -1)) <= int(r.get('entry_idx', 10**9)):
            issues.append('t_plus_1_exit')
        if r.get('entry_date') == r.get('exit_date'):
            issues.append('same_day_exit')
        if f(r.get('entry_price')) <= f(r.get('zone_high')) and r.get('entry_model') == 'STRICT_RECLAIM_NEXT_OPEN':
            issues.append('entry_not_above_reclaim_zone_high')
        for k in ('symbol', 'entry_date', 'pick_date', 'join_date', 'zone_type', 'zone_low', 'zone_high', 'cost_line', 'smart_money_cost', 'volatility_pct', 'entry_price', 'sl', 'tp1', 'tp2', 'tp3'):
            if r.get(k) in (None, '', 0, 0.0):
                issues.append('missing_' + k)
        for k in ('family', 'retrace_pct', 'fvg_mid_body_atr', 'source_label', 'v116_shadow_action'):
            if r.get(k) in (None, ''):
                issues.append('missing_' + k)
        if issues:
            fails.append({'symbol': r.get('symbol'), 'entry_date': r.get('entry_date'), 'family': r.get('family'), 'issues': issues})
    c = Counter(i for x in fails for i in x['issues'])
    return {
        'n': len(rows),
        'fail_count': len(fails),
        'issue_counts': dict(c),
        'entry_before_reclaim': sum(int(r['entry_idx']) <= int(r['reclaim_idx']) for r in rows),
        'same_day_exit': sum(r.get('entry_date') == r.get('exit_date') for r in rows),
        't_plus_1_exit_fail': sum(int(r.get('exit_idx', -1)) <= int(r.get('entry_idx', 10**9)) for r in rows),
        'sample_fails': fails[:30],
    }


def interval_audit(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    def dist(vals: List[int]) -> Dict[str, Any]:
        if not vals:
            return {'n': 0}
        xs = sorted(vals)
        return {'n': len(xs), 'min': xs[0], 'p25': xs[len(xs)//4], 'median': xs[len(xs)//2], 'p75': xs[len(xs)*3//4], 'max': xs[-1], 'neg_count': sum(v < 0 for v in xs)}
    return {
        'event_to_touch': dist([int(r['touch_idx']) - int(r['source_event_idx']) for r in rows]),
        'touch_to_reclaim': dist([int(r['reclaim_idx']) - int(r['touch_idx']) for r in rows]),
        'reclaim_to_entry': dist([int(r['entry_idx']) - int(r['reclaim_idx']) for r in rows]),
        'entry_to_exit': dist([int(r['exit_idx']) - int(r['entry_idx']) for r in rows]),
    }


def month_audit(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by = bucket(rows, lambda r: str(r.get('entry_date'))[:6])
    anomalies = {}
    for m, s in by.items():
        if s['n'] < 5 or s.get('net_wr_ge_0_8', 0) < 70 or s.get('sl_rate', 0) > 25:
            anomalies[m] = {**s, 'reason': 'LOW_SAMPLE_OR_WEAK_MONTH'}
    return {'months': by, 'anomalies': anomalies, 'stable_months_ge5_wr70_sl25': len(by) - len(anomalies), 'total_months': len(by)}


def assign_pick_scope(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    for r in sorted(rows, key=lambda x: (x.get('entry_date', ''), x.get('symbol', ''))):
        latest[r['symbol']] = r
    picks = sorted(latest.values(), key=lambda x: (x.get('entry_date', ''), x.get('symbol', '')), reverse=True)
    for p in picks:
        x = dict(p)
        p.clear(); p.update(x)
        p['source'] = ENGINE
        p['pick_scope'] = 'ACTIVE_CANDIDATE' if p.get('entry_date', '') >= '20260601' else 'WATCH_ONLY'
        p['is_active_pick'] = bool(p['pick_scope'] == 'ACTIVE_CANDIDATE')
        p['status'] = p['pick_scope']
        p['reason'] = 'V104 strict reclaim-confirmed backtest artifact; not production-promoted.'
    return picks[:300]


def main() -> None:
    files = sorted(KLINE_DIR.glob('*_daily_750.json'))
    all_rows: List[Dict[str, Any]] = []
    print(json.dumps({'event': 'start', 'engine': ENGINE, 'files': len(files), 'start_date': START_DATE}, ensure_ascii=False), flush=True)
    for i, path in enumerate(files, 1):
        all_rows.extend(replay_file(path))
        if i % 500 == 0:
            print(json.dumps({'event': 'progress', 'files_done': i, 'rows': len(all_rows)}, ensure_ascii=False), flush=True)
    all_rows.sort(key=lambda r: (r.get('entry_date', ''), r.get('symbol', ''), r.get('family', '')))
    picks = assign_pick_scope(all_rows)
    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': ENGINE,
        'source': 'raw_kline_cache_daily_750',
        'start_date': START_DATE,
        'scanned_symbols': len(files),
        'metrics': metrics(all_rows),
        'by_family': bucket(all_rows, lambda r: r.get('family')),
        'by_combo': bucket(all_rows, lambda r: r.get('combo')),
        'by_exit': bucket(all_rows, lambda r: r.get('exit_reason')),
        'by_trend': bucket(all_rows, lambda r: r.get('trend_state')),
        'entry_position': bucket(all_rows, lambda r: '<=1%chase' if f(r.get('chase_pct')) <= 1 else ('1-2%chase' if f(r.get('chase_pct')) <= 2 else '2-4%chase')),
        'sltp_audit': {
            'risk_bins': bucket(all_rows, lambda r: '<=1%' if f(r.get('risk_pct')) <= 1 else ('1-2%' if f(r.get('risk_pct')) <= 2 else ('2-4%' if f(r.get('risk_pct')) <= 4 else '>4%'))),
            'tp_contract': {'tp1_rr': 1.0, 'tp2_rr': 5.0, 'tp3_rr': 8.0, 'structure_based_sl': True},
        },
        'semantic_audit': semantic_audit(all_rows),
        'interval_audit': interval_audit(all_rows),
        'monthly_audit': month_audit(all_rows),
        'active_pick_total': sum(1 for p in picks if p.get('pick_scope') == 'ACTIVE_CANDIDATE'),
        'watch_only_pick_total': sum(1 for p in picks if p.get('pick_scope') == 'WATCH_ONLY'),
    }
    sem = report['semantic_audit']
    m = report['metrics']
    month = report['monthly_audit']
    report['release_gate'] = {
        'pass': bool(m.get('n', 0) >= 100 and m.get('net_wr_ge_0_8', 0) >= 70 and sem.get('fail_count') == 0 and month.get('stable_months_ge5_wr70_sl25', 0) >= 12),
        'checks': {
            'sample_n_ge_100': m.get('n', 0) >= 100,
            'net_wr_ge_70': m.get('net_wr_ge_0_8', 0) >= 70,
            'semantic_fail_zero': sem.get('fail_count') == 0,
            'entry_before_reclaim_zero': sem.get('entry_before_reclaim') == 0,
            'same_day_exit_zero': sem.get('same_day_exit') == 0,
            'stable_months_ge_12': month.get('stable_months_ge5_wr70_sl25', 0) >= 12,
        },
        'decision': 'PROMOTABLE_CANDIDATE_PENDING_FRONTEND_CONTRACT' if (m.get('n', 0) >= 100 and m.get('net_wr_ge_0_8', 0) >= 70 and sem.get('fail_count') == 0 and month.get('stable_months_ge5_wr70_sl25', 0) >= 12) else 'RESEARCH_ONLY_NOT_PROMOTED',
    }
    (OUT_DIR / 'v104_trades.json').write_text(json.dumps(all_rows, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v104_picks.json').write_text(json.dumps(picks, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v104_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'metrics': report['metrics'], 'by_family': report['by_family'], 'semantic_audit': report['semantic_audit'], 'monthly_summary': {k: report['monthly_audit'][k] for k in ('total_months', 'stable_months_ge5_wr70_sl25')}, 'release_gate': report['release_gate'], 'out': str(OUT_DIR)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
