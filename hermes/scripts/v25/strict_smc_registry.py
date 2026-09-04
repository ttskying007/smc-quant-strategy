#!/usr/bin/env python3
"""Strict Pine/LuxAlgo-style SMC signal registry.

Single source of truth for V67 candidate signals.  It intentionally does not
import the legacy V27/V59/V66 detector stack, because that stack mixes a later
entry-zone sequence with structure-anchor semantics.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

SWING_LEFT = 3
SWING_RIGHT = 3
BREAK_BUFFER = 1.001
FVG_MIN_GAP = 1.0005
MAX_OB_BACKSCAN = 15
STRUCT_COOLDOWN = 3


def f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def dt(bar: Dict[str, Any]) -> str:
    return str(bar.get('t', bar.get('date', '')))


@dataclass
class StrictSignal:
    type: str
    direction: str
    index: int
    date: str
    price: float
    zone_low: float = 0.0
    zone_high: float = 0.0
    anchor_event_idx: int = -1
    anchor_event_type: str = ''
    broken_swing_idx: int = -1
    broken_swing_price: float = 0.0
    confirm_index: int = -1
    raw: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        if out.get('raw') is None:
            out['raw'] = {}
        return out


def normalize_klines(klines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for b in klines:
        nb = dict(b)
        for k in ('o', 'h', 'l', 'c', 'v'):
            nb[k] = f(nb.get(k))
        out.append(nb)
    return out


def atr(klines: List[Dict[str, Any]], idx: int, period: int = 14) -> float:
    vals = []
    for i in range(max(1, idx - period + 1), idx + 1):
        b, p = klines[i], klines[i - 1]
        vals.append(max(b['h'] - b['l'], abs(b['h'] - p['c']), abs(b['l'] - p['c'])))
    return sum(vals) / len(vals) if vals else max(klines[idx]['c'] * 0.02, 0.01)


def confirmed_swings(klines: List[Dict[str, Any]], left: int = SWING_LEFT, right: int = SWING_RIGHT) -> Dict[str, List[Dict[str, Any]]]:
    highs: List[Dict[str, Any]] = []
    lows: List[Dict[str, Any]] = []
    n = len(klines)
    for i in range(left, n - right):
        hi = klines[i]['h']
        lo = klines[i]['l']
        if hi > 0 and all(j == i or klines[j]['h'] < hi for j in range(i - left, i + right + 1)):
            highs.append({'idx': i, 'price': hi, 'confirm_idx': i + right, 'date': dt(klines[i])})
        if lo > 0 and all(j == i or klines[j]['l'] > lo for j in range(i - left, i + right + 1)):
            lows.append({'idx': i, 'price': lo, 'confirm_idx': i + right, 'date': dt(klines[i])})
    return {'highs': highs, 'lows': lows}


def strict_structure(klines: List[Dict[str, Any]], swings: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    highs = sorted(swings['highs'], key=lambda x: x['confirm_idx'])
    lows = sorted(swings['lows'], key=lambda x: x['confirm_idx'])
    high_pos = low_pos = 0
    last_high: Optional[Dict[str, Any]] = None
    last_low: Optional[Dict[str, Any]] = None
    trend = 'unknown'
    last_bull_event = -999
    for i in range(len(klines)):
        while high_pos < len(highs) and highs[high_pos]['confirm_idx'] <= i:
            last_high = highs[high_pos]
            high_pos += 1
        while low_pos < len(lows) and lows[low_pos]['confirm_idx'] <= i:
            last_low = lows[low_pos]
            low_pos += 1
        close = klines[i]['c']
        if last_high and close > last_high['price'] * BREAK_BUFFER and i - last_bull_event >= STRUCT_COOLDOWN:
            ev_type = 'BOS' if trend == 'bull' else 'CHOCH'
            events.append(StrictSignal(
                type=f'{ev_type}_Bull', direction='bull', index=i, date=dt(klines[i]), price=close,
                broken_swing_idx=last_high['idx'], broken_swing_price=last_high['price'], confirm_index=i,
                raw={'swing_high': last_high, 'close': close},
            ).to_dict())
            trend = 'bull'
            last_bull_event = i
        if last_low and close < last_low['price'] / BREAK_BUFFER:
            trend = 'bear'
    return events


def strict_fvgs(klines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i in range(2, len(klines)):
        gap_low = klines[i - 2]['h']
        gap_high = klines[i]['l']
        if gap_low > 0 and gap_high > gap_low * FVG_MIN_GAP:
            out.append(StrictSignal(
                type='FVG_Bull', direction='bull', index=i, date=dt(klines[i]), price=(gap_low + gap_high) / 2,
                zone_low=gap_low, zone_high=gap_high, confirm_index=i,
                raw={'left_idx': i - 2, 'right_idx': i, 'gap_low': gap_low, 'gap_high': gap_high},
            ).to_dict())
    return out


def nearest_bearish_candle(klines: List[Dict[str, Any]], event_idx: int, max_back: int = MAX_OB_BACKSCAN) -> int:
    for j in range(event_idx - 1, max(-1, event_idx - max_back - 1), -1):
        if klines[j]['c'] < klines[j]['o']:
            return j
    return -1


def strict_obs(klines: List[Dict[str, Any]], structure: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ev in structure:
        if ev.get('direction') != 'bull':
            continue
        event_idx = int(ev['index'])
        ob_idx = nearest_bearish_candle(klines, event_idx)
        if ob_idx < 0:
            continue
        b = klines[ob_idx]
        rng = max(b['h'] - b['l'], 0.0001)
        body_ratio = abs(b['c'] - b['o']) / rng
        if body_ratio < 0.12:
            continue
        out.append(StrictSignal(
            type='OB_Bull', direction='bull', index=ob_idx, date=dt(b), price=(b['h'] + b['l']) / 2,
            zone_low=b['l'], zone_high=b['h'], anchor_event_idx=event_idx,
            anchor_event_type=ev['type'], broken_swing_idx=int(ev.get('broken_swing_idx', -1)),
            broken_swing_price=f(ev.get('broken_swing_price')), confirm_index=event_idx,
            raw={'event': ev, 'body_ratio': body_ratio, 'nearest_backscan': True},
        ).to_dict())
    return out


def detect_strict_registry(klines: List[Dict[str, Any]]) -> Dict[str, Any]:
    bars = normalize_klines(klines)
    if len(bars) < 80:
        return {'summary': {'n_bars': len(bars), 'definition_version': 'V67_STRICT_REGISTRY'}, 'signals': {'swings': {'highs': [], 'lows': []}, 'structure': [], 'fvgs': [], 'obs': []}}
    swings = confirmed_swings(bars)
    structure = strict_structure(bars, swings)
    fvgs = strict_fvgs(bars)
    obs = strict_obs(bars, structure)
    return {
        'summary': {
            'n_bars': len(bars), 'definition_version': 'V67_STRICT_REGISTRY',
            'n_swing_highs': len(swings['highs']), 'n_swing_lows': len(swings['lows']),
            'n_structure': len(structure), 'n_fvg': len(fvgs), 'n_ob': len(obs),
        },
        'signals': {'swings': swings, 'structure': structure, 'fvgs': fvgs, 'obs': obs},
    }


def zone_retrace_rank(klines: List[Dict[str, Any]], zone: Dict[str, Any], before_idx: int) -> int:
    rank = 0
    start = int(zone.get('index', 0)) + 1
    zh = f(zone.get('zone_high'))
    zl = f(zone.get('zone_low'))
    for j in range(start, max(start, before_idx)):
        if klines[j]['l'] <= zh * 1.005 and klines[j]['c'] >= zl * 0.99:
            rank += 1
    return rank
