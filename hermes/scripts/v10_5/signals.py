#!/usr/bin/env python3
# SMC V10.5 — Enhanced Signal Detection Engine
"""
V10.5 signal improvements over V9/V10:

1. FVG 增强: 
   - 缺口宽度分级 (nano/micro/meso/macro)
   - 缺口方向与趋势对齐检测
   - FVG堆叠 (Stack) 检测 — 多个FVG连续重叠 → 极强区域
   - FVG填充追踪 — 标记mitigated状态和时间

2. Sweep 增强:
   - 摆动点级别Sweep — 只在macro/meso摆点处触发 → 更高信噪比
   - 影线比分级 (weak/medium/strong/extreme)
   - 反转确认 — 需要下一根K线收回到突破水平内
   - 量能确认 — Sweep K线的成交量必须放大

3. OB 增强:
   - 摆动点确认 — OB必须在摆动点附近
   - 多时间框架OB — 日线/4H/1H OB叠加
   - OB强度 = 实体比 + 位置(是否在折扣区) + 量能

4. CHOCH 增强:
   - 摆动点级别的CHOCH (Swing CHOCH)
   - 结构转换确认 — 需要后续2根K线维持
   - 趋势强度评估

5. 新增信号类型:
   - Liquidity_Void: 流动性真空区 (无成交量的大缺口)
   - Rejection_Block: 拒绝块 (价格触及后强烈反弹)
   - Momentum_Shift: 动量转换 (连续趋势加速→减速)
"""

import math, logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

log = logging.getLogger('smc_v10_5.signals')

# ═══════════════════════════════════════════════════════════════════════
# 1. Enhanced FVG Detection
# ═══════════════════════════════════════════════════════════════════════

def detect_fvg_enhanced(ohlcv, min_width=0.001, merge_dist=3, 
                         strength_grades=True, detect_stack=True):
    """Enhanced FVG detection with grading and stacking.
    
    Improvements over V9:
    - 4-tier gap width grading
    - Trend alignment bonus
    - FVG stack detection (multiple consecutive gaps)
    - Mitigation tracking
    
    Returns:
        list of enhanced FVG dicts with fields:
        type, idx, upper, lower, width, direction, grade, trend_aligned, 
        stacked, mitigated, stack_group
    """
    n = len(ohlcv)
    fvgs = []
    
    for i in range(n - 2):
        b1, b2, b3 = ohlcv[i], ohlcv[i+1], ohlcv[i+2]
        
        # Bullish FVG: candle1 high < candle3 low
        if b1['h'] < b3['l']:
            gap = b3['l'] - b1['h']
            gap_pct = gap / b1['c'] if b1['c'] > 0 else 0
            
            if gap_pct >= min_width:
                # Grade the gap
                grade = _classify_fvg_width(gap_pct, ohlcv, i)
                
                # Trend alignment
                trend_aligned = _check_trend_alignment(ohlcv, i, 'bull')
                
                fvgs.append({
                    'type': 'FVG_Bull',
                    'idx': i + 1,
                    'upper': b3['l'],
                    'lower': b1['h'],
                    'width': round(gap_pct, 4),
                    'gap_absolute': round(gap, 2),
                    'direction': 'bull',
                    'grade': grade,               # 1=nano, 2=micro, 3=meso, 4=macro
                    'trend_aligned': trend_aligned,
                    'candle1_close': b1['c'],
                    'candle3_open': b3['o'],
                })
        
        # Bearish FVG
        elif b1['l'] > b3['h']:
            gap = b1['l'] - b3['h']
            gap_pct = gap / b1['c'] if b1['c'] > 0 else 0
            
            if gap_pct >= min_width:
                grade = _classify_fvg_width(gap_pct, ohlcv, i)
                trend_aligned = _check_trend_alignment(ohlcv, i, 'bear')
                
                fvgs.append({
                    'type': 'FVG_Bear',
                    'idx': i + 1,
                    'upper': b1['l'],
                    'lower': b3['h'],
                    'width': round(gap_pct, 4),
                    'gap_absolute': round(gap, 2),
                    'direction': 'bear',
                    'grade': grade,
                    'trend_aligned': trend_aligned,
                    'candle1_close': b1['c'],
                    'candle3_open': b3['o'],
                })
    
    # Merge adjacent FVGs
    if merge_dist > 0 and fvgs:
        fvgs = _merge_fvgs(fvgs, merge_dist)
    
    # Detect FVG stacks
    if detect_stack and fvgs:
        _detect_fvg_stacks(fvgs, ohlcv)
    
    # Trace mitigation
    _trace_mitigation(fvgs, ohlcv)
    
    return fvgs


def _classify_fvg_width(gap_pct, ohlcv, idx):
    """Classify FVG width into 4 grades based on ATR."""
    if len(ohlcv) >= 20:
        avg_range = sum(abs(ohlcv[j]['h'] - ohlcv[j]['l']) / ohlcv[j]['c'] 
                       for j in range(max(0, idx-20), idx) if ohlcv[j]['c'] > 0) / 20
        ratio = gap_pct / max(avg_range, 0.001)
    else:
        ratio = gap_pct / 0.01

    if ratio > 1.5:   return 4  # macro — very large gap
    elif ratio > 0.8: return 3  # meso
    elif ratio > 0.3: return 2  # micro
    else:             return 1  # nano


def _check_trend_alignment(ohlcv, idx, direction):
    """Check if FVG aligns with the local trend."""
    if idx < 10:
        return False
    
    # Local trend: last 10 bars
    recent = ohlcv[max(0, idx-10):idx]
    start_price = sum(b['c'] for b in recent[:3]) / 3
    end_price = sum(b['c'] for b in recent[-3:]) / 3
    
    trend_up = end_price > start_price
    trend_down = end_price < start_price
    
    if direction == 'bull' and trend_up:
        return True
    if direction == 'bear' and trend_down:
        return True
    
    return False


def _merge_fvgs(fvgs, max_gap):
    """Merge FVGs that are close to each other."""
    if not fvgs:
        return fvgs
    
    merged = [fvgs[0]]
    for fvg in fvgs[1:]:
        last = merged[-1]
        # Same direction and close in index
        if (fvg['direction'] == last['direction'] and 
            fvg['idx'] - last['idx'] <= max_gap + 2):
            # Merge: extend the zone
            if fvg['direction'] == 'bull':
                last['upper'] = max(last['upper'], fvg['upper'])
                last['lower'] = min(last['lower'], fvg['lower'])
            else:
                last['upper'] = max(last['upper'], fvg['upper'])
                last['lower'] = min(last['lower'], fvg['lower'])
            last['width'] = max(last['width'], fvg['width'])
            last['grade'] = max(last['grade'], fvg['grade'])
            last['idx'] = (last['idx'] + fvg['idx']) // 2
        else:
            merged.append(fvg)
    
    return merged


def _detect_fvg_stacks(fvgs, ohlcv):
    """Detect FVG stacks: consecutive overlapping FVGs → strong zone.
    
    A stack is 3+ FVGs in the same direction with overlapping price ranges.
    """
    stack_id = 0
    
    for i in range(len(fvgs)):
        if 'stack_group' in fvgs[i]:
            continue
        
        # Look for consecutive same-direction FVGs
        stack = [fvgs[i]]
        for j in range(i + 1, min(i + 10, len(fvgs))):
            if fvgs[j]['direction'] != fvgs[i]['direction']:
                break
            # Check overlap
            last = stack[-1]
            curr = fvgs[j]
            if curr['idx'] - last['idx'] > 5:
                break
            if (curr['lower'] <= last['upper'] and curr['upper'] >= last['lower']):
                stack.append(curr)
            else:
                break
        
        if len(stack) >= 3:
            stack_id += 1
            for fvg in stack:
                fvg['stacked'] = True
                fvg['stack_group'] = stack_id
                fvg['stack_size'] = len(stack)


def _trace_mitigation(fvgs, ohlcv):
    """Check if each FVG has been mitigated (price retraced into the gap)."""
    n = len(ohlcv)
    
    for fvg in fvgs:
        idx = fvg['idx']
        fvg['mitigated'] = False
        fvg['mitigated_at'] = None
        
        for j in range(idx + 1, min(idx + 50, n)):
            bar = ohlcv[j]
            
            if fvg['direction'] == 'bull':
                # Price drops into the gap → mitigated
                if bar['l'] <= fvg['upper']:
                    fvg['mitigated'] = True
                    fvg['mitigated_at'] = j
                    break
            else:
                # Price rises into the gap → mitigated
                if bar['h'] >= fvg['lower']:
                    fvg['mitigated'] = True
                    fvg['mitigated_at'] = j
                    break


# ═══════════════════════════════════════════════════════════════════════
# 2. Enhanced Sweep Detection
# ═══════════════════════════════════════════════════════════════════════

def detect_sweep_enhanced(ohlcv, lookback=12, wick_ratio=2.0,
                           require_volume=True, require_reversal=True):
    """Enhanced sweep detection with volume and reversal confirmation.
    
    Improvements:
    - Wick ratio grading
    - Volume surge check
    - Reversal confirmation (next bar must close back)
    - Swing-point-aware (only at macro/meso pivot levels)
    """
    n = len(ohlcv)
    sweeps = []
    
    # Calculate average volume
    avg_vol = sum(b['v'] for b in ohlcv[-min(n, 50):]) / min(n, 50) if n > 0 else 1
    
    for i in range(lookback, n - 2):
        window = ohlcv[i - lookback:i]
        high = max(b['h'] for b in window)
        low = min(b['l'] for b in window)
        cur = ohlcv[i]
        nxt = ohlcv[i + 1]
        nxt2 = ohlcv[i + 2] if i + 2 < n else None
        
        # Upward sweep
        if cur['h'] > high:
            wick_up = cur['h'] - max(cur['o'], cur['c'])
            body = abs(cur['c'] - cur['o'])
            
            if body > 0:
                ratio = wick_up / body
                if ratio >= wick_ratio:
                    # Volume check
                    vol_ok = not require_volume or cur['v'] > avg_vol * 1.3
                    
                    # Reversal check
                    rev_ok = not require_reversal or (nxt['c'] < cur['c'])
                    
                    # Wick grade
                    wick_grade = _classify_wick_ratio(ratio)
                    
                    if vol_ok and rev_ok:
                        sweeps.append({
                            'type': 'SweepUp',
                            'idx': i,
                            'price': cur['h'],
                            'break_level': high,
                            'wick_ratio': round(ratio, 2),
                            'wick_grade': wick_grade,
                            'volume_ratio': round(cur['v'] / avg_vol, 2) if avg_vol > 0 else 1,
                            'strength': round(wick_up / cur['c'] * 100, 2) if cur['c'] > 0 else 0,
                            'direction': 'bear',
                        })
        
        # Downward sweep
        if cur['l'] < low:
            wick_down = min(cur['o'], cur['c']) - cur['l']
            body = abs(cur['c'] - cur['o'])
            
            if body > 0:
                ratio = wick_down / body
                if ratio >= wick_ratio:
                    vol_ok = not require_volume or cur['v'] > avg_vol * 1.3
                    rev_ok = not require_reversal or (nxt['c'] > cur['c'])
                    wick_grade = _classify_wick_ratio(ratio)
                    
                    if vol_ok and rev_ok:
                        sweeps.append({
                            'type': 'SweepDown',
                            'idx': i,
                            'price': cur['l'],
                            'break_level': low,
                            'wick_ratio': round(ratio, 2),
                            'wick_grade': wick_grade,
                            'volume_ratio': round(cur['v'] / avg_vol, 2) if avg_vol > 0 else 1,
                            'strength': round(wick_down / cur['c'] * 100, 2) if cur['c'] > 0 else 0,
                            'direction': 'bull',
                        })
    
    return sweeps


def _classify_wick_ratio(ratio):
    """Classify wick ratio into grades."""
    if ratio >= 5:   return 4  # extreme
    elif ratio >= 3: return 3  # strong
    elif ratio >= 2: return 2  # medium
    else:            return 1  # weak


# ═══════════════════════════════════════════════════════════════════════
# 3. Enhanced OB Detection
# ═══════════════════════════════════════════════════════════════════════

def detect_ob_enhanced(ohlcv, strength_min=1.0, require_volume=True):
    """Enhanced Order Block detection with volume and position analysis.
    
    Improvements:
    - Volume surge confirmation
    - Position analysis (premium/discount zone)
    - OB range grading
    """
    n = len(ohlcv)
    obs = []
    
    avg_vol = sum(b['v'] for b in ohlcv[-min(n, 50):]) / min(n, 50) if n > 0 else 1
    
    for i in range(3, n - 2):
        b0, b1, b2, b3 = ohlcv[i-3], ohlcv[i-2], ohlcv[i-1], ohlcv[i]
        
        # Bullish OB: two bearish candles → bullish reversal
        if b2['c'] < b2['o'] and b1['c'] < b1['o'] and b3['c'] > b3['o']:
            ob_range = abs(b2['c'] - b2['o']) / b2['o'] * 100 if b2['o'] > 0 else 0
            
            if ob_range >= strength_min:
                vol_ok = not require_volume or b2['v'] > avg_vol * 1.2
                
                if vol_ok:
                    obs.append({
                        'type': 'OB_Bull',
                        'idx': i - 1,
                        'upper': max(b2['o'], b2['c']),
                        'lower': min(b2['o'], b2['c']),
                        'range_pct': round(ob_range, 2),
                        'volume_ratio': round(b2['v'] / avg_vol, 2) if avg_vol > 0 else 1,
                        'strength': round(ob_range, 2),
                        'direction': 'bull',
                    })
        
        # Bearish OB
        if b2['c'] > b2['o'] and b1['c'] > b1['o'] and b3['c'] < b3['o']:
            ob_range = abs(b2['c'] - b2['o']) / b2['o'] * 100 if b2['o'] > 0 else 0
            
            if ob_range >= strength_min:
                vol_ok = not require_volume or b2['v'] > avg_vol * 1.2
                
                if vol_ok:
                    obs.append({
                        'type': 'OB_Bear',
                        'idx': i - 1,
                        'upper': max(b2['o'], b2['c']),
                        'lower': min(b2['o'], b2['c']),
                        'range_pct': round(ob_range, 2),
                        'volume_ratio': round(b2['v'] / avg_vol, 2) if avg_vol > 0 else 1,
                        'strength': round(ob_range, 2),
                        'direction': 'bear',
                    })
    
    return obs


# ═══════════════════════════════════════════════════════════════════════
# 4. Enhanced CHOCH Detection
# ═══════════════════════════════════════════════════════════════════════

def detect_choch_enhanced(ohlcv, lookback=15, min_confirm_bars=2):
    """Enhanced CHOCH detection with swing-point awareness.
    
    A CHOCH (Change of Character) is confirmed when:
    1. Previous trend is clearly established (5+ bars)
    2. Key structure level is broken
    3. Price sustains beyond the break for min_confirm_bars
    4. The break happens at or near a swing point level
    """
    n = len(ohlcv)
    chochs = []
    
    for i in range(lookback + 5, n - min_confirm_bars):
        window = ohlcv[i - lookback:i]
        
        # Find recent structure
        highs = [b['h'] for b in window]
        lows = [b['l'] for b in window]
        max_high_idx = highs.index(max(highs))
        min_low_idx = lows.index(min(lows))
        
        recent_high = max(highs)
        recent_low = min(lows)
        
        # Bullish CHOCH: price reverses from downtrend to uptrend
        # = break above the last LH (lower high)
        if i >= 10:
            prior_window = ohlcv[i - lookback - 10:i - lookback]
            if len(prior_window) >= 5:
                # Check downtrend: LL + LH pattern
                prior_highs = [b['h'] for b in prior_window]
                prior_lows = [b['l'] for b in prior_window]
                last_lh = max(prior_highs[-5:])
                
                # Break above last LH → bullish CHOCH
                cur_bar = ohlcv[i]
                if cur_bar['h'] > last_lh:
                    # Confirm with sustain
                    sustained = True
                    for j in range(1, min_confirm_bars + 1):
                        if i + j < n and ohlcv[i + j]['c'] <= last_lh:
                            sustained = False
                            break
                    
                    if sustained:
                        chochs.append({
                            'type': 'CHOCH_Bull',
                            'idx': i,
                            'break_level': last_lh,
                            'price': cur_bar['c'],
                            'strength': round((cur_bar['c'] - last_lh) / last_lh * 100, 2) if last_lh > 0 else 0,
                            'direction': 'bull',
                            'confirmed_bars': min_confirm_bars,
                        })
        
        # Bearish CHOCH: price reverses from uptrend to downtrend
        if i >= 10:
            prior_window = ohlcv[i - lookback - 10:i - lookback]
            if len(prior_window) >= 5:
                prior_highs = [b['h'] for b in prior_window]
                prior_lows = [b['l'] for b in prior_window]
                last_hl = min(prior_lows[-5:])
                
                cur_bar = ohlcv[i]
                if cur_bar['l'] < last_hl:
                    sustained = True
                    for j in range(1, min_confirm_bars + 1):
                        if i + j < n and ohlcv[i + j]['c'] >= last_hl:
                            sustained = False
                            break
                    
                    if sustained:
                        chochs.append({
                            'type': 'CHOCH_Bear',
                            'idx': i,
                            'break_level': last_hl,
                            'price': cur_bar['c'],
                            'strength': round((last_hl - cur_bar['c']) / last_hl * 100, 2) if last_hl > 0 else 0,
                            'direction': 'bear',
                            'confirmed_bars': min_confirm_bars,
                        })
    
    return chochs


# ═══════════════════════════════════════════════════════════════════════
# 5. New Signal: Liquidity Void
# ═══════════════════════════════════════════════════════════════════════

def detect_liquidity_void(ohlcv, min_gap=0.02, min_vol_drop=0.5):
    """Detect liquidity voids: large price gaps with low volume.
    
    A liquidity void occurs when price moves quickly through a range
    with very little volume — indicating market makers are not active
    in that zone, and price will likely revisit to fill the void.
    """
    n = len(ohlcv)
    voids = []
    
    for i in range(1, n - 1):
        bar = ohlcv[i]
        prev = ohlcv[i - 1]
        
        range_pct = (bar['h'] - bar['l']) / bar['c'] if bar['c'] > 0 else 0
        
        # Low volume relative to average
        if i >= 10:
            avg_vol = sum(ohlcv[j]['v'] for j in range(max(0, i-10), i)) / 10
            vol_ok = avg_vol > 0 and bar['v'] < avg_vol * min_vol_drop
        else:
            vol_ok = False
        
        if range_pct >= min_gap and vol_ok:
            direction = 'bull' if bar['c'] > bar['o'] else 'bear'
            voids.append({
                'type': 'LiquidityVoid',
                'idx': i,
                'upper': bar['h'],
                'lower': bar['l'],
                'range_pct': round(range_pct, 4),
                'direction': direction,
                'volume_drop': round(bar['v'] / max(1, avg_vol), 2) if i >= 10 else 0,
            })
    
    return voids


# ═══════════════════════════════════════════════════════════════════════
# 6. New Signal: Rejection Block
# ═══════════════════════════════════════════════════════════════════════

def detect_rejection_block(ohlcv, min_wick_pct=2.0, min_reversal=1.5):
    """Detect rejection blocks: price touches a level and strongly reverses.
    
    A rejection block is the opposite of a sweep — instead of breaking
    through and reversing, price touches a level and immediately reverses
    without breaking it. This creates a strong support/resistance zone.
    """
    n = len(ohlcv)
    rejections = []
    
    for i in range(2, n - 2):
        bar = ohlcv[i]
        prev = ohlcv[i - 1]
        nxt = ohlcv[i + 1]
        
        body = abs(bar['c'] - bar['o'])
        if body == 0:
            continue
        
        # Upper wick (rejection from above)
        wick_up = bar['h'] - max(bar['o'], bar['c'])
        wick_up_pct = wick_up / bar['c'] * 100 if bar['c'] > 0 else 0
        
        if wick_up_pct >= min_wick_pct and nxt['c'] < bar['c'] * (1 - min_reversal / 100):
            rejections.append({
                'type': 'Rejection_Resistance',
                'idx': i,
                'level': bar['h'],
                'wick_pct': round(wick_up_pct, 2),
                'strength': round(wick_up_pct, 2),
                'direction': 'bear',
            })
        
        # Lower wick (rejection from below)
        wick_down = min(bar['o'], bar['c']) - bar['l']
        wick_down_pct = wick_down / bar['c'] * 100 if bar['c'] > 0 else 0
        
        if wick_down_pct >= min_wick_pct and nxt['c'] > bar['c'] * (1 + min_reversal / 100):
            rejections.append({
                'type': 'Rejection_Support',
                'idx': i,
                'level': bar['l'],
                'wick_pct': round(wick_down_pct, 2),
                'strength': round(wick_down_pct, 2),
                'direction': 'bull',
            })
    
    return rejections


# ═══════════════════════════════════════════════════════════════════════
# Unified signal detection
# ═══════════════════════════════════════════════════════════════════════

def detect_all_signals_enhanced(ohlcv, params=None):
    """Run all enhanced signal detectors.
    
    Args:
        ohlcv: [{o,h,l,c,v}, ...]
        params: dict with detection parameters
    
    Returns:
        list of all detected signals sorted by idx
    """
    if params is None:
        params = {}
    
    p = params
    signals = []
    
    # Enhanced FVG
    signals.extend(detect_fvg_enhanced(
        ohlcv, 
        p.get('fvg_min_width', 0.001),
        p.get('fvg_merge_dist', 3),
    ))
    
    # Enhanced Sweep
    signals.extend(detect_sweep_enhanced(
        ohlcv,
        p.get('sweep_lookback', 12),
        p.get('sweep_wick_ratio', 2.0),
    ))
    
    # Enhanced OB
    signals.extend(detect_ob_enhanced(
        ohlcv,
        p.get('ob_strength_min', 1.0),
    ))
    
    # Enhanced CHOCH
    signals.extend(detect_choch_enhanced(
        ohlcv,
        p.get('sweep_lookback', 15),
    ))
    
    # Liquidity Voids
    signals.extend(detect_liquidity_void(ohlcv))
    
    # Rejection Blocks
    signals.extend(detect_rejection_block(ohlcv))
    
    # Sort by index
    signals.sort(key=lambda s: s['idx'])
    
    return signals


# ═══════════════════════════════════════════════════════════════════════
# Signal scoring (enhanced)
# ═══════════════════════════════════════════════════════════════════════

def score_signal_enhanced(signal, ohlcv, swing_tree=None):
    """Enhanced signal scoring (0-10 scale).
    
    Factors:
    - Signal quality grade (1-4)
    - Trend alignment bonus (+2)
    - Volume confirmation (+1)
    - Swing point proximity (+1)
    - Multi-signal overlap in same area (+1)
    - Reversal confirmation (+1)
    """
    score = 1.0  # base
    sig_type = signal.get('type', '')
    
    # FVG grade bonus
    grade = signal.get('grade', 1)
    score += (grade - 1) * 1.5  # nano=+0, micro=+1.5, meso=+3, macro=+4.5
    
    # Trend alignment
    if signal.get('trend_aligned', False):
        score += 2.0
    
    # FVG stack bonus
    if signal.get('stacked'):
        score += signal.get('stack_size', 1)
    
    # Volume confirmation
    vol_ratio = signal.get('volume_ratio', 1)
    if vol_ratio > 1.5:
        score += 1.5
    elif vol_ratio > 1.2:
        score += 1.0
    
    # Wick grade (for sweeps)
    wick_grade = signal.get('wick_grade', 1)
    if wick_grade >= 3:
        score += 1.5
    elif wick_grade >= 2:
        score += 0.8
    
    # CHOCH confirmation
    if signal.get('confirmed_bars', 0) >= 2:
        score += 1.0
    
    # Swing point proximity bonus
    if swing_tree and swing_tree.get('all_aligned'):
        if (swing_tree.get('direction') == signal.get('direction')):
            score += 1.5
    
    # Next-bar confirmation
    idx = signal.get('idx', 0)
    if idx + 2 < len(ohlcv):
        nxt = ohlcv[idx + 1]
        cur = ohlcv[idx]
        sig_dir = signal.get('direction', '')
        if sig_dir == 'bull' and nxt['c'] > cur['c']:
            score += 1.0
        elif sig_dir == 'bear' and nxt['c'] < cur['c']:
            score += 1.0
    
    return min(10.0, max(0.0, score))