#!/usr/bin/env python3
"""
SMC Engine v3.2 — 最终版高胜率共振引擎
改进点:
1. 多阈值FVG (4个阈值: 0.12/0.20/0.30/0.45) → 更多信号
2. 多回看Sweep (5个lookback: 5/8/12/15/20) → 全覆盖
3. 宽松CHOCH (多时间窗口检测) → 更高检出率
4. 市场结构辅助 (只取顺趋势信号) → 过滤反向噪音
5. 时间加权评分 → 近期信号权重大
"""

import math
from collections import Counter


def detect_fvg_multi(bars):
    """4阈值FVG检测"""
    if len(bars) < 3:
        return []
    avg_r = sum(abs(k['h']-k['l']) for k in bars[-30:]) / 30 if len(bars) >= 30 else 0
    if avg_r == 0:
        return []
    all_s = []
    for th in [0.12, 0.20, 0.30, 0.45]:
        start = max(1, len(bars)-35)
        for i in range(start, len(bars)-1):
            p,c,n = bars[i-1],bars[i],bars[i+1]
            bd = abs(c['c']-c['o'])
            if c['c'] > c['o']:
                gt,gb = min(p['h'],n['h']),max(p['l'],n['l'])
                if gt>gb and gt-gb>avg_r*th:
                    st = 1+(1 if bd>(gt-gb)*2 else 0)+(1 if gt-gb>avg_r*0.5 else 0)
                    all_s.append({'type':'BullFVG','direction':'long','top':gt,'bottom':gb,
                                  'mid':(gt+gb)/2,'strength':min(3,st),'index':i,'th':th})
            elif c['c'] < c['o']:
                gt,gb = max(p['h'],n['h']),min(p['l'],n['l'])
                if gt>gb and gt-gb>avg_r*th:
                    st = 1+(1 if bd>(gt-gb)*2 else 0)+(1 if gt-gb>avg_r*0.5 else 0)
                    all_s.append({'type':'BearFVG','direction':'short','top':gt,'bottom':gb,
                                  'mid':(gt+gb)/2,'strength':min(3,st),'index':i,'th':th})
    seen = {}
    for s in all_s:
        k = (s['index'], s['direction'])
        if k not in seen or s['strength'] > seen[k]['strength']:
            seen[k] = s
    return list(seen.values())


def detect_sweep_multi(bars):
    """5回看周期Sweep"""
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


def detect_choch_wide(bars):
    """多窗口CHOCH检测 — 用多个lookback"""
    from smc_engine import detect_choch_v2
    results = []
    for lb in [8, 12, 15, 20]:
        c = detect_choch_v2(bars, lookback=lb)
        if c.get('detected'):
            c['lookback'] = lb
            results.append(c)
    if not results:
        return {'detected': False}
    # 取多数方向
    dirs = [r['direction'] for r in results]
    majority = max(set(dirs), key=dirs.count)
    return {'detected': True, 'direction': majority,
            'count': len(results), 'total_lookbacks': 4}


def detect_entries_v3_2(bars):
    """V3.2 入口检测 — 多阈值共振 + 时间加权"""
    results = []
    if len(bars) < 50:
        return results
    
    from smc_engine import calc_atr, detect_market_structure, detect_order_blocks
    
    fvg_list = detect_fvg_multi(bars)
    sweep_list = detect_sweep_multi(bars)
    ob_list = detect_order_blocks(bars)
    choch_wide = detect_choch_wide(bars)
    ms = detect_market_structure(bars, 15)
    
    if not fvg_list:
        return results
    
    last_idx = len(bars) - 1
    
    # 对每个FVG (最近15个)
    for fvg in fvg_list[-15:]:
        fvg_idx = fvg.get('index', 0)
        if fvg_idx < 3 or fvg_idx >= last_idx - 2:
            continue
        
        direction = fvg['direction']
        
        # 计算FVG的时间权重 (越近权重越高)
        age = last_idx - fvg_idx
        if age > 25:
            continue  # 太老的FVG忽略
        time_weight = max(0.5, 1.0 - age / 25.0 * 0.5)
        
        # ---- 信号共振 ----
        signals_found = {'fvg': True}
        score = 1.0  # FVG
        score_parts = ['FVG']
        
        # Sweep (距离FVG -3~+12根)
        sw = [s for s in sweep_list if s['direction'] == direction 
              and -3 <= fvg_idx - s.get('index',0) <= 12]
        if sw:
            best_sw = max(sw, key=lambda s: s.get('wick_ratio',0))
            signals_found['sweep'] = True
            sw_score = min(2.0, best_sw.get('wick_ratio',1.0) * 0.6)
            score += sw_score
            score_parts.append(f'SW({best_sw["wick_ratio"]:.1f})')
        
        # OB (距离FVG -3~+10根)
        if any(o['direction'] == direction and abs(o.get('index',0)-fvg_idx) <= 10
               for o in ob_list):
            signals_found['ob'] = True
            score += 1.0
            score_parts.append('OB')
        
        # CHOCH
        if choch_wide.get('detected') and choch_wide['direction'] == direction:
            signals_found['choch'] = True
            c_score = 1.5 + (choch_wide.get('count',1) / 4.0) * 1.0  # 1.5-2.5
            score += c_score
            score_parts.append('CH')
        
        # Market structure alignment
        if ms.get('direction') == direction:
            signals_found['ms'] = True
            score += 0.5
            score_parts.append('MS')
        
        # FVG强度
        if fvg.get('strength',1) >= 2:
            score += 0.5
        
        # 确认K线
        ci = min(fvg_idx + 1, last_idx - 1)
        if ci > 0:
            cb = bars[ci]
            if direction == 'long' and cb['c'] > cb['o']:
                score += 0.5
                score_parts.append('CF')
            elif direction == 'short' and cb['c'] < cb['o']:
                score += 0.5
                score_parts.append('CF')
        
        # 时间加权
        score *= time_weight
        
        # 入场门槛: 加权score >= 3.0 (约等于2-3个信号)
        min_signals = sum(1 for v in signals_found.values() if v)
        if score >= 3.0 and min_signals >= 2:
            atr = calc_atr(bars[:fvg_idx + 5])
            entry_price = fvg['mid']
            
            # 自适应SL/TP: 基于ATR和信号强度
            signal_strength = min(1.0, score / 6.0)
            sl_atr = 2.0 - signal_strength * 0.8  # 强信号→紧止损
            tp_atr = 2.5 + signal_strength * 1.0  # 强信号→远止盈
            
            if direction == 'long':
                sl = entry_price - atr * sl_atr
                tp = entry_price + atr * tp_atr
            else:
                sl = entry_price + atr * sl_atr
                tp = entry_price - atr * tp_atr
            
            results.append({
                'entry_idx': min(fvg_idx + 1, last_idx - 1),
                'direction': direction,
                'entry_price': round(entry_price, 4),
                'sl': round(sl, 4),
                'tp': round(tp, 4),
                'signals': score_parts,
                'signal_count': len(score_parts),
                'signal_score': round(score, 2),
                'fvg_idx': fvg_idx,
            })
    
    return results


def backtest_v3_2(bars, only_long=False):
    entries = detect_entries_v3_2(bars)
    trades = []
    for entry in entries:
        if only_long and entry['direction'] != 'long':
            continue
        ei = entry['entry_idx']
        if ei >= len(bars):
            continue
        d = entry['direction']
        ep = entry['entry_price']
        sl = entry['sl']
        tp = entry['tp']
        sigs = entry.get('signals',[])
        
        for i in range(ei, len(bars)):
            b = bars[i]
            if d == 'long':
                if b['l'] <= sl:
                    trades.append({'pnl':(sl-ep)/ep,'reason':'sl','dir':'L','ep':ep,'signals':sigs})
                    break
                if b['h'] >= tp:
                    trades.append({'pnl':(tp-ep)/ep,'reason':'tp','dir':'L','ep':ep,'signals':sigs})
                    break
            else:
                if b['h'] >= sl:
                    trades.append({'pnl':(ep-sl)/ep,'reason':'sl','dir':'S','ep':ep,'signals':sigs})
                    break
                if b['l'] <= tp:
                    trades.append({'pnl':(ep-tp)/ep,'reason':'tp','dir':'S','ep':ep,'signals':sigs})
                    break
        else:
            last = bars[-1]['c']
            pnl = (last-ep)/ep if d=='long' else (ep-last)/ep
            trades.append({'pnl':pnl,'reason':'eod','dir':d,'ep':ep,'signals':sigs})
    return trades


def evaluate_v3_2(trades, name='V3.2'):
    from smc_backtest_v2 import compute_sharpe
    n = len(trades)
    if n == 0:
        print(f"  {name}: 0 trades")
        return {'trades':0,'wr':0,'sr':0}
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    wr = len(wins)/n*100
    ret = sum(t['pnl'] for t in trades)*100
    pf = abs(sum(t['pnl'] for t in wins)/sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses)!=0 else 10
    returns = [t['pnl'] for t in trades]
    sr = compute_sharpe(returns, 252)
    print(f"  {name}: {n}t WR={wr:.1f}% SR={sr:.2f} PF={pf:.2f} Ret={ret:+.1f}%")
    
    # Signal breakdown
    sc = Counter()
    for t in trades:
        sn = len(t.get('signals',[]))
        sc[sn] += 1
    for cnt, freq in sc.most_common():
        print(f"    {cnt} sigs: {freq}t")
    
    return {'trades':n,'wr':wr,'sr':sr,'pf':pf,'ret':ret}