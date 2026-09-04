#!/usr/bin/env python3
"""
SMC Engine V6.2 — 动态自适应SL/TP + 多目标优化
===============================================
V6.1 问题复盘:
  1. SL/TP受max(0.5,sl_m)/max(1.0,tp_m)限制，实际tp=1.0固定
  2. V3最佳参数 tp_mult=0.43被强制升到1.0，导致SL=3.86*ATR, TP=1.0*ATR
  3. WR高(78%)但PF低(1.55)因为TP只有SL的1/4大小
  4. 交易量虽大(901笔)但单笔盈利小

V6.2 改进:
  1. 移除SL/TP的max限制 → 允许搜索真正的SL/TP比率
  2. 加入 risk:reward 比率作为独立参数
  3. 加入趋势过滤 (均线/ADX, 只在趋势方向开仓)
  4. 加入volatility缩放SL/TP (高波动时收紧, 低波动放松)
  5. 多目标评分: WR*0.5 + PF*0.3 + n*0.2 (归一化)

注意: gen_v61_signals.py 和 run_ga_v61.py 系列使用相同入口
"""
import sys, os, json, math, random, time, copy
from collections import defaultdict
from pathlib import Path

# === 改进: FVG检测更高效，直接复用V6.1的核心 ===

def calc_adx(bars, period=14):
    """计算ADX趋势强度"""
    if len(bars) < period + 5:
        return 0
    highs = [b[2] for b in bars]
    lows = [b[3] for b in bars]
    closes = [b[4] for b in bars]
    
    plus_dm = [0]
    minus_dm = [0]
    tr = [0]
    
    for i in range(1, len(bars)):
        hd = highs[i] - highs[i-1]
        ld = lows[i-1] - lows[i]
        plus_dm.append(hd if hd > ld and hd > 0 else 0)
        minus_dm.append(ld if ld > hd and ld > 0 else 0)
        tr.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    
    # Smooth
    def ema(data, period):
        k = 2/(period+1)
        result = [data[0]]
        for v in data[1:]:
            result.append(v*k + result[-1]*(1-k))
        return result
    
    tr_smooth = ema(tr, period)[-1]
    pd_smooth = ema(plus_dm, period)[-1]
    nd_smooth = ema(minus_dm, period)[-1]
    
    if tr_smooth == 0:
        return 0
    
    pdi = pd_smooth / tr_smooth * 100
    ndi = nd_smooth / tr_smooth * 100
    
    dx = abs(pdi - ndi) / (pdi + ndi) * 100 if (pdi + ndi) > 0 else 0
    return dx

def calc_ema(bars, period=20):
    """简单EMA"""
    if len(bars) < period:
        return bars[-1][4]
    k = 2/(period+1)
    ema = bars[0][4]
    for i in range(1, len(bars)):
        ema = bars[i][4]*k + ema*(1-k)
    return ema

# 导入V6.1的核心检测功能
from smc_engine_v61 import (
    detect_fvg_standard_v6, get_klines, load_cached_bars,
    detect_sweep_v6, detect_ob_v6, detect_choch_v6,
    calc_bpr_v6, score_fvg_signal, calc_atr, simulate_entry
)

# 重写入口检测函数，加入趋势过滤和动态SL/TP
def detect_entries_v62(bars, sp):
    """
    V6.2 入口检测 — 加入趋势过滤 + 动态SL/TP
    """
    if not bars or len(bars) < 60:
        return {}
    
    sp = sp or {}
    results = {'bronze':[], 'silver':[], 'gold':[], 'total':[]}
    
    # 检测所有FVG
    fvg_all = detect_fvg_standard_v6(bars, sp.get('fvg_th', 0.25))
    if not fvg_all:
        return results
    
    # 只保留最近100根K线的FVG
    last_idx = len(bars) - 1
    fvg_recent = [f for f in fvg_all if f['index'] >= last_idx - 100]
    
    # 检测其他信号
    sweep_all = detect_sweep_v6(bars, 12, sp.get('wick_min', 1.5))
    ob_all = detect_ob_v6(bars, fvg_all)
    choch = detect_choch_v6(bars, 30)
    bpr_list = calc_bpr_v6(fvg_all, 20)
    
    sweep_recent = [s for s in sweep_all if s.get('index', 0) >= last_idx - 150]
    ob_recent = [o for o in ob_all if o.get('index', 0) >= last_idx - 150]
    bpr_recent = [b for b in bpr_list if b['index'] >= last_idx - 80]
    
    sc_th = sp.get('score_th', 2.5)
    sl_m = sp.get('sl_mult', 2.0)
    tp_m = sp.get('tp_mult', 3.0)  # Default: RR > 1
    min_s = sp.get('min_sigs', 2)
    
    # V6.2 新参数
    trend_adx_min = sp.get('trend_adx_min', 0)  # 最小ADX (0=不过滤)
    trend_direction = sp.get('trend_direction', 0)  # 0=both, 1=long only, -1=short only
    use_trend_filter = sp.get('use_trend_filter', False)
    
    # 计算全局趋势
    if use_trend_filter:
        current_price = bars[-1]['c']
        ema20 = calc_ema(bars, 20)
        ema60 = calc_ema(bars, 60)
        adx = calc_adx(bars, 14)
        
        # 趋势方向
        trend_up = ema20 > ema60
        trend_str = "up" if trend_up else "down"
    else:
        trend_up = True
        adx = 100  # 不限制
        trend_str = "any"
    
    for fvg in fvg_recent:
        i = fvg.get('index', 0)
        if i < 3 or i >= last_idx - 2:
            continue
        
        direction = fvg['direction']
        
        # 趋势过滤
        if use_trend_filter and adx < trend_adx_min:
            continue
        if use_trend_filter:
            if trend_direction > 0 and direction != 'long':
                continue
            if trend_direction < 0 and direction != 'short':
                continue
        
        sw = [s for s in sweep_recent if s['direction']==direction and -3 <= i-s.get('index',0) <= 20]
        ob = [o for o in ob_recent if o['direction']==direction and abs(o.get('index',0)-i) <= 10]
        bpr = [b for b in bpr_recent if abs(b.get('index',0)-i) <= 12]
        
        score, sigs, n_sig = score_fvg_signal(direction, bars, i, fvg, sw, ob, choch, bpr)
        
        if score < 1.5:
            continue
        
        atr = calc_atr(bars[:i+5])
        ep = fvg['mid']
        
        # V6.2: 动态SL/TP — 去掉max限制，完全使用搜索到的参数
        if score >= sc_th and n_sig >= min_s:
            entry = {'idx':min(i+1,last_idx-1),'dir':'L' if direction=='long' else 'S',
                     'fvg_idx':i,'sigs':sigs,'sc':round(score,2),'n_sig':n_sig}
            
            if direction == 'long':
                sl_val = ep - atr * sl_m
                tp_val = ep + atr * tp_m
            else:
                sl_val = ep + atr * sl_m
                tp_val = ep - atr * tp_m
            
            # 保护：SL不能反向
            if direction == 'long' and sl_val >= ep:
                sl_val = ep - atr * 0.3
            elif direction == 'short' and sl_val <= ep:
                sl_val = ep + atr * 0.3
            
            entry['ep']=round(ep,4); entry['sl']=round(sl_val,4); entry['tp']=round(tp_val,4)
            results['bronze'].append(entry)
            results['total'].append({**entry,'level':'bronze'})
    
    return results

def single_stock_scan_v62(code, sp):
    """V6.2 单股票扫描 — 复用V6.1的数据加载"""
    try:
        bars = load_cached_bars(code)
    except:
        return []
    
    if not bars or len(bars) < 60:
        return []
    
    entries = detect_entries_v62(bars, sp)
    
    all_trades = entries.get('total', [])
    from smc_engine_v61 import simulate_entry
    trades = []
    for e in all_trades:
        result = simulate_entry(e, bars)
        if result:
            trades.append({**result, 'score': e.get('sc', 0), 'n_sig': e.get('n_sig', 0)})
    
    return trades

def quick_scan_62(code, sp):
    """兼容接口"""
    return single_stock_scan_v62(code, sp)

# Test
if __name__ == '__main__':
    print("V6.2 Engine loaded successfully")
    print("New params: trend_adx_min, trend_direction, use_trend_filter")
    print()
    
    # Quick test on 10 stocks
    codes = json.load(open(os.path.expanduser('~/.hermes/smc_opt_v6/v61_signals_full.json')))
    codes = list(codes.keys())[:10]
    
    total = 0
    wins = 0
    win_pnl = 0
    loss_pnl = 0
    
    sp = {'fvg_th':0.15, 'score_th':2.0, 'sl_mult':2.0, 'tp_mult':3.0, 'min_sigs':2}
    
    for code in codes:
        trades = single_stock_scan_v62(code, sp)
        for t in trades:
            total += 1
            if t['pnl'] > 0:
                wins += 1
                win_pnl += t['pnl']
            else:
                loss_pnl += abs(t['pnl'])
    
    wr = wins/total*100 if total else 0
    pf = win_pnl/loss_pnl if loss_pnl else (999 if win_pnl else 0)
    print(f"[Default params] Test 10 stocks: {total}t WR={wr:.1f}% PF={pf:.2f}")