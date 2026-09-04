#!/usr/bin/env python3
"""
V38 — Wyckoff阶段检测
========================
基于Wyckoff理论的4阶段 + 2亚型:
- Accumulation (吸筹): 窄幅盘整, 成交量极度萎缩, 支撑位多次测试
  - Spring/Wyckoff Bounce: 假跌破快速收回 (SMR)
- Markup (拉升): 突破盘整区, 成交量放大, HH/HL序列
  - PSY (Preliminary Support): 初步支撑后的突破
- Distribution (派发): 到达阻力区, 成交量高潮, 价量背离
  - UTAD (Upthrust After Distribution): 假突破快速回落
- Reaccumulation (再吸筹): 拉升后中继盘整
  - 类似accumulation但在更高价位

5个阶段信号:
1. Accumulation_Begin (吸筹早期) - 窄幅+缩量+多次测试
2. Accumulation_End (吸筹结束) - 突破+放量+新高
3. Markup_Continue (拉升中继) - HH/HL+趋势巩固
4. Distribution_Begin (派发早期) - UPTHRUST+量缩+价弱
5. Distribution_End (派发结束) - 跌破+加速下跌

评分: 0-1.0, >0.7 = 强阶段信号
"""

def detect_wyckoff_phases(ohlcv, structure_tree, lookback=60):
    """
    Wyckoff 4阶段检测
    返回: {
        'primary_phase': 'accumulation'|'markup'|'distribution'|'reaccumulation'|'unknown',
        'confidence': 0.0-1.0,
        'phase_signals': [...],
        'markup_stage': 0-100 (拉升完成度%),
        'accumulation_start_idx': int|None,
        'volume_profile': str,
    }
    """
    n = len(ohlcv)
    if n < lookback:
        return {'primary_phase': 'unknown', 'confidence': 0.0, 'phase_signals': []}
    
    seg = ohlcv[-lookback:]
    seg_high = max(b['h'] for b in seg)
    seg_low = min(b['l'] for b in seg)
    seg_mid = (seg_high + seg_low) / 2
    seg_range = (seg_high - seg_low) / seg_mid * 100
    
    current = ohlcv[-1]['c']
    
    # 成交量分析
    avg_vol = sum(b.get('v', b.get('vol', 0)) for b in seg) / len(seg)
    recent_vol = sum(b.get('v', b.get('vol', 0)) for b in seg[-10:]) / 10
    vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0
    
    # 价格位置分析
    price_position = (current - seg_low) / (seg_high - seg_low) * 100 if seg_high > seg_low else 50
    
    # 趋势结构
    macro_trend = structure_tree.structures.get('macro', {}).get('trend', 'neutral')
    meso_trend = structure_tree.structures.get('meso', {}).get('trend', 'neutral')
    
    # 支撑/阻力
    supports = structure_tree.get_multi_level_support()
    resistances = structure_tree.get_multi_level_resistance()
    
    phase_signals = []
    primary_phase = 'unknown'
    max_conf = 0.0
    
    # ── 信号1: Accumulation (吸筹) ──
    acc_score = 0.0
    indicators = []
    
    # 窄幅 = 盘整
    if seg_range < 10:
        acc_score += 0.25
        indicators.append('narrow_range')
    
    # 成交量萎缩
    if vol_ratio < 0.8:
        acc_score += 0.20
        indicators.append('volume_shrinking')
    
    # 多次测试支撑位 (价格在低点反弹2次+)
    if supports.get('macro') and supports.get('meso'):
        macro_support = supports['macro']
        meso_support = supports['meso']
        test_count = 0
        for i in range(max(0, n-40), n):
            b = ohlcv[i]
            if b['l'] <= meso_support * 1.02:  # 接近支撑
                test_count += 1
        if test_count >= 2:
            acc_score += 0.15
            indicators.append(f'retest_{test_count}x')
    
    # 价格在低位
    if price_position < 35:
        acc_score += 0.15
        indicators.append('low_zone')
    
    # 没有明确上升趋势
    if macro_trend != 'up':
        acc_score += 0.15
        indicators.append(f'trend_{macro_trend}')
    
    # Spring/Wyckoff Bounce检测 (假跌破快速收回)
    for i in range(max(0, n-15), n):
        if i < 2: continue
        bar, prev = ohlcv[i], ohlcv[i-1]
        if bar['l'] < seg_low * 0.995 and bar['c'] > seg_low * 0.998:
            # 下破+收回 = Spring
            acc_score += 0.20
            indicators.append('spring')
            break
    
    acc_conf = min(acc_score, 1.0)
    if acc_conf >= 0.45:
        phase_signals.append({
            'phase': 'accumulation',
            'confidence': round(acc_conf, 3),
            'indicators': indicators,
            'subtype': 'spring' if 'spring' in indicators else 'base_building',
        })
        if acc_conf > max_conf:
            primary_phase = 'accumulation'
            max_conf = acc_conf
    
    # ── 信号2: Markup (拉升) ──
    markup_score = 0.0
    indicators_m = []
    
    # HH/HL序列 (明确的上升趋势)
    if macro_trend == 'up' and meso_trend == 'up':
        markup_score += 0.30
        indicators_m.append('hh_hl_both')
    elif macro_trend == 'up' or meso_trend == 'up':
        markup_score += 0.15
        indicators_m.append('partial_hh_hl')
    
    # 成交量放量(突破确认)
    if vol_ratio > 1.2:
        markup_score += 0.20
        indicators_m.append('volume_expanding')
    
    # 价格在高位
    if price_position > 65:
        markup_score += 0.15
        indicators_m.append('high_zone')
    
    # 突破盘整区
    if seg_range < 12 and current > seg_high * 0.99:
        markup_score += 0.20
        indicators_m.append('breakout')
    
    # 价格在中位之上且趋势向上
    if price_position > 50 and meso_trend == 'up':
        markup_score += 0.10
        indicators_m.append('mid_above_up')
    
    markup_conf = min(markup_score, 1.0)
    if markup_conf >= 0.45:
        phase_signals.append({
            'phase': 'markup',
            'confidence': round(markup_conf, 3),
            'indicators': indicators_m,
            'subtype': 'breakout' if 'breakout' in indicators_m else 'trending',
        })
        if markup_conf > max_conf:
            primary_phase = 'markup'
            max_conf = markup_conf
    
    # ── 信号3: Distribution (派发) ──
    dist_score = 0.0
    indicators_d = []
    
    # 价格在阻力区
    if price_position > 75:
        dist_score += 0.20
        indicators_d.append('resistance_zone')
    
    # 成交量高潮后萎缩 (价量背离)
    if vol_ratio > 1.5 and current < seg_high * 0.99:
        dist_score += 0.15
        indicators_d.append('volume_climax')
    elif vol_ratio < 0.7 and price_position > 65:
        # 高位缩量 = 买盘衰竭
        dist_score += 0.15
        indicators_d.append('volume_fade')
    
    # 趋势顶背离 (价格高但动量减弱)
    if macro_trend == 'up' and meso_trend == 'neutral':
        dist_score += 0.15
        indicators_d.append('trend_divergence')
    
    # Upthrust检测 (假突破+快速回撤)
    for i in range(max(0, n-10), n):
        if i < 2: continue
        bar, prev = ohlcv[i], ohlcv[i-1]
        if bar['h'] > seg_high * 0.998 and bar['c'] < prev['c'] * 0.995:
            dist_score += 0.20
            indicators_d.append('upthrust')
            break
    
    # 价格在区间顶部但收弱
    if price_position > 70:
        close_pos = (current - seg_low) / (seg_high - seg_low) * 100
        if close_pos < price_position - 15:
            dist_score += 0.15
            indicators_d.append('weak_close')
    
    dist_conf = min(dist_score, 1.0)
    if dist_conf >= 0.40:
        phase_signals.append({
            'phase': 'distribution',
            'confidence': round(dist_conf, 3),
            'indicators': indicators_d,
            'subtype': 'upthrust' if 'upthrust' in indicators_d else 'top_building',
        })
        if dist_conf > max_conf:
            primary_phase = 'distribution'
            max_conf = dist_conf
    
    # ── 信号4: Reaccumulation (再吸筹/中继) ──
    reacc_score = 0.0
    indicators_r = []
    
    # 前面是markup
    if macro_trend == 'up':
        reacc_score += 0.15
        indicators_r.append('prior_up')
    
    # 窄幅盘整(在中高位)
    if seg_range < 10 and price_position > 30 and price_position < 70:
        reacc_score += 0.25
        indicators_r.append('narrow_mid')
    
    # 成交量萎缩(吸筹特征)
    if vol_ratio < 0.85:
        reacc_score += 0.15
        indicators_r.append('volume_shrinking')
    
    # 支撑位测试后反弹
    if supports.get('meso') and current > supports['meso'] * 1.01:
        reacc_score += 0.15
        indicators_r.append('support_hold')
    
    reacc_conf = min(reacc_score, 1.0)
    if reacc_conf >= 0.40:
        phase_signals.append({
            'phase': 'reaccumulation',
            'confidence': round(reacc_conf, 3),
            'indicators': indicators_r,
            'subtype': 'middleground' if 'support_hold' in indicators_r else 'base_building',
        })
        if reacc_conf > max_conf:
            primary_phase = 'reaccumulation'
            max_conf = reacc_conf
    
    # 计算拉升完成度 (position in markup cycle)
    markup_stage = price_position
    if primary_phase == 'accumulation':
        markup_stage = 0
    elif primary_phase == 'distribution':
        markup_stage = 100
    
    return {
        'primary_phase': primary_phase,
        'confidence': round(max_conf, 3),
        'phase_signals': phase_signals,
        'markup_stage': round(markup_stage, 0),
        'volume_profile': 'climax' if vol_ratio > 1.5 else 'expanding' if vol_ratio > 1.2 else 'normal' if vol_ratio > 0.8 else 'shrinking',
        'price_position': round(price_position, 0),
        'range_pct': round(seg_range, 2),
    }


# 阶段自适应参数映射
PHASE_ADAPTIVE_PARAMS = {
    'accumulation': {
        'sl_mult': 0.3,       # V38.3: 吸筹阶段紧止损 (假突破多), 原0.6
        'tp_mult': 2.0,       # 预期拉伸空间大
        'min_score': 0.50,    # 低门槛入场
        'max_trades': 1,      # 只做1笔
    },
    'markup': {
        'sl_mult': 0.4,       # V38.3: 拉升阶段宽松止损, 原0.8
        'tp_mult': 2.5,       # 预期大空间
        'min_score': 0.60,    # 中等门槛
        'max_trades': 3,      # 可做多笔
    },
    'distribution': {
        'sl_mult': 0.25,      # V38.3: 派发阶段紧止损, 原0.5
        'tp_mult': 1.5,       # 空间有限
        'min_score': 0.70,    # 高门槛
        'max_trades': 1,      # 谨慎入场
        'bear_bias': True,    # 偏向做空
    },
    'reaccumulation': {
        'sl_mult': 0.35,      # V38.3: 中继盘整中等止损, 原0.7
        'tp_mult': 2.0,       # 预期继续拉升
        'min_score': 0.55,    # 中等偏低门槛
        'max_trades': 2,
    },
    'unknown': {
        'sl_mult': 0.35,
        'tp_mult': 2.0,
        'min_score': 0.60,
        'max_trades': 2,
    },
}


def get_phase_params(phase):
    """获取阶段自适应参数"""
    return PHASE_ADAPTIVE_PARAMS.get(phase, PHASE_ADAPTIVE_PARAMS['unknown'])
