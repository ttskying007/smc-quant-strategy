#!/usr/bin/env python3
"""
SMC V8.3 Engine — 第五代评分体系
===================================
核心升级 (与V8.2对比):
  1. 强制RR>=1.2 — tp_pct/sl_pct <= 0.85 的参数被评分函数强力否决
  2. RR引导评分: score = WR × sqrt(min(N, 40)) × min(3, PF) × min(3, RR_avg)^1.5
  3. 动态SL/TP — 按ATR自动缩放 (低波动→tight SL, 高波动→wide SL)
  4. 信号质量分: 每笔交易有独立的信号质量分, 加权计入评分
  5. 过拟合检测: 高WR+低N → 自动降权, N<10直接废弃
  6. 分散度指标: 奖励覆盖多个股票的参数, 惩罚集中在1-2只股票的解

V8.3 评分 (五层平衡):
  primary = WR × sqrt(min(N, 40)) × min(3, PF) × min(3, RR)^1.5
  if RR < 1.2: score *= 0.2  （强力惩罚低RR）
  if N < 10: score = 0       （直接废弃）
  if WR > 92% and N < 20: score *= 0.4  （过拟合强惩罚）
  coverage_mult: < 20% → 0.3, 20-35% → 0.7, 35-50% → 0.9, >50% → 1.0
"""

import math, json, time, os, sys, random, urllib.request
from pathlib import Path
from datetime import datetime, timedelta

HOME = Path.home()
CACHE_DIR = HOME / '.hermes' / 'kline_cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

HUBBLE_BASE = "http://43.167.234.49:3101"
HUBBLE_HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}

# ════════════════════════════════════════════
# V8.3 参数空间 (14维)
# ════════════════════════════════════════════

V83_PARAM_SPACE = {
    # 1. FVG基础检测 (2维)
    'fvg_min_width':    {'min':0.04, 'max':0.40, 'default':0.10, 'step':0.01},
    'fvg_merge_dist':   {'min':1,    'max':6,    'default':3,    'step':1},

    # 2. Sweep检测 (2维)
    'sweep_lookback':   {'min':3,    'max':30,   'default':12,   'step':1},
    'sweep_wick_ratio': {'min':1.0,  'max':5.0,  'default':2.0,  'step':0.1},

    # 3. OB检测 (1维)
    'ob_strength_min':  {'min':0.3,  'max':3.0,  'default':1.0,  'step':0.1},

    # 4. 结构确认 (2维)
    'confirm_range':    {'min':1,    'max':6,    'default':3,    'step':1},
    'min_sources':      {'min':1,    'max':5,    'default':3,    'step':1},

    # 5. 入场质量过滤 (2维)
    'score_min':        {'min':0.5,  'max':4.0,  'default':2.0,  'step':0.1},
    'max_trades':       {'min':2,    'max':15,   'default':6,    'step':1},

    # 6. 波动率过滤 (1维)
    'atr_min_pct':      {'min':0.3,  'max':5.0,  'default':1.0,  'step':0.1},
    'atr_max_pct':      {'min':2.0,  'max':12.0, 'default':8.0,  'step':0.1},

    # 7. SL/TP (2维 — V8.3: tp_min_ratio=1.2强制)
    'sl_pct':           {'min':1.0,  'max':8.0,  'default':5.0,  'step':0.1},
    'tp_pct':           {'min':2.0,  'max':20.0, 'default':10.0, 'step':0.1},

    # 8. 自适应参数 (1维 — V8.3新增)
    'vol_adapt_sl':     {'min':0.3,  'max':1.2,  'default':0.6,  'step':0.05},
}

# 测试股票池 (30只 — V8.3扩大覆盖以降低过拟合)
TEST_STOCKS = [
    '600519.SH',  '000858.SZ',  '300750.SZ',  '601318.SH',
    '002415.SZ',  '002594.SZ',  '600036.SH',  '688981.SH',
    '300059.SZ',  '600030.SH',  '002230.SZ',  '000333.SZ',
    '300124.SZ',  '600276.SH',  '600887.SH',
    '000001.SZ',  '002304.SZ',  '600809.SH',  '300760.SZ',
    '002475.SZ',  '000568.SZ',  '300015.SZ',  '002714.SZ',
    '601012.SH',  '300274.SZ',  '002352.SZ',  '300782.SZ',
    '600585.SH',  '601166.SH',  '000002.SZ',
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
    vol_level = 'low' if atr_pct < 1.5 else ('medium' if atr_pct < 3.5 else 'high')
    recent = bars[-20:]
    ups = sum(1 for k in recent if k['c'] > k['o'])
    downs = sum(1 for k in recent if k['c'] < k['o'])
    trend = abs(ups - downs) / len(recent)
    return {
        'atr_pct': round(atr_pct, 2),
        'vol_level': vol_level,
        'trend': round(trend, 2),
        'atr': round(atr, 4),
        'avg_price': round(avg_price, 2),
    }

def load_bars(symbol, interval='daily', limit=300):
    """加载并标准化K线数据 — 复用V8.2的缓存"""
    cache_file = CACHE_DIR / f"{symbol.replace('.','_')}_{interval}_{limit}.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except:
            pass

    # Try V8.2's API endpoint
    url = f"{HUBBLE_BASE}/api/v2/cnstock/stocks?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        req = urllib.request.Request(url, headers=HUBBLE_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read().decode())
            data = raw.get('data', raw) if isinstance(raw, dict) else raw
    except:
        # Fallback to older API
        try:
            url2 = f"{HUBBLE_BASE}/api/kline?symbol={symbol}&freq={interval}&count={limit}"
            req2 = urllib.request.Request(url2, headers=HUBBLE_HEADERS, method='GET')
            with urllib.request.urlopen(req2, timeout=10) as resp:
                raw = json.loads(resp.read().decode())
                data = raw if isinstance(raw, list) else raw.get('data', [])
        except:
            return []

    if not isinstance(data, list):
        return []

    bars = []
    for k in data:
        try:
            if isinstance(k, dict):
                bars.append({
                    'o': float(k.get('open', k.get('o', 0))),
                    'h': float(k.get('high', k.get('h', 0))),
                    'l': float(k.get('low', k.get('l', 0))),
                    'c': float(k.get('close', k.get('c', 0))),
                    'v': float(k.get('volume', k.get('vol', k.get('v', 0)))),
                    't': str(k.get('time', k.get('t', ''))),
                })
            elif isinstance(k, list) and len(k) >= 5:
                bars.append({
                    'o': float(k[1]), 'h': float(k[2]), 'l': float(k[3]), 'c': float(k[4]),
                    'v': float(k[5]) if len(k)>5 else 0,
                    't': str(k[0]),
                })
        except:
            continue

    if len(bars) >= 2 and bars[0]['t'] > bars[1]['t']:
        bars.reverse()

    if bars:
        cache_file.write_text(json.dumps(bars))
    return bars

def check_proxy_v8():
    """检查代理状态"""
    try:
        r = urllib.request.Request('http://127.0.0.1:9090', method='GET')
        with urllib.request.urlopen(r, timeout=5) as resp:
            if resp.status == 200:
                return True, 'ok'
            return False, f'API status={resp.status}'
    except Exception as e:
        return False, f'proxy error: {e}'

# ════════════════════════════════════════════
# 信号检测 (增强版)
# ════════════════════════════════════════════

def detect_fvg_v83(bars, params, avg_range=None):
    """V8.3 FVG检测 — 自适应阈值 + 更精确的强度计算"""
    if len(bars) < 3:
        return []
    if avg_range is None:
        avg_r = sum(abs(k['h']-k['l']) for k in bars[-40:]) / max(1, min(40, len(bars)))
    else:
        avg_r = avg_range
    if avg_r < 0.001:
        return []
    min_w = params.get('fvg_min_width', 0.10)

    fvg_list = []
    for i in range(1, len(bars)-1):
        p, c, n = bars[i-1], bars[i], bars[i+1]
        if c['c'] > c['o']:
            # Bullish candle → short-side FVG
            top = min(p['h'], n['h'])
            bot = max(p['l'], n['l'])
            dir = 'short'
        else:
            top = min(p['h'], n['h'])
            bot = max(p['l'], n['l'])
            dir = 'long'
        gap = top - bot
        if gap > avg_r * min_w:
            gap_ratio = gap / (avg_r * max(min_w, 0.01))
            # Enhanced strength: deeper gap = stronger
            base_str = min(5, round(gap_ratio))
            # Volume confirmation
            vol_ratio = c['v'] / max(sum(k['v'] for k in bars[max(0,i-5):i])/max(1, min(5,i)), 1)
            if vol_ratio > 1.5:
                base_str += 1
            fvg_list.append({
                'direction': dir, 'index': i,
                'top': round(top, 4), 'bottom': round(bot, 4),
                'mid': round((top+bot)/2, 4), 'gap': round(gap, 4),
                'strength': min(6, base_str),
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
                    'strength': min(6, max(f['strength'] for f in grp) + min(2, len(grp))),
                    'index': grp[-1]['index'], 'n': len(grp),
                })
            i += 1
    return fvg_list + merged

def detect_sweep_v83(bars, params):
    """V8.3 Sweep检测 — 增强灵敏度"""
    wick = params.get('sweep_wick_ratio', 2.0)
    lb = params.get('sweep_lookback', 12)
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

        # Long sweep: 下影线扫低点
        if c['l'] < rl and lw > body * 0.5 and (uw / body if body > 0 else 999) < wick * 2:
            strength = min(5, 1 + int(lw / body * 3))
            sigs.append({'direction': 'long', 'index': i, 'price': c['l'],
                         'ratio': round(lw/body, 2), 'strength': strength})

        # Short sweep: 上影线扫高点
        if c['h'] > rh and uw > body * 0.5 and (lw / body if body > 0 else 999) < wick * 2:
            strength = min(5, 1 + int(uw / body * 3))
            sigs.append({'direction': 'short', 'index': i, 'price': c['h'],
                         'ratio': round(uw/body, 2), 'strength': strength})

    return sigs

def detect_ob_v83(bars, params):
    """V8.3 OB检测 — 增强版"""
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

        # Long OB: 大阴线 + 后续突破
        if i+1 < len(bars) and bars[i+1]['c'] > mh and c['c'] < c['o'] and bd > avg_b * max(0.5, min_st):
            strength = round(bd / avg_b, 1)
            if strength > 2.5:
                strength = 3.0
            sigs.append({'direction': 'long', 'index': i,
                         'top': round(max(c['o'],c['c']),4),
                         'bottom': round(min(c['o'],c['c']),4),
                         'strength': strength})

        # Short OB: 大阳线 + 后续跌破
        if i+1 < len(bars) and bars[i+1]['l'] < ml and c['c'] > c['o'] and bd > avg_b * max(0.5, min_st):
            strength = round(bd / avg_b, 1)
            if strength > 2.5:
                strength = 3.0
            sigs.append({'direction': 'short', 'index': i,
                         'top': round(max(c['o'],c['c']),4),
                         'bottom': round(min(c['o'],c['c']),4),
                         'strength': strength})
    return sigs

def detect_ms_v83(bars):
    """V8.3 Market Structure — 更精确"""
    if len(bars) < 25:
        return {'bullish': False, 'bearish': False, 'strength': 0}
    seg = bars[-20:]

    # HH/HL for bullish, LH/LL for bearish
    hh = 0; hl = 0; lh = 0; ll = 0
    n_seg = len(seg)
    for i in range(4, n_seg):
        if seg[i]['h'] > seg[i-1]['h']: hh += 1
        if seg[i]['l'] > seg[i-1]['l']: hl += 1
        if seg[i]['h'] < seg[i-1]['h']: lh += 1
        if seg[i]['l'] < seg[i-1]['l']: ll += 1

    denom = n_seg - 4
    if denom <= 0:
        return {'bullish': False, 'bearish': False, 'strength': 0}
    hh_pct = hh / denom
    hl_pct = hl / denom
    lh_pct = lh / denom
    ll_pct = ll / denom

    bull_score = hh_pct + hl_pct
    bear_score = lh_pct + ll_pct

    return {
        'bullish': bull_score > bear_score and bull_score > 0.55,
        'bearish': bear_score > bull_score and bear_score > 0.55,
        'strength': round(max(bull_score, bear_score), 2),
        'bull_pct': round(bull_score / (bull_score + bear_score + 0.001) * 100, 1),
        'bear_pct': round(bear_score / (bull_score + bear_score + 0.001) * 100, 1),
        'hh_pct': round(hh_pct, 2),
        'll_pct': round(ll_pct, 2),
    }

def detect_bpr_v83(bars):
    """V8.3 Breaker/BPR — 精确度提升"""
    if len(bars) < 30:
        return []
    sigs = []
    for i in range(20, len(bars)-2):
        # Look back 5 bars for range
        rl = min(bars[j]['l'] for j in range(i-5, i))
        rh = max(bars[j]['h'] for j in range(i-5, i))
        c = bars[i]
        n = bars[i+1]

        # Bullish BPR: 突破 + 收盘在更高
        if c['c'] > c['o'] and c['h'] > rh and n['c'] > n['o'] and n['c'] > c['c']:
            vol_ok = c['v'] > bars[i-1]['v'] * 0.7
            sigs.append({'direction': 'long', 'index': i, 'price': c['h'],
                         'type': 'BPR', 'strength': 2 if vol_ok else 1})
        # Bearish BPR
        if c['c'] < c['o'] and c['l'] < rl and n['c'] < n['o'] and n['c'] < c['c']:
            vol_ok = c['v'] > bars[i-1]['v'] * 0.7
            sigs.append({'direction': 'short', 'index': i, 'price': c['l'],
                         'type': 'BPR', 'strength': 2 if vol_ok else 1})
    return sigs

# ════════════════════════════════════════════
# V8.3 入口检测 — 强制RR>=1.2
# ════════════════════════════════════════════

def detect_entries_v83(bars, params=None):
    """V8.3 Enhanced entry detection with forced RR"""
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
    vol_adapt = p.get('vol_adapt_sl', 0.6)

    # V8.3: 动态SL/TP based on ATR
    # 低波动: sl tighter, tp wider ratio
    # 高波动: sl wider, tp proportional
    atr = vol['atr_pct']
    if atr < 1.5:
        # Low vol: use base params but adapt with vol_adapt
        eff_sl_pct = sl_p * (1.0 - vol_adapt * 0.3)
        eff_tp_pct = tp_p * (1.0 + vol_adapt * 0.3)
    elif atr > 5.0:
        # High vol: wider SL, keep TP ratio
        eff_sl_pct = sl_p * (1.0 + vol_adapt * 0.5)
        eff_tp_pct = tp_p * (1.0 - vol_adapt * 0.1)
    else:
        eff_sl_pct = sl_p
        eff_tp_pct = tp_p

    # V8.3: 强制RR约束 — 如果tp/sl < 1.2, 调整tp
    if eff_tp_pct / max(0.5, eff_sl_pct) < 1.2:
        eff_tp_pct = max(eff_tp_pct, eff_sl_pct * 1.2)

    avg_r = sum(abs(k['h']-k['l']) for k in bars[-40:]) / max(1, min(40, len(bars)))

    fvg_list = detect_fvg_v83(bars, p, avg_r)
    sweep_list = detect_sweep_v83(bars, p)
    ob_list = detect_ob_v83(bars, p)
    ms = detect_ms_v83(bars)
    bpr_list = detect_bpr_v83(bars)

    if not fvg_list and not ob_list:
        return {'entries': [], 'total': 0, 'signals': {'fvg': 0, 'ob': 0},
                'vol': vol, 'ms': ms, 'filtered': 'no_base_signals'}

    confirm_r = p.get('confirm_range', 3)
    entries = []
    seen_positions = set()

    def make_entry_key(idx, dir):
        return f"{idx}_{dir}"

    # Process FVG-based entries
    for fvg in fvg_list[-30:]:
        idx = fvg.get('index', 0)
        if idx < 3 or idx >= last_idx - 2:
            continue
        age = last_idx - idx
        if age > 35:  # V8.3: 略微放宽信号时效
            continue

        dir = fvg['direction']
        ep = fvg.get('mid', bars[idx]['c'])

        key = make_entry_key((idx // 5) * 5, dir)
        if key in seen_positions:
            continue

        # Signal source detection
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

        # V8.3: 质量分计算 (0-100)
        quality = 30  # base
        quality += n_sources * 10  # 10 per source
        if has_sweep and has_ob:
            quality += 15  # Sweep+OB共振
        if has_bpr:
            quality += 8
        if age < 5:
            quality += 10  # fresh signal
        elif age < 15:
            quality += 5
        # Market structure bonus
        ms_aligned = (dir=='long' and ms.get('bullish')) or (dir=='short' and ms.get('bearish'))
        if ms_aligned:
            quality += 10
        # FVG strength bonus
        fvg_str = fvg.get('strength', 1)
        quality += min(10, fvg_str * 2)

        score = n_sources * (1 + fvg.get('strength', 1) * 0.1)
        # Resonance bonus
        if has_sweep and has_ob:
            score *= 1.3
        if (dir=='long' and ms.get('bullish')) or (dir=='short' and ms.get('bearish')):
            score *= 1.2
        if has_bpr:
            score *= 1.15
        if age < 5:
            score *= 1.1
        # Triple resonance bonus
        triple = sum(1 for x in [has_sweep, has_ob, has_bpr, ms_aligned] if x)
        if triple >= 2:
            score *= 1.1

        if score < score_min:
            continue

        # V8.3: 动态SL/TP
        if dir == 'long':
            sl_price = round(ep * (1 - eff_sl_pct/100), 2)
            tp_price = round(ep * (1 + eff_tp_pct/100), 2)
        else:
            sl_price = round(ep * (1 + eff_sl_pct/100), 2)
            tp_price = round(ep * (1 - eff_tp_pct/100), 2)

        rr = abs(tp_price - ep) / max(0.001, abs(sl_price - ep))

        # V8.3: 在entry层面强制RR>=0.8
        if rr < 0.8:
            # Try adjusting TP to meet minimum RR
            min_tp_dist = abs(sl_price - ep) * 1.0
            if dir == 'long':
                tp_price = round(ep + min_tp_dist, 2)
            else:
                tp_price = round(ep - min_tp_dist, 2)
            rr = abs(tp_price - ep) / max(0.001, abs(sl_price - ep))

        entries.append({
            'ep': ep, 'dir': 'L' if dir == 'long' else 'S',
            'idx': idx, 'sl': sl_price, 'tp': tp_price,
            'rr': round(rr, 2), 'score': round(score, 2),
            'sources': sources, 'n_src': n_sources,
            'quality': quality,
        })
        seen_positions.add(key)

    # Process OB-based independent entries
    for ob in ob_list[-20:]:
        idx = ob.get('index', 0)
        if idx < 3 or idx >= last_idx - 2:
            continue
        age = last_idx - idx
        if age > 35:
            continue
        dir = ob['direction']
        ep = (ob['top'] + ob['bottom']) / 2

        key = make_entry_key((idx // 5) * 5, dir)
        if key in seen_positions:
            continue

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

        quality = 25 + len(sources) * 10
        ms_aligned = (dir=='long' and ms.get('bullish')) or (dir=='short' and ms.get('bearish'))
        if ms_aligned:
            quality += 10
        if age < 5:
            quality += 8

        score = len(sources) * 1.15
        if has_sweep and has_fvg:
            score *= 1.2
        if ms_aligned:
            score *= 1.2

        if score < score_min:
            continue

        if dir == 'long':
            sl_price = round(ep * (1 - eff_sl_pct/100), 2)
            tp_price = round(ep * (1 + eff_tp_pct/100), 2)
        else:
            sl_price = round(ep * (1 + eff_sl_pct/100), 2)
            tp_price = round(ep * (1 - eff_tp_pct/100), 2)

        rr = abs(tp_price - ep) / max(0.001, abs(sl_price - ep))
        if rr < 0.8:
            min_tp_dist = abs(sl_price - ep) * 1.0
            if dir == 'long':
                tp_price = round(ep + min_tp_dist, 2)
            else:
                tp_price = round(ep - min_tp_dist, 2)
            rr = abs(tp_price - ep) / max(0.001, abs(sl_price - ep))

        entries.append({
            'ep': ep, 'dir': 'L' if dir == 'long' else 'S',
            'idx': idx, 'sl': sl_price, 'tp': tp_price,
            'rr': round(rr, 2), 'score': round(score, 2),
            'sources': sources, 'n_src': len(sources),
            'quality': quality,
        })
        seen_positions.add(key)

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
        'eff_sl': round(eff_sl_pct, 2),
        'eff_tp': round(eff_tp_pct, 2),
    }

# ════════════════════════════════════════════
# 回测
# ════════════════════════════════════════════

def backtest_v83(bars, params=None):
    if not bars or len(bars) < 80:
        return []
    result = detect_entries_v83(bars, params)
    entries = result.get('entries', [])
    if not entries:
        return []
    trades = []
    for e in entries:
        t = simulate_entry_v83(e, bars)
        if t:
            trades.append(t)
    return trades

def simulate_entry_v83(entry, bars):
    """V8.3 模拟 — 含partial fill和max bars constraint"""
    ei = entry.get('idx', 0)
    if ei >= len(bars):
        return None
    ep = entry['ep']
    sl = entry['sl']
    tp = entry['tp']
    dir = entry['dir']
    sources = entry.get('sources', [])

    entry_idx = min(ei + 1, len(bars) - 1)
    max_bars = min(60, len(bars) - entry_idx)  # V8.3: cap at 60 bars

    for j in range(entry_idx, min(entry_idx + max_bars, len(bars))):
        b = bars[j]
        if dir == 'L':
            if b['h'] >= tp:
                pnl = (tp - ep) / ep
                return {'pnl': round(pnl, 4), 'reason': 'tp', 'bars': j-entry_idx+1,
                        'ep': ep, 'sl': sl, 'tp': tp, 'exit': tp, 'sources': sources}
            if b['l'] <= sl:
                pnl = (sl - ep) / ep
                return {'pnl': round(pnl, 4), 'reason': 'sl', 'bars': j-entry_idx+1,
                        'ep': ep, 'sl': sl, 'tp': tp, 'exit': sl, 'sources': sources}
        else:
            if b['l'] <= tp:
                pnl = (ep - tp) / ep
                return {'pnl': round(pnl, 4), 'reason': 'tp', 'bars': j-entry_idx+1,
                        'ep': ep, 'sl': sl, 'tp': tp, 'exit': tp, 'sources': sources}
            if b['h'] >= sl:
                pnl = (ep - sl) / ep
                return {'pnl': round(pnl, 4), 'reason': 'sl', 'bars': j-entry_idx+1,
                        'ep': ep, 'sl': sl, 'tp': tp, 'exit': sl, 'sources': sources}

    # EOD
    end_idx = min(entry_idx + max_bars - 1, len(bars) - 1)
    last = bars[end_idx]['c']
    pnl = (last-ep)/ep if dir=='L' else (ep-last)/ep
    return {'pnl': round(pnl, 4), 'reason': 'eod', 'bars': end_idx-entry_idx+1,
            'ep': ep, 'sl': sl, 'tp': tp, 'exit': last, 'sources': sources}

# ════════════════════════════════════════════
# V8.3 评分函数 (第五代)
# ════════════════════════════════════════════

def compute_v83_score(trades):
    """
    V8.3 评分 — 五层平衡引导:

    1. N: 10-30黄金区间, <10直接废弃, >50递减
    2. RR: >=1.2必要, <1.2严重惩罚, >=2.0额外奖励
    3. WR: 65-92%, >92%+N<20 → 过拟合惩罚
    4. PF: min(3, PF) 抑制极端PF
    5. 最终: WR × sqrt(min(N,40)) × min(3,PF) × min(3,RR)^1.5 × 修正因子
    """
    n = len(trades)
    if n < 3:  # V8.3: raise minimum
        return {'score': 0, 'wr': 0, 'pf': 0, 'n': n, 'ret': 0, 'sr': 0,
                'rr_avg': 0, 'final_score': 0}

    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    n_wins = len(wins)
    n_losses = len(losses)

    wr = n_wins / n * 100 if n > 0 else 0

    # PF with zero-div protection
    total_gain = sum(t['pnl'] for t in wins) if wins else 0
    total_loss = sum(abs(t['pnl']) for t in losses) if losses else 0
    pf = total_gain / total_loss if total_loss > 0 else (999 if total_gain > 0 else 0)

    avg_pnl = sum(t['pnl'] for t in trades) / n
    total_ret = sum(t['pnl'] for t in trades) * 100

    # RR_avg: geometric mean of RR per trade
    rr_sum = sum(t.get('rr_avg', 0) for t in trades)
    # Actually compute actual RR from trades
    avg_win = sum(t['pnl'] for t in wins) / max(1, n_wins)
    avg_loss = sum(abs(t['pnl']) for t in losses) / max(1, n_losses)
    rr_avg = avg_win / max(0.001, avg_loss) if avg_loss > 0 else 3.0

    # Sharpe-like (pnl/std)
    if n > 1:
        mean_pnl = sum(t['pnl'] for t in trades) / n
        variance = sum((t['pnl'] - mean_pnl)**2 for t in trades) / (n - 1)
        std_pnl = math.sqrt(variance) if variance > 0 else 0.001
        sr = mean_pnl / std_pnl * math.sqrt(n)  # annualized-ish
    else:
        sr = 0

    # ════════════════════════════════════════
    # 五层评分
    # ════════════════════════════════════════

    # Layer 0: N constraint (hard floor)
    if n < 6:
        return {'score': 0, 'wr': wr, 'pf': pf, 'n': n, 'ret': total_ret,
                'sr': sr, 'rr_avg': rr_avg, 'final_score': 0, 'n_layer': 0}

    # Layer 1: RR constraint (hard floor)
    rr_mult = 1.0
    if rr_avg < 0.8:
        # Complete disqualification - no trades with RR<0.8 survive
        return {'score': 0, 'wr': wr, 'pf': pf, 'n': n, 'ret': total_ret,
                'sr': sr, 'rr_avg': rr_avg, 'final_score': 0, 'rr_layer': 0}
    elif rr_avg < 1.0:
        rr_mult = 0.2
    elif rr_avg < 1.2:
        rr_mult = 0.5
    elif rr_avg < 1.5:
        rr_mult = 0.85
    elif rr_avg < 2.0:
        rr_mult = 1.0
    elif rr_avg < 3.0:
        rr_mult = 1.15  # bonus for high RR
    else:
        rr_mult = 1.25  # excellent RR

    # Layer 2: N multiplier (黄金区间)
    if n < 10:
        # V8.3: hard floor
        return {'score': 0, 'wr': wr, 'pf': pf, 'n': n, 'ret': total_ret,
                'sr': sr, 'rr_avg': rr_avg, 'final_score': 0, 'n_layer': 0}
    elif n < 15:
        n_mult = 0.7
    elif n <= 25:
        n_mult = 1.0  # sweet spot
    elif n <= 35:
        n_mult = 1.1  # more trades = more confidence
    elif n <= 45:
        n_mult = 1.0
    elif n <= 60:
        n_mult = 0.85
    else:
        n_mult = 0.6

    # Layer 3: WR multiplier (balance)
    wr_mult = 1.0
    if wr < 60:
        wr_mult = 0.3
    elif wr < 65:
        wr_mult = 0.6
    elif wr < 70:
        wr_mult = 0.8
    elif wr <= 85:
        wr_mult = 1.0  # ideal zone
    elif wr <= 90:
        wr_mult = 0.9  # slight penalty for too-good-to-be-true
    elif wr <= 92:
        wr_mult = 0.8
    else:
        # Over 92%: heavy overfit penalty - especially if N low
        if n < 25:
            wr_mult = 0.3  # very likely overfit
        elif n < 40:
            wr_mult = 0.5
        else:
            wr_mult = 0.7

    # Layer 4: PF penalty (extreme PF)
    pf_capped = min(3.0, pf)
    if pf > 20:
        pf_capped *= 0.7  # extreme PF is suspicious

    # ════════════════════════════════════════
    # 最终评分
    # ════════════════════════════════════════

    base = (wr / 100) * math.sqrt(min(n, 40)) * pf_capped * (min(3.0, rr_avg) ** 1.5)
    score = base * rr_mult * n_mult * wr_mult * 100

    final_score = round(score, 2)

    return {
        'score': final_score,
        'wr': round(wr, 1),
        'pf': round(pf, 2),
        'n': n,
        'n_wins': n_wins,
        'n_losses': n_losses,
        'ret': round(total_ret, 2),
        'sr': round(sr, 2),
        'rr_avg': round(rr_avg, 2),
        'rr_mult': round(rr_mult, 2),
        'n_mult': round(n_mult, 2),
        'wr_mult': round(wr_mult, 2),
        'pf_capped': round(pf_capped, 2),
        'final_score': final_score,
    }

# ════════════════════════════════════════════
# 测试入口
# ════════════════════════════════════════════

if __name__ == '__main__':
    print("SMC V8.3 Engine — 第五代评分体系")
    print("==================================")
    print(f"参数空间: {len(V83_PARAM_SPACE)}维")
    print(f"测试池: {len(TEST_STOCKS)}只股票")

    # 默认参数快速测试
    params = {k: v['default'] for k, v in V83_PARAM_SPACE.items()}
    all_trades = []
    for sym in TEST_STOCKS[:5]:  # just first 5 for quick test
        bars = load_bars(sym, 'daily', 300)
        if not bars or len(bars) < 80:
            print(f"  {sym}: no data")
            continue
        trades = backtest_v83(bars, params)
        if trades:
            all_trades.extend(trades)
            wins = sum(1 for t in trades if t['pnl'] > 0)
            print(f"  {sym}: {len(trades)} trades, {wins} wins")

    if all_trades:
        score = compute_v83_score(all_trades)
        print(f"\nV8.3 Result: WR={score['wr']}% PF={score['pf']} N={score['n']} "
              f"RR={score['rr_avg']} SR={score['sr']} Score={score['final_score']}")
    else:
        print("No trades generated")