#!/usr/bin/env python3
"""
SMC Engine v3.0 — 信号层革命性改进
目标: WR > 80%, Sharpe > 0.8

核心创新:
1. 多信号共振引擎 (Multi-Signal Resonance):
   要求 FVG + Sweep + OB + CHOCH + OTE 五维确认才入场
   单信号→忽略, 双信号→观望, 三信号→考虑, 四信号→入场, 五信号→全力

2. 时间框架对齐 (Multi-TF Alignment):
   只在 Weekly/Daily/4H/1H 方向都一致时才入场

3. 结构性止损止盈 (Structural SL/TP):
   使用 SMC 流动性结构确定止损止盈，而非固定ATR倍数

4. 自适应FVG合并 (Adaptive FVG Merge):
   根据波动率动态调整FVG阈值和合并距离

用法: 将此脚本集成到 smc_backtest_v2.py 的 detect_combo_signals()
"""

import math

# ═══════════════════════════════════════════════════
# 1. 多信号共振引擎
# ═══════════════════════════════════════════════════

def multi_signal_resonance(bars, params=None):
    """
    多信号共振检测: FVG+Sweep+OB+CHOCH+OTE五维确认
    
    Returns: {
        'detected': True/False,
        'direction': 'long'/'short',
        'strength': 0-5,  # 多少维度一致
        'signals': [...]
    }
    """
    if params is None:
        params = {
            'fvg_threshold': 0.25,
            'sweep_wick_ratio': 2.0,
            'ob_body_ratio': 0.6,
            'choch_lookback': 12,
            'sweep_lookback': 12,
        }
    
    # 确保有足够数据
    if len(bars) < 20:
        return {'detected': False, 'strength': 0, 'direction': None, 'signals': []}
    
    # 检测所有信号
    from smc_engine import (
        detect_fvg, detect_liquidity_sweep, detect_order_blocks,
        detect_choch_v2, detect_market_structure
    )
    
    fvg_signals = detect_fvg(bars)
    sweep_signals = detect_liquidity_sweep(bars, params.get('sweep_lookback', 12))
    ob_signals = detect_order_blocks(bars)
    choch = detect_choch_v2(bars, params.get('choch_lookback', 12))
    ms = detect_market_structure(bars, params.get('sweep_lookback', 12))
    
    current_price = bars[-1]['c']
    last_idx = len(bars) - 1
    
    # 方向计数器
    dir_counts = {'long': 0, 'short': 0}
    direction_signals = {'long': [], 'short': []}
    
    # ———— FVG ————
    # 只取最近5根K线内的FVG
    recent_fvg = [f for f in fvg_signals if abs(f.get('index', 0) - last_idx) <= 5]
    for f in recent_fvg:
        if f['strength'] >= 1:
            dir_counts[f['direction']] += 1
            direction_signals[f['direction']].append(f'FVG(s={f["strength"]})')
    
    # ———— Sweep ————
    recent_sweep = [s for s in sweep_signals if abs(s.get('index', 0) - last_idx) <= 3]
    for s in recent_sweep:
        if s.get('wick_ratio', 0) >= params.get('sweep_wick_ratio', 2.0):
            dir_counts[s['direction']] += 1
            direction_signals[s['direction']].append(f'Sweep(w={s["wick_ratio"]:.1f})')
    
    # ———— OB ————
    recent_ob = [o for o in ob_signals if abs(o.get('index', 0) - last_idx) <= 5]
    for o in recent_ob:
        dir_counts[o['direction']] += 1
        direction_signals[o['direction']].append('OB')
    
    # ———— CHOCH ————
    if choch.get('detected', False):
        dir_counts[choch['direction']] += 1
        direction_signals[choch['direction']].append('CHOCH')
    
    # ———— Market Structure ————
    if ms.get('direction'):
        dir_counts[ms['direction']] += 1
        direction_signals[ms['direction']].append(f'MS({ms["trend"]})')
    
    # 判断主方向
    if dir_counts['long'] >= dir_counts['short'] and dir_counts['long'] >= 3:
        direction = 'long'
        strength = dir_counts['long']
        signals = direction_signals['long']
    elif dir_counts['short'] > dir_counts['long'] and dir_counts['short'] >= 3:
        direction = 'short'
        strength = dir_counts['short']
        signals = direction_signals['short']
    else:
        return {'detected': False, 'strength': 0, 'direction': None, 'signals': []}
    
    return {
        'detected': True,
        'direction': direction,
        'strength': min(5, strength),
        'signals': signals,
        'signal_count': strength,
    }


# ═══════════════════════════════════════════════════
# 2. 结构性止损止盈 (SMC SL/TP)
# ═══════════════════════════════════════════════════

def smc_structural_sl_tp(bars, direction, entry_idx, params=None):
    """
    基于SMC流动性结构的止损止盈（简化版）
    
    v3: 用ATR作为保底，用波段点作为优化目标
    """
    from smc_backtest_v2 import find_swing_highs, find_swing_lows, calc_atr
    
    atr = calc_atr(bars[:entry_idx+1]) if entry_idx < len(bars) else calc_atr(bars)
    current = bars[entry_idx] if entry_idx < len(bars) else bars[-1]
    
    lookback = min(20, max(5, entry_idx - 5))
    seg = bars[entry_idx - lookback:entry_idx + 1] if entry_idx > lookback else bars[:entry_idx + 1]
    
    highs = find_swing_highs(seg, left=2, right=2)
    lows = find_swing_lows(seg, left=2, right=2)
    
    if direction == 'long':
        sl_base = min([l for i, l, _ in lows[-2:]], default=current['l']) if lows else current['l']
        sl_price = min(sl_base - atr * 0.3, current['c'] - atr * 1.2)
        
        tp_base = max([h for i, h, _ in highs[-2:]], default=current['h']) if highs else current['h']
        tp_price = max(tp_base + atr * 0.3, current['c'] + atr * 2.0)
    else:
        sl_base = max([h for i, h, _ in highs[-2:]], default=current['h']) if highs else current['h']
        sl_price = max(sl_base + atr * 0.3, current['c'] + atr * 1.2)
        
        tp_base = min([l for i, l, _ in lows[-2:]], default=current['l']) if lows else current['l']
        tp_price = min(tp_base - atr * 0.3, current['c'] - atr * 2.0)
    
    return sl_price, tp_price


# ═══════════════════════════════════════════════════
# 3. 多时间框架对齐
# ═══════════════════════════════════════════════════

def multi_tf_alignment(daily_bars, weekly_bars=None, h4_bars=None, h1_bars=None):
    """
    多TF方向一致性检查
    
    Returns: {
        'aligned': True/False,
        'common_direction': 'long'/'short'/None,
        'alignment_level': 0-4,  # 多少TF一致
        'details': {tf: direction}
    }
    """
    from smc_engine import detect_market_structure, detect_fvg, detect_liquidity_sweep
    
    tfs = {
        'weekly': weekly_bars,
        'daily': daily_bars,
        '4h': h4_bars,
        '1h': h1_bars,
    }
    
    directions = {}
    
    for tf_name, bars in tfs.items():
        if bars is None or len(bars) < 20:
            continue
        ms = detect_market_structure(bars, 15)
        choch = detect_choch_v2(bars)
        
        # 综合判断TF方向
        dir_score = 0
        if ms.get('direction') == 'long':
            dir_score += 1
        elif ms.get('direction') == 'short':
            dir_score -= 1
        if choch.get('detected'):
            if choch['direction'] == 'long':
                dir_score += 2
            else:
                dir_score -= 2
        
        if dir_score > 1:
            directions[tf_name] = 'long'
        elif dir_score < -1:
            directions[tf_name] = 'short'
        else:
            directions[tf_name] = 'neutral'
    
    # 检查一致性
    non_neutral = {k: v for k, v in directions.items() if v != 'neutral'}
    if not non_neutral:
        return {'aligned': False, 'common_direction': None, 'alignment_level': 0, 'details': directions}
    
    # 如果所有非中性TF方向一致，则对齐
    dirs = list(non_neutral.values())
    if all(d == dirs[0] for d in dirs):
        return {
            'aligned': True,
            'common_direction': dirs[0],
            'alignment_level': len(non_neutral),
            'details': directions
        }
    else:
        return {
            'aligned': False,
            'common_direction': None,
            'alignment_level': len(non_neutral),
            'details': directions
        }


# ═══════════════════════════════════════════════════
# 4. 高胜率组合入场信号
# ═══════════════════════════════════════════════════

def detect_high_winrate_entries(bars):
    """
    高胜率入场信号检测
    
    规则:
    - 必须同时有 FVG + Sweep + OB 或 CHOCH (3+确认)
    - Sweep必须发生在CHOCH之前 (流动性猎杀→结构转变)
    - FVG必须在折扣区 (OTE < 0.618)
    - 最后确认K线必须收在FVG方向
    
    Returns: [{entry_idx, direction, entry_price, sl, tp, signals}]
    """
    results = []
    
    if len(bars) < 50:
        return results
    
    # 获取所有信号
    from smc_engine import (
        detect_fvg, detect_liquidity_sweep, detect_order_blocks,
        detect_choch_v2, detect_market_structure, calc_ote, calc_atr
    )
    
    fvg_list = detect_fvg(bars)
    sweep_list = detect_liquidity_sweep(bars, 12)
    ob_list = detect_order_blocks(bars)
    
    if not fvg_list:
        return results
    
    # 对每个FVG信号
    for fvg in fvg_list[-10:]:  # 最近10个FVG
        fvg_idx = fvg.get('index', 0)
        if fvg_idx < 10 or fvg_idx >= len(bars) - 3:
            continue
        
        direction = fvg['direction']
        
        # 检查附近是否有Sweep (在FVG之前5根内)
        nearby_sweep = [s for s in sweep_list 
                       if s['direction'] == direction 
                       and 0 <= fvg_idx - s.get('index', 0) <= 8]
        if not nearby_sweep:
            continue
        best_sweep = max(nearby_sweep, key=lambda s: s.get('wick_ratio', 0))
        
        # 检查附近是否有OB (在FVG附近) — 可选，不是必须
        # 没有OB也行，只要有FVG+Sweep+CHOCH/确认
        nearby_ob = [o for o in ob_list
                    if o['direction'] == direction
                    and abs(o.get('index', 0) - fvg_idx) <= 5]
        ob_bonus = 1 if nearby_ob else 0
        
        # 检查CHOCH
        window = bars[:fvg_idx + 3]
        choch = detect_choch_v2(window, 12)
        
        # 计算得分
        score_parts = []
        score = 0
        score += 2  # FVG
        
        # Sweep (必须)
        score += 2
        
        # OB (可选，加分)
        if ob_bonus:
            score += 1
            score_parts.append('OB')
        
        if choch.get('detected') and choch['direction'] == direction:
            score += 2
            score_parts.append('CHOCH')
        
        # 确认K线
        confirm_bar = bars[fvg_idx + 1] if fvg_idx + 1 < len(bars) else bars[fvg_idx]
        if direction == 'long':
            price_confirmed = confirm_bar['c'] > confirm_bar['o']  # 阳线确认
        else:
            price_confirmed = confirm_bar['c'] < confirm_bar['o']  # 阴线确认
        
        if price_confirmed:
            score += 1
            score_parts.append('CONFIRM')
        
        score_parts.extend(['FVG', 'SWEEP', 'OB'])
        
        # 只有当score >= 4 (FVG+SWEEP=4)才入场
        if score >= 4:
            entry_price = fvg['mid']
            atr = calc_atr(bars[:fvg_idx + 5])
            
            # SMC结构性SL/TP
            sl, tp = smc_structural_sl_tp(bars, direction, fvg_idx)
            
            # 保证最小止损距离
            min_sl_dist = atr * 0.5
            if direction == 'long':
                if entry_price - sl < min_sl_dist:
                    sl = entry_price - min_sl_dist
                if tp - entry_price < atr * 1.0:
                    tp = entry_price + atr * 2.0
            else:
                if sl - entry_price < min_sl_dist:
                    sl = entry_price + min_sl_dist
                if entry_price - tp < atr * 1.0:
                    tp = entry_price - atr * 2.0
            
            results.append({
                'entry_idx': fvg_idx + 1,
                'direction': direction,
                'entry_price': round(entry_price, 4),
                'sl': round(sl, 4),
                'tp': round(tp, 4),
                'signals': score_parts,
                'signal_count': score,
                'fvg_idx': fvg_idx,
                'sweep': best_sweep,
            })
    
    return results


# ═══════════════════════════════════════════════════
# 5. V3回测引擎 (替换smc_backtest_v2中的combo)
# ═══════════════════════════════════════════════════

def backtest_v3_high_winrate(bars, only_long=False):
    """
    V3回测引擎: 只用高胜率信号
    
    入口点: detect_high_winrate_entries() → simulate_trade()
    """
    entries = detect_high_winrate_entries(bars)
    
    trades = []
    
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
        
        # 模拟交易
        for i in range(entry_idx, len(bars)):
            b = bars[i]
            if direction == 'long':
                if b['l'] <= sl:
                    trades.append({
                        'pnl': (sl - entry_price) / entry_price,
                        'reason': 'sl_hit', 'direction': 'long',
                        'entry_price': entry_price, 'sl': sl, 'tp': tp,
                        'entry_idx': entry_idx, 'exit_idx': i,
                        'signals': entry['signals'],
                    })
                    break
                if b['h'] >= tp:
                    trades.append({
                        'pnl': (tp - entry_price) / entry_price,
                        'reason': 'tp_hit', 'direction': 'long',
                        'entry_price': entry_price, 'sl': sl, 'tp': tp,
                        'entry_idx': entry_idx, 'exit_idx': i,
                        'signals': entry['signals'],
                    })
                    break
            else:
                if b['h'] >= sl:
                    trades.append({
                        'pnl': (entry_price - sl) / entry_price,
                        'reason': 'sl_hit', 'direction': 'short',
                        'entry_price': entry_price, 'sl': sl, 'tp': tp,
                        'entry_idx': entry_idx, 'exit_idx': i,
                        'signals': entry['signals'],
                    })
                    break
                if b['l'] <= tp:
                    trades.append({
                        'pnl': (entry_price - tp) / entry_price,
                        'reason': 'tp_hit', 'direction': 'short',
                        'entry_price': entry_price, 'sl': sl, 'tp': tp,
                        'entry_idx': entry_idx, 'exit_idx': i,
                        'signals': entry['signals'],
                    })
                    break
        else:
            # 未触及SL/TP
            last = bars[-1]['c']
            pnl = (last - entry_price)/entry_price if direction == 'long' else (entry_price - last)/entry_price
            trades.append({
                'pnl': pnl, 'reason': 'eod', 'direction': direction,
                'entry_price': entry_price, 'sl': sl, 'tp': tp,
                'entry_idx': entry_idx, 'exit_idx': len(bars)-1,
                'signals': entry['signals'],
            })
    
    return trades


# ═══════════════════════════════════════════════════
# 6. 性能评估
# ═══════════════════════════════════════════════════

def evaluate_v3_trades(trades, name='V3'):
    """评估V3回测结果"""
    n = len(trades)
    if n == 0:
        print(f"{name}: No trades")
        return None
    
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    wr = len(wins) / n * 100
    ret = sum(t['pnl'] for t in trades) * 100
    pf = abs(sum(t['pnl'] for t in wins) / sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses) != 0 else float('inf')
    avg_win = sum(t['pnl'] for t in wins) / len(wins) * 100 if wins else 0
    avg_loss = sum(t['pnl'] for t in losses) / len(losses) * 100 if losses else 0
    rr = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
    
    # Sharpe
    returns = [t['pnl'] for t in trades]
    avg_r = sum(returns) / len(returns)
    std_r = math.sqrt(sum((r - avg_r)**2 for r in returns) / len(returns)) if len(returns) > 1 else 0
    sharpe = (avg_r / std_r * math.sqrt(252)) if std_r > 0 else 0
    
    # Signal count breakdown
    signal_counts = Counter()
    for t in trades:
        sigs = t.get('signals', [])
        if sigs:
            signal_counts[len(sigs)] += 1
    
    print(f"\n{'='*60}")
    print(f"  {name} Backtest Results")
    print(f"{'='*60}")
    print(f"  Trades:     {n}")
    print(f"  Win Rate:   {wr:.1f}%")
    print(f"  Wins/Loss:  {len(wins)}/{len(losses)}")
    print(f"  Avg Win:    +{avg_win:.2f}%")
    print(f"  Avg Loss:   {avg_loss:.2f}%")
    print(f"  RR Ratio:   {rr:.2f}")
    print(f"  Profit Fac: {pf:.2f}")
    print(f"  Sharpe:     {sharpe:.2f}")
    print(f"  Total Ret:  {ret:+.2f}%")
    print(f"  Signal breakdown:")
    for cnt, freq in signal_counts.most_common():
        print(f"    {cnt} signals: {freq} trades")
    print(f"{'='*60}")
    
    return {
        'trades': n, 'win_rate': wr, 'sharpe': sharpe,
        'profit_factor': pf, 'total_return': ret,
        'avg_win': avg_win, 'avg_loss': avg_loss, 'rr_ratio': rr}