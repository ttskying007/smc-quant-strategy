#!/usr/bin/env python3
"""
结构摆动过滤器 — 只保留 HH/HL/LL/LH 结构点

SMC核心: 摆动只有在创建新的结构时才有效。
- HH: swing_high > prev_swing_high (higher high — 上升趋势延续)
- LH: swing_high < prev_swing_high (lower high — 上升趋势减弱)
- HL: swing_low > prev_swing_low (higher low — 下降趋势减弱)
- LL: swing_low < prev_swing_low (lower low — 下降趋势延续)

过滤掉: 与前一个摆动基本同价或微幅波动的小摆动
"""

def classify_swings(swing_highs, swing_lows):
    """
    给每个摆动点标注结构类型: HH, LH, HL, LL, or None
    
    Returns: filtered lists with structure_type metadata
    """
    # Sort by bar index
    highs = sorted(swing_highs, key=lambda x: x['bar_idx'])
    lows = sorted(swing_lows, key=lambda x: x['bar_idx'])
    
    # Classify highs
    classified_highs = []
    prev_high = None
    for h in highs:
        stype = None
        if prev_high is None:
            stype = 'HH'  # first high is always valid
        elif h['price'] > prev_high['price']:
            stype = 'HH'
        elif h['price'] < prev_high['price']:
            stype = 'LH'
        # Equal price: skip (not a meaningful structure point)
        
        if stype:
            h_copy = dict(h)
            h_copy['structure_type'] = stype
            h_copy['prev_price'] = prev_high['price'] if prev_high else None
            classified_highs.append(h_copy)
            prev_high = h
    
    # Classify lows
    classified_lows = []
    prev_low = None
    for l in lows:
        stype = None
        if prev_low is None:
            stype = 'LL'  # first low is always valid
        elif l['price'] > prev_low['price']:
            stype = 'HL'
        elif l['price'] < prev_low['price']:
            stype = 'LL'
        
        if stype:
            l_copy = dict(l)
            l_copy['structure_type'] = stype
            l_copy['prev_price'] = prev_low['price'] if prev_low else None
            classified_lows.append(l_copy)
            prev_low = l
    
    return classified_highs, classified_lows


def filter_structural_swings(swings_dict):
    """
    从原始摆动中过滤出结构性摆动(HH/HL/LL/LH)
    
    Input: {'highs': [...], 'lows': [...], 'swing_idxs': set()}
    Output: {'highs': [...], 'lows': [...], 'swing_idxs': set()}
    """
    highs, lows = classify_swings(swings_dict['highs'], swings_dict['lows'])
    
    swing_idxs = set()
    for h in highs: swing_idxs.add(h['idx'])
    for l in lows: swing_idxs.add(l['idx'])
    
    return {'highs': highs, 'lows': lows, 'swing_idxs': swing_idxs}


def filter_by_min_amplitude(swings_dict, min_pct=0.5):
    """
    额外过滤: 与前一个同向摆动幅度不足 min_pct% 的摆动
    """
    highs = swings_dict.get('highs', [])
    lows = swings_dict.get('lows', [])
    
    filtered_highs = []
    prev_h = None
    for h in highs:
        if prev_h is None:
            filtered_highs.append(h)
        else:
            amp_pct = abs(h['price'] - prev_h['price']) / prev_h['price'] * 100
            if amp_pct >= min_pct:
                filtered_highs.append(h)
        prev_h = h
    
    filtered_lows = []
    prev_l = None
    for l in lows:
        if prev_l is None:
            filtered_lows.append(l)
        else:
            amp_pct = abs(l['price'] - prev_l['price']) / prev_l['price'] * 100
            if amp_pct >= min_pct:
                filtered_lows.append(l)
        prev_l = l
    
    swing_idxs = set()
    for h in filtered_highs: swing_idxs.add(h['idx'])
    for l in filtered_lows: swing_idxs.add(l['idx'])
    
    return {'highs': filtered_highs, 'lows': filtered_lows, 'swing_idxs': swing_idxs}
