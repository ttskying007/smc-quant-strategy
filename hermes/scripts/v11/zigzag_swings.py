#!/usr/bin/env python3
"""
Zigzag 结构摆动检测 — 基于价格反转而非固定窗口 pivot

SMC核心: 结构摆动是价格真正反转的点，不是数学极值。
Zigzag: 当价格从上一个极值反转超过阈值时标记摆动。

优势:
- 匹配人眼识别的 HH/HL/LL/LH
- 不受固定窗口限制
- 自动过滤中间噪音
"""

def detect_zigzag_swings(ohlcv, reversal_pct=2.0, use_high_low=True):
    """
    基于 zigzag 反转的摆动检测。
    
    Args:
        ohlcv: K线数据
        reversal_pct: 反转阈值(%)，价格需反转超过此幅度才确认摆动
        use_high_low: True=用最高/最低价，False=用收盘价
    
    Returns: {'highs': [...], 'lows': [...], 'swing_idxs': set()}
    """
    n = len(ohlcv)
    if n < 5:
        return {'highs': [], 'lows': [], 'swing_idxs': set()}
    
    highs = []
    lows = []
    
    # Start from the beginning
    last_swing_bar = 0
    last_swing_price = ohlcv[0]['h'] if use_high_low else ohlcv[0]['c']
    last_swing_type = 'high'  # assume starting high
    extreme_bar = 0
    extreme_price = last_swing_price
    
    for i in range(1, n):
        bar = ohlcv[i]
        current = bar['h'] if (last_swing_type == 'low') else bar['l']
        
        # Track extreme in current direction
        if last_swing_type == 'low':
            # Rising from a low: track highest high
            h = bar['h'] if use_high_low else bar['c']
            if h > extreme_price:
                extreme_price = h
                extreme_bar = i
        else:
            # Falling from a high: track lowest low
            l = bar['l'] if use_high_low else bar['c']
            if l < extreme_price:
                extreme_price = l
                extreme_bar = i
        
        # Check reversal
        if last_swing_type == 'low':
            # Was rising from low, check if we've reversed enough
            retrace = (extreme_price - current) / extreme_price * 100
            if retrace >= reversal_pct:
                # Reversal confirmed: register the extreme as a swing HIGH
                highs.append({
                    'idx': extreme_bar,
                    'bar_idx': extreme_bar,
                    'price': extreme_price,
                    'type': 'zigzag'
                })
                last_swing_type = 'high'
                last_swing_price = extreme_price
                extreme_price = bar['l'] if use_high_low else bar['c']
                extreme_bar = i
        else:
            # Was falling from high, check if we've bounced enough
            bounce = (current - extreme_price) / extreme_price * 100
            if bounce >= reversal_pct:
                # Bounce confirmed: register the extreme as a swing LOW
                lows.append({
                    'idx': extreme_bar,
                    'bar_idx': extreme_bar,
                    'price': extreme_price,
                    'type': 'zigzag'
                })
                last_swing_type = 'low'
                last_swing_price = extreme_price
                extreme_price = bar['h'] if use_high_low else bar['c']
                extreme_bar = i
    
    # Register final extreme (dedup)
    seen_bars = set(h['bar_idx'] for h in highs) | set(l['bar_idx'] for l in lows)
    if last_swing_type == 'low':
        h = max(b['h'] if use_high_low else b['c'] for b in ohlcv[last_swing_bar:])
        for i in range(last_swing_bar, n):
            if (ohlcv[i]['h'] if use_high_low else ohlcv[i]['c']) == h:
                if i not in seen_bars:
                    highs.append({'idx': i, 'bar_idx': i, 'price': h, 'type': 'zigzag'})
                break
    else:
        l = min(b['l'] if use_high_low else b['c'] for b in ohlcv[last_swing_bar:])
        for i in range(last_swing_bar, n):
            if (ohlcv[i]['l'] if use_high_low else ohlcv[i]['c']) == l:
                if i not in seen_bars:
                    lows.append({'idx': i, 'bar_idx': i, 'price': l, 'type': 'zigzag'})
                break
    
    swing_idxs = set()
    for h in highs: swing_idxs.add(h['idx'])
    for l in lows: swing_idxs.add(l['idx'])
    
    return {'highs': highs, 'lows': lows, 'swing_idxs': swing_idxs}
