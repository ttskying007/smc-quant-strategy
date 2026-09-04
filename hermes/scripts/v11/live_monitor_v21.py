#!/usr/bin/env python3
"""
SMC V21 — Real-Time Signal Monitor
====================================
每天扫描全市场, 输出可交易信号列表

用法:
  # 单次运行
  python3 v11/live_monitor_v21.py
  
  # 每日定时 (cron)
  0 9 * * 1-5 cd ~/.hermes/scripts && python3 v11/live_monitor_v21.py --deliver

输出: 
  - 终端: 信号列表 + 统计
  - 文件: ~/.hermes/smc_signals/latest_signals.json
  - (可选) 推送: 按信号质量排序的Top50

策略: V21 Final (Swing-Enhanced Scout + Multi-Cycle + Fixed 0.3/3.0)
"""
import json, sys, time, math
from pathlib import Path
from datetime import datetime
from collections import Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase
from v11.weekly_trend import synthesize_weekly, weekly_trend

CACHE_DIR = Path('/root/.hermes/kline_cache')
SIGNAL_DIR = Path('/root/.hermes/smc_signals')
SIGNAL_DIR.mkdir(exist_ok=True)

# === V21 FINAL PARAMS ===
SWING_MAX_DISTANCE = 20
SWING_SL_CAP = 0.5
FIXED_SL = 0.3
FIXED_TP = 3.0
MIN_VOL_RATIO = 0.8
MIN_FVG_GAP = 0.3

# Only scan latest N bars (most recent data)
LOOKBACK = 60  # scan last 60 bars for signals
MIN_TRADE_BARS = 10  # need at least 10 bars behind for SL

# Track which stocks to scan (top 2000 by volume/market cap)
# For now, scan all cached stocks
MAX_STOCKS = 2000


def load_ohlcv(symbol):
    fname = f"{symbol.replace('.', '_')}_daily_300.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists(): return None
    data = json.loads(fpath.read_text())
    if not data or len(data) < 120: return None
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

def find_best_swing_sl(ohlcv, end_idx, entry_price):
    swings = find_all_swing_lows(ohlcv, end_idx)
    swings = [s for s in swings if s[2] <= SWING_MAX_DISTANCE]
    if not swings: return None
    best = None; best_score = 999
    for idx, price, dist in swings:
        capped_sl = min(price, entry_price * (1 - SWING_SL_CAP / 100))
        sl_pct = (entry_price - capped_sl) / entry_price * 100
        if 0.15 <= sl_pct <= 0.7:
            score = abs(sl_pct - 0.4) * 0.5 + (dist / SWING_MAX_DISTANCE) * 0.5
            if best is None or score < best_score:
                best_score = score; best = {'sl_price': capped_sl, 'sl_pct': round(sl_pct,2)}
    return best

def find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price):
    swings = find_all_swing_highs(ohlcv, end_idx)
    swings = [s for s in swings if s[2] <= SWING_MAX_DISTANCE]
    if not swings: return None
    best = None; best_score = 999
    sl_pct = (entry_price - sl_price) / entry_price * 100 if entry_price > sl_price else 0.3
    for idx, price, dist in swings:
        tp = max(price, entry_price * 1.005)
        tp_pct = (tp - entry_price) / entry_price * 100
        tc_rr = tp_pct / sl_pct if sl_pct > 0 else 10
        if tc_rr >= 2.0 and tp_pct <= 20.0:
            score = abs(tc_rr - 8.0) * 0.5 + (dist / SWING_MAX_DISTANCE) * 0.5
            if best is None or score < best_score:
                best_score = score; best = {'tp_price': tp, 'tp_pct': round(tp_pct,2)}
    return best

def calc_sltp(ohlcv, end_idx, entry_price, signal_type='FVG'):
    fixed_sl = entry_price * (1 - FIXED_SL / 100)
    fixed_tp = entry_price * (1 + FIXED_TP / 100)
    sl_info = find_best_swing_sl(ohlcv, end_idx, entry_price)
    if sl_info is not None:
        final_sl = sl_info['sl_price']; sl_pct_actual = sl_info['sl_pct']; sl_type = 'swing'
    else:
        if 'OB' in signal_type: return None
        final_sl = fixed_sl; sl_pct_actual = FIXED_SL; sl_type = 'fixed'
    tp_info = find_best_swing_tp(ohlcv, end_idx, entry_price, final_sl)
    if tp_info is not None:
        final_tp = tp_info['tp_price']; tp_pct = tp_info['tp_pct']
        actual_rr = tp_pct / sl_pct_actual if sl_pct_actual > 0 else 10; tp_type = 'swing'
    else:
        final_tp = fixed_tp; tp_pct = FIXED_TP
        actual_rr = FIXED_TP / sl_pct_actual if sl_pct_actual > 0 else 10; tp_type = 'fixed'
    return {'sl': round(final_sl,2), 'tp': round(final_tp,2), 'sl_pct': round(sl_pct_actual,2),
            'tp_pct': round(tp_pct,2), 'rr': round(actual_rr,2), 'sl_type': sl_type, 'tp_type': tp_type}


def analyze_current_signals(ohlcv, symbol):
    """
    V21: 在最新数据上检测可交易信号
    只扫描最后60根K线 (最新数据)
    """
    n = len(ohlcv)
    if n < 120: return None
    
    # Detect signals on full data
    phase = detect_market_phase(ohlcv)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    signal_result = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')
    all_signals = signal_result.get('all', [])
    
    if not all_signals or len(all_signals) < 5:
        return None
    
    params = {**base_params, 'sl_pct': FIXED_SL, 'tp_pct': FIXED_TP}
    
    # Scan the last LOOKBACK bars for entry opportunities
    signals_found = []
    entered_bar = -999
    
    for i in range(max(n - LOOKBACK, 80), n - 10):
        if i - entered_bar < 15: continue
        
        sigs_before = [s for s in all_signals if s.get('idx', 0) <= i]
        if len(sigs_before) < 3: continue
        
        seq_result = analyze_sequence_v11(sigs_before, params=params)
        best_seq = seq_result.get('best_sequence')
        if not best_seq: continue
        seq_name = best_seq.get('name', '')
        is_scout = 'SCOUT' in seq_name
        seq_dir = 'bull' if 'LONG' in seq_name else 'bear'
        if seq_dir != 'bull' or not is_scout: continue
        
        # Signal quality
        from v11.rolling_backtest_v15 import get_entry_signal_info
        sig_idx, sig_type, sig = get_entry_signal_info(seq_result)
        if sig_idx == 0 and not sig_type: sig_idx = i
        
        # Volume check
        if sig_idx < n - 1 and sig_idx > 30:
            bar_vol = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
            avg_vol = sum(ohlcv[j].get('v', ohlcv[j].get('vol', 0)) for j in range(max(0, sig_idx-30), sig_idx)) / 30
            if bar_vol < avg_vol * MIN_VOL_RATIO: continue
        
        sig_type_check = sig.get('type', sig_type)
        if 'FVG' in sig_type_check and sig_idx > 0 and sig_idx < n:
            bar = ohlcv[sig_idx]
            if bar['c'] <= bar['o']: continue
            upper = sig.get('upper', 0); lower = sig.get('lower', 0)
            if upper > 0 and lower > 0:
                gap_pct = (upper - lower) / lower * 100
                if gap_pct < MIN_FVG_GAP: continue
        
        # Trend
        trend_dir, _ = short_trend(ohlcv, i)
        if trend_dir == 'down': continue
        weekly = synthesize_weekly(ohlcv[:i+1])
        if len(weekly) >= 3 and weekly_trend(weekly, lookback=min(5, len(weekly))) == 'down': continue
        
        signal_type = 'FVG' if 'FVG' in sig_type_check else 'OB'
        
        # Multi-cycle filter
        micro = short_trend(ohlcv, i, lookback=8)
        meso = short_trend(ohlcv, i, lookback=20)
        macro = short_trend(ohlcv, i, lookback=40)
        up_count = sum(1 for c in [micro, meso, macro] if c[0] == 'up')
        down_count = sum(1 for c in [micro, meso, macro] if c[0] == 'down')
        if down_count >= 2 or (up_count == 1 and down_count == 0):
            continue
        
        cycle_score = up_count / 3.0
        effective_res = 0.55 if cycle_score >= 0.85 else 0.65
        if signal_type == 'OB': effective_res = max(effective_res, 0.70)
        
        window = ohlcv[:i + 1]
        tf_sequences = {'daily': seq_result}
        resonance = evaluate_full_resonance_v11(all_signals=sigs_before, tf_sequences=tf_sequences, ohlcv=window)
        if resonance.total < effective_res: continue
        
        decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
        if decision['action'] != 'enter': continue
        entry_price = decision.get('entry_price')
        if not entry_price: continue
        
        swing_params = calc_sltp(ohlcv, i, entry_price, signal_type)
        if swing_params is None: continue
        
        # Quality score for ranking
        quality = resonance.total
        if swing_params['sl_type'] == 'swing': quality += 0.2
        if signal_type == 'FVG': quality += 0.1
        quality += cycle_score * 0.2
        
        signals_found.append({
            'symbol': symbol,
            'bar_date': ohlcv[i].get('date', ohlcv[i].get('t', '')),
            'signal_type': signal_type,
            'entry_price': entry_price,
            'sl': swing_params['sl'],
            'tp': swing_params['tp'],
            'sl_type': swing_params['sl_type'],
            'rr': swing_params['rr'],
            'quality': round(quality, 2),
            'cycle': f"{'↑' if micro[0]=='up' else '→'}{'↑' if meso[0]=='up' else '→'}{'↑' if macro[0]=='up' else '→'}",
            'signal_count': len(sigs_before),
        })
        entered_bar = i
    
    return signals_found


def main():
    import argparse
    parser = argparse.ArgumentParser(description='SMC V21 Live Signal Monitor')
    parser.add_argument('--deliver', action='store_true', help='Format output for delivery')
    parser.add_argument('--top', type=int, default=30, help='Show top N signals')
    parser.add_argument('--quick', action='store_true', help='Scan fewer stocks (quick test)')
    args = parser.parse_args()
    
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    if args.quick:
        symbols = symbols[:200]
    else:
        symbols = symbols[:MAX_STOCKS]
    
    # V23: Pre-screen for swing quality
    print(f"  Loading quality ratings...")
    q_path = SIGNAL_DIR / 'stock_quality_ratings.json'
    quality_filter = {}
    if q_path.exists():
        q_data = json.loads(q_path.read_text())
        for entry in q_data.get('stocks', []):
            quality_filter[entry['symbol']] = entry
    
    print(f"V23 Live Monitor — Scanning {len(symbols)} stocks (quality filtered)...")
    print(f"  Swing coverage filter >=30% | Phase-adaptive SL/TP")
    
    all_signals = []
    t_start = time.time()
    
    for idx, sym in enumerate(symbols):
        ohlcv = load_ohlcv(sym)
        if not ohlcv: continue
        
        signals = analyze_current_signals(ohlcv, sym)
        if signals:
            all_signals.extend(signals)
        
        if (idx + 1) % 100 == 0:
            elapsed = time.time() - t_start
            print(f"  [{idx+1}/{len(symbols)}] {len(all_signals)} signals found | {elapsed:.0f}s")
    
    total_time = time.time() - t_start
    print(f"\n{'='*80}")
    print(f"SCAN COMPLETE — {len(symbols)} stocks in {total_time:.0f}s")
    print(f"{'='*80}")
    
    if not all_signals:
        print("No signals found.")
        sys.exit(0)
    
    # Sort by quality
    all_signals.sort(key=lambda x: -x['quality'])
    
    # Stats
    swing = sum(1 for s in all_signals if s['sl_type'] == 'swing')
    fvg = sum(1 for s in all_signals if s['signal_type'] == 'FVG')
    ob = sum(1 for s in all_signals if s['signal_type'] == 'OB')
    
    print(f"\nTotal Signals: {len(all_signals)} | Swing SL: {swing} | FVG: {fvg} | OB: {ob}")
    print(f"\nTop {args.top} Signals:")
    print(f"{'#':<4} {'Symbol':<12} {'Type':<6} {'Entry':<10} {'SL':<10} {'TP':<10} {'RR':<6} {'Q':<6} {'Cycle':<10} {'Date':<12}")
    print("-"*90)
    
    for i, s in enumerate(all_signals[:args.top]):
        print(f"{i+1:<4} {s['symbol']:<12} {s['signal_type']:<6} "
              f"{s['entry_price']:<10.2f} {s['sl']:<10.2f} {s['tp']:<10.2f} "
              f"{s['rr']:<6.1f}x {s['quality']:<6.2f} {s.get('cycle','?'):<10} {s.get('bar_date','?'):<12}")
    
    # Save
    outpath = SIGNAL_DIR / f'live_signals_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
    json.dump({
        'timestamp': datetime.now().isoformat(),
        'config': {'version': 'V21', 'scan_stocks': len(symbols)},
        'summary': {'total_signals': len(all_signals), 'swing_sl': swing, 'fvg': fvg, 'ob': ob},
        'signals': all_signals[:100],
    }, open(outpath, 'w'), ensure_ascii=False, indent=2, default=str)
    print(f"\nSaved: {outpath}")
    
    # Also save latest (overwrite)
    latest = SIGNAL_DIR / 'latest_signals.json'
    json.dump({'timestamp': datetime.now().isoformat(), 'signals': all_signals[:50]},
              open(latest, 'w'), default=str)
    print(f"Latest: {latest}")

if __name__ == '__main__':
    main()
