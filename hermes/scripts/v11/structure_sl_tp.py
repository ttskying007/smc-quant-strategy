#!/usr/bin/env python3
"""
SMC Structure-Based SL/TP Calculator
====================================
取代V28的固定SL=0.3% + breakeven trailing

核心原则: SL应该放在SMC结构失效的地方, 而不是一个固定百分比
- 支撑SL: 摆动低点下方 / FVG lower下方 / OB下方 / 扫荡低点下方
- 阻力TP: 下一个摆动高点 / FVG upper / OB upper / 平衡位

四种SL模式(按优先级):
  1. Swing SL:   基于摆动低点的结构SL (最可靠, 但可能太宽)
  2. FVG SL:     基于FVG下边界 (紧但有依据)
  3. OB SL:      基于OB下边界
  4. Sweep SL:   基于扫荡低点 (最紧但容易被触发)
  5. ATR SL:     基于ATR% (最后备选, 当无结构可用)
"""

from typing import List, Dict, Optional, Tuple
from collections import defaultdict


# ============================================================
# Structure finders
# ============================================================

def find_recent_swing_low(ohlcv: List[Dict], entry_idx: int,
                           lookback: int = 30) -> Optional[Dict]:
    """找最近的摆动低点(结构SL候选)
    
    Swing low = 价格低于左右各3根K线
    返回 {idx, price, distance_to_entry}
    """
    if entry_idx < 5:
        return None
    
    start = max(1, entry_idx - lookback)
    best = None
    for i in range(start, entry_idx):
        if i < 1 or i >= len(ohlcv) - 1:
            continue
        left = ohlcv[i-1]['l']
        right = ohlcv[i+1]['l']
        cur_low = ohlcv[i]['l']
        if cur_low < left and cur_low < right:
            # Found swing low
            dist = entry_idx - i
            if dist <= lookback:
                if best is None or i > best['idx']:  # Most recent
                    best = {
                        'idx': i,
                        'price': cur_low,
                        'distance': dist,
                        'type': 'swing_low',
                    }
    return best


def find_recent_swing_high(ohlcv: List[Dict], entry_idx: int,
                            lookback: int = 30) -> Optional[Dict]:
    """找最近的摆动高点(TP候选)"""
    if entry_idx < 5:
        return None
    
    start = max(1, entry_idx - lookback)
    best = None
    for i in range(start, entry_idx):
        if i < 1 or i >= len(ohlcv) - 1:
            continue
        left = ohlcv[i-1]['h']
        right = ohlcv[i+1]['h']
        cur_high = ohlcv[i]['h']
        if cur_high > left and cur_high > right:
            if best is None or i > best['idx']:
                best = {
                    'idx': i,
                    'price': cur_high,
                    'distance': entry_idx - i,
                    'type': 'swing_high',
                }
    return best


def find_next_swing_high(ohlcv: List[Dict], entry_idx: int,
                          lookahead: int = 30) -> Optional[Dict]:
    """找入场后的下一个摆动高点(TP目标)"""
    end = min(entry_idx + lookahead, len(ohlcv) - 1)
    best = None
    for i in range(entry_idx + 2, end):
        if i < 1 or i >= len(ohlcv) - 1:
            continue
        left = ohlcv[i-1]['h']
        right = ohlcv[i+1]['h']
        cur_high = ohlcv[i]['h']
        if cur_high > left and cur_high > right:
            if best is None or cur_high > best['price']:
                best = {
                    'idx': i,
                    'price': cur_high,
                    'distance': i - entry_idx,
                    'type': 'next_swing_high',
                }
    return best


def find_fvg_lower(ohlcv: List[Dict], entry_idx: int,
                   all_signals: List[Dict], lookback: int = 30) -> Optional[Dict]:
    """找最近的FVG下边界作为SL基础
    
    只考虑entry_idx之前的Bull FVG
    """
    bull_fvgs = [s for s in all_signals
                 if 'FVG_Bull' in s.get('type', '')
                 and s.get('idx', 0) < entry_idx
                 and s.get('idx', 0) >= entry_idx - lookback]
    
    if not bull_fvgs:
        return None
    
    # 取最近的FVG
    last = max(bull_fvgs, key=lambda s: s.get('idx', 0))
    return {
        'idx': last.get('idx', 0),
        'price': last.get('lower', 0),
        'upper': last.get('upper', 0),
        'distance': entry_idx - last.get('idx', 0),
        'type': 'fvg_lower',
    }


def find_ob_bottom(ohlcv: List[Dict], entry_idx: int,
                   all_signals: List[Dict], lookback: int = 30) -> Optional[Dict]:
    """找最近的OB下边界"""
    bull_obs = [s for s in all_signals
                if 'OB_Bull' in s.get('type', '')
                and s.get('idx', 0) < entry_idx
                and s.get('idx', 0) >= entry_idx - lookback]
    
    if not bull_obs:
        return None
    
    last = max(bull_obs, key=lambda s: s.get('idx', 0))
    return {
        'idx': last.get('idx', 0),
        'price': last.get('lower', 0),
        'distance': entry_idx - last.get('idx', 0),
        'type': 'ob_bottom',
    }


def find_sweep_low(ohlcv: List[Dict], entry_idx: int,
                   all_signals: List[Dict], lookback: int = 20) -> Optional[Dict]:
    """找最近的扫荡低点(SweepDown的low)"""
    sweeps = [s for s in all_signals
              if 'SweepDown' in s.get('type', '')
              and s.get('idx', 0) < entry_idx
              and s.get('idx', 0) >= entry_idx - lookback]
    
    if not sweeps:
        return None
    
    last = max(sweeps, key=lambda s: s.get('idx', 0))
    return {
        'idx': last.get('idx', 0),
        'price': last.get('lower', 0),  # SweepDown的lower = 扫荡低点
        'distance': entry_idx - last.get('idx', 0),
        'type': 'sweep_low',
    }


# ============================================================
# SL Calculator
# ============================================================

def calc_structure_sl(ohlcv: List[Dict], entry_price: float,
                      entry_idx: int, all_signals: List[Dict],
                      atr_pct: float = None) -> Dict:
    """SMC结构感知止损计算
    
    Returns:
    {
        'price': 止损价格,
        'pct': 止损百分比(相对于入场价),
        'type': 'swing' | 'fvg' | 'ob' | 'sweep' | 'atr',
        'structure_price': 原始结构价格(未加缓冲),
        'buffer_pct': 缓冲百分比,
        'distance_from_entry': 与入场价的距离(绝对值),
    }
    
    SL优先级:
    1. Swing low (结构SL — 最可靠)
    2. FVG lower (FVG下边界 — 次可靠)
    3. OB bottom (OB下边界)
    4. Sweep low (扫荡低点 — 最紧)
    5. ATR-based (最后备用)
    """
    if atr_pct is None:
        # 估算ATR
        ranges = []
        for i in range(max(1, entry_idx - 14), entry_idx):
            tr = max(
                ohlcv[i]['h'] - ohlcv[i]['l'],
                abs(ohlcv[i]['h'] - ohlcv[i-1]['c'] if i > 0 else 0),
                abs(ohlcv[i]['l'] - ohlcv[i-1]['c'] if i > 0 else 0),
            )
            ranges.append(tr / ohlcv[i]['c'] * 100 if ohlcv[i]['c'] > 0 else 0)
        atr_pct = sum(ranges) / len(ranges) if ranges else 2.0
    
    # 尝试每个SL类型
    sl_candidates = []
    
    # 1. Swing low
    swing = find_recent_swing_low(ohlcv, entry_idx)
    if swing:
        buffer = swing['price'] * 0.001  # 0.1% buffer
        sl_price = swing['price'] - buffer
        sl_pct = (entry_price - sl_price) / entry_price * 100
        # Swing SL太宽(>3*ATR)也不合理
        if sl_pct <= atr_pct * 2.5:
            sl_candidates.append({
                'price': sl_price, 'pct': sl_pct, 'type': 'swing',
                'structure_price': swing['price'], 'buffer_pct': 0.1,
            })
    
    # 2. FVG lower
    fvg = find_fvg_lower(ohlcv, entry_idx, all_signals)
    if fvg and fvg['price'] < entry_price:
        buffer = fvg['price'] * 0.001
        sl_price = fvg['price'] - buffer
        sl_pct = (entry_price - sl_price) / entry_price * 100
        if sl_pct <= atr_pct * 2.5:
            sl_candidates.append({
                'price': sl_price, 'pct': sl_pct, 'type': 'fvg',
                'structure_price': fvg['price'], 'buffer_pct': 0.1,
            })
    
    # 3. OB bottom
    ob = find_ob_bottom(ohlcv, entry_idx, all_signals)
    if ob and ob['price'] < entry_price:
        buffer = ob['price'] * 0.001
        sl_price = ob['price'] - buffer
        sl_pct = (entry_price - sl_price) / entry_price * 100
        if sl_pct <= atr_pct * 2.5:
            sl_candidates.append({
                'price': sl_price, 'pct': sl_pct, 'type': 'ob',
                'structure_price': ob['price'], 'buffer_pct': 0.1,
            })
    
    # 4. Sweep low
    sweep = find_sweep_low(ohlcv, entry_idx, all_signals)
    if sweep and sweep['price'] < entry_price:
        buffer = sweep['price'] * 0.001
        sl_price = sweep['price'] - buffer
        sl_pct = (entry_price - sl_price) / entry_price * 100
        if sl_pct <= atr_pct * 2.5:
            sl_candidates.append({
                'price': sl_price, 'pct': sl_pct, 'type': 'sweep',
                'structure_price': sweep['price'], 'buffer_pct': 0.1,
            })
    
    # 选择最佳SL:
    # 理想SL范围: 0.3% ~ 1.5 * ATR%
    if sl_candidates:
        # 优先选 swing > fvg > ob > sweep
        priority = {'swing': 0, 'fvg': 1, 'ob': 2, 'sweep': 3}
        # 在0.5% ~ ATR之间的优先
        ideal_min = max(0.3, atr_pct * 0.15)
        ideal_max = min(atr_pct, 2.5)
        
        # 找在理想范围内且优先级最高的
        candidates_in_range = [c for c in sl_candidates 
                              if ideal_min <= c['pct'] <= ideal_max]
        
        if candidates_in_range:
            best = min(candidates_in_range, key=lambda c: priority.get(c['type'], 99))
        else:
            # 没有在理想范围的，取SWING（最可靠）
            swing_cands = [c for c in sl_candidates if c['type'] == 'swing']
            if swing_cands:
                best = swing_cands[0]
            else:
                # 取最近的
                best = min(sl_candidates, key=lambda c: priority.get(c['type'], 99))
    else:
        # 5. ATR-based (最后备选)
        sl_pct = max(atr_pct * 0.3, 0.5)  # 30% of ATR, 至少0.5%
        best = {
            'price': entry_price * (1 - sl_pct / 100),
            'pct': sl_pct,
            'type': 'atr',
            'structure_price': entry_price * (1 - sl_pct / 100),
            'buffer_pct': 0,
        }
    
    return best


# ============================================================
# TP Calculator
# ============================================================

def calc_structure_tp(ohlcv: List[Dict], entry_price: float,
                      entry_idx: int, sl_price: float,
                      all_signals: List[Dict],
                      atr_pct: float = None) -> Dict:
    """SMC结构感知止盈计算
    
    Returns:
    {
        'price': 止盈价格,
        'pct': 止盈百分比,
        'type': 'swing_high' | 'fvg_upper' | 'rr_target' | 'atr',
        'rr': 盈亏比,
    }
    
    TP优先级:
    1. 下一个摆动高点 (结构TP)
    2. 下一个FVG upper (缺口TP)
    3. RR目标 (至少2R)
    4. ATR-based (最后备选)
    """
    if atr_pct is None:
        ranges = []
        for i in range(max(1, entry_idx - 14), entry_idx):
            tr = max(
                ohlcv[i]['h'] - ohlcv[i]['l'],
                abs(ohlcv[i]['h'] - ohlcv[i-1]['c'] if i > 0 else 0),
                abs(ohlcv[i]['l'] - ohlcv[i-1]['c'] if i > 0 else 0),
            )
            ranges.append(tr / ohlcv[i]['c'] * 100 if ohlcv[i]['c'] > 0 else 0)
        atr_pct = sum(ranges) / len(ranges) if ranges else 2.0
    
    risk = entry_price - sl_price if entry_price > sl_price else sl_price - entry_price
    if risk <= 0:
        risk = entry_price * 0.003  # fallback
    
    # 1. 下一个摆动高点
    next_swing = find_next_swing_high(ohlcv, entry_idx)
    if next_swing and next_swing['price'] > entry_price:
        tp_pct = (next_swing['price'] - entry_price) / entry_price * 100
        rr = (next_swing['price'] - entry_price) / risk
        return {
            'price': next_swing['price'],
            'pct': tp_pct,
            'type': 'swing_high',
            'rr': round(rr, 1),
        }
    
    # 2. FVG upper
    bull_fvgs_ahead = [s for s in all_signals
                        if 'FVG_Bull' in s.get('type', '')
                        and s.get('idx', 0) > entry_idx
                        and s.get('idx', 0) <= entry_idx + 30]
    if bull_fvgs_ahead:
        next_fvg = min(bull_fvgs_ahead, key=lambda s: s.get('idx', 0))
        upper = next_fvg.get('upper', 0)
        if upper > entry_price:
            tp_pct = (upper - entry_price) / entry_price * 100
            rr = (upper - entry_price) / risk
            return {
                'price': upper,
                'pct': tp_pct,
                'type': 'fvg_upper',
                'rr': round(rr, 1),
            }
    
    # 3. RR目标 (2R)
    tp_2r = entry_price + risk * 2
    tp_pct_2r = (tp_2r - entry_price) / entry_price * 100
    return {
        'price': tp_2r,
        'pct': tp_pct_2r,
        'type': 'rr_target',
        'rr': 2.0,
    }


# ============================================================
# Combined Structure SL/TP Calculator
# ============================================================

def calc_structure_sl_tp(ohlcv: List[Dict], entry_price: float,
                          entry_idx: int, all_signals: List[Dict]) -> Dict:
    """完整SMC结构SL/TP计算
    
    返回既包含SL也包含TP的结构信息, 用于前端展示
    """
    sl = calc_structure_sl(ohlcv, entry_price, entry_idx, all_signals)
    atr_pct = None
    ranges = []
    for i in range(max(1, entry_idx - 14), entry_idx):
        tr = max(
            ohlcv[i]['h'] - ohlcv[i]['l'],
            abs(ohlcv[i]['h'] - ohlcv[i-1]['c'] if i > 0 else 0),
            abs(ohlcv[i]['l'] - ohlcv[i-1]['c'] if i > 0 else 0),
        )
        ranges.append(tr / ohlcv[i]['c'] * 100 if ohlcv[i]['c'] > 0 else 0)
    atr_pct = sum(ranges) / len(ranges) if ranges else 2.0
    
    tp = calc_structure_tp(ohlcv, entry_price, entry_idx, sl['price'],
                           all_signals, atr_pct)
    
    return {
        'sl': sl,
        'tp': tp,
        'atr_pct': atr_pct,
        'entry_price': entry_price,
    }


# ============================================================
# Trailing Stop (SMC structure-aware)
# ============================================================

def calc_trailing_structure(ohlcv: List[Dict], entry_idx: int,
                              entry_price: float, initial_sl: float,
                              all_signals: List[Dict], max_hold: int = 60) -> Dict:
    """SMC结构感知追踪止损
    
    不同于V28的breakeven trailing:
    - 只有当价格突破了下一个结构点(swing high / FVG upper)后才上移SL
    - 新的SL跟随到突破的结构点下方
    """
    sl = initial_sl
    exit_idx = -1
    exit_price = None
    won = False
    
    for j in range(entry_idx + 1, min(entry_idx + max_hold + 1, len(ohlcv))):
        bar = ohlcv[j]
        
        # 检查是否有结构突破：价格是否打破了下一个SMC结构
        # 简单规则: 如果价格创了新高(在入场后的范围内), 上移SL
        lookback_from_entry = ohlcv[entry_idx:j+1]
        highest_since_entry = max(b['h'] for b in lookback_from_entry)
        
        if highest_since_entry > entry_price * 1.02:  # 涨了2%+
            # 上移SL到入场价+0.5% (锁定部分利润)
            new_sl = max(sl, entry_price * 1.005)
            sl = new_sl
        
        if highest_since_entry > entry_price * 1.05:  # 涨了5%+
            # 上移SL到入场价+2% (锁大部分利润)
            new_sl = max(sl, entry_price * 1.02)
            sl = new_sl
        
        # 检查是否触发SL
        if bar['l'] <= sl:
            exit_idx = j
            exit_price = max(sl, bar['l'])
            won = exit_price > entry_price
            break
    
    if exit_idx == -1:
        exit_idx = min(entry_idx + max_hold, len(ohlcv) - 1)
        exit_price = ohlcv[exit_idx]['c']
        won = exit_price > entry_price
    
    return {
        'exit_idx': exit_idx,
        'exit_price': exit_price,
        'won': won,
        'sl': sl,
        'pnl_pct': (exit_price - entry_price) / entry_price * 100,
    }
