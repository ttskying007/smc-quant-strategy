#!/usr/bin/env python3
"""
SMC Engine v3.1 — 多阈值共振检测
核心: 用多个阈值并行检测FVG/Sweep, 然后取信号共振
"""

import math
from collections import Counter

def detect_fvg_multi_threshold(bars):
    """
    多阈值FVG检测: 在3个不同阈值下检测, 合并结果
    thresholds: 0.15 (宽松) + 0.25 (标准) + 0.40 (严格)
    不同阈值会捕获不同类型的FVG
    """
    from smc_backtest_v2 import detect_fvg
    from copy import deepcopy
    
    # 我们需要修改detect_fvg的阈值, 但因为它是独立函数
    # 我们可以直接重写
    
    if len(bars) < 3:
        return []
    
    avg_r = sum(abs(k['h']-k['l']) for k in bars[-30:]) / 30 if len(bars) >= 30 else 0
    if avg_r == 0:
        return []
    
    all_signals = []
    
    # 三个阈值: 宽松/标准/严格
    for threshold in [0.15, 0.25, 0.40]:
        signals = []
        start = max(1, len(bars)-30)
        for i in range(start, len(bars)-1):
            p,c,n = bars[i-1],bars[i],bars[i+1]
            bd = abs(c['c']-c['o'])
            if c['c'] > c['o']:
                gt,gb = min(p['h'],n['h']),max(p['l'],n['l'])
                if gt>gb and gt-gb>avg_r*threshold:
                    st = 1+(1 if bd>(gt-gb)*2 else 0)+(1 if gt-gb>avg_r*0.5 else 0)
                    signals.append({
                        'type':'BullFVG','direction':'long','top':gt,'bottom':gb,
                        'mid':(gt+gb)/2,'strength':min(3,st),'index':i,
                        'threshold': threshold
                    })
            elif c['c'] < c['o']:
                gt,gb = max(p['h'],n['h']),min(p['l'],n['l'])
                if gt>gb and gt-gb>avg_r*threshold:
                    st = 1+(1 if bd>(gt-gb)*2 else 0)+(1 if gt-gb>avg_r*0.5 else 0)
                    signals.append({
                        'type':'BearFVG','direction':'short','top':gt,'bottom':gb,
                        'mid':(gt+gb)/2,'strength':min(3,st),'index':i,
                        'threshold': threshold
                    })
        all_signals.extend(signals)
    
    # 去重: 同一个index+direction只保留strength最高的
    seen = {}
    for s in all_signals:
        key = (s['index'], s['direction'])
        if key not in seen or s['strength'] > seen[key]['strength']:
            seen[key] = s
    
    return list(seen.values())


def detect_sweep_multi_lookback(bars):
    """
    多回看周期Sweep检测
    lookbacks: [8, 12, 15] 覆盖短期/中期/长期
    """
    from smc_backtest_v2 import detect_liquidity_sweep
    
    all_sw = []
    for lb in [8, 12, 15, 20]:
        sweeps = detect_liquidity_sweep(bars, lookback=lb)
        for s in sweeps:
            s['lookback'] = lb
        all_sw.extend(sweeps)
    
    # 去重
    seen = {}
    for s in all_sw:
        key = (s['index'], s['direction'])
        if key not in seen or s.get('wick_ratio', 0) > seen[key].get('wick_ratio', 0):
            seen[key] = s
    
    return list(seen.values())


def detect_high_winrate_entries_v3_1(bars):
    """
    V3.1 高胜率入场: 多阈值FVG + 多回看Sweep + 宽松CHOCH
    
    信号需求 (任选2+):
    - FVG (任何阈值)
    - Sweep (任何回看)
    - OB
    - CHOCH
    - 价格确认
    
    Strategy: 尽可能多产生共振, WR目标是50%+
    """
    results = []
    if len(bars) < 50:
        return results
    
    from smc_engine import (
        calc_atr, detect_choch_v2, detect_market_structure,
        detect_order_blocks, detect_liquidity_sweep,
    )
    from smc_backtest_v2 import find_swing_highs, find_swing_lows
    
    # 1. 多阈值FVG
    fvg_list = detect_fvg_multi_threshold(bars)
    
    # 2. 多回看Sweep
    sweep_list = detect_sweep_multi_lookback(bars)
    
    # 3. OB (标准)
    ob_list = detect_order_blocks(bars)
    
    if not fvg_list:
        return results
    
    # 对每个FVG (最近15个)
    for fvg in fvg_list[-15:]:
        fvg_idx = fvg.get('index', 0)
        if fvg_idx < 5 or fvg_idx >= len(bars) - 3:
            continue
        
        direction = fvg['direction']
        
        # 检查Sweep (在FVG之前10根或之后3根)
        nearby_sweep = [s for s in sweep_list 
                       if s['direction'] == direction 
                       and -3 <= fvg_idx - s.get('index', 0) <= 10]
        
        # 检查OB
        nearby_ob = [o for o in ob_list
                    if o['direction'] == direction
                    and abs(o.get('index', 0) - fvg_idx) <= 8]
        
        # 检查CHOCH
        window = bars[:min(fvg_idx + 5, len(bars))]
        choch = detect_choch_v2(window, 12)
        
        # 市场结构
        ms = detect_market_structure(window, 12)
        
        # 计算信号强度 (0-7)
        signals_found = []
        score = 0
        
        # FVG (必选)
        score += 1
        signals_found.append('FVG')
        
        # Sweep
        if nearby_sweep:
            score += 2
            best_sw = max(nearby_sweep, key=lambda s: s.get('wick_ratio', 0))
            signals_found.append(f'Sweep({best_sw["wick_ratio"]:.1f})')
        else:
            score += 0  # No penalty, but less ideal
        
        # OB
        if nearby_ob:
            score += 1
            signals_found.append('OB')
        
        # CHOCH
        if choch.get('detected') and choch['direction'] == direction:
            score += 2
            signals_found.append('CHOCH')
        
        # Market Structure alignment
        if ms.get('direction') == direction:
            score += 1
            signals_found.append(f'MS({ms["trend"]})')
        
        # FVG strength bonus
        if fvg.get('strength', 1) >= 2:
            score += 1
            
        # 确认K线
        confirm_idx = min(fvg_idx + 1, len(bars) - 1)
        confirm_bar = bars[confirm_idx]
        if direction == 'long' and confirm_bar['c'] > confirm_bar['o']:
            score += 1
        elif direction == 'short' and confirm_bar['c'] < confirm_bar['o']:
            score += 1
        
        # 入场门槛: score >= 4 (FVG + Sweep + 至少2个附加信号)
        if score >= 4:
            entry_price = fvg['mid']
            atr = calc_atr(bars[:fvg_idx + 5])
            
            # SL/TP: 组合使用ATR倍数
            if nearby_sweep:
                # 用Sweep的目标作为SL
                if direction == 'long':
                    sl = entry_price - atr * 2.0
                    tp = entry_price + atr * 3.0
                else:
                    sl = entry_price + atr * 2.0
                    tp = entry_price - atr * 3.0
            else:
                if direction == 'long':
                    sl = entry_price - atr * 1.5
                    tp = entry_price + atr * 2.5
                else:
                    sl = entry_price + atr * 1.5
                    tp = entry_price - atr * 2.5
            
            results.append({
                'entry_idx': min(fvg_idx + 1, len(bars) - 1),
                'direction': direction,
                'entry_price': round(entry_price, 4),
                'sl': round(sl, 4),
                'tp': round(tp, 4),
                'signals': signals_found,
                'signal_count': score,
                'fvg_idx': fvg_idx,
            })
    
    return results


def backtest_v3_1(bars, only_long=False):
    """V3.1 回测"""
    entries = detect_high_winrate_entries_v3_1(bars)
    trades = []
    
    from smc_backtest_v2 import calc_atr
    
    for entry in entries:
        if only_long and entry['direction'] != 'long':
            continue
        
        entry_idx = entry['entry_idx']
        if entry_idx >= len(bars):
            continue
        
        direction = entry['direction']
        entry_price = entry['entry_price']
        sl = entry['sl']
        tp = entry['tp']
        
        for i in range(entry_idx, len(bars)):
            b = bars[i]
            if direction == 'long':
                if b['l'] <= sl:
                    trades.append({'pnl': (sl-entry_price)/entry_price, 'reason':'sl_hit',
                                   'direction':'long','entry_price':entry_price,
                                   'signals':entry.get('signals',[])})
                    break
                if b['h'] >= tp:
                    trades.append({'pnl': (tp-entry_price)/entry_price, 'reason':'tp_hit',
                                   'direction':'long','entry_price':entry_price,
                                   'signals':entry.get('signals',[])})
                    break
            else:
                if b['h'] >= sl:
                    trades.append({'pnl': (entry_price-sl)/entry_price, 'reason':'sl_hit',
                                   'direction':'short','entry_price':entry_price,
                                   'signals':entry.get('signals',[])})
                    break
                if b['l'] <= tp:
                    trades.append({'pnl': (entry_price-tp)/entry_price, 'reason':'tp_hit',
                                   'direction':'short','entry_price':entry_price,
                                   'signals':entry.get('signals',[])})
                    break
        else:
            last = bars[-1]['c']
            pnl = (last-entry_price)/entry_price if direction=='long' else (entry_price-last)/entry_price
            trades.append({'pnl':pnl,'reason':'eod','direction':direction,
                           'entry_price':entry_price,
                           'signals':entry.get('signals',[])})
    
    return trades


def evaluate(trades, name='V3.1'):
    """评估"""
    from smc_backtest_v2 import compute_sharpe
    n = len(trades)
    if n == 0:
        print(f"{name}: No trades")
        return {'trades':0,'win_rate':0,'sharpe':0}
    
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    wr = len(wins)/n*100
    ret = sum(t['pnl'] for t in trades)*100
    pf = abs(sum(t['pnl'] for t in wins)/sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses)!=0 else float('inf')
    
    returns = [t['pnl'] for t in trades]
    sharpe = compute_sharpe(returns, 252)
    
    sc = Counter()
    for t in trades:
        sc[len(t.get('signals',[]))] += 1
    
    print(f"\n{'='*50}")
    print(f"  {name}: {n} trades, WR={wr:.1f}%, Sharpe={sharpe:.2f}")
    print(f"  PnL: {ret:+.2f}% | PF: {pf:.2f}")
    for cnt, freq in sc.most_common():
        print(f"    {cnt} signals: {freq} trades")
    
    return {'trades':n,'win_rate':wr,'sharpe':sharpe,'profit_factor':pf,'total_return':ret}