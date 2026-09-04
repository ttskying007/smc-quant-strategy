#!/usr/bin/env python3
"""
V16 SMC信号检测引擎 — 6项全面根因修复

V15诊断发现的6项根因缺陷（已全部定位并修复）:

缺陷1 [CRITICAL BUG] CHOCH/BOS 几乎无产出:
  根因: detect_structure_v15 line 533-540 用 max/min 追踪 last_swing_high/low。
  `if sw['price'] > last_swing_high: last_swing_high = sw['price']` 导致
  last_swing_high = 全图最高点, last_swing_low = 全图最低点。
  突破条件 bar['c'] > last_swing_high 需要突破全图最高 → 几乎不可能。
  Pine正确做法: last_swing_high := swing_high_ms (直接赋值, 不是max)。
  V16修复: 用最新摆动点替换，非取极值。

缺陷2 EQL=0(茅台):
  根因: Pine标准 threshold = ATR(200) * 0.1, 但我们用15-bar ATR=26元, threshold=2.6元。
  茅台300bar日线相邻摆动高点最小差价9.12元, 远大于2.6元。
  Pine在完整图表(数千bar)上有数百个pivot, 密度远高于我们的300bar。
  V16修复: (a)用200-bar ATR扩大threshold, (b)连续pivot + 非连续nearby pivot双模式。

缺陷3 BPR=55(噪声95%+):
  根因: O(n²)全组合: 29个zone × 29 = 841次比较, 去重后55个重叠。
  大部分是不同时间窗口的bull/bear zone偶然重叠, 无实际结构意义。
  V16修复: 限制重叠区间宽度 > ATR*0.3, 只输出top 5最强信号。

缺陷4 Sweep穿透太小(0.08%噪声):
  根因: 没有最小穿透要求。任何影线刺穿摆动点0.08%就触发。
  Pine中Sweep需要signifcant penetration + reversal。
  V16修复: 最小穿透 >= ATR * 0.15。

缺陷5 OB摆动点质量:
  目前用left=5/right=2, 日均摆动15-20个, 部分为局部wiggle非结构摆动。
  SMC 2026用ob_swing_length=7 left+right=14 K线确认。
  V16修复: OB用left=7/right=2, 更严格的结构摆动。

缺陷6 MSS过多(17个):
  内部摆动(left=3/right=1)在300bar上产生大量微型转折。
  V16修复: 增加最小间距到15bar, 最小突破0.3%。

参数默认(SMC 2026 + 用户指定):
  swing_length=5, ob_swing=7, ob_lookback=10, ob_disp_mult=1.5
  fvg_atr_mult=0.5, eqhl_pivot=4, eqhl_thr=0.1, min_strength=3.0
"""

import math, logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

log = logging.getLogger('smc_v16.signals')


@dataclass
class Signal:
    type: str
    idx: int
    direction: str
    price: float
    upper: float = 0.0
    lower: float = 0.0
    strength: float = 0.0
    confidence: float = 0.0
    timeframe: str = 'daily'
    confirmed_at: int = 0
    volume_ratio: float = 1.0
    grade: int = 1
    trend_aligned: bool = False
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        d = {
            'type': self.type, 'idx': self.idx, 'direction': self.direction,
            'price': round(self.price, 4), 'upper': round(self.upper, 4),
            'lower': round(self.lower, 4), 'strength': round(self.strength, 2),
            'confidence': round(self.confidence, 3), 'timeframe': self.timeframe,
            'confirmed_at': self.confirmed_at, 'volume_ratio': round(self.volume_ratio, 2),
            'grade': self.grade, 'trend_aligned': self.trend_aligned,
            'metadata': self.metadata,
        }
        return d


def calc_adaptive_thresholds(ohlcv: List[Dict]) -> Dict:
    if not ohlcv or len(ohlcv) < 20:
        return {'atr_pct': 2.0, 'vol_median': 1000, 'avg_volume': 1000,
                'fvg_min_width': 0.001, 'atr_value': 0.01, 'atr_200': 0.01}
    closes = [b['c'] for b in ohlcv if b.get('c', 0) > 0]
    highs = [b['h'] for b in ohlcv]
    lows = [b['l'] for b in ohlcv]
    vols = [b.get('v', b.get('vol', 0)) for b in ohlcv]

    recent = min(50, len(ohlcv))
    trs = []
    for i in range(max(1, len(ohlcv) - recent), len(ohlcv)):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs) / len(trs) if trs else 1
    avg_close = sum(closes) / len(closes) if closes else 100
    atr_pct = atr / avg_close * 100 if avg_close > 0 else 2.0
    vol_median = sorted(vols)[len(vols)//2] if vols else 1000
    avg_volume = sum(vols) / len(vols) if vols else 1000

    # Long ATR (200-bar equivalent for EQL) — Pine eqhl_atr_length=200
    n200 = min(200, len(ohlcv))
    trs200 = []
    for i in range(max(1, len(ohlcv) - n200), len(ohlcv)):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
        trs200.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr_200 = sum(trs200) / len(trs200) if trs200 else atr

    return {
        'atr_pct': max(0.3, min(10.0, atr_pct)),
        'atr_value': atr,
        'atr_200': atr_200,
        'vol_median': vol_median,
        'avg_volume': avg_volume,
        'fvg_min_width': atr * 0.5,  # fvg_atr_mult=0.5
    }


# ═══════════════════════════════════════════════════════════════════════
# 1. 摆动点检测
# ═══════════════════════════════════════════════════════════════════════

def detect_swings_v16(ohlcv: List[Dict], left: int = 5, right: int = 2,
                       atr_filter: bool = True) -> Dict:
    """Pine pivothigh/pivotlow with right confirmation."""
    n = len(ohlcv)
    if n < left + right + 3:
        return {'highs': [], 'lows': [], 'swing_idxs': set()}

    atr_val = 0.0
    if atr_filter and n >= 15:
        trs = []
        for i in range(1, min(15, n)):
            h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr_val = sum(trs) / len(trs) if trs else 0

    raw_highs, raw_lows = [], []

    for i in range(left, n - right):
        bar = ohlcv[i]
        is_high = True
        for j in range(i - left, i + right + 1):
            if j == i or j < 0 or j >= n:
                continue
            if ohlcv[j]['h'] > bar['h']:
                is_high = False
                break
        if is_high:
            raw_highs.append({'idx': i + right, 'bar_idx': i, 'price': bar['h']})

        is_low = True
        for j in range(i - left, i + right + 1):
            if j == i or j < 0 or j >= n:
                continue
            if ohlcv[j]['l'] < bar['l']:
                is_low = False
                break
        if is_low:
            raw_lows.append({'idx': i + right, 'bar_idx': i, 'price': bar['l']})

    highs = _merge_consecutive(raw_highs, ohlcv, is_high=True)
    lows = _merge_consecutive(raw_lows, ohlcv, is_high=False)

    if atr_filter and atr_val > 0:
        min_amp = atr_val * 0.3
        highs = _filter_tiny(highs, min_amp, ohlcv)
        lows = _filter_tiny(lows, min_amp, ohlcv)

    swing_idxs = set()
    for h in highs: swing_idxs.add(h['idx'])
    for lw in lows: swing_idxs.add(lw['idx'])

    return {'highs': highs, 'lows': lows, 'swing_idxs': swing_idxs}


def _merge_consecutive(swings, ohlcv, is_high):
    if len(swings) < 2: return swings
    result = [swings[0]]
    for s in swings[1:]:
        last = result[-1]
        if s['bar_idx'] - last['bar_idx'] <= 3:
            if is_high:
                if s['price'] > last['price']: result[-1] = s
            else:
                if s['price'] < last['price']: result[-1] = s
        else:
            result.append(s)
    return result


def _filter_tiny(swings, min_amp, ohlcv):
    if len(swings) < 2: return swings
    result = [swings[0]]
    for s in swings[1:]:
        prev = result[-1]
        amp = abs(s['price'] - prev['price'])
        if amp >= min_amp or s['bar_idx'] - prev['bar_idx'] > 20:
            result.append(s)
    return result


# ═══════════════════════════════════════════════════════════════════════
# 2. FVG — Pine exact
# ═══════════════════════════════════════════════════════════════════════

def detect_fvg_v16(ohlcv, adaptive=None, tf='daily'):
    if adaptive is None: adaptive = calc_adaptive_thresholds(ohlcv)
    n = len(ohlcv)
    signals = []
    atr_val = adaptive.get('atr_value', 0.01)
    min_gap = atr_val * 0.5

    for i in range(2, n):
        b0, b1, b2 = ohlcv[i], ohlcv[i-1], ohlcv[i-2]

        if b0['l'] > b2['h']:
            gap = b0['l'] - b2['h']
            if gap >= min_gap:
                all_bull = (b0['c'] > b0['o'] and b1['c'] > b1['o'] and b2['c'] > b2['o'])
                sig = Signal(type='FVG_Bull', idx=i-1, direction='bull',
                    price=(b2['h']+b0['l'])/2, upper=b0['l'], lower=b2['h'],
                    timeframe=tf, confirmed_at=i,
                    grade=3 if all_bull else 2,
                    trend_aligned=_check_trend(ohlcv, i, 'bull'))
                sig.strength = 2.0 + (3.0 if all_bull else 0) + min(2.0, gap/atr_val)
                sig.confidence = min(0.9, 0.4 + (0.3 if all_bull else 0) + gap/atr_val*0.1)
                sig.metadata = {'gap': round(gap, 4), 'all_same_dir': all_bull}
                signals.append(sig)

        if b0['h'] < b2['l']:
            gap = b2['l'] - b0['h']
            if gap >= min_gap:
                all_bear = (b0['c'] < b0['o'] and b1['c'] < b1['o'] and b2['c'] < b2['o'])
                sig = Signal(type='FVG_Bear', idx=i-1, direction='bear',
                    price=(b2['l']+b0['h'])/2, upper=b2['l'], lower=b0['h'],
                    timeframe=tf, confirmed_at=i,
                    grade=3 if all_bear else 2,
                    trend_aligned=_check_trend(ohlcv, i, 'bear'))
                sig.strength = 2.0 + (3.0 if all_bear else 0) + min(2.0, gap/atr_val)
                sig.confidence = min(0.9, 0.4 + (0.3 if all_bear else 0) + gap/atr_val*0.1)
                sig.metadata = {'gap': round(gap, 4), 'all_same_dir': all_bear}
                signals.append(sig)

    if signals:
        signals.sort(key=lambda s: s.idx)
        merged = [signals[0]]
        for s in signals[1:]:
            last = merged[-1]
            if abs(s.idx - last.idx) <= 3 and s.direction == last.direction:
                if s.strength > last.strength: merged[-1] = s
            else:
                merged.append(s)
        signals = merged

    return [s.to_dict() for s in signals]


def _check_trend(ohlcv, idx, direction, lookback=10):
    if idx < lookback: return False
    recent = ohlcv[max(0, idx-lookback):idx+1]
    if len(recent) < 5: return False
    avg_first = sum(b['c'] for b in recent[:3]) / 3
    avg_last = sum(b['c'] for b in recent[-3:]) / 3
    trend = (avg_last - avg_first) / avg_first * 100
    return trend > 0.3 if direction == 'bull' else trend < -0.3


# ═══════════════════════════════════════════════════════════════════════
# 3. OB — Pine exact with confirmed swings + backward scan
# ═══════════════════════════════════════════════════════════════════════

def detect_ob_v16(ohlcv, swings=None, displacement_mult=1.5,
                   ob_lookback=10, adaptive=None, tf='daily'):
    if adaptive is None: adaptive = calc_adaptive_thresholds(ohlcv)
    if swings is None: swings = detect_swings_v16(ohlcv, left=7, right=2)

    n = len(ohlcv)
    signals = []
    vol_median = adaptive['vol_median']
    used_idx = set()
    swing_highs = swings.get('highs', [])
    swing_lows = swings.get('lows', [])

    for sl in swing_lows:
        sl_bar, sl_price = sl['bar_idx'], sl['price']
        if sl_bar < ob_lookback + 2: continue

        for back in range(sl_bar - 1, max(sl_bar - ob_lookback - 5, 2), -1):
            bar = ohlcv[back]
            if bar['c'] < bar['o']:
                rng = bar['h'] - bar['l']
                if rng <= 0: continue
                disp = sl_price - bar['l']
                if disp > (rng * displacement_mult):
                    has_impulse = any(ohlcv[fwd]['c'] > ohlcv[fwd]['o']
                                      for fwd in range(back+1, sl_bar))
                    if not has_impulse: continue
                    if back in used_idx: continue

                    sig = Signal(type='OB_Bull', idx=back, direction='bull',
                        price=bar['l'], upper=bar['h'], lower=bar['l'],
                        timeframe=tf, confirmed_at=sl['idx'],
                        volume_ratio=round(bar.get('v',0)/vol_median,2) if vol_median>0 else 1)
                    sig.strength = 4.0 + min(3.0, disp/max(rng,0.0001)*0.5)
                    sig.confidence = min(0.9, 0.5 + disp/max(rng*3,0.0001))
                    sig.metadata = {'method':'swing_backward','swing_idx':sl['idx'],
                        'swing_bar':sl_bar,'swing_price':round(sl_price,4),
                        'displacement_ratio':round(disp/max(rng,0.0001),2),
                        'impulse_bars':sl_bar-back-1,'at_structure':True}
                    signals.append(sig)
                    used_idx.add(back)
                    break

    for sh in swing_highs:
        sh_bar, sh_price = sh['bar_idx'], sh['price']
        if sh_bar < ob_lookback + 2: continue

        for back in range(sh_bar - 1, max(sh_bar - ob_lookback - 5, 2), -1):
            bar = ohlcv[back]
            if bar['c'] > bar['o']:
                rng = bar['h'] - bar['l']
                if rng <= 0: continue
                disp = bar['h'] - sh_price
                if disp > (rng * displacement_mult):
                    has_impulse = any(ohlcv[fwd]['c'] < ohlcv[fwd]['o']
                                      for fwd in range(back+1, sh_bar))
                    if not has_impulse: continue
                    if back in used_idx: continue

                    sig = Signal(type='OB_Bear', idx=back, direction='bear',
                        price=bar['h'], upper=bar['h'], lower=bar['l'],
                        timeframe=tf, confirmed_at=sh['idx'],
                        volume_ratio=round(bar.get('v',0)/vol_median,2) if vol_median>0 else 1)
                    sig.strength = 4.0 + min(3.0, disp/max(rng,0.0001)*0.5)
                    sig.confidence = min(0.9, 0.5 + disp/max(rng*3,0.0001))
                    sig.metadata = {'method':'swing_backward','swing_idx':sh['idx'],
                        'swing_bar':sh_bar,'swing_price':round(sh_price,4),
                        'displacement_ratio':round(disp/max(rng,0.0001),2),
                        'impulse_bars':sh_bar-back-1,'at_structure':True}
                    signals.append(sig)
                    used_idx.add(back)
                    break

    signals.sort(key=lambda s: s.idx)
    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 4. CHOCH/BOS — CRITICAL BUG FIXED: use LATEST swing, not extreme
# ═══════════════════════════════════════════════════════════════════════

def detect_structure_v16(ohlcv, swings=None, tf='daily'):
    """
    V15 BUG: last_swing_high = max(all_highs) → 需要突破全图最高才触发.
    FIX: last_swing_high = newest swing high (Pine exact: last_swing_high := swing_high_ms)
    """
    if swings is None: swings = detect_swings_v16(ohlcv)

    n = len(ohlcv)
    swing_highs = swings.get('highs', [])
    swing_lows = swings.get('lows', [])

    if not swing_highs and not swing_lows:
        return {'CHOCH_Bull':[],'CHOCH_Bear':[],'BOS_Bull':[],'BOS_Bear':[],'all':[]}

    # Build lookup: at each bar, what's the newest known swing
    # Pine: simply assigns last_swing_high := swing_high_ms on each pivot event
    sh_by_bar = {h['bar_idx']: h for h in swing_highs}
    sl_by_bar = {lw['bar_idx']: lw for lw in swing_lows}

    choch_signals, bos_signals = [], []
    swing_trend = 0
    last_swing_high = None
    last_swing_high_bar = 0
    last_swing_low = None
    last_swing_low_bar = 0
    last_label_bar = -999

    for i in range(n):
        bar = ohlcv[i]

        # Pine: when new pivot forms, ASSIGN (overwrite) — NOT max/min
        if i in sh_by_bar:
            last_swing_high = sh_by_bar[i]['price']
            last_swing_high_bar = i
        if i in sl_by_bar:
            last_swing_low = sl_by_bar[i]['price']
            last_swing_low_bar = i

        if last_swing_high is None or last_swing_low is None:
            continue
        if i - last_label_bar < 20:
            continue

        # Bullish break: close > newest swing high
        if bar['c'] > last_swing_high and last_swing_high > 0:
            break_pct = (bar['c'] - last_swing_high) / last_swing_high * 100
            if break_pct < 0.2: continue

            if swing_trend == -1:
                tag = 'CHOCH_Bull'
                strength = 5.0 + min(3.0, break_pct)
                conf = min(0.85, 0.4 + break_pct * 0.05)
            else:
                tag = 'BOS_Bull'
                strength = 3.0 + min(2.0, break_pct)
                conf = min(0.65, 0.3 + break_pct * 0.03)

            sig = Signal(type=tag, idx=i, direction='bull',
                price=bar['c'], upper=bar['h'], lower=last_swing_high,
                strength=strength, confidence=conf, timeframe=tf, confirmed_at=i+1,
                metadata={'break_level':round(last_swing_high,4),
                    'break_pct':round(break_pct,2),
                    'prior_trend':'bear' if swing_trend==-1 else 'bull'})
            if 'CHOCH' in tag: choch_signals.append(sig)
            else: bos_signals.append(sig)
            swing_trend = 1
            last_label_bar = i

        # Bearish break: close < newest swing low
        elif bar['c'] < last_swing_low and last_swing_low > 0:
            break_pct = (last_swing_low - bar['c']) / last_swing_low * 100
            if break_pct < 0.2: continue

            if swing_trend == 1:
                tag = 'CHOCH_Bear'
                strength = 5.0 + min(3.0, break_pct)
                conf = min(0.85, 0.4 + break_pct * 0.05)
            else:
                tag = 'BOS_Bear'
                strength = 3.0 + min(2.0, break_pct)
                conf = min(0.65, 0.3 + break_pct * 0.03)

            sig = Signal(type=tag, idx=i, direction='bear',
                price=bar['c'], upper=last_swing_low, lower=bar['l'],
                strength=strength, confidence=conf, timeframe=tf, confirmed_at=i+1,
                metadata={'break_level':round(last_swing_low,4),
                    'break_pct':round(break_pct,2),
                    'prior_trend':'bull' if swing_trend==1 else 'bear'})
            if 'CHOCH' in tag: choch_signals.append(sig)
            else: bos_signals.append(sig)
            swing_trend = -1
            last_label_bar = i

    all_struct = sorted(choch_signals + bos_signals, key=lambda s: s.idx)
    return {
        'CHOCH_Bull': [s.to_dict() for s in choch_signals if s.direction=='bull'],
        'CHOCH_Bear': [s.to_dict() for s in choch_signals if s.direction=='bear'],
        'BOS_Bull': [s.to_dict() for s in bos_signals if s.direction=='bull'],
        'BOS_Bear': [s.to_dict() for s in bos_signals if s.direction=='bear'],
        'all': [s.to_dict() for s in all_struct],
    }


# ═══════════════════════════════════════════════════════════════════════
# 5. MSS — Internal structure with stricter spacing
# ═══════════════════════════════════════════════════════════════════════

def detect_mss_v16(ohlcv, swings=None, tf='daily'):
    if swings is None: swings = detect_swings_v16(ohlcv, left=3, right=1)

    n = len(ohlcv)
    signals = []
    internal_highs = swings.get('highs', [])
    internal_lows = swings.get('lows', [])

    if len(internal_highs) < 1 or len(internal_lows) < 1: return []

    hs_by_bar = {h['bar_idx']: h for h in internal_highs}
    ls_by_bar = {lw['bar_idx']: lw for lw in internal_lows}

    last_int_high, last_int_low = None, None
    last_label_bar = -999

    for i in range(n):
        bar = ohlcv[i]
        if i in hs_by_bar: last_int_high = hs_by_bar[i]['price']
        if i in ls_by_bar: last_int_low = ls_by_bar[i]['price']

        if last_int_high is None or last_int_low is None: continue
        if i - last_label_bar < 15:  # STRICTER: 15 bar min spacing (V16 fix)
            continue

        if bar['c'] > last_int_high and last_int_high > 0:
            break_pct = (bar['c'] - last_int_high) / last_int_high * 100
            if break_pct < 0.3:  # STRICTER: 0.3% min (V16 fix)
                continue
            sig = Signal(type='MSS_Bull', idx=i, direction='bull',
                price=bar['c'], upper=bar['h'], lower=last_int_high,
                strength=min(3.5, 1.0+break_pct),
                confidence=min(0.45, 0.2+break_pct/10),
                timeframe=tf, confirmed_at=i+1,
                metadata={'break_level':round(last_int_high,4),
                    'break_pct':round(break_pct,2),'structure':'internal'})
            signals.append(sig)
            last_label_bar = i

        elif bar['c'] < last_int_low and last_int_low > 0:
            break_pct = (last_int_low - bar['c']) / last_int_low * 100
            if break_pct < 0.3: continue
            sig = Signal(type='MSS_Bear', idx=i, direction='bear',
                price=bar['c'], upper=last_int_low, lower=bar['l'],
                strength=min(3.5, 1.0+break_pct),
                confidence=min(0.45, 0.2+break_pct/10),
                timeframe=tf, confirmed_at=i+1,
                metadata={'break_level':round(last_int_low,4),
                    'break_pct':round(break_pct,2),'structure':'internal'})
            signals.append(sig)
            last_label_bar = i

    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 6. Sweep — Minimum penetration threshold + swing point break
# ═══════════════════════════════════════════════════════════════════════

def detect_sweep_v16(ohlcv, swings=None, tf='daily'):
    if swings is None: swings = detect_swings_v16(ohlcv, left=5, right=2)

    n = len(ohlcv)
    signals = []
    swing_highs = swings.get('highs', [])
    swing_lows = swings.get('lows', [])

    if not swing_highs and not swing_lows: return []

    # Use atr for min_penetration threshold
    adapt = calc_adaptive_thresholds(ohlcv)
    atr_val = adapt['atr_value']
    min_penetration_pct = max(0.3, atr_val / ohlcv[-1]['c'] * 100 * 0.5)  # at least 0.3% of price
    min_wick_ratio = 1.5

    hs_by_bar, ls_by_bar = {}, {}
    for h in swing_highs: hs_by_bar.setdefault(h['bar_idx'], []).append(h)
    for lw in swing_lows: ls_by_bar.setdefault(lw['bar_idx'], []).append(lw)

    last_highs, last_lows = [], []

    for i in range(n):
        bar = ohlcv[i]
        for h in hs_by_bar.get(i, []): last_highs.append((i, h['price']))
        for lw in ls_by_bar.get(i, []): last_lows.append((i, lw['price']))

        last_highs = [(idx, p) for idx, p in last_highs if i - idx <= 15]
        last_lows = [(idx, p) for idx, p in last_lows if i - idx <= 15]

        body = abs(bar['c'] - bar['o'])
        upper_wick = bar['h'] - max(bar['c'], bar['o'])
        lower_wick = min(bar['c'], bar['o']) - bar['l']

        if upper_wick > body * min_wick_ratio and len(last_highs) >= 1:
            for sh_idx, sh_price in last_highs:
                if bar['h'] > sh_price and bar['c'] < sh_price:
                    penetration_pct = (bar['h'] - sh_price) / sh_price * 100
                    if penetration_pct < min_penetration_pct:  # V16 FIX: min penetration
                        continue
                    sig = Signal(type='SweepDown', idx=i, direction='bull',
                        price=bar['c'], upper=bar['h'], lower=min(bar['c'], bar['o']),
                        strength=4.0, confidence=0.55, timeframe=tf, confirmed_at=i,
                        metadata={'swept_level':round(sh_price,4),'swept_bar':sh_idx,
                            'wick_pct':round(penetration_pct,2)})
                    signals.append(sig)
                    break

        if lower_wick > body * min_wick_ratio and len(last_lows) >= 1:
            for sl_idx, sl_price in last_lows:
                if bar['l'] < sl_price and bar['c'] > sl_price:
                    penetration_pct = (sl_price - bar['l']) / sl_price * 100
                    if penetration_pct < min_penetration_pct: continue
                    sig = Signal(type='SweepUp', idx=i, direction='bear',
                        price=bar['c'], upper=max(bar['c'], bar['o']), lower=bar['l'],
                        strength=4.0, confidence=0.55, timeframe=tf, confirmed_at=i,
                        metadata={'swept_level':round(sl_price,4),'swept_bar':sl_idx,
                            'wick_pct':round(penetration_pct,2)})
                    signals.append(sig)
                    break

    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 7. EQL — Dual mode: consecutive + nearby pivot comparison
# ═══════════════════════════════════════════════════════════════════════

def detect_eql_v16(ohlcv, swings=None, tolerance_pct=None,
                    atr_val=None, tf='daily'):
    """
    V16 dual-mode EQL:
    1. Consecutive pivots within ATR200 * 0.1 (Pine exact)
    2. Non-consecutive nearby pivots within ATR * 0.15 (relaxed, for 300bar data)
    """
    if swings is None: swings = detect_swings_v16(ohlcv, left=4, right=2)
    adapt = calc_adaptive_thresholds(ohlcv)
    if atr_val is None: atr_val = adapt.get('atr_200', 0.01)  # 200-bar ATR (Pine)
    if tolerance_pct is None: tolerance_pct = 0.1

    threshold = atr_val * tolerance_pct  # Pine: atr(200) * 0.1
    signals = []
    swing_highs = swings.get('highs', [])
    swing_lows = swings.get('lows', [])

    # Mode 1: consecutive pivots (Pine exact)
    seen = set()
    if len(swing_highs) >= 2:
        for i in range(1, len(swing_highs)):
            prev = swing_highs[i - 1]
            curr = swing_highs[i]
            if abs(curr['price'] - prev['price']) < threshold:
                level = max(curr['price'], prev['price'])
                key = ('EQH', round(level, 1))
                if key not in seen and curr['idx'] - prev['idx'] >= 3:
                    seen.add(key)
                    sig = Signal(type='EQL_High', idx=curr['idx'], direction='bear',
                        price=round(level,2), upper=round(level,2), lower=round(level*0.995,2),
                        strength=3.0, confidence=0.45, timeframe=tf, confirmed_at=curr['idx'],
                        metadata={'level':round(level,4),'prev_swing':prev['bar_idx'],
                            'threshold':round(threshold,4),'mode':'consecutive'})
                    signals.append(sig)

    if len(swing_lows) >= 2:
        for i in range(1, len(swing_lows)):
            prev = swing_lows[i - 1]
            curr = swing_lows[i]
            if abs(curr['price'] - prev['price']) < threshold:
                level = min(curr['price'], prev['price'])
                key = ('EQL', round(level, 1))
                if key not in seen and curr['idx'] - prev['idx'] >= 3:
                    seen.add(key)
                    sig = Signal(type='EQL_Low', idx=curr['idx'], direction='bull',
                        price=round(level,2), upper=round(level*1.005,2), lower=round(level,2),
                        strength=3.0, confidence=0.45, timeframe=tf, confirmed_at=curr['idx'],
                        metadata={'level':round(level,4),'prev_swing':prev['bar_idx'],
                            'threshold':round(threshold,4),'mode':'consecutive'})
                    signals.append(sig)

    # Mode 2: nearby non-consecutive (for 300bar limited data)
    alt_threshold = atr_val * 0.2  # relaxed: 200-bar ATR * 0.2
    if not signals:
        # Compare pivots up to 5 positions apart
        for hs in [('EQH', swing_highs, True), ('EQL', swing_lows, False)]:
            tag, pivots, is_high = hs[0], hs[1], hs[2]
            for i in range(len(pivots)):
                for j in range(i + 1, min(i + 6, len(pivots))):
                    pi, pj = pivots[i], pivots[j]
                    if abs(pj['price'] - pi['price']) < alt_threshold:
                        level = max(pj['price'], pi['price']) if is_high else min(pj['price'], pi['price'])
                        key = (tag, round(level, 1))
                        if key not in seen:
                            seen.add(key)
                            typ = 'EQL_High' if is_high else 'EQL_Low'
                            direc = 'bear' if is_high else 'bull'
                            sig = Signal(type=typ, idx=pj['idx'], direction=direc,
                                price=round(level,2),
                                upper=round(level,2) if is_high else round(level*1.005,2),
                                lower=round(level*0.995,2) if is_high else round(level,2),
                                strength=2.5, confidence=0.35, timeframe=tf, confirmed_at=pj['idx'],
                                metadata={'level':round(level,4),'threshold':round(alt_threshold,4),
                                    'mode':'nearby','gap':j-i,'count':j-i+1})
                            signals.append(sig)

    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 8. BPR — Top-N strongest overlaps only
# ═══════════════════════════════════════════════════════════════════════

def detect_bpr_v16(ohlcv, fvg_signals=None, ob_signals=None, tf='daily'):
    adapt = calc_adaptive_thresholds(ohlcv)
    atr_val = adapt['atr_value']
    min_zone_width = atr_val * 0.3  # V16 FIX: minimum meaningful BPR width

    bull_zones, bear_zones = [], []
    for lst, tag in [(fvg_signals or [], 'FVG'), (ob_signals or [], 'OB')]:
        for z in lst:
            up = z.get('upper', 0)
            lo = z.get('lower', 0)
            if up <= 0 or lo <= 0: continue
            entry = {'up': up, 'lo': lo, 'idx': z.get('idx', 0),
                     'strength': z.get('strength', 2), 'source': tag}
            if 'Bull' in z.get('type', ''):
                bull_zones.append(entry)
            elif 'Bear' in z.get('type', ''):
                bear_zones.append(entry)

    if len(bull_zones) < 1 or len(bear_zones) < 1: return []

    overlaps = []
    seen = set()

    for bz in bull_zones:
        for brz in bear_zones:
            if bz['up'] > brz['lo'] and bz['lo'] < brz['up']:
                oh = min(bz['up'], brz['up'])
                ol = max(bz['lo'], brz['lo'])
                if oh - ol < min_zone_width: continue  # too narrow = noise
                if oh <= ol: continue
                key = (round(oh, 2), round(ol, 2))
                if key in seen: continue
                seen.add(key)

                total_str = bz.get('strength', 2) + brz.get('strength', 2)
                overlaps.append({
                    'idx': max(bz['idx'], brz['idx']),
                    'oh': oh, 'ol': ol,
                    'strength': total_str,
                })

    # Sort by strength descending, take top 5
    overlaps.sort(key=lambda x: -x['strength'])
    signals = []
    for ov in overlaps[:5]:
        sig = Signal(type='BPR', idx=ov['idx'], direction='neutral',
            price=(ov['oh']+ov['ol'])/2, upper=ov['oh'], lower=ov['ol'],
            strength=min(8.0, ov['strength']),
            confidence=min(0.7, 0.3+(ov['oh']-ov['ol'])/max(ov['oh'],0.01)*5),
            timeframe=tf, confirmed_at=ov['idx'],
            metadata={'overlap_high':round(ov['oh'],4),'overlap_low':round(ov['ol'],4),
                'sources':'fvg+ob'})
        signals.append(sig)

    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 9. IFVG
# ═══════════════════════════════════════════════════════════════════════

def detect_ifvg_v16(ohlcv, adaptive=None, tf='daily'):
    if adaptive is None: adaptive = calc_adaptive_thresholds(ohlcv)
    n = len(ohlcv)
    signals = []
    atr_val = adaptive.get('atr_value', 0.01)

    for i in range(1, n - 2):
        c1, c2 = ohlcv[i], ohlcv[i + 1]
        if c1['h'] < c2['l']:
            gap = c2['l'] - c1['h']
            if gap >= atr_val * 0.3:
                sig = Signal(type='IFVG_Bull', idx=i, direction='bull',
                    price=((c1['h']+c1['l'])/2+(c2['h']+c2['l'])/2)/2,
                    upper=c2['l'], lower=c1['h'],
                    strength=2.0, confidence=0.3, timeframe=tf, confirmed_at=i+1,
                    metadata={'gap': round(gap, 4)})
                signals.append(sig)
        elif c1['l'] > c2['h']:
            gap = c1['l'] - c2['h']
            if gap >= atr_val * 0.3:
                sig = Signal(type='IFVG_Bear', idx=i, direction='bear',
                    price=((c1['h']+c1['l'])/2+(c2['h']+c2['l'])/2)/2,
                    upper=c1['l'], lower=c2['h'],
                    strength=2.0, confidence=0.3, timeframe=tf, confirmed_at=i+1,
                    metadata={'gap': round(gap, 4)})
                signals.append(sig)
    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 10. 统一入口
# ═══════════════════════════════════════════════════════════════════════

def detect_all_signals_v16(ohlcv, params=None, adaptive=None, tf='daily'):
    if params is None: params = {}
    if adaptive is None: adaptive = calc_adaptive_thresholds(ohlcv)

    swing_left = params.get('swing_left', 5)
    swing_right = params.get('swing_right', 2)

    # Shared swings
    swings = detect_swings_v16(ohlcv, left=swing_left, right=swing_right)
    internal_swings = detect_swings_v16(ohlcv, left=3, right=1)
    eql_swings = detect_swings_v16(ohlcv, left=4, right=2)

    # 1. FVG
    fvg_signals = detect_fvg_v16(ohlcv, adaptive=adaptive, tf=tf)

    # 2. OB (V16: left=7 for structure-quality swings)
    ob_swings = detect_swings_v16(ohlcv, left=7, right=2)
    ob_signals = detect_ob_v16(ohlcv, swings=ob_swings,
        displacement_mult=params.get('ob_displacement_mult', 1.5),
        ob_lookback=params.get('ob_lookback', 10),
        adaptive=adaptive, tf=tf)

    # 3. Structure CHOCH/BOS (V16: LATEST swing, NOT extreme)
    structure = detect_structure_v16(ohlcv, swings=swings, tf=tf)

    # 4. MSS (V16: min 15bar spacing, 0.3% break)
    mss_signals = detect_mss_v16(ohlcv, swings=internal_swings, tf=tf)

    # 5. Sweep (V16: min penetration threshold)
    sweep_signals = detect_sweep_v16(ohlcv, swings=swings, tf=tf)

    # 6. EQL (V16: dual mode — consecutive + nearby)
    eql_signals = detect_eql_v16(ohlcv, swings=eql_swings,
        tolerance_pct=params.get('eqhl_threshold', 0.1),
        atr_val=adaptive.get('atr_200'),
        tf=tf)

    # 7. BPR (V16: top-5 strongest only)
    bpr_signals = detect_bpr_v16(ohlcv, fvg_signals=fvg_signals,
        ob_signals=ob_signals, tf=tf)

    # 8. IFVG
    ifvg_signals = detect_ifvg_v16(ohlcv, adaptive=adaptive, tf=tf)

    # Combine
    choch_signals = (structure.get('CHOCH_Bull', []) + structure.get('CHOCH_Bear', []))
    bos_signals = (structure.get('BOS_Bull', []) + structure.get('BOS_Bear', []))

    all_signals = (fvg_signals + ob_signals + sweep_signals +
                   choch_signals + bos_signals +
                   mss_signals + eql_signals + bpr_signals + ifvg_signals)
    all_signals.sort(key=lambda s: s.get('idx', 0))

    stats = {
        'total': len(all_signals),
        'fvg': len(fvg_signals), 'ob': len(ob_signals),
        'sweep': len(sweep_signals), 'choch': len(choch_signals),
        'bos': len(bos_signals), 'mss': len(mss_signals),
        'eql': len(eql_signals), 'bpr': len(bpr_signals), 'ifvg': len(ifvg_signals),
        'bull': sum(1 for s in all_signals if s.get('direction')=='bull'),
        'bear': sum(1 for s in all_signals if s.get('direction')=='bear'),
    }

    for i, sig in enumerate(all_signals): sig['seq'] = i

    return {
        'fvg': fvg_signals, 'ob': ob_signals, 'sweep': sweep_signals,
        'choch': choch_signals, 'bos': bos_signals, 'mss': mss_signals,
        'eql': eql_signals, 'bpr': bpr_signals, 'ifvg': ifvg_signals,
        'all': all_signals, 'adaptive': adaptive,
        'swings': {'highs': [s['bar_idx'] for s in swings['highs']],
                    'lows': [s['bar_idx'] for s in swings['lows']]},
        'stats': stats,
    }
