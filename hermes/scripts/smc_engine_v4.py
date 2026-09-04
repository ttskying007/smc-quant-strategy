#!/usr/bin/env python3
"""
SMC Engine v4.0 — 新一代多粒度高胜率共振引擎
================================================
核心设计目标: WR>80% 且 PF>5.0

V3.x问题分析:
  1. 信号过于依赖单一FVG+Sweep组合, 忽略了BPR/IFVG等结构
  2. score门槛单一, 不区分信号质量层次
  3. 回测只在日线500根, 样本量不足时WR波动大
  4. 震荡市/低波动股表现极差(W<20%)

V4创新:
  1. 多粒度FVG检测 (3种: 标准/宽幅/连续合并)
  2. 双通道验证系统 (宽松通道捕信号+严格通道提胜率)
  3. 基于波动率的动态参数映射
  4. BPR+OB+FVG三信号共振入场
  5. 信号质量评分+自适应SL/TP
  6. 多股票分类策略 (高波动/趋势/震荡)
"""

import math, json, time, os, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))

HUBBLE_BASE = "http://43.167.234.49:3101"
HUBBLE_HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}

# ═══════════════════════════════════════════════
# 数据获取(独立不依赖smc_backtest_v2)
# ═══════════════════════════════════════════════

def fetch_hubble(url, timeout=20):
    import urllib.request
    for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
        os.environ.pop(k, None)
    req = urllib.request.Request(url, headers=HUBBLE_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode()


def get_klines(symbol, interval='daily', limit=500):
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
    # 反转: API可能返回倒序
    if len(bars)>=2 and bars[0]['t'] > bars[1]['t']:
        bars.reverse()
    return bars


def get_stock_list():
    import json, urllib.request
    url = f"{HUBBLE_BASE}/api/v2/cnstock/symbols?listStatus=L"
    req = urllib.request.Request(url, headers=HUBBLE_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.loads(resp.read())
    return raw.get('symbols', raw.get('data', []))


# ═══════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════

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


def find_swing_highs(klines, left=2, right=2):
    return [(i, klines[i]['h']) for i in range(left, len(klines)-right)
            if klines[i]['h'] == max(klines[j]['h'] for j in range(i-left, i+right+1))]


def find_swing_lows(klines, left=2, right=2):
    return [(i, klines[i]['l']) for i in range(left, len(klines)-right)
            if klines[i]['l'] == min(klines[j]['l'] for j in range(i-left, i+right+1))]


# ═══════════════════════════════════════════════
# 多粒度FVG检测 (V4核心)
# ═══════════════════════════════════════════════

def detect_fvg_standard(bars, threshold=0.30):
    """
    标准FVG: 基于3K线缺口
    返回: [{'type','direction','top','bottom','mid','strength','index','width'}]
    """
    if len(bars) < 3:
        return []
    avg_r = sum(abs(k['h']-k['l']) for k in bars[-30:]) / max(1, min(30, len(bars)))
    if avg_r == 0:
        return []
    results = []
    for i in range(1, len(bars)-1):
        p, c, n = bars[i-1], bars[i], bars[i+1]
        bd = abs(c['c']-c['o'])
        if c['c'] > c['o']:  # 阳线 → Bullish
            top = min(p['h'], n['h'])
            bot = max(p['l'], n['l'])
            if top > bot and (top-bot) > avg_r*threshold:
                strength = 1
                if bd > (top-bot)*2: strength += 1
                if (top-bot) > avg_r*0.5: strength += 1
                results.append({'type':'BullFVG','direction':'long',
                    'top':top,'bottom':bot,'mid':(top+bot)/2,
                    'strength':min(3,strength),'index':i,'width':top-bot})
        elif c['c'] < c['o']:  # 阴线 → Bearish
            top = max(p['h'], n['h'])
            bot = min(p['l'], n['l'])
            if top > bot and (top-bot) > avg_r*threshold:
                strength = 1
                if bd > (top-bot)*2: strength += 1
                if (top-bot) > avg_r*0.5: strength += 1
                results.append({'type':'BearFVG','direction':'short',
                    'top':top,'bottom':bot,'mid':(top+bot)/2,
                    'strength':min(3,strength),'index':i,'width':top-bot})
    return results


def detect_fvg_wide(bars, threshold=0.15):
    """
    宽幅FVG: 低阈值, 捕获更多FVG
    用于宽松通道的信号积累
    """
    return detect_fvg_standard(bars, threshold)


def detect_fvg_merge(bars, threshold=0.25, max_gap=3):
    """
    连续合并FVG: 相邻FVG合并为一个区域
    合并条件: 同向, 间隔<=max_gap根K线
    """
    raw = detect_fvg_standard(bars, threshold)
    if not raw:
        return []
    # 按方向分组
    long_sigs = [s for s in raw if s['direction']=='long']
    short_sigs = [s for s in raw if s['direction']=='short']
    
    def merge_group(sigs):
        if not sigs:
            return []
        sigs.sort(key=lambda s: s['index'])
        merged = [sigs[0]]
        for s in sigs[1:]:
            last = merged[-1]
            if s['index'] - last['index'] <= max_gap:
                # 合并: 扩大区域
                last['top'] = max(last['top'], s['top'])
                last['bottom'] = min(last['bottom'], s['bottom'])
                last['mid'] = (last['top'] + last['bottom']) / 2
                last['width'] = last['top'] - last['bottom']
                last['strength'] = min(5, last['strength'] + s['strength'])
                last['end_index'] = s['index']
            else:
                last['end_index'] = last['index']
                merged.append(s)
        for m in merged:
            if 'end_index' not in m:
                m['end_index'] = m['index']
        return merged
    
    return merge_group(long_sigs) + merge_group(short_sigs)


# ═══════════════════════════════════════════════
# 精准Sweep检测 (V4)
# ═══════════════════════════════════════════════

def detect_sweep_precise(bars, lookback=15, wick_min=2.0, body_min_pct=0.3):
    """
    精准Sweep检测:
    - 过滤极小实体K线 (防wick_ratio爆炸)
    - wick_min=2.0: 只有真正长影线
    - 增加绝对影线长度过滤
    """
    if len(bars) < lookback+3:
        return []
    avg_body = sum(abs(k['c']-k['o']) for k in bars[-30:]) / max(1, min(30, len(bars)))
    if avg_body == 0:
        return []
    signals = []
    for i in range(lookback, len(bars)):
        c = bars[i]
        body = abs(c['c']-c['o'])
        if body < avg_body * body_min_pct:
            continue
        seg = bars[i-lookback:i]
        hh = max(k['h'] for k in seg)
        ll = min(k['l'] for k in seg)
        
        # BSL Sweep (向上突破)
        if c['h'] > hh and c['c'] < hh:
            wick_abs = c['h'] - max(c['c'], c['o'])
            wr = wick_abs / body if body > 0 else 999
            if wr >= wick_min:
                signals.append({'type':'BSLSweep','direction':'short',
                    'level':hh,'swept_price':c['h'],
                    'wick_ratio':round(wr,2),'wick_abs':round(wick_abs,2),
                    'index':i})
        
        # SSL Sweep (向下突破)
        if c['l'] < ll and c['c'] > ll:
            wick_abs = min(c['c'],c['o']) - c['l']
            wr = wick_abs / body if body > 0 else 999
            if wr >= wick_min:
                signals.append({'type':'SSLSweep','direction':'long',
                    'level':ll,'swept_price':c['l'],
                    'wick_ratio':round(wr,2),'wick_abs':round(wick_abs,2),
                    'index':i})
    return signals


# ═══════════════════════════════════════════════
# 结构转变检测 (V4: 多重确认)
# ═══════════════════════════════════════════════

def detect_pivot_highs(bars, left=2, right=2):
    return [(i, bars[i]['h']) for i in range(left, len(bars)-right)
            if bars[i]['h'] == max(bars[j]['h'] for j in range(i-left, i+right+1))
            and bars[i]['h'] > bars[i]['l']]

def detect_pivot_lows(bars, left=2, right=2):
    return [(i, bars[i]['l']) for i in range(left, len(bars)-right)
            if bars[i]['l'] == min(bars[j]['l'] for j in range(i-left, i+right+1))
            and bars[i]['h'] > bars[i]['l']]

def detect_choch_v4(bars):
    """
    V4 CHOCH: LL+Break或HH+Break + V2 fallback
    """
    if len(bars) < 15:
        return {'detected':False}
    seg = bars[-30:] if len(bars) > 30 else bars
    ph = detect_pivot_highs(seg)
    pl = detect_pivot_lows(seg)
    
    if len(ph) >= 3 and len(pl) >= 3:
        rpl = [(i,v) for i,v in pl[-4:]]
        rph = [(i,v) for i,v in ph[-4:]]
        
        # LL → Break SH (Bullish)
        if len(rpl) >= 3:
            vals = [v for _,v in rpl[-3:]]
            if vals[0] > vals[1] > vals[2]:  # 3 consecutive LL
                shs = sorted([v for _,v in ph if rpl[-1][0] < _], reverse=True)
                if shs and seg[-1]['c'] > shs[0]:
                    return {'detected':True,'direction':'long',
                            'break_level':shs[0],'type':'LL+Break'}
        
        # HH → Break SL (Bearish)
        if len(rph) >= 3:
            vals = [v for _,v in rph[-3:]]
            if vals[0] < vals[1] < vals[2]:  # 3 consecutive HH
                sls = sorted([v for _,v in pl if rph[-1][0] < _])
                if sls and seg[-1]['c'] < sls[0]:
                    return {'detected':True,'direction':'short',
                            'break_level':sls[0],'type':'HH+Break'}
    
    # Fallback to V2
    lb = min(20, len(bars))
    seg2 = bars[-lb:]
    f5 = seg2[:5]
    l3 = seg2[-3:]
    if len(f5) >= 5 and len(l3) >= 3:
        f5h = max(k['h'] for k in f5)
        f5l = min(k['l'] for k in f5)
        l3h = max(k['h'] for k in l3)
        l3l = min(k['l'] for k in l3)
        if f5[-1]['c'] < f5[0]['c'] and l3h > f5h:
            return {'detected':True,'direction':'long','break_level':f5h,'type':'V2'}
        if f5[-1]['c'] > f5[0]['c'] and l3l < f5l:
            return {'detected':True,'direction':'short','break_level':f5l,'type':'V2'}
    
    return {'detected':False}


# ═══════════════════════════════════════════════
# OB检测 (V4: 精确+FVG对齐)
# ═══════════════════════════════════════════════

def detect_ob_v4(bars, fvg_list=None):
    """
    V4 OB: 只在FVG重叠时保留
    """
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
        
        # BullOB: 下降 + 突破 + FVG对齐
        if bars[i+1]['c'] > mh and c['c'] < c['o'] and bd > avg_body*0.8:
            top = round(max(c['o'],c['c']), 4)
            bot = round(min(c['o'],c['c']), 4)
            if fvg_list:
                has_overlap = any(f['direction']=='long' and top>f['bottom'] and bot<f['top'] for f in fvg_list)
                if has_overlap:
                    signals.append({'type':'BullOB','direction':'long','top':top,'bottom':bot,
                                    'index':i,'overlap_fvg':True})
        
        # BearOB
        if bars[i+1]['l'] < ml and c['c'] > c['o'] and bd > avg_body*0.8:
            top = round(max(c['o'],c['c']), 4)
            bot = round(min(c['o'],c['c']), 4)
            if fvg_list:
                has_overlap = any(f['direction']=='short' and top>f['bottom'] and bot<f['top'] for f in fvg_list)
                if has_overlap:
                    signals.append({'type':'BearOB','direction':'short','top':top,'bottom':bot,
                                    'index':i,'overlap_fvg':True})
    return signals


# ═══════════════════════════════════════════════
# BPR (Balance Price Range — V4: 更精准)
# ═══════════════════════════════════════════════

def calc_bpr_v4(fvg_list, max_idx=None):
    """
    V4 BPR: 仅最近30根的FVG对, 取strength最大的
    """
    if not fvg_list or len(fvg_list) < 2:
        return []
    if max_idx is None:
        max_idx = max(f['index'] for f in fvg_list)
    recent = [f for f in fvg_list if f['index'] >= max_idx - 30]
    if len(recent) < 2:
        return []
    bull = sorted([f for f in recent if f['direction']=='long'], key=lambda x:-x.get('strength',1))[:3]
    bear = sorted([f for f in recent if f['direction']=='short'], key=lambda x:-x.get('strength',1))[:3]
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
    # 合并重叠
    raw_bprs.sort(key=lambda x:-x['width'])
    merged = []
    for b in raw_bprs:
        if not any(abs(b['index']-m['index'])<=5 or 
                   (b['top']>m['bottom'] and b['bottom']<m['top']) for m in merged):
            merged.append(b)
    return merged[:3]  # 最多3个


# ═══════════════════════════════════════════════
# 波动率分类 (V4核心)
# ═══════════════════════════════════════════════

def get_volatility_profile(bars):
    """
    返回股票的波动率画像
    用于自适应调整入场阈值
    """
    if len(bars) < 50:
        return {'vol_level':'unknown','atr_pct':0,'trend_strength':0,'avg_vol':0}
    
    # ATR% (最近20根/50根的avg)
    atr = calc_atr(bars)
    avg_price = sum((bars[i]['h']+bars[i]['l'])/2 for i in range(-20, 0)) / 20
    atr_pct = atr / avg_price * 100 if avg_price > 0 else 0
    
    # 波动率分类
    if atr_pct < 1.0:
        vol_level = 'low'
    elif atr_pct < 2.5:
        vol_level = 'medium'
    else:
        vol_level = 'high'
    
    # 趋势强度 (基于ADX-like: 最近20根K线的方向一致性)
    recent = bars[-20:]
    ups = sum(1 for k in recent if k['c'] > k['o'])
    downs = sum(1 for k in recent if k['c'] < k['o'])
    trend_strength = abs(ups - downs) / len(recent)  # 0~1
    
    # 平均成交量
    avg_vol = sum(k['v'] for k in recent) / len(recent)
    
    return {
        'vol_level': vol_level,
        'atr_pct': round(atr_pct, 2),
        'trend_strength': round(trend_strength, 2),
        'avg_vol': round(avg_vol, 0),
        'atr': round(atr, 4),
    }


def get_adaptive_params(vol_profile):
    """
    基于波动率画像返回自适应参数
    """
    vl = vol_profile['vol_level']
    ts = vol_profile['trend_strength']
    atr_pct = vol_profile['atr_pct']
    
    # 自适应FVG阈值 (高波动→高阈值)
    if vl == 'high':
        fvg_th = 0.35
        score_th = 3.5
        sl_mult = 2.0
        tp_mult = 3.0
    elif vl == 'medium':
        fvg_th = 0.25
        score_th = 3.0
        sl_mult = 1.8
        tp_mult = 2.5
    else:  # low
        fvg_th = 0.18
        score_th = 2.5
        sl_mult = 1.5
        tp_mult = 2.0
    
    # 趋势增强
    if ts > 0.5:  # 强趋势 → 松阈值捕获更多
        score_th -= 0.5
        tp_mult += 0.5
    elif ts < 0.2:  # 弱趋势/震荡 → 严阈值
        score_th += 0.5
        sl_mult *= 0.8  # 紧止损
    
    # 低波动 → 降低门槛
    if atr_pct < 1.0:
        fvg_th = max(0.15, fvg_th - 0.05)
        score_th = max(1.5, score_th - 0.5)
    
    return {
        'fvg_threshold': round(fvg_th, 2),
        'score_threshold': round(score_th, 1),
        'sl_mult': round(sl_mult, 1),
        'tp_mult': round(tp_mult, 1),
        'vol_level': vl,
        'trend_strength': ts,
    }


# ═══════════════════════════════════════════════
# V4 入口检测 (核心!)
# ═══════════════════════════════════════════════

def _ensure_time(bars):
    for b in bars:
        if 't' in b and isinstance(b['t'], (int, float)):
            b['t'] = str(int(b['t']))
    return bars

def detect_entries_v4(bars, params=None):
    bars = _ensure_time(bars)
    """
    V4 入口检测 — 多粒度FVG + 信号融合 + 双通道
    
    评分系统:
    - FVG: +1.0~2.0 (取决于strength)
    - Sweep: +0.5~2.0 (取决于wick_ratio)
    - OB: +0.8~1.5
    - CHOCH: +1.0~2.0
    - BPR: +0.5~1.0
    - Confirm K: +0.5~1.0
    - MS alignment: +0.3~0.8
    
    宽松通道: score>=2.5, >=2 signals
    严格通道: score>=4.0, >=3 signals + CHOCH
    """
    results = {'loose':[], 'strict':[], 'total':[]}
    
    if len(bars) < 60:
        return results
    
    # 波动率画像
    vol_profile = get_volatility_profile(bars)
    if params:
        ap = params  # 外部传入的参数
    else:
        ap = get_adaptive_params(vol_profile)
    
    # 多粒度FVG
    fvg_std = detect_fvg_standard(bars, ap.get('fvg_threshold', 0.30))
    fvg_wide = detect_fvg_wide(bars, max(0.12, ap.get('fvg_threshold', 0.30)*0.7))
    
    # 合并去重 (标准优先)
    seen_fvg = {}
    for f in fvg_std + fvg_wide:
        k = (f['index'], f['direction'])
        if k not in seen_fvg or f['strength'] > seen_fvg[k].get('strength', 0):
            seen_fvg[k] = f
    fvg_list = list(seen_fvg.values())
    fvg_list.sort(key=lambda x: x['index'])
    
    # 连续合并FVG
    fvg_merge = detect_fvg_merge(bars, ap.get('fvg_threshold', 0.30)*0.8, 3)
    
    # Sweep + OB + CHOCH
    sweep_list = detect_sweep_precise(bars, 15, 2.0)
    ob_list = detect_ob_v4(bars, fvg_list)
    choch = detect_choch_v4(bars)
    bpr_list = calc_bpr_v4(fvg_list)
    
    if not fvg_list:
        return results
    
    last_idx = len(bars) - 1
    sc_th = ap.get('score_threshold', 3.0)
    sl_m = ap.get('sl_mult', 1.8)
    tp_m = ap.get('tp_mult', 2.5)
    
    for fvg in fvg_list[-20:]:  # 最近20个FVG
        i = fvg.get('index', 0)
        if i < 3 or i >= last_idx - 2:
            continue
        age = last_idx - i
        if age > 30:  # 超过30根K线的FVG忽略
            continue
        
        direction = fvg['direction']
        
        # 时间加权
        tw = max(0.4, 1.0 - age / 30.0)
        
        # ═══ 共振评分 ═══
        signals_found = {'fvg': True}
        score = 1.0 + fvg.get('strength', 1) * 0.3  # FVG基础: 1.0~1.9
        score_parts = [f"FVG{fvg.get('strength',1)}"]
        
        # 1. Sweep
        sw = [s for s in sweep_list if s['direction'] == direction 
              and -5 <= i - s.get('index',0) <= 15]
        if sw:
            best_sw = max(sw, key=lambda s: s.get('wick_ratio',0))
            wr = best_sw.get('wick_ratio', 0)
            sw_score = min(2.0, 0.5 + wr * 0.4)
            score += sw_score
            signals_found['sw'] = True
            score_parts.append(f"SW({wr:.1f})")
        
        # 2. OB
        ob_near = [o for o in ob_list if o['direction'] == direction and abs(o.get('index',0)-i) <= 12]
        if ob_near:
            has_overlap = any(o.get('overlap_fvg') for o in ob_near)
            score += 1.5 if has_overlap else 0.8
            signals_found['ob'] = True
            score_parts.append('OB+' if has_overlap else 'OB')
        
        # 3. CHOCH
        if choch.get('detected') and choch['direction'] == direction:
            ch_type = choch.get('type', 'V2')
            if 'LL' in ch_type or 'HH' in ch_type:
                score += 2.0  # V4: 更强
            else:
                score += 1.5  # V2 fallback
            signals_found['ch'] = True
            score_parts.append(f"CH({ch_type})")
        
        # 4. BPR
        bpr_near = [b for b in bpr_list if abs(b.get('index',0)-i) <= 15]
        if bpr_near:
            score += 1.0
            signals_found['bpr'] = True
            score_parts.append('BPR')
        
        # 5. 市场结构对齐 (通过最近pivot判断)
        # 简化: 如果FVG出现在趋势方向上加分
        recent = bars[max(0,i-10):i+1]
        bullish_bars = sum(1 for k in recent if k['c'] > k['o'])
        bearish_bars = sum(1 for k in recent if k['c'] < k['o'])
        
        if direction == 'long':
            if bullish_bars > bearish_bars:
                score += 0.5
                signals_found['ms'] = True
                score_parts.append('MS')
        else:
            if bearish_bars > bullish_bars:
                score += 0.5
                signals_found['ms'] = True
                score_parts.append('MS')
        
        # 6. 连续合并FVG加分
        merge_near = [m for m in fvg_merge if m['direction'] == direction 
                      and abs(m.get('index',0)-i) <= 3]
        if merge_near:
            score += 0.5
            signals_found['merge'] = True
            score_parts.append('MG')
        
        # 7. 确认K线
        ci = min(i + 1, last_idx - 1)
        if ci > 0 and i < len(bars):
            cb = bars[ci]
            if (direction == 'long' and cb['c'] > cb['o']):
                score += 0.5
                signals_found['cf'] = True
                score_parts.append('CF')
            elif (direction == 'short' and cb['c'] < cb['o']):
                score += 0.5
                signals_found['cf'] = True
                score_parts.append('CF')
        
        # 最终: 时间加权
        score *= tw
        
        n_sig = sum(1 for v in signals_found.values() if v)
        
        # ═══ 双通道 ═══
        entry_data = {
            'idx': min(i + 1, last_idx - 1),
            'dir': 'L' if direction == 'long' else 'S',
            'fvg_idx': i,
            'sigs': score_parts,
            'sc': round(score, 2),
            'n_sig': n_sig,
        }
        
        # 宽松: score>=2.5, >=2 signals
        if score >= 2.0 and n_sig >= 2:
            atr = calc_atr(bars[:i+5])
            ep = fvg['mid']
            ss = min(1.0, score / 8.0)
            sl_a = sl_m - ss * 0.5  # 强信号→紧止损
            tp_a = tp_m + ss * 0.5  # 强信号→远止盈
            
            if direction == 'long':
                entry_data['ep'] = round(ep, 4)
                entry_data['sl'] = round(ep - atr * max(0.5, sl_a), 4)
                entry_data['tp'] = round(ep + atr * max(1.0, tp_a), 4)
            else:
                entry_data['ep'] = round(ep, 4)
                entry_data['sl'] = round(ep + atr * max(0.5, sl_a), 4)
                entry_data['tp'] = round(ep - atr * max(1.0, tp_a), 4)
            
            results['loose'].append(entry_data)
            results['total'].append(entry_data)
        
        # 严格: score>=4.0, >=3 signals
        if score >= 3.5 and n_sig >= 3:
            atr = calc_atr(bars[:i+5])
            ep = fvg['mid']
            
            if direction == 'long':
                strict_entry = {**entry_data,
                    'ep': round(ep, 4),
                    'sl': round(ep - atr * max(1.0, sl_m * 0.8), 4),
                    'tp': round(ep + atr * max(1.5, tp_m * 1.2), 4),
                }
            else:
                strict_entry = {**entry_data,
                    'ep': round(ep, 4),
                    'sl': round(ep + atr * max(1.0, sl_m * 0.8), 4),
                    'tp': round(ep - atr * max(1.5, tp_m * 1.2), 4),
                }
            results['strict'].append(strict_entry)
            if strict_entry not in results['total']:
                results['total'].append(strict_entry)
    
    # 去重: 5根K线内同方向只保留score最高的
    for channel in ['loose', 'strict', 'total']:
        entries = results[channel]
        entries.sort(key=lambda e: -e.get('sc', 0))
        deduped = []
        for e in entries:
            if not any(abs(e['idx']-f['idx']) <= 5 and e['dir'] == f['dir'] for f in deduped):
                deduped.append(e)
        results[channel] = deduped
    
    return results


# ═══════════════════════════════════════════════
# 回测
# ═══════════════════════════════════════════════

def simulate_entry(entry, bars):
    """模拟一笔entry"""
    if not isinstance(entry, dict) or not isinstance(bars, list) or len(bars) < 5:
        return None
    ei = entry['idx']
    if ei >= len(bars):
        return None
    d = entry['dir']
    ep = entry['ep']
    sl = entry['sl']
    tp = entry['tp']
    sigs = entry.get('sigs', [])
    sc = entry.get('sc', 0)
    
    for j in range(ei, len(bars)):
        b = bars[j]
        if d == 'L':
            if b['l'] <= sl:
                return {'pnl':(sl-ep)/ep, 'reason':'sl', 'bars':j-ei+1, 'sig':sigs, 'sc':sc}
            if b['h'] >= tp:
                return {'pnl':(tp-ep)/ep, 'reason':'tp', 'bars':j-ei+1, 'sig':sigs, 'sc':sc}
        else:
            if b['h'] >= sl:
                return {'pnl':(ep-sl)/ep, 'reason':'sl', 'bars':j-ei+1, 'sig':sigs, 'sc':sc}
            if b['l'] <= tp:
                return {'pnl':(ep-tp)/ep, 'reason':'tp', 'bars':j-ei+1, 'sig':sigs, 'sc':sc}
    # EOD
    last = bars[-1]['c']
    pnl = (last-ep)/ep if d=='L' else (ep-last)/ep
    return {'pnl':pnl, 'reason':'eod', 'bars':len(bars)-ei+1, 'sig':sigs, 'sc':sc}


def backtest_v4(bars, mode='total', params=None):
    if bars is None or not isinstance(bars, list) or len(bars) < 60:
        return []
    if bars is None or len(bars) < 60:
        return []
    """
    V4 完整回测
    mode: 'loose' | 'strict' | 'total'
    """
    entries = detect_entries_v4(bars, params)
    result = entries.get(mode, [])
    if not result:
        return []
    if not isinstance(result, list):
        return []
    trades = []
    for e in result:
        t = simulate_entry(e, bars)
        if t:
            trades.append(t)
    return trades


def evaluate(trades, name='V4'):
    n = len(trades)
    if n == 0:
        print(f"  {name}: 0 trades")
        return {'n':0,'wr':0.0}
    wins = [t for t in trades if t['pnl']>0]
    losses = [t for t in trades if t['pnl']<=0]
    wr = len(wins)/n*100
    ret = sum(t['pnl'] for t in trades)*100
    pf = abs(sum(t['pnl'] for t in wins)/sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses)!=0 else 999
    avg = sum(t['pnl'] for t in trades)/n
    std = math.sqrt(sum((p['pnl']-avg)**2 for p in trades)/n) if n>1 else 0.001
    sr = (avg/std)*math.sqrt(252) if std>0 else 0
    
    print(f"  {name}: {n:>3}t WR={wr:>5.1f}% SR={sr:>5.2f} PF={pf:>4.1f} Ret={ret:>+.1f}%")
    
    # 信号分解
    sc = Counter()
    for t in trades:
        sn = len(t.get('sig',[]))
        sc[sn] += 1
    for cnt, freq in sc.most_common(3):
        print(f"    {cnt} sigs: {freq}t")
    
    return {'n':n, 'wr':round(wr,1), 'sr':round(sr,3), 'pf':round(pf,2), 'ret':round(ret,2)}


def compute_v4_score(trades):
    """
    V4评分: 侧重WR和PF, 同时考虑样本量
    """
    n = len(trades)
    if n < 3:
        return 0
    wins = [t for t in trades if t['pnl']>0]
    losses = [t for t in trades if t['pnl']<=0]
    wr = len(wins)/n*100
    pf = abs(sum(t['pnl'] for t in wins)/sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses)!=0 else 999
    avg_r = sum(t['pnl'] for t in trades)/n
    std = math.sqrt(sum((t['pnl']-avg_r)**2 for t in trades)/n) if n>1 else 0.001
    sr = (avg_r/std)*math.sqrt(252) if std>0 else 0
    
    # 评分: WR * PF * min(1, n/20)
    n_penalty = min(1.0, n/20) if n < 20 else 1.0
    pf_capped = min(5.0, pf)
    
    score = wr * 0.5 + sr * 10.0 + pf_capped * 5.0
    score *= n_penalty
    
    if pf < 1.0:
        score *= 0.2
    if wr < 40:
        score *= 0.5
    
    return round(score, 1)


# ═══════════════════════════════════════════════
# 直接运行
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    # 测试几只股票
    test_stocks = ['600519.SH','000001.SZ','000858.SZ','600036.SH',
                   '002594.SZ','300750.SZ','601318.SH','600887.SH',
                   '000002.SZ','600585.SH']
    
    print("="*70)
    print("  SMC Engine V4 — 多粒度共振")
    print("="*70)
    
    total_t = {'loose':[], 'strict':[], 'total':[]}
    
    for code in test_stocks:
        print(f"\n  {code}:")
        try:
            bars = get_klines(code, 'daily', 600)
            if len(bars) < 100:
                print(f"    Insufficient data ({len(bars)})")
                continue
            
            vol = get_volatility_profile(bars)
            params = get_adaptive_params(vol)
            print(f"    波动: {vol['vol_level']} ATR%={vol['atr_pct']}% 趋势={vol['trend_strength']}")
            print(f"    参数: th={params['fvg_threshold']} sc={params['score_threshold']} SL={params['sl_mult']} TP={params['tp_mult']}")
            
            for mode in ['loose', 'total', 'strict']:
                trades = backtest_v4(bars, mode)
                if mode == 'strict':
                    trades2 = backtest_v4(bars, 'strict')
                    r = evaluate(trades2, f'V4.{mode}')
                else:
                    r = evaluate(trades, f'V4.{mode}')
                total_t[mode].extend(trades)
        except Exception as e:
            import traceback
            print(f"    ERROR: {e}")
            traceback.print_exc()
    
    print(f"\n{'='*70}")
    print(f"  综合 (all stocks)")
    print(f"{'='*70}")
    for mode in ['loose', 'total', 'strict']:
        if total_t[mode]:
            evaluate(total_t[mode], f'V4.{mode}(all)')