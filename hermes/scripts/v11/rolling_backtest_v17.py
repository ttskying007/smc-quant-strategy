#!/usr/bin/env python3
"""
V17 — Multi-TF Resonance (60min + Daily) FINAL
===============================================
V16基线: WR=76.2%, Swing 77% at 94% WR (4800 stocks)

V17创新 — 60分钟多周期共振:
  1. 60分钟FVG信号 → 日线入场前的提前确认
  2. 60分钟摆动点 → 更精细的SL支撑位
  3. 多周期评分: 60min有FVG=加分, 60min有Sweep+FVG=强加分
  4. 日期对齐: 每日最后2个60minK线 + 最近2个交易日的60min

缓存: /root/.hermes/kline_cache/*_60min_500.json (akshare下载)
"""
import json, sys, time, math, logging
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timedelta

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
MAX_HOLD = 60; COOLDOWN = 15
SWING_MAX_DISTANCE = 20; SL_CAP = 0.5; SL_FIXED = 0.5; TP_FIXED = 5.0
MIN_VOL_RATIO = 0.8; MIN_FVG_GAP = 0.3; OB_MIN_RESONANCE = 0.70


def load_ohlcv(symbol):
    fname = f"{symbol.replace('.', '_')}_daily_300.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists(): return None
    data = json.loads(fpath.read_text())
    if not data or len(data) < MIN_BARS: return None
    for bar in data:
        if 'date' not in bar and 't' in bar: bar['date'] = str(bar['t'])
    return data


def load_60min(symbol):
    """Load 60min data from akshare cache"""
    # Try both SZ and SH suffixes
    code = symbol.split('.')[0]
    for suffix in ['SZ', 'SH']:
        fname = f"{code}_{suffix}_60min_500.json"
        fpath = CACHE_DIR / fname
        if fpath.exists():
            data = json.loads(fpath.read_text())
            if data and len(data) >= 50:
                return data
    return None


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

def find_best_swing_sl(ohlcv, end_idx, entry_price, sl_cap=SL_CAP, max_dist=SWING_MAX_DISTANCE):
    swings = find_all_swing_lows(ohlcv, end_idx, lookback=50)
    swings = [s for s in swings if s[2] <= max_dist]
    if not swings: return None
    best = None; best_score = 999
    for idx, price, dist in swings:
        capped_sl = min(price, entry_price * (1 - sl_cap / 100))
        sl_pct = (entry_price - capped_sl) / entry_price * 100
        if 0.15 <= sl_pct <= 0.7:
            score = abs(sl_pct - 0.4) * 0.5 + (dist / max_dist) * 0.5
            if best is None or score < best_score:
                best_score = score; best = {'sl_price': capped_sl, 'sl_pct': round(sl_pct,2)}
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
                best_score = score; best = {'tp_price': tp, 'tp_pct': round(tp_pct,2)}
    return best

def calc_sltp(ohlcv, end_idx, entry_price, signal_type='FVG'):
    fixed_sl = entry_price * (1 - SL_FIXED / 100)
    fixed_tp = entry_price * (1 + TP_FIXED / 100)
    sl_info = find_best_swing_sl(ohlcv, end_idx, entry_price)
    if sl_info is not None:
        final_sl = sl_info['sl_price']; sl_pct_actual = sl_info['sl_pct']; sl_type = 'swing'
    else:
        if 'OB' in signal_type: return None
        final_sl = fixed_sl; sl_pct_actual = SL_FIXED; sl_type = 'fixed'
    tp_info = find_best_swing_tp(ohlcv, end_idx, entry_price, final_sl)
    if tp_info is not None:
        final_tp = tp_info['tp_price']; tp_pct = tp_info['tp_pct']
        actual_rr = tp_pct / sl_pct_actual if sl_pct_actual > 0 else 10; tp_type = 'swing'
    else:
        final_tp = fixed_tp; tp_pct = TP_FIXED
        actual_rr = TP_FIXED / sl_pct_actual if sl_pct_actual > 0 else 10; tp_type = 'fixed'
    return {'sl': round(final_sl,2), 'tp': round(final_tp,2), 'sl_pct': round(sl_pct_actual,2),
            'tp_pct': round(tp_pct,2), 'rr': round(actual_rr,2), 'sl_type': sl_type, 'tp_type': tp_type}


def get_entry_signal_info(seq_result):
    entry_sig = seq_result.get('entry_signal', {})
    fvg_entry = seq_result.get('fvg_entry')
    if fvg_entry and fvg_entry.get('idx') is not None:
        return fvg_entry.get('idx', 0), fvg_entry.get('type', ''), fvg_entry
    return entry_sig.get('idx', 0), entry_sig.get('type', ''), entry_sig


def check_60min_before_daily_entry(daily_bar_date, min60_data, daily_sigs_before_entry):
    """
    V17: 检查日线入场前, 60min是否有提前信号
    返回: 时间对齐的60min信号评分 (0.0-1.0)
    """
    if not min60_data or len(min60_data) < 20:
        return 0.5, 'no-60min'
    
    # Parse daily bar date for matching
    daily_start = daily_bar_date[:10] if daily_bar_date else ''
    
    # Count 60min bars that fall on or near the same day
    recent_60 = []
    for i, bar in enumerate(min60_data):
        bar_date = str(bar.get('t', bar.get('date', '')))[:10]
        if bar_date and bar_date >= daily_start:
            recent_60.append((i, bar))
            if len(recent_60) > 20:  # last 20 60min bars
                break
    
    # Last 8 60min bars (2 trading days)
    last_8 = [b for _, b in recent_60[-8:]] if recent_60 else []
    if len(last_8) < 4:
        return 0.5, 'insufficient-60min'
    
    # Run signal detection on these recent 60min bars
    # Simple: check for FVG patterns manually
    fvg_count = 0
    ob_count = 0
    sweep_count = 0
    
    for i in range(1, len(last_8) - 1):
        prev, curr, next_b = last_8[i-1], last_8[i], last_8[i+1]
        
        # FVG detection (gap between high and low)
        fvg_high = min(prev['h'], curr['h'])
        fvg_low = max(prev['l'], curr['l'])
        if fvg_high > fvg_low:
            gap_pct = (fvg_high - fvg_low) / fvg_low * 100
            if gap_pct >= MIN_FVG_GAP and curr['c'] > curr['o']:
                fvg_count += 1
        
        # Sweep detection
        if prev['c'] > prev['o'] and curr['l'] < prev['l'] and curr['c'] > curr['o']:
            sweep_count += 1
        
        # OB detection
        body = abs(curr['c'] - curr['o'])
        upper_wick = curr['h'] - max(curr['c'], curr['o'])
        if upper_wick > body * 2 and curr['c'] > curr['o']:
            ob_count += 1
    
    # Score based on 60min signals
    score = 0.5
    details = []
    
    if fvg_count >= 2:
        score += 0.20
        details.append(f'{fvg_count}xFVG')
    elif fvg_count >= 1:
        score += 0.10
        details.append('1xFVG')
    
    if sweep_count >= 1:
        score += 0.15
        details.append('SWEEP')
    
    if sweep_count >= 1 and fvg_count >= 1:
        score += 0.10  # Sweep→FVG bonus
        details.append('Sweep+FVG')
    
    if ob_count >= 2:
        score -= 0.10  # Too much OB
        details.append('OB-noise')
    
    score = max(0.0, min(1.0, score))
    return round(score, 2), '|'.join(details) if details else 'neutral'


def analyze_at_point(ohlcv, min60_data, all_signals, end_idx, params):
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
    
    # V17: Multi-TF 60min resonance check
    daily_bar = ohlcv[end_idx] if end_idx < len(ohlcv) else {}
    daily_date = daily_bar.get('date', daily_bar.get('t', ''))
    tf60_score, tf60_detail = check_60min_before_daily_entry(daily_date, min60_data, sigs_before)
    
    # Reduce daily resonance threshold if 60min confirms
    effective_min_resonance = 0.65
    if tf60_score >= 0.7:
        effective_min_resonance = 0.55  # 60min confirms → easier daily entry
    if signal_type == 'OB':
        effective_min_resonance = max(effective_min_resonance, 0.70)
    
    window = ohlcv[:end_idx + 1]
    tf_sequences = {'daily': seq_result}
    resonance = evaluate_full_resonance_v11(all_signals=sigs_before, tf_sequences=tf_sequences, ohlcv=window)
    if resonance.total < effective_min_resonance: return None
    
    return {
        'seq_result': seq_result, 'resonance': resonance,
        'seq_name': seq_name, 'is_scout': is_scout,
        'n_sigs': len(sigs_before), 'best_seq': best_seq,
        'signal_type': signal_type,
        'tf60_score': tf60_score, 'tf60_detail': tf60_detail,
    }


def simulate_trades(ohlcv, min60_data, all_signals, params):
    n = len(ohlcv); roll_end = n - ROLL_END_OFFSET
    trades = []; entered_bar = -999; trade_id = 0
    
    for i in range(ROLL_START, roll_end):
        if i - entered_bar < COOLDOWN: continue
        entry_info = analyze_at_point(ohlcv, min60_data, all_signals, i, params)
        if entry_info is None: continue
        
        seq_result = entry_info['seq_result']
        resonance = entry_info['resonance']
        tf_sequences = {'daily': seq_result}
        best_seq = entry_info['best_seq']; signal_type = entry_info['signal_type']
        tf60_score = entry_info['tf60_score']; tf60_detail = entry_info['tf60_detail']
        
        decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
        if decision['action'] != 'enter': continue
        entry_price = decision.get('entry_price')
        if not entry_price: continue
        
        swing_params = calc_sltp(ohlcv, i, entry_price, signal_type)
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
            'resonance_grade': resonance.grade(),
            'hold_bars': exit_idx - i,
            'sl_type': swing_params['sl_type'], 'sl_pct': swing_params['sl_pct'],
            'tp_pct': swing_params['tp_pct'], 'signal_type': signal_type,
            'tf60_score': tf60_score, 'tf60_detail': tf60_detail,
            'has_60min': min60_data is not None,
        })
        trade_id += 1; entered_bar = i
    return trades


def backtest_stock(ohlcv, symbol):
    t0 = time.time()
    phase = detect_market_phase(ohlcv)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')['all']
    if not all_signals or len(all_signals) < 5:
        return {'trades': [], 'n_signals': len(all_signals) if all_signals else 0, 'phase': phase}
    
    # Load 60min data
    min60_data = load_60min(symbol)
    has60 = min60_data is not None and len(min60_data) >= 50
    
    params = {**base_params, 'sl_pct': SL_FIXED, 'tp_pct': TP_FIXED}
    trades = simulate_trades(ohlcv, min60_data, all_signals, params)
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
    high_tf = sum(1 for t in trades if t.get('tf60_score', 0) >= 0.7)
    
    return {
        'trades': trades,
        'perf': {
            'n_trades': len(trades), 'wins': wins, 'losses': len(trades)-wins,
            'win_rate': round(wr,1), 'avg_rr': round(avg_rr,2),
            'profit_factor': round(pf,2) if pf < 999 else 999,
            'avg_pnl': round(avg_pnl,2), 'total_pnl': round(sum(t['pnl_pct'] for t in trades),2),
            'swing_sl_pct': round(swing_sl/len(trades)*100,1),
            'high_tf_pct': round(high_tf/len(trades)*100,1) if trades else 0,
            'has_60min': has60,
        },
        'n_signals': len(all_signals), 'phase': phase, 'elapsed': round(time.time()-t0,1),
    }


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print("V17 — Multi-TF Resonance (60min + Daily)")
    print(f"  200 stocks | 60min FVG pre-confirm | Swing SL same as V16")
    print(f"{'='*80}")
    
    # Check 60min cache availability
    n60 = len(list(CACHE_DIR.glob('*_60min_500.json')))
    print(f"  60min cache: {n60} files available")
    if n60 < 50:
        print(f"  ⚠ Few 60min files — 60min data still downloading in background")
    
    all_trades, stock_results = [], []; t_start = time.time()
    for idx, sym in enumerate(symbols[:MAX_STOCKS]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv: continue
        result = backtest_stock(ohlcv, sym)
        trades = result.get('trades', []); perf = result.get('perf', {})
        if trades:
            all_trades.extend(trades)
            stock_results.append({'symbol': sym, **perf})
            has60 = 'Y' if perf.get('has_60min') else 'N'
            print(f"  [{idx+1:3d}/200] {sym:12s} t={perf['n_trades']:2d} WR={perf['win_rate']:.0f}% RR={perf['avg_rr']:.1f}x PF={perf['profit_factor']:.1f} P&L={perf['avg_pnl']:+.2f}% swing={perf.get('swing_sl_pct',0):.0f}% 60m={has60} tf={perf.get('high_tf_pct',0):.0f}%")
        else:
            print(f"  [{idx+1:3d}/200] {sym:12s} NO-TRADE sigs={result.get('n_signals',0)} phase={result.get('phase','?')} 60m={'Y' if result.get('n_signals',0) and load_60min(sym) else 'N'}")
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
        fx = [t for t in all_trades if t.get('sl_type')!='swing']
        fx_wr = sum(1 for t in fx if t['won'])/len(fx)*100 if fx else 0
        
        # 60min TF analysis
        with_60 = [t for t in all_trades if t.get('has_60min')]
        w60_wr = sum(1 for t in with_60 if t['won'])/len(with_60)*100 if with_60 else 0
        high_tf = [t for t in all_trades if t.get('tf60_score',0) >= 0.7]
        low_tf = [t for t in all_trades if t.get('tf60_score',0) < 0.7]
        ht_wr = sum(1 for t in high_tf if t['won'])/len(high_tf)*100 if high_tf else 0
        lt_wr = sum(1 for t in low_tf if t['won'])/len(low_tf)*100 if low_tf else 0
        
        print(f"\n{'='*80}")
        print(f"V17 MULTI-TF SUMMARY — {len(stock_results)} tradable out of {MAX_STOCKS} | {total_time:.1f}s")
        print(f"{'='*80}")
        print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {avg_rr:.2f}x | PF: {pf:.2f} | P&L: {avg_pnl:+.2f}%")
        print(f"  Swing SL: {len(sw)}/{n} ({len(sw)/n*100:.0f}%) | Swing WR: {sw_wr:.1f}% | Fixed WR: {fx_wr:.1f}%")
        print(f"  With 60min data: {len(with_60)} trades | WR={w60_wr:.1f}%")
        print(f"  Multi-TF>=0.7: {len(high_tf)} trades | WR={ht_wr:.1f}% | <0.7: {len(low_tf)} | WR={lt_wr:.1f}%")
        print(f"  WR>=70%: {sum(1 for s in stock_results if s['win_rate']>=70)} | WR>=80%: {sum(1 for s in stock_results if s['win_rate']>=80)}")
        
        # TF score correlation
        print(f"\n  60min TF Score vs WR:")
        for threshold in [0.5, 0.6, 0.7, 0.8]:
            subset = [t for t in all_trades if t.get('tf60_score',0) >= threshold]
            if subset:
                swr = sum(1 for t in subset if t['won'])/len(subset)*100
                print(f"    TF>={threshold:.1f}: {len(subset):3d} trades | WR={swr:.0f}%")
        
        outpath = OUTPUT_DIR / 'backtest_v17.json'
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'config': {'version': 'V17', 'multi_tf': True},
            'summary': {'total_trades': n, 'tradable': len(stock_results),
                        'win_rate': round(wr,1), 'avg_rr': round(avg_rr,2),
                        'profit_factor': round(pf,2), 'avg_pnl': round(avg_pnl,2)},
            'stocks': stock_results, 'all_trades': all_trades,
        }, open(outpath,'w'), ensure_ascii=False, indent=2, default=str)
        print(f"\n  Saved: {outpath}")

if __name__ == '__main__':
    main()
