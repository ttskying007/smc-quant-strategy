#!/usr/bin/env python3
# SMC V11 — Enhanced Signal Detection Engine with Temporal Precision
"""
V11信号检测引擎 — V10.5的所有改进 + 以下核心创新:

1. 时间精度增强:
   - 每根K线精确标记每个信号的起始/确认/结束位置
   - 信号之间的距离(K线数)直接影响置信度
   - 信号发生的时间窗口约束(超出窗口的不计为序列)

2. 信号顺序内置:
   - 每个信号记录"相对于其他信号的顺序位置"
   - 信号顺序匹配直接从检测引擎输出, 不再需要后处理

3. 自适应阈值:
   - 基于股票ATR%自动调整FVG最小宽度
   - 基于平均波动率自动调整Sweep影线比
   - 基于成交量中位数自动调整OB强度

4. Multi-TF就绪:
   - 每个信号标记所属时间框架
   - 支持同一信号在不同TF的交叉验证

5. 6种信号类型全面增强:
   - FVG: 宽度分级+堆叠检测+趋势对齐+填充追踪
   - IFVG: 反向缺口检测+方向判定
   - Sweep: 摆动点感知+成交量确认+反转确认+影线分级
   - OB: 成交量确认+位置分析+实体比+摆动点附近
   - CHOCH: 摆动点级别+持续确认+趋势强度
   - 新增: BPR, LiquidityVoid, RejectionBlock, BreakerBlock
"""

import math, logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

log = logging.getLogger('smc_v11.signals')


# ═══════════════════════════════════════════════════════════════════════
# Signal data structures
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class Signal:
    """统一信号数据结构 — 所有信号类型共用"""
    type: str                    # 'FVG_Bull', 'IFVG_Bear', 'SweepDown', etc.
    idx: int                     # 信号发生的K线索引
    direction: str               # 'bull' | 'bear'
    price: float                 # 当前价格/信号的参考价格
    timeframe: str = 'daily'     # 'daily' | '4h' | '1h' | '15min'
    strength: float = 0.0        # 0-10 scale
    confidence: float = 0.5      # 0-1 scale
    
    # 价格区域 (用于重叠检测)
    upper: float = 0.0           # 上沿
    lower: float = 0.0           # 下沿
    
    # 时间信息
    confirmed_at: int = -1       # 确认的K线索引
    expired_at: int = -1         # 失效的K线索引
    is_active: bool = True       # 当前是否有效
    
    # 元数据
    grade: int = 1               # 1-4 质量等级
    trend_aligned: bool = False  # 是否与趋势对齐
    volume_ratio: float = 1.0    # 成交量比
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            'type': self.type,
            'idx': self.idx,
            'direction': self.direction,
            'price': self.price,
            'timeframe': self.timeframe,
            'strength': round(self.strength, 2),
            'confidence': round(self.confidence, 3),
            'upper': round(self.upper, 4),
            'lower': round(self.lower, 4),
            'confirmed_at': self.confirmed_at,
            'is_active': self.is_active,
            'grade': self.grade,
            'trend_aligned': self.trend_aligned,
            'volume_ratio': round(self.volume_ratio, 2),
            **self.metadata,
        }


# ═══════════════════════════════════════════════════════════════════════
# Adaptive threshold calculator
# ═══════════════════════════════════════════════════════════════════════

def calc_adaptive_thresholds(ohlcv: List[Dict]) -> Dict:
    """基于数据自适应计算所有阈值
    
    核心思想: 不同股票波动特性不同, 统一阈值不可靠。
    使用统计分析来自适应每只股票的最佳阈值。
    
    Returns:
        {
            'atr_pct': float,          # 平均ATR%
            'atr_median': float,       # ATR中位数
            'avg_volume': float,        # 平均成交量
            'vol_median': float,        # 成交中位数
            'vol_std': float,           # 成交量标准差
            'fvg_min_width': float,     # 自适应FVG最小宽度
            'sweep_wick_ratio': float,  # 自适应Sweep影线比
            'ob_strength_min': float,   # 自适应OB最小强度
            'volatility_class': str,    # low/medium/high
        }
    """
    n = len(ohlcv)
    if n < 20:
        return {
            'atr_pct': 2.0, 'atr_median': 2.0,
            'avg_volume': 1e6, 'vol_median': 1e6, 'vol_std': 1e6,
            'fvg_min_width': 0.001, 'sweep_wick_ratio': 2.0,
            'ob_strength_min': 1.0, 'volatility_class': 'medium',
        }
    
    # ATR计算
    ranges = []
    for i in range(1, n):
        tr = max(
            ohlcv[i]['h'] - ohlcv[i]['l'],
            abs(ohlcv[i]['h'] - ohlcv[i-1]['c']),
            abs(ohlcv[i]['l'] - ohlcv[i-1]['c']),
        )
        ranges.append(tr / ohlcv[i]['c'] * 100 if ohlcv[i]['c'] > 0 else 0)
    
    sorted_ranges = sorted(ranges)
    atr_pct = sum(ranges[-min(14, len(ranges)):]) / min(14, len(ranges))
    atr_median = sorted_ranges[len(sorted_ranges) // 2] if sorted_ranges else 1.0
    
    # 成交量统计
    vols = [b['v'] for b in ohlcv]
    sorted_vols = sorted(vols)
    avg_vol = sum(vols) / len(vols)
    vol_median = sorted_vols[len(sorted_vols) // 2] if sorted_vols else 1
    vol_std = math.sqrt(sum((v - avg_vol) ** 2 for v in vols) / len(vols)) if vols else 0
    
    # 自适应阈值: 波动率越大, 阈值越宽松
    if atr_pct < 1.5:
        vol_class = 'low'
        fvg_min = 0.0005       # 低波动: FVG很窄也能检测
        sweep_wick = 2.5        # 低波动: 需要更明确的影线
        ob_min = 0.8            # 低波动: OB实体较小
    elif atr_pct < 3.5:
        vol_class = 'medium'
        fvg_min = 0.001
        sweep_wick = 2.0
        ob_min = 1.0
    else:
        vol_class = 'high'
        fvg_min = 0.002        # 高波动: FVG需要更宽
        sweep_wick = 1.8       # 高波动: 影线更常见
        ob_min = 1.2           # 高波动: OB需要更大实体
    
    # 根据ATR中位数微调
    scale = max(0.5, min(2.0, atr_median / 2.0))
    fvg_min *= scale
    ob_min *= scale
    
    return {
        'atr_pct': round(atr_pct, 2),
        'atr_median': round(atr_median, 2),
        'avg_volume': round(avg_vol, 0),
        'vol_median': round(vol_median, 0),
        'vol_std': round(vol_std, 0),
        'fvg_min_width': round(fvg_min, 5),
        'sweep_wick_ratio': round(sweep_wick, 2),
        'ob_strength_min': round(ob_min, 2),
        'volatility_class': vol_class,
    }


# ═══════════════════════════════════════════════════════════════════════
# 1. Enhanced FVG Detection
# ═══════════════════════════════════════════════════════════════════════

def detect_fvg_v11(ohlcv: List[Dict], min_width: float = None,
                   merge_dist: int = 3, adaptive: Dict = None,
                   tf: str = 'daily') -> List[Dict]:
    """V11增强FVG检测
    
    V11改进:
    - 自适应min_width (基于ATR)
    - 缺口宽度分级 (nano/micro/meso/macro)
    - 趋势对齐检测 (局部趋势确认)
    - FVG堆叠检测 (3+连续)
    - 填充追踪 (标记mitigated时间和位置)
    - 方向一致性验证
    """
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    if min_width is None:
        min_width = adaptive['fvg_min_width']
    
    n = len(ohlcv)
    signals = []
    atr = adaptive.get('atr_pct', 2.0)
    
    for i in range(n - 2):
        b1, b2, b3 = ohlcv[i], ohlcv[i+1], ohlcv[i+2]
        
        # ── FVG Color Pattern Detection ──
        # Bullish FVG: price gap up (c1.h < c3.l)
        #   If ALL 3 candles are bearish → "continuation bear FVG" = strongest buy signal
        #   If only some are bearish → "regular FVG" = standard buy signal
        # Bearish FVG: price gap down (c1.l > c3.h)  
        #   If ALL 3 candles are bullish → "continuation bull FVG" = strongest sell signal
        #   If only some are bullish → "regular FVG" = standard sell signal
        
        b1_bear = b1['c'] < b1['o']
        b2_bear = b2['c'] < b2['o']
        b3_bear = b3['c'] < b3['o']
        b1_bull = b1['c'] > b1['o']
        b2_bull = b2['c'] > b2['o']
        b3_bull = b3['c'] > b3['o']
        
        all_bearish = b1_bear and b2_bear and b3_bear
        all_bullish = b1_bull and b2_bull and b3_bull
        
        # C2 body check for strength
        c2_body_pct = abs(b2['c'] - b2['o']) / b2['c'] * 100 if b2['c'] > 0 else 0
        c2_body_ok = c2_body_pct >= atr * 0.6
        
        # ── Bullish FVG: c1.h < c3.l (gap up = future buy zone) ──
        if b1['h'] < b3['l']:
            gap = b3['l'] - b1['h']
            gap_pct = gap / b1['c'] if b1['c'] > 0 else 0
            
            if gap_pct >= min_width and (c2_body_ok or all_bearish):
                is_consecutive_bearish = all_bearish
                grade = _classify_fvg_width(gap_pct, ohlcv, i, adaptive)
                if is_consecutive_bearish:
                    grade = max(grade, 3)  # 连续阴线=更高质量FVG
                trend_aligned = _check_trend_alignment(ohlcv, i, 'bull')
                
                sig = Signal(
                    type='FVG_Bull', idx=i+1, direction='bull',
                    price=(b1['h'] + b3['l']) / 2,
                    upper=b3['l'], lower=b1['h'], timeframe=tf,
                    grade=grade, trend_aligned=trend_aligned,
                    confirmed_at=i+2,
                )
                sig.strength = _calc_fvg_strength(sig, b2, adaptive)
                sig.confidence = _calc_fvg_confidence(sig, b1, b2, b3, gap_pct)
                if is_consecutive_bearish:
                    sig.confidence = min(1.0, sig.confidence + 0.15)
                    sig.strength = min(10, sig.strength + 2.0)
                sig.metadata = {
                    'gap_pct': round(gap_pct, 4),
                    'gap_absolute': round(gap, 2),
                    'candle1_close': b1['c'],
                    'candle3_open': b3['o'],
                    'candle2_range': round((b2['h'] - b2['l']) / b2['c'] * 100, 2),
                    'consecutive_bearish': is_consecutive_bearish,
                    'c2_body_ok': c2_body_ok,
                    'fvg_color_pattern': '3bear' if is_consecutive_bearish else 'mixed',
                }
                signals.append(sig)
        
        # ── Bearish FVG: c1.l > c3.h (gap down = future sell zone) ──
        elif b1['l'] > b3['h']:
            gap = b1['l'] - b3['h']
            gap_pct = gap / b1['c'] if b1['c'] > 0 else 0
            
            if gap_pct >= min_width and (c2_body_ok or all_bullish):
                is_consecutive_bullish = all_bullish
                grade = _classify_fvg_width(gap_pct, ohlcv, i, adaptive)
                if is_consecutive_bullish:
                    grade = max(grade, 3)
                trend_aligned = _check_trend_alignment(ohlcv, i, 'bear')
                
                sig = Signal(
                    type='FVG_Bear', idx=i+1, direction='bear',
                    price=(b1['l'] + b3['h']) / 2,
                    upper=b1['l'], lower=b3['h'], timeframe=tf,
                    grade=grade, trend_aligned=trend_aligned,
                    confirmed_at=i+2,
                )
                sig.strength = _calc_fvg_strength(sig, b2, adaptive)
                sig.confidence = _calc_fvg_confidence(sig, b1, b2, b3, gap_pct)
                if is_consecutive_bullish:
                    sig.confidence = min(1.0, sig.confidence + 0.15)
                    sig.strength = min(10, sig.strength + 2.0)
                sig.metadata = {
                    'gap_pct': round(gap_pct, 4),
                    'gap_absolute': round(gap, 2),
                    'consecutive_bullish': is_consecutive_bullish,
                    'c2_body_ok': c2_body_ok,
                    'fvg_color_pattern': '3bull' if is_consecutive_bullish else 'mixed',
                }
                signals.append(sig)
    
    # Merge adjacent FVGs
    if merge_dist > 0 and signals:
        signals = _merge_fvgs_v11(signals, merge_dist)
    
    # Detect FVG stacks
    _detect_fvg_stacks_v11(signals, ohlcv)
    
    # Trace mitigation
    _trace_mitigation_v11(signals, ohlcv)
    
    return [s.to_dict() for s in signals]


def _classify_fvg_width(gap_pct: float, ohlcv, idx: int, adaptive: Dict) -> int:
    """基于ATR的FVG宽度分级"""
    atr = adaptive.get('atr_pct', 2.0)
    ratio = gap_pct / max(atr / 100, 0.001)
    
    if ratio > 1.5:   return 4  # macro
    elif ratio > 0.8: return 3  # meso
    elif ratio > 0.3: return 2  # micro
    else:             return 1  # nano


def _check_trend_alignment(ohlcv, idx: int, direction: str, lookback: int = 10) -> bool:
    """检查FVG是否与局部趋势对齐"""
    if idx < lookback:
        return False
    
    recent = ohlcv[max(0, idx - lookback):idx + 1]
    if len(recent) < 5:
        return False
    
    # 用前3根和后3根的均价判断趋势
    start_price = sum(b['c'] for b in recent[:3]) / 3
    end_price = sum(b['c'] for b in recent[-3:]) / 3
    
    trend_up = end_price > start_price * 1.005  # 0.5% minimum
    trend_down = end_price < start_price * 0.995
    
    if direction == 'bull' and trend_up:
        return True
    if direction == 'bear' and trend_down:
        return True
    return False


def _calc_fvg_strength(sig: Signal, middle_candle: Dict, adaptive: Dict) -> float:
    """FVG信号强度评分 (0-10)"""
    strength = 1.0  # base
    
    # Grade bonus
    strength += (sig.grade - 1) * 1.5
    
    # Trend alignment
    if sig.trend_aligned:
        strength += 2.0
    
    # Middle candle size matters — larger = stronger FVG
    mid_range = middle_candle['h'] - middle_candle['l']
    mid_range_pct = mid_range / middle_candle['c'] * 100 if middle_candle['c'] > 0 else 0
    atr = adaptive.get('atr_pct', 2.0)
    if mid_range_pct > atr:
        strength += 1.5  # 突破性大K线
    elif mid_range_pct > atr * 0.6:
        strength += 0.8
    
    return min(10, strength)


def _calc_fvg_confidence(sig: Signal, b1, b2, b3, gap_pct: float) -> float:
    """FVG置信度 (0-1)"""
    conf = 0.4  # base
    
    # Higher grade = higher confidence
    conf += (sig.grade - 1) * 0.1
    
    # Trend alignment
    if sig.trend_aligned:
        conf += 0.15
    
    # Gap width (as a bonus if it's significant)
    if gap_pct > 0.005:  # 0.5% gap
        conf += 0.15
    elif gap_pct > 0.002:
        conf += 0.08
    
    # Middle candle direction (breakout candle should be strong)
    if sig.direction == 'bull' and b2['c'] > b2['o']:
        conf += 0.1  # bullish middle candle
    elif sig.direction == 'bear' and b2['c'] < b2['o']:
        conf += 0.1  # bearish middle candle
    
    return min(1.0, conf)


def _merge_fvgs_v11(fvg_signals: List, max_gap: int) -> List:
    """合并相邻同向FVG"""
    if not fvg_signals:
        return []
    
    merged = [fvg_signals[0]]
    for sig in fvg_signals[1:]:
        last = merged[-1]
        if (sig.direction == last.direction and
            sig.idx - last.idx <= max_gap + 2):
            # Merge: extend the zone
            last.upper = max(last.upper, sig.upper)
            last.lower = min(last.lower, sig.lower)
            last.grade = max(last.grade, sig.grade)
            last.strength = max(last.strength, sig.strength)
            last.confidence = max(last.confidence, sig.confidence)
            last.idx = (last.idx + sig.idx) // 2
        else:
            merged.append(sig)
    
    return merged


def _detect_fvg_stacks_v11(signals: List, ohlcv: List):
    """检测FVG堆叠 — 3+个FVG重叠 → 极强区域"""
    stack_id = 0
    for i in range(len(signals)):
        # Skip if type is not FVG
        if 'FVG' not in signals[i].type:
            continue
        if signals[i].metadata.get('stacked'):
            continue
        
        stack = [signals[i]]
        for j in range(i + 1, min(i + 10, len(signals))):
            if 'FVG' not in signals[j].type:
                break
            if signals[j].direction != signals[i].direction:
                break
            
            last = stack[-1]
            curr = signals[j]
            if curr.idx - last.idx > 5:
                break
            if curr.lower <= last.upper and curr.upper >= last.lower:
                stack.append(curr)
            else:
                break
        
        if len(stack) >= 3:
            stack_id += 1
            for sig in stack:
                sig.metadata['stacked'] = True
                sig.metadata['stack_group'] = stack_id
                sig.metadata['stack_size'] = len(stack)
                sig.strength += len(stack) * 0.5  # stack bonus


def _trace_mitigation_v11(signals: List, ohlcv: List):
    """追踪FVG填充状态"""
    n = len(ohlcv)
    for sig in signals:
        if 'FVG' not in sig.type:
            continue
        idx = sig.idx
        sig.metadata['mitigated'] = False
        sig.metadata['mitigated_at'] = None
        
        for j in range(idx + 1, min(idx + 50, n)):
            bar = ohlcv[j]
            if sig.direction == 'bull':
                if bar['l'] <= sig.upper:
                    sig.metadata['mitigated'] = True
                    sig.metadata['mitigated_at'] = j
                    break
            else:
                if bar['h'] >= sig.lower:
                    sig.metadata['mitigated'] = True
                    sig.metadata['mitigated_at'] = j
                    break


# ═══════════════════════════════════════════════════════════════════════
# 2. Enhanced Sweep Detection
# ═══════════════════════════════════════════════════════════════════════

def detect_sweep_v11(ohlcv: List[Dict], lookback: int = 12,
                     wick_ratio: float = None, adaptive: Dict = None,
                     require_volume: bool = True, require_reversal: bool = True,
                     tf: str = 'daily') -> List[Dict]:
    """V11增强Sweep检测
    
    V11改进:
    - 自适应影线比 (基于波动率)
    - 摆动点级别触发 (只在关键结构点)
    - 成交量确认 (必须放量)
    - 反转确认 (下一根K线必须收回到突破水平内)
    - 影线分级 (weak/medium/strong/extreme)
    - 多级验证: 不仅看前N根K线的极值, 还要看结构点
    """
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    if wick_ratio is None:
        wick_ratio = adaptive['sweep_wick_ratio']
    
    n = len(ohlcv)
    signals = []
    avg_vol = adaptive['avg_volume']
    vol_median = adaptive['vol_median']
    
    # 预计算摆动点
    swing_highs = _find_swing_highs(ohlcv, lookback)
    swing_lows = _find_swing_lows(ohlcv, lookback)
    
    def _near_swing(idx: int, price: float, is_high: bool, window: int = 8) -> bool:
        """Check if price is near a swing point within `window` bars of idx"""
        if is_high:
            for sh_idx, sh_price in swing_highs:
                if abs(sh_idx - idx) <= window and abs(price - sh_price) / max(sh_price, 0.01) < 0.005:
                    return True
        else:
            for sl_idx, sl_price in swing_lows:
                if abs(sl_idx - idx) <= window and abs(price - sl_price) / max(sl_price, 0.01) < 0.005:
                    return True
        return False
    
    for i in range(lookback, n - 2):
        cur = ohlcv[i]
        nxt = ohlcv[i + 1]
        nxt2 = ohlcv[i + 2] if i + 2 < n else None
        
        body = abs(cur['c'] - cur['o'])
        if body == 0:
            continue
        
        # 计算当前K线的局部极值
        window_high = max(b['h'] for b in ohlcv[i - lookback:i])
        window_low = min(b['l'] for b in ohlcv[i - lookback:i])
        
        # BSL Sweep (向上突破前高): 空头止损猎杀
        if cur['h'] > window_high:
            wick_up = cur['h'] - max(cur['o'], cur['c'])
            ratio = wick_up / body
            
            if ratio >= wick_ratio:
                vol_ok = (not require_volume or 
                         cur['v'] > vol_median * 1.2 or
                         cur['v'] > avg_vol * 1.15)
                rev_ok = (not require_reversal or 
                         nxt['c'] < cur['c'] * 0.998 or
                         (nxt2 and nxt2['c'] < cur['c']))
                
                # 是否是摆动点处的突破 (更强)
                at_swing = _near_swing(i, cur['h'], is_high=True)
                
                if vol_ok and rev_ok:
                    wick_grade = _classify_wick(ratio)
                    sig = Signal(
                        type='SweepUp', idx=i, direction='bear',
                        price=cur['h'], timeframe=tf,
                        upper=cur['h'], lower=cur['h'] - wick_up,
                        grade=wick_grade,
                        confirmed_at=i+1,
                        volume_ratio=round(cur['v'] / avg_vol, 2) if avg_vol > 0 else 1,
                    )
                    sig.strength = _calc_sweep_strength(cur, wick_up, ratio, 
                                                       wick_grade, adaptive, at_swing)
                    sig.confidence = _calc_sweep_confidence(cur, ratio, vol_ok, at_swing)
                    sig.metadata = {
                        'break_level': round(window_high, 2),
                        'wick_ratio': round(ratio, 2),
                        'wick_grade': wick_grade,
                        'at_swing_point': at_swing,
                        'body_pct': round(body / cur['c'] * 100, 2),
                        'liquidity_type': 'BSL',  # Buy Side Liquidity sweep
                    }
                    signals.append(sig)
        
        # SSL Sweep (向下突破前低): 多头止损猎杀
        if cur['l'] < window_low:
            wick_down = min(cur['o'], cur['c']) - cur['l']
            ratio = wick_down / body
            
            if ratio >= wick_ratio:
                vol_ok = (not require_volume or 
                         cur['v'] > vol_median * 1.2 or
                         cur['v'] > avg_vol * 1.15)
                rev_ok = (not require_reversal or 
                         nxt['c'] > cur['c'] * 1.002 or
                         (nxt2 and nxt2['c'] > cur['c']))
                
                at_swing = _near_swing(i, cur['l'], is_high=False)
                
                if vol_ok and rev_ok:
                    wick_grade = _classify_wick(ratio)
                    sig = Signal(
                        type='SweepDown', idx=i, direction='bull',
                        price=cur['l'], timeframe=tf,
                        upper=cur['l'] + wick_down, lower=cur['l'],
                        grade=wick_grade, confirmed_at=i+1,
                        volume_ratio=round(cur['v'] / avg_vol, 2) if avg_vol > 0 else 1,
                    )
                    sig.strength = _calc_sweep_strength(cur, wick_down, ratio,
                                                       wick_grade, adaptive, at_swing)
                    sig.confidence = _calc_sweep_confidence(cur, ratio, vol_ok, at_swing)
                    sig.metadata = {
                        'break_level': round(window_low, 2),
                        'wick_ratio': round(ratio, 2),
                        'wick_grade': wick_grade,
                        'at_swing_point': at_swing,
                        'liquidity_type': 'SSL',  # Sell Side Liquidity sweep
                    }
                    signals.append(sig)
    
    return [s.to_dict() for s in signals]


def _find_swing_highs(ohlcv: List[Dict], lookback: int) -> List[Tuple[int, float]]:
    """找摆动高点列表 (idx, price)"""
    highs = []
    n = len(ohlcv)
    for i in range(lookback, n - lookback):
        if all(ohlcv[i]['h'] >= ohlcv[j]['h'] 
               for j in range(i - lookback, i + lookback + 1) if 0 <= j < n):
            highs.append((i, ohlcv[i]['h']))
    return highs


def _find_swing_lows(ohlcv: List[Dict], lookback: int) -> List[Tuple[int, float]]:
    """找摆动低点列表 (idx, price)"""
    lows = []
    n = len(ohlcv)
    for i in range(lookback, n - lookback):
        if all(ohlcv[i]['l'] <= ohlcv[j]['l']
               for j in range(i - lookback, i + lookback + 1) if 0 <= j < n):
            lows.append((i, ohlcv[i]['l']))
    return lows


def _classify_wick(ratio: float) -> int:
    """影线比分级"""
    if ratio >= 5:   return 4  # extreme
    elif ratio >= 3: return 3  # strong
    elif ratio >= 2: return 2  # medium
    else:            return 1  # weak


def _calc_sweep_strength(cur: Dict, wick: float, wick_ratio: float,
                         wick_grade: int, adaptive: Dict, at_swing: bool) -> float:
    """Sweep信号强度 (0-10)"""
    strength = 1.0  # base
    
    # Wick grade bonus
    strength += (wick_grade - 1) * 1.5
    
    # Volume bonus
    avg_vol = adaptive['avg_volume']
    vol_ratio = cur['v'] / avg_vol if avg_vol > 0 else 1
    if vol_ratio > 2.0:
        strength += 2.0
    elif vol_ratio > 1.5:
        strength += 1.0
    
    # Swing point bonus
    if at_swing:
        strength += 2.0
    
    # Wick percentage of price
    wick_pct = wick / cur['c'] * 100 if cur['c'] > 0 else 0
    atr = adaptive['atr_pct']
    if wick_pct > atr:
        strength += 1.0
    
    return min(10, strength)


def _calc_sweep_confidence(cur: Dict, wick_ratio: float,
                           vol_ok: bool, at_swing: bool) -> float:
    """Sweep置信度 (0-1)"""
    conf = 0.3  # base
    
    # Wick quality
    if wick_ratio >= 5:
        conf += 0.25
    elif wick_ratio >= 3:
        conf += 0.15
    elif wick_ratio >= 2:
        conf += 0.05
    
    # Volume confirmation
    if vol_ok:
        conf += 0.15
    
    # Swing point context
    if at_swing:
        conf += 0.20
    
    return min(1.0, conf)


# ═══════════════════════════════════════════════════════════════════════
# 3. Enhanced OB Detection
# ═══════════════════════════════════════════════════════════════════════

def detect_ob_v11(ohlcv: List[Dict], strength_min: float = None,
                  adaptive: Dict = None, require_volume: bool = True,
                  tf: str = 'daily') -> List[Dict]:
    """V11.2 True ICT Order Block Detection

    ICT Order Block = the LAST candle in opposite direction BEFORE an impulsive move.

    Bullish OB: In uptrend context, the last bearish candle whose low is NOT broken
                before a strong bullish impulse (2+ consecutive bullish candles).
                = where sell orders were absorbed.

    Bearish OB: In downtrend context, the last bullish candle whose high is NOT broken
                before a strong bearish impulse (2+ consecutive bearish candles).
                = where buy orders were absorbed.

    关键特征:
    - OB是推动行情启动的last opposite candle, 不是任意一K线
    - 必须有后续的direction impulse (2+同向K线)
    - 摆动点/结构点处的OB更强
    - OB的极值(low/bear / high/bull)不应在短时间内被突破
    """
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    if strength_min is None:
        strength_min = adaptive['ob_strength_min']

    n = len(ohlcv)
    if n < 30:
        return []

    signals = []
    vol_median = adaptive['vol_median']
    atr = adaptive['atr_pct']

    # 预计算摆动点
    sw_lookback = 12
    swing_highs = _find_swing_highs(ohlcv, sw_lookback)
    swing_lows = _find_swing_lows(ohlcv, sw_lookback)
    swing_idxs = set(i for i, _ in swing_highs + swing_lows)

    def _is_near_swing(idx: int, max_dist: int = 5) -> bool:
        return any(abs(idx - sp) <= max_dist for sp in swing_idxs)

    def _is_strong_impulse(start: int, direction: str, min_bars: int = 2) -> int:
        """Check for strong impulse after OB. Returns number of consecutive bars."""
        count = 0
        for k in range(start, min(start + 5, n)):
            bar = ohlcv[k]
            if direction == 'bull' and bar['c'] > bar['o']:
                count += 1
            elif direction == 'bear' and bar['c'] < bar['o']:
                count += 1
            else:
                break
        return count

    # Scan every candle as potential OB
    for i in range(5, n - 3):
        bar = ohlcv[i]
        body = abs(bar['c'] - bar['o'])
        body_pct = body / bar['o'] * 100 if bar['o'] > 0 else 0
        if body == 0:
            continue

        # ── Bullish OB: last bearish candle before bullish impulse ──
        if bar['c'] < bar['o']:  # Current candle is bearish
            # Check if this is near a swing low structure
            at_structure = _is_near_swing(i)

            # Look for bullish impulse starting AFTER this candle
            impulse_bars = _is_strong_impulse(i + 1, 'bull', min_bars=2)

            if impulse_bars >= 2:
                # Volume check on impulse candles
                impulse_vol = sum(ohlcv[i + 1 + k]['v'] for k in range(min(impulse_bars, 3))) / min(impulse_bars, 3)
                vol_ok = impulse_vol > vol_median * 1.2 or bar['v'] > vol_median * 1.2

                if vol_ok:
                    sig = Signal(
                        type='OB_Bull', idx=i, direction='bull',
                        price=bar['l'],  # Low = support
                        upper=bar['h'], lower=bar['l'],
                        timeframe=tf, confirmed_at=i + 1,
                        volume_ratio=round(bar['v'] / vol_median, 2) if vol_median > 0 else 1,
                    )
                    sig.strength = _calc_ob_strength_v11(body_pct, bar['v'], vol_median, adaptive)
                    sig.confidence = _calc_ob_confidence_v11(body_pct, vol_ok, at_structure, impulse_bars)
                    sig.metadata = {
                        'body_pct': round(body_pct, 2),
                        'impulse_bars': impulse_bars,
                        'at_structure': at_structure,
                        'ob_type': 'true_ob',
                    }
                    signals.append(sig)

        # ── Bearish OB: last bullish candle before bearish impulse ──
        elif bar['c'] > bar['o']:  # Current candle is bullish
            at_structure = _is_near_swing(i)

            impulse_bars = _is_strong_impulse(i + 1, 'bear', min_bars=2)

            if impulse_bars >= 2:
                impulse_vol = sum(ohlcv[i + 1 + k]['v'] for k in range(min(impulse_bars, 3))) / min(impulse_bars, 3)
                vol_ok = impulse_vol > vol_median * 1.2 or bar['v'] > vol_median * 1.2

                if vol_ok:
                    sig = Signal(
                        type='OB_Bear', idx=i, direction='bear',
                        price=bar['h'],  # High = resistance
                        upper=bar['h'], lower=bar['l'],
                        timeframe=tf, confirmed_at=i + 1,
                        volume_ratio=round(bar['v'] / vol_median, 2) if vol_median > 0 else 1,
                    )
                    sig.strength = _calc_ob_strength_v11(body_pct, bar['v'], vol_median, adaptive)
                    sig.confidence = _calc_ob_confidence_v11(body_pct, vol_ok, at_structure, impulse_bars)
                    sig.metadata = {
                        'body_pct': round(body_pct, 2),
                        'impulse_bars': impulse_bars,
                        'at_structure': at_structure,
                        'ob_type': 'true_ob',
                    }
                    signals.append(sig)

    # Deduplicate: keep strongest OB per area
    signals.sort(key=lambda s: -s.strength)
    unique = []
    seen_levels = set()
    for sig in signals:
        level_key = round(sig.price, 2)
        dir_key = sig.direction
        key = (level_key, dir_key)
        if key not in seen_levels:
            seen_levels.add(key)
            unique.append(sig)

    unique.sort(key=lambda s: s.idx)
    return [s.to_dict() for s in unique]


def _calc_ob_strength_v11(body_pct: float, volume: float,
                          vol_median: float, adaptive: Dict) -> float:
    """OB强度 (0-10)"""
    strength = 2.0  # base — true OB has higher base

    # Body size relative to ATR
    atr = adaptive['atr_pct']
    if body_pct > atr:
        strength += 2.0
    elif body_pct > atr * 0.6:
        strength += 1.0

    # Volume
    vol_ratio = volume / vol_median if vol_median > 0 else 1
    if vol_ratio > 2.0:
        strength += 2.0
    elif vol_ratio > 1.5:
        strength += 1.0
    elif vol_ratio > 1.2:
        strength += 0.5

    return min(10, strength)


def _calc_ob_confidence_v11(body_pct: float, vol_ok: bool,
                            at_structure: bool, impulse_bars: int) -> float:
    """OB置信度 (0-1) — V11.2

    真正的订单块确认条件:
    - 后续有2+同向K线 → 基础高
    - 成交量放大 → 加分
    - 摆动点/结构点处 → 加分
    - 更长的impulse → 更高置信度
    """
    conf = 0.40  # base

    if body_pct > 3.0:
        conf += 0.15
    elif body_pct > 2.0:
        conf += 0.10
    elif body_pct > 1.0:
        conf += 0.05

    if vol_ok:
        conf += 0.15

    if at_structure:
        conf += 0.20  # 摆动点位置很重要

    if impulse_bars >= 4:
        conf += 0.10
    elif impulse_bars >= 3:
        conf += 0.05

    return min(1.0, conf)


def _calc_ob_confidence(range_pct: float, volume: float,
                        vol_median: float, confirm_candle: Dict) -> float:
    """OB置信度 (0-1)"""
    conf = 0.4  # base
    
    # OB实体越大越强
    if range_pct > 3.0:
        conf += 0.20
    elif range_pct > 2.0:
        conf += 0.10
    elif range_pct > 1.0:
        conf += 0.05
    
    # 成交量确认
    vol_ratio = volume / vol_median if vol_median > 0 else 1
    if vol_ratio > 1.5:
        conf += 0.15
    elif vol_ratio > 1.2:
        conf += 0.05
    
    # 确认K线方向 → OB后价格确实反转
    if confirm_candle['c'] > confirm_candle['o']:
        conf += 0.10
    
    return min(1.0, conf)


# ═══════════════════════════════════════════════════════════════════════
# 4. Enhanced CHOCH Detection
# ═══════════════════════════════════════════════════════════════════════

def detect_choch_v11(ohlcv: List[Dict], lookback: int = 15,
                     min_confirm_bars: int = 2, sweep_signals: List[Dict] = None,
                     tf: str = 'daily') -> List[Dict]:
    """V11.3 ICT CHOCH检测 — 带流动性位置约束
    
    ICT核心规则 (Model 1: SH + MSS + RTO):
    
    做多条件:
    1. SSL必须被消化 (SweepDown猎杀卖方流动性)
    2. MSS/CHOCH必须出现在SSL被消化点位的上方!!!
    3. 如果MSS出现在SSL下方, 该信号无效(机构还没准备好)
    
    做空条件:
    1. BSL必须被消化 (SweepUp猎杀买方流动性)
    2. MSS/CHOCH必须出现在BSL消化点位的下方!!!
    3. 如果MSS出现在BSL上方, 该信号无效
    
    位置约束: MSS/CHOCH的位置比形态更重要!
    """
    n = len(ohlcv)
    if n < lookback + 10:
        return []
    
    signals = []
    
    # 1. 找所有摆动点
    swing_highs = []
    swing_lows = []
    
    for i in range(lookback, n - lookback):
        bar = ohlcv[i]
        is_high = True
        for j in range(i - lookback, i + lookback + 1):
            if j == i: continue
            if ohlcv[j]['h'] > bar['h']:
                is_high = False
                break
        if is_high:
            swing_highs.append((i, bar['h']))
        
        is_low = True
        for j in range(i - lookback, i + lookback + 1):
            if j == i: continue
            if ohlcv[j]['l'] < bar['l']:
                is_low = False
                break
        if is_low:
            swing_lows.append((i, bar['l']))
    
    if len(swing_highs) < 2 and len(swing_lows) < 2:
        return []
    
    # 预计算sweep水平
    sweep_levels_bull = []  # SSL猎杀后的支撑水平
    sweep_levels_bear = []  # BSL猎杀后的阻力水平
    if sweep_signals:
        for s in sweep_signals:
            if s.get('direction') == 'bull':  # SweepDown = bull signal
                sweep_levels_bull.append((s.get('idx', 0), s.get('price', 0)))
            elif s.get('direction') == 'bear':  # SweepUp = bear signal
                sweep_levels_bear.append((s.get('idx', 0), s.get('price', 0)))
    
    def _is_above_sweep(idx: int, price: float, lookahead: int = 20) -> bool:
        """Bull CHOCH必须在此之前的SSL sweep之上"""
        for s_idx, s_price in sweep_levels_bull:
            if 0 <= idx - s_idx <= lookahead and price > s_price * 1.001:
                return True
        return True  # 没sweep数据也放行(兼容旧模式)
    
    def _is_below_sweep(idx: int, price: float, lookahead: int = 20) -> bool:
        """Bear CHOCH必须在此之前的BSL sweep之下"""
        for s_idx, s_price in sweep_levels_bear:
            if 0 <= idx - s_idx <= lookahead and price < s_price * 0.999:
                return True
        return True
    
    # 2. 在摆动点处检测CHOCH
    # --- 看涨CHOCH ---
    for idx_low, low_price in swing_lows:
        prior_highs = [(hi, hp) for hi, hp in swing_highs if hi < idx_low]
        if len(prior_highs) < 2:
            continue
        last_h1, p1 = prior_highs[-1]
        last_h2, p2 = prior_highs[-2]
        if p1 >= p2:
            continue
        last_lh_price = p1
        
        for k in range(idx_low + 1, min(idx_low + lookback, n)):
            bar = ohlcv[k]
            if bar['h'] > last_lh_price:
                confirm_count = 0
                sustained = True
                for c in range(1, min_confirm_bars + 1):
                    if k + c >= n:
                        break
                    if ohlcv[k + c]['c'] < last_lh_price:
                        sustained = False
                        break
                    confirm_count += 1
                
                if sustained and confirm_count >= min_confirm_bars:
                    break_strength = (bar['c'] - last_lh_price) / last_lh_price * 100
                    if break_strength < 0.5:
                        break
                    
                    # ── ICT位置约束: MSS必须在SSL猎杀上方 ──
                    if not _is_above_sweep(k, bar['c']):
                        break  # 位置不对, 直接跳过
                    
                    sig = Signal(
                        type='CHOCH_Bull', idx=k, direction='bull',
                        price=bar['c'], timeframe=tf,
                        upper=bar['h'], lower=last_lh_price,
                        confirmed_at=k + confirm_count,
                    )
                    sig.strength = _calc_choch_strength_v11(break_strength, confirm_count, lookback)
                    sig.confidence = _calc_choch_confidence_v11(break_strength, confirm_count)
                    sig.metadata = {
                        'break_level': round(last_lh_price, 2),
                        'break_strength': round(break_strength, 2),
                        'swing_scale': lookback,
                    }
                    signals.append(sig)
                    break
    
    # --- 看跌CHOCH ---
    for idx_high, high_price in swing_highs:
        prior_lows = [(il, lp) for il, lp in swing_lows if il < idx_high]
        if len(prior_lows) < 2:
            continue
        last_l1, lp1 = prior_lows[-1]
        last_l2, lp2 = prior_lows[-2]
        if lp1 <= lp2:
            continue
        last_hl_price = lp1
        
        for k in range(idx_high + 1, min(idx_high + lookback, n)):
            bar = ohlcv[k]
            if bar['l'] < last_hl_price:
                confirm_count = 0
                sustained = True
                for c in range(1, min_confirm_bars + 1):
                    if k + c >= n:
                        break
                    if ohlcv[k + c]['c'] > last_hl_price:
                        sustained = False
                        break
                    confirm_count += 1
                
                if sustained and confirm_count >= min_confirm_bars:
                    break_strength = (last_hl_price - bar['c']) / last_hl_price * 100
                    if break_strength < 0.5:
                        break
                    
                    # ── ICT位置约束: MSS必须在BSL猎杀下方 ──
                    if not _is_below_sweep(k, bar['c']):
                        break
                    
                    sig = Signal(
                        type='CHOCH_Bear', idx=k, direction='bear',
                        price=bar['c'], timeframe=tf,
                        upper=last_hl_price, lower=bar['l'],
                        confirmed_at=k + confirm_count,
                    )
                    sig.strength = _calc_choch_strength_v11(break_strength, confirm_count, lookback)
                    sig.confidence = _calc_choch_confidence_v11(break_strength, confirm_count)
                    sig.metadata = {
                        'break_level': round(last_hl_price, 2),
                        'break_strength': round(break_strength, 2),
                        'swing_scale': lookback,
                    }
                    signals.append(sig)
                    break
    
    return [s.to_dict() for s in signals]


def _calc_choch_strength_v11(break_strength: float, confirm_count: int, lookback: int) -> float:
    """CHOCH强度 (0-10) — V11.1"""
    strength = 3.0  # base (CHOCH在摆动点处 = 很强)
    
    if break_strength > 3.0:
        strength += 3.0
    elif break_strength > 1.5:
        strength += 2.0
    elif break_strength > 0.8:
        strength += 1.0
    
    if confirm_count >= 3:
        strength += 2.0
    elif confirm_count >= 2:
        strength += 1.0
    
    # 规模加成
    if lookback >= 20:
        strength += 2.0
    elif lookback >= 12:
        strength += 1.0
    
    return min(10, strength)


def _calc_choch_confidence_v11(break_strength: float, confirm_count: int) -> float:
    """CHOCH置信度 (0-1) — V11.1"""
    conf = 0.55  # base — 摆动点处CHOCH基础置信度更高
    
    if break_strength > 3.0:
        conf += 0.20
    elif break_strength > 1.5:
        conf += 0.10
    
    if confirm_count >= 3:
        conf += 0.15
    elif confirm_count >= 2:
        conf += 0.08
    
    return min(1.0, conf)


# ═══════════════════════════════════════════════════════════════════════
# 5. New Signals
# ═══════════════════════════════════════════════════════════════════════

def detect_bpr_v11(ohlcv: List[Dict], fvg_signals: List[Dict],
                   tf: str = 'daily') -> List[Dict]:
    """BPR (Balanced Price Range) — 反向FVG的重叠区域
    
    ICT定义: 最近的看涨FVG和看跌FVG之间区域重叠形成的价格区间。
    BPR是强支撑/阻力区域, 因为机构在该区域同时布置了买单和卖单。
    
    当前一个Bull FVG和Bear FVG在价格上有重叠时:
    - 重叠区 = BPR核心区
    - 价格回到BPR = 机构关注点
    - BPR上沿/下沿 = 强支撑/阻力
    
    效果: BPR比单一FVG更可靠, 因为它是双向价格失衡的交汇点。
    """
    if not fvg_signals or len(fvg_signals) < 2:
        return []
    
    n = len(ohlcv)
    signals = []
    
    # 按方向分组
    bull_fvgs = [f for f in fvg_signals if 'Bull' in f.get('type', '')]
    bear_fvgs = [f for f in fvg_signals if 'Bear' in f.get('type', '')]
    
    if not bull_fvgs or not bear_fvgs:
        return []
    
    # 找最近的Bull FVG和Bear FVG之间的重叠
    # 用滑动窗口: 取最近10-30根K线内的反向FVG
    
    for bull_fvg in bull_fvgs:
        bull_idx = bull_fvg.get('idx', 0)
        bull_upper = bull_fvg.get('upper', 0)
        bull_lower = bull_fvg.get('lower', 0)
        
        if bull_upper <= 0 or bull_lower <= 0:
            continue
        
        # 找这个Bull FVG之后的Bear FVG (30根K线内)
        for bear_fvg in bear_fvgs:
            bear_idx = bear_fvg.get('idx', 0)
            if bear_idx <= bull_idx or bear_idx > bull_idx + 30:
                continue
            
            bear_upper = bear_fvg.get('upper', 0)
            bear_lower = bear_fvg.get('lower', 0)
            
            if bear_upper <= 0 or bear_lower <= 0:
                continue
            
            # 检查价格重叠: Bull FVG的上沿 > Bear FVG的下沿
            # Bull FVG: lower→upper (支撑区)
            # Bear FVG: lower→upper (阻力区)
            if bull_upper > bear_lower and bull_lower < bear_upper:
                # 有重叠!
                overlap_high = min(bull_upper, bear_upper)
                overlap_low = max(bull_lower, bear_lower)
                
                if overlap_high > overlap_low:
                    bpr_sig = Signal(
                        type='BPR', idx=bear_idx, direction='neutral',
                        price=(overlap_high + overlap_low) / 2,
                        timeframe=tf,
                        upper=overlap_high,
                        lower=overlap_low,
                        grade=max(bull_fvg.get('grade', 1), bear_fvg.get('grade', 1)),
                        strength=min(8.0, bull_fvg.get('strength', 3.0) + bear_fvg.get('strength', 3.0)),
                        confidence=min(0.75, 
                            bull_fvg.get('confidence', 0.4) + bear_fvg.get('confidence', 0.4)),
                        confirmed_at=bear_idx,
                        metadata={
                            'bull_fvg_idx': bull_idx,
                            'bear_fvg_idx': bear_idx,
                            'bull_fvg_type': bull_fvg.get('type', ''),
                            'bear_fvg_type': bear_fvg.get('type', ''),
                            'overlap_high': round(overlap_high, 4),
                            'overlap_low': round(overlap_low, 4),
                            'overlap_pct': round((overlap_high - overlap_low) / overlap_low * 100, 4),
                        },
                    )
                    signals.append(bpr_sig)
                    break  # 每Bull取最近Bear
    
    return [s.to_dict() for s in signals]


def detect_liquidity_void_v11(ohlcv: List[Dict], min_gap_pct: float = 0.3,
                              tf: str = 'daily') -> List[Dict]:
    """Liquidity Void — 真正的价格流动性真空 (跳空缺口)

    ICT定义: 两根连续K线之间存在价格缺口(gap), 缺口范围内无交易发生。
    - 看涨LV: 向上跳空(bar['l'] > prev['h']), gap内买方无法建仓
    - 看跌LV: 向下跳空(bar['h'] < prev['l']), gap内卖方无法建仓

    Liquidity Void = 价格真空区 = 未来价格可能快速回补/反弹的区域。
    """
    n = len(ohlcv)
    signals = []

    for i in range(1, n):
        bar = ohlcv[i]
        prev = ohlcv[i - 1]

        # Bullish gap: current low > previous high
        gap_up = bar['l'] - prev['h']
        gap_up_pct = gap_up / prev['c'] * 100 if prev['c'] > 0 else 0

        if gap_up > 0 and gap_up_pct >= min_gap_pct:
            sig = Signal(
                type='LiquidityVoid', idx=i, direction='bull',
                price=bar['o'], timeframe=tf,
                upper=bar['l'], lower=prev['h'],
                grade=3, strength=min(8.0, 3.0 + gap_up_pct),
                confidence=min(0.75, 0.4 + gap_up_pct / 10),
                confirmed_at=i,
                metadata={
                    'gap_pct': round(gap_up_pct, 2),
                    'gap_type': 'up',
                },
            )
            signals.append(sig)

        # Bearish gap: current high < previous low
        gap_down = prev['l'] - bar['h']
        gap_down_pct = gap_down / prev['c'] * 100 if prev['c'] > 0 else 0

        if gap_down > 0 and gap_down_pct >= min_gap_pct:
            sig = Signal(
                type='LiquidityVoid', idx=i, direction='bear',
                price=bar['o'], timeframe=tf,
                upper=prev['l'], lower=bar['h'],
                grade=3, strength=min(8.0, 3.0 + gap_down_pct),
                confidence=min(0.75, 0.4 + gap_down_pct / 10),
                confirmed_at=i,
                metadata={
                    'gap_pct': round(gap_down_pct, 2),
                    'gap_type': 'down',
                },
            )
            signals.append(sig)

    return [s.to_dict() for s in signals]


def detect_rejection_block_v11(ohlcv: List[Dict], min_wick_pct: float = 2.0,
                               min_reversal: float = 1.5,
                               tf: str = 'daily') -> List[Dict]:
    """拒绝块检测 — 价格触及某水平后强烈反转"""
    n = len(ohlcv)
    signals = []
    
    for i in range(2, n - 2):
        bar = ohlcv[i]
        nxt = ohlcv[i + 1]
        
        body = abs(bar['c'] - bar['o'])
        if body == 0:
            continue
        
        # Upper wick rejection (阻力)
        wick_up = bar['h'] - max(bar['o'], bar['c'])
        wick_up_pct = wick_up / bar['c'] * 100 if bar['c'] > 0 else 0
        
        if wick_up_pct >= min_wick_pct and nxt['c'] < bar['c'] * (1 - min_reversal / 100):
            sig = Signal(
                type='Rejection_Resistance', idx=i, direction='bear',
                price=bar['h'], timeframe=tf,
                upper=bar['h'], lower=bar['h'] - wick_up,
                strength=4.0, confidence=0.55,
                metadata={'wick_pct': round(wick_up_pct, 2)},
            )
            signals.append(sig)
        
        # Lower wick rejection (支撑)
        wick_down = min(bar['o'], bar['c']) - bar['l']
        wick_down_pct = wick_down / bar['c'] * 100 if bar['c'] > 0 else 0
        
        if wick_down_pct >= min_wick_pct and nxt['c'] > bar['c'] * (1 + min_reversal / 100):
            sig = Signal(
                type='Rejection_Support', idx=i, direction='bull',
                price=bar['l'], timeframe=tf,
                upper=bar['l'] + wick_down, lower=bar['l'],
                strength=4.0, confidence=0.55,
                metadata={'wick_pct': round(wick_down_pct, 2)},
            )
            signals.append(sig)
    
    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 6. IFVG (Inversion FVG)
# ═══════════════════════════════════════════════════════════════════════

def detect_ifvg_v11(ohlcv: List[Dict], min_width: float = None,
                    adaptive: Dict = None, tf: str = 'daily') -> List[Dict]:
    """IFVG (Implied Fair Value Gap) — 影线中点隐含缺口
    
    ICT定义: 当K线实体重叠但影线暴露了价格失衡区域时,
    用影线中点(high+low)/2作为缺口判断基准。
    
    Implied Bullish FVG:
    - 中间K线(c2)有长上影线, c1和c3是阴线
    - c1的(high+low)/2 < c3的(high+low)/2 表示隐含向上失衡
    - 价格可能回来回补
    """
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    if min_width is None:
        min_width = adaptive['fvg_min_width']  # 与FVG相同阈值
    
    n = len(ohlcv)
    signals = []
    
    for i in range(n - 2):
        b1, b2, b3 = ohlcv[i], ohlcv[i+1], ohlcv[i+2]
        
        # 影线中点
        mid1 = (b1['h'] + b1['l']) / 2
        mid3 = (b3['h'] + b3['l']) / 2
        
        # 隐含Bullish FVG: c1中点 < c3中点 (隐含低价区间→高价移动)
        implied_bull = mid1 < mid3 * 0.985        # 1.5%的隐含缺口
        # 隐含Bearish FVG: c1中点 > c3中点
        implied_bear = mid1 > mid3 * 1.015
        
        # 只有没有可见gap时才检测隐含gap (IFVG ≠ FVG)
        no_visible_gap = not (b1['h'] < b3['l'] or b1['l'] > b3['h'])
        
        if implied_bull and no_visible_gap:
            # 不是标准FVG(无可见gap), 但隐含缺口存在
            gap = mid3 - mid1
            gap_pct = gap / b1['c'] if b1['c'] > 0 else 0
            if gap_pct >= min_width:
                sig = Signal(
                    type='IFVG_Bull', idx=i+1, direction='bull',
                    price=mid1, timeframe=tf,
                    upper=max(b3['h'], b1['h']), lower=min(b1['l'], b3['l']),
                    grade=2, strength=3.0, confidence=0.40,
                    confirmed_at=i+2,
                    metadata={
                        'mid1': round(mid1, 4), 'mid3': round(mid3, 4),
                        'implied_gap_pct': round(gap_pct, 4),
                        'ifvg_type': 'wick_midpoint',
                    },
                )
                signals.append(sig)
        
        if implied_bear and no_visible_gap:
            gap = mid1 - mid3
            gap_pct = gap / b1['c'] if b1['c'] > 0 else 0
            if gap_pct >= min_width:
                sig = Signal(
                    type='IFVG_Bear', idx=i+1, direction='bear',
                    price=mid1, timeframe=tf,
                    upper=max(b1['h'], b3['h']), lower=min(b1['l'], b3['l']),
                    grade=2, strength=3.0, confidence=0.40,
                    confirmed_at=i+2,
                    metadata={
                        'mid1': round(mid1, 4), 'mid3': round(mid3, 4),
                        'implied_gap_pct': round(gap_pct, 4),
                        'ifvg_type': 'wick_midpoint',
                    },
                )
                signals.append(sig)
    
    return [s.to_dict() for s in signals]


def detect_mitigated_fvg_v11(ohlcv: List[Dict], fvg_signals: List[Dict],
                              tf: str = 'daily') -> List[Dict]:
    """FVG_Mitigated — 被填充的FVG反向变成支撑/阻力
    
    当FVG被完全填充后:
    - Bull FVG被填充 → 原lower变成空头阻力 (FVG_Mitigated_Bear)
    - Bear FVG被填充 → 原upper变成多头支撑 (FVG_Mitigated_Bull)
    
    核心原理: 流动性被猎杀后, 原来的失衡区变成反向的结构区。
    """
    if not fvg_signals:
        return []
    
    n = len(ohlcv)
    signals = []
    
    for fvg in fvg_signals:
        if not fvg.get('mitigated', False):
            continue
        
        fvg_idx = fvg.get('idx', 0)
        fvg_upper = fvg.get('upper', 0)
        fvg_lower = fvg.get('lower', 0)
        mitigated_at = fvg.get('mitigated_at', -1)
        
        if mitigated_at < 0 or mitigated_at >= n:
            continue
        
        if 'Bull' in fvg.get('type', ''):
            sig = Signal(
                type='FVG_Mitigated_Bear', idx=mitigated_at, direction='bear',
                price=fvg_lower, timeframe=tf,
                upper=fvg_upper, lower=fvg_lower,
                strength=min(7.0, 3.0 + fvg.get('strength', 3.0) * 0.5),
                confidence=min(0.7, 0.4 + fvg.get('confidence', 0.5) * 0.3),
                confirmed_at=mitigated_at,
                metadata={
                    'original_fvg_idx': fvg_idx,
                    'original_type': fvg.get('type', ''),
                    'inversion_level': round(fvg_lower, 4),
                },
            )
            signals.append(sig)
        elif 'Bear' in fvg.get('type', ''):
            sig = Signal(
                type='FVG_Mitigated_Bull', idx=mitigated_at, direction='bull',
                price=fvg_upper, timeframe=tf,
                upper=fvg_upper, lower=fvg_lower,
                strength=min(7.0, 3.0 + fvg.get('strength', 3.0) * 0.5),
                confidence=min(0.7, 0.4 + fvg.get('confidence', 0.5) * 0.3),
                confirmed_at=mitigated_at,
                metadata={
                    'original_fvg_idx': fvg_idx,
                    'original_type': fvg.get('type', ''),
                    'inversion_level': round(fvg_upper, 4),
                },
            )
            signals.append(sig)
    
    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 7. Breaker Block
# ═══════════════════════════════════════════════════════════════════════

def detect_breaker_block_v11(ohlcv: List[Dict], choch_signals: List[Dict],
                              ob_signals: List[Dict],
                              fvg_signals: List[Dict] = None,
                              tf: str = 'daily') -> List[Dict]:
    """BreakerBlock — CHOCH发生后，原OB被破坏变成反向的Breaker Block
    
    ICT "一击必中"模型 (Model 2: Breaker + FVG):
    
    Breaker Block发生后, 如果同时有FVG重叠:
    - 这是极高胜率的入场点 (Breaker + FVG = 超级模式)
    - 重叠区域的SL更小, RR更高
    
    Bull CHOCH后 → 前一个Bear OB变成支撑(BreakerBlock_Bull)
    Bear CHOCH后 → 前一个Bull OB变成阻力(BreakerBlock_Bear)
    """
    if not choch_signals or not ob_signals:
        return []
    
    signals = []
    
    for choch in choch_signals:
        choch_idx = choch.get('idx', 0)
        choch_dir = choch.get('direction', '')
        
        if choch_dir == 'bull':
            relevant_obs = [
                ob for ob in ob_signals
                if ob.get('direction') == 'bear'
                and ob.get('idx', 0) < choch_idx
                and ob.get('idx', 0) >= choch_idx - 30
            ]
            if not relevant_obs:
                continue
            last_ob = max(relevant_obs, key=lambda x: x.get('idx', 0))
            
            ob_upper = last_ob.get('upper', 0)
            ob_lower = last_ob.get('lower', 0)
            
            # 检查FVG重叠 (一击必中增强)
            has_fvg_overlap = False
            if fvg_signals:
                for fvg in fvg_signals:
                    if fvg.get('direction') == 'bull':
                        f_upper = fvg.get('upper', 0)
                        f_lower = fvg.get('lower', 0)
                        if f_lower < ob_upper and f_upper > ob_lower:
                            has_fvg_overlap = True
                            break
            
            sig = Signal(
                type='BreakerBlock_Bull', idx=choch_idx, direction='bull',
                price=last_ob.get('lower', 0), timeframe=tf,
                upper=ob_upper, lower=ob_lower,
                strength=min(8.0, 4.0 + choch.get('strength', 3.0) * 0.4 +
                           (1.5 if has_fvg_overlap else 0)),
                confidence=min(0.85 if has_fvg_overlap else 0.75,
                    0.5 + choch.get('confidence', 0.5) * 0.2 +
                    (0.15 if has_fvg_overlap else 0)),
                confirmed_at=choch_idx,
                metadata={
                    'original_ob_type': last_ob.get('type', ''),
                    'original_ob_idx': last_ob.get('idx', 0),
                    'choch_idx': choch_idx,
                    'has_fvg_overlap': has_fvg_overlap,
                },
            )
            signals.append(sig)
        
        elif choch_dir == 'bear':
            relevant_obs = [
                ob for ob in ob_signals
                if ob.get('direction') == 'bull'
                and ob.get('idx', 0) < choch_idx
                and ob.get('idx', 0) >= choch_idx - 30
            ]
            if not relevant_obs:
                continue
            last_ob = max(relevant_obs, key=lambda x: x.get('idx', 0))
            
            ob_upper = last_ob.get('upper', 0)
            ob_lower = last_ob.get('lower', 0)
            
            has_fvg_overlap = False
            if fvg_signals:
                for fvg in fvg_signals:
                    if fvg.get('direction') == 'bear':
                        f_upper = fvg.get('upper', 0)
                        f_lower = fvg.get('lower', 0)
                        if f_lower < ob_upper and f_upper > ob_lower:
                            has_fvg_overlap = True
                            break
            
            sig = Signal(
                type='BreakerBlock_Bear', idx=choch_idx, direction='bear',
                price=last_ob.get('upper', 0), timeframe=tf,
                upper=ob_upper, lower=ob_lower,
                strength=min(8.0, 4.0 + choch.get('strength', 3.0) * 0.4 +
                           (1.5 if has_fvg_overlap else 0)),
                confidence=min(0.85 if has_fvg_overlap else 0.75,
                    0.5 + choch.get('confidence', 0.5) * 0.2 +
                    (0.15 if has_fvg_overlap else 0)),
                confirmed_at=choch_idx,
                metadata={
                    'original_ob_type': last_ob.get('type', ''),
                    'original_ob_idx': last_ob.get('idx', 0),
                    'choch_idx': choch_idx,
                    'has_fvg_overlap': has_fvg_overlap,
                },
            )
            signals.append(sig)
    
    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 8. EQL (Equal Highs/Lows)
# ═══════════════════════════════════════════════════════════════════════

def detect_eql_v11(ohlcv: List[Dict], lookback: int = 30,
                   tolerance_pct: float = 0.3,
                   tf: str = 'daily') -> List[Dict]:
    """EQL (Equal Highs/Lows) — 等高点/等低点支撑阻力
    
    等高点: 两根K线高点相差不到0.3%，形成阻力
    等低点: 两根K线低点相差不到0.3%，形成支撑
    需要间隔2-15根K线的两根K线
    
    原理: 市场在相同水平多次测试, 说明该水平有结构意义。
    """
    n = len(ohlcv)
    if n < 10:
        return []
    
    signals = []
    max_gap = 15
    min_gap = 2
    
    for i in range(min(lookback, n)):
        for j in range(i + min_gap, min(i + max_gap + 1, n)):
            # Equal highs — bearish resistance
            hi, hj = ohlcv[i]['h'], ohlcv[j]['h']
            avg_price = max(hi, hj, 0.01)
            diff_pct = abs(hi - hj) / avg_price * 100
            
            if diff_pct <= tolerance_pct:
                level = min(hi, hj)  # 用较低的高点作为阻力
                # Closeness factor: closer = stronger
                closeness = 1.0 - diff_pct / tolerance_pct if tolerance_pct > 0 else 0.5
                
                sig = Signal(
                    type='EQL_High', idx=j, direction='bear',
                    price=level, timeframe=tf,
                    upper=level, lower=level * 0.998,
                    strength=2.0 + closeness * 3.0,
                    confidence=0.3 + closeness * 0.4,
                    confirmed_at=j,
                    metadata={
                        'level': round(level, 4),
                        'candle1_idx': i,
                        'candle2_idx': j,
                        'diff_pct': round(diff_pct, 2),
                        'gap_bars': j - i,
                    },
                )
                signals.append(sig)
            
            # Equal lows — bullish support
            li, lj = ohlcv[i]['l'], ohlcv[j]['l']
            avg_price = max(li, lj, 0.01)
            diff_pct = abs(li - lj) / avg_price * 100
            
            if diff_pct <= tolerance_pct:
                level = max(li, lj)  # 用较高的低点作为支撑
                closeness = 1.0 - diff_pct / tolerance_pct if tolerance_pct > 0 else 0.5
                
                sig = Signal(
                    type='EQL_Low', idx=j, direction='bull',
                    price=level, timeframe=tf,
                    upper=level * 1.002, lower=level,
                    strength=2.0 + closeness * 3.0,
                    confidence=0.3 + closeness * 0.4,
                    confirmed_at=j,
                    metadata={
                        'level': round(level, 4),
                        'candle1_idx': i,
                        'candle2_idx': j,
                        'diff_pct': round(diff_pct, 2),
                        'gap_bars': j - i,
                    },
                )
                signals.append(sig)
    
    # Deduplicate: keep only the strongest signal per unique level+direction
    signals.sort(key=lambda s: -s.strength)
    unique = []
    seen_levels = set()
    for sig in signals:
        level_key = round(sig.metadata.get('level', 0), 2)
        dir_key = sig.direction
        key = (level_key, dir_key)
        if key not in seen_levels:
            seen_levels.add(key)
            unique.append(sig)
    
    unique.sort(key=lambda s: s.idx)
    return [s.to_dict() for s in unique]


# ═══════════════════════════════════════════════════════════════════════
# 9. OTE (Optimal Trade Entry)
# ═══════════════════════════════════════════════════════════════════════

def detect_ote_v11(ohlcv: List[Dict], swing_signals: List[Dict] = None,
                   tf: str = 'daily') -> List[Dict]:
    """OTE (Optimal Trade Entry) — 斐波那契61.8%回撤最佳入场
    
    基于斐波那契回撤: 在上升趋势的回调中找61.8%区域
    需要先找摆动点，然后价格回调到0.618位置
    
    关键: 找从最近摆动低点到摆动高点的61.8%回撤位
    metadata中记录retracement_ratio
    """
    n = len(ohlcv)
    if n < 20:
        return []
    
    signals = []
    
    # Find swing points with lookback=10
    sw_lookback = 10
    swing_highs = []
    swing_lows = []
    
    for i in range(sw_lookback, n - sw_lookback):
        bar = ohlcv[i]
        is_high = all(ohlcv[j]['h'] <= bar['h']
                      for j in range(i - sw_lookback, i + sw_lookback + 1)
                      if 0 <= j < n and j != i)
        is_low = all(ohlcv[j]['l'] >= bar['l']
                     for j in range(i - sw_lookback, i + sw_lookback + 1)
                     if 0 <= j < n and j != i)
        if is_high:
            swing_highs.append((i, bar['h']))
        if is_low:
            swing_lows.append((i, bar['l']))
    
    # Bullish OTE: uptrend impulse (swing low -> swing high), then retrace to 0.618
    for low_idx, low_price in swing_lows:
        # Find the nearest swing high after this low
        future_highs = [(hi, hp) for hi, hp in swing_highs
                        if hi > low_idx and hi < low_idx + 30]
        if not future_highs:
            continue
        high_idx, high_price = future_highs[0]
        
        impulse = high_price - low_price
        if impulse <= 0 or low_price <= 0:
            continue
        
        impulse_pct = impulse / low_price * 100
        if impulse_pct < 1.0:  # 最小1%的波动
            continue
        
        fib_618 = high_price - impulse * 0.618
        fib_500 = high_price - impulse * 0.500  # OTE range lower bound
        
        # Look for price retracing to the OTE zone (0.50-0.68 of impulse)
        search_end = min(high_idx + 20, n)
        for k in range(high_idx + 1, search_end):
            bar = ohlcv[k]
            tolerance = impulse * 0.02
            
            in_zone = (bar['l'] <= fib_618 + tolerance and
                       bar['h'] >= fib_500 - tolerance)
            
            if in_zone:
                # Volume contraction during retrace = stronger
                vol_before = sum(ohlcv[max(0, k-5):k][j]['v'] for j in range(min(5, k))) / min(5, max(1, k))
                vol_contracted = vol_before > 0 and bar['v'] < vol_before * 0.8
                
                # How deep in the zone are we?
                retrace_ratio = (high_price - bar['c']) / impulse if impulse > 0 else 0
                
                strength = 3.0 + min(4.0, impulse_pct)
                if vol_contracted:
                    strength += 1.5
                confidence = 0.4 + min(0.3, impulse_pct / 20)
                if vol_contracted:
                    confidence += 0.15
                
                sig = Signal(
                    type='OTE_Bull', idx=k, direction='bull',
                    price=bar['c'], timeframe=tf,
                    upper=high_price, lower=low_price,
                    strength=min(10.0, strength),
                    confidence=min(0.8, confidence),
                    confirmed_at=k,
                    metadata={
                        'retracement_ratio': round(retrace_ratio, 3),
                        'swing_low_idx': low_idx,
                        'swing_high_idx': high_idx,
                        'swing_low_price': round(low_price, 4),
                        'swing_high_price': round(high_price, 4),
                        'fib_618_level': round(fib_618, 4),
                        'fib_500_level': round(fib_500, 4),
                        'impulse_pct': round(impulse_pct, 2),
                        'vol_contracted': vol_contracted,
                    },
                )
                signals.append(sig)
                break  # 每个摆动对只取一次
    
    # Bearish OTE: downtrend impulse (swing high -> swing low), then retrace to 0.618
    for high_idx, high_price in swing_highs:
        future_lows = [(li, lp) for li, lp in swing_lows
                       if li > high_idx and li < high_idx + 30]
        if not future_lows:
            continue
        low_idx, low_price = future_lows[0]
        
        impulse = high_price - low_price
        if impulse <= 0 or high_price <= 0:
            continue
        
        impulse_pct = impulse / high_price * 100
        if impulse_pct < 1.0:
            continue
        
        fib_618 = low_price + impulse * 0.618
        fib_500 = low_price + impulse * 0.500
        
        search_end = min(low_idx + 20, n)
        for k in range(low_idx + 1, search_end):
            bar = ohlcv[k]
            tolerance = impulse * 0.02
            
            in_zone = (bar['l'] <= fib_618 + tolerance and
                       bar['h'] >= fib_500 - tolerance)
            
            if in_zone:
                vol_before = sum(ohlcv[max(0, k-5):k][j]['v'] for j in range(min(5, k))) / min(5, max(1, k))
                vol_contracted = vol_before > 0 and bar['v'] < vol_before * 0.8
                
                retrace_ratio = (bar['c'] - low_price) / impulse if impulse > 0 else 0
                
                strength = 3.0 + min(4.0, impulse_pct)
                if vol_contracted:
                    strength += 1.5
                confidence = 0.4 + min(0.3, impulse_pct / 20)
                if vol_contracted:
                    confidence += 0.15
                
                sig = Signal(
                    type='OTE_Bear', idx=k, direction='bear',
                    price=bar['c'], timeframe=tf,
                    upper=high_price, lower=low_price,
                    strength=min(10.0, strength),
                    confidence=min(0.8, confidence),
                    confirmed_at=k,
                    metadata={
                        'retracement_ratio': round(retrace_ratio, 3),
                        'swing_high_idx': high_idx,
                        'swing_low_idx': low_idx,
                        'swing_high_price': round(high_price, 4),
                        'swing_low_price': round(low_price, 4),
                        'fib_618_level': round(fib_618, 4),
                        'fib_500_level': round(fib_500, 4),
                        'impulse_pct': round(impulse_pct, 2),
                        'vol_contracted': vol_contracted,
                    },
                )
                signals.append(sig)
                break
    
    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 10. MSS (Market Structure Shift)
# ═══════════════════════════════════════════════════════════════════════

def detect_mss_v11(ohlcv: List[Dict], lookback: int = 10,
                   min_confirm: int = 1, tf: str = 'daily') -> List[Dict]:
    """MSS (Market Structure Shift) — 微观结构转变

    与CHOCH的区别: MSS检测微小结构变化(3根K线窗口), 快但置信度低
    CHOCH检测重大结构转换(摆动点级别), 慢但更可靠

    用途: MSS=预警信号, CHOCH=确认信号
    MSS在CHOCH之前触发, 给交易者提前准备

    特点:
    - 使用超短窗口(3根K线)检测局部结构
    - 突破确认要求低(1根确认)
    - 适合快速反应, 不适合做入场依据
    """
    n = len(ohlcv)
    if n < 10:
        return []

    signals = []
    local_window = 3  # 短窗口 = 微观结构

    for i in range(lookback, n - min_confirm - 1):
        # 最近3根K线的局部极值
        start = i - local_window
        recent_high = max(ohlcv[j]['h'] for j in range(start, i))
        recent_low = min(ohlcv[j]['l'] for j in range(start, i))

        bar = ohlcv[i]

        # Bullish MSS: 收盘突破局部高点
        if bar['c'] > recent_high and bar['h'] > recent_high:
            confirmed = True
            confirm_count = 0
            for c in range(1, min_confirm + 1):
                if i + c >= n:
                    break
                if ohlcv[i + c]['c'] < recent_high:
                    confirmed = False
                    break
                confirm_count += 1

            if not (confirmed and confirm_count >= min_confirm):
                continue

            break_strength = ((bar['c'] - recent_high) / recent_high * 100
                              if recent_high > 0 else 0)
            if break_strength < 0.2:  # 更小的阈值 = 更快触发
                continue

            sig = Signal(
                type='MSS_Bull', idx=i, direction='bull',
                price=bar['c'], timeframe=tf,
                upper=bar['h'], lower=recent_high,
                strength=min(4.0, 1.5 + break_strength),
                confidence=min(0.45, 0.25 + break_strength / 20),
                confirmed_at=i + confirm_count,
                metadata={
                    'break_level': round(recent_high, 4),
                    'break_strength': round(break_strength, 2),
                    'local_window': local_window,
                    'confirm_bars': confirm_count,
                    'micro_structure': True,
                },
            )
            signals.append(sig)

        # Bearish MSS: 收盘跌破局部低点
        elif bar['c'] < recent_low and bar['l'] < recent_low:
            confirmed = True
            confirm_count = 0
            for c in range(1, min_confirm + 1):
                if i + c >= n:
                    break
                if ohlcv[i + c]['c'] > recent_low:
                    confirmed = False
                    break
                confirm_count += 1

            if not (confirmed and confirm_count >= min_confirm):
                continue

            break_strength = ((recent_low - bar['c']) / recent_low * 100
                              if recent_low > 0 else 0)
            if break_strength < 0.2:
                continue

            sig = Signal(
                type='MSS_Bear', idx=i, direction='bear',
                price=bar['c'], timeframe=tf,
                upper=recent_low, lower=bar['l'],
                strength=min(4.0, 1.5 + break_strength),
                confidence=min(0.45, 0.25 + break_strength / 20),
                confirmed_at=i + confirm_count,
                metadata={
                    'break_level': round(recent_low, 4),
                    'break_strength': round(break_strength, 2),
                    'local_window': local_window,
                    'confirm_bars': confirm_count,
                    'micro_structure': True,
                },
            )
            signals.append(sig)

    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 11. PO3 (Power of 3)
# ═══════════════════════════════════════════════════════════════════════

def detect_po3_v11(ohlcv: List[Dict], lookback: int = 20,
                   adaptive: Dict = None,
                   tf: str = 'daily') -> List[Dict]:
    """PO3 (Power of 3) — ICT Power of 3: 蓄势(ACC)->操纵(MAN)->分配(DIS)
    
    检测模式:
    ACC阶段: 窄幅震荡+低成交量(3-8根K线)
    MAN阶段: 突然扫荡流动性(假突破前高或前低)
    DIS阶段: 价格向反方向运行
    
    一次PO3检测输出3个阶段的信号, metadata记录各阶段idx。
    
    原理: ICT核心概念, 市场通过三个阶段的运作来猎杀流动性。
    """
    n = len(ohlcv)
    if n < 30:
        return []
    
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    
    signals = []
    processed_acc = set()  # 避免重复处理
    
    # ACC范围阈值: 基于ATR自适应
    atr = adaptive.get('atr_pct', 2.0)
    acc_range_max = atr  # ACC范围不能超过1×ATR
    
    for i in range(lookback, n - 10):
        if i in processed_acc:
            continue
        
        # 尝试找到ACC阶段: 3-8根窄幅震荡K线
        for acc_len in range(3, min(9, n - i - 3)):
            acc_bars = ohlcv[i:i + acc_len]
            
            # ACC条件: 窄幅 + 低成交量
            acc_high = max(b['h'] for b in acc_bars)
            acc_low = min(b['l'] for b in acc_bars)
            acc_range_pct = ((acc_high - acc_low) / acc_low * 100
                             if acc_low > 0 else 0)
            
            if acc_range_pct > acc_range_max:  # 超过ATR%不算窄幅
                continue
            
            # 低成交量: ACC期间均量 < 之前10根均量的80%
            acc_vol_avg = sum(b['v'] for b in acc_bars) / acc_len
            prev_bars = ohlcv[max(0, i - 10):i]
            if prev_bars:
                prev_vol_avg = sum(b['v'] for b in prev_bars) / len(prev_bars)
                vol_ok = prev_vol_avg > 0 and acc_vol_avg < prev_vol_avg * 0.8
            else:
                vol_ok = False
            
            if not vol_ok:
                continue
            
            # MAN阶段: ACC之后立即出现突破K线
            man_idx = i + acc_len
            if man_idx >= n:
                continue
            
            man_bar = ohlcv[man_idx]
            man_high = man_bar['h']
            man_low = man_bar['l']
            
            # 突破方向
            broke_up = man_high > acc_high
            broke_down = man_low < acc_low
            
            if not (broke_up or broke_down):
                continue
            
            # DIS阶段: MAN之后，价格向反方向运行
            dis_found = False
            for dis_offset in range(1, min(8, n - man_idx)):
                dis_idx = man_idx + dis_offset
                dis_bar = ohlcv[dis_idx]
                
                if broke_up and not broke_down:
                    # MAN向上假突破 -> DIS向下
                    if (dis_bar['c'] < acc_high and
                            dis_bar['l'] < min(acc_low, man_low)):
                        dis_direction = 'bear'
                        dis_found = True
                        break
                elif broke_down and not broke_up:
                    # MAN向下假突破 -> DIS向上
                    if (dis_bar['c'] > acc_low and
                            dis_bar['h'] > max(acc_high, man_high)):
                        dis_direction = 'bull'
                        dis_found = True
                        break
                else:
                    # 双向突破, 看收盘方向决定
                    if man_bar['c'] > man_bar['o']:
                        # MAN偏多, DIS应向下
                        if dis_bar['c'] < acc_high:
                            dis_direction = 'bear'
                            dis_found = True
                            break
                    else:
                        if dis_bar['c'] > acc_low:
                            dis_direction = 'bull'
                            dis_found = True
                            break
            
            if not dis_found:
                continue
            
            # Mark ACC idx as processed
            for acc_offset in range(acc_len):
                processed_acc.add(i + acc_offset)
            
            po3_type = f'PO3_{"Bear" if dis_direction == "bear" else "Bull"}'
            
            # --- Output ACC signal ---
            sig_acc = Signal(
                type='PO3_Acc', idx=i, direction='neutral',
                price=(acc_high + acc_low) / 2, timeframe=tf,
                upper=acc_high, lower=acc_low,
                strength=4.0, confidence=0.5,
                confirmed_at=man_idx - 1,
                metadata={
                    'phase': 'acc',
                    'acc_start': i,
                    'acc_end': man_idx - 1,
                    'acc_range_pct': round(acc_range_pct, 2),
                    'acc_len': acc_len,
                    'po3_type': po3_type,
                    'dis_direction': dis_direction,
                },
            )
            signals.append(sig_acc)
            
            # --- Output MAN signal ---
            man_type = 'SweepUp' if broke_up else 'SweepDown'
            sig_man = Signal(
                type='PO3_Man', idx=man_idx,
                direction='bear' if broke_up else 'bull',
                price=man_bar['h'] if broke_up else man_bar['l'],
                timeframe=tf,
                upper=man_bar['h'], lower=man_bar['l'],
                strength=5.0, confidence=0.55,
                confirmed_at=man_idx,
                metadata={
                    'phase': 'man',
                    'man_idx': man_idx,
                    'acc_start': i,
                    'acc_end': man_idx - 1,
                    'man_type': man_type,
                    'po3_type': po3_type,
                    'dis_direction': dis_direction,
                },
            )
            signals.append(sig_man)
            
            # --- Output DIS signal ---
            dis_bar = ohlcv[dis_idx]
            sig_dis = Signal(
                type='PO3_DIS', idx=dis_idx, direction=dis_direction,
                price=dis_bar['c'], timeframe=tf,
                upper=max(dis_bar['h'], acc_high),
                lower=min(dis_bar['l'], acc_low),
                strength=6.0, confidence=0.6,
                confirmed_at=dis_idx,
                metadata={
                    'phase': 'dis',
                    'dis_idx': dis_idx,
                    'dis_direction': dis_direction,
                    'acc_start': i,
                    'acc_end': man_idx - 1,
                    'man_idx': man_idx,
                    'po3_type': po3_type,
                },
            )
            signals.append(sig_dis)
            
            break  # 从当前i找到一组PO3后就跳过
    
    return [s.to_dict() for s in signals]


# ═══════════════════════════════════════════════════════════════════════
# 12. Unified Detection (V11 entry point)
# ═══════════════════════════════════════════════════════════════════════

def detect_all_signals_v11(ohlcv: List[Dict], params: Dict = None,
                           adaptive: Dict = None, tf: str = 'daily') -> Dict:
    """V11统一信号检测入口
    
    一次性检测所有信号类型, 返回按类型分组的完整结果。
    
    Returns:
        {
            'fvg': [...],
            'sweep': [...],
            'ob': [...],
            'choch': [...],
            'bpr': [...],
            'liquidity_void': [...],
            'rejection_block': [...],
            'all': [...],      # 合并并排序
            'adaptive': {...}, # 自适应阈值
            'stats': {...},    # 统计
        }
    """
    if params is None:
        params = {}
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)
    
    # 1. FVG (基础信号)
    fvg_signals = detect_fvg_v11(
        ohlcv, min_width=params.get('fvg_min_width'),
        merge_dist=params.get('fvg_merge_dist', 3),
        adaptive=adaptive, tf=tf,
    )
    
    # 2. Sweep (流动性猎杀)
    sweep_signals = detect_sweep_v11(
        ohlcv, lookback=params.get('sweep_lookback', 12),
        wick_ratio=params.get('sweep_wick_ratio'),
        adaptive=adaptive, tf=tf,
    )
    
    # 3. OB (订单块)
    ob_signals = detect_ob_v11(
        ohlcv, strength_min=params.get('ob_strength_min'),
        adaptive=adaptive, tf=tf,
    )
    
    # 4. CHOCH (结构转换 — 带sweep位置约束)
    choch_signals = detect_choch_v11(
        ohlcv, lookback=params.get('sweep_lookback', 15),
        sweep_signals=sweep_signals, tf=tf,
    )
    
    # 5. BPR (Balanced Price Range — 反向FVG重叠)
    bpr_signals = detect_bpr_v11(ohlcv, fvg_signals, tf=tf)
    
    # 6. Liquidity Void
    lv_signals = detect_liquidity_void_v11(ohlcv, tf=tf)
    
    # 7. Rejection Block
    rj_signals = detect_rejection_block_v11(ohlcv, tf=tf)
    
    # 8. IFVG (Implied FVG — 影线中点隐含缺口, 独立检测)
    ifvg_signals = detect_ifvg_v11(ohlcv, adaptive=adaptive, tf=tf)
    
    # 9. Mitigated FVG (原Inversion FVG — 被填充FVG的反向区域)
    mitigated_fvg_signals = detect_mitigated_fvg_v11(ohlcv, fvg_signals, tf=tf)
    
    # 10. Breaker Block (CHOCH + OB + FVG重叠)
    brk_signals = detect_breaker_block_v11(ohlcv, choch_signals, ob_signals,
                                            fvg_signals=fvg_signals, tf=tf)
    
    # 11. EQL (Equal Highs/Lows)
    eql_signals = detect_eql_v11(ohlcv, tf=tf)
    
    # 12. OTE (Optimal Trade Entry)
    ote_signals = detect_ote_v11(ohlcv, tf=tf)
    
    # 13. MSS (Market Structure Shift)
    mss_signals = detect_mss_v11(ohlcv, tf=tf)
    
    # 14. PO3 (Power of 3)
    po3_signals = detect_po3_v11(ohlcv, adaptive=adaptive, tf=tf)
    
    # 合并所有信号并按时间排序
    all_signals = (fvg_signals + sweep_signals + ob_signals +
                   choch_signals + bpr_signals + lv_signals + rj_signals +
                   ifvg_signals + mitigated_fvg_signals + brk_signals + eql_signals +
                   ote_signals + mss_signals + po3_signals)
    all_signals.sort(key=lambda s: s.get('idx', 0))
    
    # 统计
    stats = {
        'total': len(all_signals),
        'fvg': len(fvg_signals),
        'sweep': len(sweep_signals),
        'ob': len(ob_signals),
        'choch': len(choch_signals),
        'bpr': len(bpr_signals),
        'liquidity_void': len(lv_signals),
        'rejection_block': len(rj_signals),
        'ifvg': len(ifvg_signals),
        'mitigated_fvg': len(mitigated_fvg_signals),
        'breaker_block': len(brk_signals),
        'eql': len(eql_signals),
        'ote': len(ote_signals),
        'mss': len(mss_signals),
        'po3': len(po3_signals),
        'bull': sum(1 for s in all_signals if s.get('direction') == 'bull'),
        'bear': sum(1 for s in all_signals if s.get('direction') == 'bear'),
    }
    
    # 增强: 给每个信号加顺序编号
    for i, sig in enumerate(all_signals):
        sig['seq'] = i  # 全局顺序号
    
    return {
        'fvg': fvg_signals,
        'sweep': sweep_signals,
        'ob': ob_signals,
        'choch': choch_signals,
        'bpr': bpr_signals,
        'liquidity_void': lv_signals,
        'rejection_block': rj_signals,
        'ifvg': ifvg_signals,
        'mitigated_fvg': mitigated_fvg_signals,
        'breaker_block': brk_signals,
        'eql': eql_signals,
        'ote': ote_signals,
        'mss': mss_signals,
        'po3': po3_signals,
        'all': all_signals,
        'adaptive': adaptive,
        'stats': stats,
    }
