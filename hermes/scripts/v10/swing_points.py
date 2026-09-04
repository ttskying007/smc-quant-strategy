#!/usr/bin/env python3
# SMC V10 — Multi-Scale Swing Point Detection Engine
"""
核心创新: 多层级摆动点检测, 构建市场结构树。

传统 pivot 检测只用单一 lookback，V10 使用多尺度:
- 微观 (3-5 bars): 小摆动点 — 用于精细入场
- 中观 (8-15 bars): 中摆动点 — 用于结构确认
- 宏观 (20-50 bars): 大摆动点 — 用于趋势方向

每个层级的摆动点相互验证:
  - 微观摆动点被中观包含 → 低级别共振
  - 中观摆动点被宏观确认 → 高级别共振
  - 所有层级指向同方向 → 圣杯级

输出: 结构树 dict → 直接可用于 ECharts markPoint 渲染
"""

import math, logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

log = logging.getLogger('smc_v10.swing_points')


# ═══════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SwingPoint:
    """Single swing point (high or low)."""
    idx: int                    # candle index
    price: float                # price level
    level: str                  # 'micro'(3-5) | 'meso'(8-15) | 'macro'(20-50)
    is_high: bool               # True=swing high, False=swing low
    strength: float = 0.0       # 0-1, how clean the pivot is
    confirmed_by: List[int] = field(default_factory=list)  # higher-level pivots confirming

    def __repr__(self):
        direction = 'HH' if self.is_high else 'LL'
        return f"SP({self.level}:{direction}@{self.idx}={self.price:.2f} s={self.strength:.1f})"


@dataclass
class MarketStructure:
    """Market structure between two swing points."""
    from_pivot: SwingPoint
    to_pivot: SwingPoint
    direction: str           # 'bullish' | 'bearish' | 'neutral'
    is_bos: bool = False     # Break of Structure
    is_choch: bool = False   # Change of Character
    is_liquidity_pool: bool = False  # EQH/EQL area
    
    @property
    def bars(self) -> int:
        return self.to_pivot.idx - self.from_pivot.idx
    
    @property
    def price_change(self) -> float:
        return self.to_pivot.price - self.from_pivot.price


# ═══════════════════════════════════════════════════════════════════════
# Core algorithm: multi-scale pivot detection
# ═══════════════════════════════════════════════════════════════════════

def find_swing_points(ohlcv, scales=None, min_strength=0.3):
    """Multi-scale swing point detection.
    
    Uses multiple lookback windows to find pivots at different scales.
    A point is a pivot if it's the highest/lowest in its local window.
    
    Args:
        ohlcv: [{o,h,l,c,v}, ...] in chronological order
        scales: list of (left_bars, right_bars, level_name)
                defaults: [(3,3,'micro'), (8,5,'meso'), (20,8,'macro'), (50,15,'mega')]
        min_strength: minimum strength (0-1) to include a pivot
    
    Returns:
        {
            'micro': [SwingPoint, ...],
            'meso': [SwingPoint, ...],
            'macro': [SwingPoint, ...],
            'mega': [SwingPoint, ...],
            'structures': [MarketStructure, ...],
            'tree': {...},           # hierarchical confirmation tree
            'current_phase': str,    # trending_up/down/ranging/volatile
        }
    """
    if scales is None:
        scales = [
            (3, 3, 'micro'),      # ~1 week in daily
            (8, 5, 'meso'),       # ~2-3 weeks  
            (20, 8, 'macro'),     # ~1-2 months
            (50, 15, 'mega'),     # ~3-4 months
        ]
    
    n = len(ohlcv)
    all_pivots = {}
    
    for left, right, level in scales:
        pivots = _detect_pivots_at_scale(ohlcv, left, right, level, min_strength)
        all_pivots[level] = pivots
    
    # Cross-scale confirmation
    _cross_validate_pivots(all_pivots)
    
    # Build market structures
    structures = _build_structures(all_pivots)
    
    # Detect current market phase
    phase = _detect_market_phase(all_pivots, ohlcv)
    
    # Build hierarchical tree
    tree = _build_hierarchy_tree(all_pivots, structures)
    
    return {
        'micro': all_pivots.get('micro', []),
        'meso': all_pivots.get('meso', []),
        'macro': all_pivots.get('macro', []),
        'mega': all_pivots.get('mega', []),
        'structures': structures,
        'tree': tree,
        'current_phase': phase,
    }


def _detect_pivots_at_scale(ohlcv, left, right, level, min_strength):
    """Detect swing highs and lows at one scale."""
    n = len(ohlcv)
    pivots = []
    
    for i in range(left, n - right):
        bar = ohlcv[i]
        
        # Check if swing high
        is_high = True
        for j in range(i - left, i + right + 1):
            if j == i:
                continue
            if ohlcv[j]['h'] >= bar['h']:
                is_high = False
                break
        
        if is_high:
            strength = _calc_pivot_strength(ohlcv, i, left, right, is_high=True)
            if strength >= min_strength:
                pivots.append(SwingPoint(
                    idx=i, price=bar['h'], level=level,
                    is_high=True, strength=strength
                ))
        
        # Check if swing low
        is_low = True
        for j in range(i - left, i + right + 1):
            if j == i:
                continue
            if ohlcv[j]['l'] <= bar['l']:
                is_low = False
                break
        
        if is_low:
            strength = _calc_pivot_strength(ohlcv, i, left, right, is_high=False)
            if strength >= min_strength:
                pivots.append(SwingPoint(
                    idx=i, price=bar['l'], level=level,
                    is_high=False, strength=strength
                ))
    
    # Sort by idx
    pivots.sort(key=lambda p: p.idx)
    return pivots


def _calc_pivot_strength(ohlcv, idx, left, right, is_high):
    """Calculate pivot strength (0-1).
    
    Strength is higher when:
    - The pivot clearly stands out from neighbors
    - The reversal is decisive (large range candle)
    - Volume supports the pivot
    """
    bar = ohlcv[idx]
    n = len(ohlcv)
    
    # 1. Price deviation from neighbors
    if is_high:
        nearby_max = max(ohlcv[j]['h'] for j in range(max(0, idx-left), min(n, idx+right+1)) if j != idx)
        deviation = (bar['h'] - nearby_max) / bar['h'] * 100 if bar['h'] > 0 else 0
    else:
        nearby_min = min(ohlcv[j]['l'] for j in range(max(0, idx-left), min(n, idx+right+1)) if j != idx)
        deviation = (nearby_min - bar['l']) / bar['l'] * 100 if bar['l'] > 0 else 0
    
    dev_score = min(1.0, deviation * 10)  # 0.1% deviation → 1.0
    
    # 2. Candle decisiveness (large body relative to range)
    body = abs(bar['c'] - bar['o'])
    range_hl = bar['h'] - bar['l']
    if range_hl > 0:
        body_ratio = body / range_hl
    else:
        body_ratio = 0
    body_score = body_ratio  # engulfing candle = high score
    
    # 3. Directional alignment (close near extreme for strength)
    if is_high:
        close_score = (bar['c'] - bar['l']) / range_hl if range_hl > 0 else 0.5
    else:
        close_score = (bar['h'] - bar['c']) / range_hl if range_hl > 0 else 0.5
    
    # 4. Volume confirmation
    if idx >= 20:
        avg_vol = sum(ohlcv[j]['v'] for j in range(idx-20, idx)) / 20
        if avg_vol > 0:
            vol_ratio = min(2.0, bar['v'] / avg_vol)
            vol_score = vol_ratio / 2.0
        else:
            vol_score = 0.5
    else:
        vol_score = 0.5
    
    # Weighted combination
    strength = (
        dev_score * 0.35 +
        body_score * 0.25 +
        close_score * 0.20 +
        vol_score * 0.20
    )
    
    return min(1.0, max(0.0, strength))


def _cross_validate_pivots(all_pivots):
    """Cross-validate: higher-level pivots confirm lower-level ones.
    
    A micro pivot is "confirmed" if there's a meso/macro/mega pivot nearby
    in the same direction. This filters noise.
    """
    level_order = ['micro', 'meso', 'macro', 'mega']
    
    for i, low_level in enumerate(level_order):
        low_pivots = all_pivots.get(low_level, [])
        if not low_pivots:
            continue
        
        for lp in low_pivots:
            # Check each higher level for confirmation
            for j in range(i + 1, len(level_order)):
                high_level = level_order[j]
                high_pivots = all_pivots.get(high_level, [])
                
                for hp in high_pivots:
                    # Same direction (both highs or both lows)
                    if lp.is_high != hp.is_high:
                        continue
                    # Within proximity (higher level has larger window)
                    proximity = max(3, j * 5)  # micro=3, meso=5, macro=8
                    if abs(lp.idx - hp.idx) <= proximity:
                        # Price alignment: pivot prices should be close
                        price_diff = abs(lp.price - hp.price) / lp.price if lp.price > 0 else 0
                        if price_diff < 0.03:  # within 3%
                            lp.confirmed_by.append(hp.idx)
                            break  # confirmed by this level, check next


# ═══════════════════════════════════════════════════════════════════════
# Market structure analysis
# ═══════════════════════════════════════════════════════════════════════

def _build_structures(all_pivots):
    """Build market structures from swing points.
    
    A structure is the movement between two consecutive swing points.
    Analyzes: BOS (continuation), CHOCH (reversal), liquidity pools.
    """
    # Use meso+macro pivots for structures (less noise)
    meso = all_pivots.get('meso', [])
    macro = all_pivots.get('macro', [])
    
    # Merge and deduplicate, keeping higher level
    all_sp = _merge_pivots(meso, macro)
    all_sp.sort(key=lambda p: p.idx)
    
    if len(all_sp) < 2:
        return []
    
    structures = []
    
    for i in range(len(all_sp) - 1):
        sp1, sp2 = all_sp[i], all_sp[i + 1]
        
        struct = MarketStructure(
            from_pivot=sp1,
            to_pivot=sp2,
            direction='neutral'
        )
        
        # Determine direction
        if sp2.is_high and not sp1.is_high:
            # Low → High = bullish move
            struct.direction = 'bullish'
            # Check if new high exceeds previous high
            prev_highs = [p for p in all_sp[:i+1] if p.is_high]
            if prev_highs and sp2.price > prev_highs[-1].price:
                struct.is_bos = True  # Break above previous HH
        elif not sp2.is_high and sp1.is_high:
            # High → Low = bearish move
            struct.direction = 'bearish'
            prev_lows = [p for p in all_sp[:i+1] if not p.is_high]
            if prev_lows and sp2.price < prev_lows[-1].price:
                struct.is_bos = True  # Break below previous LL
        elif sp2.is_high and sp1.is_high:
            if abs(sp2.price - sp1.price) / sp1.price < 0.02:
                struct.is_liquidity_pool = True  # EQH
        elif not sp2.is_high and not sp1.is_high:
            if abs(sp2.price - sp1.price) / sp1.price < 0.02:
                struct.is_liquidity_pool = True  # EQL
        
        # CHOCH detection: direction change between consecutive structures
        if i > 0:
            prev = structures[-1]
            if prev.direction == 'bearish' and struct.direction == 'bullish':
                struct.is_choch = True  # Bear→Bull reversal
            elif prev.direction == 'bullish' and struct.direction == 'bearish':
                struct.is_choch = True  # Bull→Bear reversal
        
        structures.append(struct)
    
    return structures


def _merge_pivots(primary, secondary):
    """Merge two pivot lists, preferring primary when close."""
    # Simple approach: take primary, add secondary only if far from primary
    result = list(primary)
    for sp in secondary:
        too_close = any(abs(sp.idx - r.idx) <= 3 and sp.is_high == r.is_high 
                        for r in result)
        if not too_close:
            result.append(sp)
    return result


def _detect_market_phase(all_pivots, ohlcv):
    """Detect current market phase from swing point patterns.
    
    Returns: 'trending_up' | 'trending_down' | 'ranging' | 'volatile' | 'breakout'
    """
    macro = all_pivots.get('macro', [])
    meso = all_pivots.get('meso', [])
    
    if len(macro) < 3 or len(meso) < 3:
        return 'volatile'
    
    # Get last 3 macro swing points
    recent_macro = macro[-3:]
    highs = [p.price for p in recent_macro if p.is_high]
    lows = [p.price for p in recent_macro if not p.is_high]
    
    # Trending up: higher highs and higher lows
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1] > highs[0] and lows[-1] > lows[0]:
            # Check if breakout (acceleration)
            price_change = (highs[-1] - highs[0]) / highs[0] if highs[0] > 0 else 0
            if price_change > 0.05:  # >5% in macro scale
                return 'breakout'
            return 'trending_up'
    
    # Trending down
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1] < highs[0] and lows[-1] < lows[0]:
            price_change = (lows[-1] - lows[0]) / lows[0] if lows[0] > 0 else 0
            if abs(price_change) > 0.05:
                return 'breakout'
            return 'trending_down'
    
    # Ranging: highs and lows oscillating within band
    if recent_macro:
        all_prices = [p.price for p in recent_macro]
        price_range = (max(all_prices) - min(all_prices)) / min(all_prices) if min(all_prices) > 0 else 0
        if price_range < 0.08:
            return 'ranging'
    
    # Check ATR-based volatility
    if len(ohlcv) >= 20:
        atr = _calc_atr(ohlcv, 14)
        avg_price = sum(b['c'] for b in ohlcv[-20:]) / 20
        atr_pct = atr / avg_price * 100 if avg_price > 0 else 0
        if atr_pct > 5:
            return 'volatile'
    
    return 'ranging'


def _calc_atr(ohlcv, period=14):
    """Calculate Average True Range."""
    if len(ohlcv) < period + 1:
        return 0
    trs = []
    for i in range(1, len(ohlcv)):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    return sum(trs[-period:]) / period


def _build_hierarchy_tree(all_pivots, structures):
    """Build hierarchical confirmation tree.
    
    Returns dict mapping pivot levels to confirmation status:
    {
        'all_aligned': True/False,
        'direction': 'bull'/'bear'/None,
        'levels_confirmed': ['micro','meso','macro'],
        'strength': 0-1
    }
    """
    tree = {
        'all_aligned': False,
        'direction': None,
        'levels_confirmed': [],
        'strength': 0.0,
    }
    
    # Check if swing points are aligned across levels
    micro = all_pivots.get('micro', [])
    meso = all_pivots.get('meso', [])
    macro = all_pivots.get('macro', [])
    
    if not (micro and meso and macro):
        return tree
    
    # Get most recent pivots
    recent_micro = micro[-3:] if len(micro) >= 3 else micro
    recent_meso = meso[-3:] if len(meso) >= 3 else meso
    recent_macro = macro[-3:] if len(macro) >= 3 else macro
    
    # Count directions
    def majority_direction(pivots):
        bulls = sum(1 for p in pivots if not p.is_high)
        bears = sum(1 for p in pivots if p.is_high)
        if bulls > bears:
            return 'bull'
        elif bears > bulls:
            return 'bear'
        return None
    
    micro_dir = majority_direction(recent_micro)
    meso_dir = majority_direction(recent_meso)
    macro_dir = majority_direction(recent_macro)
    
    directions = [micro_dir, meso_dir, macro_dir]
    valid_dirs = [d for d in directions if d is not None]
    
    if valid_dirs and all(d == valid_dirs[0] for d in valid_dirs):
        tree['all_aligned'] = True
        tree['direction'] = valid_dirs[0]
        tree['levels_confirmed'] = ['micro', 'meso', 'macro'][:len(valid_dirs)]
        tree['strength'] = len(valid_dirs) / 3.0
    elif len(valid_dirs) >= 2:
        # Partial alignment
        tree['levels_confirmed'] = ['meso', 'macro'] if macro_dir and meso_dir else ['micro', 'meso']
        tree['strength'] = 0.5
    
    return tree


# ═══════════════════════════════════════════════════════════════════════
# Swing-point-based signal enhancement
# ═══════════════════════════════════════════════════════════════════════

def detect_swing_based_signals(ohlcv, swing_result):
    """Generate enhanced signals using swing points.
    
    Combines SMC concepts with swing point analysis:
    1. Sweep at swing level → stronger than generic Sweep
    2. CHOCH confirmed by swing tree → high confidence
    3. FVG near confirmed swing point → high probability retest
    """
    signals = []
    structures = swing_result.get('structures', [])
    tree = swing_result.get('tree', {})
    macro = swing_result.get('macro', [])
    meso = swing_result.get('meso', [])
    
    # Signal 1: CHOCH at swing point level
    for struct in structures:
        if struct.is_choch:
            direction = 'bull' if struct.direction == 'bullish' else 'bear'
            # Higher score if confirmed by tree
            conf_bonus = 1.5 if tree.get('all_aligned') and tree.get('direction') == direction else 1.0
            signals.append({
                'type': 'Swing_CHOCH',
                'idx': struct.to_pivot.idx,
                'price': struct.to_pivot.price,
                'direction': direction,
                'strength': struct.to_pivot.strength * conf_bonus,
                'structure_bars': struct.bars,
            })
    
    # Signal 2: Liquidity pool (EQH/EQL) at swing levels
    for struct in structures:
        if struct.is_liquidity_pool:
            signals.append({
                'type': 'Swing_LiquidityPool',
                'idx': struct.to_pivot.idx,
                'price': struct.to_pivot.price,
                'direction': 'neutral',
                'strength': 0.7,
                'pivot_level': struct.to_pivot.level,
            })
    
    # Signal 3: Swing level break → potential entry
    if len(macro) >= 2:
        last_swing = macro[-1]
        if last_swing.is_high:
            signals.append({
                'type': 'Swing_Resistance',
                'idx': last_swing.idx,
                'price': last_swing.price,
                'direction': 'bear',
                'strength': last_swing.strength * len(last_swing.confirmed_by) / 2,
            })
        else:
            signals.append({
                'type': 'Swing_Support',
                'idx': last_swing.idx,
                'price': last_swing.price,
                'direction': 'bull',
                'strength': last_swing.strength * len(last_swing.confirmed_by) / 2,
            })
    
    return signals


# ═══════════════════════════════════════════════════════════════════════
# ECharts-compatible output
# ═══════════════════════════════════════════════════════════════════════

def swing_to_echarts(swing_result):
    """Convert swing points to ECharts markPoint/markLine format."""
    mark_points = []
    mark_lines = []
    
    colors = {'micro': '#f0a040', 'meso': '#58a6ff', 'macro': '#3fb950', 'mega': '#f85149'}
    symbols = {'micro': 'circle', 'meso': 'diamond', 'macro': 'triangle', 'mega': 'pin'}
    
    for level in ['micro', 'meso', 'macro', 'mega']:
        pivots = swing_result.get(level, [])
        for sp in pivots:
            point = {
                'name': f'{level.upper()} {"H" if sp.is_high else "L"}',
                'coord': [sp.idx, sp.price],
                'value': f'{sp.price:.2f}',
                'symbol': symbols.get(level, 'circle'),
                'symbolSize': 8 if level == 'micro' else (12 if level == 'meso' else (16 if level == 'macro' else 20)),
                'itemStyle': {'color': colors.get(level, '#888')},
                'label': {'show': True, 'formatter': f'{sp.price:.1f}',
                          'position': 'top' if sp.is_high else 'bottom'},
            }
            mark_points.append(point)
    
    # Add structure lines
    for struct in swing_result.get('structures', []):
        if struct.is_choch or struct.is_bos:
            line = {
                'name': 'CHOCH' if struct.is_choch else 'BOS',
                'coords': [
                    [struct.from_pivot.idx, struct.from_pivot.price],
                    [struct.to_pivot.idx, struct.to_pivot.price],
                ],
                'lineStyle': {
                    'color': '#3fb950' if struct.direction == 'bullish' else '#f85149',
                    'type': 'dashed' if struct.is_choch else 'solid',
                    'width': 2,
                },
            }
            mark_lines.append(line)
    
    return mark_points, mark_lines


# ═══════════════════════════════════════════════════════════════════════
# Quick API
# ═══════════════════════════════════════════════════════════════════════

def analyze_swings(ohlcv):
    """Quick swing analysis — returns the most important signals."""
    result = find_swing_points(ohlcv)
    signals = detect_swing_based_signals(ohlcv, result)
    marks, lines = swing_to_echarts(result)
    
    return {
        'phase': result['current_phase'],
        'tree_direction': result['tree'].get('direction'),
        'tree_aligned': result['tree'].get('all_aligned', False),
        'tree_strength': result['tree'].get('strength', 0),
        'signals': signals,
        'marks': marks,
        'lines': lines,
        'macro_pivots': result.get('macro', []),
        'meso_pivots': result.get('meso', []),
    }
