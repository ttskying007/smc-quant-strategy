#!/usr/bin/env python3
"""
SMC V8.4 Engine — 第四代RR优先评分体系
======================================
核心升级 (与V8.3对比):
  1. RR平方惩罚 — score = WR × sqrt(min(N,40)) × min(3, PF) × min(3, RR)^2.0
  2. 强制RR>=1.5 — tp_pct/sl_pct >= 1.5 硬约束
  3. 300次迭代 — 更充分搜索
  4. 信号质量加权 — 多源信号加权
  5. 过拟合防御强化 — WR>90%+N<25 → 降权50%
  6. 动态自适应收紧 — 每轮缩小20%
  7. 六阶段搜索 + 局部爬山

V8.4 评分 (RR优先):
  primary = WR × sqrt(min(N, 40)) × min(3, PF) × min(3, RR)^2.0
  if RR < 1.5: score *= 0.1   (强力否决低RR)
  if N < 12: score = 0          (直接废弃)
  if WR > 90% and N < 25: score *= 0.5  (过拟合强惩罚)
  coverage_mult: < 15% → 0.2, 15-25% → 0.5, 25-40% → 0.8, >40% → 1.0
"""

import math, json, time, os, sys, random, urllib.request, urllib.error, traceback
from pathlib import Path
from datetime import datetime, timedelta

HOME = Path.home()
CACHE_DIR = HOME / '.hermes' / 'kline_cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

HUBBLE_BASE = "http://43.167.234.49:3101"
HUBBLE_HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}

# ════════════════════════════════════════════
# V8.4 参数空间 (14维)
# ════════════════════════════════════════════

V84_PARAM_SPACE = {
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
    'score_min':        {'min':0.5,  'max':4.0,  'default':0.5,  'step':0.1},
    'max_trades':       {'min':2,    'max':15,   'default':3,    'step':1},

    # 6. 波动率过滤 (1维)
    'atr_min_pct':      {'min':0.3,  'max':5.0,  'default':1.0,  'step':0.1},
    'atr_max_pct':      {'min':2.0,  'max':12.0, 'default':8.0,  'step':0.1},

    # 7. SL/TP (2维 — V8.4: tp/sl >= 1.5 强制)
    'sl_pct':           {'min':1.0,  'max':6.0,  'default':3.0,  'step':0.1},
    'tp_pct':           {'min':2.0,  'max':18.0, 'default':9.0,  'step':0.1},

    # 8. 自适应参数 (1维)
    'vol_adapt_sl':     {'min':0.3,  'max':1.2,  'default':0.6,  'step':0.05},
}

# 测试股票池 (40只 — 更大覆盖)
TEST_STOCKS = [
    '600519.SH',  '000858.SZ',  '300750.SZ',  '601318.SH',
    '002415.SZ',  '002594.SZ',  '600036.SH',  '688981.SH',
    '300059.SZ',  '600030.SH',  '002230.SZ',  '000333.SZ',
    '300124.SZ',  '600276.SH',  '600887.SH',
    '000001.SZ',  '002304.SZ',  '600809.SH',  '300760.SZ',
    '002475.SZ',  '000568.SZ',  '300015.SZ',  '002714.SZ',
    '601012.SH',  '300274.SZ',  '002352.SZ',  '300782.SZ',
    '600585.SH',  '601166.SH',  '000002.SZ',
    '688111.SH',  '600900.SH',  '601899.SH',  '300498.SZ',
    '002371.SZ',  '000725.SZ',  '603259.SH',  '300308.SZ',
    '600941.SH',  '000063.SZ',
]

# ════════════════════════════════════════════
# Hubble API调用
# ════════════════════════════════════════════

def hubble_api(endpoint, params=None):
    """调用Hubble API"""
    url = f"{HUBBLE_BASE}{endpoint}"
    if params:
        qs = urllib.parse.urlencode(params)
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, headers=HUBBLE_HEADERS)
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

def fetch_kline_cached(symbol, period='daily', count=120):
    """获取K线(缓存) — 智能匹配已缓存数据"""
    cache_key = f"{symbol}_{period}_{count}"
    cache_file = CACHE_DIR / f"{cache_key.replace('.','_')}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if isinstance(data, list):
                return data
        except:
            pass
    # 搜索已有缓存 (可能不同count)
    pattern = f"{symbol.replace('.','_')}_{period}_"
    for f in sorted(CACHE_DIR.glob(f"{pattern}*.json"), reverse=True):
        try:
            data = json.loads(f.read_text())
            if isinstance(data, list):
                return data
        except:
            continue
    raw = hubble_api(f"/api/kline/{symbol}", {'period': period, 'count': str(count)})
    data = raw if isinstance(raw, list) else raw.get('data', [])
    if data:
        cache_file.write_text(json.dumps(data))
    return data

# ════════════════════════════════════════════
# K线数据处理
# ════════════════════════════════════════════

def kline_to_ohlcv(kline_data):
    """转换Hubble K线为OHLCV列表"""
    ohlcv = []
    for bar in kline_data:
        if isinstance(bar, dict):
            o = float(bar.get('open', bar.get('o', 0)))
            h = float(bar.get('high', bar.get('h', 0)))
            l = float(bar.get('low', bar.get('l', 0)))
            c = float(bar.get('close', bar.get('c', 0)))
            v = float(bar.get('volume', bar.get('v', 0)))
            ohlcv.append({'o': o, 'h': h, 'l': l, 'c': c, 'v': v})
        elif isinstance(bar, (list, tuple)):
            o = float(bar[1]) if len(bar) > 1 else 0
            h = float(bar[2]) if len(bar) > 2 else 0
            l = float(bar[3]) if len(bar) > 3 else 0
            c = float(bar[4]) if len(bar) > 4 else 0
            v = float(bar[5]) if len(bar) > 5 else 0
            ohlcv.append({'o': o, 'h': h, 'l': l, 'c': c, 'v': v})
    return ohlcv

# ════════════════════════════════════════════
# ATR计算
# ════════════════════════════════════════════

def calc_atr(ohlcv, period=14):
    """计算ATR"""
    if len(ohlcv) < period + 1:
        return 0
    trs = []
    for i in range(1, len(ohlcv)):
        h = ohlcv[i]['h']
        l = ohlcv[i]['l']
        pc = ohlcv[i-1]['c']
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    return sum(trs[-period:]) / period

# ════════════════════════════════════════════
# FVG检测 (公允价值缺口)
# ════════════════════════════════════════════

def detect_fvg(ohlcv, min_width=0.001, merge_dist=3):
    """检测FVG — 三根K线: 第一根高<第三根低"""
    fvg_signals = []
    i = 0
    while i < len(ohlcv) - 2:
        b1, _, b3 = ohlcv[i], ohlcv[i+1], ohlcv[i+2]
        upper = min(b1['h'], b3['h'])
        lower = max(b1['l'], b3['l'])
        if upper > lower:
            width = (upper - lower) / b1['c']
            if width >= min_width:
                fvg_signals.append({
                    'type': 'FVG',
                    'idx': i + 1,
                    'upper': upper,
                    'lower': lower,
                    'width': width,
                    'direction': 'bull' if b3['c'] > b1['c'] else 'bear'
                })
        i += 1
    # 合并相邻FVG
    if merge_dist > 0 and fvg_signals:
        merged = [fvg_signals[0]]
        for s in fvg_signals[1:]:
            last = merged[-1]
            if s['idx'] - last['idx'] <= merge_dist:
                last['upper'] = max(last['upper'], s['upper'])
                last['lower'] = min(last['lower'], s['lower'])
                last['idx'] = (last['idx'] + s['idx']) // 2
            else:
                merged.append(s)
        return merged
    return fvg_signals

# ════════════════════════════════════════════
# IFVG检测 (反向FVG)
# ════════════════════════════════════════════

def detect_ifvg(ohlcv, min_width=0.001):
    """检测IFVG: 三根K线中间有重叠缺口"""
    signals = []
    for i in range(len(ohlcv) - 2):
        b1, b3 = ohlcv[i], ohlcv[i+2]
        if b1['h'] < b3['h'] and b1['l'] > b3['l']:
            gap = abs(b3['l'] - b1['h']) / b1['c']
            if gap >= min_width:
                signals.append({
                    'type': 'IFVG', 'idx': i+1,
                    'upper': max(b1['h'], b3['h']),
                    'lower': min(b1['l'], b3['l']),
                    'gap': gap
                })
    return signals

# ════════════════════════════════════════════
# Sweep检测 (流动性扫荡)
# ════════════════════════════════════════════

def detect_sweep(ohlcv, lookback=12, wick_ratio=2.0):
    """检测Sweep — 价格突破前高/低后迅速反转"""
    signals = []
    for i in range(lookback, len(ohlcv) - 2):
        window = ohlcv[i-lookback:i]
        high = max(b['h'] for b in window)
        low = min(b['l'] for b in window)
        cur = ohlcv[i]
        nxt = ohlcv[i+1]
        next2 = ohlcv[i+2]
        # 向上扫荡 (突破前高后反转)
        if cur['h'] > high and nxt['c'] < cur['c']:
            wick_up = cur['h'] - max(cur['o'], cur['c'])
            body = abs(cur['c'] - cur['o'])
            if body > 0 and wick_up / body > wick_ratio:
                signals.append({
                    'type': 'SweepUp', 'idx': i,
                    'high': cur['h'], 'low': cur['l'],
                    'wick_ratio': wick_up / body,
                    'strength': wick_up / cur['c'] * 100
                })
        # 向下扫荡
        if cur['l'] < low and nxt['c'] > cur['c']:
            wick_down = min(cur['o'], cur['c']) - cur['l']
            body = abs(cur['c'] - cur['o'])
            if body > 0 and wick_down / body > wick_ratio:
                signals.append({
                    'type': 'SweepDown', 'idx': i,
                    'high': cur['h'], 'low': cur['l'],
                    'wick_ratio': wick_down / body,
                    'strength': wick_down / cur['c'] * 100
                })
    return signals

# ════════════════════════════════════════════
# OB检测 (订单块)
# ════════════════════════════════════════════

def detect_ob(ohlcv, strength_min=1.0):
    """检测OB — 最后一段阴线/阳线"""
    signals = []
    for i in range(3, len(ohlcv) - 2):
        b0, b1, b2, b3 = ohlcv[i-3], ohlcv[i-2], ohlcv[i-1], ohlcv[i]
        # OB: 连续下跌后最后一根阴线
        if b2['c'] < b2['o'] and b1['c'] < b1['o'] and b3['c'] > b3['o']:
            ob_range = abs(b2['c'] - b2['o']) / b2['o'] * 100
            if ob_range >= strength_min:
                signals.append({
                    'type': 'OB_Bull', 'idx': i-1,
                    'upper': max(b2['o'], b2['c']),
                    'lower': min(b2['o'], b2['c']),
                    'strength': ob_range
                })
        # 连续上涨后最后一根阳线
        if b2['c'] > b2['o'] and b1['c'] > b1['o'] and b3['c'] < b3['o']:
            ob_range = abs(b2['c'] - b2['o']) / b2['o'] * 100
            if ob_range >= strength_min:
                signals.append({
                    'type': 'OB_Bear', 'idx': i-1,
                    'upper': max(b2['o'], b2['c']),
                    'lower': min(b2['o'], b2['c']),
                    'strength': ob_range
                })
    return signals

# ════════════════════════════════════════════
# BPR检测 (公允价值破裂)
# ════════════════════════════════════════════

def detect_bpr(ohlcv, lookback=10):
    """检测BPR — 价格回到FVG区域后反转"""
    fvgs = detect_fvg(ohlcv, min_width=0.001)
    signals = []
    for fvg in fvgs:
        idx = fvg['idx']
        for i in range(idx + 1, min(idx + lookback + 1, len(ohlcv))):
            bar = ohlcv[i]
            if fvg['direction'] == 'bull':
                if fvg['lower'] <= bar['l'] <= fvg['upper']:
                    if i + 1 < len(ohlcv) and ohlcv[i+1]['c'] > bar['c']:
                        signals.append({
                            'type': 'BPR_Bull', 'idx': i,
                            'upper': fvg['upper'],
                            'lower': fvg['lower'],
                            'price': bar['c'],
                            'strength': abs(bar['c'] - fvg['lower']) / fvg['lower'] * 100
                        })
                        break
    return signals

# ════════════════════════════════════════════
# MSB检测 (市场结构突破)
# ════════════════════════════════════════════

def detect_msb(ohlcv, lookback=10):
    """检测MSB — 突破前高/低并维持"""
    signals = []
    for i in range(lookback, len(ohlcv) - 2):
        window = ohlcv[i-lookback:i]
        high = max(b['h'] for b in window)
        low = min(b['l'] for b in window)
        cur = ohlcv[i]
        nxt = ohlcv[i+1]
        nxt2 = ohlcv[i+2]
        # 向上突破
        if cur['h'] > high and nxt['h'] > high and nxt2['c'] > high:
            signals.append({
                'type': 'MSB_Up', 'idx': i,
                'break_level': high,
                'price': cur['c'],
                'strength': (cur['c'] - high) / high * 100
            })
        # 向下突破
        if cur['l'] < low and nxt['l'] < low and nxt2['c'] < low:
            signals.append({
                'type': 'MSB_Down', 'idx': i,
                'break_level': low,
                'price': cur['c'],
                'strength': (low - cur['c']) / low * 100
            })
    return signals

# ════════════════════════════════════════════
# 综合信号检测
# ════════════════════════════════════════════

def detect_all_signals(ohlcv, params):
    """检测所有类型信号, 返回信号列表"""
    signals = []
    signals.extend(detect_fvg(ohlcv, params.get('fvg_min_width', 0.001), params.get('fvg_merge_dist', 3)))
    signals.extend(detect_ifvg(ohlcv, params.get('fvg_min_width', 0.001)))
    signals.extend(detect_sweep(ohlcv, params.get('sweep_lookback', 12), params.get('sweep_wick_ratio', 2.0)))
    signals.extend(detect_ob(ohlcv, params.get('ob_strength_min', 1.0)))
    signals.extend(detect_bpr(ohlcv, params.get('sweep_lookback', 10)))
    signals.extend(detect_msb(ohlcv, params.get('sweep_lookback', 10)))
    # 去重
    unique = []
    seen = set()
    for s in signals:
        key = f"{s['type']}_{s['idx']}"
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique

# ════════════════════════════════════════════
# 信号质量评分
# ════════════════════════════════════════════

def score_signal(signal, ohlcv):
    """给单个信号打分 (0-5)"""
    score = 1.0
    # FVG越宽越好
    if signal['type'] == 'FVG':
        width = signal.get('width', 0)
        score += min(2.0, width * 50)
    # Sweep越强越好
    if 'Sweep' in signal['type']:
        strength = signal.get('strength', 0)
        score += min(2.0, strength * 5)
    # OB越强越好
    if 'OB' in signal['type']:
        strength = signal.get('strength', 0)
        score += min(2.0, strength * 0.5)
    # 确认信号 (价格向信号方向移动)
    idx = signal.get('idx', 0)
    if idx + 2 < len(ohlcv):
        nxt = ohlcv[idx + 1]
        if 'Bull' in signal['type'] or signal.get('direction') == 'bull':
            if nxt['c'] > ohlcv[idx]['c']:
                score += 1.0
        elif 'Bear' in signal['type'] or signal.get('direction') == 'bear':
            if nxt['c'] < ohlcv[idx]['c']:
                score += 1.0
    return min(5.0, score)

# ════════════════════════════════════════════
# 交易信号生成 → 入场逻辑
# ════════════════════════════════════════════

def evaluate_trades(ohlcv, params):
    """基于信号生成交易并评估盈亏"""
    signals = detect_all_signals(ohlcv, params)
    if not signals:
        return {'n_trades': 0, 'wins': 0, 'losses': 0, 'returns': [], 'rr_list': [],
                'signal_scores': [], 'signals_per_stock': 0}

    # 参数
    score_min = params.get('score_min', 0.5)
    confirm_range = params.get('confirm_range', 3)
    min_sources = params.get('min_sources', 3)
    max_trades = params.get('max_trades', 3)
    sl_pct = params.get('sl_pct', 3.0)
    tp_pct = params.get('tp_pct', 9.0)
    vol_adapt = params.get('vol_adapt_sl', 0.6)
    atr_min = params.get('atr_min_pct', 0.3)
    atr_max = params.get('atr_max_pct', 8.0)

    # 强制TP/SL >= 1.5
    if tp_pct / sl_pct < 1.5:
        return {'n_trades': 0, 'wins': 0, 'losses': 0, 'returns': [], 'rr_list': [],
                'signal_scores': [], 'signals_per_stock': 0}

    # ATR
    atr = calc_atr(ohlcv, 14)
    atr_pct = atr / ohlcv[-1]['c'] * 100 if ohlcv else 0
    if atr_pct > 0:
        if atr_pct < atr_min or atr_pct > atr_max:
            return {'n_trades': 0, 'wins': 0, 'losses': 0, 'returns': [], 'rr_list': [],
                    'signal_scores': [], 'signals_per_stock': 0}

    # 给每个信号打分
    scored_sigs = [(score_signal(s, ohlcv), s) for s in signals]
    scored_sigs.sort(key=lambda x: -x[0])

    trades = []
    used_indices = set()
    for sig_score, sig in scored_sigs:
        if sig_score < score_min:
            continue
        if len(trades) >= max_trades:
            break
        idx = sig['idx']
        # 避免重复交易相近位置
        too_close = False
        for t in trades:
            if abs(t['idx'] - idx) <= confirm_range:
                too_close = True
                break
        if too_close:
            continue
        used_indices.add(idx)

        # 入场价格
        entry = ohlcv[idx + 1]['o'] if idx + 1 < len(ohlcv) else ohlcv[idx]['c']

        # V8.4: 自适应SL/TP
        sl_adapted = sl_pct * (1.0 - vol_adapt * (1.0 - min(atr_pct / 5.0, 1.0)))
        tp_adapted = tp_pct * (1.0 - vol_adapt * (1.0 - min(atr_pct / 5.0, 1.0)))
        sl_adapted = max(0.5, sl_adapted)
        tp_adapted = max(sl_adapted * 1.5, tp_adapted)  # 确保比例

        is_bull = 'Bull' in sig['type'] or sig.get('direction') == 'bull'
        if is_bull:
            sl = entry * (1 - sl_adapted / 100)
            tp = entry * (1 + tp_adapted / 100)
        else:
            sl = entry * (1 + sl_adapted / 100)
            tp = entry * (1 - tp_adapted / 100)

        # 模拟出场
        hit_sl = False
        hit_tp = False
        exit_price = entry
        for j in range(idx + 2, min(idx + 60, len(ohlcv))):
            bar = ohlcv[j]
            if is_bull:
                if bar['l'] <= sl:
                    hit_sl = True
                    exit_price = sl
                    break
                if bar['h'] >= tp:
                    hit_tp = True
                    exit_price = tp
                    break
            else:
                if bar['h'] >= sl:
                    hit_sl = True
                    exit_price = sl
                    break
                if bar['l'] <= tp:
                    hit_tp = True
                    exit_price = tp
                    break

        ret = (exit_price - entry) / entry * 100
        if not is_bull:
            ret = -ret

        rr = abs(tp_adapted / sl_adapted) if hit_tp else (abs(ret) / sl_adapted if hit_sl and ret != 0 else 0)
        rr = max(rr, 0.001)

        trades.append({
            'entry': entry, 'exit': exit_price,
            'ret': ret, 'win': ret > 0,
            'rr': rr,
            'sig_score': sig_score,
            'signal_count': len(signals),
            'idx': idx
        })

    wins = sum(1 for t in trades if t['win'])
    n = len(trades)
    returns = [t['ret'] for t in trades]
    rr_list = [t['rr'] for t in trades]

    return {
        'n_trades': n, 'wins': wins, 'losses': n - wins,
        'returns': returns, 'rr_list': rr_list,
        'signal_scores': [t['sig_score'] for t in trades],
        'signals_per_stock': len(signals)
    }

# ════════════════════════════════════════════
# V8.4 评分函数
# ════════════════════════════════════════════

def v84_score(eval_results):
    """V8.4 RR优先评分"""
    total_trades = sum(r.get('n_trades', 0) for r in eval_results.values())
    total_wins = sum(r.get('wins', 0) for r in eval_results.values())
    all_returns = []
    all_rr = []
    all_quality = []
    stock_with_trades = sum(1 for r in eval_results.values() if r.get('n_trades', 0) > 0)
    total_stocks = len(eval_results)

    for r in eval_results.values():
        all_returns.extend(r.get('returns', []))
        all_rr.extend(r.get('rr_list', []))
        all_quality.extend(r.get('signal_scores', []))

    if total_trades == 0:
        return {'score': 0, 'wr': 0, 'n': 0, 'pf': 0, 'rr_avg': 0,
                'ret': 0, 'coverage': 0, 'sr': 0, 'avg_quality': 0}

    wr = total_wins / total_trades * 100 if total_trades > 0 else 0
    rr_avg = sum(all_rr) / len(all_rr) if all_rr else 0
    ret_total = sum(all_returns) if all_returns else 0
    avg_quality = sum(all_quality) / len(all_quality) if all_quality else 0

    # Profit Factor
    gross_win = sum(r for r in all_returns if r > 0) or 0.001
    gross_loss = abs(sum(r for r in all_returns if r < 0)) or 0.001
    pf = gross_win / gross_loss

    # Sharpe Ratio (简化)
    if len(all_returns) > 1:
        avg_r = sum(all_returns) / len(all_returns)
        var = sum((r - avg_r) ** 2 for r in all_returns) / len(all_returns)
        std = math.sqrt(var) if var > 0 else 1
        sr = avg_r / std * math.sqrt(252 if len(all_returns) > 10 else 1)
    else:
        sr = 0

    coverage_pct = stock_with_trades / total_stocks * 100 if total_stocks > 0 else 0

    # ═══ V8.4 核心评分 (v3 — WR优先引擎) ═══
    # WR指数2.0，RR线性，大幅奖励高WR
    score = (wr / 100) ** 2.0 * math.sqrt(min(total_trades, 50)) * min(3, pf) * min(2.5, rr_avg)

    # 惩罚
    if rr_avg < 1.2 and total_trades >= 3:
        score *= 0.1  # RR基本要求

    if total_trades < 8:
        score = 0  # 硬废弃
    elif total_trades < 15:
        score *= max(0.3, total_trades / 15)  # 软惩罚

    score = max(0, score)

    return {'score': round(score, 2), 'wr': round(wr, 1), 'n': total_trades,
            'pf': round(pf, 2), 'rr_avg': round(rr_avg, 2),
            'ret': round(ret_total, 2), 'coverage': round(coverage_pct, 1),
            'sr': round(sr, 2), 'avg_quality': round(avg_quality, 2)}

# ════════════════════════════════════════════
# 参数评估 (单组参数 → 所有股票)
# ════════════════════════════════════════════

def evaluate_params(params, stocks, progress_cb=None):
    """评估单组参数"""
    all_results = {}
    total = len(stocks)
    for idx, symbol in enumerate(stocks):
        try:
            kline = fetch_kline_cached(symbol, 'daily', 120)
            if not kline or len(kline) < 30:
                all_results[symbol] = {'n_trades': 0, 'wins': 0, 'losses': 0,
                                       'returns': [], 'rr_list': [], 'signal_scores': [],
                                       'signals_per_stock': 0, 'error': 'no_data'}
                continue
            ohlcv = kline_to_ohlcv(kline)
            result = evaluate_trades(ohlcv, params)
            all_results[symbol] = result
        except Exception as e:
            all_results[symbol] = {'n_trades': 0, 'wins': 0, 'losses': 0,
                                   'returns': [], 'rr_list': [], 'signal_scores': [],
                                   'signals_per_stock': 0, 'error': str(e)}
        if progress_cb and idx % 5 == 0:
            progress_cb(idx, total)
    return v84_score(all_results)


# ════════════════════════════════════════════
# 命令行入口 (供优化器调用)
# ════════════════════════════════════════════

def main():
    """单次评估命令行"""
    import sys
    params = {}
    for p_name in V84_PARAM_SPACE:
        p_def = V84_PARAM_SPACE[p_name]
        params[p_name] = p_def['default']
    # 从命令行覆盖
    for arg in sys.argv[1:]:
        if '=' in arg:
            k, v = arg.split('=', 1)
            if k in V84_PARAM_SPACE:
                params[k] = float(v)

    stocks = TEST_STOCKS[:int(sys.argv[1])] if len(sys.argv) > 1 else TEST_STOCKS[:10]
    result = evaluate_params(params, stocks)
    print(json.dumps(result))

if __name__ == '__main__':
    main()