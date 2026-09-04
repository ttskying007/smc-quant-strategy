#!/usr/bin/env python3
"""V37 — V36 Core + Liquidity Context Filter
============================================
在V36经过验证的核心引擎上叠加流动性分析:

架构:
  V36核心 (FVG Bull-only, confirmed_at入场, tight SL+trailing)
  + 流动性上下文过滤 (仅在流动性猎杀后或接近流动性区域的交易加分)
  + 周线多周期对齐
  + 信号时序评分 (MSS/CHOCH层级)

关键: 不改动V36已验证的SL/TP/退出逻辑, 只在入场过滤层增加维度。
"""

import json, sys, math, time, random
from pathlib import Path
from collections import Counter
from typing import List, Dict, Optional

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.liquidity_v37 import (
    detect_liquidity_zones, calc_adaptive_windows_v37,
    enhance_signals_with_liquidity,
)

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v37')
OUTPUT_DIR.mkdir(exist_ok=True)

MAX_STOCKS = 200
MIN_BARS = 120
SWING_MAX_DIST = 30
MAX_HOLD = 60


def load_ohlcv(symbol: str) -> Optional[List[Dict]]:
    fname = f"{symbol.replace('.','_')}_daily_300.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists():
        return None
    data = json.loads(fpath.read_text())
    if not data or len(data) < MIN_BARS:
        return None
    for bar in data:
        if 'date' not in bar and 't' in bar:
            bar['date'] = str(bar['t'])
    return data


def calc_atr(ohlcv, idx, period=14):
    if idx < period + 1:
        return (ohlcv[idx]['h'] - ohlcv[idx]['l']) / ohlcv[idx]['l'] * 100
    trs = []
    for i in range(max(1, idx - period), idx + 1):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    avg_tr = sum(trs) / len(trs)
    return avg_tr / ohlcv[idx]['l'] * 100


def find_swing_lows(ohlcv, end_idx, lookback=60):
    if end_idx < 3:
        return []
    start = max(0, end_idx - lookback)
    swings = []
    for i in range(end_idx - 1, start, -1):
        b = ohlcv[i]
        l = ohlcv[i-1] if i > start else None
        r = ohlcv[i+1] if i < end_idx - 1 else None
        lv = l['l'] if l else 9999
        rv = r['l'] if r else 9999
        if b['l'] < lv and b['l'] < rv:
            swings.append((i, b['l'], end_idx - i))
    return swings


def find_best_swing_sl(ohlcv, end_idx, entry_price):
    swings = find_swing_lows(ohlcv, end_idx)
    swings = [s for s in swings if s[2] <= SWING_MAX_DIST]
    if not swings:
        return None
    best, bs = None, 999
    for idx, price, dist in swings:
        capped = min(price, entry_price * (1 - 0.5 / 100))
        sp = (entry_price - capped) / entry_price * 100
        if 0.10 <= sp <= 0.70:
            sc = abs(sp - 0.35) * 0.4 + (dist / SWING_MAX_DIST) * 0.6
            if sc < bs:
                bs = sc
                best = (capped, 'swing', idx)
    return best


def calc_trailing_v36(entry_price, current_price, direction):
    if direction == 'bull':
        gain = (current_price - entry_price) / entry_price * 100
        if gain < 0.2:
            return None  # 保本: 不变
        if gain < 0.5:
            return entry_price  # 保本
        if gain < 1.0:
            return entry_price * 1.002
        if gain < 2.0:
            return entry_price * 1.005
        if gain < 4.0:
            return entry_price * 1.01
        return entry_price * 1.02
    return None


def short_trend(ohlcv, idx, lookback=10):
    if idx < lookback:
        return 'neutral', 0
    seg = ohlcv[idx-lookback:idx+1]
    s, e = seg[0]['c'], seg[-1]['c']
    change = (e - s) / s * 100
    ema = sum(ohlcv[i]['c'] for i in range(idx-min(5,idx), idx+1)) / min(6, idx+1)
    ema_d = (ohlcv[idx]['c'] - ema) / ema * 100
    if change > 0.6 and ema_d > 0:
        return 'up', change
    if change < -0.6 and ema_d < 0:
        return 'down', abs(change)
    return 'neutral', 0


def calc_weekly_context(ohlcv, idx):
    """周线上下文 — 方向 + 价格位置"""
    if idx < 20:
        return {'trend': 'neutral', 'pos': 'middle', 'score': 0.5}
    
    weekly_close = [ohlcv[i]['c'] for i in range(max(0, idx-60), idx+1, 5)]
    if len(weekly_close) < 4:
        return {'trend': 'neutral', 'pos': 'middle', 'score': 0.5}
    
    w_trend = 'up' if weekly_close[-1] > weekly_close[0] * 1.02 else \
              'down' if weekly_close[-1] < weekly_close[0] * 0.98 else 'neutral'
    
    w_high = max(ohlcv[i]['h'] for i in range(max(0, idx-30), idx+1))
    w_low = min(ohlcv[i]['l'] for i in range(max(0, idx-30), idx+1))
    
    if w_high == w_low:
        return {'trend': w_trend, 'pos': 'middle', 'score': 0.5}
    
    pos = (ohlcv[idx]['c'] - w_low) / (w_high - w_low)
    
    at_level = 'support' if pos < 0.2 else 'resistance' if pos > 0.8 else 'middle'
    
    score = 0.5
    if (w_trend == 'up' and at_level == 'support') or \
       (w_trend == 'up' and at_level == 'middle'):
        score = 0.75
    elif w_trend == 'up' and at_level == 'resistance':
        score = 0.55
    elif w_trend == 'down' and at_level == 'resistance':
        score = 0.40
    elif w_trend == 'down' and at_level == 'support':
        score = 0.30
    
    return {'trend': w_trend, 'pos': at_level, 'score': score}


# ═══════════════════════════════════════════════════════════════════════
# V37 入场评分 (V36核心 + 流动性上下文过滤)
# ═══════════════════════════════════════════════════════════════════════

def score_entry_v37(all_signals, liquidity_result, weekly_ctx, idx, direction):
    """V37综合入场评分
    
    在V36 FVG Bull-only基础上增加:
    1. 流动性上下文: 猎杀后FVG → 加分
    2. 多信号共振: FVG+OB+FVG堆叠 → 加分
    3. 周线对齐: 周线趋势一致 → 加分
    4. 结构变化: MSS/CHOCH ≈ 入场点 → 加分
    """
    score = 0.50  # V36 baseline (只要FVG通过基线就有0.50)
    
    # 1. 流动性猎杀加分 (最多+0.30)
    sweep_sigs = liquidity_result.get('sweep_signals', [])
    for ss in sweep_sigs:
        if ss.get('direction', '') == direction and ss.get('idx', 0) >= max(0, idx - 15):
            cluster = ss.get('zone_cluster_size', 0)
            score += min(0.30, 0.15 + cluster * 0.03)
            break
    
    # 2. 多信号共振 (最多+0.15)
    sigs_8b = [s for s in all_signals 
               if 0 < s.get('idx', 0) - idx <= 8
               and s.get('direction', '') == direction]
    types = set()
    for s in sigs_8b:
        t = s.get('type', '')
        if 'FVG' in t: types.add('FVG')
        if 'OB' in t: types.add('OB')
        if 'Sweep' in t: types.add('Sweep')
    if len(types) >= 3:
        score += 0.15
    elif len(types) >= 2:
        score += 0.08
    
    # 3. 周线对齐 (最多+0.10)
    weekly_score = weekly_ctx.get('score', 0.5)
    if direction == 'bull':
        if weekly_score > 0.6:
            score += 0.10
    else:
        if weekly_score < 0.4:
            score += 0.10
    
    # 4. MSS/CHOCH结构加分 (最多+0.10)
    for s in sigs_8b:
        t = s.get('type', '')
        if 'MSS' in t:
            score += 0.03
        if 'CHOCH' in t:
            score += 0.07
            break
    
    return min(1.0, score)


# ═══════════════════════════════════════════════════════════════════════
# V37 回测 (V36核心 + 流动性过滤)
# ═══════════════════════════════════════════════════════════════════════

def backtest_stock_v37(symbol, ohlcv):
    """单只股票V37回测"""
    n = len(ohlcv)
    
    # 1. 全信号检测
    sig_result = detect_all_signals_v11(ohlcv)
    all_signals = sig_result['all']
    
    if not all_signals:
        return {'symbol': symbol, 'trades': [], 'tradable': False}
    
    # 2. 流动性分析
    liquidity_result = detect_liquidity_zones(ohlcv)
    
    # 3. 信号增强
    enhanced = enhance_signals_with_liquidity(all_signals, ohlcv)
    
    # 4. 回测
    trades = []
    in_pos = False
    pos = {}
    
    for i in range(120, n - 1):
        bar = ohlcv[i]
        
        if not in_pos:
            # V36核心: FVG Bull-only
            bull_fvg = [s for s in enhanced if 'FVG' in s.get('type', '')
                        and s.get('direction', '') == 'bull'
                        and i >= s.get('confirmed_at', s.get('idx', 0))
                        and 0 < i - s.get('confirmed_at', s.get('idx', 0)) <= 5]
            
            if not bull_fvg:
                continue
            
            best = max(bull_fvg, key=lambda s: s.get('strength', 0))
            
            # V37评分
            weekly_ctx = calc_weekly_context(ohlcv, i)
            v37_score = score_entry_v37(enhanced, liquidity_result, weekly_ctx, i, 'bull')
            
            # 过滤: 评分<0.55不交易 (略高于V36基线)
            if v37_score < 0.55:
                continue
            
            current = bar['c']
            
            # SL: V36摆动点式
            sl_result = find_best_swing_sl(ohlcv, i, current)
            if sl_result:
                sl_price, sl_type = sl_result[0], sl_result[1]
            else:
                sl_pct = 0.3
                sl_price = current * (1 - sl_pct / 100)
                sl_type = 'fixed_03'
            
            # TP: 前方摆动高点
            swing_highs = []
            for j in range(max(0, i-60), i):
                if j < 3: continue
                b = ohlcv[j]
                l = ohlcv[j-1] if j > 0 else None
                r = ohlcv[j+1] if j < n-1 else None
                if l and r:
                    if b['h'] > l['h'] and b['h'] > r['h']:
                        swing_highs.append((j, b['h']))
            
            future_highs = [(j, p) for j, p in swing_highs if j > i and p > current]
            if future_highs:
                nearest = min(future_highs, key=lambda x: x[1] - current)
                tp_price = nearest[1]
                tp_type = 'swing_high'
            else:
                atr = calc_atr(ohlcv, i)
                tp_price = current * (1 + atr * 5 / 100)
                tp_type = 'atr_projection'
            
            in_pos = True
            pos = {
                'entry_idx': i,
                'entry_price': current,
                'sl_price': sl_price,
                'sl_type': sl_type,
                'tp_price': tp_price,
                'tp_type': tp_type,
                'trailing_sl': sl_price,
                'weekly_trend': weekly_ctx.get('trend', 'neutral'),
                'v37_score': v37_score,
                'has_liquidity_sweep': v37_score > 0.65,  # 高分=有猎杀
            }
        
        else:
            hold = i - pos['entry_idx']
            hi, lo, cc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i]['c']
            
            # Trailing
            new_sl = calc_trailing_v36(pos['entry_price'], cc, 'bull')
            if new_sl:
                pos['trailing_sl'] = new_sl
            
            exit_reason = None
            exit_price = None
            
            if lo <= pos['trailing_sl']:
                exit_reason = 'stop_loss'
                exit_price = pos['trailing_sl']
            elif hi >= pos['tp_price']:
                exit_reason = 'take_profit'
                exit_price = pos['tp_price']
            elif hold >= MAX_HOLD:
                exit_reason = 'max_hold'
                exit_price = cc
            
            if exit_reason:
                pnl = (exit_price - pos['entry_price']) / pos['entry_price'] * 100
                sl_pct = abs(pos['entry_price'] - pos['trailing_sl']) / pos['entry_price'] * 100
                rr = abs(pnl) / max(0.01, sl_pct)
                
                trades.append({
                    'entry_idx': pos['entry_idx'],
                    'exit_idx': i,
                    'hold': hold,
                    'entry_price': pos['entry_price'],
                    'exit_price': exit_price,
                    'pnl_pct': round(pnl, 2),
                    'rr': round(rr, 2),
                    'exit_reason': exit_reason,
                    'sl_type': pos['sl_type'],
                    'tp_type': pos['tp_type'],
                    'v37_score': round(pos['v37_score'], 3),
                    'weekly_trend': pos['weekly_trend'],
                    'has_sweep': pos['has_liquidity_sweep'],
                })
                in_pos = False
                pos = {}
    
    if not trades:
        return {'symbol': symbol, 'trades': [], 'tradable': False}
    
    wins = [t for t in trades if t['pnl_pct'] > 0]
    losses = [t for t in trades if t['pnl_pct'] <= 0]
    wr = len(wins) / len(trades) * 100
    avg_win = sum(t['pnl_pct'] for t in wins) / max(1, len(wins))
    avg_loss = abs(sum(t['pnl_pct'] for t in losses)) / max(1, len(losses))
    rr = avg_win / max(0.01, avg_loss)
    pf = sum(t['pnl_pct'] for t in wins) / max(0.01, abs(sum(t['pnl_pct'] for t in losses)))
    total_pnl = sum(t['pnl_pct'] for t in trades)
    
    return {
        'symbol': symbol, 'trades': trades, 'tradable': True,
        'stats': {
            'n': len(trades), 'wr': round(wr, 1), 'rr': round(rr, 2),
            'pf': round(pf, 1), 'pnl': round(total_pnl, 2),
            'wins': len(wins), 'losses': len(losses),
        },
        'sweep_ratio': sum(1 for t in trades if t['has_sweep']) / max(1, len(trades)),
    }


# ═══════════════════════════════════════════════════════════════════════
# 批量运行
# ═══════════════════════════════════════════════════════════════════════

def run_batch(symbols, limit=200):
    results = {'stocks': {}, 'all_trades': [], 'total': 0, 'tradable': 0}
    
    for idx, sym in enumerate(symbols[:limit]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            continue
        r = backtest_stock_v37(sym, ohlcv)
        results['stocks'][sym] = r
        results['all_trades'].extend(r.get('trades', []))
        results['total'] += 1
        if r.get('tradable'):
            results['tradable'] += 1
        
        if (idx + 1) % 25 == 0:
            s = r.get('stats', {})
            print(f"  [{idx+1}/{min(limit,len(symbols))}] {sym:>10} "
                  f"n={s.get('n',0):>3} WR={s.get('wr',0):>4}% PF={s.get('pf',0):>6}")
    
    tradable = [r for r in results['stocks'].values() if r.get('tradable')]
    
    if tradable:
        total_n = sum(r['stats']['n'] for r in tradable)
        total_w = sum(r['stats']['wins'] for r in tradable)
        wr = total_w / max(1, total_n) * 100
        pnl = sum(r['stats']['pnl'] for r in tradable)
        
        w_avg_rr = sum(r['stats']['rr'] * r['stats']['n'] for r in tradable) / max(1, total_n)
        wr80 = sum(1 for r in tradable if r['stats']['wr'] >= 80)
        avg_sweep = sum(r['sweep_ratio'] for r in tradable) / len(tradable)
        
        print(f"\n{'='*70}")
        print(f"V37 — {results['tradable']}/{results['total']} tradable | {limit} stocks")
        print(f"{'='*70}")
        print(f"  Trades: {total_n} | WR: {wr:.1f}% | RR: {w_avg_rr:.2f}x")
        print(f"  Total P&L: {pnl:+.2f}% | WR>=80%: {wr80}")
        print(f"  Avg sweep ratio: {avg_sweep:.0%}")
        
        out = OUTPUT_DIR / 'backtest_v37.json'
        with open(out, 'w') as f:
            json.dump({
                'summary': {
                    'tradable': results['tradable'],
                    'total': results['total'],
                    'trades': total_n,
                    'wr': round(wr, 1),
                    'rr': round(w_avg_rr, 2),
                    'pnl': round(pnl, 2),
                    'wr80': wr80,
                    'sweep_ratio': round(avg_sweep, 3),
                },
                'stocks': {k: v for k, v in results['stocks'].items() 
                          if v.get('tradable')},
            }, f, indent=1)
        print(f"\n  Saved: {out}")
    
    return results


if __name__ == '__main__':
    cache_files = list(CACHE_DIR.glob('*_daily_300.json'))
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.') for f in cache_files])
    random.seed(42)
    tests = random.sample(symbols, min(MAX_STOCKS, len(symbols)))
    
    print("V37 — V36 Core + Liquidity Context")
    print(f"Stocks: {len(tests)} | Bars: {MIN_BARS}+")
    print('='*70)
    
    t0 = time.time()
    run_batch(tests, limit=MAX_STOCKS)
    print(f"Time: {time.time()-t0:.0f}s")
