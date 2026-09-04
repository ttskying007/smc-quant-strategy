#!/usr/bin/env python3
"""
V18 — Signal Sequence + Per-Stock Optimizer
============================================
V16核心: Swing SL 76% at 93% WR, WR=77%

V18创新:
  1. 信号序列评分 — 根据前5个信号类型做模式匹配
     Sweep→FVG = +bonus | OB→FVG = best | OOOOO = skip
  2. 每股SL/TP参数优化 — V14风格整合到V16
     SL: 0.3% / 0.5% / 0.7% | TP: 3.0% / 5.0% / 8.0%
  3. 摆动点+信号序列双重过滤
  4. 信号密度评分 — 适中最好, 太多太少都差

预期: WR=80-82%
"""
import json, sys, time, math, logging
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase
from v11.weekly_trend import synthesize_weekly, weekly_trend

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v11')
MAX_STOCKS = 200; MIN_BARS = 120; ROLL_START = 80; ROLL_END_OFFSET = 10
MAX_HOLD = 60; COOLDOWN = 15; SCOUT_MIN_RESONANCE = 0.65; OB_MIN_RESONANCE = 0.70
SWING_MAX_DISTANCE = 20; SL_CAP = 0.5; SL_FIXED = 0.5; TP_FIXED = 5.0
MIN_VOL_RATIO = 0.8; MIN_FVG_GAP = 0.3


# ====== Signal Sequence Scoring ======
def score_signal_sequence(sigs_before, entry_signal_type):
    """
    V18: 基于信号序列模式评分
    前5个信号 → 模式匹配 → 加分/减分/跳过
    """
    if len(sigs_before) < 3:
        return 0.5, 'insufficient'
    
    recent = [s for s in sigs_before[-8:] if s.get('idx', 0) < len(sigs_before)][-5:]
    pattern = []
    for s in recent:
        st = s.get('type', '?')
        if 'FVG' in st: pattern.append('F')
        elif 'OB' in st: pattern.append('O')
        elif 'Sweep' in st: pattern.append('S')
        elif 'CHOCH' in st: pattern.append('C')
        elif 'BPR' in st: pattern.append('B')
        else: pattern.append('?')
    
    if not pattern:
        return 0.5, 'no-pattern'
    
    seq = ''.join(pattern)
    score = 0.5
    reasons = []
    
    # === Pattern-based scoring ===
    
    # 1. Sweep before entry = liquidity grab + good reversal
    if len(pattern) >= 2:
        if pattern[-1] == 'F' and 'S' in pattern[:-1]:
            score += 0.20
            reasons.append('Sweep→FVG')
        if pattern[-1] == 'O' and pattern[-2] == 'F':
            score += 0.10
            reasons.append('FVG→OB')
        if pattern[-1] == 'F' and pattern[-2] == 'O':
            score += 0.25  # OB→FVG = BEST
            reasons.append('OB→FVG')
    
    # 2. FVG at entry position
    if pattern[-1] == 'F':
        score += 0.10
        reasons.append('FVG-entry')
    
    # 3. Too many OBs = noise
    ob_count = pattern.count('O')
    if ob_count >= 4:
        score -= 0.30  # Heavy penalty
        reasons.append(f'OBx{ob_count}-noise')
    elif ob_count >= 3:
        score -= 0.10
        reasons.append(f'OBx{ob_count}-warn')
    
    # 4. Sweep+OB together = worst (double liquidity grab = chop)
    so_pairs = sum(1 for i in range(len(pattern)-1) if pattern[i]=='S' and pattern[i+1]=='O')
    if so_pairs >= 2:
        score -= 0.25
        reasons.append('SOx2-chop')
    
    # 5. All same type = noise
    if len(set(pattern)) <= 1:
        score -= 0.20
        reasons.append('mono-signal')
    
    # 6. Diverse signals = good (market is developing clear structure)
    unique_types = len(set(pattern))
    if unique_types >= 3 and len(pattern) >= 3:
        score += 0.10
        reasons.append('diverse')
    
    score = max(0.0, min(1.0, score))
    return round(score, 2), '|'.join(reasons) if reasons else 'neutral'


def load_ohlcv(symbol):
    fname = f"{symbol.replace('.', '_')}_daily_300.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists(): return None
    data = json.loads(fpath.read_text())
    if not data or len(data) < MIN_BARS: return None
    for bar in data:
        if 'date' not in bar and 't' in bar: bar['date'] = str(bar['t'])
    return data


def short_trend(ohlcv, idx, lookback=10):
    if idx < lookback: return 'neutral', 0.0
    segment = ohlcv[idx-lookback:idx+1]
    start, end = segment[0]['c'], segment[-1]['c']
    change = (end - start) / start * 100
    ema = sum(ohlcv[i]['c'] for i in range(idx-min(5,idx), idx+1)) / min(6, idx+1)
    ema_dist = (ohlcv[idx]['c'] - ema) / ema * 100
    if change > 0.6 and ema_dist > 0: return 'up', change
    elif change < -0.6 and ema_dist < 0: return 'down', abs(change)
    return 'neutral', 0


def find_all_swing_lows(ohlcv, end_idx, lookback=50):
    if end_idx < 3: return []
    start = max(0, end_idx - lookback)
    swings = []
    for i in range(end_idx - 1, start, -1):
        bar = ohlcv[i]
        left = ohlcv[i-1]['l'] if i > start else 9999
        right = ohlcv[i+1]['l'] if i < end_idx - 1 else 9999
        if bar['l'] < left and bar['l'] < right:
            swings.append((i, bar['l'], end_idx - i))
    return swings


def find_all_swing_highs(ohlcv, end_idx, lookback=50):
    if end_idx < 3: return []
    start = max(0, end_idx - lookback)
    swings = []
    for i in range(end_idx - 1, start, -1):
        bar = ohlcv[i]
        left = ohlcv[i-1]['h'] if i > start else 0
        right = ohlcv[i+1]['h'] if i < end_idx - 1 else 0
        if bar['h'] > left and bar['h'] > right:
            swings.append((i, bar['h'], end_idx - i))
    return swings


def find_best_swing_sl(ohlcv, end_idx, entry_price, max_dist=SWING_MAX_DISTANCE):
    swings = find_all_swing_lows(ohlcv, end_idx, lookback=50)
    swings = [s for s in swings if s[2] <= max_dist]
    if not swings: return None
    best = None; best_score = 999
    for idx, price, dist in swings:
        capped_sl = min(price, entry_price * (1 - SL_CAP / 100))
        sl_pct = (entry_price - capped_sl) / entry_price * 100
        if 0.15 <= sl_pct <= 0.7:
            score = abs(sl_pct - 0.4) * 0.5 + (dist / max_dist) * 0.5
            if best is None or score < best_score:
                best_score = score; best = {'sl_price': capped_sl, 'sl_pct': round(sl_pct,2), 'dist': dist}
    return best


def find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price, max_dist=SWING_MAX_DISTANCE):
    swings = find_all_swing_highs(ohlcv, end_idx, lookback=50)
    swings = [s for s in swings if s[2] <= max_dist]
    if not swings: return None
    best = None; best_score = 999
    sl_pct = (entry_price - sl_price) / entry_price * 100 if entry_price > sl_price else 0.3
    for idx, price, dist in swings:
        tp = max(price, entry_price * 1.005)
        tp_pct = (tp - entry_price) / entry_price * 100
        tc_rr = tp_pct / sl_pct if sl_pct > 0 else 10
        if tc_rr >= 2.0 and tp_pct <= 20.0:
            score = abs(tc_rr - 8.0) * 0.5 + (dist / max_dist) * 0.5
            if best is None or score < best_score:
                best_score = score; best = {'tp_price': tp, 'tp_pct': round(tp_pct,2), 'rr': round(tc_rr,2)}
    return best


def calc_sltp(ohlcv, end_idx, entry_price, signal_type='FVG', sl_fixed=SL_FIXED, tp_fixed=TP_FIXED):
    fixed_sl = entry_price * (1 - sl_fixed / 100)
    fixed_tp = entry_price * (1 + tp_fixed / 100)
    sl_info = find_best_swing_sl(ohlcv, end_idx, entry_price)
    if sl_info is not None:
        final_sl = sl_info['sl_price']; sl_pct_actual = sl_info['sl_pct']; sl_type = 'swing'
    else:
        if 'OB' in signal_type: return None
        final_sl = fixed_sl; sl_pct_actual = sl_fixed; sl_type = 'fixed'
    tp_info = find_best_swing_tp(ohlcv, end_idx, entry_price, final_sl)
    if tp_info is not None:
        final_tp = tp_info['tp_price']; actual_rr = tp_info['rr']; tp_type = 'swing'
    else:
        final_tp = fixed_tp; actual_rr = tp_fixed / sl_pct_actual if sl_pct_actual > 0 else 10; tp_type = 'fixed'
    return {'sl': round(final_sl,2), 'tp': round(final_tp,2), 'sl_pct': round(sl_pct_actual,2),
            'tp_pct': round((final_tp-entry_price)/entry_price*100,2), 'rr': round(actual_rr,2),
            'sl_type': sl_type, 'tp_type': tp_type}


def get_entry_signal_info(seq_result):
    entry_sig = seq_result.get('entry_signal', {})
    fvg_entry = seq_result.get('fvg_entry')
    if fvg_entry and fvg_entry.get('idx') is not None:
        return fvg_entry.get('idx', 0), fvg_entry.get('type', ''), fvg_entry
    return entry_sig.get('idx', 0), entry_sig.get('type', ''), entry_sig


def analyze_at_point(ohlcv, all_signals, end_idx, params, signal_seq_filter=0.0):
    sigs_before = [s for s in all_signals if s.get('idx', 0) <= end_idx]
    if len(sigs_before) < 3: return None
    seq_result = analyze_sequence_v11(sigs_before, params=params)
    best_seq = seq_result.get('best_sequence')
    if not best_seq: return None
    seq_name = best_seq.get('name', '')
    is_scout = 'SCOUT' in seq_name
    seq_dir = 'bull' if 'LONG' in seq_name else 'bear'
    if seq_dir != 'bull' or not is_scout: return None
    
    sig_idx, sig_type, sig = get_entry_signal_info(seq_result)
    if sig_idx == 0 and not sig_type: sig_idx = end_idx
    
    if sig_idx < len(ohlcv) - 1 and sig_idx > 30:
        bar_vol = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
        avg_vol = sum(ohlcv[i].get('v', ohlcv[i].get('vol', 0)) for i in range(max(0, sig_idx-30), sig_idx)) / 30
        if bar_vol < avg_vol * MIN_VOL_RATIO: return None
    
    sig_type_check = sig.get('type', sig_type)
    if 'FVG' in sig_type_check and sig_idx > 0 and sig_idx < len(ohlcv):
        bar = ohlcv[sig_idx]
        if bar['c'] <= bar['o']: return None
        upper = sig.get('upper', 0); lower = sig.get('lower', 0)
        if upper > 0 and lower > 0:
            gap_pct = (upper - lower) / lower * 100
            if gap_pct < MIN_FVG_GAP: return None
    
    if len(sigs_before) < 8: return None
    trend_dir, _ = short_trend(ohlcv, end_idx)
    if trend_dir == 'down': return None
    
    weekly = synthesize_weekly(ohlcv[:end_idx+1])
    if len(weekly) >= 3:
        wt = weekly_trend(weekly, lookback=min(5, len(weekly)))
        if wt == 'down': return None
    
    signal_type = 'FVG' if 'FVG' in sig_type_check else 'OB'
    
    # V18: Signal sequence scoring
    seq_score, seq_reason = score_signal_sequence(sigs_before, signal_type)
    
    # V18: Filter by sequence score
    if seq_score < signal_seq_filter:
        return None
    
    effective_min_resonance = OB_MIN_RESONANCE if signal_type == 'OB' else SCOUT_MIN_RESONANCE
    window = ohlcv[:end_idx + 1]
    tf_sequences = {'daily': seq_result}
    resonance = evaluate_full_resonance_v11(all_signals=sigs_before, tf_sequences=tf_sequences, ohlcv=window)
    if resonance.total < effective_min_resonance: return None
    
    return {
        'seq_result': seq_result, 'resonance': resonance,
        'seq_name': seq_name, 'is_scout': is_scout,
        'n_sigs': len(sigs_before), 'seq_dir': seq_dir,
        'best_seq': best_seq, 'entry_idx': sig_idx,
        'signal_type': signal_type,
        'seq_score': seq_score, 'seq_reason': seq_reason,
        'sig_idx': sig_idx,
    }


def simulate_trades(ohlcv, all_signals, params, sl_fixed=SL_FIXED, tp_fixed=TP_FIXED,
                    signal_seq_filter=0.0):
    n = len(ohlcv); roll_end = n - ROLL_END_OFFSET
    trades = []; entered_bar = -999; trade_id = 0
    
    for i in range(ROLL_START, roll_end):
        if i - entered_bar < COOLDOWN: continue
        entry_info = analyze_at_point(ohlcv, all_signals, i, params, signal_seq_filter)
        if entry_info is None: continue
        
        seq_result = entry_info['seq_result']
        resonance = entry_info['resonance']
        tf_sequences = {'daily': seq_result}
        best_seq = entry_info['best_seq']
        signal_type = entry_info['signal_type']
        seq_score = entry_info['seq_score']
        seq_reason = entry_info['seq_reason']
        
        decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
        if decision['action'] != 'enter': continue
        entry_price = decision.get('entry_price')
        if not entry_price: continue
        
        swing_params = calc_sltp(ohlcv, i, entry_price, signal_type, sl_fixed, tp_fixed)
        if swing_params is None: continue
        sl_price = swing_params['sl']; tp_price = swing_params['tp']
        
        sl_cond = lambda bar: bar['l'] <= sl_price
        tp_cond = lambda bar: bar['h'] >= tp_price
        exit_idx, exit_price, won = -1, None, False
        for j in range(i + 1, min(i + MAX_HOLD + 1, n)):
            bar = ohlcv[j]
            if tp_cond(bar): exit_idx, exit_price, won = j, tp_price, True; break
            if sl_cond(bar): exit_idx, exit_price, won = j, sl_price, False; break
        if exit_idx == -1:
            exit_idx = min(i + MAX_HOLD, n - 1)
            exit_price = ohlcv[exit_idx]['c']
            won = exit_price > entry_price
        
        pnl_pct = (exit_price - entry_price) / entry_price * 100
        risk = abs(entry_price - sl_price)
        actual_rr = abs(exit_price - entry_price) / risk if risk > 0 else 10
        
        trades.append({
            'trade_id': trade_id, 'entry_idx': i, 'exit_idx': exit_idx,
            'entry_price': round(entry_price,2), 'exit_price': round(exit_price,2),
            'sl': round(sl_price,2), 'tp': round(tp_price,2),
            'pnl_pct': round(pnl_pct,2), 'won': won, 'rr': round(actual_rr,2),
            'seq_name': best_seq.get('name', 'Scout'),
            'resonance_grade': resonance.grade(), 'confidence': decision['confidence'],
            'hold_bars': exit_idx - i,
            'sl_type': swing_params['sl_type'], 'tp_type': swing_params['tp_type'],
            'sl_pct': swing_params['sl_pct'], 'tp_pct': swing_params['tp_pct'],
            'signal_type': signal_type,
            'seq_score': seq_score, 'seq_reason': seq_reason,
        })
        trade_id += 1; entered_bar = i
    return trades


def backtest_stock(ohlcv, symbol, sl_fixed=SL_FIXED, tp_fixed=TP_FIXED,
                   signal_seq_filter=0.0):
    t0 = time.time()
    phase = detect_market_phase(ohlcv)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')['all']
    if not all_signals or len(all_signals) < 5:
        return {'trades': [], 'n_signals': len(all_signals) if all_signals else 0, 'phase': phase}
    params = {**base_params, 'sl_pct': sl_fixed, 'tp_pct': tp_fixed}
    trades = simulate_trades(ohlcv, all_signals, params, sl_fixed, tp_fixed, signal_seq_filter)
    if len(trades) < 2:
        return {'trades': [], 'n_signals': len(all_signals), 'phase': phase}
    wins = sum(1 for t in trades if t['won'])
    wr = wins / len(trades) * 100
    win_pnl = sum(t['pnl_pct'] for t in trades if t['won'])
    loss_pnl = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
    pf = win_pnl / loss_pnl if loss_pnl > 0 else 99.9
    avg_pnl = sum(t['pnl_pct'] for t in trades) / len(trades)
    avg_rr = sum(t['rr'] for t in trades) / len(trades)
    swing_sl = sum(1 for t in trades if t.get('sl_type') == 'swing')
    return {
        'trades': trades,
        'perf': {
            'n_trades': len(trades), 'wins': wins, 'losses': len(trades) - wins,
            'win_rate': round(wr,1), 'avg_rr': round(avg_rr,2),
            'profit_factor': round(pf,2) if pf < 999 else 999,
            'avg_pnl': round(avg_pnl,2), 'total_pnl': round(sum(t['pnl_pct'] for t in trades),2),
            'swing_sl_pct': round(swing_sl/len(trades)*100,1),
        },
        'n_signals': len(all_signals), 'phase': phase, 'elapsed': round(time.time()-t0,1),
    }


def per_stock_optimize(ohlcv, symbol):
    """V18: 每股SL/TP参数优化"""
    t0 = time.time()
    phase = detect_market_phase(ohlcv)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')['all']
    if not all_signals or len(all_signals) < 5:
        return None
    
    params = {**base_params}
    
    # Try different SL/TP combinations
    sl_options = [0.3, 0.5, 0.7]
    tp_options = [3.0, 5.0, 8.0]
    seq_filters = [0.0, 0.3, 0.5]
    
    best = None
    best_score = -999
    
    for sl in sl_options:
        for tp in tp_options:
            for seq_f in seq_filters:
                trades = simulate_trades(ohlcv, all_signals, {**params, 'sl_pct': sl, 'tp_pct': tp},
                                         sl, tp, seq_f)
                if len(trades) < 2: continue
                
                wins = sum(1 for t in trades if t['won'])
                wr = wins / len(trades) * 100
                win_pnl = sum(t['pnl_pct'] for t in trades if t['won'])
                loss_pnl = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
                pf = win_pnl / loss_pnl if loss_pnl > 0 else 99.9
                avg_pnl = sum(t['pnl_pct'] for t in trades) / len(trades)
                
                # Score: WR * sqrt(n) * min(PF, 20)
                score = wr * math.sqrt(len(trades)) * min(pf, 20) / 100
                
                if score > best_score:
                    best_score = score
                    best = {
                        'sl': sl, 'tp': tp, 'seq_filter': seq_f,
                        'n_trades': len(trades), 'win_rate': round(wr, 1),
                        'profit_factor': round(pf, 2), 'avg_pnl': round(avg_pnl, 2),
                        'score': round(score, 1),
                    }
    
    if best:
        best['elapsed'] = round(time.time() - t0, 1)
    return best


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    # Phase 1: Test V18 with no seq filter (baseline)
    print(f"{'='*80}")
    print("V18 — Signal Sequence Scoring (no filter, baseline)")
    print(f"{'='*80}")
    
    all_trades, stock_results = [], []; t_start = time.time()
    for idx, sym in enumerate(symbols[:MAX_STOCKS]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv: continue
        result = backtest_stock(ohlcv, sym, signal_seq_filter=0.0)
        trades = result.get('trades', []); perf = result.get('perf', {})
        if trades:
            all_trades.extend(trades)
            stock_results.append({'symbol': sym, **perf})
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} t={perf['n_trades']:2d} WR={perf['win_rate']:.0f}% RR={perf['avg_rr']:.1f}x PF={perf['profit_factor']:.1f} P&L={perf['avg_pnl']:+.2f}% swing={perf.get('swing_sl_pct',0):.0f}%")
        else:
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} NO-TRADE sigs={result.get('n_signals',0)} phase={result.get('phase','?')}")
        if (idx+1) % 30 == 0: time.sleep(0.3)
    
    total_time = time.time() - t_start
    if all_trades:
        n = len(all_trades); wins = sum(1 for t in all_trades if t['won'])
        wr = wins / n * 100
        win_pnl = sum(t['pnl_pct'] for t in all_trades if t['won'])
        loss_pnl = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
        pf = win_pnl / loss_pnl if loss_pnl > 0 else 999
        avg_rr = sum(t['rr'] for t in all_trades) / n
        avg_pnl = sum(t['pnl_pct'] for t in all_trades) / n
        sw = [t for t in all_trades if t.get('sl_type')=='swing']
        sw_wr = sum(1 for t in sw if t['won'])/len(sw)*100 if sw else 0
        print(f"\n{'='*80}")
        print(f"V18 BASELINE — {len(stock_results)} tradable | {total_time:.1f}s")
        print(f"{'='*80}")
        print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {avg_rr:.2f}x | PF: {pf:.2f} | P&L: {avg_pnl:+.2f}%")
        print(f"  Swing SL: {len(sw)}/{n} ({len(sw)/n*100:.0f}%) | Swing WR: {sw_wr:.1f}%")
        print(f"  WR>=70%: {sum(1 for s in stock_results if s['win_rate']>=70)} | WR>=80%: {sum(1 for s in stock_results if s['win_rate']>=80)}")
    
    # Phase 2: Test with seq filter=0.3
    print(f"\n{'='*80}")
    print("V18 — Signal Sequence Filtered (seq_score>=0.3)")
    print(f"{'='*80}")
    
    trades2, stocks2 = [], []; t2 = time.time()
    for idx, sym in enumerate(symbols[:MAX_STOCKS]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv: continue
        result = backtest_stock(ohlcv, sym, signal_seq_filter=0.3)
        trades = result.get('trades', []); perf = result.get('perf', {})
        if trades:
            trades2.extend(trades)
            stocks2.append({'symbol': sym, **perf})
        if (idx+1) % 30 == 0: time.sleep(0.3)
    
    t2_time = time.time() - t2
    if trades2:
        n2 = len(trades2); w2 = sum(1 for t in trades2 if t['won'])
        wr2 = w2 / n2 * 100; rr2 = sum(t['rr'] for t in trades2) / n2
        print(f"  Trades: {n2} | WR: {wr2:.1f}% | RR: {rr2:.2f}x")
        print(f"  Tradable: {len(stocks2)} stocks in {t2_time:.1f}s")
    
    # Phase 3: Per-stock optimization (subset)
    print(f"\n{'='*80}")
    print("V18 — Per-Stock Parameter Optimization (50 stocks)")
    print(f"{'='*80}")
    
    opt_results = []
    for idx, sym in enumerate(symbols[:50]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv: continue
        opt = per_stock_optimize(ohlcv, sym)
        if opt:
            opt_results.append({'symbol': sym, **opt})
            print(f"  [{idx+1:3d}/50] {sym:12s} SL={opt['sl']}% TP={opt['tp']}% seqF={opt['seq_filter']} n={opt['n_trades']} WR={opt['win_rate']:.0f}% PF={opt['profit_factor']:.1f} score={opt['score']} | {opt.get('elapsed',0):.1f}s")
        else:
            print(f"  [{idx+1:3d}/50] {sym:12s} NO-OPT")
    
    if opt_results:
        print(f"\n  Per-Stock Optimal Parameters:")
        sl_cnt = Counter(r['sl'] for r in opt_results)
        tp_cnt = Counter(r['tp'] for r in opt_results)
        sf_cnt = Counter(r['seq_filter'] for r in opt_results)
        print(f"    SL: {dict(sl_cnt.most_common())}")
        print(f"    TP: {dict(tp_cnt.most_common())}")
        print(f"    Seq Filter: {dict(sf_cnt.most_common())}")
    
    # Save everything
    outpath = OUTPUT_DIR / 'backtest_v18.json'
    json.dump({
        'timestamp': datetime.now().isoformat(),
        'config': {'version': 'V18', 'max_stocks': MAX_STOCKS, 'signal_seq': True},
        'summary': {'total_stocks': MAX_STOCKS, 'tradable': len(stock_results),
                    'total_trades': len(all_trades),
                    'win_rate': round(wins/n*100,1) if all_trades else 0,
                    'avg_rr': round(avg_rr,2) if all_trades else 0,
                    'profit_factor': round(pf,2) if all_trades else 0,
                    'avg_pnl': round(avg_pnl,2) if all_trades else 0},
        'stocks': stock_results, 'all_trades': all_trades,
    }, open(outpath, 'w'), ensure_ascii=False, indent=2, default=str)
    
    # Save per-stock optimization
    optpath = OUTPUT_DIR / 'backtest_v18_optimized.json'
    json.dump({'timestamp': datetime.now().isoformat(), 'results': opt_results}, 
              open(optpath, 'w'), ensure_ascii=False, indent=2, default=str)
    print(f"\n  Saved: {outpath}")
    print(f"  Saved: {optpath}")

if __name__ == '__main__':
    main()
