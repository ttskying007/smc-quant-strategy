#!/usr/bin/env python3
"""
SMC V5.4 Engine — 分层自适应引擎
==================================
核心改进:
  1. 高波动(ATR≥2%)和低波动(<2%)分别优化参数
  2. 结构止损: 基于前低/前高, 而非固定% (适配市场)
  3. 动态参数: 根据最近20根K线的波动率自动调整
  4. 评分系统: 信号源数 * 结构强度 * 成交量确认

关键升级:
  - 从"固定参数" → "波动率自适应参数"
  - 从"百分比止损" → "结构止损+移动止损"
  - 从"单指标" → "信号源计数+结构评分"
"""

import math, json, time, os, sys
from pathlib import Path

HUBBLE_BASE = "http://43.167.234.49:3101"
HUBBLE_HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}

# ════════ 自适应参数 (波动率分层) ════════

def get_adaptive_params(atr_pct, preset='balanced'):
    """根据波动率动态生成参数"""
    if atr_pct >= 3.0:  # 高波动
        return {
            'fvg_min_width': 0.32,      # 高波动需要大FVG
            'fvg_merge_dist': 2,
            'sweep_lookback': 20,
            'sweep_wick_ratio': 2.5,
            'confirm_range': 2,
            'min_consecutive': 1,
            'sl_pct': 2.0,              # 高波动收紧止损
            'tp_pct': 4.0,
            'min_signal_sources': 1,
            'max_trades': 6,
            'min_score': 1.2,
            'trail_sl': True,
            'trail_activation': 0.5,    # 盈利50%后移动止损
        }
    elif atr_pct >= 2.0:  # 中波动
        return {
            'fvg_min_width': 0.25,
            'fvg_merge_dist': 3,
            'sweep_lookback': 15,
            'sweep_wick_ratio': 2.0,
            'confirm_range': 2,
            'min_consecutive': 2,
            'sl_pct': 2.5,
            'tp_pct': 5.0,
            'min_signal_sources': 1,
            'max_trades': 5,
            'min_score': 1.0,
            'trail_sl': True,
            'trail_activation': 0.3,
        }
    else:  # 低波动
        return {
            'fvg_min_width': 0.15,      # 低波动用小FVG
            'fvg_merge_dist': 3,
            'sweep_lookback': 12,
            'sweep_wick_ratio': 1.8,
            'confirm_range': 3,
            'min_consecutive': 2,
            'sl_pct': 2.0,              # 低波动也需要控制风险
            'tp_pct': 4.0,
            'min_signal_sources': 1,
            'max_trades': 5,
            'min_score': 0.8,
            'trail_sl': True,
            'trail_activation': 0.2,
        }


# ════════ 工具函数 ════════

def calc_atr(klines, period=14):
    if len(klines) < period+1:
        return 0
    if len(klines) < period+2:
        return abs(klines[-1]['h']-klines[-1]['l'])
    trs = []
    for i in range(1, min(period+1, len(klines))):
        tr = max(klines[-i]['h']-klines[-i]['l'],
                 abs(klines[-i]['h']-klines[-i-1]['c']),
                 abs(klines[-i]['l']-klines[-i-1]['c']))
        trs.append(tr)
    return sum(trs)/len(trs) if trs else 0

def get_vol_profile(bars):
    if len(bars) < 30:
        return {'atr_pct': 0, 'vol_level': 'unknown', 'trend': 0, 'atr': 0}
    atr = calc_atr(bars)
    avg_price = sum((bars[i]['h']+bars[i]['l'])/2 for i in range(-20, 0)) / 20 if len(bars) >= 20 else sum((b['h']+b['l'])/2 for b in bars)/len(bars)
    atr_pct = atr / avg_price * 100 if avg_price > 0 else 0
    
    if atr_pct >= 3.0: vol_level = 'high'
    elif atr_pct >= 1.5: vol_level = 'medium'
    else: vol_level = 'low'
    
    recent = bars[-20:]
    ups = sum(1 for k in recent if k['c'] > k['o'])
    trend = abs(ups - len(recent)/2) / len(recent) * 2 if len(recent) >= 2 else 0
    
    return {'atr_pct': round(atr_pct, 2), 'vol_level': vol_level, 'trend': round(trend, 3), 'atr': round(atr, 4)}

# ════════ 信号检测 (核心) ════════

def detect_fvg(bars, min_width):
    """FVG检测 — 三根K线gap"""
    if len(bars) < 3: return []
    avg_r = sum(abs(k['h']-k['l']) for k in bars[-30:]) / max(1, min(30, len(bars)))
    if avg_r < 0.001: return []
    fvgs = []
    for i in range(1, len(bars)-1):
        p, c, n = bars[i-1], bars[i], bars[i+1]
        top = min(p['h'], n['h'])
        bot = max(p['l'], n['l'])
        gap = top - bot
        if gap > avg_r * min_width:
            dir = 'short' if c['c'] > c['o'] else 'long'
            strength = min(5, round(gap / (avg_r * 0.15), 1))
            fvgs.append({
                'dir': dir, 'index': i,
                'top': round(top, 4), 'bottom': round(bot, 4),
                'mid': round((top+bot)/2, 4),
                'gap': round(gap, 4), 'strength': strength,
            })
    return fvgs

def detect_sweep(bars, lookback=15, wick_ratio=2.0):
    """Sweep检测 — 影线突破前高/前低"""
    if len(bars) < lookback+2: return []
    sigs = []
    for i in range(lookback+1, len(bars)):
        c = bars[i]
        body = abs(c['c']-c['o'])
        if body < 0.001: continue
        uw = c['h'] - max(c['c'], c['o'])
        lw = min(c['c'], c['o']) - c['l']
        rl = min(bars[j]['l'] for j in range(i-lookback, i))
        rh = max(bars[j]['h'] for j in range(i-lookback, i))
        if c['l'] < rl and uw > body * wick_ratio * 0.5:
            sigs.append({'dir': 'long', 'index': i, 'price': c['l'], 'ratio': round(uw/body, 2) if body > 0 else 99})
        if c['h'] > rh and lw > body * wick_ratio * 0.4:
            sigs.append({'dir': 'short', 'index': i, 'price': c['h'], 'ratio': round(lw/body, 2) if body > 0 else 99})
    return sigs

def detect_ob(bars):
    """OB检测 — 大实体后确认"""
    if len(bars) < 7: return []
    avg_b = sum(abs(bars[i]['c']-bars[i]['o']) for i in range(max(0,len(bars)-30), len(bars))) / max(1, min(30, len(bars)))
    sigs = []
    for i in range(4, len(bars)-2):
        pre = bars[i-4:i]
        c = bars[i]
        bd = abs(c['c']-c['o'])
        mh = max(k['h'] for k in pre)
        ml = min(k['l'] for k in pre)
        if bars[i+1]['c'] > mh and c['c'] < c['o'] and bd > avg_b * 0.4:
            sigs.append({'dir': 'long', 'index': i, 'top': round(max(c['o'],c['c']),4), 'bottom': round(min(c['o'],c['c']),4)})
        if bars[i+1]['l'] < ml and c['c'] > c['o'] and bd > avg_b * 0.4:
            sigs.append({'dir': 'short', 'index': i, 'top': round(max(c['o'],c['c']),4), 'bottom': round(min(c['o'],c['c']),4)})
    return sigs

def detect_cho_choch(bars):
    """CHoCH检测 — 趋势反转"""
    if len(bars) < 20: return {'cho': False, 'choch': False, 'bull': 0, 'bear': 0}
    seg = bars[-15:]
    # 找波段
    mids = [(b['h']+b['l'])/2 for b in seg]
    n = len(mids)
    # 简单: 连续3根上涨后跌 = bear, 连续3根下跌后涨 = bull
    ups = sum(1 for i in range(max(0,n-10), n-1) if seg[i]['c'] < seg[i+1]['c'])
    downs = sum(1 for i in range(max(0,n-10), n-1) if seg[i]['c'] > seg[i+1]['c'])
    last_3_up = all(seg[i]['c'] < seg[i+1]['c'] for i in range(max(0,n-4), n-1))
    last_3_dn = all(seg[i]['c'] > seg[i+1]['c'] for i in range(max(0,n-4), n-1))
    return {
        'cho': last_3_up or last_3_dn,
        'choch': (last_3_up and seg[-1]['c'] > seg[-2]['h']) or (last_3_dn and seg[-1]['c'] < seg[-2]['l']),
        'bull': ups / max(1, ups+downs) * 100,
        'bear': downs / max(1, ups+downs) * 100,
    }


# ════════ 结构止损计算 ════════

def compute_swing_sl_tp(bars, entry_idx, direction, ep, atr):
    """用波段结构计算止损止盈"""
    lb = min(20, entry_idx)
    
    if direction == 'L':  # long: 止损在最近低点下方
        recent_low = min(bars[j]['l'] for j in range(entry_idx-lb, entry_idx+1))
        sl_price = recent_low * 0.998  # 0.2%缓冲
        # TP: ATR * 2.0 或最近前高
        recent_high = max(bars[j]['h'] for j in range(entry_idx-lb, entry_idx+1))
        tp_price = max(ep * 1.04, recent_high)
    else:
        recent_high = max(bars[j]['h'] for j in range(entry_idx-lb, entry_idx+1))
        sl_price = recent_high * 1.002
        recent_low = min(bars[j]['l'] for j in range(entry_idx-lb, entry_idx+1))
        tp_price = min(ep * 0.96, recent_low)
    
    return round(sl_price, 2), round(tp_price, 2)


# ════════ V5.4 入口检测 ════════

def detect_entries_v54(bars, params=None):
    """
    V5.4主入口检测:
    1. 获取波动率 → 自适应参数
    2. 检测FVG+Sweep+OB+CHoCH
    3. 信号计数 + 结构评分
    4. 结构止损/止盈
    """
    if not bars or len(bars) < 60:
        return {'entries': [], 'total': 0}
    
    vol = get_vol_profile(bars)
    atr_pct = vol['atr_pct']
    
    # 自适应参数 (允许外部覆盖)
    if params:
        ap = params.copy()
        for k in ['fvg_min_width','sweep_lookback','sweep_wick_ratio']:
            if k not in ap:
                ap[k] = get_adaptive_params(atr_pct).get(k)
        for k in ['sl_pct','tp_pct','max_trades','min_score','min_signal_sources']:
            if k not in ap:
                ap[k] = get_adaptive_params(atr_pct).get(k)
        for k in ['trail_sl','trail_activation','min_consecutive','confirm_range']:
            if k not in ap:
                ap[k] = get_adaptive_params(atr_pct).get(k)
    else:
        ap = get_adaptive_params(atr_pct)
    
    # 检测所有信号
    fvg_list = detect_fvg(bars, ap.get('fvg_min_width', 0.25))
    sweep_list = detect_sweep(bars, ap.get('sweep_lookback', 15), ap.get('sweep_wick_ratio', 2.0))
    ob_list = detect_ob(bars)
    choch = detect_cho_choch(bars)
    
    if not fvg_list and not sweep_list:
        return {'entries': [], 'total': 0, 'signals': {'fvg': 0, 'sweep': 0, 'ob': 0}, 'vol': vol}
    
    last_idx = len(bars) - 1
    max_tr = ap.get('max_trades', 5)
    min_sc = ap.get('min_score', 1.0)
    min_src = ap.get('min_signal_sources', 1)
    
    # 合并信号
    entries = []
    
    # 先处理FVG (主信号源)
    for fvg in reversed(fvg_list[-25:]):  # 取最近25个FVG
        idx = fvg.get('index', 0)
        if idx < 3 or idx > last_idx - 2:
            continue
        age = last_idx - idx
        if age > 40:
            continue
        
        dir = fvg['dir']
        ep = fvg.get('mid', bars[idx]['c'])
        
        # 信号源统计
        src_names = ['FVG']
        score_base = 2.0 + fvg.get('strength', 1) * 0.3
        
        # 检查附近有无Sweep
        nearby_sweep = [s for s in sweep_list if s['dir'] == dir and abs(s.get('index', 0)-idx) <= 8]
        if nearby_sweep:
            src_names.append('Sweep')
            score_base *= 1.3
            if max(s['ratio'] for s in nearby_sweep) > 2.5:
                score_base *= 1.2
        
        # 检查附近有无OB
        nearby_ob = [o for o in ob_list if o['dir'] == dir and abs(o.get('index', 0)-idx) <= 6]
        if nearby_ob:
            src_names.append('OB')
            score_base *= 1.2
        
        # CHoCH确认
        if (dir == 'long' and choch.get('bull', 0) > 55) or (dir == 'short' and choch.get('bear', 0) > 55):
            src_names.append('CHoCH')
            score_base *= 1.15
        
        if len(src_names) < min_src:
            continue
        
        # 成交量确认
        recent_vol = sum(bars[j]['v'] for j in range(max(0, idx-5), idx))
        baseline_vol = sum(bars[j]['v'] for j in range(max(0, idx-20), max(5, idx-5)))
        if baseline_vol > 0:
            vol_ratio = recent_vol / baseline_vol
            if vol_ratio > 1.2:
                score_base *= 1.1
        
        # 时效性 (越新越好)
        if age < 5:
            score_base *= 1.15
        
        # 结构止损/止盈
        atr = vol['atr']
        sl_price, tp_price = compute_swing_sl_tp(bars, idx, 'L' if dir=='long' else 'S', ep, atr)
        
        # 确保SL/TP合理
        if dir == 'long':
            sl_price = min(sl_price, round(ep * 0.97, 2))  # max 3%
            tp_price = max(tp_price, round(ep * 1.03, 2))
        else:
            sl_price = max(sl_price, round(ep * 1.03, 2))
            tp_price = min(tp_price, round(ep * 0.97, 2))
        
        rr = abs(tp_price - ep) / max(0.001, abs(sl_price - ep))
        if rr < 0.8:
            continue  # R:R太低跳过
        
        entries.append({
            'ep': ep, 'dir': 'L' if dir == 'long' else 'S',
            'idx': idx, 'sl': sl_price, 'tp': tp_price,
            'rr': round(rr, 2), 'score': round(score_base, 2),
            'src': '+'.join(src_names), 'n_src': len(src_names),
            'age': age,
        })
    
    # 评分排序 + 去重
    entries.sort(key=lambda e: -e['score'])
    deduped = []
    for e in entries:
        if not any(abs(e['idx']-d['idx']) <= 8 and e['dir'] == d['dir'] for d in deduped):
            deduped.append(e)
    
    result = deduped[:max_tr]
    
    return {
        'entries': result,
        'total': len(result),
        'signals': {
            'fvg': len(fvg_list), 'sweep': len(sweep_list),
            'ob': len(ob_list), 'choch': choch,
        },
        'vol': vol,
        'adaptive_params': {k: ap.get(k) for k in ['fvg_min_width','sl_pct','tp_pct','min_signal_sources','trail_sl']},
    }


# ════════ 回测 ════════

def backtest_v54(bars, params=None):
    """V5.4回测 — 结构止损"""
    if not bars or len(bars) < 60:
        return []
    
    result = detect_entries_v54(bars, params)
    entries = result.get('entries', [])
    if not entries:
        return []
    
    trades = []
    for e in entries:
        t = simulate_v54_trade(e, bars)
        if t:
            trades.append(t)
    return trades


def simulate_v54_trade(entry, bars):
    """模拟一笔交易 — 支持移动止损"""
    ei = entry.get('idx', 0)
    if ei >= len(bars) - 1:
        return None
    
    ep = entry['ep']
    sl = entry['sl']
    tp = entry['tp']
    dir = entry['dir']
    
    entry_idx = ei + 1  # 下一根K线入场
    if entry_idx >= len(bars):
        return None
    
    current_sl = sl
    trail_activated = False
    
    for j in range(entry_idx, len(bars)):
        b = bars[j]
        
        if dir == 'L':
            # 移动止损
            if not trail_activated and b['h'] >= ep + (tp - ep) * 0.4:
                trail_activated = True
                current_sl = ep * 1.001  # 保本
            
            if b['h'] >= tp:
                pnl = (tp - ep) / ep
                # 检查是否同时触止损
                if b['l'] <= current_sl:
                    pnl = max((current_sl - ep) / ep, pnl * 0.5)
                return {'pnl': round(pnl, 4), 'reason': 'tp', 'bars': j-entry_idx+1, 'ep': ep, 'sl': sl, 'tp': tp, 'src': entry.get('src','')}
            if b['l'] <= current_sl:
                pnl = (current_sl - ep) / ep
                return {'pnl': round(pnl, 4), 'reason': 'sl', 'bars': j-entry_idx+1, 'ep': ep, 'sl': sl, 'tp': tp, 'src': entry.get('src','')}
        else:
            if not trail_activated and b['l'] <= ep - abs(tp - ep) * 0.4:
                trail_activated = True
                current_sl = ep * 0.999
            
            if b['l'] <= tp:
                pnl = (ep - tp) / ep
                return {'pnl': round(pnl, 4), 'reason': 'tp', 'bars': j-entry_idx+1, 'ep': ep, 'sl': sl, 'tp': tp, 'src': entry.get('src','')}
            if b['h'] >= current_sl:
                pnl = (ep - current_sl) / ep
                return {'pnl': round(pnl, 4), 'reason': 'sl', 'bars': j-entry_idx+1, 'ep': ep, 'sl': sl, 'tp': tp, 'src': entry.get('src','')}
    
    # EOD
    last = bars[-1]['c']
    pnl = (last-ep)/ep if dir=='L' else (ep-last)/ep
    return {'pnl': round(pnl, 4), 'reason': 'eod', 'bars': len(bars)-entry_idx+1, 'ep': ep, 'sl': sl, 'tp': tp, 'src': entry.get('src','')}


def compute_score(trades):
    """评分"""
    n = len(trades)
    if n < 2:
        return {'score': 0, 'wr': 0, 'pf': 0, 'n': n, 'ret': 0, 'sr': 0}
    
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    n_wins = len(wins)
    wr = n_wins / n * 100
    total_win = sum(t['pnl'] for t in wins)
    total_loss = sum(abs(t['pnl']) for t in losses)
    pf = total_win / total_loss if total_loss > 0 else 999
    
    avg_pnl = sum(t['pnl'] for t in trades) / n
    total_ret = sum(t['pnl'] for t in trades) * 100
    std = math.sqrt(sum((t['pnl']-avg_pnl)**2 for t in trades)/n) if n > 1 else 0.001
    sr = (avg_pnl / std) * math.sqrt(252) if std > 0 else 0
    
    # Score: WR主导 + PF补充 + 交易量加权
    score = wr * 0.5 + min(40, pf * 5) * 0.25 + min(30, n * 2) * 0.25
    
    return {
        'score': round(score, 1), 'wr': round(wr, 1), 'pf': round(pf, 2),
        'n': n, 'n_wins': n_wins, 'n_losses': n - n_wins,
        'ret': round(total_ret, 2), 'sr': round(sr, 2),
    }


# ════════ 数据加载 ════════

def fetch(url, timeout=20):
    import urllib.request
    for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
        os.environ.pop(k, None)
    req = urllib.request.Request(url, headers=HUBBLE_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode()

def load_bars(symbol, interval='daily', limit=300):
    import json
    cache_dir = Path.home() / '.hermes' / 'kline_cache'
    cache_file = cache_dir / f"{symbol.replace('.','_')}_{interval}_{limit}.json"
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)
    
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
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_file, 'w') as f:
        json.dump(bars, f)
    return bars


if __name__ == '__main__':
    print("=== SMC V5.4 Engine (Adaptive) ===")
    for sym in ['300231.SZ', '000858.SZ', '002415.SZ', '300750.SZ']:
        bars = load_bars(sym, 'daily', 300)
        if bars:
            vol = get_vol_profile(bars)
            r = detect_entries_v54(bars)
            tr = backtest_v54(bars)
            s = compute_score(tr) if tr else {'score':0, 'wr':0, 'pf':0, 'n':0, 'ret':0}
            print(f"\n{sym}: Vol={vol['vol_level']} ({vol['atr_pct']}%)")
            print(f"  Entries: {r['total']} | Trades: {s['n']} | WR={s['wr']}% PF={s['pf']}")
            if r['entries']:
                print(f"  Top1: {r['entries'][0]['dir']} ep={r['entries'][0]['ep']} RR={r['entries'][0]['rr']} score={r['entries'][0]['score']}")
            if tr:
                print(f"  Ret={s['ret']}% SR={s['sr']}")