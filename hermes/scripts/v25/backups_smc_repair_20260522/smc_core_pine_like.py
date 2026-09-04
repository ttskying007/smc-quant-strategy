#!/usr/bin/env python3
"""
SMC Core Pine-like — V32A Signal Correctness Core
==================================================
Pine/LuxAlgo-faithful raw signal core for chart/audit use.

Goals:
- Replace noisy V27 raw markers with stateful, current-pivot-only structure.
- Keep CHOCH as base structure event; MSS is a qualified attribute, not a replacement.
- Sweep only once per liquidity level, one per direction per bar.
- OB only from valid structure events, active/mitigated state aware.
- Add EQH/EQL and Liquidity Void outputs that V27 never emitted.

This module intentionally does NOT optimize WR/RR. It is a signal-correctness core.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


DEFAULT_PROFILE = {
    'swing_len': 20,          # Pine/LuxAlgo swing structure scale; adaptive below
    'internal_len': 5,        # LuxAlgo internal structure default
    'eq_len': 3,
    'eq_threshold_atr': 0.10,
    'sweep_lookback': 80,
    'sweep_reclaim_atr': 0.05,
    'sweep_min_wick_ratio': 0.35,
    'ob_backscan': 10,
    'active_ob_max': 20,
    'fvg_min_gap_atr': 0.12,
    'fvg_auto_threshold': True,
    # BPR is deliberately conservative: A-share daily gaps create many raw FVGs,
    # so opposing FVG overlap must be close in time and wide enough vs ATR.
    'bpr_max_gap': 12,
    'bpr_min_width_atr': 0.25,
    'lv_min_range_atr': 1.6,
    'lv_min_body_ratio': 0.70,
}


def _f(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def _date(b):
    return str(b.get('t', b.get('date', '')))


def normalize_klines(klines: List[Dict]) -> List[Dict]:
    out = []
    for b in klines:
        nb = dict(b)
        for k in ('o', 'h', 'l', 'c', 'v'):
            nb[k] = _f(nb.get(k, 0.0))
        nb['t'] = _date(nb)
        out.append(nb)
    return out


def true_ranges(klines: List[Dict]) -> List[float]:
    trs = []
    prev_c = None
    for b in klines:
        h, l, c = b['h'], b['l'], b['c']
        if prev_c is None:
            tr = h - l
        else:
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(max(tr, 0.0))
        prev_c = c
    return trs


def rolling_atr(klines: List[Dict], period: int = 14) -> List[float]:
    trs = true_ranges(klines)
    atr = []
    s = 0.0
    for i, tr in enumerate(trs):
        s += tr
        if i >= period:
            s -= trs[i - period]
        denom = min(i + 1, period)
        atr.append(s / denom if denom else 0.0)
    return atr


def adaptive_profile(klines: List[Dict], timeframe: str = 'daily', override: Optional[Dict] = None) -> Dict:
    p = dict(DEFAULT_PROFILE)
    n = len(klines)
    if n >= 60:
        atr = rolling_atr(klines, 20)
        closes = [max(b['c'], 1e-9) for b in klines]
        atr_pct = [a / c for a, c in zip(atr[-120:], closes[-120:]) if c > 0]
        med_atr_pct = sorted(atr_pct)[len(atr_pct)//2] if atr_pct else 0.025
        # Noisy/high-volatility symbols need longer structural scale.
        if med_atr_pct >= 0.055:
            p['swing_len'] = 30
            p['sweep_reclaim_atr'] = 0.08
            p['fvg_min_gap_atr'] = 0.18
        elif med_atr_pct <= 0.018:
            p['swing_len'] = 16
            p['fvg_min_gap_atr'] = 0.08
        else:
            p['swing_len'] = 20
        if timeframe in ('60min', 'm60', '60'):
            p['swing_len'] = max(12, int(p['swing_len'] * 0.75))
            p['sweep_lookback'] = 60
        elif timeframe in ('weekly', 'week', 'w'):
            p['swing_len'] = max(26, int(p['swing_len'] * 1.5))
            p['sweep_lookback'] = 100
    if override:
        p.update({k: v for k, v in override.items() if v is not None})
    return p


@dataclass
class Pivot:
    level: Optional[float] = None
    idx: Optional[int] = None
    date: str = ''
    crossed: bool = True
    kind: str = ''


@dataclass
class Trend:
    bias: int = 0  # 1 bull, -1 bear, 0 unknown


def pine_pivots(klines: List[Dict], size: int, use_left: bool = True) -> Dict:
    """Confirmed pivots using Pine-like right confirmation.

    A pivot at k becomes knowable at k + size. With use_left=True it must also
    exceed/undercut size bars to its left, avoiding V27's noisy 3/3 behavior.
    """
    highs, lows = [], []
    n = len(klines)
    for cur in range(size, n):
        k = cur - size
        if k <= 0 or (use_left and k - size < 0):
            continue
        h, l = klines[k]['h'], klines[k]['l']
        right_highs = [klines[j]['h'] for j in range(k + 1, cur + 1)]
        right_lows = [klines[j]['l'] for j in range(k + 1, cur + 1)]
        if use_left:
            left_highs = [klines[j]['h'] for j in range(k - size, k)]
            left_lows = [klines[j]['l'] for j in range(k - size, k)]
        else:
            left_highs, left_lows = [], []
        if h > max(right_highs + left_highs):
            highs.append({'idx': k, 'confirm_idx': cur, 'price': h, 'date': _date(klines[k]), 'size': size})
        if l < min(right_lows + left_lows):
            lows.append({'idx': k, 'confirm_idx': cur, 'price': l, 'date': _date(klines[k]), 'size': size})
    return {'highs': highs, 'lows': lows, 'n': len(highs) + len(lows), 'size': size}


def structure_state_machine(klines: List[Dict], pivots: Dict, atr: List[float], level: str = 'swing', sweeps: Optional[List[Dict]] = None) -> List[Dict]:
    by_confirm = {}
    for h in pivots.get('highs', []):
        by_confirm.setdefault(h['confirm_idx'], []).append(('high', h))
    for l in pivots.get('lows', []):
        by_confirm.setdefault(l['confirm_idx'], []).append(('low', l))

    high_pivot = Pivot(kind='high')
    low_pivot = Pivot(kind='low')
    trend = Trend(0)
    events = []
    sweep_by_idx_dir = {}
    for s in sweeps or []:
        sweep_by_idx_dir[(s['index'], s['direction'])] = s

    for i, b in enumerate(klines):
        # New pivots become active only when confirmed; this preserves causality.
        for kind, p in by_confirm.get(i, []):
            if kind == 'high':
                high_pivot = Pivot(p['price'], p['idx'], p['date'], False, 'high')
            else:
                low_pivot = Pivot(p['price'], p['idx'], p['date'], False, 'low')

        c = b['c']; prev_c = klines[i-1]['c'] if i > 0 else c
        buf = max(atr[i] * 0.02, c * 0.0002)

        if high_pivot.level is not None and not high_pivot.crossed:
            if prev_c <= high_pivot.level and c > high_pivot.level + buf:
                old_bias = trend.bias
                ev_type = 'CHOCH' if old_bias == -1 else 'BOS'
                trend.bias = 1
                high_pivot.crossed = True
                is_mss, mss_reason = _qualify_mss(events, sweeps or [], i, 'bull', atr[i], klines)
                events.append({
                    'type': ev_type, 'direction': 'bull', 'index': i, 'date': _date(b),
                    'price': high_pivot.level, 'break_price': c, 'swing_idx': high_pivot.idx,
                    'swing_price': high_pivot.level, 'source_level': level,
                    'old_trend': 'bearish' if old_bias == -1 else ('bullish' if old_bias == 1 else 'unknown'),
                    'new_trend': 'bullish', 'is_mss': bool(ev_type == 'CHOCH' and is_mss),
                    'mss_reason': mss_reason if ev_type == 'CHOCH' and is_mss else '',
                    'atr': atr[i], 'confidence': 0.80 if level == 'swing' else 0.65,
                })

        if low_pivot.level is not None and not low_pivot.crossed:
            if prev_c >= low_pivot.level and c < low_pivot.level - buf:
                old_bias = trend.bias
                ev_type = 'CHOCH' if old_bias == 1 else 'BOS'
                trend.bias = -1
                low_pivot.crossed = True
                is_mss, mss_reason = _qualify_mss(events, sweeps or [], i, 'bear', atr[i], klines)
                events.append({
                    'type': ev_type, 'direction': 'bear', 'index': i, 'date': _date(b),
                    'price': low_pivot.level, 'break_price': c, 'swing_idx': low_pivot.idx,
                    'swing_price': low_pivot.level, 'source_level': level,
                    'old_trend': 'bullish' if old_bias == 1 else ('bearish' if old_bias == -1 else 'unknown'),
                    'new_trend': 'bearish', 'is_mss': bool(ev_type == 'CHOCH' and is_mss),
                    'mss_reason': mss_reason if ev_type == 'CHOCH' and is_mss else '',
                    'atr': atr[i], 'confidence': 0.80 if level == 'swing' else 0.65,
                })
    return events


def _qualify_mss(events: List[Dict], sweeps: List[Dict], idx: int, direction: str, atr_val: float, klines: List[Dict]) -> Tuple[bool, str]:
    # MSS is a CHOCH with recent valid opposite-side liquidity sweep and displacement.
    lookback = 12
    recent = [s for s in sweeps if s['direction'] == direction and 0 < idx - s['index'] <= lookback]
    if not recent:
        return False, ''
    b = klines[idx]
    rng = max(b['h'] - b['l'], 1e-9)
    body = abs(b['c'] - b['o'])
    disp_ok = rng >= atr_val * 0.9 or body / rng >= 0.55
    if not disp_ok:
        return False, ''
    return True, f"recent_{recent[-1].get('subtype','SWEEP')}_displacement"


def eqh_eql_signals(klines: List[Dict], eq_pivots: Dict, atr: List[float], threshold_mult: float = 0.10) -> List[Dict]:
    out = []
    for side in ('highs', 'lows'):
        prev = None
        for p in eq_pivots.get(side, []):
            if prev is not None:
                idx = p['confirm_idx']
                thresh = max(atr[idx] * threshold_mult, p['price'] * 0.001)
                if abs(p['price'] - prev['price']) <= thresh:
                    typ = 'EQH' if side == 'highs' else 'EQL'
                    direction = 'bear' if typ == 'EQH' else 'bull'
                    out.append({
                        'type': typ, 'direction': direction, 'index': idx, 'date': _date(klines[idx]),
                        'level': round((p['price'] + prev['price']) / 2, 4),
                        'price': round((p['price'] + prev['price']) / 2, 4),
                        'left_idx': prev['idx'], 'right_idx': p['idx'], 'confirm_idx': idx,
                        'confidence': 0.7,
                    })
            prev = p
    return out


def sweep_signals_stateful(klines: List[Dict], pivots: Dict, eqs: List[Dict], atr: List[float], profile: Dict) -> List[Dict]:
    levels = []
    # Use swing pivots as liquidity levels, plus EQH/EQL as higher confidence pools.
    for h in pivots.get('highs', []):
        levels.append({'id': f"H{h['idx']}", 'idx': h['idx'], 'confirm_idx': h['confirm_idx'], 'price': h['price'], 'side': 'high', 'swept': False, 'pool': 'SWING'})
    for l in pivots.get('lows', []):
        levels.append({'id': f"L{l['idx']}", 'idx': l['idx'], 'confirm_idx': l['confirm_idx'], 'price': l['price'], 'side': 'low', 'swept': False, 'pool': 'SWING'})
    for e in eqs:
        levels.append({'id': f"{e['type']}{e['right_idx']}", 'idx': e['right_idx'], 'confirm_idx': e['index'], 'price': e['level'], 'side': 'high' if e['type'] == 'EQH' else 'low', 'swept': False, 'pool': e['type']})

    levels.sort(key=lambda x: x['confirm_idx'])
    out = []
    max_lb = int(profile['sweep_lookback'])
    reclaim_atr = float(profile['sweep_reclaim_atr'])
    min_wick_ratio = float(profile['sweep_min_wick_ratio'])

    for i, b in enumerate(klines):
        emitted_dir = set()
        # Most recent levels first; only one sweep per direction per bar.
        candidates = [lv for lv in levels if not lv['swept'] and lv['confirm_idx'] < i and i - lv['idx'] <= max_lb]
        candidates.sort(key=lambda lv: lv['idx'], reverse=True)
        for lv in candidates:
            if lv['side'] == 'low':
                direction = 'bull'; subtype = 'SSL'
                if direction in emitted_dir: continue
                buf = max(atr[i] * reclaim_atr, lv['price'] * 0.0005)
                rng = max(b['h'] - b['l'], 1e-9)
                lower_wick = min(b['o'], b['c']) - b['l']
                if b['l'] < lv['price'] - buf and b['c'] > lv['price'] and lower_wick / rng >= min_wick_ratio:
                    out.append({'type': 'SWEEP', 'subtype': subtype, 'direction': direction, 'index': i, 'date': _date(b),
                                'price': lv['price'], 'wick_low': b['l'], 'close': b['c'], 'swept_idx': lv['idx'],
                                'pool': lv['pool'], 'confidence': 0.80 if lv['pool'] in ('EQL','EQH') else 0.65})
                    lv['swept'] = True; emitted_dir.add(direction)
            else:
                direction = 'bear'; subtype = 'BSL'
                if direction in emitted_dir: continue
                buf = max(atr[i] * reclaim_atr, lv['price'] * 0.0005)
                rng = max(b['h'] - b['l'], 1e-9)
                upper_wick = b['h'] - max(b['o'], b['c'])
                if b['h'] > lv['price'] + buf and b['c'] < lv['price'] and upper_wick / rng >= min_wick_ratio:
                    out.append({'type': 'SWEEP', 'subtype': subtype, 'direction': direction, 'index': i, 'date': _date(b),
                                'price': lv['price'], 'wick_high': b['h'], 'close': b['c'], 'swept_idx': lv['idx'],
                                'pool': lv['pool'], 'confidence': 0.80 if lv['pool'] in ('EQL','EQH') else 0.65})
                    lv['swept'] = True; emitted_dir.add(direction)
    return out


def fvg_list_pine_like(klines: List[Dict], atr: List[float], profile: Dict) -> List[Dict]:
    out = []
    deltas = []
    for i in range(2, len(klines)):
        b = klines[i]
        prev = klines[i-1]
        prev2 = klines[i-2]
        c0 = max(b['c'], 1e-9)
        delta_pct = abs((b['c'] - b['o']) / c0)
        deltas.append(delta_pct)
        auto_thresh = (sum(deltas) / len(deltas) * 2.0) if profile.get('fvg_auto_threshold') and deltas else 0.0
        min_gap = max(atr[i] * float(profile['fvg_min_gap_atr']), c0 * 0.0008)
        # Bullish: current low above high two bars ago and prior close confirms above old high.
        gap = b['l'] - prev2['h']
        if gap > min_gap and prev['c'] > prev2['h'] and delta_pct >= auto_thresh * 0.35:
            out.append({'type': 'FVG', 'direction': 'bull', 'index': i, 'date': _date(b),
                        'gap_low': prev2['h'], 'gap_high': b['l'], 'mid': (prev2['h'] + b['l']) / 2,
                        'width': gap, 'atr': atr[i], 'confidence': min(0.9, 0.55 + gap / max(atr[i], 1e-9) * 0.1)})
        gap = prev2['l'] - b['h']
        if gap > min_gap and prev['c'] < prev2['l'] and delta_pct >= auto_thresh * 0.35:
            out.append({'type': 'FVG', 'direction': 'bear', 'index': i, 'date': _date(b),
                        'gap_low': b['h'], 'gap_high': prev2['l'], 'mid': (b['h'] + prev2['l']) / 2,
                        'width': gap, 'atr': atr[i], 'confidence': min(0.9, 0.55 + gap / max(atr[i], 1e-9) * 0.1)})
    return out


def ob_signals_pine_like(klines: List[Dict], struct_events: List[Dict], atr: List[float], profile: Dict) -> List[Dict]:
    out = []
    active = []
    max_back = int(profile['ob_backscan'])
    max_active = int(profile['active_ob_max'])
    # Only swing events and MSS-qualified internal CHOCH are eligible for chart-grade OB.
    for ev in struct_events:
        if ev.get('source_level') != 'swing' and not ev.get('is_mss'):
            continue
        idx = ev['index']
        direction = ev['direction']
        found = None
        start = max(0, idx - max_back)
        for j in range(idx - 1, start - 1, -1):
            b = klines[j]
            # Bullish OB = nearest bearish candle before bullish break; reverse for bearish.
            if direction == 'bull' and b['c'] < b['o']:
                found = j; break
            if direction == 'bear' and b['c'] > b['o']:
                found = j; break
        if found is None:
            continue
        b = klines[found]
        # LuxAlgo-like volatility parsing: high-volatility candle uses body extremes less naively.
        rng = b['h'] - b['l']
        high_vol = rng >= 2.0 * max(atr[found], 1e-9)
        if direction == 'bull':
            zl = min(b['o'], b['c']) if high_vol else b['l']
            zh = b['h'] if not high_vol else max(b['o'], b['c'])
            invalidation = zl
        else:
            zl = b['l'] if not high_vol else min(b['o'], b['c'])
            zh = max(b['o'], b['c']) if high_vol else b['h']
            invalidation = zh
        ob = {'type': 'OB', 'direction': direction, 'index': found, 'date': _date(b),
              'confirm_index': idx, 'confirm_date': ev['date'], 'source_event': ev['type'],
              'source_level': ev.get('source_level',''), 'zone_low': zl, 'zone_high': zh,
              'invalidation': invalidation, 'mid': (zl + zh) / 2, 'mitigated': False,
              'confidence': 0.80 if ev.get('source_level') == 'swing' else 0.65}
        active.append(ob)
        active = active[-max_active:]
        out.append(ob)
        # Mitigate older active OBs up to current bar.
        for old in active:
            if old is ob or old.get('mitigated'):
                continue
            kb = klines[idx]
            if old['direction'] == 'bull' and kb['l'] <= old['zone_high'] and kb['c'] < old['zone_low']:
                old['mitigated'] = True; old['mitigated_idx'] = idx
            if old['direction'] == 'bear' and kb['h'] >= old['zone_low'] and kb['c'] > old['zone_high']:
                old['mitigated'] = True; old['mitigated_idx'] = idx
    return out


def bpr_signals_pine_like(fvgs: List[Dict], atr: List[float], profile: Dict) -> List[Dict]:
    out = []
    max_gap = int(profile['bpr_max_gap'])
    min_width_mult = float(profile['bpr_min_width_atr'])
    last_by_dir = {'bull': [], 'bear': []}
    for f in fvgs:
        opp = 'bear' if f['direction'] == 'bull' else 'bull'
        for g in reversed(last_by_dir[opp][-8:]):
            if abs(f['index'] - g['index']) > max_gap:
                continue
            zl = max(f['gap_low'], g['gap_low'])
            zh = min(f['gap_high'], g['gap_high'])
            if zh <= zl:
                continue
            idx = max(f['index'], g['index'])
            if (zh - zl) < atr[idx] * min_width_mult:
                continue
            # Direction follows latest FVG reclaim side.
            out.append({'type': 'BPR', 'direction': f['direction'], 'index': idx, 'date': f['date'],
                        'first_fvg_idx': g['index'], 'second_fvg_idx': f['index'],
                        'zone_low': zl, 'zone_high': zh, 'mid': (zl + zh) / 2,
                        'confidence': 0.55})
            break
        last_by_dir[f['direction']].append(f)
    return out


def liquidity_voids(klines: List[Dict], atr: List[float], profile: Dict) -> List[Dict]:
    out = []
    for i, b in enumerate(klines):
        rng = b['h'] - b['l']
        if rng <= 0 or atr[i] <= 0:
            continue
        body = abs(b['c'] - b['o'])
        if rng >= atr[i] * float(profile['lv_min_range_atr']) and body / rng >= float(profile['lv_min_body_ratio']):
            direction = 'bull' if b['c'] > b['o'] else 'bear'
            out.append({'type': 'LiquidityVoid', 'direction': direction, 'index': i, 'date': _date(b),
                        'zone_low': min(b['o'], b['c']), 'zone_high': max(b['o'], b['c']),
                        'mid': (b['o'] + b['c']) / 2, 'confidence': 0.55})
    return out


def ote_signals_from_struct(klines: List[Dict], struct_events: List[Dict], pivots: Dict) -> List[Dict]:
    out = []
    # Conservative chart zones only for swing events; not used as standalone trading signal.
    pivot_by_idx = {p['idx']: p for p in pivots.get('highs', []) + pivots.get('lows', [])}
    for ev in struct_events:
        if ev.get('source_level') != 'swing':
            continue
        sidx = ev.get('swing_idx')
        if sidx is None:
            continue
        eidx = ev['index']
        if not (0 <= sidx < eidx < len(klines)):
            continue
        lows = [klines[j]['l'] for j in range(sidx, eidx + 1)]
        highs = [klines[j]['h'] for j in range(sidx, eidx + 1)]
        lo, hi = min(lows), max(highs)
        if hi <= lo:
            continue
        if ev['direction'] == 'bull':
            zl = hi - (hi - lo) * 0.79
            zh = hi - (hi - lo) * 0.62
        else:
            zl = lo + (hi - lo) * 0.62
            zh = lo + (hi - lo) * 0.79
        out.append({'type': 'OTE', 'direction': ev['direction'], 'index': eidx, 'date': ev['date'],
                    'zone_low': min(zl, zh), 'zone_high': max(zl, zh), 'mid': (zl + zh) / 2,
                    'source_event': ev['type'], 'confidence': 0.55})
    return out


def breaker_blocks_from_obs(klines: List[Dict], obs: List[Dict]) -> List[Dict]:
    """Breaker blocks: failed OBs that price closes through and may later retest.

    Bullish breaker = former bearish OB invalidated by a close above its high.
    Bearish breaker = former bullish OB invalidated by a close below its low.
    """
    out = []
    for ob in obs:
        start = int(ob.get('confirm_index', ob.get('index', 0))) + 1
        zl, zh = _f(ob.get('zone_low')), _f(ob.get('zone_high'))
        if zl <= 0 or zh <= 0:
            continue
        for i in range(start, min(start + 80, len(klines))):
            b = klines[i]
            if ob.get('direction') == 'bear' and b['c'] > zh:
                out.append({'type': 'BreakerBlock', 'direction': 'bull', 'index': i, 'date': _date(b),
                            'zone_low': zl, 'zone_high': zh, 'mid': (zl + zh) / 2,
                            'source_ob_idx': ob.get('index'), 'break_price': b['c'], 'confidence': 0.60})
                break
            if ob.get('direction') == 'bull' and b['c'] < zl:
                out.append({'type': 'BreakerBlock', 'direction': 'bear', 'index': i, 'date': _date(b),
                            'zone_low': zl, 'zone_high': zh, 'mid': (zl + zh) / 2,
                            'source_ob_idx': ob.get('index'), 'break_price': b['c'], 'confidence': 0.60})
                break
    return out


def rejection_blocks_from_sweeps(klines: List[Dict], sweeps: List[Dict], atr: List[float]) -> List[Dict]:
    """Rejection blocks derived from liquidity sweep rejection candles."""
    out = []
    for sw in sweeps:
        i = int(sw.get('index', -1))
        if not (0 <= i < len(klines)):
            continue
        b = klines[i]
        rng = max(b['h'] - b['l'], 1e-9)
        body_low, body_high = min(b['o'], b['c']), max(b['o'], b['c'])
        if sw.get('direction') == 'bull':
            wick = body_low - b['l']
            if wick / rng >= 0.35 and b['c'] > b['o']:
                out.append({'type': 'RejectionBlock', 'direction': 'bull', 'index': i, 'date': _date(b),
                            'zone_low': body_low, 'zone_high': body_high, 'mid': (body_low + body_high) / 2,
                            'source_sweep_idx': sw.get('index'), 'confidence': min(0.8, 0.55 + wick / rng * 0.25)})
        else:
            wick = b['h'] - body_high
            if wick / rng >= 0.35 and b['c'] < b['o']:
                out.append({'type': 'RejectionBlock', 'direction': 'bear', 'index': i, 'date': _date(b),
                            'zone_low': body_low, 'zone_high': body_high, 'mid': (body_low + body_high) / 2,
                            'source_sweep_idx': sw.get('index'), 'confidence': min(0.8, 0.55 + wick / rng * 0.25)})
    return out


def detect_all_signals_pine_like(klines: List[Dict], profile: Optional[Dict] = None, timeframe: str = 'daily') -> Dict:
    klines = normalize_klines(klines)
    n = len(klines)
    if n < 80:
        return _empty_result(n)
    p = adaptive_profile(klines, timeframe=timeframe, override=profile)
    atr = rolling_atr(klines, 14)

    swing = pine_pivots(klines, int(p['swing_len']), use_left=True)
    internal = pine_pivots(klines, int(p['internal_len']), use_left=True)
    eq_piv = pine_pivots(klines, int(p['eq_len']), use_left=True)
    eqs = eqh_eql_signals(klines, eq_piv, atr, float(p['eq_threshold_atr']))
    sweeps = sweep_signals_stateful(klines, swing, eqs, atr, p)

    swing_struct = structure_state_machine(klines, swing, atr, 'swing', sweeps)
    internal_struct = structure_state_machine(klines, internal, atr, 'internal', sweeps)
    # Chart-grade structure: swing events + MSS-qualified internal CHOCH for tactical visibility.
    structure = list(swing_struct) + [e for e in internal_struct if e.get('is_mss')]
    structure.sort(key=lambda x: x['index'])

    fvgs = fvg_list_pine_like(klines, atr, p)
    bprs = bpr_signals_pine_like(fvgs, atr, p)
    obs = ob_signals_pine_like(klines, structure, atr, p)
    otes = ote_signals_from_struct(klines, swing_struct, swing)
    lvs = liquidity_voids(klines, atr, p)
    breakers = breaker_blocks_from_obs(klines, obs)
    rejections = rejection_blocks_from_sweeps(klines, sweeps, atr)

    signals = {
        'swings': swing,
        'internal_swings': internal,
        'swing_structure': swing_struct,
        'internal_structure': internal_struct,
        'structure': structure,
        'fvgs': fvgs,
        'bprs': bprs,
        'sweeps': sweeps,
        'obs': obs,
        'otes': otes,
        'eqh_eql': eqs,
        'liquidity_voids': lvs,
        'po3s': [],
        'breakers': breakers,
        'rejection_blocks': rejections,
    }
    summary = {
        'n_bars': n,
        'n_swing_highs': len(swing.get('highs', [])),
        'n_swing_lows': len(swing.get('lows', [])),
        'n_internal_highs': len(internal.get('highs', [])),
        'n_internal_lows': len(internal.get('lows', [])),
        'n_bos_choch_mss': len(structure),
        'n_swing_structure': len(swing_struct),
        'n_internal_structure': len(internal_struct),
        'n_fvg': len(fvgs),
        'n_bpr': len(bprs),
        'n_sweep': len(sweeps),
        'n_ob': len(obs),
        'n_ote': len(otes),
        'n_eqh_eql': len(eqs),
        'n_lv': len(lvs),
        'n_breakers': len(breakers),
        'n_rejection_blocks': len(rejections),
        'n_po3': 0,
        'profile': p,
        'definition_version': 'smc_core_pine_like_v32a',
    }
    return {'signals': signals, 'summary': summary}


def _empty_result(n=0):
    return {
        'signals': {
            'swings': {'highs': [], 'lows': [], 'n': 0},
            'internal_swings': {'highs': [], 'lows': [], 'n': 0},
            'swing_structure': [], 'internal_structure': [], 'structure': [],
            'fvgs': [], 'bprs': [], 'sweeps': [], 'obs': [], 'otes': [],
            'eqh_eql': [], 'liquidity_voids': [], 'po3s': [], 'breakers': [], 'rejection_blocks': [],
        },
        'summary': {'n_bars': n, 'definition_version': 'smc_core_pine_like_v32a'},
    }


# Compatibility alias for callers expecting detect_all_signals_v27-like name.
def detect_all_signals_v32a(klines: List[Dict], profile: Optional[Dict] = None, timeframe: str = 'daily') -> Dict:
    return detect_all_signals_pine_like(klines, profile=profile, timeframe=timeframe)


if __name__ == '__main__':
    import json, sys
    data = json.loads(open(sys.argv[1]).read())
    res = detect_all_signals_pine_like(data)
    print(json.dumps(res['summary'], ensure_ascii=False, indent=2))
