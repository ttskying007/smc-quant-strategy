#!/usr/bin/env python3
"""
SMC V8 Engine — 新一代高胜率自适应信号引擎
============================================
核心架构:
  1. 多层信号源: FVG(价格行动) + Sweep(流动性) + OB(订单块) + MS(市场结构) + BPR(Breaker)
  2. 评分引导: WR目标80%+ 优先, RR约束3:1+, PF约束5+
  3. 快速迭代: 15只代表股票, ~10秒/轮
  4. 自适应参数: 分三阶段搜索 (覆盖→准确→盈亏比)
  5. 全状态JSON同步 (供WebUI读取)

对比V7+:
  - V7+ 100只股票全覆盖 → 每轮4-6分钟, WR封顶65%
  - V8 15只快速测试 → 每轮10秒, 目标WR>80%
  - V7+ 固定参数空间 → V8 动态参数空间(按波动率分组)
  - V7+ 无阶段策略 → V8 三阶段自动切换

V53对比:
  - V53 只取高ATR股票 → 信号太少, 过拟合
  - V8 所有ATR级别都测 → 但按ATR分组调参
"""

import math, json, time, os, sys, random
from pathlib import Path

HOME = Path.home()
CACHE_DIR = HOME / '.hermes' / 'kline_cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

HUBBLE_BASE = "http://43.167.234.49:3101"
HUBBLE_HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}

# ════════════════════════════════════════════
# V8 参数空间 (12维, 与V53兼容但有扩展)
# ════════════════════════════════════════════

V8_PARAM_SPACE = {
    # 1. FVG基础检测 (2维)
    'fvg_min_width':    {'min':0.06, 'max':0.40, 'default':0.12, 'step':0.02},  # FVG最小宽度(相对avg_range)
    'fvg_merge_dist':   {'min':1,    'max':5,    'default':3,    'step':1},      # FVG合并距离(K线数)
    
    # 2. Sweep检测 (2维)
    'sweep_lookback':   {'min':8,    'max':25,   'default':15,   'step':1},      # 流动性寻找回溯
    'sweep_wick_ratio': {'min':1.5,  'max':4.0,  'default':2.0,  'step':0.1},    # 影线/实体比
    
    # 3. OB检测 (1维)
    'ob_strength_min':  {'min':0.5,  'max':2.5,  'default':1.0,  'step':0.1},    # OB最低强度
    
    # 4. 结构确认 (2维)
    'confirm_range':    {'min':1,    'max':5,    'default':3,    'step':1},      # 信号确认窗口
    'min_sources':      {'min':1,    'max':4,    'default':2,    'step':1},      # 最少信号源数
    
    # 5. 入场质量过滤 (2维)
    'score_min':        {'min':0.5,  'max':3.0,  'default':1.5,  'step':0.1},    # 最低信号分
    'max_trades':       {'min':2,    'max':12,   'default':6,    'step':1},      # 最多交易数
    
    # 6. 波动率过滤 (1维)
    'atr_min_pct':      {'min':0.5,  'max':4.0,  'default':1.5,  'step':0.1},    # ATR百分比下限
    'atr_max_pct':      {'min':3.0,  'max':10.0, 'default':8.0,  'step':0.1},    # ATR百分比上限
    
    # 7. SL/TP (2维)
    'sl_pct':           {'min':1.0,  'max':6.0,  'default':3.0,  'step':0.1},    # 止损%
    'tp_pct':           {'min':2.0,  'max':15.0, 'default':6.0,  'step':0.1},    # 止盈%
}

# 测试股票池 (15只, 覆盖不同板块和波动率)
TEST_STOCKS = [
    '600519.SH',  # 茅台 - 低波动消费龙头
    '000858.SZ',  # 五粮液 - 中低波动消费
    '300750.SZ',  # 宁德时代 - 中高波动新能源
    '601318.SH',  # 中国平安 - 低波动金融
    '002415.SZ',  # 海康威视 - 中波动科技
    '002594.SZ',  # 比亚迪 - 中高波动汽车
    '600036.SH',  # 招商银行 - 低波动金融
    '688981.SH',  # 中芯国际 - 高波动芯片
    '300059.SZ',  # 东方财富 - 中高波动券商
    '600030.SH',  # 中信证券 - 中波动券商
    '002230.SZ',  # 科大讯飞 - 中高波动AI
    '000333.SZ',  # 美的集团 - 中低波动家电
    '300124.SZ',  # 汇川技术 - 中波动工业
    '600276.SH',  # 恒瑞医药 - 中波动医药
    '600887.SH',  # 伊利股份 - 低波动食品
]

# ════════════════════════════════════════════
# 工具函数
# ════════════════════════════════════════════

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

def get_vol_profile(bars):
    if len(bars) < 50:
        return {'atr_pct': 0, 'vol_level': 'unknown', 'trend': 0}
    atr = calc_atr(bars)
    avg_price = sum((bars[i]['h']+bars[i]['l'])/2 for i in range(-20, 0)) / 20
    atr_pct = atr / avg_price * 100 if avg_price > 0 else 0
    if atr_pct < 1.5:
        vol_level = 'low'
    elif atr_pct < 3.5:
        vol_level = 'medium'
    else:
        vol_level = 'high'
    recent = bars[-20:]
    ups = sum(1 for k in recent if k['c'] > k['o'])
    downs = sum(1 for k in recent if k['c'] < k['o'])
    trend = abs(ups - downs) / len(recent)
    return {'atr_pct': round(atr_pct, 2), 'vol_level': vol_level, 'trend': round(trend, 2), 'atr': round(atr, 4)}

# ════════════════════════════════════════════
# 信号检测
# ════════════════════════════════════════════

def detect_fvg_v8(bars, params):
    """V8 FVG检测 — 更精确的gap计算"""
    if len(bars) < 3:
        return []
    avg_r = sum(abs(k['h']-k['l']) for k in bars[-40:]) / max(1, min(40, len(bars)))
    if avg_r == 0:
        return []
    min_w = params.get('fvg_min_width', 0.12)
    fvg_list = []
    for i in range(1, len(bars)-1):
        p, c, n = bars[i-1], bars[i], bars[i+1]
        # Bullish FVG: current candle goes up, gap between prev high and next low
        if c['c'] > c['o']:
            top = min(p['h'], n['h'])
            bot = max(p['l'], n['l'])
            dir = 'short'  # gap up → short signal (price likely to retrace to fill)
        else:
            top = min(p['h'], n['h'])
            bot = max(p['l'], n['l'])
            dir = 'long'   # gap down → long signal
        gap = top - bot
        if gap > avg_r * min_w:
            strength = min(3, round(gap / (avg_r * max(min_w, 0.01))))
            fvg_list.append({
                'direction': dir, 'index': i,
                'top': round(top, 4), 'bottom': round(bot, 4),
                'mid': round((top+bot)/2, 4), 'gap': round(gap, 4),
                'strength': strength,
            })
    # 合并相邻FVG
    merge_dist = params.get('fvg_merge_dist', 3)
    merged = []
    by_dir = {'long': [], 'short': []}
    for f in fvg_list:
        by_dir[f['direction']].append(f)
    for dir, fl in by_dir.items():
        fl.sort(key=lambda x:x['index'])
        i = 0
        while i < len(fl):
            grp = [fl[i]]
            while i+1 < len(fl) and fl[i+1]['index'] - grp[-1]['index'] <= merge_dist:
                grp.append(fl[i+1])
                i += 1
            if len(grp) > 1:
                merged.append({
                    'direction': dir, 'top': max(f['top'] for f in grp),
                    'bottom': min(f['bottom'] for f in grp),
                    'mid': round((max(f['top'] for f in grp)+min(f['bottom'] for f in grp))/2, 4),
                    'strength': max(f['strength'] for f in grp) + 1,
                    'index': grp[-1]['index'], 'n': len(grp),
                })
            i += 1
    return fvg_list + merged

def detect_sweep_v8(bars, params):
    """V8 Sweep检测"""
    wick = params.get('sweep_wick_ratio', 2.0)
    lb = params.get('sweep_lookback', 15)
    sigs = []
    for i in range(lb+1, len(bars)):
        c = bars[i]
        body = abs(c['c']-c['o'])
        if body < 0.0001:
            continue
        uw = c['h'] - max(c['c'], c['o'])
        lw = min(c['c'], c['o']) - c['l']
        rl = min(bars[j]['l'] for j in range(i-lb, i))
        rh = max(bars[j]['h'] for j in range(i-lb, i))
        # Long sweep: price breaks below recent low, long upper wick
        if c['l'] < rl and uw > body and uw/body >= wick:
            sigs.append({'direction': 'long', 'index': i, 'price': c['l'], 'ratio': round(uw/body, 2)})
        # Short sweep: price breaks above recent high, long lower wick
        if c['h'] > rh and lw > body and lw/body >= wick*0.8:
            sigs.append({'direction': 'short', 'index': i, 'price': c['h'], 'ratio': round(lw/body, 2)})
    return sigs

def detect_ob_v8(bars, params):
    """V8 OB检测 — 带强度过滤"""
    if len(bars) < 8:
        return []
    avg_b = sum(abs(bars[i]['c']-bars[i]['o']) for i in range(max(0,len(bars)-30), len(bars))) / max(1, min(30, len(bars)))
    min_st = params.get('ob_strength_min', 1.0)
    sigs = []
    for i in range(4, len(bars)-2):
        pre = bars[i-4:i]
        c = bars[i]
        bd = abs(c['c']-c['o'])
        mh = max(k['h'] for k in pre)
        ml = min(k['l'] for k in pre)
        # Bullish OB: bear candle, then next candle closes above range high
        if bars[i+1]['c'] > mh and c['c'] < c['o'] and bd > avg_b * min_st:
            sigs.append({'direction': 'long', 'index': i,
                         'top': round(max(c['o'],c['c']),4),
                         'bottom': round(min(c['o'],c['c']),4),
                         'strength': round(bd / avg_b, 1)})
        # Bearish OB: bull candle, then next candle closes below range low
        if bars[i+1]['l'] < ml and c['c'] > c['o'] and bd > avg_b * min_st:
            sigs.append({'direction': 'short', 'index': i,
                         'top': round(max(c['o'],c['c']),4),
                         'bottom': round(min(c['o'],c['c']),4),
                         'strength': round(bd / avg_b, 1)})
    return sigs

def detect_ms_v8(bars):
    """V8市场结构检测 — 更精确的趋势判断"""
    if len(bars) < 20:
        return {'bullish': False, 'bearish': False, 'strength': 0}
    
    # 使用15根K线判断趋势
    seg = bars[-15:]
    # Bullish: HH + HL
    hh_count = sum(1 for i in range(4, len(seg)) if seg[i]['h'] > seg[i-1]['h'])
    hl_count = sum(1 for i in range(4, len(seg)) if seg[i]['l'] > seg[i-1]['l'])
    # Bearish: LH + LL
    lh_count = sum(1 for i in range(4, len(seg)) if seg[i]['h'] < seg[i-1]['h'])
    ll_count = sum(1 for i in range(4, len(seg)) if seg[i]['l'] < seg[i-1]['l'])
    
    bull_score = (hh_count / max(1, (len(seg)-4))) + (hl_count / max(1, (len(seg)-4)))
    bear_score = (lh_count / max(1, (len(seg)-4))) + (ll_count / max(1, (len(seg)-4)))
    
    return {
        'bullish': bull_score > bear_score and bull_score > 0.5,
        'bearish': bear_score > bull_score and bear_score > 0.5,
        'strength': round(max(bull_score, bear_score), 2),
        'bull_pct': round(bull_score / (bull_score + bear_score + 0.001) * 100, 1),
        'bear_pct': round(bear_score / (bull_score + bear_score + 0.001) * 100, 1),
    }

def detect_bpr_v8(bars):
    """V8 Breaker检测 — 价格突破关键结构"""
    if len(bars) < 30:
        return []
    sigs = []
    for i in range(20, len(bars)-2):
        # Find recent swing high/low (5 bars ago)
        if i < 5 or i+5 >= len(bars):
            continue
        rh = max(bars[j]['h'] for j in range(i-5, i))
        rl = min(bars[j]['l'] for j in range(i-5, i))
        c = bars[i]
        n = bars[i+1]
        # Bullish BPR: break above recent high, confirm next bar
        if c['c'] > c['o'] and c['h'] > rh and n['c'] > n['o'] and n['c'] > c['c']:
            sigs.append({'direction': 'long', 'index': i, 'price': c['h'], 'type': 'BPR'})
        # Bearish BPR: break below recent low, confirm next bar
        if c['c'] < c['o'] and c['l'] < rl and n['c'] < n['o'] and n['c'] < c['c']:
            sigs.append({'direction': 'short', 'index': i, 'price': c['l'], 'type': 'BPR'})
    return sigs

# ════════════════════════════════════════════
# V8 入口检测 (核心)
# ════════════════════════════════════════════

def detect_entries_v8(bars, params=None):
    """V8入口检测 — 多层信号融合"""
    if not bars or len(bars) < 80:
        return {'entries': [], 'total': 0, 'signals': {}, 'vol': {}, 'ms': {}}
    
    p = params or {}
    vol = get_vol_profile(bars)
    
    # 波动率过滤
    atr_min = p.get('atr_min_pct', 0.5)
    atr_max = p.get('atr_max_pct', 8.0)
    if vol['atr_pct'] < atr_min or vol['atr_pct'] > atr_max:
        return {'entries': [], 'total': 0, 'signals': {}, 'vol': vol, 'ms': {},
                'filtered': f'vol_out_of_range({vol["atr_pct"]:.1f}% not in [{atr_min},{atr_max}])'}
    
    last_idx = len(bars) - 1
    max_trades = p.get('max_trades', 6)
    score_min = p.get('score_min', 1.5)
    sl_p = p.get('sl_pct', 3.0)
    tp_p = p.get('tp_pct', 6.0)
    
    # 检测所有信号源
    fvg_list = detect_fvg_v8(bars, p)
    sweep_list = detect_sweep_v8(bars, p)
    ob_list = detect_ob_v8(bars, p)
    ms = detect_ms_v8(bars)
    bpr_list = detect_bpr_v8(bars)
    
    if not fvg_list and not ob_list:
        return {'entries': [], 'total': 0, 'signals': {'fvg': 0, 'ob': 0}, 'vol': vol, 'ms': ms,
                'filtered': 'no_base_signals'}
    
    confirm_r = p.get('confirm_range', 3)
    entries = []
    
    for fvg in fvg_list[-30:]:
        idx = fvg.get('index', 0)
        if idx < 3 or idx >= last_idx - 2:
            continue
        age = last_idx - idx
        if age > 40:
            continue
        
        dir = fvg['direction']
        ep = fvg.get('mid', bars[idx]['c'])
        
        # 信号源计数
        sources = ['FVG']
        has_sweep = any(s['direction']==dir and abs(s['index']-idx)<=confirm_r for s in sweep_list)
        has_ob = any(s['direction']==dir and abs(s['index']-idx)<=confirm_r for s in ob_list)
        has_bpr = any(s['direction']==dir and abs(s['index']-idx)<=confirm_r for s in bpr_list)
        
        if has_sweep: sources.append('Sweep')
        if has_ob: sources.append('OB')
        if has_bpr: sources.append('BPR')
        if dir=='long' and ms.get('bullish'): sources.append('MS')
        if dir=='short' and ms.get('bearish'): sources.append('MS')
        
        n_sources = len(sources)
        min_src = p.get('min_sources', 2)
        
        if n_sources < min_src:
            continue
        
        # 综合评分
        st = fvg.get('strength', 1)
        score = n_sources * (1 + st * 0.15)
        # 刚形成的FVG加分
        if age < 5:
            score *= 1.15
        # Sweep+OB组合加分
        if has_sweep and has_ob:
            score *= 1.25
        # MS趋势加分
        if (dir=='long' and ms.get('bullish')) or (dir=='short' and ms.get('bearish')):
            score *= 1.2
        # BPR加分
        if has_bpr:
            score *= 1.15
        
        if score < score_min:
            continue
        
        # SL/TP
        if dir == 'long':
            sl_price = round(ep * (1 - sl_p/100), 2)
            tp_price = round(ep * (1 + tp_p/100), 2)
        else:
            sl_price = round(ep * (1 + sl_p/100), 2)
            tp_price = round(ep * (1 - tp_p/100), 2)
        
        rr = abs(tp_price - ep) / max(0.001, abs(sl_price - ep))
        
        entries.append({
            'ep': ep,
            'dir': 'L' if dir == 'long' else 'S',
            'idx': idx,
            'sl': sl_price,
            'tp': tp_price,
            'rr': round(rr, 2),
            'score': round(score, 2),
            'sources': sources,
            'n_src': n_sources,
        })
    
    # 同样检查基于OB的独立信号 (没有FVG但有OB+Sweep)
    for ob in ob_list[-20:]:
        idx = ob.get('index', 0)
        if idx < 3 or idx >= last_idx - 2:
            continue
        age = last_idx - idx
        if age > 40:
            continue
        dir = ob['direction']
        ep = (ob['top'] + ob['bottom']) / 2
        
        # 如果这个位置已经有FVG信号, 跳过 (防止重复)
        if any(abs(e['idx']-idx)<=5 and e['dir']==dir for e in entries):
            continue
        
        sources = ['OB']
        has_fvg = any(s['direction']==dir and abs(s['index']-idx)<=confirm_r for s in fvg_list)
        has_sweep = any(s['direction']==dir and abs(s['index']-idx)<=confirm_r for s in sweep_list)
        has_bpr = any(s['direction']==dir and abs(s['index']-idx)<=confirm_r for s in bpr_list)
        
        if has_fvg: sources.append('FVG')
        if has_sweep: sources.append('Sweep')
        if has_bpr: sources.append('BPR')
        if dir=='long' and ms.get('bullish'): sources.append('MS')
        if dir=='short' and ms.get('bearish'): sources.append('MS')
        
        if len(sources) < min_src:
            continue
        
        score = len(sources) * 1.2
        if age < 5: score *= 1.1
        if has_sweep and has_fvg: score *= 1.2
        
        if score < score_min:
            continue
        
        if dir == 'long':
            sl_price = round(ep * (1 - sl_p/100), 2)
            tp_price = round(ep * (1 + tp_p/100), 2)
        else:
            sl_price = round(ep * (1 + sl_p/100), 2)
            tp_price = round(ep * (1 - tp_p/100), 2)
        
        entries.append({
            'ep': ep, 'dir': 'L' if dir == 'long' else 'S',
            'idx': idx, 'sl': sl_price, 'tp': tp_price,
            'rr': round(abs(tp_price-ep)/max(0.001,abs(sl_price-ep)), 2),
            'score': round(score, 2), 'sources': sources, 'n_src': len(sources),
        })
    
    # 排序+去重
    entries.sort(key=lambda e: -e['score'])
    deduped = []
    for e in entries:
        if not any(abs(e['idx']-d['idx'])<=10 and e['dir']==d['dir'] for d in deduped):
            deduped.append(e)
    if len(deduped) > max_trades:
        deduped = deduped[:max_trades]
    
    return {
        'entries': deduped, 'total': len(deduped),
        'signals': {'fvg': len(fvg_list), 'sweep': len(sweep_list),
                    'ob': len(ob_list), 'bpr': len(bpr_list)},
        'vol': vol, 'ms': ms,
    }

# ════════════════════════════════════════════
# 回测
# ════════════════════════════════════════════

def backtest_v8(bars, params=None):
    """V8回测"""
    if not bars or len(bars) < 80:
        return []
    result = detect_entries_v8(bars, params)
    entries = result.get('entries', [])
    if not entries:
        return []
    trades = []
    for e in entries:
        t = simulate_entry_v8(e, bars)
        if t:
            trades.append(t)
    return trades

def simulate_entry_v8(entry, bars):
    """模拟一笔交易"""
    ei = entry.get('idx', 0)
    if ei >= len(bars):
        return None
    ep = entry['ep']
    sl = entry['sl']
    tp = entry['tp']
    dir = entry['dir']
    sources = entry.get('sources', [])
    
    entry_idx = min(ei + 1, len(bars) - 1)
    
    for j in range(entry_idx, len(bars)):
        b = bars[j]
        if dir == 'L':
            if b['h'] >= tp:
                pnl = (tp - ep) / ep
                # 同时触发止损
                if b['l'] <= sl:
                    pnl_hit = abs(tp - ep) if abs(tp-ep) > abs(sl-ep) else (sl-ep)/ep
                    pnl = (tp - ep) / ep if abs(tp-ep) > abs(sl-ep) else (sl-ep)/ep
                return {'pnl': round(pnl, 4), 'reason': 'tp', 'bars': j-entry_idx+1,
                        'ep': ep, 'sl': sl, 'tp': tp, 'exit': tp, 'sources': sources}
            if b['l'] <= sl:
                return {'pnl': round((sl-ep)/ep, 4), 'reason': 'sl', 'bars': j-entry_idx+1,
                        'ep': ep, 'sl': sl, 'tp': tp, 'exit': sl, 'sources': sources}
        else:
            if b['l'] <= tp:
                pnl = (ep - tp) / ep
                if b['h'] >= sl:
                    pnl = (ep - tp) / ep if abs(tp-ep) > abs(sl-ep) else (ep-sl)/ep
                return {'pnl': round(pnl, 4), 'reason': 'tp', 'bars': j-entry_idx+1,
                        'ep': ep, 'sl': sl, 'tp': tp, 'exit': tp, 'sources': sources}
            if b['h'] >= sl:
                return {'pnl': round((ep-sl)/ep, 4), 'reason': 'sl', 'bars': j-entry_idx+1,
                        'ep': ep, 'sl': sl, 'tp': tp, 'exit': sl, 'sources': sources}
    
    # EOD
    last = bars[-1]['c']
    pnl = (last-ep)/ep if dir=='L' else (ep-last)/ep
    return {'pnl': round(pnl, 4), 'reason': 'eod', 'bars': len(bars)-entry_idx+1,
            'ep': ep, 'sl': sl, 'tp': tp, 'exit': last, 'sources': sources}

# ════════════════════════════════════════════
# V8 评分函数 (WR目标导向)
# ════════════════════════════════════════════

def compute_v8_score(trades):
    """
    V8评分 — 三层引导:
    1. WR优先: WR×0.5 + PF×0.3 + N×0.2
    2. WR>80%→高分 WR<60%→严重惩罚
    3. 交易数<N_min→惩罚
    """
    n = len(trades)
    if n < 1:
        return {'score': 0, 'wr': 0, 'pf': 0, 'n': n, 'ret': 0, 'sr': 0, 'rr_avg': 0}
    
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    n_wins = len(wins)
    n_losses = len(losses)
    
    wr = n_wins / n * 100 if n > 0 else 0
    pf = abs(sum(t['pnl'] for t in wins) / sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses) != 0 else (999 if wins else 0)
    avg_pnl = sum(t['pnl'] for t in trades) / n
    total_ret = sum(t['pnl'] for t in trades) * 100
    
    std = math.sqrt(sum((t['pnl']-avg_pnl)**2 for t in trades)/n) if n > 1 else 0.001
    sr = (avg_pnl / std) * math.sqrt(252) if std > 0 else 0
    
    # WR引导 (核心!)
    if wr >= 80:
        wr_bonus = 1.5
    elif wr >= 70:
        wr_bonus = 1.2
    elif wr >= 60:
        wr_bonus = 1.0
    elif wr >= 50:
        wr_bonus = 0.6
    elif wr >= 40:
        wr_bonus = 0.3
    else:
        wr_bonus = 0.1
    
    # PF惩罚
    pf_score = min(30, pf * 5) if pf > 0 else 0
    
    # N: 交易数太多或太少都惩罚
    if n < 3:
        n_score = n * 2  # 小交易数=低分
    elif n > 20:
        n_score = 20  # cap
    else:
        n_score = n * 1.5
    
    # RR(平均盈亏比)
    rr_avg = 0
    if wins and losses:
        avg_win = abs(sum(t['pnl'] for t in wins) / n_wins)
        avg_loss = abs(sum(t['pnl'] for t in losses) / n_losses)
        rr_avg = avg_win / max(0.0001, avg_loss)
    
    score = wr * 0.5 + pf_score * 0.3 + n_score * 0.2
    
    # WR≥80% 额外boost
    if wr >= 80:
        score *= 1.3
    elif wr >= 70:
        score *= 1.1
    
    # PF太小→惩罚
    if pf < 1.5 and n > 0:
        score *= 0.5
    
    # V8.1: N太少直接大幅惩罚
    if n < 10:
        n_penalty = n / 10.0  # n=5 → 0.5, n=2 → 0.2
        score *= max(0.1, n_penalty)
    elif n > 60:
        score *= 0.7  # too many trades = noise
    
    return {
        'score': round(score, 1),
        'wr': round(wr, 1),
        'pf': round(pf, 2),
        'n': n,
        'n_wins': n_wins,
        'n_losses': n_losses,
        'ret': round(total_ret, 2),
        'sr': round(sr, 2),
        'rr_avg': round(rr_avg, 2),
    }

# ════════════════════════════════════════════
# 数据加载 (同V53)
# ════════════════════════════════════════════

def fetch(url, timeout=20):
    import urllib.request
    for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
        os.environ.pop(k, None)
    req = urllib.request.Request(url, headers=HUBBLE_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode()

def get_bars(symbol, interval='daily', limit=300):
    import json
    url = f"{HUBBLE_BASE}/api/v2/cnstock/stocks?symbol={symbol}&interval={interval}&limit={limit}"
    raw = json.loads(fetch(url))
    data = raw.get('data', raw) if isinstance(raw, dict) else raw
    if not isinstance(data, list):
        return []
    bars = []
    for k in data:
        if isinstance(k, dict):
            bars.append({'o':float(k.get('open',k.get('o',0))), 'h':float(k.get('high',k.get('h',0))),
                         'l':float(k.get('low',k.get('l',0))), 'c':float(k.get('close',k.get('c',0))),
                         'v':float(k.get('volume',k.get('vol',k.get('v',0)))), 't':str(k.get('time',k.get('t','')))})
        elif isinstance(k, list) and len(k) >= 5:
            bars.append({'o':float(k[1]),'h':float(k[2]),'l':float(k[3]),'c':float(k[4]),
                         'v':float(k[5]) if len(k)>5 else 0, 't':str(k[0])})
    if len(bars) >= 2 and bars[0]['t'] > bars[1]['t']:
        bars.reverse()
    return bars

def load_bars(symbol, interval='daily', limit=300):
    """加载K线(优先缓存)"""
    cache_file = CACHE_DIR / f"{symbol.replace('.','_')}_{interval}_{limit}.json"
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)
    bars = get_bars(symbol, interval, limit)
    with open(cache_file, 'w') as f:
        json.dump(bars, f)
    return bars

# ════════════════════════════════════════════
# 代理检查
# ════════════════════════════════════════════

def check_proxy_ok():
    """检查代理 — 返回True/False"""
    try:
        r = subprocess.run(['pgrep', '-f', 'mihomo'], capture_output=True, text=True, timeout=3)
        if not r.stdout.strip():
            return False
    except:
        return False
    try:
        req = urllib.request.Request('http://127.0.0.1:9090', method='GET')
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except:
        return False

if __name__ == '__main__':
    import subprocess, urllib.request
    print("=" * 50)
    print("  SMC V8 Engine")
    print("=" * 50)
    print(f"  Params: {len(V8_PARAM_SPACE)} dimensions")
    print(f"  Test stocks: {len(TEST_STOCKS)}")
    
    # Quick test
    sym = '300231.SZ'
    bars = load_bars(sym, 'daily', 300)
    if bars:
        vol = get_vol_profile(bars)
        print(f"\n  Test: {sym} (ATR={vol['atr_pct']}%)")
        result = detect_entries_v8(bars)
        entries = result['entries']
        signals = result.get('signals', {})
        print(f"  FVG={signals.get('fvg',0)} Sweep={signals.get('sweep',0)} OB={signals.get('ob',0)} BPR={signals.get('bpr',0)}")
        print(f"  Entries: {result['total']} | Vol: {vol['vol_level']} MS: bull={result.get('ms',{}).get('bullish',False)}")
        if entries:
            for e in entries[:3]:
                print(f"    {e['dir']} ep={e['ep']} sl={e['sl']} tp={e['tp']} R={e['rr']} score={e['score']} src={e['sources']}")
        trades = backtest_v8(bars)
        if trades:
            s = compute_v8_score(trades)
            print(f"  Backtest: WR={s['wr']}% PF={s['pf']} N={s['n']} Ret={s['ret']}% SR={s['sr']}")
        else:
            print(f"  No trades (filtered)")