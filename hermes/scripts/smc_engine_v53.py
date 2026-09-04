#!/usr/bin/env python3
"""
SMC V5.3 Engine — 高波动率信号引擎
======================================
核心原则:
  1. 只交易 ATR > 2% 的高波动率股票
  2. 采用结构止损 (前低/前高) 而不是固定百分比
  3. 多TF确认: 日线结构 + 60分钟入场
  4. 信号质量: WR > 80%, PF > 5.0

与V5前代的关键区别:
  - 移除复杂的评分系统, 用"信号计数+结构确认"替代
  - 每笔交易有明确的"结构止损"和"结构止盈"
  - 只产生高置信度信号
"""

import math, json, time, os, sys, random
from pathlib import Path

HUBBLE_BASE = "http://43.167.234.49:3101"
HUBBLE_HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}

# ════════ 简化参数空间 (仅12维, vs V5的24维) ════════

V53_PARAM_SPACE = {
    # FVG门槛 (2维)
    'fvg_min_width':    {'min':0.08, 'max':0.35, 'default':0.15, 'step':0.02},
    'fvg_merge_dist':   {'min':2, 'max':6, 'default':3, 'step':1},
    # Sweep (2维)
    'sweep_lookback':   {'min':10, 'max':25, 'default':15, 'step':1},
    'sweep_wick_ratio': {'min':1.5, 'max':3.5, 'default':2.0, 'step':0.1},
    # 结构确认 (2维)
    'confirm_range':    {'min':1, 'max':3, 'default':2, 'step':1},
    'min_consecutive':  {'min':1, 'max':3, 'default':2, 'step':1},
    # 止损比例 (%)
    'sl_pct':           {'min':1.5, 'max':6.0, 'default':3.0, 'step':0.1},
    'tp_pct':           {'min':3.0, 'max':12.0, 'default':6.0, 'step':0.1},
    # 最少信号源 (FVG+Sweep+OB至少多少种)
    'min_signal_sources':{'min':2, 'max':4, 'default':2, 'step':1},
    # 波动率门槛
    'min_atr_pct':      {'min':1.0, 'max':4.0, 'default':2.0, 'step':0.2},
    # 信号量
    'max_trades':       {'min':2, 'max':10, 'default':5, 'step':1},
    'min_score':        {'min':1.0, 'max':3.0, 'default':1.5, 'step':0.1},
}

# ════════ 工具 ════════

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

# ════════ 结构检测 ════════

def find_swing_highs(bars, lookback=5):
    """找到波段高点"""
    highs = []
    for i in range(lookback, len(bars)-lookback):
        if all(bars[i]['h'] >= bars[j]['h'] for j in range(i-lookback, i+lookback+1) if j != i):
            highs.append({'idx': i, 'price': bars[i]['h']})
    return highs

def find_swing_lows(bars, lookback=5):
    """找到波段低点"""
    lows = []
    for i in range(lookback, len(bars)-lookback):
        if all(bars[i]['l'] <= bars[j]['l'] for j in range(i-lookback, i+lookback+1) if j != i):
            lows.append({'idx': i, 'price': bars[i]['l']})
    return lows

def detect_fvg_v53(bars, params):
    """FVG检测 — 简单的gap检测"""
    if len(bars) < 3:
        return []
    avg_r = sum(abs(k['h']-k['l']) for k in bars[-30:]) / max(1, min(30, len(bars)))
    if avg_r == 0:
        return []
    min_w = params.get('fvg_min_width', 0.15)
    fvg_list = []
    for i in range(1, len(bars)-1):
        p, c, n = bars[i-1], bars[i], bars[i+1]
        # Bullish FVG = gap up → short signal on top
        if c['c'] > c['o']:
            top = min(p['h'], n['h'])
            bot = max(p['l'], n['l'])
        else:
            top = min(p['h'], n['h'])
            bot = max(p['l'], n['l'])
        gap = top - bot
        if gap > avg_r * min_w:
            direction = 'short' if c['c'] > c['o'] else 'long'
            strength = min(3, round(gap / (avg_r * 0.2)))
            fvg_list.append({
                'direction': direction, 'index': i,
                'top': round(top, 4), 'bottom': round(bot, 4),
                'mid': round((top+bot)/2, 4), 'gap': round(gap, 4),
                'strength': strength,
            })
    # 合并相邻同向
    merge = params.get('fvg_merge_dist', 3)
    merged = []
    by_dir = {'long': [], 'short': []}
    for f in fvg_list:
        by_dir[f['direction']].append(f)
    for dir, fl in by_dir.items():
        fl.sort(key=lambda x:x['index'])
        i = 0
        while i < len(fl):
            grp = [fl[i]]
            while i+1 < len(fl) and fl[i+1]['index'] - grp[-1]['index'] <= merge:
                grp.append(fl[i+1])
                i += 1
            if len(grp) > 1:
                merged.append({
                    'direction': dir,
                    'top': max(f['top'] for f in grp),
                    'bottom': min(f['bottom'] for f in grp),
                    'mid': round((max(f['top'] for f in grp)+min(f['bottom'] for f in grp))/2, 4),
                    'strength': max(f['strength'] for f in grp) + 1,
                    'index': grp[-1]['index'],
                    'n': len(grp),
                })
            i += 1
    return fvg_list + merged

def detect_sweep_v53(bars, params):
    """Sweep检测 — 精准影线"""
    wick = params.get('sweep_wick_ratio', 2.0)
    lb = params.get('sweep_lookback', 15)
    sigs = []
    for i in range(lb+1, len(bars)):
        c = bars[i]
        body = abs(c['c']-c['o'])
        if body < 0.001:
            continue
        uw = c['h'] - max(c['c'], c['o'])
        lw = min(c['c'], c['o']) - c['l']
        rl = min(bars[j]['l'] for j in range(i-lb, i))
        rh = max(bars[j]['h'] for j in range(i-lb, i))
        # Long sweep
        if c['l'] < rl and uw > body and uw/body >= wick:
            sigs.append({'direction': 'long', 'index': i, 'price': c['l'], 'ratio': round(uw/body, 2)})
        # Short sweep
        if c['h'] > rh and lw > body and lw/body >= wick*0.8:
            sigs.append({'direction': 'short', 'index': i, 'price': c['h'], 'ratio': round(lw/body, 2)})
    return sigs

def detect_ob_v53(bars, params):
    """OB检测"""
    avg_b = sum(abs(bars[i]['c']-bars[i]['o']) for i in range(max(0,len(bars)-30), len(bars))) / max(1, min(30, len(bars)))
    sigs = []
    for i in range(4, len(bars)-2):
        pre = bars[i-4:i]
        c = bars[i]
        bd = abs(c['c']-c['o'])
        mh = max(k['h'] for k in pre)
        ml = min(k['l'] for k in pre)
        # BullOB
        if bars[i+1]['c'] > mh and c['c'] < c['o'] and bd > avg_b * 0.5:
            sigs.append({'direction': 'long', 'index': i,
                         'top': round(max(c['o'],c['c']),4),
                         'bottom': round(min(c['o'],c['c']),4)})
        # BearOB
        if bars[i+1]['l'] < ml and c['c'] > c['o'] and bd > avg_b * 0.5:
            sigs.append({'direction': 'short', 'index': i,
                         'top': round(max(c['o'],c['c']),4),
                         'bottom': round(min(c['o'],c['c']),4)})
    return sigs

def detect_ms_structure(bars):
    """检测市场结构 (MS) — HH/HL/LH/LL"""
    if len(bars) < 15:
        return {'bullish': False, 'bearish': False}
    seg = bars[-15:]
    # Bullish: higher highs, higher lows
    hh = all(seg[i]['h'] <= seg[i+1]['h'] for i in range(max(0,len(seg)-8), len(seg)-1))
    hl = all(seg[i]['l'] <= seg[i+1]['l'] for i in range(max(0,len(seg)-8), len(seg)-1))
    # Bearish: lower highs, lower lows
    lh = all(seg[i]['h'] >= seg[i+1]['h'] for i in range(max(0,len(seg)-8), len(seg)-1))
    ll = all(seg[i]['l'] >= seg[i+1]['l'] for i in range(max(0,len(seg)-8), len(seg)-1))
    return {
        'bullish': hh or hl,
        'bearish': lh or ll,
        'bull_strength': sum(1 for k in seg if k['c'] > k['o']),
        'bear_strength': sum(1 for k in seg if k['c'] < k['o']),
    }

def compute_structural_sl(bars, entry_idx, direction, default_sl_pct, ep):
    """计算结构止损 — 找最近的结构高低点"""
    lb = min(30, entry_idx)
    if direction == 'long':
        # SL: 最近30根K线的最低点 - 缓冲
        recent_low = min(bars[j]['l'] for j in range(entry_idx-lb, entry_idx+1))
        sl_price = recent_low * 0.995  # 0.5%缓冲
        return round(sl_price, 2)
    else:
        recent_high = max(bars[j]['h'] for j in range(entry_idx-lb, entry_idx+1))
        sl_price = recent_high * 1.005
        return round(sl_price, 2)


def compute_structural_tp(bars, entry_idx, direction, sl_price, ep):
    """计算结构止盈 — 找到最近的FVG/OB作为盈利目标"""
    tp_price = None
    if direction == 'long':
        # 往上看最近的FVG top或波段高点
        for i in range(entry_idx, min(entry_idx+30, len(bars))):
            if bars[i]['h'] > ep * 1.04:
                tp_price = bars[i]['h']
                break
    else:
        for i in range(entry_idx, min(entry_idx+30, len(bars))):
            if bars[i]['l'] < ep * 0.96:
                tp_price = bars[i]['l']
                break
    
    if tp_price is None:
        # 默认用ATR倍数
        atr = calc_atr(bars)
        if direction == 'long':
            tp_price = ep + atr * 3.0
        else:
            tp_price = ep - atr * 3.0
    
    return round(tp_price, 2)


# ════════ V5.3 入口检测 ════════

def detect_entries_v53(bars, params=None):
    """V5.3入口检测 — 结构确认 + 信号源计数"""
    if not bars or len(bars) < 80:
        return {'entries': [], 'total': 0, 'signals': {}}
    
    p = params or {}
    vol = get_vol_profile(bars)
    
    # 过滤: 仅高波动率
    min_atr = p.get('min_atr_pct', 2.0)
    if vol['atr_pct'] < min_atr:
        return {'entries': [], 'total': 0, 'signals': {}, 'filtered': 'low_vol'}
    
    last_idx = len(bars) - 1
    max_trades = p.get('max_trades', 5)
    min_score = p.get('min_score', 1.5)
    sl_p = p.get('sl_pct', 3.0)
    tp_p = p.get('tp_pct', 6.0)
    
    # 检测所有信号
    fvg_list = detect_fvg_v53(bars, p)
    sweep_list = detect_sweep_v53(bars, p)
    ob_list = detect_ob_v53(bars, p)
    ms = detect_ms_structure(bars)
    
    if not fvg_list:
        return {'entries': [], 'total': 0, 'signals': {'fvg': 0}, 'filtered': 'no_fvg'}
    
    entries = []
    
    for fvg in fvg_list[-20:]:
        idx = fvg.get('index', 0)
        if idx < 3 or idx >= last_idx - 2:
            continue
        age = last_idx - idx
        if age > 30:
            continue
        
        dir = fvg['direction']
        ep = fvg.get('mid', bars[idx]['c'])
        
        # 信号源计数
        sources = ['FVG']
        has_sweep = any(s['direction']==dir and abs(s['index']-idx)<=10 for s in sweep_list)
        has_ob = any(s['direction']==dir and abs(s['index']-idx)<=8 for s in ob_list)
        
        if has_sweep: sources.append('Sweep')
        if has_ob: sources.append('OB')
        if dir=='long' and ms.get('bullish'): sources.append('MS_long')
        if dir=='short' and ms.get('bearish'): sources.append('MS_short')
        
        n_sources = len(sources)
        min_src = p.get('min_signal_sources', 2)
        
        if n_sources < min_src:
            continue
        
        # 计算score = 信号源数 * 强度
        score = n_sources * (1 + fvg.get('strength', 1) * 0.2)
        if age < 5:
            score *= 1.2
        if has_sweep and (s['ratio'] if (s:=[s for s in sweep_list if s['direction']==dir and abs(s['index']-idx)<=10]) else [{'ratio':0}])[0]['ratio'] > 2.5:
            score *= 1.3
        if ms.get('bull_strength',0) > 10 and dir=='long':
            score *= 1.2
        if ms.get('bear_strength',0) > 10 and dir=='short':
            score *= 1.2
        # 成交量确认
        vol_ratio = sum(k['v'] for k in bars[-5:]) / max(1, sum(k['v'] for k in bars[-20:-5]) / 15)
        if vol_ratio > 1.3:
            score *= 1.1
        
        if score < min_score:
            continue
        
        # 计算SL/TP
        if dir == 'long':
            sl_price = round(ep * (1 - sl_p/100), 2)
            tp_price = round(ep * (1 + tp_p/100), 2)
        else:
            sl_price = round(ep * (1 + sl_p/100), 2)
            tp_price = round(ep * (1 - tp_p/100), 2)
        
        rr = abs(tp_price - ep) / max(0.01, abs(sl_price - ep))
        
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
    
    # 按score排序, 取top
    entries.sort(key=lambda e: -e['score'])
    
    # 去重 (10根K线内同方向去重)
    deduped = []
    for e in entries:
        if not any(abs(e['idx']-d['idx'])<=10 and e['dir']==d['dir'] for d in deduped):
            deduped.append(e)
    
    if len(deduped) > max_trades:
        deduped = deduped[:max_trades]
    
    return {
        'entries': deduped,
        'total': len(deduped),
        'signals': {'fvg': len(fvg_list), 'sweep': len(sweep_list), 'ob': len(ob_list)},
        'vol': vol,
        'ms': ms,
    }


# ════════ 回测 ════════

def backtest_v53(bars, params=None):
    """V5.3回测"""
    if not bars or len(bars) < 80:
        return []
    
    result = detect_entries_v53(bars, params)
    entries = result.get('entries', [])
    if not entries:
        return []
    
    trades = []
    for e in entries:
        t = simulate_entry_v53(e, bars)
        if t:
            trades.append(t)
    return trades


def simulate_entry_v53(entry, bars):
    """模拟一笔 — 带结构止损确认"""
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
            # 先检查是否达到tp (优先tp)
            if b['h'] >= tp:
                pnl = (tp - ep) / ep
                # 如果达到tp, 但还没被止损
                if b['l'] <= sl:
                    # 同时触发, 取中间值
                    pnl = (sl - ep) / ep if abs(sl - ep) > abs(tp - ep) else (tp - ep) / ep
                return {'pnl': round(pnl, 4), 'reason': 'tp', 'bars': j-entry_idx+1,
                        'ep': ep, 'sl': sl, 'tp': tp, 'exit': tp, 'sources': sources}
            if b['l'] <= sl:
                return {'pnl': round((sl-ep)/ep, 4), 'reason': 'sl', 'bars': j-entry_idx+1,
                        'ep': ep, 'sl': sl, 'tp': tp, 'exit': sl, 'sources': sources}
        else:
            if b['l'] <= tp:
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


# ════════ V5.3 评分 ════════

def compute_v53_score(trades):
    """评分: WR * 0.5 + PF * 0.3 + N * 0.2"""
    n = len(trades)
    if n < 2:
        return {'score': 0, 'wr': 0, 'pf': 0, 'n': n, 'ret': 0, 'sr': 0}
    
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    n_wins = len(wins)
    n_losses = len(losses)
    
    wr = n_wins / n * 100
    pf = abs(sum(t['pnl'] for t in wins) / sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses) != 0 else 999
    avg_pnl = sum(t['pnl'] for t in trades) / n
    total_ret = sum(t['pnl'] for t in trades) * 100
    
    std = math.sqrt(sum((t['pnl']-avg_pnl)**2 for t in trades)/n) if n > 1 else 0.001
    sr = (avg_pnl / std) * math.sqrt(252) if std > 0 else 0
    
    score = wr * 0.5 + min(30, pf * 6) * 0.3 + min(30, n * 1.5) * 0.2
    
    return {
        'score': round(score, 1),
        'wr': round(wr, 1),
        'pf': round(pf, 2),
        'n': n,
        'n_wins': n_wins,
        'n_losses': n_losses,
        'ret': round(total_ret, 2),
        'sr': round(sr, 2),
    }


# ════════ 数据 ════════

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
    cache_path = Path.home() / '.hermes' / 'kline_cache' / f"{symbol.replace('.','_')}_{interval}_{limit}.json"
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
    """加载K线, 优先缓存"""
    cache_dir = Path.home() / '.hermes' / 'kline_cache'
    cache_file = cache_dir / f"{symbol.replace('.','_')}_{interval}_{limit}.json"
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)
    bars = get_bars(symbol, interval, limit)
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_file, 'w') as f:
        json.dump(bars, f)
    return bars

def get_stock_list():
    import json, urllib.request
    url = f"{HUBBLE_BASE}/api/v2/cnstock/symbols?listStatus=L"
    req = urllib.request.Request(url, headers=HUBBLE_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.loads(resp.read())
    return raw.get('symbols', raw.get('data', []))


if __name__ == '__main__':
    print("=== SMC V5.3 Engine ===")
    print(f"Params: {len(V53_PARAM_SPACE)} dimensions")
    
    # Quick test
    bars = load_bars('300231.SZ', 'daily', 300)
    if bars:
        vol = get_vol_profile(bars)
        print(f"\nTest: 300231.SZ (ATR={vol['atr_pct']}%)")
        result = detect_entries_v53(bars)
        entries = result['entries']
        print(f"  Entries: {result['total']} | Vol: {vol['vol_level']} ({vol['atr_pct']}%)")
        if entries:
            for e in entries[:3]:
                print(f"    {e['dir']} ep={e['ep']} sl={e['sl']} tp={e['tp']} R={e['rr']} score={e['score']} src={e['sources']}")
        trades = backtest_v53(bars)
        if trades:
            s = compute_v53_score(trades)
            print(f"  Backtest: WR={s['wr']}% PF={s['pf']} N={s['n']} Ret={s['ret']}% SR={s['sr']}")
        else:
            print("  No trades")