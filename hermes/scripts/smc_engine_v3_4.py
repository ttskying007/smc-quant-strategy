#!/usr/bin/env python3
"""
SMC Engine v3.4 — 最终量产版
基于V3.2核心 + V3.3经验, 平衡信号量与WR

改进:
1. Score门槛: 3.0 -> 2.2 (增加~4x信号)
2. FVG阈值: 4个 -> 5个 (新增0.08超宽松)
3. Sweep距离: 扩大范围 (-5~+18)
4. OB距离: 5->12 (更宽松)
5. 时间加权减弱: max_weight从1.0->0.9, 衰减从0.5->0.3
6. 信号去重时距离从5->6 (更多多样性)
"""

import math
from collections import Counter


def detect_fvg_multi_v34(bars):
    """5阈值FVG检测"""
    if len(bars) < 3:
        return []
    avg_r = sum(abs(k['h']-k['l']) for k in bars[-30:]) / 30 if len(bars) >= 30 else 0
    if avg_r == 0:
        return []
    all_s = []
    for th in [0.08, 0.15, 0.25, 0.35, 0.45]:
        start = max(1, len(bars)-40)
        for i in range(start, len(bars)-1):
            p,c,n = bars[i-1],bars[i],bars[i+1]
            bd = abs(c['c']-c['o'])
            if c['c'] > c['o']:
                gt,gb = min(p['h'],n['h']),max(p['l'],n['l'])
                if gt>gb and gt-gb>avg_r*th:
                    st = 1+(1 if bd>(gt-gb)*2 else 0)+(1 if gt-gb>avg_r*0.5 else 0)
                    all_s.append({'d':'long','t':gt,'b':gb,'m':(gt+gb)/2,'s':min(3,st),'i':i,'th':th})
            elif c['c'] < c['o']:
                gt,gb = max(p['h'],n['h']),min(p['l'],n['l'])
                if gt>gb and gt-gb>avg_r*th:
                    st = 1+(1 if bd>(gt-gb)*2 else 0)+(1 if gt-gb>avg_r*0.5 else 0)
                    all_s.append({'d':'short','t':gt,'b':gb,'m':(gt+gb)/2,'s':min(3,st),'i':i,'th':th})
    seen = {}
    for s in all_s:
        k = (s['i'], s['d'])
        if k not in seen or s['s'] > seen[k]['s']:
            seen[k] = s
    return list(seen.values())


def detect_entries_v3_4(bars):
    """V3.4 入口检测 — 平衡版"""
    results = []
    if len(bars) < 50:
        return results
    
    from smc_engine import detect_liquidity_sweep, calc_atr, detect_market_structure, detect_order_blocks, detect_choch_v2
    
    # 多阈值FVG
    fvg_list = detect_fvg_multi_v34(bars)
    
    # 多回看Sweep
    sweep_list = []
    for lb in [5, 8, 12, 15, 20]:
        for s in detect_liquidity_sweep(bars, lookback=lb):
            s['lb'] = lb
            sweep_list.append(s)
    seen_sw = {}
    for s in sweep_list:
        k = (s['index'], s['direction'])
        if k not in seen_sw or s.get('wick_ratio',0) > seen_sw[k].get('wick_ratio',0):
            seen_sw[k] = s
    sweep_list = list(seen_sw.values())
    
    # OB
    ob_list = detect_order_blocks(bars)
    
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
    
    ms = detect_market_structure(bars, 15)
    
    if not fvg_list:
        return results
    
    last_idx = len(bars) - 1
    
    for fvg in fvg_list[-20:]:
        i = fvg.get('i', 0)
        if i < 3 or i >= last_idx - 2:
            continue
        
        age = last_idx - i
        if age > 30:
            continue
        
        direction = fvg['d']
        # 时间加权减弱: 最大0.9, 衰减更慢
        tw = max(0.6, 0.9 - age / 30.0 * 0.3)
        
        signals_found = {'fg': True}
        score = 1.0
        score_parts = ['FVG']
        
        # Sweep: 扩大距离 (-5 ~ +18)
        sw = [s for s in sweep_list if s['direction'] == direction 
              and -5 <= i - s.get('index', 0) <= 18]
        if sw:
            best_sw = max(sw, key=lambda s: s.get('wick_ratio', 0))
            sw_score = min(2.0, best_sw.get('wick_ratio', 1.0) * 0.5)
            score += sw_score
            signals_found['sw'] = True
            score_parts.append(f'SW')
        
        # OB: 扩大距离到12
        if any(o['direction'] == direction and abs(o.get('index', 0)-i) <= 12 for o in ob_list):
            score += 0.8
            signals_found['ob'] = True
            score_parts.append('OB')
        
        # CHOCH
        if choch_wide.get('detected') and choch_wide['direction'] == direction:
            score += 1.2
            signals_found['ch'] = True
            score_parts.append('CH')
        
        # MS
        if ms.get('direction') == direction:
            score += 0.4
            signals_found['ms'] = True
            score_parts.append('MS')
        
        # FVG强度
        if fvg.get('s', 1) >= 2:
            score += 0.4
            score_parts.append('ST')
        
        # 确认K线
        ci = min(i + 1, last_idx - 1)
        if ci > 0 and i < len(bars):
            cb = bars[ci]
            if (direction == 'long' and cb['c'] > cb['o']) or (direction == 'short' and cb['c'] < cb['o']):
                score += 0.4
                score_parts.append('CF')
        
        # 时间加权
        score *= tw
        n_sig = sum(1 for v in signals_found.values() if v)
        
        # === V3.4核心: 门槛从3.0降至2.2 ===
        if score >= 2.2 and n_sig >= 2:
            atr = calc_atr(bars[:i + 5])
            entry_price = fvg['m']
            
            ss = min(1.0, score / 5.0)
            sl_atr = 2.0 - ss * 0.8
            tp_atr = 2.5 + ss * 1.0
            
            if direction == 'long':
                results.append({
                    'ep': min(i + 1, last_idx - 1),
                    'dir': 'L',
                    'en': round(entry_price, 4),
                    'sl': round(entry_price - atr * sl_atr, 4),
                    'tp': round(entry_price + atr * tp_atr, 4),
                    'sigs': score_parts,
                    'sc': round(score, 2),
                })
            else:
                results.append({
                    'ep': min(i + 1, last_idx - 1),
                    'dir': 'S',
                    'en': round(entry_price, 4),
                    'sl': round(entry_price + atr * sl_atr, 4),
                    'tp': round(entry_price - atr * tp_atr, 4),
                    'sigs': score_parts,
                    'sc': round(score, 2),
                })
    
    # 6根K线内同方向去重
    sorted_r = sorted(results, key=lambda r: -r['sc'])
    final = []
    for r in sorted_r:
        if not any(abs(r['ep'] - f['ep']) <= 6 and r['dir'] == f['dir'] for f in final):
            final.append(r)
    
    return final


def backtest_v3_4(bars, only_long=False):
    """V3.4 回测"""
    entries = detect_entries_v3_4(bars)
    trades = []
    for e in entries:
        if only_long and e['dir'] != 'L':
            continue
        ei = e['ep']
        if ei >= len(bars):
            continue
        d, ep, sl, tp = e['dir'], e['en'], e['sl'], e['tp']
        
        for j in range(ei, len(bars)):
            b = bars[j]
            if d == 'L':
                if b['l'] <= sl:
                    trades.append({'pnl':(sl-ep)/ep, 'sig':e['sigs'], 'sc':e['sc']}); break
                if b['h'] >= tp:
                    trades.append({'pnl':(tp-ep)/ep, 'sig':e['sigs'], 'sc':e['sc']}); break
            else:
                if b['h'] >= sl:
                    trades.append({'pnl':(ep-sl)/ep, 'sig':e['sigs'], 'sc':e['sc']}); break
                if b['l'] <= tp:
                    trades.append({'pnl':(ep-tp)/ep, 'sig':e['sigs'], 'sc':e['sc']}); break
        else:
            l = bars[-1]['c']
            trades.append({'pnl':(l-ep)/ep if d=='L' else (ep-l)/ep, 'sig':e['sigs'], 'sc':e['sc']})
    return trades


def evaluate(trades, name='V3.4'):
    from smc_backtest_v2 import compute_sharpe
    n = len(trades)
    if n == 0:
        print(f"  {name}: 0 trades")
        return {'n':0,'wr':0.0}
    wins = [t for t in trades if t['pnl']>0]
    wr = len(wins)/n*100
    sr = compute_sharpe([t['pnl'] for t in trades],252)
    ret = sum(t['pnl'] for t in trades)*100
    print(f"  {name}: {n:>3}t WR={wr:>5.1f}% SR={sr:>5.2f} Ret={ret:>+.1f}%")
    return {'n':n,'wr':wr,'sr':sr,'ret':ret}