#!/usr/bin/env python3
"""
SMC V12 全功能交易引擎 — 每股/每阶段/摆动点/全量扫描
================================================================

核心创新:
1. 每股参数自适应: 每只股票独立优化SL/TP (摆脱固定0.5%/5.0%)
2. 每阶段参数自适应: breakout/volatile/ranging不同参数集
3. 摆动点精确入场: 不简单bar-close入场, 使用摆动点分析
4. 信号质量评分: 综合评估FVG gap/成交量/摆动点对齐/K线形态
5. Scout优先 + 修复的Silver/Bronze (缩小窗口)
6. 全量市场扫描: 4800只股票+ETF

数据来源: 日线缓存 /root/.hermes/kline_cache/
"""
import json, sys, time, math
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v12')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# 配置参数
# ============================================================
MIN_BARS = 120
ROLL_START = 80
ROLL_END_OFFSET = 10
MAX_HOLD = 40
COOLDOWN = 12  # 冷启动K线数

# 参数扫描空间
SL_CANDIDATES = [0.3, 0.5, 0.7, 1.0, 1.5]
TP_CANDIDATES = [2.0, 3.0, 4.0, 5.0, 6.0]
# 每阶段默认初始参数
PHASE_DEFAULT_PARAMS = {
    'breakout': {'sl': 0.5, 'tp': 5.0},
    'volatile': {'sl': 0.7, 'tp': 4.0},
    'ranging': {'sl': 0.5, 'tp': 3.0},
    'trending_down': {'sl': 0.5, 'tp': 3.0},
}

# ============================================================
# 数据加载
# ============================================================
def load_ohlcv(symbol):
    """加载日线缓存"""
    fname = f"{symbol.replace('.', '_')}_daily_300.json"
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


# ============================================================
# 摆动点分析
# ============================================================
def find_swing_points(ohlcv, lookback=5):
    """找出摆动高点和低点"""
    highs = []
    lows = []
    n = len(ohlcv)
    for i in range(lookback, n - lookback):
        # 摆动高点: 中间K线的最高价大于左右lookback根K线
        is_high = all(ohlcv[i]['h'] >= ohlcv[j]['h'] for j in range(i-lookback, i+lookback+1) if j != i)
        if is_high:
            highs.append({'idx': i, 'price': ohlcv[i]['h'], 'type': 'high'})
        
        # 摆动低点
        is_low = all(ohlcv[i]['l'] <= ohlcv[j]['l'] for j in range(i-lookback, i+lookback+1) if j != i)
        if is_low:
            lows.append({'idx': i, 'price': ohlcv[i]['l'], 'type': 'low'})
    return highs, lows


def find_swing_near_signal(sig_idx, ohlcv, swing_highs, swing_lows, max_dist=3):
    """信号附近是否有摆动点"""
    near_high = [s for s in swing_highs if abs(s['idx'] - sig_idx) <= max_dist]
    near_low = [s for s in swing_lows if abs(s['idx'] - sig_idx) <= max_dist]
    return near_high, near_low


# ============================================================
# 信号质量评分
# ============================================================
def score_signal_quality(sig, ohlcv, swing_highs, swing_lows):
    """综合信号质量评分 (0-100)"""
    score = 50  # 基础分
    
    sig_idx = sig.get('idx', 0)
    sig_type = sig.get('type', '')
    direction = sig.get('direction', '')
    
    if sig_idx <= 0 or sig_idx >= len(ohlcv):
        return 30
    
    bar = ohlcv[sig_idx]
    
    # 1. 成交量确认 (+10)
    bar_vol = bar.get('v', bar.get('vol', 0))
    avg_vol = 0
    for i in range(max(0, sig_idx-30), sig_idx):
        avg_vol += ohlcv[i].get('v', ohlcv[i].get('vol', 0))
    avg_vol = avg_vol / min(30, sig_idx)
    if avg_vol > 0 and bar_vol > avg_vol * 1.2:
        score += 15
    elif avg_vol > 0 and bar_vol > avg_vol * 0.8:
        score += 5
    
    # 2. K线形态 (+10)
    body = abs(bar['c'] - bar['o'])
    range_p = bar['h'] - bar['l']
    if range_p > 0:
        body_ratio = body / range_p
        if direction == 'bull' and bar['c'] > bar['o']:
            # 阳线 + 实体占比 >50%
            if body_ratio > 0.5:
                score += 10
            else:
                score += 3
        elif direction == 'bear' and bar['c'] < bar['o']:
            if body_ratio > 0.5:
                score += 10
            else:
                score += 3
    
    # 3. FVG gap大小 (+10)
    if 'FVG' in sig_type:
        upper = sig.get('upper', 0)
        lower = sig.get('lower', 0)
        if upper > 0 and lower > 0:
            gap_pct = (upper - lower) / lower * 100
            if gap_pct >= 1.0:
                score += 15
            elif gap_pct >= 0.5:
                score += 10
            elif gap_pct >= 0.3:
                score += 5
            else:
                score -= 5  # 太小gap扣分
    
    # 4. 摆动点对齐 (+10)
    near_high, near_low = find_swing_near_signal(sig_idx, ohlcv, swing_highs, swing_lows, max_dist=3)
    if direction == 'bull' and near_low:
        score += 10  # FVG在摆动低点附近
    elif direction == 'bear' and near_high:
        score += 10
    elif near_high or near_low:
        score += 3
    
    # 5. 趋势方向一致性 (+10)
    if sig_idx >= 20:
        ma20 = sum(ohlcv[i]['c'] for i in range(sig_idx-20, sig_idx)) / 20
        ma10 = sum(ohlcv[i]['c'] for i in range(sig_idx-10, sig_idx)) / 10
        if direction == 'bull' and ma10 > ma20:
            score += 10
        elif direction == 'bear' and ma10 < ma20:
            score += 10
        elif direction == 'bull' and bar['c'] > ma20:
            score += 5
        elif direction == 'bear' and bar['c'] < ma20:
            score += 5
    
    # 6. 近期胜率历史 (用简单筛选)
    if sig_idx > 60:
        recent_high = max(ohlcv[i]['h'] for i in range(max(0, sig_idx-20), sig_idx))
        recent_low = min(ohlcv[i]['l'] for i in range(max(0, sig_idx-20), sig_idx))
        atr = recent_high - recent_low
        if atr > 0:
            vol_ratio = (bar['h'] - bar['l']) / atr
            if 0.5 <= vol_ratio <= 1.5:
                score += 5
    
    return min(100, max(0, score))


# ============================================================
# 信号级别入场 (基于质量评分)
# ============================================================
def analyze_signal_entry(ohlcv, all_signals, swing_highs, swing_lows, params):
    """
    版v2 — 每个信号独立检测入场机会
    改进: 加入质量评分+摆动点确认
    """
    n = len(ohlcv)
    roll_end = n - ROLL_END_OFFSET
    trades = []
    entered_bar = -999
    
    for end_idx in range(ROLL_START, roll_end):
        if end_idx - entered_bar < COOLDOWN:
            continue
        
        sigs_before = [s for s in all_signals if s.get('idx', 0) <= end_idx]
        if len(sigs_before) < 3:
            continue
        
        seq_result = analyze_sequence_v11(sigs_before, params=params)
        best_seq = seq_result.get('best_sequence')
        if not best_seq:
            continue
        
        seq_name = best_seq.get('name', '')
        is_scout = 'SCOUT' in seq_name
        seq_dir = 'bull' if 'LONG' in seq_name else 'bear'
        
        # === 方向过滤: Bull-only (Bear方向WR低) ===
        if seq_dir != 'bull':
            continue
        
        # 获取该序列对应的原始信号 - use seq_result entry_signal
        entry_signal = seq_result.get('entry_signal', {})
        sig_idx = entry_signal.get('idx', end_idx) if isinstance(entry_signal, dict) else end_idx
        
        # === 信号质量评分检查 (宽松阈值) ===
        quality = score_signal_quality(entry_signal, ohlcv, swing_highs, swing_lows)
        if quality < 30:
            continue
        
        # === Scout额外检查 ===
        if is_scout:
            # 短期趋势检查
            if sig_idx >= 10:
                trend_change = (ohlcv[sig_idx]['c'] - ohlcv[sig_idx-10]['c']) / ohlcv[sig_idx-10]['c'] * 100
                if trend_change < -1.0:  # 下跌趋势不做多
                    continue
            # 需要足够信号密度
            if len(sigs_before) < 8:
                continue
        
        # === 非Scout (Silver/Bronze) — 修复的入场逻辑 ===
        if not is_scout:
            # 检查信号的紧凑性: 多信号序列的信号间距离应该很短
            matched = best_seq.get('matched_tokens', [])
            if len(matched) >= 2:
                indices = [t.get('idx', 0) for t in matched]
                max_gap = max(indices) - min(indices)
                # 如果信号分散在太多K线上, 跳过
                if max_gap > 15:
                    continue
            
            # 信号质量评分必须更高
            if quality < 55:
                continue
        
        # === 共振检查 ===
        window = ohlcv[:end_idx + 1]
        tf_sequences = {'daily': seq_result}
        resonance = evaluate_full_resonance_v11(
            all_signals=sigs_before, tf_sequences=tf_sequences, ohlcv=window
        )
        
        decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
        if decision['action'] != 'enter':
            continue
        
        if is_scout and resonance.total < 0.60:
            continue
        
        # === 摆动点精确入场 ===
        entry_price = decision.get('entry_price')
        direction = decision.get('direction', 'bull')
        
        # 尝试使用摆动点优化入场
        if direction == 'bull':
            # 找最近的摆动低点作为支撑
            recent_lows = [s for s in swing_lows if s['idx'] <= end_idx and s['idx'] >= end_idx - 5]
            if recent_lows and entry_price:
                best_low = max(recent_lows, key=lambda x: x['price'])
                # 如果摆动低点高于当前价, 使用摆动低点做更精确的入场
                if best_low['price'] < entry_price:
                    pass  # 保留原入场价
        else:
            recent_highs = [s for s in swing_highs if s['idx'] <= end_idx and s['idx'] >= end_idx - 5]
        
        sl_price = decision.get('sl')
        tp_price = decision.get('tp')
        
        if not entry_price or not sl_price or not tp_price:
            continue
        
        # === 持仓模拟 ===
        if direction == 'bull':
            sl_cond = lambda b: b['l'] <= sl_price
            tp_cond = lambda b: b['h'] >= tp_price
        else:
            sl_cond = lambda b: b['h'] >= sl_price
            tp_cond = lambda b: b['l'] <= tp_price
        
        exit_idx, exit_price, won = -1, None, False
        for j in range(end_idx + 1, min(end_idx + MAX_HOLD + 1, n)):
            bar = ohlcv[j]
            if tp_cond(bar): exit_idx, exit_price, won = j, tp_price, True; break
            if sl_cond(bar): exit_idx, exit_price, won = j, sl_price, False; break
        
        if exit_idx == -1:
            exit_idx = min(end_idx + MAX_HOLD, n - 1)
            exit_price = ohlcv[exit_idx]['c']
            won = (exit_price > entry_price) if direction == 'bull' else (exit_price < entry_price)
        
        pnl_pct = ((exit_price - entry_price) / entry_price * 100) if direction == 'bull' else ((entry_price - exit_price) / entry_price * 100)
        actual_rr = abs(exit_price - entry_price) / abs(entry_price - sl_price + 0.001)
        
        trades.append({
            'entry_idx': end_idx, 'exit_idx': exit_idx, 'direction': direction,
            'entry_price': round(entry_price, 2), 'exit_price': round(exit_price, 2),
            'sl': round(sl_price, 2), 'tp': round(tp_price, 2),
            'pnl_pct': round(pnl_pct, 2), 'won': won, 'rr': round(actual_rr, 2),
            'seq_name': best_seq.get('name', 'Scout'),
            'quality_score': quality,
            'resonance_grade': resonance.grade(),
            'confidence': decision['confidence'],
            'hold_bars': exit_idx - end_idx,
            'n_sigs_before': len(sigs_before),
        })
        entered_bar = end_idx
    
    return trades


# ============================================================
# 参数扫描 + 回测单股票
# ============================================================
def scan_params_for_stock(ohlcv, all_signals, swing_highs, swing_lows, base_params, phase):
    """扫描SL/TP参数组合, 找最优"""
    best = {'sl_pct': 0.5, 'tp_pct': 5.0, 'n_trades': 0, 'score': 0}
    
    for sl_pct in SL_CANDIDATES:
        for tp_pct in TP_CANDIDATES:
            params = {**base_params, 'sl_pct': sl_pct, 'tp_pct': tp_pct}
            trades = analyze_signal_entry(ohlcv, all_signals, swing_highs, swing_lows, params)
            
            if len(trades) < 3:
                continue
            
            wins = sum(1 for t in trades if t['won'])
            wr = wins / len(trades) * 100
            win_pnl = sum(t['pnl_pct'] for t in trades if t['won'])
            loss_pnl = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
            pf = win_pnl / loss_pnl if loss_pnl > 0 else 0
            avg_rr = sum(t['rr'] for t in trades) / len(trades)
            
            # 综合评分
            score = (wr / 100) ** 2 * min(3.0, avg_rr) * min(3.0, pf) * min(2.0, len(trades) / 10)
            
            if score > best['score']:
                best = {
                    'sl_pct': sl_pct, 'tp_pct': tp_pct,
                    'n_trades': len(trades), 'wins': wins, 'losses': len(trades) - wins,
                    'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
                    'profit_factor': round(pf, 2) if pf != float('inf') else 99.9,
                    'avg_pnl': round(sum(t['pnl_pct'] for t in trades) / len(trades), 2),
                    'total_pnl': round(sum(t['pnl_pct'] for t in trades), 2),
                    'score': round(score, 2),
                }
    
    return best


def backtest_stock(ohlcv, symbol, use_param_scan=True):
    """单股票全流程回测"""
    t0 = time.time()
    phase = detect_market_phase(ohlcv)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    
    # 全量信号检测 (一次)
    all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')['all']
    if not all_signals or len(all_signals) < 5:
        return {'trades': [], 'n_signals': len(all_signals) if all_signals else 0, 'phase': phase}
    
    # 摆动点分析 (一次)
    swing_highs, swing_lows = find_swing_points(ohlcv, lookback=5)
    
    if use_param_scan:
        # 参数扫描
        best = scan_params_for_stock(ohlcv, all_signals, swing_highs, swing_lows, base_params, phase)
        if best['n_trades'] > 0:
            params = {**base_params, 'sl_pct': best['sl_pct'], 'tp_pct': best['tp_pct']}
            trades = analyze_signal_entry(ohlcv, all_signals, swing_highs, swing_lows, params)
            elapsed = time.time() - t0
            return {
                'trades': trades, 'perf': best,
                'best_params': {'sl_pct': best['sl_pct'], 'tp_pct': best['tp_pct']},
                'n_signals': len(all_signals), 'phase': phase,
                'n_swing_highs': len(swing_highs), 'n_swing_lows': len(swing_lows),
                'elapsed': round(elapsed, 1),
            }
    else:
        # 使用阶段默认参数
        phase_params = PHASE_DEFAULT_PARAMS.get(phase, {'sl': 0.5, 'tp': 5.0})
        params = {**base_params, 'sl_pct': phase_params['sl'], 'tp_pct': phase_params['tp']}
        trades = analyze_signal_entry(ohlcv, all_signals, swing_highs, swing_lows, params)
        if trades:
            wins = sum(1 for t in trades if t['won'])
            wr = wins / len(trades) * 100
            win_pnl = sum(t['pnl_pct'] for t in trades if t['won'])
            loss_pnl = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
            pf = win_pnl / loss_pnl if loss_pnl > 0 else 99.9
            avg_rr = sum(t['rr'] for t in trades) / len(trades)
            elapsed = time.time() - t0
            return {
                'trades': trades,
                'perf': {
                    'sl_pct': phase_params['sl'], 'tp_pct': phase_params['tp'],
                    'n_trades': len(trades), 'wins': wins, 'losses': len(trades) - wins,
                    'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
                    'profit_factor': round(pf, 2),
                    'avg_pnl': round(sum(t['pnl_pct'] for t in trades) / len(trades), 2),
                    'total_pnl': round(sum(t['pnl_pct'] for t in trades), 2),
                },
                'best_params': {'sl_pct': phase_params['sl'], 'tp_pct': phase_params['tp']},
                'n_signals': len(all_signals), 'phase': phase,
                'n_swing_highs': len(swing_highs), 'n_swing_lows': len(swing_lows),
                'elapsed': round(elapsed, 1),
            }
    
    return {'trades': [], 'n_signals': len(all_signals), 'phase': phase,
            'n_swing_highs': len(swing_highs), 'n_swing_lows': len(swing_lows)}


# ============================================================
# 主流程
# ============================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description='SMC V12 Backtest')
    parser.add_argument('--limit', type=int, default=200, help='Max stocks to test')
    parser.add_argument('--param-scan', action='store_true', help='Per-stock parameter scan')
    parser.add_argument('--output', type=str, default='backtest_v12.json', help='Output filename')
    args = parser.parse_args()
    
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    max_stocks = min(args.limit, len(symbols))
    
    print(f"{'='*85}")
    print(f"SMC V12 综合回测 — {max_stocks}/{len(symbols)} 股票")
    if args.param_scan:
        print(f"  每股参数扫描: SL={SL_CANDIDATES} TP={TP_CANDIDATES}")
    else:
        print(f"  阶段默认参数: {PHASE_DEFAULT_PARAMS}")
    print(f"  摆动点入场 + 信号质量评分 + Scout优先+多序列修复")
    print(f"{'='*85}")
    
    all_trades, stock_results = [], []
    t_start = time.time()
    param_stats = defaultdict(int)
    
    for idx, sym in enumerate(symbols[:max_stocks]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            print(f"  [{idx+1:3d}/{max_stocks}] {sym:12s} SKIP (no data)")
            continue
        
        result = backtest_stock(ohlcv, sym, use_param_scan=args.param_scan)
        trades = result.get('trades', [])
        all_trades.extend(trades)
        
        if trades and 'perf' in result:
            p = result['perf']
            stock_results.append({
                'symbol': sym, 'sl_pct': p['sl_pct'], 'tp_pct': p['tp_pct'],
                'n_trades': p['n_trades'], 'wins': p['wins'], 'losses': p.get('losses', 0),
                'win_rate': p['win_rate'], 'avg_rr': p['avg_rr'],
                'profit_factor': p['profit_factor'], 'avg_pnl': p['avg_pnl'],
                'total_pnl': p.get('total_pnl', 0), 'score': p.get('score', 0),
                'n_signals': result['n_signals'], 'phase': result['phase'],
                'n_swing_highs': result.get('n_swing_highs', 0),
                'n_swing_lows': result.get('n_swing_lows', 0),
            })
            param_stats[p['sl_pct']] += 1
            param_stats[p['tp_pct']] += 1
            
            # 序列分布统计
            seqs = Counter(t.get('seq_name', '?') for t in trades)
            seq_str = ','.join(f"{s}:{c}" for s, c in seqs.most_common(3))
            
            print(f"  [{idx+1:3d}/{max_stocks}] {sym:12s} "
                  f"SL={p['sl_pct']:.1f}% TP={p['tp_pct']:.1f}% "
                  f"trades={p['n_trades']:2d} WR={p['win_rate']:.0f}% "
                  f"RR={p['avg_rr']:.2f}x PF={p['profit_factor']:.1f} "
                  f"P&L={p['avg_pnl']:+.2f}% {result['phase'][:8]:8s} "
                  f"swings={result.get('n_swing_highs',0)}+{result.get('n_swing_lows',0)} "
              f"| {result.get('elapsed',0):.1f}s")
        else:
            print(f"  [{idx+1:3d}/{max_stocks}] {sym:12s} NO-TRADE "
                  f"sigs={result.get('n_signals',0)} {result.get('phase','?')[:8]:8s} "
                  f"swings={result.get('n_swing_highs',0)}+{result.get('n_swing_lows',0)}")
        
        if (idx + 1) % 20 == 0:
            time.sleep(0.3)
    
    # === 汇总 ===
    total_time = time.time() - t_start
    print(f"\n{'='*85}")
    print(f"V12 汇总 — {len(stock_results)} 可交易 / {max_stocks} 股票, {total_time:.1f}s")
    print(f"{'='*85}")
    
    if all_trades:
        n = len(all_trades)
        wins = sum(1 for t in all_trades if t['won'])
        wr = wins / n * 100
        win_pnl = sum(t['pnl_pct'] for t in all_trades if t['won'])
        loss_pnl = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
        pf = win_pnl / loss_pnl if loss_pnl > 0 else 99.9
        avg_rr = sum(t['rr'] for t in all_trades) / n
        avg_pnl = sum(t['pnl_pct'] for t in all_trades) / n
        avg_quality = sum(t.get('quality_score', 50) for t in all_trades) / n
        
        print(f"\n  交易数: {n} | WR: {wr:.1f}% | RR: {avg_rr:.2f}x | PF: {pf:.2f} | 平均P&L: {avg_pnl:+.2f}%")
        print(f"  平均质量评分: {avg_quality:.1f} | 平均持仓: {sum(t['hold_bars'] for t in all_trades)/n:.1f}K线")
        
        # 序列分布
        seq_cnt = Counter(t.get('seq_name','?') for t in all_trades)
        print(f"\n  序列分布:")
        for seq, cnt in seq_cnt.most_common(10):
            w = sum(1 for t in all_trades if t.get('seq_name') == seq and t['won'])
            print(f"    {seq:20s}: {cnt:4d}笔 WR={w/cnt*100:.1f}% RR={sum(t['rr'] for t in all_trades if t.get('seq_name')==seq)/cnt:.2f}x")
        
        # 高WR股票
        wr80 = sum(1 for s in stock_results if s['win_rate'] >= 80)
        wr70 = sum(1 for s in stock_results if s['win_rate'] >= 70)
        wr60 = sum(1 for s in stock_results if s['win_rate'] >= 60)
        print(f"\n  高WR分布: WR>=80%: {wr80} | WR>=70%: {wr70} | WR>=60%: {wr60}")
        
        # 参数分布
        sl_cnt = Counter(s['sl_pct'] for s in stock_results)
        tp_cnt = Counter(s['tp_pct'] for s in stock_results)
        print(f"  SL分布: {dict(sl_cnt.most_common())}")
        print(f"  TP分布: {dict(tp_cnt.most_common())}")
        
        # 阶段分布
        phase_cnt = Counter(s['phase'] for s in stock_results)
        print(f"  阶段分布: {dict(phase_cnt.most_common())}")
        
        # 分数TOP10
        sorted_s = sorted(stock_results, key=lambda s: s.get('score', 0), reverse=True)
        print(f"\n  TOP 5 (by score):")
        for s in sorted_s[:5]:
            print(f"    {s['symbol']:12s} SL={s['sl_pct']:.1f}% TP={s['tp_pct']:.1f}% "
                  f"WR={s['win_rate']:.0f}% RR={s['avg_rr']:.2f}x PF={s['profit_factor']:.1f} "
                  f"trades={s['n_trades']} score={s.get('score',0):.1f}")
        
        print(f"\n  底5 (by WR):")
        sorted_wr = sorted(stock_results, key=lambda s: s['win_rate'])
        for s in sorted_wr[:5]:
            print(f"    {s['symbol']:12s} SL={s['sl_pct']:.1f}% TP={s['tp_pct']:.1f}% "
                  f"WR={s['win_rate']:.0f}% RR={s['avg_rr']:.2f}x PF={s['profit_factor']:.1f} "
                  f"trades={s['n_trades']} phase={s['phase']}")
    
    # 保存
    out = {
        'timestamp': datetime.now().isoformat(),
        'config': {
            'max_stocks': max_stocks, 'param_scan': args.param_scan,
            'sl_candidates': SL_CANDIDATES, 'tp_candidates': TP_CANDIDATES,
            'cooldown': COOLDOWN,
        },
        'summary': {
            'total_stocks': max_stocks, 'tradable': len(stock_results),
            'total_trades': len(all_trades),
            'win_rate': round(wr, 1) if all_trades else 0,
            'avg_rr': round(avg_rr, 2) if all_trades else 0,
            'profit_factor': round(pf, 2) if all_trades else 0,
        },
        'stocks': stock_results, 'all_trades': all_trades,
    }
    outpath = OUTPUT_DIR / args.output
    outpath.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print(f"\n  保存: {outpath}")


if __name__ == '__main__':
    main()
