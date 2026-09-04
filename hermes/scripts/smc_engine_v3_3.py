#!/usr/bin/env python3
"""
SMC Engine v3.3 — 自适应信号倍增版
============================================

V3.2的问题: 信号太少 (平均5.3笔/200只)，WR 58%但覆盖率不够。

V3.3的改进:
1. 波动率自适应score门槛: ATR高→高门槛, ATR低→低门槛
2. 双通道检测: 宽松通道(多信号)+严格通道(高胜率)并行
3. 动态SL/TP: 基于股票波动率调整止盈止损
4. 信号去重+合并: 相近entry合并减少重复

核心思路:
  把每只股票的信号量从~5提升到~30，
  保持WR从58%仅降到~50%，
  最终总盈利大幅提升。
"""

import math
from collections import Counter


def calc_atr(bars, period=14):
    if len(bars) < period+1:
        return bars[-1]['h']-bars[-1]['l'] if bars else 0
    trs = []
    for i in range(-period, 0):
        tr = max(bars[i]['h']-bars[i]['l'],
                 abs(bars[i]['h']-bars[i-1]['c']),
                 abs(bars[i]['l']-bars[i-1]['c']))
        trs.append(tr)
    return sum(trs)/len(trs)


def detect_fvg_multi_full(bars, thresholds=None):
    """全量FVG检测: 4个阈值+全范围"""
    if thresholds is None:
        thresholds = [0.12, 0.18, 0.25, 0.35, 0.45]
    if len(bars) < 3:
        return []
    avg_r = sum(abs(k['h']-k['l']) for k in bars[-30:]) / 30 if len(bars) >= 30 else 0
    if avg_r == 0:
        return []
    all_s = []
    for th in thresholds:
        start = max(1, len(bars)-40)
        for i in range(start, len(bars)-1):
            p,c,n = bars[i-1],bars[i],bars[i+1]
            bd = abs(c['c']-c['o'])
            if c['c'] > c['o']:
                gt,gb = min(p['h'],n['h']),max(p['l'],n['l'])
                if gt>gb and gt-gb>avg_r*th:
                    st = 1+(1 if bd>(gt-gb)*2 else 0)+(1 if gt-gb>avg_r*0.5 else 0)
                    all_s.append({'d':'long','top':gt,'bottom':gb,'mid':(gt+gb)/2,'s':min(3,st),'i':i,'th':th})
            elif c['c'] < c['o']:
                gt,gb = max(p['h'],n['h']),min(p['l'],n['l'])
                if gt>gb and gt-gb>avg_r*th:
                    st = 1+(1 if bd>(gt-gb)*2 else 0)+(1 if gt-gb>avg_r*0.5 else 0)
                    all_s.append({'d':'short','top':gt,'bottom':gb,'mid':(gt+gb)/2,'s':min(3,st),'i':i,'th':th})
    seen = {}
    for s in all_s:
        k = (s['i'], s['d'])
        if k not in seen or s['s'] > seen[k]['s']:
            seen[k] = s
    return list(seen.values())


def detect_sweep_multi_full(bars):
    """全量Sweep: 5回看周期"""
    from smc_engine import detect_liquidity_sweep
    all_sw = []
    for lb in [5, 8, 12, 15, 20]:
        for s in detect_liquidity_sweep(bars, lookback=lb):
            s['lb'] = lb
            all_sw.append(s)
    seen = {}
    for s in all_sw:
        k = (s['index'], s['direction'])
        if k not in seen or s.get('wick_ratio',0) > seen[k].get('wick_ratio',0):
            seen[k] = s
    return list(seen.values())


def detect_entries_v3_3(bars):
    """
    V3.3 入口检测 — 自适应信号倍增
    
    两阶段:
    1. 宽松通道: score>=2.0 且至少1个辅助信号 → 大量entry
    2. 严格通道: score>=4.0 且至少3个辅助信号 → 精选entry
    
    合并: 相近entry (5根K线内同方向) 合并
    """
    results = {'loose': [], 'strict': [], 'total': []}
    if len(bars) < 50:
        return results
    
    from smc_engine import detect_market_structure, detect_order_blocks, detect_choch_v2, calc_atr as _calc_atr
    
    # 获取所有信号
    fvg_list = detect_fvg_multi_full(bars)
    sweep_list = detect_sweep_multi_full(bars)
    ob_list = detect_order_blocks(bars)
    ms = detect_market_structure(bars, 15)
    
    # 多窗口CHOCH
    choch_results = []
    for lb in [8, 12, 15, 20]:
        c = detect_choch_v2(bars, lookback=lb)
        if c.get('detected'):
            choch_results.append(c)
    choch_wide = {'detected': bool(choch_results)}
    if choch_results:
        dirs = [r['direction'] for r in choch_results]
        choch_wide['direction'] = max(set(dirs), key=dirs.count)
    
    if not fvg_list:
        return results
    
    # 波动率分析 — 决定宽松/严格比例
    atr = calc_atr(bars)
    avg_price = sum(k['c'] for k in bars[-30:]) / 30 if len(bars) >= 30 else 1
    atr_pct = atr / avg_price * 100 if avg_price > 0 else 0
    
    # ATR%越高 -> 用更严格的门槛 (高波动=高风险)
    # 但也要给更多机会 — 所以宽松和严格都要
    vol_factor = min(1.0, atr_pct / 3.0)  # 0-1 range
    
    last_idx = len(bars) - 1
    
    for fvg in fvg_list[-20:]:  # 最近20个FVG
        i = fvg.get('i', 0)
        if i < 3 or i >= last_idx - 2:
            continue
        
        age = last_idx - i
        if age > 30:
            continue
        
        direction = fvg['d']
        tw = max(0.4, 1.0 - age / 30.0 * 0.6)
        
        # 信号共振得分
        signals_found = {'fg': True}
        score = 1.0 + fvg.get('s', 1) * 0.3
        
        # Sweep (宽松距离)
        sw = [s for s in sweep_list if s['direction'] == direction 
              and -4 <= i - s.get('index', 0) <= 15]
        if sw:
            score += min(2.0, max(sw, key=lambda x: x.get('wick_ratio',1)).get('wick_ratio',1) * 0.5)
            signals_found['sw'] = True
        
        # OB (宽松距离)
        if any(o['direction'] == direction and abs(o.get('index', 0)-i) <= 12 for o in ob_list):
            score += 0.8
            signals_found['ob'] = True
        
        # CHOCH
        if choch_wide.get('detected') and choch_wide['direction'] == direction:
            score += 1.2 + len(choch_results) * 0.15
            signals_found['ch'] = True
        
        # MS
        if ms.get('direction') == direction:
            score += 0.4
            signals_found['ms'] = True
        
        # 确认K线
        ci = min(i + 1, last_idx - 1)
        if ci > 0 and i < len(bars):
            cb = bars[ci]
            if (direction == 'long' and cb['c'] > cb['o']) or (direction == 'short' and cb['c'] < cb['o']):
                score += 0.4
                signals_found['cf'] = True
        
        # 时间加权
        score *= tw
        n_sig = sum(1 for v in signals_found.values() if v)
        
        # 自适应score门槛: 低波动用低门槛(多信号)
        loose_th = max(1.2, 2.0 - vol_factor * 0.8)
        strict_th = max(2.5, 3.5 - vol_factor * 0.5)
        
        if score < loose_th:
            continue
        if n_sig < 2:
            continue
        
        atr_current = calc_atr(bars[:i+5])
        entry_price = fvg['mid']
        
        # 自适应SL/TP: 高波动→更宽SL
        sl_mult = 1.5 + vol_factor * 1.5  # 1.5~3.0
        tp_mult = 2.0 + vol_factor * 1.5  # 2.0~3.5
        
        # 信号强度调节
        ss = min(1.0, score / 5.0)
        sl_final = sl_mult - ss * 0.5
        tp_final = tp_mult + ss * 0.5
        
        if direction == 'long':
            sl = entry_price - atr_current * sl_final
            tp = entry_price + atr_current * tp_final
        else:
            sl = entry_price + atr_current * sl_final
            tp = entry_price - atr_current * tp_final
        
        entry_data = {
            'idx': min(i + 1, last_idx - 1),
            'dir': direction,
            'ep': round(entry_price, 4),
            'sl': round(sl, 4),
            'tp': round(tp, 4),
            'score': round(score, 2),
            'n_sig': n_sig,
            'sigs': list(signals_found.keys()),
            'strict': n_sig >= 3 and score >= strict_th,
            'fvg_i': i,
        }
        
        if entry_data['strict']:
            results['strict'].append(entry_data)
        results['loose'].append(entry_data)
        results['total'].append(entry_data)
    
    # 去重: 5根K线内同方向只保留score最高的entry
    def dedup(entries):
        if not entries:
            return []
        sorted_e = sorted(entries, key=lambda e: (-e['score'], e['idx']))
        final = []
        used_idx = set()
        for e in sorted_e:
            ei = e['idx']
            if any(abs(ei - u) <= 5 and e['dir'] == final[idx]['dir'] 
                   for idx, u in enumerate(used_idx) if idx < len(final)):
                continue
            final.append(e)
            used_idx.add(ei)
        return final
    
    results['loose'] = dedup(results['loose'])
    results['strict'] = dedup(results['strict'])
    
    return results


def backtest_v3_3(bars, mode='total'):
    """
    V3.3 回测
    mode: 'strict' = 只用精选信号, 'loose' = 只用宽松, 'total' = 全部
    """
    entries_data = detect_entries_v3_3(bars)
    
    if mode == 'strict':
        entries = entries_data.get('strict', [])
    elif mode == 'loose':
        entries = entries_data.get('loose', [])
    else:
        entries = entries_data.get('total', [])
    
    trades = []
    for e in entries:
        ei = e['idx']
        if ei >= len(bars):
            continue
        d, ep, sl, tp = e['dir'], e['ep'], e['sl'], e['tp']
        
        for j in range(ei, len(bars)):
            b = bars[j]
            if d == 'long':
                if b['l'] <= sl:
                    trades.append({'pnl':(sl-ep)/ep,'r':'sl','sig':e['sigs'],'score':e['score'],'strict':e.get('strict',False)})
                    break
                if b['h'] >= tp:
                    trades.append({'pnl':(tp-ep)/ep,'r':'tp','sig':e['sigs'],'score':e['score'],'strict':e.get('strict',False)})
                    break
            else:
                if b['h'] >= sl:
                    trades.append({'pnl':(ep-sl)/ep,'r':'sl','sig':e['sigs'],'score':e['score'],'strict':e.get('strict',False)})
                    break
                if b['l'] <= tp:
                    trades.append({'pnl':(ep-tp)/ep,'r':'tp','sig':e['sigs'],'score':e['score'],'strict':e.get('strict',False)})
                    break
        else:
            l = bars[-1]['c']
            pnl = (l-ep)/ep if d=='long' else (ep-l)/ep
            trades.append({'pnl':pnl,'r':'eod','sig':e['sigs'],'score':e['score'],'strict':e.get('strict',False)})
    
    return trades


def evaluate(trades, name='V3.3'):
    """结果评估"""
    from smc_backtest_v2 import compute_sharpe
    n = len(trades)
    if n == 0:
        print(f"  {name}: 0 trades")
        return {'n':0,'wr':0,'sr':0}
    
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    wr = len(wins)/n*100
    ret = sum(t['pnl'] for t in trades)*100
    pf = abs(sum(t['p'] for t in wins)/sum(t['p'] for t in losses)) if losses and sum(t['p'] for t in losses)!=0 else float('inf')
    sr = compute_sharpe([t['pnl'] for t in trades], 252)
    
    strict_n = len([t for t in trades if t.get('strict')])
    
    print(f"  {name}: {n}t WR={wr:.1f}% SR={sr:.2f} PF={pf:.1f} Ret={ret:+.1f}% Strict={strict_n}")
    return {'n':n,'wr':wr,'sr':sr,'pf':pf,'ret':ret}