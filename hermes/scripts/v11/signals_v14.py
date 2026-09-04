#!/usr/bin/env python3
"""V14 SMC信号检测引擎 — Pine Script质量对齐版

核心改进 (对比V11):
1. 摆动点: Pine-style pivothigh/pivotlow, 右确认, ATR振幅过滤
2. OB: 从摆动点向后扫描 + 位移过滤器 (>=1.3x) + 成交量确认
3. CHOCH: 状态机 (跟踪趋势, 检测BOS/CHOCH on crossover)
4. EQL: 基于摆动点 (只对比摆动高/低点, 非所有K线对)
5. FVG/Sweep/MSS/OTE/PO3/BPR/IFVG: 复用V11已验证逻辑

设计原则: 信号质量 > 数量. 宁可少但准.
"""
import math, logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

log = logging.getLogger('smc_v14.signals')

# ═══════════════════════════════════════════════════════════════════════
# Signal data structures (复用V11)
# ═══════════════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════════════
# 自适应阈值 (复用V11 calc_adaptive_thresholds)
# ═══════════════════════════════════════════════════════════════════════

def calc_adaptive_thresholds(ohlcv: List[Dict]) -> Dict:
    """计算基于数据的自适应阈值——复用V11"""
    if not ohlcv or len(ohlcv) < 20:
        return {'atr_pct': 2.0, 'vol_median': 1000, 'avg_volume': 1000,
                'fvg_min_width': 0.001, 'ob_strength_min': 0.5,
                'swing_lookback': 12}
    closes = [b['c'] for b in ohlcv if b.get('c', 0) > 0]
    highs = [b['h'] for b in ohlcv]
    lows = [b['l'] for b in ohlcv]
    vols = [b.get('v', b.get('vol', 0)) for b in ohlcv]

    recent = min(50, len(ohlcv))
    trs = []
    for i in range(max(1, len(ohlcv) - recent), len(ohlcv)):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs) / len(trs) if trs else (max(highs) - min(lows)) / max(1, len(ohlcv))
    avg_close = sum(closes) / len(closes) if closes else 100
    atr_pct = atr / avg_close * 100 if avg_close > 0 else 2.0
    vol_median = sorted(vols)[len(vols)//2] if vols else 1000
    avg_volume = sum(vols) / len(vols) if vols else 1000

    sw_lookback = 8 if len(ohlcv) < 250 else 12  # 60min更短的摆动窗口

    return {
        'atr_pct': max(0.3, min(10.0, atr_pct)),
        'vol_median': vol_median,
        'avg_volume': avg_volume,
        'fvg_min_width': 0.0003,  # 60min可用更小
        'ob_strength_min': 0.5,
        'swing_lookback': sw_lookback,
    }

# ═══════════════════════════════════════════════════════════════════════
# 1. 摆动点检测 (Pine-quality: 左确认 + 右确认 + ATR振幅过滤)
# ═══════════════════════════════════════════════════════════════════════

def detect_swings_v14(ohlcv: List[Dict], left: int = 8, right: int = 3,
                      atr_filter: bool = True) -> Dict:
    """Pine-style pivothigh/pivotlow

    参数:
      left: 左侧检查bar数 (Pine默认10, 60min用8)
      right: 右侧确认bar数 (Pine默认10, 60min用3)

    摆动点要求:
      - 高点: 左右各left/right根K线内最高
      - 低点: 左右各left/right根K线内最低
      - ATR过滤: 摆动幅度 > 0.5*ATR (避免噪声)
    """
    n = len(ohlcv)
    if n < left + right + 5:
        return {'highs': [], 'lows': [], 'swing_idxs': set()}

    # 预计算ATR用于振幅过滤
    atr_pct = 0
    if atr_filter and n >= 15:
        trs = []
        for i in range(1, min(15, n)):
            h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        avg_tr = sum(trs) / len(trs) if trs else 0
        avg_price = sum(b['c'] for b in ohlcv[:min(15, n)]) / min(15, n)
        atr_pct = avg_tr / avg_price * 100 if avg_price > 0 else 0

    highs, lows = [], []
    sw_idx_set = set()

    for i in range(left, n - right):
        bar = ohlcv[i]

        # Swing high
        is_high = True
        for j in range(i - left, i + right + 1):
            if j == i or j < 0 or j >= n:
                continue
            if ohlcv[j]['h'] > bar['h']:
                is_high = False
                break
        if is_high:
            highs.append({'idx': i, 'price': bar['h']})
            sw_idx_set.add(i)

        # Swing low
        is_low = True
        for j in range(i - left, i + right + 1):
            if j == i or j < 0 or j >= n:
                continue
            if ohlcv[j]['l'] < bar['l']:
                is_low = False
                break
        if is_low:
            lows.append({'idx': i, 'price': bar['l']})
            sw_idx_set.add(i)

    # ATR振幅过滤: 剔除相邻摆动点之间幅度过小的
    if atr_filter and atr_pct > 0 and len(highs) > 1:
        min_amp = atr_pct * 0.3
        filtered = [highs[0]]
        for h in highs[1:]:
            prev = filtered[-1]
            amp = abs(h['price'] - prev['price']) / prev['price'] * 100
            if amp >= min_amp or h['idx'] - prev['idx'] >= left * 2:
                filtered.append(h)
        highs = filtered

    if atr_filter and atr_pct > 0 and len(lows) > 1:
        min_amp = atr_pct * 0.3
        filtered = [lows[0]]
        for lw in lows[1:]:
            prev = filtered[-1]
            amp = abs(lw['price'] - prev['price']) / prev['price'] * 100
            if amp >= min_amp or lw['idx'] - prev['idx'] >= left * 2:
                filtered.append(lw)
        lows = filtered

    return {'highs': highs, 'lows': lows, 'swing_idxs': sw_idx_set}


# ═══════════════════════════════════════════════════════════════════════
# 2. FVG检测 (复用V11逻辑 — 已验证)
# ═══════════════════════════════════════════════════════════════════════

def _classify_fvg_width(gap_pct: float, atr_pct: float) -> int:
    ratio = gap_pct / max(atr_pct / 100, 0.0001)
    if ratio > 1.5:   return 4  # macro
    elif ratio > 0.8: return 3  # meso
    elif ratio > 0.3: return 2  # micro
    else:             return 1  # nano

def _check_trend_alignment(ohlcv, idx, direction, lookback=10):
    if idx < lookback:
        return False
    recent = ohlcv[max(0, idx - lookback):idx + 1]
    if len(recent) < 5:
        return False
    avg_first = sum(b['c'] for b in recent[:3]) / 3
    avg_last = sum(b['c'] for b in recent[-3:]) / 3
    trend = (avg_last - avg_first) / avg_first * 100
    if direction == 'bull':
        return trend > 0.3
    else:
        return trend < -0.3

def detect_fvg_v14(ohlcv: List[Dict], min_width: float = None,
                   merge_dist: int = 3, adaptive: Dict = None,
                   tf: str = 'daily') -> List[Dict]:
    """FVG检测 — 复用V11逻辑"""
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    if min_width is None:
        min_width = adaptive['fvg_min_width']
    n = len(ohlcv)
    signals = []
    atr_pct = adaptive.get('atr_pct', 2.0)

    for i in range(n - 2):
        b1, b2, b3 = ohlcv[i], ohlcv[i+1], ohlcv[i+2]
        b1_bear = b1['c'] < b1['o']
        b2_bear = b2['c'] < b2['o']
        b3_bear = b3['c'] < b3['o']
        b1_bull = b1['c'] > b1['o']
        b2_bull = b2['c'] > b2['o']
        b3_bull = b3['c'] > b3['o']
        all_bearish = b1_bear and b2_bear and b3_bear
        all_bullish = b1_bull and b2_bull and b3_bull
        c2_body_pct = abs(b2['c'] - b2['o']) / b2['c'] * 100 if b2['c'] > 0 else 0
        c2_body_ok = c2_body_pct >= atr_pct * 0.6

        # Bullish FVG
        if b1['h'] < b3['l']:
            gap = b3['l'] - b1['h']
            gap_pct = gap / b1['c'] if b1['c'] > 0 else 0
            if gap_pct >= min_width and (c2_body_ok or all_bearish):
                grade = _classify_fvg_width(gap_pct, atr_pct)
                if all_bearish:
                    grade = max(grade, 3)
                trend_aligned = _check_trend_alignment(ohlcv, i, 'bull')
                sig = Signal(
                    type='FVG_Bull', idx=i+1, direction='bull',
                    price=(b1['h'] + b3['l']) / 2,
                    upper=b3['l'], lower=b1['h'], timeframe=tf,
                    grade=grade, trend_aligned=trend_aligned,
                    confirmed_at=i+2,
                )
                sig.strength = 2.0 + grade * 1.5 + (0.5 if all_bearish else 0)
                sig.confidence = min(0.5 + gap_pct * 10, 1.0) + (0.15 if all_bearish else 0)
                sig.metadata = {'gap_pct': round(gap_pct, 4)}
                signals.append(sig)

        # Bearish FVG
        elif b1['l'] > b3['h']:
            gap = b1['l'] - b3['h']
            gap_pct = gap / b1['c'] if b1['c'] > 0 else 0
            if gap_pct >= min_width and (c2_body_ok or all_bullish):
                grade = _classify_fvg_width(gap_pct, atr_pct)
                if all_bullish:
                    grade = max(grade, 3)
                trend_aligned = _check_trend_alignment(ohlcv, i, 'bear')
                sig = Signal(
                    type='FVG_Bear', idx=i+1, direction='bear',
                    price=(b1['l'] + b3['h']) / 2,
                    upper=b1['l'], lower=b3['h'], timeframe=tf,
                    grade=grade, trend_aligned=trend_aligned,
                    confirmed_at=i+2,
                )
                sig.strength = 2.0 + grade * 1.5 + (0.5 if all_bullish else 0)
                sig.confidence = min(0.5 + gap_pct * 10, 1.0) + (0.15 if all_bullish else 0)
                sig.metadata = {'gap_pct': round(gap_pct, 4)}
                signals.append(sig)

    # Merge adjacent FVGs
    if merge_dist > 0 and signals:
        signals.sort(key=lambda s: s.idx)
        merged = [signals[0]]
        for s in signals[1:]:
            last = merged[-1]
            if abs(s.idx - last.idx) <= merge_dist and s.direction == last.direction:
                # Keep stronger one
                if s.strength > last.strength:
                    merged[-1] = s
            else:
                merged.append(s)
        signals = merged

    return [s.to_dict() for s in signals]


# ── 快摆动点 (无右确认, 用于OB扫描) ──

def _quick_swing_highs(ohlcv, lookback=8):
    n = len(ohlcv)
    highs = []
    for i in range(lookback, n - lookback):
        if all(ohlcv[i]['h'] >= ohlcv[j]['h']
               for j in range(i - lookback, i + lookback + 1) if 0 <= j < n and j != i):
            highs.append({'idx': i, 'price': ohlcv[i]['h']})
    return highs

def _quick_swing_lows(ohlcv, lookback=8):
    n = len(ohlcv)
    lows = []
    for i in range(lookback, n - lookback):
        if all(ohlcv[i]['l'] <= ohlcv[j]['l']
               for j in range(i - lookback, i + lookback + 1) if 0 <= j < n and j != i):
            lows.append({'idx': i, 'price': ohlcv[i]['l']})
    return lows


# ═══════════════════════════════════════════════════════════════════════
# 3. OB检测 (Pine-style: 从摆动点向后扫描 + 位移过滤器)
# ═══════════════════════════════════════════════════════════════════════

def detect_ob_v14(ohlcv: List[Dict], swings: Dict = None,
                  displacement_mult: float = 0.8,
                  adaptive: Dict = None, tf: str = 'daily') -> List[Dict]:
    """Pine-quality OB检测

    ICT Order Block = 推动行情启动的最后一根逆势K线.

    流程 (Bull OB):
    1. 取swing high (摆动高点)
    2. 从swing high向前扫描, 跳过bearish pullback
    3. 找bullish impulse (2+连阳)
    4. impulse之前最后一根bearish candle = OB
    5. 验证: 位移比 >= displacement_mult
           (impulse距离 / OB本身range)
    6. 成交量过滤: impulse volume > median * 1.2
    """
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    if swings is None:
        swings = detect_swings_v14(ohlcv)

    n = len(ohlcv)
    signals = []
    vol_median = adaptive['vol_median']
    used_idx = set()

    swing_highs = swings.get('highs', [])
    swing_lows = swings.get('lows', [])
    swing_idxs = swings.get('swing_idxs', set())

    # 同时计算快摆动点 (无右确认), 用于OB的位移计算
    quick_highs = _quick_swing_highs(ohlcv, 8)
    quick_lows = _quick_swing_lows(ohlcv, 8)
    quick_swing_idxs = set(si for si, _ in quick_highs + quick_lows)

    # ── Bull OB: 从swing high向后扫描 ──
    for sh in quick_highs:  # 用快摆动点覆盖更多OB
        sh_idx = sh['idx']
        if sh_idx < 10:
            continue

        # 从swing high向前(更早)扫描, 跳过pullback bearish bars
        # push_impulse_start = 从sh_idx往前找bullish impulse的起点
        impulse_end = None
        impulse_start = None

        # 从swing high往前, 跳过bearish bars, 找bullish impulse
        for back in range(sh_idx - 1, max(sh_idx - 25, 5), -1):
            bar = ohlcv[back]
            if bar['c'] > bar['o']:  # bullish bar → impulse candidate
                if impulse_end is None:
                    impulse_end = back
                # 继续往前找连续bullish
                continue
            else:
                # bearish bar → impulse ends here
                if impulse_end is not None:
                    impulse_start = back + 1
                    break
                impulse_end = None  # reset, keep searching

        if impulse_end is None or impulse_start is None:
            continue

        impulse_bars = impulse_end - impulse_start + 1
        if impulse_bars < 2:
            continue

        # OB = impulse_start - 1 (最后逆势bar)
        ob_idx = impulse_start - 1
        if ob_idx < 5 or ob_idx in used_idx:
            continue

        ob_bar = ohlcv[ob_idx]
        if ob_bar['c'] >= ob_bar['o']:  # must be bearish
            continue

        # 位移计算
        ob_range = ob_bar['h'] - ob_bar['l']
        impulse_start_price = ohlcv[impulse_start]['l' if ohlcv[impulse_start]['c'] > ohlcv[impulse_start]['o'] else 'c']
        impulse_end_price = ohlcv[impulse_end]['h']
        impulse_distance = impulse_end_price - impulse_start_price
        displacement_ratio = impulse_distance / ob_range if ob_range > 0 else 0

        if displacement_ratio < displacement_mult:
            continue

        # 成交量
        impulse_vol = sum(ohlcv[k]['v'] for k in range(impulse_start, impulse_end + 1)) / impulse_bars
        vol_ok = impulse_vol > vol_median * 1.2 or ob_bar['v'] > vol_median * 1.2
        if not vol_ok:
            continue

        # 在摆动点附近?
        at_swing = any(abs(ob_idx - si) <= 5 for si in swing_idxs)

        sig = Signal(
            type='OB_Bull', idx=ob_idx, direction='bull',
            price=ob_bar['l'], upper=ob_bar['h'], lower=ob_bar['l'],
            timeframe=tf, confirmed_at=impulse_end,
            volume_ratio=round(ob_bar['v'] / vol_median, 2) if vol_median > 0 else 1,
        )
        sig.strength = 4.0 + (2.0 if at_swing else 0) + min(2.0, displacement_ratio * 0.5)
        sig.confidence = min(0.9, 0.4 + (0.2 if at_swing else 0) + displacement_ratio * 0.1)
        sig.metadata = {
            'impulse_bars': impulse_bars,
            'displacement_ratio': round(displacement_ratio, 2),
            'at_swing': at_swing,
            'swing_idx': sh_idx,
            'method': 'swing_backward',
        }
        signals.append(sig)
        used_idx.add(ob_idx)

    # ── Bear OB: 从swing low向后扫描 ──
    for sl in quick_lows:  # 用快摆动点覆盖更多OB
        sl_idx = sl['idx']
        if sl_idx < 10:
            continue

        impulse_end = None
        impulse_start = None
        for back in range(sl_idx - 1, max(sl_idx - 25, 5), -1):
            bar = ohlcv[back]
            if bar['c'] < bar['o']:  # bearish bar
                if impulse_end is None:
                    impulse_end = back
                continue
            else:
                if impulse_end is not None:
                    impulse_start = back + 1
                    break
                impulse_end = None

        if impulse_end is None or impulse_start is None:
            continue
        impulse_bars = impulse_end - impulse_start + 1
        if impulse_bars < 2:
            continue

        ob_idx = impulse_start - 1
        if ob_idx < 5 or ob_idx in used_idx:
            continue
        ob_bar = ohlcv[ob_idx]
        if ob_bar['c'] <= ob_bar['o']:  # must be bullish
            continue

        ob_range = ob_bar['h'] - ob_bar['l']
        impulse_start_price = ohlcv[impulse_start]['h'] if ohlcv[impulse_start]['c'] < ohlcv[impulse_start]['o'] else 'c'
        impulse_end_price_dn = ohlcv[impulse_end]['l']
        impulse_distance_dn = max(0, impulse_start_price - impulse_end_price_dn) if isinstance(impulse_start_price, (int, float)) else 0

        # Use close-based displacement for bear
        impulse_start_close = ohlcv[impulse_start]['c']
        impulse_end_close = ohlcv[impulse_end]['c']
        impulse_distance_close = impulse_start_close - impulse_end_close
        displacement_ratio = impulse_distance_close / ob_range if ob_range > 0 else 0

        if displacement_ratio < displacement_mult:
            continue

        impulse_vol = sum(ohlcv[k]['v'] for k in range(impulse_start, impulse_end + 1)) / impulse_bars
        vol_ok = impulse_vol > vol_median * 1.2 or ob_bar['v'] > vol_median * 1.2
        if not vol_ok:
            continue

        at_swing = any(abs(ob_idx - si) <= 5 for si in swing_idxs)

        sig = Signal(
            type='OB_Bear', idx=ob_idx, direction='bear',
            price=ob_bar['h'], upper=ob_bar['h'], lower=ob_bar['l'],
            timeframe=tf, confirmed_at=impulse_end,
            volume_ratio=round(ob_bar['v'] / vol_median, 2) if vol_median > 0 else 1,
        )
        sig.strength = 4.0 + (2.0 if at_swing else 0) + min(2.0, displacement_ratio * 0.5)
        sig.confidence = min(0.9, 0.4 + (0.2 if at_swing else 0) + displacement_ratio * 0.1)
        sig.metadata = {
            'impulse_bars': impulse_bars,
            'displacement_ratio': round(displacement_ratio, 2),
            'at_swing': at_swing,
            'swing_idx': sl_idx,
            'method': 'swing_backward',
        }
        signals.append(sig)
        used_idx.add(ob_idx)

    # ── 不再用前向扫描fallback — 纯摆动点向后扫描 = 质量保证 ──
    # V11的假信号问题正来自前向扫描。宁可少但要准。

    signals.sort(key=lambda s: s.idx)
    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 4. CHOCH检测 (状态机: 跟踪趋势 + 摆动点突破)
# ═══════════════════════════════════════════════════════════════════════

def _detect_trend_v14(ohlcv, idx, lookback=10):
    """快速趋势判断"""
    if idx < lookback:
        return 'neutral', 0
    first = ohlcv[idx - lookback]['c']
    last = ohlcv[idx]['c']
    change = (last - first) / first * 100 if first > 0 else 0
    if change > 0.5:
        return 'up', change
    elif change < -0.5:
        return 'down', abs(change)
    return 'neutral', abs(change)

def detect_choch_v14(ohlcv: List[Dict], swings: Dict = None,
                     lookback: int = 15, min_confirm: int = 1,
                     tf: str = 'daily') -> List[Dict]:
    """CHOCH检测 — 状态机

    Pine参考(LuxAlgo方式):
    跟踪最近的摆动高/低点。
    - Bull CHOCH: 价格收盘突破上一个swing high (之前趋势是down)
    - Bear CHOCH: 价格收盘跌破上一个swing low (之前趋势是up)

    关键: 用状态机跟踪trend, 不需要O(n²)扫描
    """
    if swings is None:
        swings = detect_swings_v14(ohlcv)

    n = len(ohlcv)
    signals = []
    swing_highs = swings.get('highs', [])
    swing_lows = swings.get('lows', [])

    if len(swing_highs) < 2 and len(swing_lows) < 2:
        return []

    # ── Bull CHOCH: 价格突破前一个swing high ──
    # 条件: 之前的trend是down (至少从最近swing low来看)
    for sh in swing_highs:
        sh_idx = sh['idx']
        sh_price = sh['price']

        # 找这个swing high之前的swing low
        prior_lows = [sl for sl in swing_lows if sl['idx'] < sh_idx]
        if not prior_lows:
            continue
        last_sl = prior_lows[-1]

        # 下跌趋势确认: 从swing low到swing high涨幅不大 (<5%)
        # 或者检查swing low之前的trend
        trend, t_strength = _detect_trend_v14(ohlcv, sh_idx, 15)

        # Bull CHOCH: 价格突破sh_price
        for k in range(sh_idx + 1, min(sh_idx + lookback, n)):
            bar = ohlcv[k]
            if bar['c'] > sh_price:
                # 确认
                confirmed = True
                for c in range(1, min_confirm + 1):
                    if k + c >= n:
                        break
                    if ohlcv[k + c]['c'] < sh_price:
                        confirmed = False
                        break
                if confirmed:
                    break_strength = (bar['c'] - sh_price) / sh_price * 100
                    if break_strength < 0.3:
                        continue

                    sig = Signal(
                        type='CHOCH_Bull', idx=k, direction='bull',
                        price=bar['c'], upper=bar['h'], lower=sh_price,
                        timeframe=tf, confirmed_at=k + min_confirm,
                    )
                    sig.strength = 3.0 + min(3.0, break_strength * 0.5) + (2.0 if trend == 'down' else 0)
                    sig.confidence = min(0.8, 0.3 + break_strength * 0.02 + (0.2 if trend == 'down' else 0))
                    sig.metadata = {
                        'break_level': round(sh_price, 4),
                        'break_strength': round(break_strength, 2),
                        'prior_trend': trend,
                        'swing_idx': sh_idx,
                    }
                    signals.append(sig)
                    break

    # ── Bear CHOCH: 价格跌破前一个swing low ──
    for sl in swing_lows:
        sl_idx = sl['idx']
        sl_price = sl['price']

        prior_highs = [sh for sh in swing_highs if sh['idx'] < sl_idx]
        if not prior_highs:
            continue

        trend, t_strength = _detect_trend_v14(ohlcv, sl_idx, 15)

        for k in range(sl_idx + 1, min(sl_idx + lookback, n)):
            bar = ohlcv[k]
            if bar['c'] < sl_price:
                confirmed = True
                for c in range(1, min_confirm + 1):
                    if k + c >= n:
                        break
                    if ohlcv[k + c]['c'] > sl_price:
                        confirmed = False
                        break
                if confirmed:
                    break_strength = (sl_price - bar['c']) / sl_price * 100
                    if break_strength < 0.3:
                        continue

                    sig = Signal(
                        type='CHOCH_Bear', idx=k, direction='bear',
                        price=bar['c'], upper=sl_price, lower=bar['l'],
                        timeframe=tf, confirmed_at=k + min_confirm,
                    )
                    sig.strength = 3.0 + min(3.0, break_strength * 0.5) + (2.0 if trend == 'up' else 0)
                    sig.confidence = min(0.8, 0.3 + break_strength * 0.02 + (0.2 if trend == 'up' else 0))
                    sig.metadata = {
                        'break_level': round(sl_price, 4),
                        'break_strength': round(break_strength, 2),
                        'prior_trend': trend,
                        'swing_idx': sl_idx,
                    }
                    signals.append(sig)
                    break

    signals.sort(key=lambda s: s.idx)
    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 5. Sweep检测 (复用V11逻辑 — 已验证)
# ═══════════════════════════════════════════════════════════════════════

def detect_sweep_v14(ohlcv: List[Dict], lookback: int = 12,
                     wick_ratio: float = None, adaptive: Dict = None,
                     tf: str = 'daily') -> List[Dict]:
    """Sweep检测 — 复用V11核心逻辑"""
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    if wick_ratio is None:
        wick_ratio = adaptive.get('atr_pct', 2.0) * 0.5

    n = len(ohlcv)
    signals = []
    vol_median = adaptive['vol_median']

    # 预计算摆动点
    swing_highs = []
    swing_lows = []
    sw_lb = 12
    for i in range(sw_lb, n - sw_lb):
        bar = ohlcv[i]
        is_h = all(ohlcv[i]['h'] >= ohlcv[j]['h'] for j in range(i - sw_lb, i + sw_lb + 1) if 0 <= j < n and j != i)
        if is_h: swing_highs.append(i)
        is_l = all(ohlcv[i]['l'] <= ohlcv[j]['l'] for j in range(i - sw_lb, i + sw_lb + 1) if 0 <= j < n and j != i)
        if is_l: swing_lows.append(i)

    swing_idxs = set(swing_highs + swing_lows)

    for i in range(lookback, n - 1):
        bar = ohlcv[i]
        body = abs(bar['c'] - bar['o'])
        upper_wick = bar['h'] - max(bar['c'], bar['o'])
        lower_wick = min(bar['c'], bar['o']) - bar['l']
        wick_ratio_val = max(upper_wick, lower_wick) / max(body, 0.0001)
        at_swing = i in swing_idxs or any(abs(i - s) <= 3 for s in swing_idxs)

        # SweepDown (bullish) - upper wick breaks above recent HH
        if upper_wick >= body * 2 and upper_wick > body * wick_ratio:
            for j in range(max(0, i - lookback), i):
                if ohlcv[j]['h'] < bar['h'] and i - j <= 3:
                    # Verified: breaks swing high
                    sig = Signal(
                        type='SweepDown', idx=i, direction='bull',
                        price=round((bar['h'] + max(bar['c'], bar['o'])) / 2, 2),
                        upper=bar['h'], lower=min(bar['c'], bar['o']),
                        timeframe=tf, confirmed_at=i,
                        volume_ratio=round(bar['v'] / vol_median, 2) if vol_median > 0 else 1,
                    )
                    sig.strength = 3.0 + (2.0 if at_swing else 0)
                    sig.confidence = 0.5 + (0.2 if at_swing else 0)
                    sig.metadata = {'wick_ratio': round(wick_ratio_val, 1), 'at_swing': at_swing}
                    signals.append(sig)
                    break

        # SweepUp (bearish) - lower wick breaks below recent LL
        if lower_wick >= body * 2 and lower_wick > body * wick_ratio:
            for j in range(max(0, i - lookback), i):
                if ohlcv[j]['l'] > bar['l'] and i - j <= 3:
                    sig = Signal(
                        type='SweepUp', idx=i, direction='bear',
                        price=round((bar['l'] + min(bar['c'], bar['o'])) / 2, 2),
                        upper=max(bar['c'], bar['o']), lower=bar['l'],
                        timeframe=tf, confirmed_at=i,
                        volume_ratio=round(bar['v'] / vol_median, 2) if vol_median > 0 else 1,
                    )
                    sig.strength = 3.0 + (2.0 if at_swing else 0)
                    sig.confidence = 0.5 + (0.2 if at_swing else 0)
                    sig.metadata = {'wick_ratio': round(wick_ratio_val, 1), 'at_swing': at_swing}
                    signals.append(sig)
                    break

    signals.sort(key=lambda s: s.idx)
    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 6. MSS检测 (复用V11逻辑)
# ═══════════════════════════════════════════════════════════════════════

def detect_mss_v14(ohlcv: List[Dict], lookback: int = 10,
                   min_confirm: int = 1, tf: str = 'daily') -> List[Dict]:
    """MSS — 微结构转变 (复用V11)"""
    n = len(ohlcv)
    if n < 10:
        return []
    signals = []
    local_window = 3

    for i in range(lookback, n - min_confirm - 1):
        start = i - local_window
        recent_high = max(ohlcv[j]['h'] for j in range(max(0, start), i))
        recent_low = min(ohlcv[j]['l'] for j in range(max(0, start), i))
        bar = ohlcv[i]

        if bar['c'] > recent_high and bar['h'] > recent_high:
            confirmed = True
            for c in range(1, min_confirm + 1):
                if i + c >= n:
                    break
                if ohlcv[i + c]['c'] < recent_high:
                    confirmed = False
                    break
            if not confirmed:
                continue
            break_strength = (bar['c'] - recent_high) / recent_high * 100 if recent_high > 0 else 0
            if break_strength < 0.2:
                continue
            sig = Signal(
                type='MSS_Bull', idx=i, direction='bull',
                price=bar['c'], upper=bar['h'], lower=recent_high,
                strength=min(4.0, 1.5 + break_strength),
                confidence=min(0.45, 0.25 + break_strength / 20),
                timeframe=tf, confirmed_at=i + min_confirm,
                metadata={'break_level': round(recent_high, 4), 'break_strength': round(break_strength, 2)},
            )
            signals.append(sig)

        elif bar['c'] < recent_low and bar['l'] < recent_low:
            confirmed = True
            for c in range(1, min_confirm + 1):
                if i + c >= n:
                    break
                if ohlcv[i + c]['c'] > recent_low:
                    confirmed = False
                    break
            if not confirmed:
                continue
            break_strength = (recent_low - bar['c']) / recent_low * 100 if recent_low > 0 else 0
            if break_strength < 0.2:
                continue
            sig = Signal(
                type='MSS_Bear', idx=i, direction='bear',
                price=bar['c'], upper=recent_low, lower=bar['l'],
                strength=min(4.0, 1.5 + break_strength),
                confidence=min(0.45, 0.25 + break_strength / 20),
                timeframe=tf, confirmed_at=i + min_confirm,
                metadata={'break_level': round(recent_low, 4), 'break_strength': round(break_strength, 2)},
            )
            signals.append(sig)

    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 7. EQL检测 (Pine-style: 基于摆动点, 非暴力扫描)
# ═══════════════════════════════════════════════════════════════════════

def detect_eql_v14(ohlcv: List[Dict], swings: Dict = None,
                   tolerance_pct: float = 0.6,
                   tf: str = 'daily') -> List[Dict]:
    """EQL检测 — 基于摆动点

    使用价格区间分组: 将相近价格的摆动点归为一组,
    组内有多个摆动点则标记为EQL。

    tolerance: 两个摆动点价格相差不超过tolerance_pct才算相近。
    daily用0.6%, 60min用1.0%。
    """
    if swings is None:
        swings = detect_swings_v14(ohlcv)

    signals = []
    swing_highs = swings.get('highs', [])
    swing_lows = swings.get('lows', [])
    max_gap = 25
    min_gap = 3

    # Equal highs: 按价格聚类的摆动高点
    if len(swing_highs) >= 2:
        # 按价格排序, 找相近组
        sorted_highs = sorted(swing_highs, key=lambda s: s['price'])
        groups = []
        current = [sorted_highs[0]]
        for s in sorted_highs[1:]:
            diff = abs(s['price'] - current[-1]['price']) / max(s['price'], 0.01) * 100
            if diff <= tolerance_pct:
                current.append(s)
            else:
                if len(current) >= 2:
                    groups.append(current)
                current = [s]
        if len(current) >= 2:
            groups.append(current)

        for grp in groups:
            level = min(s['price'] for s in grp)
            # 取组内最早的idx
            earliest = min(grp, key=lambda s: s['idx'])
            latest_idx = max(s['idx'] for s in grp)
            closeness = min(1.0, len(grp) * 0.2)
            sig = Signal(
                type='EQL_High', idx=latest_idx, direction='bear',
                price=round(level, 2), upper=round(level, 2), lower=round(level * 0.995, 2),
                strength=2.0 + closeness * 4.0,
                confidence=0.3 + closeness * 0.5,
                timeframe=tf, confirmed_at=latest_idx,
                metadata={'level': round(level, 4), 'count': len(grp)},
            )
            signals.append(sig)

    # Equal lows
    if len(swing_lows) >= 2:
        sorted_lows = sorted(swing_lows, key=lambda s: s['price'])
        groups = []
        current = [sorted_lows[0]]
        for s in sorted_lows[1:]:
            diff = abs(s['price'] - current[-1]['price']) / max(s['price'], 0.01) * 100
            if diff <= tolerance_pct:
                current.append(s)
            else:
                if len(current) >= 2:
                    groups.append(current)
                current = [s]
        if len(current) >= 2:
            groups.append(current)

        for grp in groups:
            level = max(s['price'] for s in grp)
            latest_idx = max(s['idx'] for s in grp)
            closeness = min(1.0, len(grp) * 0.2)
            sig = Signal(
                type='EQL_Low', idx=latest_idx, direction='bull',
                price=round(level, 2), upper=round(level * 1.005, 2), lower=round(level, 2),
                strength=2.0 + closeness * 4.0,
                confidence=0.3 + closeness * 0.5,
                timeframe=tf, confirmed_at=latest_idx,
                metadata={'level': round(level, 4), 'count': len(grp)},
            )
            signals.append(sig)

    # 去重: per unique level+direction
    signals.sort(key=lambda s: -s.strength)
    unique = []
    seen = set()
    for sig in signals:
        key = (round(sig.metadata.get('level', 0), 2), sig.direction)
        if key not in seen:
            seen.add(key)
            unique.append(sig)

    unique.sort(key=lambda s: s.idx)
    return [s.to_dict() for s in unique]


# ═══════════════════════════════════════════════════════════════════════
# 8-13. 其他信号类型 (复用V11, 简化)
# ═══════════════════════════════════════════════════════════════════════

def detect_bpr_v14(ohlcv: List[Dict], fvg_signals: List[Dict],
                   tf: str = 'daily') -> List[Dict]:
    """BPR — 复用V11"""
    if not fvg_signals or len(fvg_signals) < 2:
        return []
    bull_fvgs = [f for f in fvg_signals if 'Bull' in f.get('type', '')]
    bear_fvgs = [f for f in fvg_signals if 'Bear' in f.get('type', '')]
    if not bull_fvgs or not bear_fvgs:
        return []
    signals = []
    for bf in bull_fvgs:
        bf_idx = bf.get('idx', 0)
        bf_up = bf.get('upper', 0)
        bf_lo = bf.get('lower', 0)
        if bf_up <= 0 or bf_lo <= 0:
            continue
        for brf in bear_fvgs:
            brf_idx = brf.get('idx', 0)
            if brf_idx <= bf_idx or brf_idx > bf_idx + 30:
                continue
            brf_up = brf.get('upper', 0)
            brf_lo = brf.get('lower', 0)
            if brf_up <= 0 or brf_lo <= 0:
                continue
            if bf_up > brf_lo and bf_lo < brf_up:
                oh = min(bf_up, brf_up)
                ol = max(bf_lo, brf_lo)
                if oh > ol:
                    sig = Signal(
                        type='BPR', idx=brf_idx, direction='neutral',
                        price=(oh + ol) / 2, upper=oh, lower=ol,
                        grade=max(bf.get('grade', 1), brf.get('grade', 1)),
                        strength=min(8.0, bf.get('strength', 3) + brf.get('strength', 3)),
                        confidence=min(0.75, bf.get('confidence', 0.4) + brf.get('confidence', 0.4)),
                        timeframe=tf, confirmed_at=brf_idx,
                        metadata={'overlap_high': round(oh, 4), 'overlap_low': round(ol, 4)},
                    )
                    signals.append(sig)
                    break
    return [s.to_dict() for s in signals]


def detect_ifvg_v14(ohlcv: List[Dict], adaptive: Dict = None,
                    tf: str = 'daily') -> List[Dict]:
    """IFVG — 简化版, 复用V11核心"""
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    atr_pct = adaptive.get('atr_pct', 2.0)
    n = len(ohlcv)
    signals = []
    for i in range(1, n - 2):
        p, c1, c2 = ohlcv[i-1], ohlcv[i], ohlcv[i+1]
        # Implied gap: c1的影线中点 + c2的影线中点形成隐含缺口
        c1_mid = (c1['h'] + c1['l']) / 2
        c2_mid = (c2['h'] + c2['l']) / 2

        if c1['h'] < c2['l']:
            gap = c2['l'] - c1['h']
            gap_pct = gap / c1['c'] if c1['c'] > 0 else 0
            if gap_pct >= adaptive['fvg_min_width']:
                sig = Signal(
                    type='IFVG_Bull', idx=i, direction='bull',
                    price=(c1_mid + c2_mid) / 2, upper=c2['l'], lower=c1['h'],
                    strength=2.0, confidence=0.35, timeframe=tf, confirmed_at=i+1,
                    metadata={'gap_pct': round(gap_pct, 4)},
                )
                signals.append(sig)
        elif c1['l'] > c2['h']:
            gap = c1['l'] - c2['h']
            gap_pct = gap / c1['c'] if c1['c'] > 0 else 0
            if gap_pct >= adaptive['fvg_min_width']:
                sig = Signal(
                    type='IFVG_Bear', idx=i, direction='bear',
                    price=(c1_mid + c2_mid) / 2, upper=c1['l'], lower=c2['h'],
                    strength=2.0, confidence=0.35, timeframe=tf, confirmed_at=i+1,
                    metadata={'gap_pct': round(gap_pct, 4)},
                )
                signals.append(sig)
    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 14. 统一检测入口
# ═══════════════════════════════════════════════════════════════════════

def detect_all_signals_v14(ohlcv: List[Dict], params: Dict = None,
                           adaptive: Dict = None, tf: str = 'daily') -> Dict:
    """V14统一信号检测入口

    按以下顺序检测:
    1. 摆动点 (一次计算, 多处使用)
    2. FVG (基础信号)
    3. OB (基于摆动点)
    4. CHOCH (基于摆动点)
    5. Sweep
    6-13. MSS / EQL(基于摆动点) / BPR / IFVG / 其他

    设计原则: 共享摆动点计算结果, 避免重复扫描。
    """
    if params is None:
        params = {}
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)

    # 一次计算摆动点, 共享给OB/CHOCH/EQL
    swing_left = params.get('swing_left', 10 if 'daily' in tf else 8)
    swing_right = params.get('swing_right', 5 if 'daily' in tf else 3)
    swings = detect_swings_v14(ohlcv, left=swing_left, right=swing_right)

    # 1. FVG
    fvg_signals = detect_fvg_v14(ohlcv, adaptive=adaptive, tf=tf)

    # 2. Sweep
    sweep_signals = detect_sweep_v14(ohlcv, adaptive=adaptive, tf=tf)

    # 3. OB (基于摆动点)
    ob_signals = detect_ob_v14(ohlcv, swings=swings,
                               displacement_mult=params.get('ob_displacement_mult', 1.3),
                               adaptive=adaptive, tf=tf)

    # 4. CHOCH (基于摆动点)
    choch_signals = detect_choch_v14(ohlcv, swings=swings, tf=tf)

    # 5. BPR (基于FVG)
    bpr_signals = detect_bpr_v14(ohlcv, fvg_signals, tf=tf)

    # 6. MSS
    mss_signals = detect_mss_v14(ohlcv, tf=tf)

    # 7. EQL (基于摆动点)
    eql_signals = detect_eql_v14(ohlcv, swings=swings, tf=tf)

    # 8. IFVG
    ifvg_signals = detect_ifvg_v14(ohlcv, adaptive=adaptive, tf=tf)

    # 9. 其他辅助信号 (简化, 不复用所有14种)
    # 只保留核心9种: FVG/OB/Sweep/CHOCH/MSS/EQL/BPR/IFVG/(Swing本身就是线)
    # 去掉: OTE/PO3/LV/RJ/Breaker/IFVG(已保留)/MitigatedFVG

    # 合并
    all_signals = (fvg_signals + ob_signals + sweep_signals + choch_signals +
                   bpr_signals + mss_signals + eql_signals + ifvg_signals)
    all_signals.sort(key=lambda s: s.get('idx', 0))

    # 统计
    stats = {
        'total': len(all_signals),
        'fvg': len(fvg_signals),
        'ob': len(ob_signals),
        'sweep': len(sweep_signals),
        'choch': len(choch_signals),
        'bpr': len(bpr_signals),
        'mss': len(mss_signals),
        'eql': len(eql_signals),
        'ifvg': len(ifvg_signals),
        'bull': sum(1 for s in all_signals if s.get('direction') == 'bull'),
        'bear': sum(1 for s in all_signals if s.get('direction') == 'bear'),
    }

    for i, sig in enumerate(all_signals):
        sig['seq'] = i

    return {
        'fvg': fvg_signals,
        'ob': ob_signals,
        'sweep': sweep_signals,
        'choch': choch_signals,
        'bpr': bpr_signals,
        'mss': mss_signals,
        'eql': eql_signals,
        'ifvg': ifvg_signals,
        'all': all_signals,
        'adaptive': adaptive,
        'swings': {'highs': [s['idx'] for s in swings['highs']], 'lows': [s['idx'] for s in swings['lows']]},
        'stats': stats,
    }
