#!/usr/bin/env python3
"""
V16 — Distance-Filtered Swing + SL=0.5% Fixed
===============================================
V15瓶颈: 非摆动SL=0.3% WR=27% (太容易被随机波动打掉)
V16修复: 非摆动SL=0.5%(匹配SL_CAP) — V14证实0.5% WR=98%

核心策略:
  1. 20K线内有摆动SL → 黄金(WR=95%)
  2. 20K线外无摆动SL → 固定SL=0.5%(不再是0.3%, 减少假止损)
  3. OB+无摆动SL → 跳过 (V13验证OB固定SL=47.8%)
  4. 周线趋势过滤 | 信号质量过滤
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
MAX_HOLD = 60; COOLDOWN = 15; SCOUT_MIN_RESONANCE = 0.65

# V15: Distance-filtered swing
SWING_LOOKBACK = 50         # 仍然搜索50K线找摆动
SWING_MAX_DISTANCE = 20     # 但只取20K线内的摆动SL
SL_CAP = 0.5
SL_FIXED = 0.5           # 固定SL(改宽到0.5%匹配SL_CAP)
TP_FIXED = 5.0
SWING_TP_MIN_RR = 2.0

# Quality filters
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


def find_all_swing_lows(ohlcv, end_idx, lookback=SWING_LOOKBACK):
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


def find_all_swing_highs(ohlcv, end_idx, lookback=SWING_LOOKBACK):
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
    """V15: 找20K线内的最佳摆动SL"""
    swings = find_all_swing_lows(ohlcv, end_idx, lookback=SWING_LOOKBACK)
    # 只取max_dist内的摆动
    swings = [s for s in swings if s[2] <= max_dist]
    if not swings:
        return None
    
    best = None; best_score = 999
    for idx, price, dist in swings:
        capped_sl = min(price, entry_price * (1 - SL_CAP / 100))
        sl_pct = (entry_price - capped_sl) / entry_price * 100
        if 0.15 <= sl_pct <= 0.7:
            sl_score = abs(sl_pct - 0.4) * 0.5
            dist_score = (dist / max_dist) * 0.5
            if best is None or (sl_score + dist_score) < best_score:
                best_score = sl_score + dist_score
                best = {'sl_price': capped_sl, 'sl_pct': round(sl_pct, 2),
                        'dist': dist, 'idx': idx}
    return best


def find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price, max_dist=SWING_MAX_DISTANCE):
    swings = find_all_swing_highs(ohlcv, end_idx, lookback=SWING_LOOKBACK)
    swings = [s for s in swings if s[2] <= max_dist]
    if not swings: return None
    
    best = None; best_score = 999
    sl_pct = (entry_price - sl_price) / entry_price * 100 if entry_price > sl_price else 0.3
    for idx, price, dist in swings:
        tp = max(price, entry_price * 1.005)
        tp_pct = (tp - entry_price) / entry_price * 100
        tc_rr = tp_pct / sl_pct if sl_pct > 0 else 10
        if tc_rr >= SWING_TP_MIN_RR and tp_pct <= 20.0:
            rr_score = abs(tc_rr - 8.0) * 0.5
            dist_score = (dist / max_dist) * 0.5
            if best is None or (rr_score + dist_score) < best_score:
                best_score = rr_score + dist_score
                best = {'tp_price': tp, 'tp_pct': round(tp_pct, 2),
                        'rr': round(tc_rr, 2), 'dist': dist, 'idx': idx}
    return best


def calc_swing_sltp_v15(ohlcv, end_idx, entry_price, signal_type='FVG'):
    """
    V15: 距离约束摆动SL/TP
    - 20K线内有摆动SL → 使用, WR~95%
    - 20K线外无摆动SL → 退回固定SL(FVG-only)
    """
    fixed_sl = entry_price * (1 - SL_FIXED / 100)
    fixed_tp = entry_price * (1 + TP_FIXED / 100)
    
    sl_info = find_best_swing_sl(ohlcv, end_idx, entry_price, max_dist=SWING_MAX_DISTANCE)
    
    if sl_info is not None:
        # 有近摆动SL → 黄金策略
        final_sl = sl_info['sl_price']
        sl_pct_actual = sl_info['sl_pct']
        sl_dist = sl_info['dist']
        sl_type = 'swing'
    else:
        # 无近摆动SL → OB跳过, 只FVG+固定SL
        if 'OB' in signal_type:
            return None  # OB+无摆动 = 跳过
        final_sl = fixed_sl
        sl_pct_actual = SL_FIXED
        sl_dist = 999
        sl_type = 'fixed'
    
    # TP: 摆动或固定
    tp_info = find_best_swing_tp(ohlcv, end_idx, entry_price, final_sl, max_dist=SWING_MAX_DISTANCE)
    if tp_info is not None:
        final_tp = tp_info['tp_price']
        tp_pct_actual = tp_info['tp_pct']
        actual_rr = tp_info['rr']
        tp_type = 'swing'
    else:
        final_tp = fixed_tp
        tp_pct_actual = TP_FIXED
        actual_rr = TP_FIXED / sl_pct_actual if sl_pct_actual > 0 else 10
        tp_type = 'fixed'
    
    return {
        'sl': round(final_sl, 2), 'tp': round(final_tp, 2),
        'sl_pct': round(sl_pct_actual, 2),
        'tp_pct': round(tp_pct_actual, 2),
        'rr': round(actual_rr, 2),
        'sl_type': sl_type, 'tp_type': tp_type,
        'sl_dist': sl_dist,
    }


def get_entry_signal_info(seq_result):
    entry_sig = seq_result.get('entry_signal', {})
    fvg_entry = seq_result.get('fvg_entry')
    if fvg_entry and fvg_entry.get('idx') is not None:
        return fvg_entry.get('idx', 0), fvg_entry.get('type', ''), fvg_entry
    return entry_sig.get('idx', 0), entry_sig.get('type', ''), entry_sig


def analyze_at_point(ohlcv, all_signals, end_idx, params):
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
        avg_vol = sum(ohlcv[i].get('v', ohlcv[i].get('vol', 0))
                       for i in range(max(0, sig_idx-30), sig_idx)) / 30
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
    }


def simulate_trades(ohlcv, all_signals, params):
    n = len(ohlcv); roll_end = n - ROLL_END_OFFSET
    trades = []; entered_bar = -999; trade_id = 0
    
    for i in range(ROLL_START, roll_end):
        if i - entered_bar < COOLDOWN: continue
        entry_info = analyze_at_point(ohlcv, all_signals, i, params)
        if entry_info is None: continue
        
        seq_result = entry_info['seq_result']
        resonance = entry_info['resonance']
        is_scout = entry_info['is_scout']
        tf_sequences = {'daily': seq_result}
        best_seq = entry_info['best_seq']
        signal_type = entry_info['signal_type']
        
        decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
        if decision['action'] != 'enter': continue
        entry_price = decision.get('entry_price')
        if not entry_price: continue
        
        swing_params = calc_swing_sltp_v15(ohlcv, i, entry_price, signal_type)
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
            'entry_price': round(entry_price, 2), 'exit_price': round(exit_price, 2),
            'sl': round(sl_price, 2), 'tp': round(tp_price, 2),
            'pnl_pct': round(pnl_pct, 2), 'won': won, 'rr': round(actual_rr, 2),
            'seq_name': best_seq.get('name', 'Scout'),
            'resonance_grade': resonance.grade(), 'confidence': decision['confidence'],
            'hold_bars': exit_idx - i,
            'sl_type': swing_params['sl_type'], 'tp_type': swing_params['tp_type'],
            'sl_pct': swing_params['sl_pct'], 'tp_pct': swing_params['tp_pct'],
            'signal_type': signal_type, 'sl_dist': swing_params['sl_dist'],
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
    params = {**base_params, 'sl_pct': SL_FIXED, 'tp_pct': TP_FIXED}
    trades = simulate_trades(ohlcv, all_signals, params)
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
            'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
            'profit_factor': round(pf, 2) if pf < 999 else 999,
            'avg_pnl': round(avg_pnl, 2), 'total_pnl': round(sum(t['pnl_pct'] for t in trades), 2),
            'swing_sl_pct': round(swing_sl / len(trades) * 100, 1),
        },
        'n_signals': len(all_signals), 'phase': phase, 'elapsed': round(time.time() - t0, 1),
    }


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    print(f"{'='*80}")
    print(f"V15 — Distance-Filtered Swing (max_dist={SWING_MAX_DISTANCE})")
    print(f"  {min(MAX_STOCKS, len(symbols))}/{len(symbols)} stocks")
    print(f"  Swing within {SWING_MAX_DISTANCE} bars: WR~95%")
    print(f"  No near swing → FVG-only fixed SL | OB skipped")
    print(f"  Target: WR>=80% | Swing coverage>=60%")
    print(f"{'='*80}")
    
    all_trades, stock_results = [], []; t_start = time.time()
    for idx, sym in enumerate(symbols[:MAX_STOCKS]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv: continue
        result = backtest_stock(ohlcv, sym)
        trades = result.get('trades', []); perf = result.get('perf', {})
        if trades:
            all_trades.extend(trades)
            stock_results.append({'symbol': sym, **perf, 'n_signals': result.get('n_signals', 0), 'phase': result.get('phase', '?')})
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} trades={perf['n_trades']:2d} WR={perf['win_rate']:.0f}% RR={perf['avg_rr']:.1f}x PF={perf['profit_factor']:.1f} P&L={perf['avg_pnl']:+.2f}% swingSL={perf.get('swing_sl_pct',0):.0f}% | {result.get('elapsed',0):.1f}s")
        else:
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} NO-TRADE sigs={result.get('n_signals',0)} phase={result.get('phase','?')}")
        if (idx + 1) % 30 == 0: time.sleep(0.3)
    
    total_time = time.time() - t_start
    print(f"\n{'='*80}")
    print(f"V15 SUMMARY — {len(stock_results)} tradable out of {MAX_STOCKS} | {total_time:.1f}s")
    print(f"{'='*80}")
    
    if all_trades:
        n = len(all_trades); wins = sum(1 for t in all_trades if t['won'])
        wr = wins / n * 100
        win_pnl = sum(t['pnl_pct'] for t in all_trades if t['won'])
        loss_pnl = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
        pf = win_pnl / loss_pnl if loss_pnl > 0 else 999
        avg_rr = sum(t['rr'] for t in all_trades) / n
        avg_pnl = sum(t['pnl_pct'] for t in all_trades) / n
        sw = [t for t in all_trades if t.get('sl_type') == 'swing']
        fx = [t for t in all_trades if t.get('sl_type') != 'swing']
        sw_wr = sum(1 for t in sw if t['won'])/len(sw)*100 if sw else 0
        fx_wr = sum(1 for t in fx if t['won'])/len(fx)*100 if fx else 0
        avg_sl = sum(t.get('sl_pct',0) for t in all_trades)/n
        avg_tp = sum(t.get('tp_pct',0) for t in all_trades)/n
        print(f"\n  Trades: {n} | WR: {wr:.1f}% | Avg RR: {avg_rr:.2f}x | PF: {pf:.2f} | Avg P&L: {avg_pnl:+.2f}%")
        print(f"  Avg SL: {avg_sl:.2f}% | Avg TP: {avg_tp:.2f}%")
        print(f"  Swing SL: {len(sw)}/{n} ({len(sw)/n*100:.0f}%) | Swing WR: {sw_wr:.1f}% | Fixed WR: {fx_wr:.1f}%")
        print(f"  WR>=60%: {sum(1 for s in stock_results if s['win_rate']>=60)} | WR>=70%: {sum(1 for s in stock_results if s['win_rate']>=70)} | WR>=80%: {sum(1 for s in stock_results if s['win_rate']>=80)}")
        fvg_t = [t for t in all_trades if t.get('signal_type')=='FVG']
        ob_t = [t for t in all_trades if t.get('signal_type')=='OB']
        print(f"  FVG: {len(fvg_t)} WR={sum(1 for t in fvg_t if t['won'])/len(fvg_t)*100:.1f}% | OB: {len(ob_t)} WR={sum(1 for t in ob_t if t['won'])/len(ob_t)*100:.1f}%")
        if sw:
            print(f"\n  Swing SL Distance (capped at {SWING_MAX_DISTANCE}):")
            for d_range in [(0,5),(5,10),(10,15),(15,21)]:
                subset = [t for t in sw if d_range[0] <= t.get('sl_dist',999) < d_range[1]]
                if subset:
                    swd = sum(1 for t in subset if t['won'])/len(subset)*100
                    print(f"    dist={d_range[0]}-{d_range[1]}: {len(subset):3d} trades | WR={swd:.0f}%")
        print(f"\n  TOP 10 by WR:")
        for s in sorted(stock_results, key=lambda x: x['win_rate'], reverse=True)[:10]:
            print(f"    {s['symbol']:12s} WR={s['win_rate']:.0f}% RR={s['avg_rr']:.1f}x trades={s['n_trades']} swingSL={s.get('swing_sl_pct',0):.0f}%")
    
    outpath = OUTPUT_DIR / 'backtest_v15.json'
    out = {'timestamp': datetime.now().isoformat(), 'config': {'version': 'V15', 'max_stocks': MAX_STOCKS, 'swing_max_distance': SWING_MAX_DISTANCE, 'sl_cap': SL_CAP, 'sl_fixed': SL_FIXED, 'tp_fixed': TP_FIXED}, 'summary': {'total_stocks': MAX_STOCKS, 'tradable': len(stock_results), 'total_trades': len(all_trades), 'win_rate': round(wr, 1) if all_trades else 0, 'avg_rr': round(avg_rr, 2) if all_trades else 0, 'profit_factor': round(pf, 2) if all_trades else 0, 'avg_pnl': round(avg_pnl, 2) if all_trades else 0}, 'stocks': stock_results, 'all_trades': all_trades}
    outpath.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print(f"\n  Saved: {outpath}")

if __name__ == '__main__':
    main()
