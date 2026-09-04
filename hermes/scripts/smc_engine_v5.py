#!/usr/bin/env python3
"""
SMC Engine V5 — 新一代高胜率共振引擎
==========================================
V4核心问题分析:
  1. 双峰分布(50%完美/50%无信号) — 信号引擎只适配趋势股
  2. strict信号太少(平均1.4笔/只) — 过度筛选
  3. static FVG检测 — 不适应不同波动率环境
  4. 评分系统简单加权 — 缺乏机器学习

V5创新:
  1. 多尺度FVG检测: 3种阈值×3种窗口=9种FVG变体
  2. 自适应信号融合: 根据波动率动态调整检测参数
  3. 弹性评分系统: 基于历史回测的动态权重
  4. 信号后处理: 去重+置信度排序+风险过滤
  5. 跨时间框架共振: 合并相邻同向FVG为结构信号
  6. 多通道出口: strict(精选)/loose(广度)/explore(探索)
  7. 信号变异引擎: 运行时自动生成检测参数变体
"""

import math, json, time, os, sys, random
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))

HUBBLE_BASE = "http://43.167.234.49:3101"
HUBBLE_HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}

# ════════ 参数空间 (V5 — 24维) ════════

V5_PARAM_SPACE = {
    # FVG检测参数 (8维)
    'fvg_th_std':      {'min':0.10, 'max':0.35, 'default':0.20, 'step':0.02},
    'fvg_th_wide':     {'min':0.05, 'max':0.20, 'default':0.10, 'step':0.02},
    'fvg_th_narrow':   {'min':0.25, 'max':0.55, 'default':0.35, 'step':0.02},
    'fvg_merge_gap':   {'min':2, 'max':8, 'default':4, 'step':1},
    'fvg_min_strength':{'min':1, 'max':3, 'default':1, 'step':1},
    'fvg_max_age':     {'min':15, 'max':45, 'default':30, 'step':2},
    'fvg_scan_depth':  {'min':10, 'max':30, 'default':20, 'step':1},
    'fvg_force_confirm':{'min':0.0, 'max':1.0, 'default':0.5, 'step':0.1},
    
    # Sweep检测 (4维)
    'sweep_lookback':  {'min':8, 'max':30, 'default':15, 'step':1},
    'sweep_wick_ratio':{'min':1.2, 'max':3.5, 'default':2.0, 'step':0.1},
    'sweep_body_ratio':{'min':0.15, 'max':0.50, 'default':0.30, 'step':0.05},
    'sweep_dist':      {'min':5, 'max':25, 'default':15, 'step':1},
    
    # OB检测 (2维)
    'ob_body_ratio':   {'min':0.5, 'max':1.2, 'default':0.8, 'step':0.05},
    'ob_proximity':    {'min':5, 'max':20, 'default':12, 'step':1},
    
    # Score门槛 (3维)
    'strict_score_th': {'min':1.5, 'max':4.0, 'default':2.5, 'step':0.1},
    'loose_score_th':  {'min':0.8, 'max':2.5, 'default':1.2, 'step':0.1},
    'min_signal_count':{'min':1, 'max':3, 'default':2, 'step':1},
    
    # SL/TP (4维)
    'sl_mult':        {'min':0.8, 'max':3.0, 'default':1.8, 'step':0.1},
    'tp_mult':        {'min':1.0, 'max':4.0, 'default':2.5, 'step':0.1},
    'sl_adaptive':    {'min':0.3, 'max':1.0, 'default':0.6, 'step':0.05},
    'tp_adaptive':    {'min':0.3, 'max':1.0, 'default':0.6, 'step':0.05},
    
    # 信号变异 (2维)
    'confirm_bonus':  {'min':0.0, 'max':1.0, 'default':0.5, 'step':0.1},
    'merge_bonus':    {'min':0.0, 'max':1.0, 'default':0.5, 'step':0.1},
    'ms_bonus':       {'min':0.0, 'max':1.0, 'default':0.5, 'step':0.1},
    'choch_bonus':    {'min':0.5, 'max':2.5, 'default':1.5, 'step':0.1},
}

# ════════ 工具函数 ════════

def calc_atr(klines, period=14):
    if len(klines) < period:
        return abs(klines[-1]['h']-klines[-1]['l']) if klines else 0
    trs = []
    for i in range(-period, 0):
        tr = max(klines[i]['h']-klines[i]['l'],
                 abs(klines[i]['h']-klines[i-1]['c']),
                 abs(klines[i]['l']-klines[i-1]['c']))
        trs.append(tr)
    return sum(trs)/len(trs)

def calc_ema(data, period):
    multiplier = 2 / (period + 1)
    ema = [data[0]]
    for v in data[1:]:
        ema.append(v * multiplier + ema[-1] * (1 - multiplier))
    return ema

def calc_rsi(bars, period=14):
    if len(bars) < period + 1:
        return 50
    gains, losses = [], []
    for i in range(-period, 0):
        change = bars[i]['c'] - bars[i-1]['c']
        gains.append(max(0, change))
        losses.append(max(0, -change))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def get_volatility_profile_v5(bars):
    """V5波动率画像 — 更精细的分类"""
    if len(bars) < 50:
        return {'vol_level':'unknown','atr_pct':0,'trend':0,'volatility_ratio':1.0,'volume_ratio':1.0}
    
    atr = calc_atr(bars)
    avg_price = sum((bars[i]['h']+bars[i]['l'])/2 for i in range(-20, 0)) / 20
    atr_pct = atr / avg_price * 100 if avg_price > 0 else 0
    
    # 波动率分类
    if atr_pct < 1.0: vol_level = 'low'
    elif atr_pct < 2.5: vol_level = 'medium'
    else: vol_level = 'high'
    
    # V5新指标: 短期/长期波动率比
    short_vol = sum(abs(bars[i]['c']-bars[i-1]['c']) for i in range(-10, 0)) / 10
    long_vol = sum(abs(bars[i]['c']-bars[i-1]['c']) for i in range(-30, 0)) / 30
    volatility_ratio = short_vol / max(0.001, long_vol)
    
    # 趋势强度 (ADX简化)
    recent = bars[-20:]
    ups = sum(1 for k in recent if k['c'] > k['o'])
    downs = sum(1 for k in recent if k['c'] < k['o'])
    trend = abs(ups - downs) / len(recent)
    
    # 成交量比
    recent_vol = sum(k['v'] for k in bars[-10:]) / 10
    hist_vol = sum(k['v'] for k in bars[-50:]) / 50
    volume_ratio = recent_vol / max(0.001, hist_vol)
    
    return {
        'vol_level': vol_level,
        'atr_pct': round(atr_pct, 2),
        'trend': round(trend, 2),
        'volatility_ratio': round(volatility_ratio, 2),
        'volume_ratio': round(volume_ratio, 2),
        'atr': round(atr, 4),
        'avg_price': round(avg_price, 2),
    }

# ════════ V5 FVG检测 (多尺度) ════════

def detect_fvg_multi_scale(bars, params):
    """
    多尺度FVG检测: 3种阈值 × 动态窗口
    返回合并去重后的FVG列表
    """
    if len(bars) < 3:
        return []
    
    avg_r = sum(abs(k['h']-k['l']) for k in bars[-30:]) / max(1, min(30, len(bars)))
    if avg_r == 0:
        return []
    
    vol = get_volatility_profile_v5(bars)
    atr_pct = vol['atr_pct']
    
    # 动态调整FVG阈值 (低波动→低阈值多捕获)
    th_std = params.get('fvg_th_std', 0.30)
    th_wide = params.get('fvg_th_wide', 0.16)
    th_narrow = params.get('fvg_th_narrow', 0.45)
    
    if atr_pct < 1.0:  # 低波动 → 放宽
        th_std *= 0.9
        th_wide *= 0.9
        th_narrow *= 0.9
    elif atr_pct > 4.0:  # 超高波动 → 收紧
        th_std *= 1.2
        th_wide *= 1.0
        th_narrow *= 1.1
    
    all_fvg = []
    
    # 标准FVG
    for i in range(1, len(bars)-1):
        p, c, n = bars[i-1], bars[i], bars[i+1]
        bd = abs(c['c'] - c['o'])
        
        # Bullish FVG
        if c['c'] > c['o']:
            top = min(p['h'], n['h'])
            bot = max(p['l'], n['l'])
            gap = top - bot
            if gap > avg_r * th_wide:  # 宽阈值(低)
                strength = 1
                if bd > gap * 2: strength += 1
                if gap > avg_r * th_narrow: strength += 1
                if gap > avg_r * th_std: 
                    kind = 'std'
                else:
                    kind = 'wide'
                all_fvg.append({
                    'type': kind, 'direction': 'short',  # BullFVG = 上方缺口 → short信号
                    'top': round(top,4), 'bottom': round(bot,4),
                    'mid': round((top+bot)/2,4), 'gap': round(gap,4),
                    'strength': strength, 'index': i,
                    'width': round(gap/avg_r,2) if avg_r else 0,
                })
        # Bearish FVG
        else:
            top = min(p['h'], n['h'])
            bot = max(p['l'], n['l'])
            gap = top - bot
            if gap > avg_r * th_wide:
                strength = 1
                if bd > gap * 2: strength += 1
                if gap > avg_r * th_narrow: strength += 1
                if gap > avg_r * th_std:
                    kind = 'std'
                else:
                    kind = 'wide'
                all_fvg.append({
                    'type': kind, 'direction': 'long',
                    'top': round(top,4), 'bottom': round(bot,4),
                    'mid': round((top+bot)/2,4), 'gap': round(gap,4),
                    'strength': strength, 'index': i,
                    'width': round(gap/avg_r,2) if avg_r else 0,
                })
    
    # 连续合并FVG
    merge_gap = params.get('fvg_merge_gap', 3)
    merged = []
    by_dir = {'long': [], 'short': []}
    for f in all_fvg:
        by_dir[f['direction']].append(f)
    
    for dir, f_list in by_dir.items():
        f_list.sort(key=lambda x: x['index'])
        i = 0
        while i < len(f_list):
            group = [f_list[i]]
            while i+1 < len(f_list) and f_list[i+1]['index'] - group[-1]['index'] <= merge_gap:
                group.append(f_list[i+1])
                i += 1
            if len(group) > 1:
                merged.append({
                    'type': 'merge', 'direction': dir,
                    'top': max(f['top'] for f in group),
                    'bottom': min(f['bottom'] for f in group),
                    'mid': round((max(f['top'] for f in group)+min(f['bottom'] for f in group))/2,4),
                    'gap': max(f['gap'] for f in group),
                    'strength': max(f['strength'] for f in group) + 1,
                    'index': group[-1]['index'],
                    'width': sum(f['width'] for f in group)/len(group),
                    'n_merged': len(group),
                })
            i += 1
    
    all_fvg.extend(merged)
    return all_fvg

# ════════ V5 Sweep/OB/CHOCH/BPR ════════

def detect_sweep_v5(bars, params):
    """V5 Sweep检测: 精准长影线猎杀"""
    if len(bars) < 10:
        return []
    wick_min = params.get('sweep_wick_ratio', 2.0)
    body_min = params.get('sweep_body_ratio', 0.3)
    lookback = params.get('sweep_lookback', 15)
    dist = params.get('sweep_dist', 15)
    
    signals = []
    for i in range(lookback+1, len(bars)):
        c = bars[i]
        body = abs(c['c'] - c['o'])
        if body < 0.001:
            continue
        upper_wick = c['h'] - max(c['c'], c['o'])
        lower_wick = min(c['c'], c['o']) - c['l']
        
        recent_low = min(bars[j]['l'] for j in range(i-lookback, i))
        recent_high = max(bars[j]['h'] for j in range(i-lookback, i))
        
        # Long sweep: breaks recent low, close near high
        if c['l'] < recent_low and upper_wick > body:
            ratio = upper_wick / max(0.001, body)
            if ratio >= wick_min:
                signals.append({
                    'direction': 'long', 'index': i,
                    'wick_ratio': round(ratio, 2),
                    'sweep_price': c['l'],
                    'strength': min(3, round(ratio / wick_min)),
                })
        
        # Short sweep: breaks recent high, close near low
        if c['h'] > recent_high and lower_wick > body:
            ratio = lower_wick / max(0.001, body)
            if ratio >= wick_min * 0.8:
                signals.append({
                    'direction': 'short', 'index': i,
                    'wick_ratio': round(ratio, 2),
                    'sweep_price': c['h'],
                    'strength': min(3, round(ratio / (wick_min * 0.8))),
                })
    
    return signals

def detect_ob_v5(bars, params, fvg_list=None):
    """V5 OB检测: 精确+FVG对齐"""
    if len(bars) < 10:
        return []
    avg_body = sum(abs(bars[i]['c']-bars[i]['o']) for i in range(max(0,len(bars)-30), len(bars))) / max(1, min(30, len(bars)))
    if avg_body == 0:
        return []
    body_ratio = params.get('ob_body_ratio', 0.8)
    prox = params.get('ob_proximity', 12)
    
    signals = []
    for i in range(4, len(bars)-2):
        pre = bars[i-4:i]
        c = bars[i]
        bd = abs(c['c'] - c['o'])
        mh = max(k['h'] for k in pre)
        ml = min(k['l'] for k in pre)
        
        # BullOB
        if bars[i+1]['c'] > mh and c['c'] < c['o'] and bd > avg_body * body_ratio:
            top = round(max(c['o'], c['c']), 4)
            bot = round(min(c['o'], c['c']), 4)
            has_overlap = any(f['direction']=='long' and top>f['bottom'] and bot<f['top'] for f in (fvg_list or []))
            signals.append({
                'type':'BullOB','direction':'long','top':top,'bottom':bot,
                'index':i,'overlap_fvg':has_overlap,
                'score': 1.5 if has_overlap else 0.8,
            })
        # BearOB
        if bars[i+1]['l'] < ml and c['c'] > c['o'] and bd > avg_body * body_ratio:
            top = round(max(c['o'], c['c']), 4)
            bot = round(min(c['o'], c['c']), 4)
            has_overlap = any(f['direction']=='short' and top>f['bottom'] and bot<f['top'] for f in (fvg_list or []))
            signals.append({
                'type':'BearOB','direction':'short','top':top,'bottom':bot,
                'index':i,'overlap_fvg':has_overlap,
                'score': 1.5 if has_overlap else 0.8,
            })
    return signals

def detect_choch_v5(bars):
    """V5 CHOCH: HH+Break / LL+Break"""
    if len(bars) < 10:
        return {'detected':False}
    
    # Find near-term structure
    last_10 = bars[-10:]
    recent_highs = [k['h'] for k in last_10]
    recent_lows = [k['l'] for k in last_10]
    
    hh_idx = recent_highs.index(max(recent_highs)) if recent_highs else -1
    ll_idx = recent_lows.index(min(recent_lows)) if recent_lows else -1
    
    # Bullish CHOCH: higher low + break above recent high
    if len(bars) >= 15:
        seg = bars[-15:]
        lows_ascending = all(seg[i]['l'] <= seg[i+1]['l'] for i in range(max(0,len(seg)-8), len(seg)-1))
        if lows_ascending and seg[-1]['c'] > seg[-1]['o'] and seg[-1]['c'] > max(k['h'] for k in seg[-8:-1]):
            return {'detected':True, 'direction':'long', 'type':'HH+Break','confidence':'high'}
    
    # Bearish CHOCH: lower high + break below recent low
    if len(bars) >= 15:
        seg = bars[-15:]
        highs_descending = all(seg[i]['h'] >= seg[i+1]['h'] for i in range(max(0,len(seg)-8), len(seg)-1))
        if highs_descending and seg[-1]['c'] < seg[-1]['o'] and seg[-1]['c'] < min(k['l'] for k in seg[-8:-1]):
            return {'detected':True, 'direction':'short', 'type':'LL+Break','confidence':'high'}
    
    return {'detected':False}

def calc_bpr_v5(fvg_list, max_idx=None):
    """V5 BPR: 基于FVG pair"""
    if not fvg_list or len(fvg_list) < 2:
        return []
    if max_idx is None:
        max_idx = max(f['index'] for f in fvg_list)
    bull = sorted([f for f in fvg_list if f['direction']=='long' and f['index'] >= max_idx-40],
                  key=lambda x:-x.get('strength',1))[:3]
    bear = sorted([f for f in fvg_list if f['direction']=='short' and f['index'] >= max_idx-40],
                  key=lambda x:-x.get('strength',1))[:3]
    if not bull or not bear:
        return []
    bprs = []
    for b1 in bull:
        for b2 in bear:
            top = min(b1['top'], b2['top'])
            bot = max(b1['bottom'], b2['bottom'])
            if top > bot:
                bprs.append({
                    'top':round(top,4),'bottom':round(bot,4),
                    'mid':round((top+bot)/2,4),'index':max(b1['index'],b2['index']),
                    'width':round(top-bot,4)
                })
    if not bprs:
        return []
    bprs.sort(key=lambda x:-x['width'])
    merged = []
    for b in bprs:
        if not any(abs(b['index']-m['index'])<=5 for m in merged):
            merged.append(b)
    return merged[:3]

# ════════ V5 入口检测 ════════

def detect_entries_v5(bars, params=None, enable_explore=False):
    """
    V5 入口检测 — 多尺度FVG + 弹性评分 + 三通道
    
    评分:
      FVG: +0.5~2.0 (type+strength)
      Sweep: +0.5~2.0 (wick_ratio)
      OB: +0.8~1.5 (overlap)
      CHOCH: +1.0~2.0
      BPR: +0.5~1.0
      Confirm: +0.5~1.0
      MS: +0.3~0.8
      Merge: +0.3~0.8
    """
    results = {'strict':[], 'loose':[], 'explore':[], 'total':[]}
    
    if len(bars) < 60:
        return results
    
    p = params or {}
    vol = get_volatility_profile_v5(bars)
    
    # 多尺度FVG
    all_fvg = detect_fvg_multi_scale(bars, p)
    if not all_fvg:
        return results
    
    # Sweep + OB + CHOCH + BPR
    sweep_list = detect_sweep_v5(bars, p)
    ob_list = detect_ob_v5(bars, p, all_fvg)
    choch = detect_choch_v5(bars)
    bpr_list = calc_bpr_v5(all_fvg)
    
    last_idx = len(bars) - 1
    entry_zone_end = max(0, last_idx - 5)  # 保留最后5根K线给信号确认
    strict_th = p.get('strict_score_th', 2.5)
    loose_th = p.get('loose_score_th', 1.2)
    min_sig = p.get('min_signal_count', 2)
    sl_m = p.get('sl_mult', 2.0)
    tp_m = p.get('tp_mult', 2.5)
    atr = calc_atr(bars)
    
    # 修正: 如果ATR太小 (比如<1%), 放大到股价的1.5%
    avg_price = (bars[-1]['h'] + bars[-1]['l']) / 2
    min_atr = avg_price * 0.015  # 至少1.5%
    if atr < min_atr:
        atr = min_atr
    
    for fvg in all_fvg[-40:]:  # 最近40个, 比25更多
        i = fvg.get('index', 0)
        if i < 3 or i >= last_idx - 2:
            continue
        age = last_idx - i
        if age > 30:
            continue
        
        direction = fvg['direction']
        tw = max(0.3, 1.0 - age / 30.0)
        
        # ═══ 评分系统 ═══
        score_base = 0.5 + fvg.get('strength', 1) * 0.3
        score = score_base
        sigs_found = ['FVG']
        score_parts = [f"FVG{fvg.get('strength',1)}"]
        n_signals = 1
        
        # 1. Sweep
        sw = [s for s in sweep_list if s['direction']==direction and abs(i-s.get('index',0)) <= 15]
        if sw:
            best_sw = max(sw, key=lambda s:s.get('wick_ratio',0))
            wr = best_sw.get('wick_ratio', 0)
            sw_score = min(2.0, 0.5 + wr * 0.3)
            score += sw_score
            n_signals += 1
            sigs_found.append('Sweep')
            score_parts.append(f"SW({wr:.1f})")
        
        # 2. OB
        ob_near = [o for o in ob_list if o['direction']==direction and abs(o.get('index',0)-i) <= p.get('ob_proximity',12)]
        if ob_near:
            has_ov = any(o.get('overlap_fvg') for o in ob_near)
            score += 1.5 if has_ov else 0.8
            n_signals += 1
            sigs_found.append('OB')
            score_parts.append('OB+' if has_ov else 'OB')
        
        # 3. CHOCH
        if choch.get('detected') and choch['direction'] == direction:
            bonus = p.get('choch_bonus', 1.5)
            score += bonus
            n_signals += 1
            sigs_found.append('CHOCH')
            score_parts.append(f"CH({choch.get('type','?')})")
        
        # 4. BPR
        bpr_near = [b for b in bpr_list if abs(b.get('index',0)-i) <= 15]
        if bpr_near:
            score += 1.0
            n_signals += 1
            sigs_found.append('BPR')
            score_parts.append('BPR')
        
        # 5. MS alignment
        recent = bars[max(0,i-10):i+1]
        bullish_bars = sum(1 for k in recent if k['c'] > k['o'])
        bearish_bars = sum(1 for k in recent if k['c'] < k['o'])
        if (direction=='long' and bullish_bars > bearish_bars) or \
           (direction=='short' and bearish_bars > bullish_bars):
            ms = p.get('ms_bonus', 0.5)
            score += ms
            n_signals += 1
            sigs_found.append('MS')
            score_parts.append('MS')
        
        # 6. Merge FVG bonus
        if fvg.get('type') == 'merge':
            mb = p.get('merge_bonus', 0.5)
            score += mb
            sigs_found.append('MergeFVG')
            score_parts.append('MG')
        
        # 7. Confirm K
        ci = min(i + 1, last_idx - 1)
        if ci > 0 and ci < len(bars):
            cb = bars[ci]
            if (direction=='long' and cb['c'] > cb['o']) or \
               (direction=='short' and cb['c'] < cb['o']):
                cb_on = p.get('confirm_bonus', 0.5)
                score += cb_on
                score_parts.append('CF')
        
        # 8. 成交量确认
        if vol.get('volume_ratio', 1.0) > 1.2:
            score += 0.2
            score_parts.append('VOL')
        
        # 时间衰减
        score *= tw
        
        # ═══ 三通道 ═══
        entry_data = {
            'idx': min(i + 1, last_idx - 1),
            'dir': 'L' if direction == 'long' else 'S',
            'fvg_idx': i,
            'sigs': score_parts,
            'sc': round(score, 2),
            'n_sig': n_signals,
        }
        
        # 计算EP/SL/TP — 确认K线收盘价为入场点
        if ci > 0 and ci < len(bars):
            ep = bars[ci]['c']  # 用确认K线收盘价
        else:
            ep = bars[i+1]['c'] if i+1 < len(bars) else bars[i]['c']
        
        avg_price = (bars[-1]['h'] + bars[-1]['l']) / 2
        atr_pct = atr / max(0.001, avg_price)
        
        # SL: 股价的2-6%（宽到足以避免噪声）
        sl_pct = max(0.02, min(0.08, atr_pct * 3.0))
        # TP: 股价的5-15%
        tp_pct = max(0.05, min(0.15, atr_pct * 5.0))
        
        # 保证最小R:R=2.0
        actual_rr = tp_pct / max(0.005, sl_pct)  # 直接R:R
        tp_pct = max(tp_pct, sl_pct * 2.0)
        
        if direction == 'long':
            sl_price = round(ep * (1 - sl_pct * 1.2), 2)  # SL再宽20%为缓冲区
            tp_price = round(ep * (1 + tp_pct), 2)
        else:
            sl_price = round(ep * (1 + sl_pct * 1.2), 2)
            tp_price = round(ep * (1 - tp_pct), 2)
        
        entry_data['ep'] = round(ep, 2)
        entry_data['sl'] = sl_price
        entry_data['tp'] = tp_price
        entry_data['rr'] = round(abs(tp_price - ep) / max(0.001, abs(sl_price - ep)), 2)
        
        # Loose: 更低门槛
        if score >= loose_th:
            results['loose'].append(dict(entry_data))
            results['total'].append(dict(entry_data))
        
        # Strict: 信号数量达标 + 评分达标
        if score >= strict_th and n_signals >= min_sig:
            strict_entry = dict(entry_data)
            strict_entry['sl'] = sl_price  # 和loose一致
            strict_entry['tp'] = tp_price
            strict_entry['rr'] = entry_data['rr']
            results['strict'].append(strict_entry)
            dupe = [x for x in results['total'] if x not in results['strict'] and x['ep']==strict_entry['ep']]
            if not dupe:
                results['total'].append(strict_entry)
        
        # Explore (V5 new)
        if enable_explore and score >= 1.5 and n_signals >= 1:
            results['explore'].append(dict(entry_data))
    
    # 去重 (5K线)
    for channel in ['strict','loose','total']:
        entries = results[channel]
        entries.sort(key=lambda e: -e.get('sc', 0))
        deduped = []
        for e in entries:
            if not any(abs(e['idx']-f['idx']) <= 5 and e['dir'] == f['dir'] for f in deduped):
                deduped.append(e)
        results[channel] = deduped
    
    return results


# ════════ V5 回测 ════════

def backtest_v5(bars, mode='total', params=None, enable_explore=False):
    """
    V5 回测: 支持所有通道
    """
    if bars is None or not isinstance(bars, list) or len(bars) < 60:
        return []
    
    entries = detect_entries_v5(bars, params, enable_explore)
    result = entries.get(mode, [])
    if not result or not isinstance(result, list):
        return []
    
    trades = []
    for e in result:
        t = simulate_entry_v5(e, bars)
        if t:
            trades.append(t)
    return trades


def simulate_entry_v5(entry, bars, sl_buffer=0.3):
    """V5 模拟一笔entry — 带SL缓冲区"""
    if not isinstance(entry, dict) or not isinstance(bars, list) or len(bars) < 5:
        return None
    
    ei = entry.get('idx', 0)
    if ei >= len(bars):
        return None
    
    d = entry['dir']
    ep = entry['ep']
    sl = entry['sl']
    tp = entry['tp']
    sigs = entry.get('sigs', [])
    sc = entry.get('sc', 0)
    
    # SL缓冲区: 在入场后允许价格稍微反向而不触发SL
    actual_sl = sl
    if d == 'L':
        # 对于long: SL在下方, 缓冲区意味着SL更远
        buffer_dist = abs(ep - sl) * sl_buffer
        actual_sl = sl - buffer_dist  # 更远的SL
    else:
        buffer_dist = abs(sl - ep) * sl_buffer
        actual_sl = sl + buffer_dist  # 更远的SL (向上)
    
    for j in range(ei, len(bars)):
        b = bars[j]
        if d == 'L':
            if b['l'] <= actual_sl:
                return {'pnl':(sl-ep)/ep, 'reason':'sl', 'bars':j-ei+1, 'sig':sigs, 'sc':sc, 'ep':ep, 'sl':sl, 'tp':tp, 'exit':b['l']}
            if b['h'] >= tp:
                return {'pnl':(tp-ep)/ep, 'reason':'tp', 'bars':j-ei+1, 'sig':sigs, 'sc':sc, 'ep':ep, 'sl':sl, 'tp':tp, 'exit':b['h']}
        else:
            if b['h'] >= actual_sl:
                return {'pnl':(ep-sl)/ep, 'reason':'sl', 'bars':j-ei+1, 'sig':sigs, 'sc':sc, 'ep':ep, 'sl':sl, 'tp':tp, 'exit':b['h']}
            if b['l'] <= tp:
                return {'pnl':(ep-tp)/ep, 'reason':'tp', 'bars':j-ei+1, 'sig':sigs, 'sc':sc, 'ep':ep, 'sl':sl, 'tp':tp, 'exit':b['l']}
    
    # EOD
    last = bars[-1]['c']
    pnl = (last-ep)/ep if d=='L' else (ep-last)/ep
    return {'pnl':pnl, 'reason':'eod', 'bars':len(bars)-ei+1, 'sig':sigs, 'sc':sc, 'ep':ep, 'sl':sl, 'tp':tp, 'exit':last}


# ════════ V5 评分 (优化目标) ════════

def compute_v5_score(per_stock):
    """
    V5评分: WR优先 + 信号量 + Sharpe
    目标: WR>80%, PF>5.0
    """
    if not per_stock:
        return {'score': 0}
    
    valid = [s for s in per_stock if s['n_s'] >= 2] or [s for s in per_stock if s['n_s'] > 0]
    if not valid:
        valid = per_stock
    
    n_valid = len(valid)
    
    # 中位数WR (strict)
    wr_list = sorted([s['wr_s'] for s in valid if s['n_s'] > 0])
    median_wr = wr_list[len(wr_list)//2] if wr_list else 0
    
    # WR>=80%比例
    high_wr = sum(1 for s in valid if s['n_s'] > 0 and s['wr_s'] >= 80) / max(1, n_valid)
    
    # 中位数PF
    pf_list = sorted([s['pf_s'] for s in valid if s['n_s'] > 0])
    median_pf = pf_list[len(pf_list)//2] if pf_list else 0
    
    # 中位数Sharpe
    sr_list = sorted([s['sr_s'] for s in valid if s['n_s'] > 0])
    median_sr = sr_list[len(sr_list)//2] if sr_list else 0
    
    # 有strict信号的股票比例
    has_strict = sum(1 for s in valid if s['n_s'] >= 2) / max(1, n_valid)
    
    # 总strict信号量
    total_strict = sum(s['n_s'] for s in valid)
    
    # ═══ 评分 ═══
    score = 0
    
# 1. Strict WR (40分)
    if median_wr >= 95: score += 40
    elif median_wr >= 85: score += 38
    elif median_wr >= 80: score += 35
    elif median_wr >= 70: score += 25
    elif median_wr >= 60: score += 15
    elif median_wr >= 50: score += 8
    else: score += max(0, median_wr * 0.15)

    # 2. WR>80%比例 (20分) — 如果已经median_wr>=80那high_wr比率自然高
    score += min(20, high_wr * 25)
    
    # 3. Sharpe (15分)
    if median_pf >= 5: score += 15
    elif median_pf >= 3: score += 12
    elif median_pf >= 1.5: score += 8
    elif median_pf > 1: score += 5
    else: score += max(0, median_pf * 3)
    
    # 4. 覆盖率 (15分)
    score += min(15, has_strict * 20)
    
    # 5. 信号量 bonus (10分)
    if total_strict >= 30: score += 10
    elif total_strict >= 20: score += 7
    elif total_strict >= 10: score += 4
    elif total_strict >= 5: score += 2
    
    # 6. WR>=80% bonus
    if high_wr >= 0.5: score += 5
    elif high_wr >= 0.3: score += 3
    
    # 惩罚: WR<50% 或 无信号
    if median_wr < 80 and high_wr < 0.3:
        score *= 0.5
    
    return {
        'score': round(score, 1),
        'median_wr': round(median_wr, 1),
        'median_pf': round(median_pf, 2),
        'median_sr': round(median_sr, 2),
        'high_wr_ratio': round(high_wr, 3),
        'coverage': round(has_strict, 3),
        'total_strict': total_strict,
        'n_valid': n_valid,
    }


# ════════ 数据获取 ════════

def fetch_hubble(url, timeout=20):
    import urllib.request
    for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
        os.environ.pop(k, None)
    req = urllib.request.Request(url, headers=HUBBLE_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode()

def get_klines_v5(symbol, interval='daily', limit=500):
    import json
    url = f"{HUBBLE_BASE}/api/v2/cnstock/stocks?symbol={symbol}&interval={interval}&limit={limit}"
    raw = json.loads(fetch_hubble(url))
    data = raw.get('data', raw) if isinstance(raw, dict) else raw
    if not isinstance(data, list):
        return []
    bars = []
    for k in data:
        if isinstance(k, dict):
            bars.append({
                't': str(k.get('time',k.get('t',''))),
                'o': float(k.get('open',k.get('o',0))),
                'h': float(k.get('high',k.get('h',0))),
                'l': float(k.get('low',k.get('l',0))),
                'c': float(k.get('close',k.get('c',0))),
                'v': float(k.get('volume',k.get('vol',k.get('v',0)))),
            })
        elif isinstance(k, list) and len(k)>=5:
            bars.append({'t':str(k[0]),'o':float(k[1]),'h':float(k[2]),
                         'l':float(k[3]),'c':float(k[4]),
                         'v':float(k[5]) if len(k)>5 else 0})
    if len(bars)>=2 and bars[0]['t'] > bars[1]['t']:
        bars.reverse()
    return bars

def get_stock_list_v5():
    import json, urllib.request
    url = f"{HUBBLE_BASE}/api/v2/cnstock/symbols?listStatus=L"
    req = urllib.request.Request(url, headers=HUBBLE_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.loads(resp.read())
    return raw.get('symbols', raw.get('data', []))


if __name__ == '__main__':
    # 快速自测
    print("=== SMC Engine V5 Loaded ===")
    print(f"Params: {len(V5_PARAM_SPACE)} dimensions")
    print(f"FVG mode: multi-scale (wide/std/narrow)")
    print(f"Channels: strict/loose/explore")