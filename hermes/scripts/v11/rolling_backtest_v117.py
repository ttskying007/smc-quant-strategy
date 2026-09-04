#!/usr/bin/env python3
"""
V11.7 — Scout-only + 摆动点约束SL/TP (SL 0.3-0.5%黄金区间)
==============================================================
核心改进 (基于V11.6突破性发现):

V11.6发现: 摆动SL在0.3-0.5%区间WR=97% (165笔)
V11.7策略:
1. 摆动点SL必须在0.3%-0.5%之间 -> 入场+跳过极端情况
2. 摆动TP在1.0%-15%之间
3. 无摆动点时退回固定SL=0.3%/TP=5.0%
4. 周线趋势过滤
5. 信号质量修复

预期: WR~80%, 覆盖率略降但质量大幅提升
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
SWING_LOOKBACK = 20
SL_MIN = 0.3  # 摆动SL最小(低于此用固定)
SL_MAX = 0.5  # 摆动SL最大(高于此用固定)
SL_FIXED = 0.3
TP_FIXED = 5.0


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


def find_best_swing_sl(ohlcv, end_idx, entry_price, lookback=SWING_LOOKBACK):
    """找距离最接近0.3-0.5%的摆动低点"""
    if end_idx < 3:
        return None
    start = max(0, end_idx - lookback)
    
    candidates = []
    for i in range(end_idx - 1, start, -1):
        bar = ohlcv[i]
        left = ohlcv[i-1]['l'] if i > start else 9999
        right = ohlcv[i+1]['l'] if i < end_idx - 1 else 9999
        if bar['l'] < left and bar['l'] < right:
            sl_pct = (entry_price - bar['l']) / entry_price * 100
            if 0.25 <= sl_pct <= 0.6:  # 宽松筛选
                candidates.append({
                    'idx': i, 'price': bar['l'],
                    'sl_pct': sl_pct,
                    'dist_from_optimal': abs(sl_pct - 0.4),  # 越接近0.4%越好
                })
    
    if not candidates:
        return None
    # 选最接近0.4%的
    candidates.sort(key=lambda x: x['dist_from_optimal'])
    return candidates[0]


def find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price, lookback=SWING_LOOKBACK):
    """找最近摆动高点作为TP，确保RR>=2.0x"""
    if end_idx < 3:
        return None
    start = max(0, end_idx - lookback)
    
    target_rr = 8.0  # 目标RR
    
    candidates = []
    for i in range(end_idx - 1, start, -1):
        bar = ohlcv[i]
        left = ohlcv[i-1]['h'] if i > start else 0
        right = ohlcv[i+1]['h'] if i < end_idx - 1 else 0
        if bar['h'] > left and bar['h'] > right:
            tp_pct = (bar['h'] - entry_price) / entry_price * 100
            sl_dist = (entry_price - sl_price) / entry_price * 100
            rr = tp_pct / sl_dist if sl_dist > 0 else 0
            if rr >= 2.0 and tp_pct <= 20.0:  # RR>=2且TP不大于20%
                candidates.append({
                    'idx': i, 'price': bar['h'],
                    'tp_pct': tp_pct, 'rr': rr,
                    'dist_from_target': abs(rr - target_rr) if rr > 0 else 999,
                })
    
    if not candidates:
        return None
    candidates.sort(key=lambda x: x['dist_from_target'])
    return candidates[0]


def calc_swing_sltp_v2(ohlcv, end_idx, entry_price):
    """V11.7 摆动点SL/TP: 黄金约束"""
    # 固定保底
    fixed_sl = entry_price * (1 - SL_FIXED / 100)
    fixed_tp = entry_price * (1 + TP_FIXED / 100)
    
    # 找摆动SL
    sl_info = find_best_swing_sl(ohlcv, end_idx, entry_price)
    
    if sl_info is None or not (SL_MIN <= sl_info['sl_pct'] <= SL_MAX):
        # 退回固定
        return {
            'sl': round(fixed_sl, 2), 'tp': round(fixed_tp, 2),
            'sl_pct': SL_FIXED, 'tp_pct': TP_FIXED,
            'rr': TP_FIXED / SL_FIXED if SL_FIXED > 0 else 10,
            'use_swing': False,
        }
    
    sl_price = sl_info['price']
    sl_pct = sl_info['sl_pct']
    
    # 找摆动TP
    tp_info = find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price)
    
    if tp_info:
        tp_price = tp_info['price']
        tp_pct = tp_info['tp_pct']
        swing_rr = tp_info['rr']
    else:
        # 用固定TP=5.0%
        tp_price = entry_price * (1 + TP_FIXED / 100)
        tp_pct = TP_FIXED
        swing_rr = tp_pct / sl_pct
    
    return {
        'sl': round(sl_price, 2), 'tp': round(tp_price, 2),
        'sl_pct': round(sl_pct, 2), 'tp_pct': round(tp_pct, 2),
        'rr': round(swing_rr, 2),
        'use_swing': True,
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
    
    if seq_dir != 'bull':
        return None
    if not is_scout:
        return None
    
    # 信号质量
    sig_idx, sig_type, sig = get_entry_signal_info(seq_result)
    if sig_idx == 0 and not sig_type:
        sig_idx = end_idx
    
    if sig_idx < len(ohlcv) - 1 and sig_idx > 30:
        bar_vol = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
        avg_vol = sum(ohlcv[i].get('v', ohlcv[i].get('vol', 0))
                       for i in range(max(0, sig_idx-30), sig_idx)) / 30
        if bar_vol < avg_vol * 0.8:
            return None
    
    sig_type_check = sig.get('type', sig_type)
    if 'FVG' in sig_type_check and sig_idx > 0 and sig_idx < len(ohlcv):
        bar = ohlcv[sig_idx]
        if bar['c'] <= bar['o']:
            return None
    
    if 'FVG' in sig_type_check:
        upper = sig.get('upper', 0)
        lower = sig.get('lower', 0)
        if upper > 0 and lower > 0:
            gap_pct = (upper - lower) / lower * 100
            if gap_pct < 0.3:
                return None
    
    trend_dir, trend_str = short_trend(ohlcv, end_idx)
    if trend_dir != 'neutral' and trend_dir != 'up':
        return None
    if len(sigs_before) < 10:
        return None
    
    # 周线
    weekly = synthesize_weekly(ohlcv[:end_idx+1])
    if len(weekly) >= 3:
        wt = weekly_trend(weekly, lookback=min(5, len(weekly)))
        if wt == 'down':
            return None
    
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
        if not entry_price:
            continue
        
        # V11.7 摆动点SL/TP (黄金约束)
        swing_params = calc_swing_sltp_v2(ohlcv, i, entry_price)
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
            'entry_idx': i, 'exit_idx': exit_idx,
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
    print(f"V11.7 — Scout-only + 摆动点黄金约束SL/TP (0.3-0.5%)")
    print(f"  {min(MAX_STOCKS, len(symbols))}/{len(symbols)} stocks")
    print(f"  摆动SL 0.3-0.5% | 摆动TP 2.0-20x RR | 回落SL={SL_FIXED}%/TP={TP_FIXED}%")
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
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} "
                  f"trades={perf['n_trades']:2d} WR={perf['win_rate']:.0f}% "
                  f"RR={perf['avg_rr']:.1f}x PF={perf['profit_factor']:.1f} "
                  f"P&L={perf['avg_pnl']:+.2f}% swing={perf.get('swing_pct',0):.0f}% | "
                  f"{result.get('elapsed',0):.1f}s")
        else:
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} "
                  f"NO-TRADE sigs={result.get('n_signals',0)} phase={result.get('phase','?')}")
        
        if (idx + 1) % 30 == 0:
            time.sleep(0.3)
    
    total_time = time.time() - t_start
    print(f"\n{'='*80}")
    print(f"V11.7 SUMMARY — {len(stock_results)} tradable out of {MAX_STOCKS} | {total_time:.1f}s")
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
        
        sw_grp = [t for t in all_trades if t.get('use_swing_sltp')]
        fx_grp = [t for t in all_trades if not t.get('use_swing_sltp')]
        sw_wr = sum(1 for t in sw_grp if t['won'])/len(sw_grp)*100 if sw_grp else 0
        fx_wr = sum(1 for t in fx_grp if t['won'])/len(fx_grp)*100 if fx_grp else 0
        
        avg_sl = sum(t.get('sl_pct',0) for t in all_trades)/n
        avg_tp = sum(t.get('tp_pct',0) for t in all_trades)/n
        
        print(f"\n  Trades: {n} | WR: {wr:.1f}% | Avg RR: {avg_rr:.2f}x | "
              f"PF: {pf:.2f} | Avg P&L: {avg_pnl:+.2f}%")
        print(f"  Swing SL/TP: {swing_count}/{n} ({swing_count/n*100:.0f}%) | "
              f"Avg SL: {avg_sl:.2f}% | Avg TP: {avg_tp:.2f}%")
        print(f"  Swing WR: {sw_wr:.1f}% ({len(sw_grp)}) | Fixed WR: {fx_wr:.1f}% ({len(fx_grp)})")
        print(f"  WR>=60%: {sum(1 for s in stock_results if s['win_rate']>=60)}")
        print(f"  WR>=70%: {sum(1 for s in stock_results if s['win_rate']>=70)}")
        print(f"  WR>=80%: {sum(1 for s in stock_results if s['win_rate']>=80)}")
        
        seq_cnt = Counter(t.get('seq_name','?') for t in all_trades)
        print(f"  Seq: {dict(seq_cnt.most_common(3))}")
        print(f"  Avg hold: {sum(t['hold_bars'] for t in all_trades)/n:.1f} bars")
        
        print(f"\n  TOP 10 by WR:")
        for s in sorted(stock_results, key=lambda x: x['win_rate'], reverse=True)[:10]:
            print(f"    {s['symbol']:12s} WR={s['win_rate']:.0f}% RR={s['avg_rr']:.1f}x "
                  f"PF={s['profit_factor']:.1f} trades={s['n_trades']} swing={s.get('swing_pct',0):.0f}%")
    
    outpath = OUTPUT_DIR / 'backtest_v11_v117.json'
    out = {
        'timestamp': datetime.now().isoformat(),
        'config': {'version': 'V11.7', 'max_stocks': MAX_STOCKS,
                   'sl_min': SL_MIN, 'sl_max': SL_MAX,
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
