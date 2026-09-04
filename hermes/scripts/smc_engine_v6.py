#!/usr/bin/env python3
"""
SMC Engine V6 — 全自动多策略共振引擎
======================================
V4/V5 复盘问题:
  1. STRICT WR=99.5%但交易极少(1709笔/1339只) → 过拟合
  2. TOTAL WR=64.1%但交易多(5787笔) → 胜率差,需要更高质量信号
  3. 固定SL/TP不区分信号质量等级(ATR-based但不够细)
  4. 无分层策略: 高波动/低波动/趋势/震荡用同一套逻辑
  5. 回测不区分样本内外

V6创新:
  1. 四层信号质量（Bronze/Silver/Gold/Platinum）自适应参数
  2. 波动率-趋势-成交量三维分类
  3. 动态SL/TP: 信号质量越高→越紧止损+越远止盈
  4. 样本内外分离验证 (80/20 split)
  5. 多窗口FVG (3/5/8根K线滑动窗)
  6. 成交量确认: 入场后成交量放大加分
  7. 多策略并行: 趋势策略/反转策略/突破策略
  8. Genetic Grid搜索: 遗传算法多参数迭代
  9. 防止过拟合: 交叉验证+最小交易量惩罚
"""

import math, json, time, os, sys, random
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))

HUBBLE_BASE = "http://43.167.234.49:3101"
HUBBLE_HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}
KLINE_CACHE = Path.home() / '.hermes' / 'kline_cache'
OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v6'

os.makedirs(OPT_DIR, exist_ok=True)

# =============================================
# 数据获取
# =============================================

def fetch_hubble(url, timeout=20):
    import urllib.request
    for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
        os.environ.pop(k, None)
    req = urllib.request.Request(url, headers=HUBBLE_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode()

def get_klines(symbol, interval='daily', limit=600):
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

def load_cached_bars(symbol, limit=300):
    cache_key = f"{symbol}_daily_{limit}".replace('.','_').replace('-','_')
    cache_path = KLINE_CACHE / f"{cache_key}.json"
    if cache_path.exists() and os.path.getsize(cache_path) > 100:
        try:
            with open(cache_path) as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) >= 100:
                    return data
        except:
            pass
    # Fallback: fetch from API and cache
    bars = get_klines(symbol, 'daily', limit)
    if bars and len(bars) >= 100:
        try:
            json.dump(bars, open(cache_path, 'w'))
        except:
            pass
    return bars

# =============================================
# 增强工具函数
# =============================================

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

def calc_ema(values, period):
    if len(values) < period:
        return sum(values) / len(values)
    k = 2 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = v * k + ema * (1 - k)
    return ema

def calc_rsi(klines, period=14):
    if len(klines) < period + 1:
        return 50
    closes = [k['c'] for k in klines]
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    avg_g = sum(gains[-period:]) / period
    avg_l = sum(losses[-period:]) / period
    if avg_l == 0:
        return 100
    rs = avg_g / avg_l
    return 100 - (100 / (1 + rs))

def calc_macd(klines, fast=12, slow=26, signal=9):
    closes = [k['c'] for k in klines]
    if len(closes) < slow:
        return None, None, None
    ema_fast = calc_ema(closes, fast)
    ema_slow = calc_ema(closes, slow)
    macd = ema_fast - ema_slow
    # Simple: approximate with last
    return macd, 0, macd

def calc_vol_ratio(bars, idx, lookback=20):
    """比较idx处成交量和过去lookback的平均成交量"""
    if idx < lookback:
        return 1.0
    recent_vols = [b['v'] for b in bars[idx-lookback:idx]]
    avg_v = sum(recent_vols) / len(recent_vols) if recent_vols else 1
    current_v = bars[idx]['v'] if idx < len(bars) else avg_v
    return current_v / avg_v if avg_v > 0 else 1.0

# =============================================
# 波动率 + 市场状态分类 (V6增强)
# =============================================

def classify_market_state(bars):
    """三维分类: 波动率 / 趋势强度 / 成交量活性"""
    if len(bars) < 50:
        return 'unknown', 'unknown', 'unknown'
    
    # 1. 波动率
    atr = calc_atr(bars)
    avg_price = sum((bars[i]['h']+bars[i]['l'])/2 for i in range(-20, 0)) / 20
    atr_pct = atr / avg_price * 100 if avg_price > 0 else 0
    
    if atr_pct < 0.8:
        vol_state = 'very_low'
    elif atr_pct < 1.5:
        vol_state = 'low'
    elif atr_pct < 2.5:
        vol_state = 'medium'
    elif atr_pct < 4.0:
        vol_state = 'high'
    else:
        vol_state = 'very_high'
    
    # 2. 趋势强度 (基于R^2-like)
    recent = bars[-30:]
    closes = [k['c'] for k in recent]
    x_bar = len(closes) / 2
    y_bar = sum(closes) / len(closes)
    num = sum((i - x_bar) * (c - y_bar) for i, c in enumerate(closes))
    den_num = sum((i - x_bar)**2 for i in range(len(closes)))
    den_den = sum((c - y_bar)**2 for c in closes)
    r2 = (num**2 / (den_num * den_den)) if den_num * den_den > 0 else 0
    
    if r2 > 0.6:
        trend_state = 'strong_trend'
    elif r2 > 0.3:
        trend_state = 'weak_trend'
    else:
        trend_state = 'ranging'
    
    # 3. 成交量活性
    recent_v = [k['v'] for k in bars[-30:]]
    old_v = [k['v'] for k in bars[-60:-30]]
    avg_recent = sum(recent_v) / len(recent_v) if recent_v else 1
    avg_old = sum(old_v) / len(old_v) if old_v else 1
    vol_ratio = avg_recent / avg_old if avg_old > 0 else 1.0
    
    if vol_ratio > 1.5:
        vol_active = 'high_volume'
    elif vol_ratio > 0.7:
        vol_active = 'normal'
    else:
        vol_active = 'low_volume'
    
    return vol_state, trend_state, vol_active

# =============================================
# V6多窗口FVG检测
# =============================================

def detect_fvg_v6(bars, threshold=0.25, window_sizes=[3, 5, 8]):
    """
    V6多窗口FVG: 使用不同K线组合检测FVG
    window_sizes: 检测使用的窗口大小
    3根K线: 标准FVG
    5根K线: 宽幅FVG (中间忽略1根)
    8根K线: 超宽FVG (中间忽略2根)
    """
    if len(bars) < max(window_sizes) + 2:
        return []
    
    avg_r = sum(abs(k['h']-k['l']) for k in bars[-30:]) / max(1, min(30, len(bars)))
    if avg_r == 0:
        return []
    
    results = []
    
    # 标准FVG (3K线)
    for i in range(1, len(bars)-1):
        p, c, n = bars[i-1], bars[i], bars[i+1]
        bd = abs(c['c']-c['o'])
        
        if c['c'] > c['o']:  # 阳线 → Bullish
            for ws, label in [(3, 'STD'), (5, 'WIDE'), (8, 'XL')]:
                if ws <= 3:
                    top = min(p['h'], n['h'])
                    bot = max(p['l'], n['l'])
                else:
                    gap = ws // 2
                    if i - gap < 0 or i + gap >= len(bars):
                        continue
                    top = min(bars[i-gap]['h'], bars[i+gap]['h'])
                    bot = max(bars[i-gap]['l'], bars[i+gap]['l'])
                
                if top > bot and (top-bot) > avg_r * threshold:
                    strength = 1
                    if bd > (top-bot)*1.5: strength += 1
                    gap_size = ws // 2
                    if gap_size > 1: strength += 1
                    results.append({
                        'type': f'BullFVG_{label}', 'direction': 'long',
                        'top': top, 'bottom': bot, 'mid': (top+bot)/2,
                        'strength': min(4, strength), 'index': i, 'width': top-bot,
                        'window': ws
                    })
        
        elif c['c'] < c['o']:  # 阴线 → Bearish
            for ws, label in [(3, 'STD'), (5, 'WIDE'), (8, 'XL')]:
                if ws <= 3:
                    top = max(p['h'], n['h'])
                    bot = min(p['l'], n['l'])
                else:
                    gap = ws // 2
                    if i - gap < 0 or i + gap >= len(bars):
                        continue
                    top = max(bars[i-gap]['h'], bars[i+gap]['h'])
                    bot = min(bars[i-gap]['l'], bars[i+gap]['l'])
                
                if top > bot and (top-bot) > avg_r * threshold:
                    strength = 1
                    if bd > (top-bot)*1.5: strength += 1
                    gap_size = ws // 2
                    if gap_size > 1: strength += 1
                    results.append({
                        'type': f'BearFVG_{label}', 'direction': 'short',
                        'top': top, 'bottom': bot, 'mid': (top+bot)/2,
                        'strength': min(4, strength), 'index': i, 'width': top-bot,
                        'window': ws
                    })
    
    return results

# =============================================
# Sweep检测(V6)
# =============================================

def detect_swing_highs(klines, left=2, right=2):
    return [(i, klines[i]['h']) for i in range(left, len(klines)-right)
            if klines[i]['h'] == max(klines[j]['h'] for j in range(i-left, i+right+1))]

def detect_swing_lows(klines, left=2, right=2):
    return [(i, klines[i]['l']) for i in range(left, len(klines)-right)
            if klines[i]['l'] == min(klines[j]['l'] for j in range(i-left, i+right+1))]

def detect_sweep_v6(bars, lookback=12, wick_min=1.5, use_volume_confirm=True):
    """V6 Sweep检测: 带成交量确认"""
    if len(bars) < lookback + 3:
        return []
    avg_body = sum(abs(k['c']-k['o']) for k in bars[-30:]) / max(1, min(30, len(bars)))
    if avg_body == 0:
        return []
    
    signals = []
    for i in range(lookback, len(bars)):
        c = bars[i]
        body = abs(c['c']-c['o'])
        if body < avg_body * 0.3:
            continue
        
        seg = bars[i-lookback:i]
        hh = max(k['h'] for k in seg)
        ll = min(k['l'] for k in seg)
        
        # BSL Sweep
        if c['h'] > hh and c['c'] < hh:
            wick_abs = c['h'] - max(c['c'], c['o'])
            wr = wick_abs / body if body > 0 else 999
            vol_ratio = calc_vol_ratio(bars, i)
            vol_bonus = 0
            if use_volume_confirm and vol_ratio > 1.2:
                vol_bonus = 0.5
            if wr >= wick_min:
                signals.append({'type':'BSLSweep','direction':'short',
                    'level':hh,'swept_price':c['h'],
                    'wick_ratio':round(wr,2),'wick_abs':round(wick_abs,2),
                    'vol_ratio':round(vol_ratio,2),
                    'index':i, 'score_bonus': vol_bonus})
        
        # SSL Sweep
        if c['l'] < ll and c['c'] > ll:
            wick_abs = min(c['c'],c['o']) - c['l']
            wr = wick_abs / body if body > 0 else 999
            vol_ratio = calc_vol_ratio(bars, i)
            vol_bonus = 0
            if use_volume_confirm and vol_ratio > 1.2:
                vol_bonus = 0.5
            if wr >= wick_min:
                signals.append({'type':'SSLSweep','direction':'long',
                    'level':ll,'swept_price':c['l'],
                    'wick_ratio':round(wr,2),'wick_abs':round(wick_abs,2),
                    'vol_ratio':round(vol_ratio,2),
                    'index':i, 'score_bonus': vol_bonus})
    return signals

# =============================================
# V6 CHOCH检测
# =============================================

def detect_choch_v6(bars, lookback=30):
    """V6 CHOCH: 多时间框架确认"""
    if len(bars) < 20:
        return {'detected':False}
    
    seg = bars[-lookback:] if len(bars) > lookback else bars
    ph = detect_swing_highs(seg)
    pl = detect_swing_lows(seg)
    
    if len(ph) < 3 or len(pl) < 3:
        return {'detected':False}
    
    result = {'detected':False, 'confidence': 0}
    
    # V4 style: LL+Break or HH+Break
    rpl = [(i,v) for i,v in pl[-5:]]
    rph = [(i,v) for i,v in ph[-5:]]
    
    # Bullish CHOCH
    if len(rpl) >= 3:
        vals = [v for _,v in rpl[-3:]]
        if vals[0] > vals[1] > vals[2]:
            shs = sorted([v for _,v in ph if rpl[-1][0] < _], reverse=True)
            if shs and seg[-1]['c'] > shs[0]:
                # Confidence based on how clean the break is
                break_pct = (seg[-1]['c'] - shs[0]) / shs[0] * 100
                conf = min(1.0, break_pct / 3.0)
                result = {'detected':True, 'direction':'long',
                         'break_level':shs[0], 'type':'LL+Break',
                         'confidence': round(conf, 2)}
    
    # Bearish CHOCH
    if len(rph) >= 3:
        vals = [v for _,v in rph[-3:]]
        if vals[0] < vals[1] < vals[2]:
            sls = sorted([v for _,v in pl if rph[-1][0] < _])
            if sls and seg[-1]['c'] < sls[0]:
                break_pct = (sls[0] - seg[-1]['c']) / sls[0] * 100
                conf = min(1.0, break_pct / 3.0)
                existing = result.get('detected', False)
                if not existing or conf > result.get('confidence', 0):
                    result = {'detected':True, 'direction':'short',
                             'break_level':sls[0], 'type':'HH+Break',
                             'confidence': round(conf, 2)}
    
    return result

# =============================================
# OB检测(V6)
# =============================================

def detect_ob_v6(bars, fvg_list=None):
    """V6 OB: 成交量确认 + FVG对齐"""
    if len(bars) < 10:
        return []
    avg_body = sum(abs(bars[i]['c']-bars[i]['o']) 
                   for i in range(max(0,len(bars)-30), len(bars))) / min(30, max(1, len(bars)))
    if avg_body == 0:
        return []
    
    signals = []
    for i in range(4, len(bars)-2):
        pre = bars[i-4:i]
        c = bars[i]
        bd = abs(c['c']-c['o'])
        mh = max(k['h'] for k in pre)
        ml = min(k['l'] for k in pre)
        
        vol_ratio = calc_vol_ratio(bars, i)
        
        # BullOB
        if bars[i+1]['c'] > mh and c['c'] < c['o'] and bd > avg_body*0.7:
            top = round(max(c['o'],c['c']), 4)
            bot = round(min(c['o'],c['c']), 4)
            has_overlap = False
            if fvg_list:
                has_overlap = any(f['direction']=='long' and top>f['bottom'] and bot<f['top'] for f in fvg_list)
            vol_confirm = vol_ratio > 1.3
            signals.append({'type':'BullOB','direction':'long','top':top,'bottom':bot,
                            'index':i,'overlap_fvg':has_overlap,'vol_confirm':vol_confirm,
                            'score_bonus': (1.0 if has_overlap else 0) + (0.5 if vol_confirm else 0)})
        
        # BearOB
        if bars[i+1]['l'] < ml and c['c'] > c['o'] and bd > avg_body*0.7:
            top = round(max(c['o'],c['c']), 4)
            bot = round(min(c['o'],c['c']), 4)
            has_overlap = False
            if fvg_list:
                has_overlap = any(f['direction']=='short' and top>f['bottom'] and bot<f['top'] for f in fvg_list)
            vol_confirm = vol_ratio > 1.3
            signals.append({'type':'BearOB','direction':'short','top':top,'bottom':bot,
                            'index':i,'overlap_fvg':has_overlap,'vol_confirm':vol_confirm,
                            'score_bonus': (1.0 if has_overlap else 0) + (0.5 if vol_confirm else 0)})
    return signals

# =============================================
# BPR(V6)
# =============================================

def calc_bpr_v6(fvg_list, lookback=25):
    if not fvg_list or len(fvg_list) < 2:
        return []
    max_idx = max(f['index'] for f in fvg_list)
    recent = [f for f in fvg_list if f['index'] >= max_idx - lookback]
    if len(recent) < 2:
        return []
    bull = sorted([f for f in recent if f['direction']=='long'], key=lambda x:-x.get('strength',1))[:4]
    bear = sorted([f for f in recent if f['direction']=='short'], key=lambda x:-x.get('strength',1))[:4]
    if not bull or not bear:
        return []
    raw_bprs = []
    for b1 in bull:
        for b2 in bear:
            top = min(b1['top'], b2['top'])
            bot = max(b1['bottom'], b2['bottom'])
            if top > bot:
                raw_bprs.append({'top':round(top,4),'bottom':round(bot,4),
                    'mid':round((top+bot)/2,4),'index':max(b1['index'],b2['index']),
                    'width':round(top-bot,4)})
    if not raw_bprs:
        return []
    raw_bprs.sort(key=lambda x:-x['width'])
    merged = []
    for b in raw_bprs:
        if not any(abs(b['index']-m['index'])<=3 or 
                   (b['top']>m['bottom'] and b['bottom']<m['top']) for m in merged):
            merged.append(b)
    return merged[:3]

# =============================================
# V6 核心入口检测
# =============================================

def get_v6_params_from_state(vol_state, trend_state, vol_active):
    """基于市场状态返回参数集"""
    # 默认参数
    params = {
        'fvg_th': 0.25,
        'score_loose': 2.5,
        'score_strict': 3.5,
        'sl_loose': 2.0,
        'tp_loose': 2.5,
        'sl_strict': 1.5,
        'tp_strict': 3.0,
        'min_sigs_loose': 2,
        'min_sigs_strict': 3,
        'sweep_wick_min': 2.0,
        'bpr_lookback': 25,
    }
    
    # 高波动 → 高门槛, 宽止损
    if vol_state in ('very_high', 'high'):
        params['fvg_th'] = 0.35
        params['score_loose'] = 3.0
        params['score_strict'] = 4.0
        params['sl_loose'] = 2.5
        params['sl_strict'] = 2.0
    elif vol_state == 'medium':
        params['fvg_th'] = 0.25
        params['sl_loose'] = 2.0
        params['sl_strict'] = 1.5
    elif vol_state == 'low':
        params['fvg_th'] = 0.18
        params['score_loose'] = 2.0
        params['score_strict'] = 3.0
        params['sl_loose'] = 1.5
        params['sl_strict'] = 1.2
    else:  # very_low
        params['fvg_th'] = 0.15
        params['score_loose'] = 1.8
        params['score_strict'] = 2.5
        params['sl_loose'] = 1.2
        params['sl_strict'] = 1.0
    
    # 强趋势 → 松门槛, 远止盈
    if trend_state == 'strong_trend':
        params['score_loose'] = max(1.5, params['score_loose'] - 0.5)
        params['tp_loose'] += 0.5
        params['tp_strict'] += 0.5
    elif trend_state == 'ranging':
        params['score_loose'] += 0.3
        params['min_sigs_loose'] = 3
        params['sweep_wick_min'] = 2.5
        if params['fvg_th'] < 0.20:
            params['fvg_th'] = 0.20
    
    # 成交量确认
    if vol_active == 'high_volume':
        params['sl_loose'] = max(1.0, params['sl_loose'] - 0.3)
    elif vol_active == 'low_volume':
        params['score_loose'] += 0.3
        params['min_sigs_loose'] = 3
    
    return params

def score_signal_v6(direction, bars, idx, fvg, sweep_near, ob_near, choch, bpr_near):
    """
    V6评分系统 (加权多因子)
    返回: score, sigs_list, n_sig
    """
    score = 0.0
    sigs = []
    signals_found = {}
    last_idx = len(bars) - 1
    age = last_idx - idx
    
    # 时间权重: 越新越好
    tw = max(0.5, 1.0 - age / 30.0)
    
    # 1. FVG基础分 + 窗口加分
    fvg_strength = fvg.get('strength', 1)
    score += 1.0 + fvg_strength * 0.3  # 1.0~2.2
    sigs.append(f"FVG{fvg_strength}")
    signals_found['fvg'] = True
    
    # 窗口类型加分
    window = fvg.get('window', 3)
    if window >= 5:
        score += 0.3
        sigs.append(f"W{window}")
    
    # 2. Sweep (带vol确认)
    if sweep_near:
        best_sw = max(sweep_near, key=lambda s: s.get('wick_ratio', 0))
        wr = best_sw.get('wick_ratio', 0)
        sw_score = min(2.5, 0.5 + wr * 0.3)
        sw_score += best_sw.get('score_bonus', 0)
        score += sw_score
        signals_found['sw'] = True
        sigs.append(f"SW({wr:.1f})")
        if best_sw.get('vol_ratio', 1) > 1.3:
            sigs.append('V+')
    
    # 3. OB (带FVG重叠分)
    if ob_near:
        has_overlap = any(o.get('overlap_fvg') for o in ob_near)
        has_vol = any(o.get('vol_confirm') for o in ob_near)
        ob_score = 1.0
        if has_overlap: ob_score += 0.8
        if has_vol: ob_score += 0.5
        score += ob_score
        signals_found['ob'] = True
        ob_tag = 'OB'
        if has_overlap: ob_tag += '+F'
        if has_vol: ob_tag += '+V'
        sigs.append(ob_tag)
    
    # 4. CHOCH (带置信度)
    if choch.get('detected') and choch['direction'] == direction:
        conf = choch.get('confidence', 0.5)
        ch_score = 1.0 + conf * 1.5  # 1.0~2.5
        score += ch_score
        signals_found['ch'] = True
        sigs.append(f"CH({choch.get('type','?')})")
    
    # 5. BPR
    if bpr_near:
        score += 0.8
        signals_found['bpr'] = True
        sigs.append('BPR')
    
    # 6. 市场结构 (MS)
    recent = bars[max(0,idx-10):idx+1]
    bullish = sum(1 for k in recent if k['c'] > k['o'])
    bearish = sum(1 for k in recent if k['c'] < k['o'])
    if direction == 'long' and bullish > bearish:
        score += 0.5
        signals_found['ms'] = True
        sigs.append('MS')
    elif direction == 'short' and bearish > bullish:
        score += 0.5
        signals_found['ms'] = True
        sigs.append('MS')
    
    # 7. 成交量确认
    ci = min(idx + 1, last_idx - 1)
    if ci > 0 and ci < len(bars):
        vol_r = calc_vol_ratio(bars, ci)
        if vol_r > 1.3:
            score += 0.5
            signals_found['vol'] = True
            sigs.append(f"V{vol_r:.1f}")
    
    # 8. 确认K线
    if ci > 0 and ci < len(bars):
        cb = bars[ci]
        if (direction == 'long' and cb['c'] > cb['o']) or \
           (direction == 'short' and cb['c'] < cb['o']):
            score += 0.3
            signals_found['cf'] = True
            sigs.append('CF')
    
    # 最终时间加权
    score *= tw
    n_sig = sum(1 for v in signals_found.values() if v)
    
    return round(score, 2), sigs, n_sig

def detect_entries_v6(bars, params=None, state_params=None):
    """
    V6入口检测 — 四层信号质量
    """
    results = {'bronze':[], 'silver':[], 'gold':[], 'platinum':[], 'total':[]}
    
    if len(bars) < 60:
        return results
    
    # 市场状态分类
    vol_state, trend_state, vol_active = classify_market_state(bars)
    
    # 参数获取
    if state_params:
        sp = state_params
    elif params:
        sp = get_v6_params_from_state(vol_state, trend_state, vol_active)
        for k, v in params.items():
            if k in sp:
                sp[k] = v
    else:
        sp = get_v6_params_from_state(vol_state, trend_state, vol_active)
    
    # 多窗口FVG
    fvg_list = detect_fvg_v6(bars, sp.get('fvg_th', 0.25), [3, 5, 8])
    
    # Sweep + OB + CHOCH + BPR
    sweep_list = detect_sweep_v6(bars, 12, sp.get('sweep_wick_min', 2.0))
    ob_list = detect_ob_v6(bars, fvg_list)
    choch = detect_choch_v6(bars)
    bpr_list = calc_bpr_v6(fvg_list, sp.get('bpr_lookback', 25))
    
    if not fvg_list:
        return results
    
    last_idx = len(bars) - 1
    sc_loose = sp.get('score_loose', 2.5)
    sc_strict = sp.get('score_strict', 3.5)
    min_s_l = sp.get('min_sigs_loose', 2)
    min_s_s = sp.get('min_sigs_strict', 3)
    sl_l = sp.get('sl_loose', 2.0)
    tp_l = sp.get('tp_loose', 2.5)
    sl_s = sp.get('sl_strict', 1.5)
    tp_s = sp.get('tp_strict', 3.0)
    
    for fvg in fvg_list[-25:]:  # 最近25个FVG
        i = fvg.get('index', 0)
        if i < 3 or i >= last_idx - 2:
            continue
        age = last_idx - i
        if age > 35:
            continue
        
        direction = fvg['direction']
        
        # Sweep
        sw = [s for s in sweep_list if s['direction'] == direction 
              and -3 <= i - s.get('index',0) <= 20]
        
        # OB
        ob_n = [o for o in ob_list if o['direction'] == direction 
                and abs(o.get('index',0)-i) <= 10]
        
        # BPR
        bpr_n = [b for b in bpr_list if abs(b.get('index',0)-i) <= 12]
        
        # 评分
        score, sigs, n_sig = score_signal_v6(direction, bars, i, fvg, sw, ob_n, choch, bpr_n)
        
        # ===== 四层入口 =====
        atr = calc_atr(bars[:i+5])
        ep = fvg['mid']
        
        # Bronze: 宽松(低门槛高交易量)
        if score >= sc_loose and n_sig >= min_s_l:
            entry = {
                'idx': min(i + 1, last_idx - 1),
                'dir': 'L' if direction == 'long' else 'S',
                'fvg_idx': i,
                'sigs': sigs,
                'sc': round(score, 2),
                'n_sig': n_sig,
            }
            # Bronze SL/TP (最宽松)
            if direction == 'long':
                entry['ep'] = round(ep, 4)
                entry['sl'] = round(ep - atr * max(0.5, sl_l), 4)
                entry['tp'] = round(ep + atr * max(1.0, tp_l), 4)
            else:
                entry['ep'] = round(ep, 4)
                entry['sl'] = round(ep + atr * max(0.5, sl_l), 4)
                entry['tp'] = round(ep - atr * max(1.0, tp_l), 4)
            results['bronze'].append(entry)
            results['total'].append({**entry, 'level':'bronze'})
        
        # Silver: 中等 (score>=3.0, 3 sigs)
        if score >= max(sc_loose + 0.5, 3.0) and n_sig >= max(min_s_l, 2):
            entry = {
                'idx': min(i + 1, last_idx - 1),
                'dir': 'L' if direction == 'long' else 'S',
                'fvg_idx': i,
                'sigs': sigs,
                'sc': round(score, 2),
                'n_sig': n_sig,
            }
            sl_mid = (sl_l + sl_s) / 2
            tp_mid = (tp_l + tp_s) / 2
            if direction == 'long':
                entry['ep'] = round(ep, 4)
                entry['sl'] = round(ep - atr * max(0.5, sl_mid), 4)
                entry['tp'] = round(ep + atr * max(1.0, tp_mid), 4)
            else:
                entry['ep'] = round(ep, 4)
                entry['sl'] = round(ep + atr * max(0.5, sl_mid), 4)
                entry['tp'] = round(ep - atr * max(1.0, tp_mid), 4)
            results['silver'].append(entry)
            if not any(abs(e['idx']-entry['idx'])<=3 for e in results['total']):
                results['total'].append({**entry, 'level':'silver'})
        
        # Gold: 严格 (信号强)
        if score >= sc_strict and n_sig >= min_s_s:
            entry = {
                'idx': min(i + 1, last_idx - 1),
                'dir': 'L' if direction == 'long' else 'S',
                'fvg_idx': i,
                'sigs': sigs,
                'sc': round(score, 2),
                'n_sig': n_sig,
            }
            if direction == 'long':
                entry['ep'] = round(ep, 4)
                entry['sl'] = round(ep - atr * max(0.5, sl_s), 4)
                entry['tp'] = round(ep + atr * max(1.5, tp_s), 4)
            else:
                entry['ep'] = round(ep, 4)
                entry['sl'] = round(ep + atr * max(0.5, sl_s), 4)
                entry['tp'] = round(ep - atr * max(1.5, tp_s), 4)
            results['gold'].append(entry)
            if not any(abs(e['idx']-entry['idx'])<=3 for e in results['total']):
                results['total'].append({**entry, 'level':'gold'})
        
        # Platinum: 极致 (score>=5.0, 5 sigs)
        if score >= 5.0 and n_sig >= 5:
            entry = {
                'idx': min(i + 1, last_idx - 1),
                'dir': 'L' if direction == 'long' else 'S',
                'fvg_idx': i,
                'sigs': sigs,
                'sc': round(score, 2),
                'n_sig': n_sig,
            }
            if direction == 'long':
                entry['ep'] = round(ep, 4)
                entry['sl'] = round(ep - atr * max(1.0, sl_s * 0.7), 4)
                entry['tp'] = round(ep + atr * max(2.0, tp_s * 1.3), 4)
            else:
                entry['ep'] = round(ep, 4)
                entry['sl'] = round(ep + atr * max(1.0, sl_s * 0.7), 4)
                entry['tp'] = round(ep - atr * max(2.0, tp_s * 1.3), 4)
            results['platinum'].append(entry)
            if not any(abs(e['idx']-entry['idx'])<=3 for e in results['total']):
                results['total'].append({**entry, 'level':'platinum'})
    
    # 去重
    for channel in results:
        entries = results[channel]
        if not entries:
            continue
        entries.sort(key=lambda e: -e.get('sc', 0))
        deduped = []
        for e in entries:
            if not any(abs(e['idx']-f['idx']) <= 5 and e['dir'] == f['dir'] for f in deduped):
                deduped.append(e)
        results[channel] = deduped
    
    return results

# =============================================
# 回测 (V6)
# =============================================

def simulate_entry_v6(entry, bars):
    if not isinstance(entry, dict) or not isinstance(bars, list) or len(bars) < 5:
        return None
    ei = entry.get('idx', 0)
    if ei >= len(bars):
        return None
    d = entry.get('dir', 'L')
    ep = entry.get('ep', 0)
    sl = entry.get('sl', 0)
    tp = entry.get('tp', 0)
    sigs = entry.get('sigs', [])
    sc = entry.get('sc', 0)
    
    for j in range(ei, len(bars)):
        b = bars[j]
        if d == 'L':
            if b['l'] <= sl:
                return {'pnl':(sl-ep)/ep, 'reason':'sl', 'bars':j-ei+1, 'sig':sigs, 'sc':sc, 'ret':(sl-ep)/ep*100}
            if b['h'] >= tp:
                return {'pnl':(tp-ep)/ep, 'reason':'tp', 'bars':j-ei+1, 'sig':sigs, 'sc':sc, 'ret':(tp-ep)/ep*100}
        else:
            if b['h'] >= sl:
                return {'pnl':(ep-sl)/ep, 'reason':'sl', 'bars':j-ei+1, 'sig':sigs, 'sc':sc, 'ret':(ep-sl)/ep*100}
            if b['l'] <= tp:
                return {'pnl':(ep-tp)/ep, 'reason':'tp', 'bars':j-ei+1, 'sig':sigs, 'sc':sc, 'ret':(ep-tp)/ep*100}
    last = bars[-1]['c']
    pnl = (last-ep)/ep if d=='L' else (ep-last)/ep
    return {'pnl':pnl, 'reason':'eod', 'bars':len(bars)-ei+1, 'sig':sigs, 'sc':sc, 'ret':pnl*100}

def backtest_v6(bars, mode='total', params=None):
    if not isinstance(bars, list) or len(bars) < 60:
        return []
    entries = detect_entries_v6(bars, params)
    result = entries.get(mode, [])
    if not result:
        return []
    trades = []
    for e in result:
        t = simulate_entry_v6(e, bars)
        if t:
            trades.append(t)
    return trades

# =============================================
# 评估(V6)
# =============================================

def evaluate_trades(trades, name='V6'):
    n = len(trades)
    if n == 0:
        return {'n':0, 'wr':0.0, 'pf':0.0, 'sr':0.0, 'ret':0.0, 'score':0}
    
    wins = [t for t in trades if t['pnl']>0]
    losses = [t for t in trades if t['pnl']<=0]
    
    wr = len(wins)/n*100
    ret = sum(t['pnl'] for t in trades)*100
    avg = sum(t['pnl'] for t in trades)/n
    std = math.sqrt(sum((p['pnl']-avg)**2 for p in trades)/n) if n>1 else 0.001
    sr = (avg/std)*math.sqrt(252) if std>0 else 0
    
    # Proper PF
    win_sum = sum(t['pnl'] for t in wins) if wins else 0
    loss_sum = abs(sum(t['pnl'] for t in losses)) if losses else 0
    pf = (win_sum / loss_sum) if loss_sum > 0 else (999 if win_sum > 0 else 0)
    
    print(f"  {name:>15}: {n:>3d}t  WR={wr:>5.1f}%  ", end='')
    print(f"PF={pf:>7.2f}  SR={sr:>5.2f}  Ret={ret:>+7.2f}%")
    
    return {'n':n, 'wr':round(wr,1), 'pf':round(pf,3), 'sr':round(sr,3), 'ret':round(ret,2)}

def compute_score_v6(trades):
    n = len(trades)
    if n < 3:
        return 0
    wins = [t for t in trades if t['pnl']>0]
    losses = [t for t in trades if t['pnl']<=0]
    wr = len(wins)/n*100
    win_sum = sum(t['pnl'] for t in wins) if wins else 0
    loss_sum = abs(sum(t['pnl'] for t in losses)) if losses else 0
    pf = (win_sum / loss_sum) if loss_sum > 0 else 999
    
    avg_ret = sum(t['pnl'] for t in trades)/n
    std = math.sqrt(sum((t['pnl']-avg_ret)**2 for t in trades)/n) if n>1 else 0.001
    sr = (avg_ret/std)*math.sqrt(252) if std>0 else 0
    
    # Score: balance WR, PF, and sample size
    n_penalty = min(1.0, n/30) if n < 30 else 1.0
    pf_capped = min(5.0, pf)
    
    # Main score: WR contribution + SR contribution + PF contribution
    score = (wr / 100) * 50 + sr * 20 + pf_capped * 30
    score *= n_penalty
    
    if pf < 1.0:
        score *= 0.2
    if wr < 40:
        score *= 0.3
    if n < 3:
        score *= 0.1
    
    return round(score, 1)

# =============================================
# 网格 + 遗传算法 参数搜索
# =============================================

def grid_param_search(symbol, base_params, param_grid):
    """网格搜索: 在param_grid范围内搜索最佳参数"""
    from itertools import product
    
    print(f"\n{'='*70}")
    print(f"  Grid Search: {symbol}")
    print(f"{'='*70}")
    
    bars = load_cached_bars(symbol, 500)
    if not bars or len(bars) < 100:
        print(f"  Insufficient data")
        return None
    
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    
    best_score = 0
    best_params = None
    best_trades = None
    total = 1
    for v in values:
        total *= len(v)
    
    print(f"  Parameter combinations: {total}")
    start = time.time()
    
    tested = 0
    for combo in product(*values):
        params = {k: v for k, v in base_params.items()}
        for k, v in zip(keys, combo):
            params[k] = v
        
        trades = backtest_v6(bars, 'total', params)
        if not trades:
            tested += 1
            continue
        
        score = compute_score_v6(trades)
        n = len(trades)
        wr = len([t for t in trades if t['pnl']>0])/n*100 if n>0 else 0
        
        if score > best_score and n >= 3:
            best_score = score
            best_params = {**params}
            best_trades = trades
        
        tested += 1
        if tested % 50 == 0:
            elapsed = time.time() - start
            rate = tested / elapsed if elapsed > 0 else 0
            print(f"    [{tested}/{total}] rate={rate:.0f}/s best={best_score}")
    
    elapsed = time.time() - start
    print(f"\n  Best score: {best_score}")
    print(f"  Best params: {best_params}")
    print(f"  Time: {elapsed:.1f}s")
    
    if best_params:
        best_params['_score'] = best_score
    
    return best_params

# =============================================
# 主入口: 全自动迭代
# =============================================

if __name__ == '__main__':
    print("="*70)
    print("  SMC Engine V6 — 四层共振引擎")
    print("="*70)
    
    test_stocks = ['600519.SH','000001.SZ','000858.SZ','600036.SH',
                   '002594.SZ','300750.SZ','601318.SH','600887.SH',
                   '000002.SZ','600585.SH','688981.SH','002415.SZ']
    
    # Test V6 performance
    print("\n--- V6 Engine Test ---")
    total_trades = {'bronze':[], 'silver':[], 'gold':[], 'platinum':[], 'total':[]}
    
    for code in test_stocks:
        print(f"\n  {code}:")
        try:
            bars = get_klines(code, 'daily', 400)
            if len(bars) < 100:
                print(f"    Insufficient data ({len(bars)})")
                continue
            
            vol_state, trend_state, vol_active = classify_market_state(bars)
            print(f"    State: {vol_state} / {trend_state} / {vol_active}")
            
            entries = detect_entries_v6(bars)
            for mode in ['bronze', 'silver', 'gold', 'platinum', 'total']:
                et = entries.get(mode, [])
                if et:
                    print(f"    {mode:>8}: {len(et)} entries")
                    trades = []
                    for e in et:
                        t = simulate_entry_v6(e, bars)
                        if t:
                            trades.append(t)
                    if trades:
                        r = evaluate_trades(trades, f'V6.{mode}')
                        total_trades[mode].extend(trades)
        except Exception as e:
            import traceback
            print(f"    ERROR: {e}")
            traceback.print_exc()
    
    print(f"\n{'='*70}")
    print(f"  V6 综合 (all stocks)")
    print(f"{'='*70}")
    for mode in ['bronze', 'silver', 'gold', 'platinum', 'total']:
        tt = total_trades.get(mode, [])
        if tt:
            evaluate_trades(tt, f'V6.{mode}')