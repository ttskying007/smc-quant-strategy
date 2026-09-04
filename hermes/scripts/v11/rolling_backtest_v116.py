#!/usr/bin/env python3
"""
V11.6 — Scout-only + 摆动点动态SL/TP + 信号质量修复
======================================================
核心突破: 不再用固定SL=0.3%/0.5%, 而是基于摆动点动态设置

核心改进:
1. Scout-only (FVG/OB单信号) — 已验证WR最高
2. 摆动点动态SL — 入场前最近摆动低点为SL(自然支撑)
3. 摆动点动态TP — 入场前最近摆动高点为TP(自然阻力)
4. 摆动点紧缩 — 距离>15根K线则退回固定SL/TP
5. 信号质量修复(first_signal字段)
6. FVG优先入场
7. 周线趋势过滤

预期: WR~75-80%, RR~5-8x (SL变宽降低RR但提高WR)
"""
import json, sys, time, math, logging
from pathlib import Path
from collections import Counter
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

MAX_STOCKS = 200
MIN_BARS = 120
ROLL_START = 80
ROLL_END_OFFSET = 10
MAX_HOLD = 60
COOLDOWN = 15
SCOUT_MIN_RESONANCE = 0.65
SWING_MAX_DISTANCE = 15  # 摆动点最远距离(超过退回固定)
SL_FIXED = 0.3           # 回退固定SL(0.3% V14最优)
TP_FIXED = 5.0           # 回退固定TP


def load_ohlcv(symbol):
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


def short_trend(ohlcv, idx, lookback=10):
    if idx < lookback:
        return 'neutral', 0.0
    segment = ohlcv[idx-lookback:idx+1]
    start, end = segment[0]['c'], segment[-1]['c']
    change = (end - start) / start * 100
    ema = sum(ohlcv[i]['c'] for i in range(idx-min(5,idx), idx+1)) / min(6, idx+1)
    ema_dist = (ohlcv[idx]['c'] - ema) / ema * 100
    if change > 0.8 and ema_dist > 0:
        return 'up', change
    elif change < -0.8 and ema_dist < 0:
        return 'down', abs(change)
    return 'neutral', 0


def find_nearest_swing_low(ohlcv, end_idx, lookback=15):
    """找入场前最近的摆动低点(SL用)"""
    if end_idx < 3:
        return None, 0
    start = max(0, end_idx - lookback)
    for i in range(end_idx - 1, start - 1, -1):
        bar = ohlcv[i]
        left = ohlcv[i-1]['l'] if i > start else 9999
        right = ohlcv[i+1]['l'] if i < end_idx - 1 else 9999
        if bar['l'] < left and bar['l'] < right:
            dist = end_idx - i
            return i, bar['l']
    # 找不到摆动低点, 用最低价
    min_bar = min(ohlcv[start:end_idx], key=lambda b: b['l'])
    min_idx = ohlcv.index(min_bar)
    return min_idx, min_bar['l']


def find_nearest_swing_high(ohlcv, end_idx, lookback=15):
    """找入场前最近的摆动高点(TP用)"""
    if end_idx < 3:
        return None, 0
    start = max(0, end_idx - lookback)
    for i in range(end_idx - 1, start - 1, -1):
        bar = ohlcv[i]
        left = ohlcv[i-1]['h'] if i > start else 0
        right = ohlcv[i+1]['h'] if i < end_idx - 1 else 0
        if bar['h'] > left and bar['h'] > right:
            dist = end_idx - i
            return i, bar['h']
    # 找不到摆动高点
    max_bar = max(ohlcv[start:end_idx], key=lambda b: b['h'])
    max_idx = ohlcv.index(max_bar)
    return max_idx, max_bar['h']


def calc_swing_sltp(ohlcv, end_idx, entry_price):
    """基于摆动点计算SL和TP"""
    # 找摆动低点(SL)
    sl_idx, sl_price = find_nearest_swing_low(ohlcv, end_idx, lookback=SWING_MAX_DISTANCE)
    sl_dist = end_idx - sl_idx if sl_idx is not None else 999
    
    # 找摆动高点(TP)
    tp_idx, tp_price = find_nearest_swing_high(ohlcv, end_idx, lookback=SWING_MAX_DISTANCE)
    tp_dist = end_idx - tp_idx if tp_idx is not None else 999
    
    # 计算固定SL/TP作为保底
    fixed_sl = entry_price * (1 - SL_FIXED / 100)
    fixed_tp = entry_price * (1 + TP_FIXED / 100)
    
    use_swing = False
    
    # 摆动点SL: 距离合适且价格合理(不破入场价)
    if sl_idx is not None and sl_dist <= SWING_MAX_DISTANCE and sl_dist >= 2:
        swing_sl = min(sl_price, entry_price * 0.995)  # 最多比入场低0.5%
        sl_pct = (entry_price - swing_sl) / entry_price * 100
        if 0.15 <= sl_pct <= 3.0:  # SL距离0.15%-3%
            use_swing = True
            final_sl = swing_sl
        else:
            final_sl = fixed_sl
    else:
        final_sl = fixed_sl
    
    # 摆动点TP: 距离合适且价格合理
    if tp_idx is not None and tp_dist <= SWING_MAX_DISTANCE and tp_dist >= 2:
        swing_tp = max(tp_price, entry_price * 1.005)
        if swing_tp > final_sl:
            tp_pct = (swing_tp - entry_price) / entry_price * 100
            if 1.0 <= tp_pct <= 20.0:
                use_swing = True
                final_tp = swing_tp
            else:
                final_tp = fixed_tp
        else:
            final_tp = fixed_tp
    else:
        final_tp = fixed_tp
    
    # 计算实际RR
    swing_rr = (final_tp - entry_price) / (entry_price - final_sl) if entry_price > final_sl else TP_FIXED / SL_FIXED
    
    return {
        'sl': round(final_sl, 2),
        'tp': round(final_tp, 2),
        'sl_pct': round((entry_price - final_sl) / entry_price * 100, 2),
        'tp_pct': round((final_tp - entry_price) / entry_price * 100, 2),
        'rr': round(swing_rr, 2),
        'use_swing': use_swing,
        'sl_dist': sl_dist if sl_idx else 0,
        'tp_dist': tp_dist if tp_idx else 0,
    }


def get_entry_signal_info(seq_result):
    entry_sig = seq_result.get('entry_signal', {})
    fvg_entry = seq_result.get('fvg_entry')
    if fvg_entry and fvg_entry.get('idx') is not None:
        return fvg_entry.get('idx', 0), fvg_entry.get('type', ''), fvg_entry
    return entry_sig.get('idx', 0), entry_sig.get('type', ''), entry_sig


def analyze_at_point(ohlcv, all_signals, end_idx, params):
    sigs_before = [s for s in all_signals if s.get('idx', 0) <= end_idx]
    if len(sigs_before) < 3:
        return None
    
    seq_result = analyze_sequence_v11(sigs_before, params=params)
    best_seq = seq_result.get('best_sequence')
    if not best_seq:
        return None
    
    seq_name = best_seq.get('name', '')
    is_scout = 'SCOUT' in seq_name
    seq_dir = 'bull' if 'LONG' in seq_name else 'bear'
    
    # Bull-only
    if seq_dir != 'bull':
        return None
    
    # Scout-only
    if not is_scout:
        return None
    
    # 信号质量检查 (修复版)
    sig_idx, sig_type, sig = get_entry_signal_info(seq_result)
    if sig_idx == 0 and not sig_type:
        sig_idx = end_idx
    
    # 成交量确认
    if sig_idx < len(ohlcv) - 1 and sig_idx > 30:
        bar_vol = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
        avg_vol = sum(ohlcv[i].get('v', ohlcv[i].get('vol', 0))
                       for i in range(max(0, sig_idx-30), sig_idx)) / 30
        if bar_vol < avg_vol * 0.8:
            return None
    
    # FVG收阳确认
    sig_type_check = sig.get('type', sig_type)
    if 'FVG' in sig_type_check and sig_idx > 0 and sig_idx < len(ohlcv):
        bar = ohlcv[sig_idx]
        if bar['c'] <= bar['o']:
            return None
    
    # FVG gap size
    if 'FVG' in sig_type_check:
        upper = sig.get('upper', 0)
        lower = sig.get('lower', 0)
        if upper > 0 and lower > 0:
            gap_pct = (upper - lower) / lower * 100
            if gap_pct < 0.3:
                return None
    
    # 日线趋势检查
    trend_dir, trend_str = short_trend(ohlcv, end_idx)
    if trend_dir != 'neutral' and trend_dir != 'up':
        return None
    if len(sigs_before) < 10:
        return None
    
    # 周线趋势过滤
    weekly = synthesize_weekly(ohlcv[:end_idx+1])
    if len(weekly) >= 3:
        wt = weekly_trend(weekly, lookback=min(5, len(weekly)))
        if wt == 'down':
            return None
    
    # 共振计算
    window = ohlcv[:end_idx + 1]
    tf_sequences = {'daily': seq_result}
    resonance = evaluate_full_resonance_v11(
        all_signals=sigs_before, tf_sequences=tf_sequences, ohlcv=window,
    )
    
    return {
        'seq_result': seq_result, 'resonance': resonance,
        'seq_name': seq_name, 'is_scout': is_scout,
        'n_sigs': len(sigs_before), 'seq_dir': seq_dir,
        'best_seq': best_seq,
        'sig_idx': sig_idx,
    }


def simulate_trades(ohlcv, all_signals, params):
    n = len(ohlcv)
    roll_end = n - ROLL_END_OFFSET
    trades = []
    entered_bar = -999
    
    for i in range(ROLL_START, roll_end):
        if i - entered_bar < COOLDOWN:
            continue
        
        entry_info = analyze_at_point(ohlcv, all_signals, i, params)
        if entry_info is None:
            continue
        
        seq_result = entry_info['seq_result']
        resonance = entry_info['resonance']
        is_scout = entry_info['is_scout']
        tf_sequences = {'daily': seq_result}
        best_seq = entry_info['best_seq']
        
        decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
        if decision['action'] != 'enter':
            continue
        if is_scout and resonance.total < SCOUT_MIN_RESONANCE:
            continue
        
        entry_price = decision.get('entry_price')
        direction = 'bull'
        
        if not entry_price:
            continue
        
        # [V11.6] 摆动点动态SL/TP
        swing_params = calc_swing_sltp(ohlcv, i, entry_price)
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
            won = exit_price > ohlcv[i]['c']
        
        pnl_pct = (exit_price - entry_price) / entry_price * 100
        actual_rr = abs(exit_price - entry_price) / abs(entry_price - sl_price + 0.001)
        
        trades.append({
            'entry_idx': i, 'exit_idx': exit_idx, 'direction': direction,
            'entry_price': round(entry_price, 2), 'exit_price': round(exit_price, 2),
            'sl': round(sl_price, 2), 'tp': round(tp_price, 2),
            'pnl_pct': round(pnl_pct, 2), 'won': won, 'rr': round(actual_rr, 2),
            'seq_name': best_seq.get('name', 'Scout'),
            'resonance_grade': resonance.grade(),
            'confidence': decision['confidence'],
            'hold_bars': exit_idx - i,
            'use_swing_sltp': swing_params['use_swing'],
            'sl_pct': swing_params['sl_pct'],
            'tp_pct': swing_params['tp_pct'],
        })
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
    
    swing_count = sum(1 for t in trades if t.get('use_swing_sltp', False))
    
    return {
        'trades': trades,
        'perf': {
            'n_trades': len(trades), 'wins': wins, 'losses': len(trades) - wins,
            'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
            'profit_factor': round(pf, 2) if pf < 999 else 999,
            'avg_pnl': round(avg_pnl, 2), 'total_pnl': round(sum(t['pnl_pct'] for t in trades), 2),
            'swing_pct': round(swing_count / len(trades) * 100, 1) if trades else 0,
        },
        'n_signals': len(all_signals), 'phase': phase,
        'elapsed': round(time.time() - t0, 1),
    }


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print(f"V11.6 回测 -- Scout-only + 摆动点动态SL/TP")
    print(f"  {min(MAX_STOCKS, len(symbols))}/{len(symbols)} stocks")
    print(f"  摆动点SL/TP(自然支撑/阻力) | 回退SL={SL_FIXED}%/TP={TP_FIXED}%")
    print(f"  周线趋势过滤 | 信号质量过滤 | FVG优先入场")
    print(f"{'='*80}")
    
    all_trades, stock_results = [], []
    t_start = time.time()
    
    for idx, sym in enumerate(symbols[:MAX_STOCKS]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            continue
        
        result = backtest_stock(ohlcv, sym)
        trades = result.get('trades', [])
        perf = result.get('perf', {})
        
        if trades:
            all_trades.extend(trades)
            stock_results.append({
                'symbol': sym,
                **perf, 'n_signals': result.get('n_signals', 0),
                'phase': result.get('phase', '?'),
            })
            swing_pct = perf.get('swing_pct', 0)
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} "
                  f"trades={perf['n_trades']:2d} WR={perf['win_rate']:.0f}% "
                  f"RR={perf['avg_rr']:.1f}x PF={perf['profit_factor']:.1f} "
                  f"P&L={perf['avg_pnl']:+.2f}% swing={swing_pct:.0f}% | "
                  f"{result.get('elapsed',0):.1f}s")
        else:
            sigs = result.get('n_signals', 0)
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} "
                  f"NO-TRADE sigs={sigs} phase={result.get('phase','?')}")
        
        if (idx + 1) % 30 == 0:
            time.sleep(0.3)
    
    total_time = time.time() - t_start
    print(f"\n{'='*80}")
    print(f"V11.6 SUMMARY — {len(stock_results)} tradable out of {MAX_STOCKS}")
    print(f"  Time: {total_time:.1f}s")
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
        
        swing_count = sum(1 for t in all_trades if t.get('use_swing_sltp', False))
        avg_sl_pct = sum(t.get('sl_pct', 0) for t in all_trades) / n
        avg_tp_pct = sum(t.get('tp_pct', 0) for t in all_trades) / n
        
        print(f"\n  Trades: {n} | WR: {wr:.1f}% | Avg RR: {avg_rr:.2f}x | "
              f"PF: {pf:.2f} | Avg P&L: {avg_pnl:+.2f}%")
        print(f"  Swing SL/TP: {swing_count}/{n} ({swing_count/n*100:.0f}%) | "
              f"Avg SL: {avg_sl_pct:.2f}% | Avg TP: {avg_tp_pct:.2f}%")
        print(f"  WR>=60%: {sum(1 for s in stock_results if s['win_rate']>=60)} stocks")
        print(f"  WR>=70%: {sum(1 for s in stock_results if s['win_rate']>=70)} stocks")
        print(f"  WR>=80%: {sum(1 for s in stock_results if s['win_rate']>=80)} stocks")
        
        seq_cnt = Counter(t.get('seq_name','?') for t in all_trades)
        print(f"  Seq dist: {dict(seq_cnt.most_common(5))}")
        
        hold_avg = sum(t['hold_bars'] for t in all_trades) / n
        print(f"  Avg hold bars: {hold_avg:.1f}")
        
        # WR by swing vs fixed
        swing_wr = sum(1 for t in all_trades if t.get('use_swing_sltp') and t['won']) / max(1, swing_count) * 100
        fixed_count = n - swing_count
        fixed_wr = sum(1 for t in all_trades if not t.get('use_swing_sltp') and t['won']) / max(1, fixed_count) * 100
        print(f"  Swing WR: {swing_wr:.1f}% ({swing_count}) | Fixed WR: {fixed_wr:.1f}% ({fixed_count})")
        
        print(f"\n  TOP 10 by WR:")
        for s in sorted(stock_results, key=lambda x: x['win_rate'], reverse=True)[:10]:
            print(f"    {s['symbol']:12s} WR={s['win_rate']:.0f}% RR={s['avg_rr']:.1f}x "
                  f"PF={s['profit_factor']:.1f} trades={s['n_trades']} swing={s.get('swing_pct',0):.0f}%")
    
    outpath = OUTPUT_DIR / 'backtest_v11_v116.json'
    out = {
        'timestamp': datetime.now().isoformat(),
        'config': {'version': 'V11.6', 'max_stocks': MAX_STOCKS,
                   'swing_max_dist': SWING_MAX_DISTANCE,
                   'sl_fallback': SL_FIXED, 'tp_fallback': TP_FIXED},
        'summary': {
            'total_stocks': MAX_STOCKS, 'tradable': len(stock_results),
            'total_trades': len(all_trades),
            'win_rate': round(wr, 1) if all_trades else 0,
            'avg_rr': round(avg_rr, 2) if all_trades else 0,
            'profit_factor': round(pf, 2) if all_trades else 0,
            'avg_pnl': round(avg_pnl, 2) if all_trades else 0,
            'swing_pct': round(swing_count/n*100, 1) if all_trades else 0,
        },
        'stocks': stock_results, 'all_trades': all_trades,
    }
    outpath.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print(f"\n  Saved: {outpath}")


if __name__ == '__main__':
    main()
