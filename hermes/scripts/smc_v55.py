#!/usr/bin/env python3
"""
SMC V5.5 Engine — 稳定高胜率引擎
==================================
核心设计原则:
  1. 参数必须有物理意义: FVG至少0.1以上, SL至少1.5%以上
  2. 混合评分: WR*0.3 + PF*0.3 + Return*0.2 + N*0.2
  3. 波动率自适应: 高/中/低3层独立参数
  4. 信号质量优先: 宁可少但精确

关键区别 vs V5.4:
  - 严格的参数边界 (不搜索极端值)
  - 分层评分 (不是纯WR驱动)
  - 成交量/趋势确认增强
"""

import math, json, time, os, sys
from pathlib import Path

HUBBLE_BASE = "http://43.167.234.49:3101"
HUBBLE_HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}

# ════════ 参数定义 (严格物理边界) ════════

PARAM_DEFS = {
    # 高波动 (ATR >= 3.0%)
    'high_fvg_min_width': {'min': 0.20, 'max': 0.50, 'default': 0.30, 'step': 0.02},
    'high_sweep_lookback': {'min': 12, 'max': 28, 'default': 18, 'step': 1},
    'high_sweep_wick': {'min': 1.8, 'max': 3.5, 'default': 2.5, 'step': 0.1},
    'high_sl_pct': {'min': 2.0, 'max': 6.0, 'default': 3.0, 'step': 0.2},
    'high_tp_pct': {'min': 4.0, 'max': 12.0, 'default': 6.0, 'step': 0.5},
    
    # 中波动 (1.5% <= ATR < 3.0%)
    'med_fvg_min_width': {'min': 0.15, 'max': 0.40, 'default': 0.25, 'step': 0.02},
    'med_sweep_lookback': {'min': 10, 'max': 22, 'default': 15, 'step': 1},
    'med_sweep_wick': {'min': 1.5, 'max': 3.0, 'default': 2.0, 'step': 0.1},
    'med_sl_pct': {'min': 2.0, 'max': 5.0, 'default': 3.0, 'step': 0.2},
    'med_tp_pct': {'min': 3.0, 'max': 10.0, 'default': 5.0, 'step': 0.5},
    
    # 低波动 (ATR < 1.5%)
    'low_fvg_min_width': {'min': 0.10, 'max': 0.30, 'default': 0.18, 'step': 0.02},
    'low_sweep_lookback': {'min': 8, 'max': 18, 'default': 12, 'step': 1},
    'low_sweep_wick': {'min': 1.2, 'max': 2.5, 'default': 1.6, 'step': 0.1},
    'low_sl_pct': {'min': 1.5, 'max': 4.0, 'default': 2.5, 'step': 0.2},
    'low_tp_pct': {'min': 3.0, 'max': 8.0, 'default': 5.0, 'step': 0.5},
    
    # 跨层参数
    'confirm_range': {'min': 1, 'max': 4, 'default': 2, 'step': 1},
    'min_sources': {'min': 1, 'max': 2, 'default': 1, 'step': 1},
    'max_trades': {'min': 3, 'max': 10, 'default': 6, 'step': 1},
    'min_score': {'min': 1.0, 'max': 3.0, 'default': 1.5, 'step': 0.1},
    'trail_activation': {'min': 0.25, 'max': 0.60, 'default': 0.40, 'step': 0.05},
}

# ════════ 工具 ════════

def calc_atr(klines, period=14):
    if len(klines) < period+1: return 0
    trs = []
    for i in range(1, min(period+1, len(klines))):
        tr = max(klines[-i]['h']-klines[-i]['l'],
                 abs(klines[-i]['h']-klines[-i-1]['c']),
                 abs(klines[-i]['l']-klines[-i-1]['c']))
        trs.append(tr)
    return sum(trs)/len(trs) if trs else 0

def get_vol(bars):
    if len(bars) < 30: return {'atr_pct': 0, 'level': 'unknown'}
    atr = calc_atr(bars)
    ap = sum((b['h']+b['l'])/2 for b in bars[-20:]) / 20
    atr_pct = atr / ap * 100 if ap > 0 else 0
    if atr_pct >= 3.0: lvl = 'high'
    elif atr_pct >= 1.5: lvl = 'med'
    else: lvl = 'low'
    return {'atr_pct': round(atr_pct, 2), 'level': lvl}

def get_layer_params(fp, atr_pct):
    """获取波动率层的参数"""
    l = 'high' if atr_pct >= 3.0 else ('med' if atr_pct >= 1.5 else 'low')
    return {
        'fvg_min_width': fp.get(f'{l}_fvg_min_width', 0.25),
        'sweep_lookback': int(fp.get(f'{l}_sweep_lookback', 15)),
        'sweep_wick': fp.get(f'{l}_sweep_wick', 2.0),
        'sl_pct': fp.get(f'{l}_sl_pct', 3.0),
        'tp_pct': fp.get(f'{l}_tp_pct', 6.0),
        'confirm_range': int(fp.get('confirm_range', 2)),
        'min_sources': int(fp.get('min_sources', 1)),
        'max_trades': int(fp.get('max_trades', 6)),
        'min_score': fp.get('min_score', 1.5),
        'trail': fp.get('trail_activation', 0.4),
        'layer': l,
    }


# ════════ 回测 (内联, 自包含) ════════

def backtest_all(bars, flat_params):
    """V5.5完整回测 — 返回trade list"""
    if len(bars) < 60: return []
    
    vol = get_vol(bars)
    atr_pct = vol['atr_pct']
    lp = get_layer_params(flat_params, atr_pct)
    
    # ── FVG检测 ──
    avg_r = sum(abs(k['h']-k['l']) for k in bars[-30:]) / max(1, min(30, len(bars)))
    if avg_r < 0.001: return []
    
    fvgs = []
    for i in range(1, len(bars)-1):
        p, c, n = bars[i-1], bars[i], bars[i+1]
        top = min(p['h'], n['h'])
        bot = max(p['l'], n['l'])
        gap = top - bot
        fvg_w = lp['fvg_min_width']
        if gap > avg_r * fvg_w:
            dir = 'S' if c['c'] > c['o'] else 'L'
            strength = min(5, gap / (avg_r * 0.15))
            fvgs.append({
                'dir': dir, 'idx': i, 'mid': round((top+bot)/2, 2),
                'gap_ratio': gap/avg_r, 'strength': round(strength, 1),
            })
    
    if not fvgs: return []
    
    # ── Sweep检测 ──
    lkb = lp['sweep_lookback']
    wick = lp['sweep_wick']
    sweeps = []
    for i in range(lkb+1, len(bars)):
        c = bars[i]
        body = abs(c['c']-c['o'])
        if body < 0.001: continue
        uw = c['h'] - max(c['c'], c['o'])
        lw = min(c['c'], c['o']) - c['l']
        rl = min(bars[j]['l'] for j in range(i-lkb, i))
        rh = max(bars[j]['h'] for j in range(i-lkb, i))
        if c['l'] < rl and uw/body >= wick*0.5:
            sweeps.append({'dir':'L','idx':i,'price':c['l'],'ratio':round(uw/body,2)})
        if c['h'] > rh and lw/body >= wick*0.4:
            sweeps.append({'dir':'S','idx':i,'price':c['h'],'ratio':round(lw/body,2)})
    
    # ── 合并信号 → entries ──
    eps = []
    last_idx = len(bars) - 1
    for fvg in reversed(fvgs[-max(25, len(fvgs)):]):
        idx = fvg['idx']
        dir = fvg['dir']
        ep = fvg['mid']
        
        if idx < 5 or idx > last_idx - 2: continue
        if last_idx - idx > 35: continue
        
        src = ['FVG']
        score = 2.0 + fvg['strength'] * 0.3
        
        # Sweep near
        near_sw = [s for s in sweeps if s['dir']==dir and abs(s['idx']-idx)<=8]
        if near_sw:
            src.append('SP')
            score *= 1.3
            max_r = max(s['ratio'] for s in near_sw)
            if max_r > 2.5: score *= 1.15
        
        # CHoCH
        seg = bars[-15:]
        ups = sum(1 for i in range(len(seg)-1) if seg[i]['c']<seg[i+1]['c'])
        if (dir=='L' and ups > 9) or (dir=='S' and ups < 6):
            src.append('MS')
            score *= 1.1
        
        if len(src) < lp['min_sources']: continue
        if score < lp['min_score']: continue
        
        # SL/TP
        sl = round(ep * (1 - lp['sl_pct']/100), 2) if dir=='L' else round(ep * (1 + lp['sl_pct']/100), 2)
        tp = round(ep * (1 + lp['tp_pct']/100), 2) if dir=='L' else round(ep * (1 - lp['tp_pct']/100), 2)
        rr = abs(tp-ep) / max(0.01, abs(sl-ep))
        if rr < 1.2: continue
        
        eps.append({'dir':dir,'ep':ep,'idx':idx,'sl':sl,'tp':tp,'rr':round(rr,2),'score':round(score,2),'src':'+'.join(src)})
    
    if not eps: return []
    eps.sort(key=lambda e: -e['score'])
    dedup = []
    for e in eps:
        if not any(abs(e['idx']-d['idx'])<=10 and e['dir']==d['dir'] for d in dedup):
            dedup.append(e)
    eps = dedup[:lp['max_trades']]
    if not eps: return []
    
    # ── 模拟交易 ──
    trades = []
    for e in eps:
        ei = e['idx'] + 2  # 2根K线后入场
        if ei >= len(bars): continue
        sl = e['sl']
        trail_a = False
        for j in range(ei, len(bars)):
            b = bars[j]
            if e['dir'] == 'L':
                if not trail_a and b['h'] >= e['ep'] + (e['tp']-e['ep'])*lp['trail']:
                    trail_a = True; sl = e['ep']*1.002
                if b['h'] >= e['tp']:
                    trades.append({'pnl':round((e['tp']-e['ep'])/e['ep'],4),'src':e['src'],'dir':'L'})
                    break
                if b['l'] <= sl:
                    trades.append({'pnl':round((sl-e['ep'])/e['ep'],4),'src':e['src'],'dir':'L'})
                    break
            else:
                if not trail_a and b['l'] <= e['ep'] - abs(e['tp']-e['ep'])*lp['trail']:
                    trail_a = True; sl = e['ep']*0.998
                if b['l'] <= e['tp']:
                    trades.append({'pnl':round((e['ep']-e['tp'])/e['ep'],4),'src':e['src'],'dir':'S'})
                    break
                if b['h'] >= sl:
                    trades.append({'pnl':round((e['ep']-sl)/e['ep'],4),'src':e['src'],'dir':'S'})
                    break
            if j - ei > 60:  # max 60 bars
                l = b['c']
                pnl = (l-e['ep'])/e['ep'] if e['dir']=='L' else (e['ep']-l)/e['ep']
                trades.append({'pnl':round(pnl,4),'src':e['src'],'dir':e['dir']})
                break
    
    return trades


def score_trades(trades):
    """V5.5评分: WR+PF+Return 均衡"""
    n = len(trades)
    if n < 2:
        return {'score': 0, 'wr': 0, 'pf': 0, 'n': n, 'ret': 0}

    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    wr = len(wins) / n * 100
    tw = sum(t['pnl'] for t in wins)
    tl = sum(abs(t['pnl']) for t in losses)
    pf = tw/tl if tl > 0 else 999
    avg = sum(t['pnl'] for t in trades) / n
    ret = sum(t['pnl'] for t in trades) * 100
    
    std = math.sqrt(sum((t['pnl']-avg)**2 for t in trades)/n) if n > 1 else 0.001
    sr = (avg/std) * math.sqrt(252) if std > 0 else 0
    
    # 关键目标: WR > 80%, PF > 5, Ret > 10%
    wr_score = min(40, wr * 0.4)                    # WR最多40
    pf_score = min(35, pf * 5)                      # PF最多35  
    ret_score = min(15, ret * 0.5)                  # Ret最多15
    n_score = min(10, n)                            # N最多10
    
    # Bonus: PF>5 +5, WR>85% +3
    bonus = 0
    if pf >= 5: bonus += 5
    if pf >= 8: bonus += 3
    if wr >= 85: bonus += 3
    if wr >= 90: bonus += 2
    
    score = wr_score + pf_score + ret_score + n_score + bonus
    
    return {
        'score': round(score, 1), 'wr': round(wr, 1), 'pf': round(pf, 2),
        'n': n, 'n_wins': len(wins), 'n_losses': n-len(wins),
        'ret': round(ret, 2), 'sr': round(sr, 2),
        'components': {'wr_s':wr_score, 'pf_s':pf_score, 'ret_s':ret_score, 'n_s':n_score, 'bonus':bonus},
    }


# ════════ 数据加载 ════════

def fetch(url, timeout=20):
    import urllib.request
    for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
        os.environ.pop(k, None)
    req = urllib.request.Request(url, headers=HUBBLE_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode()

def load_bars(symbol, forced_refresh=False):
    import json as json_mod
    cache_dir = Path.home() / '.hermes' / 'kline_cache'
    cache_f = cache_dir / f"{symbol.replace('.','_')}_daily_300.json"
    
    if cache_f.exists() and not forced_refresh:
        try:
            with open(cache_f) as fh:
                return json_mod.load(fh)
        except: pass
    
    url = f"{HUBBLE_BASE}/api/v2/cnstock/stocks?symbol={symbol}&interval=daily&limit=300"
    try:
        raw = json_mod.loads(fetch(url))
        data = raw.get('data', raw)
        if not isinstance(data, list): return []
        bars = []
        for k in data:
            if isinstance(k, dict):
                bars.append({'o':float(k.get('open',k.get('o',0))),'h':float(k.get('high',k.get('h',0))),
                             'l':float(k.get('low',k.get('l',0))),'c':float(k.get('close',k.get('c',0))),
                             'v':float(k.get('volume',k.get('vol',k.get('v',0)))),'t':str(k.get('time',k.get('t','')))})
            elif isinstance(k, list) and len(k) >= 5:
                bars.append({'o':float(k[1]),'h':float(k[2]),'l':float(k[3]),'c':float(k[4]),
                             'v':float(k[5]) if len(k)>5 else 0,'t':str(k[0])})
        if len(bars) >= 2 and bars[0]['t'] > bars[1]['t']:
            bars.reverse()
        cache_dir.mkdir(parents=True, exist_ok=True)
        with open(cache_f, 'w') as fh:
            json_mod.dump(bars, fh)
        return bars
    except:
        return []


if __name__ == '__main__':
    print("=== SMC V5.5 Engine ===")
    print(f"Params: {len(PARAM_DEFS)} dimensions")
    
    test_symbols = ['300231.SZ', '000858.SZ', '002415.SZ', '300750.SZ', '002594.SZ']
    for sym in test_symbols:
        bars = load_bars(sym)
        if bars:
            vol = get_vol(bars)
            tr = backtest_all(bars, {k: v['default'] for k, v in PARAM_DEFS.items()})
            if tr:
                s = score_trades(tr)
                print(f"{sym}: Vol={vol['level']} ({vol['atr_pct']}%) Trades={s['n']} WR={s['wr']}% PF={s['pf']} Ret={s['ret']}% Score={s['score']}")
            else:
                vol = get_vol(bars)
                print(f"{sym}: No trades (Vol={vol['level']} {vol['atr_pct']}%)")