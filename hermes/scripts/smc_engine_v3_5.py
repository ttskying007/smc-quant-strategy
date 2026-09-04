#!/usr/bin/env python3
"""
SMC Engine v3.5 — 基于V3.2核心，仅降低门槛至2.5
其他所有逻辑保持与V3.2完全相同

目的: 精确量化score门槛降低对信号量的影响
"""
import sys, os, math
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
sys.path.insert(0, os.path.expanduser('~/.hermes/skills/trading/smc-engine/scripts'))

# Import V3.2 fully
from smc_engine_v3_2 import (detect_fvg_multi, detect_sweep_multi, detect_choch_wide,
                               detect_order_blocks, detect_market_structure, calc_atr,
                               backtest_v3_2 as backtest_v32_original)
import smc_engine_v3_2 as v32_module


def backtest_v3_5(bars, only_long=False):
    """
    V3.5: V3.2核心 + score门槛从3.0降至2.5
    """
    from smc_engine_v3_2 import (
        detect_fvg_multi, detect_sweep_multi, detect_order_blocks,
        detect_market_structure, detect_choch_multi, calc_atr
    )
    
    if len(bars) < 50:
        return []
    
    fvg_list = detect_fvg_multi(bars)
    sweep_list = detect_sweep_multi(bars)
    ob_list = detect_order_blocks(bars)
    choch_wide = detect_choch_multi(bars)
    ms = detect_market_structure(bars, 15)
    
    if not fvg_list:
        return []
    
    last_idx = len(bars) - 1
    results = []
    
    for fvg in fvg_list[-15:]:
        i = fvg.get('index', 0)
        if i < 3 or i >= last_idx - 2:
            continue
        
        age = last_idx - i
        if age > 25:
            continue
        
        direction = fvg['direction']
        tw = max(0.5, 1.0 - age / 25.0 * 0.5)
        
        signals_found = {'fvg': True}
        score = 1.0
        score_parts = ['FVG']
        
        # Sweep
        sw = [s for s in sweep_list if s['direction'] == direction 
              and -3 <= i - s.get('index', 0) <= 12]
        if sw:
            score += min(2.0, max(sw, key=lambda s: s.get('wick_ratio',1)).get('wick_ratio',1) * 0.6)
            signals_found['sw'] = True
            score_parts.append('SW')
        
        # OB
        if any(o['direction'] == direction and abs(o.get('index', 0)-i) <= 10 for o in ob_list):
            score += 1.0
            signals_found['ob'] = True
            score_parts.append('OB')
        
        # CHOCH
        if choch_wide.get('detected') and choch_wide['direction'] == direction:
            c_score = 1.5 + (choch_wide.get('count', 1) / 4.0) * 1.0
            score += c_score
            signals_found['ch'] = True
            score_parts.append('CH')
        
        # MS
        if ms.get('direction') == direction:
            score += 0.5
            signals_found['ms'] = True
            score_parts.append('MS')
        
        # FVG strength
        if fvg.get('strength', 1) >= 2:
            score += 0.5
            score_parts.append('ST')
        
        # Confirm
        ci = min(i + 1, last_idx - 1)
        if ci > 0 and i < len(bars):
            cb = bars[ci]
            if (direction == 'long' and cb['c'] > cb['o']) or (direction == 'short' and cb['c'] < cb['o']):
                score += 0.5
                score_parts.append('CF')
        
        score *= tw
        n_sig = sum(1 for v in signals_found.values() if v)
        
        # === V3.5 核心: V3.2逻辑, 门槛从3.0降至2.5 ===
        if score >= 2.5 and n_sig >= 2:
            atr = calc_atr(bars[:i + 5])
            ep = fvg['mid']
            ss = min(1.0, score / 6.0)
            sl_a = 2.0 - ss * 0.8
            tp_a = 2.5 + ss * 1.0
            
            if direction == 'long':
                results.append({
                    'idx': min(i + 1, last_idx - 1),
                    'dir': 'L',
                    'ep': round(ep, 4),
                    'sl': round(ep - atr * sl_a, 4),
                    'tp': round(ep + atr * tp_a, 4),
                    'sigs': score_parts,
                    'sc': round(score, 2),
                })
            else:
                results.append({
                    'idx': min(i + 1, last_idx - 1),
                    'dir': 'S',
                    'ep': round(ep, 4),
                    'sl': round(ep + atr * sl_a, 4),
                    'tp': round(ep - atr * tp_a, 4),
                    'sigs': score_parts,
                    'sc': round(score, 2),
                })
    
    # 5根K线去重
    sorted_r = sorted(results, key=lambda r: -r['sc'])
    final = []
    for r in sorted_r:
        if not any(abs(r['idx'] - f['idx']) <= 5 and r['dir'] == f['dir'] for f in final):
            final.append(r)
    
    # Simulate
    trades = []
    for e in final:
        ei = e['idx']
        if ei >= len(bars):
            continue
        d, ep, sl, tp = e['dir'], e['ep'], e['sl'], e['tp']
        
        for j in range(ei, len(bars)):
            b = bars[j]
            if d == 'L':
                if b['l'] <= sl:
                    trades.append({'pnl':(sl-ep)/ep, 'sig':e.get('sigs',[]), 'sc':e.get('sc',0)})
                    break
                if b['h'] >= tp:
                    trades.append({'pnl':(tp-ep)/ep, 'sig':e.get('sigs',[]), 'sc':e.get('sc',0)})
                    break
            else:
                if b['h'] >= sl:
                    trades.append({'pnl':(ep-sl)/ep, 'sig':e.get('sigs',[]), 'sc':e.get('sc',0)})
                    break
                if b['l'] <= tp:
                    trades.append({'pnl':(ep-tp)/ep, 'sig':e.get('sigs',[]), 'sc':e.get('sc',0)})
                    break
        else:
            l = bars[-1]['c']
            trades.append({'pnl':(l-ep)/ep if d=='L' else (ep-l)/ep, 'sig':e.get('sigs',[]), 'sc':e.get('sc',0)})
    
    return trades


def evaluate(trades, name='V3.5'):
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


if __name__ == '__main__':
    # Quick test
    from smc_backtest_v2 import fetch_klines, normalize_klines
    from smc_engine_v3_2 import backtest_v3_2
    
    stocks = ['600519.SH','000001.SZ','000858.SZ','600036.SH']
    v32n = 0; v35n = 0
    
    for code in stocks:
        bars = normalize_klines(fetch_klines(code, 'daily', 500))
        v32t = backtest_v3_2(bars)
        v35t = backtest_v3_5(bars)
        print(f"  {code}: V3.2={len(v32t)}t V3.5={len(v35t)}t")
        v32n += len(v32t); v35n += len(v35t)
    
    print(f"\n  Total: V3.2={v32n} V3.5={v35n} mul={v35n/max(1,v32n):.1f}x")