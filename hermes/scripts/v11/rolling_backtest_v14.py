#!/usr/bin/env python3
"""
V14 — Extreme Swing Coverage + Adaptive SL/TP
==============================================
核心目标: 提高摆动SL覆盖率从40%→80%, 推动WR从74%→82%+

基于V13发现:
  - Swing SL WR=97.3% (150笔) — 黄金策略
  - Fixed SL WR=59.0% (229笔) — 瓶颈
  - Fixed SL全部是FVG (OB过滤完美)
  - 固定SL损失平均-0.29%, 太小不致命但拉低WR

V14核心改进:
  1. 摆动检测lookback=50 (从25扩展) — 覆盖更多
  2. 多摆动点备选: 不只是最近, 寻找最佳摆动SL (最接近0.5%的)
  3. 距离衰减: 摆动点越远, 信号分越低 (但不是直接跳过)
  4. Fixed SL提升: 当摆动SL不可用时按FVG-only+质量二次过滤
  5. 动量过滤: 小阳线确认 (不是任何上涨都行)
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

# V14: Extreme swing coverage
SWING_LOOKBACK = 50       # 25→50: 两个月日线数据
SL_CAP = 0.5
SL_FIXED = 0.3
TP_FIXED = 5.0
SWING_TP_MIN_RR = 2.0
SWING_SL_FAR_THRESHOLD = 20  # 超过20根K线的摆动算"远"

# Quality filters
MIN_VOL_RATIO = 0.8
MIN_FVG_GAP = 0.3
OB_MIN_RESONANCE = 0.70


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
    """找所有摆动低点, 返回[(idx, price, dist), ...]"""
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
    """找所有摆动高点"""
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


def find_best_swing_sl(ohlcv, end_idx, entry_price, lookback=SWING_LOOKBACK):
    """V14: 找最佳摆动SL — 不取最近, 取最接近0.5%的"""
    swings = find_all_swing_lows(ohlcv, end_idx, lookback)
    if not swings:
        return None
    
    best = None
    best_score = 999
    
    for idx, price, dist in swings:
        capped_sl = min(price, entry_price * (1 - SL_CAP / 100))
        sl_pct = (entry_price - capped_sl) / entry_price * 100
        if 0.15 <= sl_pct <= 0.7:
            # Score: prefer SL close to 0.5% AND close distance
            sl_score = abs(sl_pct - 0.4) * 0.6  # SL closeness (weight 60%)
            dist_score = (dist / SWING_LOOKBACK) * 0.4  # distance penalty (weight 40%)
            # Distance penalty: nearer = better
            dist_penalty = dist / 50.0 if dist > 10 else 0
            combined = sl_score + dist_penalty
            
            if best is None or combined < best_score:
                best_score = combined
                best = {
                    'sl_price': capped_sl, 'sl_pct': round(sl_pct, 2),
                    'dist': dist, 'idx': idx,
                }
    
    return best


def find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price, lookback=SWING_LOOKBACK):
    """V14: 找最佳摆动TP"""
    swings = find_all_swing_highs(ohlcv, end_idx, lookback)
    if not swings:
        return None
    
    best = None
    best_score = 999
    sl_pct = (entry_price - sl_price) / entry_price * 100 if entry_price > sl_price else 0.3
    
    for idx, price, dist in swings:
        tp = max(price, entry_price * 1.005)
        tp_pct = (tp - entry_price) / entry_price * 100
        tc_rr = tp_pct / sl_pct if sl_pct > 0 else 10
        
        if tc_rr >= SWING_TP_MIN_RR and tp_pct <= 20.0:
            # Score: prefer moderate RR (5-10x) and close distance
            rr_score = abs(tc_rr - 8.0) * 0.5
            dist_score = (dist / SWING_LOOKBACK) * 0.5
            combined = rr_score + dist_score
            
            if best is None or combined < best_score:
                best_score = combined
                best = {
                    'tp_price': tp, 'tp_pct': round(tp_pct, 2),
                    'rr': round(tc_rr, 2), 'dist': dist, 'idx': idx,
                }
    
    return best


def calc_swing_sltp_v14(ohlcv, end_idx, entry_price, signal_type='FVG'):
    """V14: 摆动+固定SL混合策略"""
    fixed_sl = entry_price * (1 - SL_FIXED / 100)
    fixed_tp = entry_price * (1 + TP_FIXED / 100)
    
    # 找最佳摆动SL
    sl_info = find_best_swing_sl(ohlcv, end_idx, entry_price)
    
    final_sl = fixed_sl
    sl_type = 'fixed'
    sl_pct_actual = SL_FIXED
    sl_dist = 999
    
    if sl_info is not None:
        final_sl = sl_info['sl_price']
        sl_pct_actual = sl_info['sl_pct']
        sl_dist = sl_info['dist']
        sl_type = 'swing'
    
    # V14: 非摆动SL时OB跳过
    if sl_type == 'fixed' and 'OB' in signal_type:
        return None
    
    # 找摆动TP
    tp_info = find_best_swing_tp(ohlcv, end_idx, entry_price, final_sl)
    
    if tp_info is not None:
        final_tp = tp_info['tp_price']
        tp_pct = tp_info['tp_pct']
        actual_rr = tp_info['rr']
        tp_type = 'swing'
    else:
        final_tp = fixed_tp
        tp_pct = TP_FIXED
        sl_pct_for_rr = sl_pct_actual if sl_pct_actual > 0 else 0.3
        actual_rr = TP_FIXED / sl_pct_for_rr
        tp_type = 'fixed'
    
    return {
        'sl': round(final_sl, 2), 'tp': round(final_tp, 2),
        'sl_pct': round(sl_pct_actual, 2),
        'tp_pct': round((final_tp - entry_price) / entry_price * 100, 2),
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
    
    # Volume
    if sig_idx < len(ohlcv) - 1 and sig_idx > 30:
        bar_vol = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
        avg_vol = sum(ohlcv[i].get('v', ohlcv[i].get('vol', 0))
                       for i in range(max(0, sig_idx-30), sig_idx)) / 30
        if bar_vol < avg_vol * MIN_VOL_RATIO: return None
    
    sig_type_check = sig.get('type', sig_type)
    
    # FVG bullish candle + gap
    if 'FVG' in sig_type_check and sig_idx > 0 and sig_idx < len(ohlcv):
        bar = ohlcv[sig_idx]
        if bar['c'] <= bar['o']: return None
        upper = sig.get('upper', 0); lower = sig.get('lower', 0)
        if upper > 0 and lower > 0:
            gap_pct = (upper - lower) / lower * 100
            if gap_pct < MIN_FVG_GAP: return None
    
    if len(sigs_before) < 8: return None
    
    # Trend
    trend_dir, _ = short_trend(ohlcv, end_idx)
    if trend_dir == 'down': return None
    
    # Weekly
    weekly = synthesize_weekly(ohlcv[:end_idx+1])
    if len(weekly) >= 3:
        wt = weekly_trend(weekly, lookback=min(5, len(weekly)))
        if wt == 'down': return None
    
    signal_type = 'FVG' if 'FVG' in sig_type_check else 'OB'
    effective_min_resonance = OB_MIN_RESONANCE if signal_type == 'OB' else SCOUT_MIN_RESONANCE
    
    window = ohlcv[:end_idx + 1]
    tf_sequences = {'daily': seq_result}
    resonance = evaluate_full_resonance_v11(
        all_signals=sigs_before, tf_sequences=tf_sequences, ohlcv=window,
    )
    
    if resonance.total < effective_min_resonance: return None
    
    return {
        'seq_result': seq_result, 'resonance': resonance,
        'seq_name': seq_name, 'is_scout': is_scout,
        'n_sigs': len(sigs_before), 'seq_dir': seq_dir,
        'best_seq': best_seq, 'entry_idx': sig_idx,
        'signal_type': signal_type,
    }


def simulate_trades(ohlcv, all_signals, params):
    n = len(ohlcv)
    roll_end = n - ROLL_END_OFFSET
    trades = []
    entered_bar = -999
    trade_id = 0
    
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
        
        # V14: 摆动SL/TP + OB过滤
        swing_params = calc_swing_sltp_v14(ohlcv, i, entry_price, signal_type)
        if swing_params is None: continue  # OB无摆动SL -> 跳过
        
        sl_price = swing_params['sl']
        tp_price = swing_params['tp']
        
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
            'resonance_grade': resonance.grade(),
            'confidence': decision['confidence'],
            'hold_bars': exit_idx - i,
            'sl_type': swing_params['sl_type'],
            'tp_type': swing_params['tp_type'],
            'sl_pct': swing_params['sl_pct'],
            'tp_pct': swing_params['tp_pct'],
            'signal_type': signal_type,
            'sl_dist': swing_params['sl_dist'],
        })
        trade_id += 1
        entered_bar = i
    
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
            'avg_pnl': round(avg_pnl, 2),
            'total_pnl': round(sum(t['pnl_pct'] for t in trades), 2),
            'swing_sl_pct': round(swing_sl / len(trades) * 100, 1),
        },
        'n_signals': len(all_signals), 'phase': phase,
        'elapsed': round(time.time() - t0, 1),
    }


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print(f"V14 — Extreme Swing Coverage (lookback=50) + Best Swing Selection")
    print(f"  {min(MAX_STOCKS, len(symbols))}/{len(symbols)} stocks")
    print(f"  Swing lookback: {SWING_LOOKBACK} bars | OB filtered at fixed")
    print(f"  No more 'nearest-only' — pick BEST swing SL near 0.4%")
    print(f"{'='*80}")
    
    all_trades, stock_results = [], []
    t_start = time.time()
    
    for idx, sym in enumerate(symbols[:MAX_STOCKS]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv: continue
        result = backtest_stock(ohlcv, sym)
        trades = result.get('trades', [])
        perf = result.get('perf', {})
        
        if trades:
            all_trades.extend(trades)
            stock_results.append({
                'symbol': sym, **perf,
                'n_signals': result.get('n_signals', 0),
                'phase': result.get('phase', '?'),
            })
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} "
                  f"trades={perf['n_trades']:2d} WR={perf['win_rate']:.0f}% "
                  f"RR={perf['avg_rr']:.1f}x PF={perf['profit_factor']:.1f} "
                  f"P&L={perf['avg_pnl']:+.2f}% swingSL={perf.get('swing_sl_pct',0):.0f}% | "
                  f"{result.get('elapsed',0):.1f}s")
        else:
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} "
                  f"NO-TRADE sigs={result.get('n_signals',0)} phase={result.get('phase','?')}")
        
        if (idx + 1) % 30 == 0: time.sleep(0.3)
    
    total_time = time.time() - t_start
    print(f"\n{'='*80}")
    print(f"V14 SUMMARY — {len(stock_results)} tradable out of {MAX_STOCKS} | {total_time:.1f}s")
    print(f"{'='*80}")
    
    if all_trades:
        n = len(all_trades)
        wins = sum(1 for t in all_trades if t['won'])
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
        
        print(f"\n  Trades: {n} | WR: {wr:.1f}% | Avg RR: {avg_rr:.2f}x | "
              f"PF: {pf:.2f} | Avg P&L: {avg_pnl:+.2f}%")
        print(f"  Avg SL: {avg_sl:.2f}% | Avg TP: {avg_tp:.2f}%")
        print(f"  Swing SL: {len(sw)}/{n} ({len(sw)/n*100:.0f}%) | "
              f"Swing WR: {sw_wr:.1f}% | Fixed WR: {fx_wr:.1f}%")
        print(f"  WR>=60%: {sum(1 for s in stock_results if s['win_rate']>=60)} | "
              f"WR>=70%: {sum(1 for s in stock_results if s['win_rate']>=70)} | "
              f"WR>=80%: {sum(1 for s in stock_results if s['win_rate']>=80)}")
        
        fvg_trades = [t for t in all_trades if t.get('signal_type') == 'FVG']
        ob_trades = [t for t in all_trades if t.get('signal_type') == 'OB']
        fvg_wr = sum(1 for t in fvg_trades if t['won'])/len(fvg_trades)*100 if fvg_trades else 0
        ob_wr = sum(1 for t in ob_trades if t['won'])/len(ob_trades)*100 if ob_trades else 0
        print(f"\n  FVG: {len(fvg_trades)} WR={fvg_wr:.1f}% | OB: {len(ob_trades)} WR={ob_wr:.1f}%")
        
        # Swing SL distance analysis
        if sw:
            print(f"\n  Swing SL Distance:")
            for d_range in [(0,5),(5,10),(10,20),(20,35),(35,51)]:
                subset = [t for t in sw if d_range[0] <= t.get('sl_dist',999) < d_range[1]]
                if subset:
                    swd = sum(1 for t in subset if t['won'])/len(subset)*100
                    print(f"    dist={d_range[0]}-{d_range[1]}: {len(subset):3d} trades | WR={swd:.0f}%")
        
        print(f"\n  TOP 10 by WR:")
        for s in sorted(stock_results, key=lambda x: x['win_rate'], reverse=True)[:10]:
            print(f"    {s['symbol']:12s} WR={s['win_rate']:.0f}% RR={s['avg_rr']:.1f}x "
                  f"trades={s['n_trades']} swingSL={s.get('swing_sl_pct',0):.0f}%")
    
    outpath = OUTPUT_DIR / 'backtest_v14.json'
    out = {
        'timestamp': datetime.now().isoformat(),
        'config': {
            'version': 'V14',
            'max_stocks': MAX_STOCKS,
            'swing_lookback': SWING_LOOKBACK,
            'sl_cap': SL_CAP, 'sl_fixed': SL_FIXED, 'tp_fixed': TP_FIXED,
            'swing_tp_min_rr': SWING_TP_MIN_RR,
        },
        'summary': {
            'total_stocks': MAX_STOCKS, 'tradable': len(stock_results),
            'total_trades': len(all_trades),
            'win_rate': round(wr, 1) if all_trades else 0,
            'avg_rr': round(avg_rr, 2) if all_trades else 0,
            'profit_factor': round(pf, 2) if all_trades else 0,
            'avg_pnl': round(avg_pnl, 2) if all_trades else 0,
        },
        'stocks': stock_results, 'all_trades': all_trades,
    }
    outpath.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print(f"\n  Saved: {outpath}")


if __name__ == '__main__':
    main()
