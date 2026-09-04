#!/usr/bin/env python3
"""
V17 结构区域扫描器 — 多源TP/SL结构化扫描

从V17信号引擎输出中提取所有可用结构点，构建TP和SL区域列表。
用于入场决策: 评估入场位置是否在强支撑/阻力位，TP是否充足。

核心逻辑:
- TP: 入场价上方所有结构阻力 → FVG顶/OB顶/swing_high/BOS/CHOCH level/EQH
- SL: 入场价下方所有结构支撑 → FVG底/OB底/swing_low/BOS/CHOCH level/EQL
- 过滤: TP<1%不用, SL<0.5%或高于入场不用
- 输出: 按距离排序的结构区域列表 + 入场质量评分
"""

from typing import List, Dict, Tuple, Optional
import math


def scan_structure_zones(ohlcv, signals_v17, entry_bar, entry_price, direction='bull'):
    """
    扫描入场点前后的所有结构区域。
    
    Args:
        ohlcv: K线数据
        signals_v17: V17 detect_all_signals_v17() 的输出
        entry_bar: 入场K线索引
        entry_price: 入场价格 (可以是收盘价或区域价格)
        direction: 'bull' (做多) 或 'bear' (做空)
    
    Returns:
        {
            'tp_zones': [{type, bar, price, distance_pct, strength, source}],
            'sl_zones': [{type, bar, price, distance_pct, strength, source}],
            'entry_quality': {score, sl_distance, tp_count, tp_distances, ...}
        }
    """
    swings = signals_v17.get('swings', {})
    adaptive = signals_v17.get('adaptive', {})
    atr_val = adaptive.get('atr_value', 0.01)
    avg_price = adaptive.get('avg_close', entry_price)
    
    # Minimum distance thresholds
    min_tp_pct = 1.0   # TP must be at least 1% from entry
    min_sl_pct = 0.3   # SL must be at least 0.3% from entry
    
    tp_zones = []
    sl_zones = []
    
    if direction == 'bull':
        _scan_bull_tp(ohlcv, signals_v17, entry_bar, entry_price, tp_zones, min_tp_pct)
        _scan_bull_sl(ohlcv, signals_v17, entry_bar, entry_price, sl_zones, min_sl_pct)
    else:
        _scan_bear_tp(ohlcv, signals_v17, entry_bar, entry_price, tp_zones, min_tp_pct)
        _scan_bear_sl(ohlcv, signals_v17, entry_bar, entry_price, sl_zones, min_sl_pct)
    
    # Sort by distance from entry
    tp_zones.sort(key=lambda z: z['distance_pct'])
    sl_zones.sort(key=lambda z: z['distance_pct'])
    
    # Deduplicate by price proximity
    tp_zones = _dedup_zones(tp_zones, atr_val)
    sl_zones = _dedup_zones(sl_zones, atr_val)
    
    # Quality scoring
    quality = _score_entry_quality(tp_zones, sl_zones, entry_bar, signals_v17, atr_val)
    
    return {
        'tp_zones': tp_zones,
        'sl_zones': sl_zones,
        'entry_quality': quality,
    }


def _add_zone(zones, typ, bar, price, entry_price, strength, source, metadata=None):
    """添加结构区域，自动计算距离"""
    distance_pct = abs(price - entry_price) / entry_price * 100
    zone = {
        'type': typ,
        'bar': bar,
        'price': round(price, 4),
        'distance_pct': round(distance_pct, 2),
        'strength': round(strength, 2),
        'source': source,
    }
    if metadata:
        zone['metadata'] = metadata
    zones.append(zone)


def _scan_bull_tp(ohlcv, signals, entry_bar, entry_price, tp_zones, min_tp_pct):
    """扫描做多TP目标 (入场价上方)"""
    n = len(ohlcv)
    
    # 1. FVG_Bull tops and FVG_Bear tops (resistance)
    for fvg in signals.get('fvg', []):
        if fvg['idx'] >= entry_bar:  # future FVG
            top = fvg.get('upper', 0)
            if top > entry_price:
                dist = (top - entry_price) / entry_price * 100
                if dist >= min_tp_pct:
                    _add_zone(tp_zones, 'FVG_top', fvg['idx'], top, entry_price,
                             fvg.get('strength', 3), 'fvg',
                             {'fvg_type': fvg.get('type', '?'), 'gap': fvg.get('metadata', {}).get('gap', 0)})
    
    # 2. OB_Bear tops (supply zone = resistance for longs)
    for ob in signals.get('ob', []):
        if ob.get('type') == 'OB_Bear' and ob['idx'] >= entry_bar:
            top = ob.get('upper', 0)
            if top > entry_price:
                dist = (top - entry_price) / entry_price * 100
                if dist >= min_tp_pct:
                    _add_zone(tp_zones, 'OB_top', ob['idx'], top, entry_price,
                             ob.get('strength', 4), 'ob',
                             {'disp_ratio': ob.get('metadata', {}).get('displacement_ratio', 0)})
    
    # 3. Swing highs (前高)
    swings = signals.get('swings', {})
    # We need full swing data — use ohlcv-based pivot detection
    # Instead, scan from signals metadata
    for sig_type in ['CHOCH_Bull', 'BOS_Bull']:
        for s in signals.get('choch', []) + signals.get('bos', []):
            if s.get('type') == sig_type and s['idx'] > entry_bar:
                level = s.get('metadata', {}).get('break_level', 0)
                if level > entry_price:
                    dist = (level - entry_price) / entry_price * 100
                    if dist >= min_tp_pct:
                        _add_zone(tp_zones, f'{sig_type}_level', s['idx'], level, entry_price,
                                 s.get('strength', 4), 'structure',
                                 {'break_pct': s.get('metadata', {}).get('break_pct', 0)})
    
    # 4. EQH levels
    for e in signals.get('eql', []):
        if e.get('type') == 'EQH' and e['idx'] > entry_bar:
            level = e.get('metadata', {}).get('level', e.get('price', 0))
            if level > entry_price:
                dist = (level - entry_price) / entry_price * 100
                if dist >= min_tp_pct:
                    _add_zone(tp_zones, 'EQH', e['idx'], level, entry_price,
                             e.get('strength', 3), 'eql')
    
    # 5. Sweep_BSL levels (swept highs = resistance)
    for sw in signals.get('sweep', []):
        if sw.get('type') == 'Sweep_BSL' and sw['idx'] > entry_bar:
            swept = sw.get('metadata', {}).get('swept_level', 0)
            if swept > entry_price:
                dist = (swept - entry_price) / entry_price * 100
                if dist >= min_tp_pct:
                    _add_zone(tp_zones, 'BSL_swept', sw['idx'], swept, entry_price,
                             sw.get('strength', 4), 'liquidity')


def _scan_bull_sl(ohlcv, signals, entry_bar, entry_price, sl_zones, min_sl_pct):
    """扫描做多SL支撑 (入场价下方)"""
    
    # 1. FVG_Bull lower edges (支撑)
    for fvg in signals.get('fvg', []):
        if fvg.get('type') == 'FVG_Bull':
            lo = fvg.get('lower', 0)
            if lo < entry_price:
                dist = (entry_price - lo) / entry_price * 100
                if dist >= min_sl_pct:
                    _add_zone(sl_zones, 'FVG_lower', fvg['idx'], lo, entry_price,
                             fvg.get('strength', 3), 'fvg')
    
    # 2. OB_Bull lower edges (支撑)
    for ob in signals.get('ob', []):
        if ob.get('type') == 'OB_Bull':
            lo = ob.get('lower', 0)
            if lo < entry_price:
                dist = (entry_price - lo) / entry_price * 100
                if dist >= min_sl_pct:
                    _add_zone(sl_zones, 'OB_lower', ob['idx'], lo, entry_price,
                             ob.get('strength', 4), 'ob')
    
    # 3. CHOCH_Bear / BOS_Bear break levels (below = structure support)
    for s in signals.get('choch', []) + signals.get('bos', []):
        if s.get('type') in ('CHOCH_Bear', 'BOS_Bear'):
            level = s.get('metadata', {}).get('break_level', 0)
            if 0 < level < entry_price:
                dist = (entry_price - level) / entry_price * 100
                if dist >= min_sl_pct:
                    _add_zone(sl_zones, f'{s["type"]}_level', s['idx'], level, entry_price,
                             s.get('strength', 4), 'structure')
    
    # 4. EQL levels
    for e in signals.get('eql', []):
        if e.get('type') == 'EQL':
            level = e.get('metadata', {}).get('level', e.get('price', 0))
            if level < entry_price:
                dist = (entry_price - level) / entry_price * 100
                if dist >= min_sl_pct:
                    _add_zone(sl_zones, 'EQL', e['idx'], level, entry_price,
                             e.get('strength', 3), 'eql')
    
    # 5. Sweep_SSL levels (swept lows = support)
    for sw in signals.get('sweep', []):
        if sw.get('type') == 'Sweep_SSL':
            swept = sw.get('metadata', {}).get('swept_level', 0)
            if swept < entry_price:
                dist = (entry_price - swept) / entry_price * 100
                if dist >= min_sl_pct:
                    _add_zone(sl_zones, 'SSL_swept', sw['idx'], swept, entry_price,
                             sw.get('strength', 4), 'liquidity')


def _scan_bear_tp(ohlcv, signals, entry_bar, entry_price, tp_zones, min_tp_pct):
    """扫描做空TP目标 (入场价下方)"""
    # Mirror of bull TP: look for supports BELOW entry
    for fvg in signals.get('fvg', []):
        if fvg.get('type') == 'FVG_Bear' and fvg['idx'] >= entry_bar:
            lo = fvg.get('lower', 0)
            if lo < entry_price:
                dist = (entry_price - lo) / entry_price * 100
                if dist >= min_tp_pct:
                    _add_zone(tp_zones, 'FVG_lower', fvg['idx'], lo, entry_price,
                             fvg.get('strength', 3), 'fvg')
    
    for ob in signals.get('ob', []):
        if ob.get('type') == 'OB_Bull' and ob['idx'] >= entry_bar:
            lo = ob.get('lower', 0)
            if lo < entry_price:
                dist = (entry_price - lo) / entry_price * 100
                if dist >= min_tp_pct:
                    _add_zone(tp_zones, 'OB_lower', ob['idx'], lo, entry_price,
                             ob.get('strength', 4), 'ob')
    
    for e in signals.get('eql', []):
        if e.get('type') == 'EQL' and e['idx'] > entry_bar:
            level = e.get('metadata', {}).get('level', e.get('price', 0))
            if level < entry_price:
                dist = (entry_price - level) / entry_price * 100
                if dist >= min_tp_pct:
                    _add_zone(tp_zones, 'EQL', e['idx'], level, entry_price,
                             e.get('strength', 3), 'eql')
    
    for sw in signals.get('sweep', []):
        if sw.get('type') == 'Sweep_SSL' and sw['idx'] > entry_bar:
            swept = sw.get('metadata', {}).get('swept_level', 0)
            if swept < entry_price:
                dist = (entry_price - swept) / entry_price * 100
                if dist >= min_tp_pct:
                    _add_zone(tp_zones, 'SSL_swept', sw['idx'], swept, entry_price,
                             sw.get('strength', 4), 'liquidity')


def _scan_bear_sl(ohlcv, signals, entry_bar, entry_price, sl_zones, min_sl_pct):
    """扫描做空SL阻力 (入场价上方)"""
    for fvg in signals.get('fvg', []):
        if fvg.get('type') == 'FVG_Bear':
            top = fvg.get('upper', 0)
            if top > entry_price:
                dist = (top - entry_price) / entry_price * 100
                if dist >= min_sl_pct:
                    _add_zone(sl_zones, 'FVG_upper', fvg['idx'], top, entry_price,
                             fvg.get('strength', 3), 'fvg')
    
    for ob in signals.get('ob', []):
        if ob.get('type') == 'OB_Bear':
            top = ob.get('upper', 0)
            if top > entry_price:
                dist = (top - entry_price) / entry_price * 100
                if dist >= min_sl_pct:
                    _add_zone(sl_zones, 'OB_upper', ob['idx'], top, entry_price,
                             ob.get('strength', 4), 'ob')


def _dedup_zones(zones, atr_val, price_tolerance_pct=0.15):
    """合并价格过于接近的区域（同一结构的不同表现形式）"""
    if len(zones) < 2:
        return zones
    
    result = [zones[0]]
    for z in zones[1:]:
        last = result[-1]
        price_diff_pct = abs(z['price'] - last['price']) / max(last['price'], 0.01) * 100
        if price_diff_pct < price_tolerance_pct:
            # Keep the stronger one
            if z['strength'] > last['strength']:
                result[-1] = z
        else:
            result.append(z)
    
    return result


def _score_entry_quality(tp_zones, sl_zones, entry_bar, signals, atr_val):
    """
    入场质量评分 (0-10)
    
    维度:
    - SL距离: 最近SL≥1% +2分, ≥2% +4分
    - TP数量: ≥2个 +2分, ≥3个 +3分  
    - 信号强度: 触发信号strength≥5 +1分
    - 趋势对齐: trend_aligned +1分
    """
    score = 0.0
    details = {}
    
    # SL距离评分
    if sl_zones:
        nearest_sl = sl_zones[0]['distance_pct']
        details['nearest_sl_pct'] = nearest_sl
        if nearest_sl >= 3.0:
            score += 5.0
        elif nearest_sl >= 2.0:
            score += 4.0
        elif nearest_sl >= 1.0:
            score += 2.5
        elif nearest_sl >= 0.5:
            score += 1.0
        else:
            score += 0.0  # SL too close = poor entry
    else:
        details['nearest_sl_pct'] = 0
        score += 0.0  # no SL found
    
    # TP数量评分
    tp_count = len(tp_zones)
    details['tp_count'] = tp_count
    if tp_count >= 4:
        score += 3.0
    elif tp_count >= 2:
        score += 2.0
    elif tp_count >= 1:
        score += 1.0
    
    # TP距离 (最近的TP有多远)
    if tp_zones:
        nearest_tp = tp_zones[0]['distance_pct']
        details['nearest_tp_pct'] = nearest_tp
        if nearest_tp >= 3.0:
            score += 1.5
        elif nearest_tp >= 2.0:
            score += 1.0
    
    # Cap at 10
    details['score'] = min(10.0, score)
    return details
