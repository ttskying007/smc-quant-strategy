#!/usr/bin/env python3
"""V69 matrix audit: one unique L→D setup, real fill entries, SL/TP matrix.

Isolated research script. It does NOT touch production/frontend files.

Contract from Lei:
1) one setup only, no duplicate RR samples in setup generation
2) FVG_Demand only for candidate; OB stays observation only
3) compare reclaim_close / zone_high / zone_mid real-fill entries
4) compare current SL / sweep_low SL / swing_low SL
5) compare RR0.8 / RR1.0 / BSL target / hybrid TP
6) full market 4655 daily-750 cache
7) output complete tables by signal, entry, SL, TP, SL reason, hold days, retrace depth
8) do not promote unless it crosses gate after full audit
"""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT_DIR = Path('/root/.hermes/smc_opt_v69_matrix')
OUT_DIR.mkdir(parents=True, exist_ok=True)
TRADES_OUT = OUT_DIR / 'v69_matrix_trades.json'
SETUPS_OUT = OUT_DIR / 'v69_unique_setups.json'
REPORT_OUT = OUT_DIR / 'v69_matrix_report.json'
MD_OUT = OUT_DIR / 'v69_matrix_report.md'
MAX_HOLD = 60
PROMOTE_WR = 90.0
PROMOTE_MIN_N = 100


def f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def d(b: Dict[str, Any]) -> str:
    return str(b.get('t') or b.get('date') or '')[:8]


def atr(ks: List[Dict[str, Any]], idx: int, n: int = 14) -> float:
    trs: List[float] = []
    for i in range(max(1, idx - n + 1), idx + 1):
        h, l, pc = f(ks[i].get('h')), f(ks[i].get('l')), f(ks[i - 1].get('c'))
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 0.0


def is_swing_low(ks: List[Dict[str, Any]], i: int, left: int = 3, right: int = 3) -> bool:
    if i - left < 0 or i + right >= len(ks):
        return False
    lo = f(ks[i].get('l'))
    return all(f(ks[j].get('l')) > lo for j in range(i - left, i)) and all(f(ks[j].get('l')) >= lo for j in range(i + 1, i + right + 1))


def is_swing_high(ks: List[Dict[str, Any]], i: int, left: int = 3, right: int = 3) -> bool:
    if i - left < 0 or i + right >= len(ks):
        return False
    hi = f(ks[i].get('h'))
    return all(f(ks[j].get('h')) < hi for j in range(i - left, i)) and all(f(ks[j].get('h')) <= hi for j in range(i + 1, i + right + 1))


def swings_until(ks: List[Dict[str, Any]], upto: int, left: int = 3, right: int = 3) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    lows: List[Dict[str, Any]] = []
    highs: List[Dict[str, Any]] = []
    end = max(left, upto - right)
    for i in range(left, end + 1):
        if is_swing_low(ks, i, left, right):
            lows.append({'bar': i, 'price': f(ks[i].get('l'))})
        if is_swing_high(ks, i, left, right):
            highs.append({'bar': i, 'price': f(ks[i].get('h'))})
    return lows, highs


def find_ssl_sweeps(ks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    lows: List[Dict[str, Any]] = []
    for i in range(8, len(ks) - MAX_HOLD - 2):
        cand = i - 3
        if cand >= 3 and is_swing_low(ks, cand, 3, 3):
            lows.append({'bar': cand, 'price': f(ks[cand].get('l'))})
        recent = [x for x in lows if 3 <= i - x['bar'] <= 60]
        if not recent:
            continue
        lo, cl, op = f(ks[i].get('l')), f(ks[i].get('c')), f(ks[i].get('o'))
        a = atr(ks, i)
        target = min(recent, key=lambda x: (abs(lo - x['price']) / max(x['price'], 1e-9), i - x['bar']))
        pierce = target['price'] - lo
        reclaim = cl > target['price'] and cl > op
        if pierce >= max(a * 0.05, target['price'] * 0.0015) and reclaim:
            wick = (min(op, cl) - lo) / max(f(ks[i].get('h')) - lo, 1e-9)
            out.append({
                'bar': i,
                'liq_bar': target['bar'],
                'liq_price': target['price'],
                'sweep_low': lo,
                'pierce_atr': pierce / max(a, 1e-9),
                'wick_ratio': wick,
            })
    return out


def find_displacement_after(ks: List[Dict[str, Any]], lbar: int, max_wait: int = 12) -> Optional[Dict[str, Any]]:
    _, highs = swings_until(ks, lbar, 3, 3)
    highs = [h for h in highs if 3 <= lbar - h['bar'] <= 80]
    if not highs:
        return None
    sh = highs[-1]
    for j in range(lbar + 1, min(len(ks) - MAX_HOLD - 1, lbar + max_wait + 1)):
        op, cl = f(ks[j].get('o')), f(ks[j].get('c'))
        body = cl - op
        a = atr(ks, j)
        if cl > sh['price'] and body > 0 and body >= a * 0.35:
            return {'bar': j, 'swing_high_bar': sh['bar'], 'swing_high': sh['price'], 'disp_atr': body / max(a, 1e-9)}
    return None


def demand_pois(ks: List[Dict[str, Any]], lbar: int, dbar: int) -> List[Dict[str, Any]]:
    pois: List[Dict[str, Any]] = []
    for j in range(dbar - 1, max(lbar - 1, dbar - 8), -1):
        op, cl = f(ks[j].get('o')), f(ks[j].get('c'))
        if cl < op:
            pois.append({'type': 'OB_Demand', 'bar': j, 'low': f(ks[j].get('l')), 'high': max(op, cl), 'origin': 'last_down_before_displacement'})
            break
    for i in range(max(lbar + 2, dbar - 2), min(dbar + 3, len(ks))):
        h0, l2 = f(ks[i - 2].get('h')), f(ks[i].get('l'))
        if h0 > 0 and l2 > h0 and (l2 - h0) >= atr(ks, i) * 0.20:
            pois.append({'type': 'FVG_Demand', 'bar': i - 1, 'low': h0, 'high': l2, 'origin': 'displacement_imbalance'})
    return pois


def first_touch_idx(ks: List[Dict[str, Any]], poi: Dict[str, Any], dbar: int, max_wait: int = 12) -> Optional[int]:
    zl, zh = poi['low'], poi['high']
    for e in range(max(dbar + 1, poi.get('bar', dbar) + 1), min(len(ks) - MAX_HOLD - 1, dbar + max_wait + 1)):
        lo, hi, cl = f(ks[e].get('l')), f(ks[e].get('h')), f(ks[e].get('c'))
        if lo <= zh and hi >= zl:
            if cl < zl:
                return None
            return e
    return None


def find_reclaim_idx(ks: List[Dict[str, Any]], poi: Dict[str, Any], dbar: int, max_wait: int = 12) -> Optional[int]:
    zl, zh = poi['low'], poi['high']
    for e in range(max(dbar + 1, poi.get('bar', dbar) + 1), min(len(ks) - MAX_HOLD - 1, dbar + max_wait + 1)):
        op, cl, hi, lo = f(ks[e].get('o')), f(ks[e].get('c')), f(ks[e].get('h')), f(ks[e].get('l'))
        if not (lo <= zh and hi >= zl):
            continue
        if cl < zl:
            return None
        reclaim = cl >= max(zl, (zl + zh) / 2) and cl > op
        pin = (min(op, cl) - lo) >= abs(cl - op) * 1.3 and cl >= zl
        if reclaim or pin:
            return e
    return None


def nearest_bsl_target(ks: List[Dict[str, Any]], upto: int, entry: float) -> Optional[Dict[str, Any]]:
    _, highs = swings_until(ks, upto, 3, 3)
    candidates = [h for h in highs if h['price'] > entry * 1.002 and 5 <= upto - h['bar'] <= 120]
    if not candidates:
        return None
    nearest = min(candidates, key=lambda h: h['price'])
    return {'bar': nearest['bar'], 'price': nearest['price']}


def recent_swing_low(ks: List[Dict[str, Any]], upto: int, fallback: float) -> Dict[str, Any]:
    lows, _ = swings_until(ks, upto, 3, 3)
    candidates = [x for x in lows if 3 <= upto - x['bar'] <= 40]
    if not candidates:
        return {'bar': None, 'price': fallback}
    return min(candidates[-5:], key=lambda x: x['price'])


def unique_setup_key(L: Dict[str, Any], D: Dict[str, Any], poi: Dict[str, Any]) -> Tuple[int, int, int, str]:
    return (L['bar'], D['bar'], poi['bar'], poi['type'])


def setup_quality_key(setup: Dict[str, Any]) -> Tuple[int, float, float, float]:
    # Unique setup selection priority: FVG candidate first; OB is observation only.
    priority = {'FVG_Demand': 0, 'OB_Demand': 1, 'OB_FVG_Demand': 2}
    return (
        priority.get(setup['zone_type'], 9),
        -f(setup.get('disp_atr')),
        -f(setup.get('pierce_atr')),
        abs(f(setup['zone_high']) - f(setup['entry_probe_price'])) / max(f(setup['entry_probe_price']), 1e-9),
    )


def build_unique_setups(symbol: str, ks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    raw: List[Dict[str, Any]] = []
    for L in find_ssl_sweeps(ks):
        D = find_displacement_after(ks, L['bar'])
        if not D:
            continue
        for poi in demand_pois(ks, L['bar'], D['bar']):
            probe = first_touch_idx(ks, poi, D['bar'])
            if probe is None:
                continue
            bsl = nearest_bsl_target(ks, probe, (poi['low'] + poi['high']) / 2)
            swl = recent_swing_low(ks, probe, min(L['sweep_low'], poi['low']))
            raw.append({
                'symbol': symbol,
                'setup_id': f"{symbol}:{L['bar']}:{D['bar']}:{poi['bar']}:{poi['type']}",
                'sequence': 'SSL_SWEEP -> BULL_DISPLACEMENT -> DEMAND_POI -> ENTRY_VARIANT',
                'liq_date': d(ks[L['bar']]),
                'confirm_date': d(ks[D['bar']]),
                'zone_date': d(ks[poi['bar']]),
                'liq_bar': L['bar'],
                'confirm_bar': D['bar'],
                'zone_bar': poi['bar'],
                'zone_type': poi['type'],
                'zone_low': round(poi['low'], 4),
                'zone_high': round(poi['high'], 4),
                'entry_probe_idx': probe,
                'entry_probe_date': d(ks[probe]),
                'entry_probe_price': round(f(ks[probe].get('c')), 4),
                'sweep_low': round(L['sweep_low'], 4),
                'liq_price': round(L['liq_price'], 4),
                'recent_swing_low': round(swl['price'], 4),
                'recent_swing_low_bar': swl['bar'],
                'bsl_price': round(bsl['price'], 4) if bsl else None,
                'bsl_bar': bsl['bar'] if bsl else None,
                'pierce_atr': round(L['pierce_atr'], 3),
                'disp_atr': round(D['disp_atr'], 3),
            })
    # Unique per L+D only. If both OB and FVG appear, keep FVG_Demand as candidate; OB remains visible in observation buckets if selected when no FVG exists.
    best: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for s in raw:
        k = (s['liq_bar'], s['confirm_bar'])
        if k not in best or setup_quality_key(s) < setup_quality_key(best[k]):
            best[k] = s
    return list(best.values())


def entry_variant(ks: List[Dict[str, Any]], setup: Dict[str, Any], kind: str) -> Optional[Dict[str, Any]]:
    zl, zh = f(setup['zone_low']), f(setup['zone_high'])
    start = max(int(setup['confirm_bar']) + 1, int(setup['zone_bar']) + 1)
    end = min(len(ks) - MAX_HOLD - 1, int(setup['confirm_bar']) + 12 + 1)
    if kind == 'reclaim_close':
        idx = find_reclaim_idx(ks, {'low': zl, 'high': zh, 'bar': setup['zone_bar']}, int(setup['confirm_bar']))
        if idx is None:
            return None
        return {'entry_idx': idx, 'entry_price': f(ks[idx].get('c')), 'entry_fill_rule': 'close_after_reclaim'}
    if kind == 'zone_high':
        px = zh
    elif kind == 'zone_mid':
        px = (zl + zh) / 2
    else:
        raise ValueError(kind)
    for idx in range(start, end):
        lo, hi, cl = f(ks[idx].get('l')), f(ks[idx].get('h')), f(ks[idx].get('c'))
        if lo <= px <= hi:
            if cl < zl:
                return None
            return {'entry_idx': idx, 'entry_price': px, 'entry_fill_rule': 'intraday_limit_fill'}
    return None


def sl_variant(ks: List[Dict[str, Any]], setup: Dict[str, Any], entry_idx: int, entry_price: float, kind: str) -> Optional[Dict[str, Any]]:
    zl = f(setup['zone_low'])
    a = atr(ks, entry_idx)
    if kind == 'current':
        sl = min(zl * 0.985, zl - a * 0.25)
        anchor = zl
        reason = 'zone_low_buffer'
    elif kind == 'sweep_low':
        anchor = f(setup['sweep_low'])
        sl = min(anchor * 0.995, anchor - a * 0.15)
        reason = 'sweep_low_buffer'
    elif kind == 'swing_low':
        anchor = f(setup['recent_swing_low'])
        sl = min(anchor * 0.995, anchor - a * 0.15)
        reason = 'recent_swing_low_buffer'
    else:
        raise ValueError(kind)
    if sl <= 0 or sl >= entry_price:
        return None
    return {'sl': sl, 'sl_anchor': anchor, 'sl_reason': reason, 'risk_pct': (entry_price / sl - 1) * 100}


def tp_variant(setup: Dict[str, Any], entry: float, sl: float, kind: str) -> Optional[Dict[str, Any]]:
    risk = entry - sl
    bsl = f(setup.get('bsl_price'), 0.0)
    if risk <= 0:
        return None
    if kind == 'rr0.8':
        tp = entry + risk * 0.8
        reason = 'fixed_rr_0.8'
    elif kind == 'rr1.0':
        tp = entry + risk * 1.0
        reason = 'fixed_rr_1.0'
    elif kind == 'bsl':
        if bsl <= entry:
            return None
        tp = bsl
        reason = 'nearest_bsl'
    elif kind == 'hybrid':
        rr1 = entry + risk * 1.0
        if bsl > entry:
            tp = min(bsl, rr1)
            reason = 'min_bsl_rr1'
        else:
            tp = rr1
            reason = 'rr1_no_bsl'
    else:
        raise ValueError(kind)
    if tp <= entry:
        return None
    return {'tp1': tp, 'tp_reason': reason, 'rr_realized': (tp - entry) / risk}


def simulate(ks: List[Dict[str, Any]], entry_idx: int, ep: float, sl: float, tp1: float) -> Optional[Dict[str, Any]]:
    if ep <= 0 or sl <= 0 or tp1 <= 0 or not (sl < ep < tp1):
        return None
    for j in range(entry_idx + 1, min(len(ks), entry_idx + MAX_HOLD + 1)):
        lo, hi = f(ks[j].get('l')), f(ks[j].get('h'))
        # Conservative same-day ambiguity: if both hit in one daily bar, count SL first.
        if lo <= sl:
            return {'exit_date': d(ks[j]), 'exit_reason': 'SL_HIT', 'exit_price': round(sl, 4), 'hold_bars': j - entry_idx, 'pnl_pct': round((sl / ep - 1) * 100, 4)}
        if hi >= tp1:
            return {'exit_date': d(ks[j]), 'exit_reason': 'TP1_HIT', 'exit_price': round(tp1, 4), 'hold_bars': j - entry_idx, 'pnl_pct': round((tp1 / ep - 1) * 100, 4)}
    stop_idx = entry_idx + MAX_HOLD
    if stop_idx < len(ks):
        px = f(ks[stop_idx].get('c'))
        return {'exit_date': d(ks[stop_idx]), 'exit_reason': 'TIME_STOP', 'exit_price': round(px, 4), 'hold_bars': MAX_HOLD, 'pnl_pct': round((px / ep - 1) * 100, 4)}
    return None


def retrace_pct(ks: List[Dict[str, Any]], setup: Dict[str, Any], entry_idx: int) -> float:
    zl, zh = f(setup['zone_low']), f(setup['zone_high'])
    lo = f(ks[entry_idx].get('l'))
    return max(0.0, min(100.0, (zh - lo) / max(zh - zl, 1e-9) * 100.0))


def run_matrix_for_setup(ks: List[Dict[str, Any]], setup: Dict[str, Any]) -> List[Dict[str, Any]]:
    trades: List[Dict[str, Any]] = []
    for entry_kind in ('reclaim_close', 'zone_high', 'zone_mid'):
        ev = entry_variant(ks, setup, entry_kind)
        if not ev:
            continue
        entry_idx, ep = ev['entry_idx'], ev['entry_price']
        for sl_kind in ('current', 'sweep_low', 'swing_low'):
            sv = sl_variant(ks, setup, entry_idx, ep, sl_kind)
            if not sv:
                continue
            for tp_kind in ('rr0.8', 'rr1.0', 'bsl', 'hybrid'):
                tv = tp_variant(setup, ep, sv['sl'], tp_kind)
                if not tv:
                    continue
                sim = simulate(ks, entry_idx, ep, sv['sl'], tv['tp1'])
                if not sim:
                    continue
                risk = sv['risk_pct']
                # Matrix outputs every realistic combo, but carries candidate eligibility flags for separate ranking.
                semantic_pass = int(setup['liq_bar']) < int(setup['confirm_bar']) <= int(setup['zone_bar']) < entry_idx
                tplus1_pass = str(sim['exit_date']) > d(ks[entry_idx])
                trades.append({
                    'symbol': setup['symbol'],
                    'engine': 'V69_MATRIX_UNIQUE_LD',
                    'setup_id': setup['setup_id'],
                    'zone_type': setup['zone_type'],
                    'candidate_signal_pass': setup['zone_type'] == 'FVG_Demand',
                    'entry_method': entry_kind,
                    'entry_fill_rule': ev['entry_fill_rule'],
                    'sl_method': sl_kind,
                    'sl_reason': sv['sl_reason'],
                    'tp_method': tp_kind,
                    'tp_reason': tv['tp_reason'],
                    'sequence': setup['sequence'],
                    'liq_date': setup['liq_date'], 'confirm_date': setup['confirm_date'], 'zone_date': setup['zone_date'], 'entry_date': d(ks[entry_idx]),
                    'liq_bar': setup['liq_bar'], 'confirm_bar': setup['confirm_bar'], 'zone_bar': setup['zone_bar'], 'entry_idx': entry_idx,
                    'zone_low': setup['zone_low'], 'zone_high': setup['zone_high'], 'entry_price': round(ep, 4),
                    'sl': round(sv['sl'], 4), 'tp1': round(tv['tp1'], 4), 'risk_pct': round(risk, 3), 'rr_realized': round(tv['rr_realized'], 3),
                    'retrace_pct': round(retrace_pct(ks, setup, entry_idx), 2),
                    'pierce_atr': setup['pierce_atr'], 'disp_atr': setup['disp_atr'],
                    'sweep_low': setup['sweep_low'], 'recent_swing_low': setup['recent_swing_low'], 'bsl_price': setup['bsl_price'],
                    'semantic_order_pass': bool(semantic_pass), 't_plus_1_pass': bool(tplus1_pass),
                    **sim,
                })
    return trades


def replay_file(kf: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    sym = kf.stem.replace('_daily_750', '')
    symbol = sym.replace('_SH', '.SH').replace('_SZ', '.SZ').replace('_BJ', '.BJ')
    try:
        ks = json.loads(kf.read_text())
    except Exception:
        return [], []
    if len(ks) < 180:
        return [], []
    for b in ks:
        for key in ('o', 'h', 'l', 'c', 'v'):
            if key in b:
                b[key] = f(b[key])
    setups = build_unique_setups(symbol, ks)
    trades: List[Dict[str, Any]] = []
    for setup in setups:
        trades.extend(run_matrix_for_setup(ks, setup))
    return setups, trades


def metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {'n': 0}
    pnls = [f(r.get('pnl_pct')) for r in rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    sl = [r for r in rows if r.get('exit_reason') == 'SL_HIT']
    tp = [r for r in rows if r.get('exit_reason') == 'TP1_HIT']
    holds = [int(f(r.get('hold_bars'))) for r in rows]
    return {
        'n': len(rows),
        'wr': round(len(wins) / len(rows) * 100, 2),
        'sl_rate': round(len(sl) / len(rows) * 100, 2),
        'tp_rate': round(len(tp) / len(rows) * 100, 2),
        'avg_pnl': round(statistics.mean(pnls), 4),
        'median_pnl': round(statistics.median(pnls), 4),
        'cum_pnl': round(sum(pnls), 2),
        'avg_win': round(statistics.mean(wins), 4) if wins else 0,
        'avg_loss': round(statistics.mean(losses), 4) if losses else 0,
        'payoff': round((statistics.mean(wins) / abs(statistics.mean(losses))), 3) if wins and losses else 0,
        'avg_hold': round(statistics.mean(holds), 2),
        'exit_counts': dict(Counter(r.get('exit_reason') for r in rows)),
    }


def bucket_name(field: str, row: Dict[str, Any]) -> str:
    if field == 'hold_bin':
        h = int(f(row.get('hold_bars')))
        return '01_1bar' if h <= 1 else ('02_2_3' if h <= 3 else ('03_4_7' if h <= 7 else ('04_8_15' if h <= 15 else '05_16_60')))
    if field == 'retrace_bin':
        r = f(row.get('retrace_pct'))
        return 'a_<30' if r < 30 else ('b_30_60' if r < 60 else ('c_60_90' if r < 90 else 'd_90_100'))
    if field == 'risk_bin':
        r = f(row.get('risk_pct'))
        return 'a_<2' if r < 2 else ('b_2_4' if r < 4 else ('c_4_6' if r < 6 else ('d_6_8' if r < 8 else 'e_8+')))
    if field == 'combo':
        return f"{row.get('zone_type')}|{row.get('entry_method')}|{row.get('sl_method')}|{row.get('tp_method')}"
    return str(row.get(field))


def bucket(rows: List[Dict[str, Any]], field: str) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[bucket_name(field, r)].append(r)
    return {k: metrics(v) for k, v in sorted(groups.items(), key=lambda kv: kv[0])}


def combo_ranking(rows: List[Dict[str, Any]], candidate_only: bool) -> List[Dict[str, Any]]:
    base = [r for r in rows if (not candidate_only or r.get('candidate_signal_pass'))]
    groups: Dict[Tuple[str, str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for r in base:
        groups[(r['zone_type'], r['entry_method'], r['sl_method'], r['tp_method'])].append(r)
    out = []
    for combo, vals in groups.items():
        m = metrics(vals)
        out.append({
            'zone_type': combo[0], 'entry_method': combo[1], 'sl_method': combo[2], 'tp_method': combo[3],
            'metrics': m,
            'promote_gate': m.get('n', 0) >= PROMOTE_MIN_N and m.get('wr', 0) >= PROMOTE_WR,
        })
    out.sort(key=lambda x: (x['promote_gate'], x['metrics'].get('wr', 0), x['metrics'].get('avg_pnl', -999), x['metrics'].get('n', 0)), reverse=True)
    return out


def audit(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    required = ['symbol', 'setup_id', 'zone_type', 'entry_method', 'sl_method', 'tp_method', 'liq_date', 'confirm_date', 'zone_date', 'entry_date', 'exit_date', 'entry_price', 'sl', 'tp1', 'pnl_pct']
    missing = 0
    sem = 0
    t1 = 0
    bad_price = 0
    duplicate_setup_per_combo = 0
    seen = set()
    for r in rows:
        if any(r.get(k) in (None, '') for k in required):
            missing += 1
        if not r.get('semantic_order_pass'):
            sem += 1
        if not r.get('t_plus_1_pass'):
            t1 += 1
        if not (f(r.get('sl')) < f(r.get('entry_price')) < f(r.get('tp1'))):
            bad_price += 1
        key = (r.get('setup_id'), r.get('entry_method'), r.get('sl_method'), r.get('tp_method'))
        if key in seen:
            duplicate_setup_per_combo += 1
        seen.add(key)
    return {
        'required_field_fail': missing,
        'semantic_order_fail': sem,
        't_plus_1_fail': t1,
        'bad_price_order_fail': bad_price,
        'duplicate_setup_per_combo_fail': duplicate_setup_per_combo,
        'pass': missing == sem == t1 == bad_price == duplicate_setup_per_combo == 0,
    }


def write_md(report: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append('# V69 Unique L→D Matrix Audit')
    lines.append('')
    lines.append(f"Generated: {report['generated_at']}")
    lines.append('')
    lines.append('## Base')
    b = report['base_metrics']
    lines.append(f"| scope | n | WR | avg | SL | TP | hold |")
    lines.append('|---|---:|---:|---:|---:|---:|---:|')
    lines.append(f"| all matrix | {b['n']} | {b['wr']} | {b['avg_pnl']} | {b['sl_rate']} | {b['tp_rate']} | {b['avg_hold']} |")
    c = report['candidate_fvg_metrics']
    lines.append(f"| FVG candidate only | {c['n']} | {c['wr']} | {c['avg_pnl']} | {c['sl_rate']} | {c['tp_rate']} | {c['avg_hold']} |")
    lines.append('')
    lines.append('## Top FVG Combos')
    lines.append('| rank | entry | SL | TP | n | WR | avg | SL rate | hold | promote |')
    lines.append('|---:|---|---|---|---:|---:|---:|---:|---:|---|')
    for i, item in enumerate(report['candidate_combo_top20'][:20], 1):
        m = item['metrics']
        lines.append(f"| {i} | {item['entry_method']} | {item['sl_method']} | {item['tp_method']} | {m['n']} | {m['wr']} | {m['avg_pnl']} | {m['sl_rate']} | {m['avg_hold']} | {item['promote_gate']} |")
    lines.append('')
    lines.append('## Audit')
    lines.append('| gate | value |')
    lines.append('|---|---:|')
    for k, v in report['audit'].items():
        lines.append(f'| {k} | {v} |')
    lines.append('')
    lines.append('## Decision')
    lines.append(report['decision'])
    MD_OUT.write_text('\n'.join(lines) + '\n')


def main() -> None:
    files = sorted(KLINE_DIR.glob('*_daily_750.json'))
    all_setups: List[Dict[str, Any]] = []
    all_trades: List[Dict[str, Any]] = []
    print(f"V69 matrix replay {len(files)} stocks {datetime.now():%H:%M:%S}", flush=True)
    for i, kf in enumerate(files, 1):
        setups, trades = replay_file(kf)
        all_setups.extend(setups)
        all_trades.extend(trades)
        if i % 250 == 0:
            print(f"  {i}/{len(files)} setups={len(all_setups)} trades={len(all_trades)}", flush=True)
    cand = [r for r in all_trades if r.get('candidate_signal_pass')]
    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'n_stocks': len(files),
        'n_unique_setups': len(all_setups),
        'n_fvg_setups': sum(1 for s in all_setups if s.get('zone_type') == 'FVG_Demand'),
        'n_ob_observation_setups': sum(1 for s in all_setups if s.get('zone_type') != 'FVG_Demand'),
        'base_metrics': metrics(all_trades),
        'candidate_fvg_metrics': metrics(cand),
        'audit': audit(all_trades),
        'buckets_all': {
            'signal': bucket(all_trades, 'zone_type'),
            'entry': bucket(all_trades, 'entry_method'),
            'sl': bucket(all_trades, 'sl_method'),
            'tp': bucket(all_trades, 'tp_method'),
            'sl_reason': bucket(all_trades, 'sl_reason'),
            'hold_bin': bucket(all_trades, 'hold_bin'),
            'retrace_bin': bucket(all_trades, 'retrace_bin'),
            'risk_bin': bucket(all_trades, 'risk_bin'),
            'exit_reason': bucket(all_trades, 'exit_reason'),
        },
        'buckets_fvg_candidate': {
            'entry': bucket(cand, 'entry_method'),
            'sl': bucket(cand, 'sl_method'),
            'tp': bucket(cand, 'tp_method'),
            'sl_reason': bucket(cand, 'sl_reason'),
            'hold_bin': bucket(cand, 'hold_bin'),
            'retrace_bin': bucket(cand, 'retrace_bin'),
            'risk_bin': bucket(cand, 'risk_bin'),
            'exit_reason': bucket(cand, 'exit_reason'),
        },
        'candidate_combo_top20': combo_ranking(all_trades, candidate_only=True)[:20],
        'ob_observation_combo_top20': combo_ranking([r for r in all_trades if not r.get('candidate_signal_pass')], candidate_only=False)[:20],
        'promotion_gate': {'min_n': PROMOTE_MIN_N, 'min_wr': PROMOTE_WR},
    }
    passing = [x for x in report['candidate_combo_top20'] if x['promote_gate']]
    report['decision'] = 'PROMOTION_ELIGIBLE_NEEDS_FRONTEND_SYNC' if passing and report['audit']['pass'] else 'NO_PROMOTION_V69_MATRIX_BELOW_90WR_OR_AUDIT_FAIL'
    SETUPS_OUT.write_text(json.dumps(all_setups, ensure_ascii=False, indent=2))
    TRADES_OUT.write_text(json.dumps(all_trades, ensure_ascii=False, indent=2))
    REPORT_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    write_md(report)
    print(json.dumps({
        'setups': len(all_setups),
        'trades': len(all_trades),
        'candidate_fvg': report['candidate_fvg_metrics'],
        'audit': report['audit'],
        'top5': report['candidate_combo_top20'][:5],
        'decision': report['decision'],
        'outputs': {'report': str(REPORT_OUT), 'trades': str(TRADES_OUT), 'setups': str(SETUPS_OUT), 'md': str(MD_OUT)},
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
