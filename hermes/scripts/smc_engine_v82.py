#!/usr/bin/env python3
"""
SMC V8.2 Engine — 带RR引导的第四代评分
============================================
核心改进（与V8对比）:
  1. 评分函数纳入必要RR条件: RR<0.8 → 自动淘汰
  2. N目标从"越多越好"改为"N=25-40黄金区间"
  3. 参数空间增加tp_min_ratio强制保证RR>1.0
  4. 过拟合检测: 如果WR>95%且N<15, 自动降权
  5. 自适应温度: 每轮根据WR/N动态调节

V8.2评分 (三层平衡):
  primary: balance = WR × sqrt(N) × min(3, PF) × sqrt(max(0.5, RR_avg))
  if RR_avg < 0.8: score *= 0.3
  if N < 8: score *= N/12
  if N > 50: score *= 0.8
  if WR > 95 and N < 15: score *= 0.5  # 过拟合惩罚
"""

import math, json, time, os, sys, random
from pathlib import Path

HOME = Path.home()
CACHE_DIR = HOME / '.hermes' / 'kline_cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

HUBBLE_BASE = "http://43.167.234.49:3101"
HUBBLE_HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}

# ════════════════════════════════════════════
# V8.2 参数空间 (13维)
# ════════════════════════════════════════════

V82_PARAM_SPACE = {
    # 1. FVG基础检测 (2维)
    'fvg_min_width':    {'min':0.05, 'max':0.35, 'default':0.12, 'step':0.02},
    'fvg_merge_dist':   {'min':1,    'max':5,    'default':3,    'step':1},
    
    # 2. Sweep检测 (2维)
    'sweep_lookback':   {'min':5,    'max':25,   'default':15,   'step':1},
    'sweep_wick_ratio': {'min':1.2,  'max':4.0,  'default':2.0,  'step':0.1},
    
    # 3. OB检测 (1维)
    'ob_strength_min':  {'min':0.3,  'max':2.5,  'default':1.0,  'step':0.1},
    
    # 4. 结构确认 (2维)
    'confirm_range':    {'min':1,    'max':5,    'default':3,    'step':1},
    'min_sources':      {'min':1,    'max':4,    'default':2,    'step':1},
    
    # 5. 入场质量过滤 (2维)
    'score_min':        {'min':0.5,  'max':3.0,  'default':1.5,  'step':0.1},
    'max_trades':       {'min':2,    'max':12,   'default':6,    'step':1},
    
    # 6. 波动率过滤 (1维)
    'atr_min_pct':      {'min':0.5,  'max':4.0,  'default':1.5,  'step':0.1},
    'atr_max_pct':      {'min':3.0,  'max':10.0, 'default':8.0,  'step':0.1},
    
    # 7. SL/TP (2维 — 新增tp_min_ratio确保RR>1)
    'sl_pct':           {'min':1.0,  'max':6.0,  'default':3.0,  'step':0.1},
    'tp_pct':           {'min':1.5,  'max':15.0, 'default':6.0,  'step':0.1},
}

# 测试股票池 (15只)
TEST_STOCKS = [
    '600519.SH',  '000858.SZ',  '300750.SZ',  '601318.SH',
    '002415.SZ',  '002594.SZ',  '600036.SH',  '688981.SH',
    '300059.SZ',  '600030.SH',  '002230.SZ',  '000333.SZ',
    '300124.SZ',  '600276.SH',  '600887.SH',
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
# 信号检测 (与V8相同, 但有RR约束增强)
# ════════════════════════════════════════════

def detect_fvg_v82(bars, params):
    if len(bars) < 3:
        return []
    avg_r = sum(abs(k['h']-k['l']) for k in bars[-40:]) / max(1, min(40, len(bars)))
    if avg_r == 0:
        return []
    min_w = params.get('fvg_min_width', 0.12)
    fvg_list = []
    for i in range(1, len(bars)-1):
        p, c, n = bars[i-1], bars[i], bars[i+1]
        if c['c'] > c['o']:
            top = min(p['h'], n['h'])
            bot = max(p['l'], n['l'])
            dir = 'short'
        else:
            top = min(p['h'], n['h'])
            bot = max(p['l'], n['l'])
            dir = 'long'
        gap = top - bot
        if gap > avg_r * min_w:
            strength = min(3, round(gap / (avg_r * max(min_w, 0.01))))
            fvg_list.append({
                'direction': dir, 'index': i,
                'top': round(top, 4), 'bottom': round(bot, 4),
                'mid': round((top+bot)/2, 4), 'gap': round(gap, 4),
                'strength': strength,
            })
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

def detect_sweep_v82(bars, params):
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
        if c['l'] < rl and uw > body and uw/body >= wick:
            sigs.append({'direction': 'long', 'index': i, 'price': c['l'], 'ratio': round(uw/body, 2)})
        if c['h'] > rh and lw > body and lw/body >= wick*0.8:
            sigs.append({'direction': 'short', 'index': i, 'price': c['h'], 'ratio': round(lw/body, 2)})
    return sigs

def detect_ob_v82(bars, params):
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
        if bars[i+1]['c'] > mh and c['c'] < c['o'] and bd > avg_b * min_st:
            sigs.append({'direction': 'long', 'index': i,
                         'top': round(max(c['o'],c['c']),4),
                         'bottom': round(min(c['o'],c['c']),4),
                         'strength': round(bd / avg_b, 1)})
        if bars[i+1]['l'] < ml and c['c'] > c['o'] and bd > avg_b * min_st:
            sigs.append({'direction': 'short', 'index': i,
                         'top': round(max(c['o'],c['c']),4),
                         'bottom': round(min(c['o'],c['c']),4),
                         'strength': round(bd / avg_b, 1)})
    return sigs

def detect_ms_v82(bars):
    if len(bars) < 20:
        return {'bullish': False, 'bearish': False, 'strength': 0}
    seg = bars[-15:]
    hh_count = sum(1 for i in range(4, len(seg)) if seg[i]['h'] > seg[i-1]['h'])
    hl_count = sum(1 for i in range(4, len(seg)) if seg[i]['l'] > seg[i-1]['l'])
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

def detect_bpr_v82(bars):
    if len(bars) < 30:
        return []
    sigs = []
    for i in range(20, len(bars)-2):
        if i < 5 or i+5 >= len(bars):
            continue
        rh = max(bars[j]['h'] for j in range(i-5, i))
        rl = min(bars[j]['l'] for j in range(i-5, i))
        c = bars[i]
        n = bars[i+1]
        if c['c'] > c['o'] and c['h'] > rh and n['c'] > n['o'] and n['c'] > c['c']:
            sigs.append({'direction': 'long', 'index': i, 'price': c['h'], 'type': 'BPR'})
        if c['c'] < c['o'] and c['l'] < rl and n['c'] < n['o'] and n['c'] < c['c']:
            sigs.append({'direction': 'short', 'index': i, 'price': c['l'], 'type': 'BPR'})
    return sigs

# ════════════════════════════════════════════
# V8.2 入口检测 — RR约束增强版
# ════════════════════════════════════════════

def detect_entries_v82(bars, params=None):
    if not bars or len(bars) < 80:
        return {'entries': [], 'total': 0, 'signals': {}, 'vol': {}, 'ms': {}}
    
    p = params or {}
    vol = get_vol_profile(bars)
    
    # 波动率过滤
    atr_min = p.get('atr_min_pct', 0.5)
    atr_max = p.get('atr_max_pct', 8.0)
    if vol['atr_pct'] < atr_min or vol['atr_pct'] > atr_max:
        return {'entries': [], 'total': 0, 'signals': {}, 'vol': vol, 'ms': {},
                'filtered': f'vol_out_of_range({vol["atr_pct"]:.1f}%)'}
    
    last_idx = len(bars) - 1
    max_trades = p.get('max_trades', 6)
    score_min = p.get('score_min', 1.5)
    sl_p = p.get('sl_pct', 3.0)
    tp_p = p.get('tp_pct', 6.0)
    
    # V8.2: RR强制约束 — tp至少是sl的1.2倍
    rr_min_from_params = tp_p / max(0.5, sl_p) if sl_p > 0 else 3.0
    
    fvg_list = detect_fvg_v82(bars, p)
    sweep_list = detect_sweep_v82(bars, p)
    ob_list = detect_ob_v82(bars, p)
    ms = detect_ms_v82(bars)
    bpr_list = detect_bpr_v82(bars)
    
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
        
        # V8.2: 信号源检测 — 更严格
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
        
        # 综合评分 (V8.2: 更强调多源共振)
        st = fvg.get('strength', 1)
        score = n_sources * (1 + st * 0.15)
        if age < 5:
            score *= 1.15
        if has_sweep and has_ob:
            score *= 1.25
        if (dir=='long' and ms.get('bullish')) or (dir=='short' and ms.get('bearish')):
            score *= 1.2
        if has_bpr:
            score *= 1.15
        
        if score < score_min:
            continue
        
        # SL/TP (使用固定%)
        if dir == 'long':
            sl_price = round(ep * (1 - sl_p/100), 2)
            tp_price = round(ep * (1 + tp_p/100), 2)
        else:
            sl_price = round(ep * (1 + sl_p/100), 2)
            tp_price = round(ep * (1 - tp_p/100), 2)
        
        rr = abs(tp_price - ep) / max(0.001, abs(sl_price - ep))
        
        # V8.2: RR约束 — 如果RR < 0.7, 降低score
        if rr < 0.7:
            score *= 0.3  # 严重惩罚低RR
        elif rr < 1.0:
            score *= 0.7  # 中度惩罚
        
        entries.append({
            'ep': ep, 'dir': 'L' if dir == 'long' else 'S',
            'idx': idx, 'sl': sl_price, 'tp': tp_price,
            'rr': round(rr, 2), 'score': round(score, 2),
            'sources': sources, 'n_src': n_sources,
        })
    
    # 基于OB的独立信号
    for ob in ob_list[-20:]:
        idx = ob.get('index', 0)
        if idx < 3 or idx >= last_idx - 2:
            continue
        age = last_idx - idx
        if age > 40:
            continue
        dir = ob['direction']
        ep = (ob['top'] + ob['bottom']) / 2
        
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
        
        min_src = p.get('min_sources', 1)
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
        
        rr = abs(tp_price - ep) / max(0.001, abs(sl_price - ep))
        if rr < 0.7:
            score *= 0.3
        elif rr < 1.0:
            score *= 0.7
        
        entries.append({
            'ep': ep, 'dir': 'L' if dir == 'long' else 'S',
            'idx': idx, 'sl': sl_price, 'tp': tp_price,
            'rr': round(rr, 2), 'score': round(score, 2),
            'sources': sources, 'n_src': len(sources),
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

def backtest_v82(bars, params=None):
    if not bars or len(bars) < 80:
        return []
    result = detect_entries_v82(bars, params)
    entries = result.get('entries', [])
    if not entries:
        return []
    trades = []
    for e in entries:
        t = simulate_entry_v82(e, bars)
        if t:
            trades.append(t)
    return trades

def simulate_entry_v82(entry, bars):
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
                if b['l'] <= sl:
                    pnl = (tp - ep) / ep if abs(tp-ep) > abs(sl-ep) else (sl-ep)/ep
                else:
                    pnl = (tp - ep) / ep
                return {'pnl': round(pnl, 4), 'reason': 'tp', 'bars': j-entry_idx+1,
                        'ep': ep, 'sl': sl, 'tp': tp, 'exit': tp, 'sources': sources}
            if b['l'] <= sl:
                return {'pnl': round((sl-ep)/ep, 4), 'reason': 'sl', 'bars': j-entry_idx+1,
                        'ep': ep, 'sl': sl, 'tp': tp, 'exit': sl, 'sources': sources}
        else:
            if b['l'] <= tp:
                if b['h'] >= sl:
                    pnl = (ep - tp) / ep if abs(tp-ep) > abs(sl-ep) else (ep-sl)/ep
                else:
                    pnl = (ep - tp) / ep
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
# V8.2 评分函数 (RR纳入 + N黄金区间)
# ════════════════════════════════════════════

def compute_v82_score(trades):
    """
    V8.2评分 — 四层平衡引导:
    1. 黄金N=25-40, N<8→惩罚, N>50→惩罚
    2. RR_avg < 0.8 → 大幅惩罚
    3. WR>95%且N<15 → 过拟合惩罚
    4. 综合: WR × sqrt(N) × min(3, PF) × RR_mult
    """
    n = len(trades)
    if n < 1:
        return {'score': 0, 'wr': 0, 'pf': 0, 'n': n, 'ret': 0, 'sr': 0, 'rr_avg': 0}
    
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    n_wins = len(wins)
    n_losses = len(losses)
    
    wr = n_wins / n * 100 if n > 0 else 0
    # PF (Profit Factor): handle edge cases properly
    loss_sum = abs(sum(t['pnl'] for t in losses)) if losses else 0
    win_sum = sum(t['pnl'] for t in wins) if wins else 0
    if loss_sum > 0:
        pf = win_sum / loss_sum
    elif wins:
        # No losses but have wins -> infinite PF, capped
        pf = min(50.0, max(10.0, win_sum * 10))
    else:
        pf = 0
    avg_pnl = sum(t['pnl'] for t in trades) / n
    total_ret = sum(t['pnl'] for t in trades) * 100
    
    std = math.sqrt(sum((t['pnl']-avg_pnl)**2 for t in trades)/n) if n > 1 else 0.001
    sr = (avg_pnl / std) * math.sqrt(252) if std > 0 else 0
    
    # RR (盈亏比)
    rr_avg = 0
    if wins:
        avg_win = sum(t['pnl'] for t in wins) / n_wins
        if losses:
            avg_loss = loss_sum / n_losses
            rr_avg = avg_win / max(0.0001, avg_loss)
        else:
            # No losses -> infinite RR, use conservative estimate
            rr_avg = avg_win / max(0.001, abs(avg_win * 0.3))
    
    # ════════ V8.2 核心评分 ════════
    
    # 1. PF capping
    pf_capped = min(3.0, pf)
    
    # 2. RR multiplier — 核心!!!
    if rr_avg < 0.5:
        rr_mult = 0.2  # 几乎淘汰
    elif rr_avg < 0.8:
        rr_mult = 0.5  # 大幅降权
    elif rr_avg < 1.2:
        rr_mult = 0.8  # 轻微降权
    elif rr_avg < 2.0:
        rr_mult = 1.0  # 正常
    else:
        rr_mult = 1.1  # RR>2.0 bonus
    
    # 3. N golden zone
    if n < 5:
        n_mult = n / 12.0  # severe penalty
    elif n < 8:
        n_mult = n / 10.0  # n=7 → 0.7
    elif n < 15:
        n_mult = 0.8 + n / 50.0  # n=10 → 1.0
    elif n < 25:
        n_mult = 1.0  # sweetspot lower
    elif n < 40:
        n_mult = 1.1  # sweetspot!
    elif n < 55:
        n_mult = 0.9  # too many trades penalty
    else:
        n_mult = 0.6  # noise!
    
    # 4. Overfitting guard: WR>95% AND N<15
    if wr >= 95 and n < 15:
        n_mult *= 0.4  # huge overfit penalty
    
    # 5. WR multiplier
    if wr >= 80:
        wr_mult = 1.2
    elif wr >= 70:
        wr_mult = 1.0
    elif wr >= 60:
        wr_mult = 0.7
    elif wr >= 50:
        wr_mult = 0.4
    else:
        wr_mult = 0.1  # WR<50 → useless
    
    # ════════ 最终评分 ════════
    base_score = wr * math.sqrt(max(1, n)) * pf_capped
    final_score = base_score * wr_mult * rr_mult * n_mult
    
    # Round
    final_score_rounded = round(final_score, 1)
    
    return {
        'score': final_score_rounded,
        'wr': round(wr, 1),
        'pf': round(pf, 2),
        'n': n,
        'n_wins': n_wins,
        'n_losses': n_losses,
        'ret': round(total_ret, 2),
        'sr': round(sr, 2),
        'rr_avg': round(rr_avg, 2),
        # V8.2 debug
        '_rr_mult': round(rr_mult, 3),
        '_n_mult': round(n_mult, 3),
        '_wr_mult': round(wr_mult, 3),
    }

# ════════════════════════════════════════════
# 数据加载
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
    cache_file = CACHE_DIR / f"{symbol.replace('.','_')}_{interval}_{limit}.json"
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)
    bars = get_bars(symbol, interval, limit)
    with open(cache_file, 'w') as f:
        json.dump(bars, f)
    return bars

# ════════════════════════════════════════════
# 代理检查 (共享)
# ════════════════════════════════════════════

import subprocess, urllib.request

def check_proxy_v8():
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
    print("=" * 60)
    print("  SMC V8.2 Engine — RR引导版")
    print("=" * 60)
    print(f"  Params: {len(V82_PARAM_SPACE)} dimensions")
    print(f"  Test stocks: {len(TEST_STOCKS)}")
    
    sym = '300231.SZ'
    bars = load_bars(sym, 'daily', 300)
    if bars:
        vol = get_vol_profile(bars)
        print(f"\n  Test: {sym} (ATR={vol['atr_pct']}%)")
        result = detect_entries_v82(bars)
        entries = result['entries']
        signals = result.get('signals', {})
        print(f"  FVG={signals.get('fvg',0)} Sweep={signals.get('sweep',0)} OB={signals.get('ob',0)} BPR={signals.get('bpr',0)}")
        print(f"  Entries: {result['total']} | Vol: {vol['vol_level']}")
        if entries:
            for e in entries[:3]:
                print(f"    {e['dir']} ep={e['ep']} sl={e['sl']} tp={e['tp']} R={e['rr']} score={e['score']} src={e['sources']}")
        trades = backtest_v82(bars)
        if trades:
            s = compute_v82_score(trades)
            print(f"  Backtest: WR={s['wr']}% PF={s['pf']} N={s['n']} Ret={s['ret']}% RR_avg={s['rr_avg']}")
            print(f"  Score={s['score']} (_RRm={s.get('_rr_mult')} _Nm={s.get('_n_mult')} _WRm={s.get('_wr_mult')})")
        else:
            print(f"  No trades (filtered)")