#!/usr/bin/env python3
"""V11.6 全量市场扫描 — Scout-only + 摆动点动态SL/TP"""
import json, sys, time, math, logging, concurrent.futures
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

MIN_BARS = 120
ROLL_START = 80
ROLL_END_OFFSET = 10
MAX_HOLD = 60
COOLDOWN = 15
SCOUT_MIN_RESONANCE = 0.65
SWING_MAX_DISTANCE = 15
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


def find_nearest_swing_low(ohlcv, end_idx, lookback=15):
    if end_idx < 3:
        return None, 0
    start = max(0, end_idx - lookback)
    for i in range(end_idx - 1, start - 1, -1):
        bar = ohlcv[i]
        left = ohlcv[i-1]['l'] if i > start else 9999
        right = ohlcv[i+1]['l'] if i < end_idx - 1 else 9999
        if bar['l'] < left and bar['l'] < right:
            return i, bar['l']
    min_bar = min(ohlcv[start:end_idx], key=lambda b: b['l'])
    min_idx = ohlcv.index(min_bar)
    return min_idx, min_bar['l']


def find_nearest_swing_high(ohlcv, end_idx, lookback=15):
    if end_idx < 3:
        return None, 0
    start = max(0, end_idx - lookback)
    for i in range(end_idx - 1, start - 1, -1):
        bar = ohlcv[i]
        left = ohlcv[i-1]['h'] if i > start else 0
        right = ohlcv[i+1]['h'] if i < end_idx - 1 else 0
        if bar['h'] > left and bar['h'] > right:
            return i, bar['h']
    max_bar = max(ohlcv[start:end_idx], key=lambda b: b['h'])
    max_idx = ohlcv.index(max_bar)
    return max_idx, max_bar['h']


def calc_swing_sltp(ohlcv, end_idx, entry_price):
    sl_idx, sl_price = find_nearest_swing_low(ohlcv, end_idx, lookback=SWING_MAX_DISTANCE)
    sl_dist = end_idx - sl_idx if sl_idx is not None else 999
    tp_idx, tp_price = find_nearest_swing_high(ohlcv, end_idx, lookback=SWING_MAX_DISTANCE)
    tp_dist = end_idx - tp_idx if tp_idx is not None else 999
    
    fixed_sl = entry_price * (1 - SL_FIXED / 100)
    fixed_tp = entry_price * (1 + TP_FIXED / 100)
    
    use_swing = False
    if sl_idx is not None and sl_dist <= SWING_MAX_DISTANCE and sl_dist >= 2:
        swing_sl = min(sl_price, entry_price * 0.995)
        sl_pct = (entry_price - swing_sl) / entry_price * 100
        if 0.15 <= sl_pct <= 3.0:
            use_swing = True
            final_sl = swing_sl
        else:
            final_sl = fixed_sl
    else:
        final_sl = fixed_sl
    
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
    
    return {
        'sl': round(final_sl, 2), 'tp': round(final_tp, 2),
        'sl_pct': round((entry_price - final_sl) / entry_price * 100, 2),
        'tp_pct': round((final_tp - entry_price) / entry_price * 100, 2),
        'rr': round((final_tp - entry_price) / (entry_price - final_sl), 2),
        'use_swing': use_swing,
    }


def get_entry_signal_info(seq_result):
    entry_sig = seq_result.get('entry_signal', {})
    fvg_entry = seq_result.get('fvg_entry')
    if fvg_entry and fvg_entry.get('idx') is not None:
        return fvg_entry.get('idx', 0), fvg_entry.get('type', ''), fvg_entry
    return entry_sig.get('idx', 0), entry_sig.get('type', ''), entry_sig


def process_stock(symbol):
    t0 = time.time()
    ohlcv = load_ohlcv(symbol)
    if not ohlcv:
        return None
    
    try:
        phase = detect_market_phase(ohlcv)
        base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
        all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')['all']
    except:
        return {'symbol': symbol, 'error': 'signal detect failed', 'elapsed': round(time.time()-t0, 1)}
    
    if not all_signals or len(all_signals) < 5:
        return {'symbol': symbol, 'trades': 0, 'n_signals': len(all_signals) if all_signals else 0, 'phase': phase, 'elapsed': round(time.time()-t0, 1)}
    
    params = {**base_params, 'sl_pct': SL_FIXED, 'tp_pct': TP_FIXED}
    n = len(ohlcv)
    roll_end = n - ROLL_END_OFFSET
    trades = []
    entered_bar = -999
    
    for i in range(ROLL_START, roll_end):
        if i - entered_bar < COOLDOWN:
            continue
        
        sigs_before = [s for s in all_signals if s.get('idx', 0) <= i]
        if len(sigs_before) < 3:
            continue
        
        try:
            seq_result = analyze_sequence_v11(sigs_before, params=params)
        except:
            continue
        
        best_seq = seq_result.get('best_sequence')
        if not best_seq:
            continue
        
        seq_name = best_seq.get('name', '')
        is_scout = 'SCOUT' in seq_name
        seq_dir = 'bull' if 'LONG' in seq_name else 'bear'
        
        if seq_dir != 'bull' or not is_scout:
            continue
        
        # 信号质量
        sig_idx, sig_type, sig = get_entry_signal_info(seq_result)
        if sig_idx == 0:
            sig_idx = i
        
        if sig_idx < n and sig_idx > 30:
            bar_vol = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
            avg_vol = sum(ohlcv[k].get('v', ohlcv[k].get('vol', 0)) for k in range(max(0, sig_idx-30), sig_idx)) / 30
            if bar_vol < avg_vol * 0.8:
                continue
        
        sig_type_check = sig.get('type', sig_type)
        if 'FVG' in sig_type_check and 0 < sig_idx < n:
            if ohlcv[sig_idx]['c'] <= ohlcv[sig_idx]['o']:
                continue
            upper = sig.get('upper', 0)
            lower = sig.get('lower', 0)
            if upper > 0 and lower > 0:
                if (upper - lower) / lower * 100 < 0.3:
                    continue
        
        trend_dir, _ = short_trend(ohlcv, i)
        if trend_dir not in ('neutral', 'up'):
            continue
        
        # 周线
        weekly = synthesize_weekly(ohlcv[:i+1])
        if len(weekly) >= 3:
            wt = weekly_trend(weekly, lookback=min(5, len(weekly)))
            if wt == 'down':
                continue
        
        try:
            window = ohlcv[:i+1]
            tf_sequences = {'daily': seq_result}
            resonance = evaluate_full_resonance_v11(all_signals=sigs_before, tf_sequences=tf_sequences, ohlcv=window)
            decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
            if decision['action'] != 'enter':
                continue
            if is_scout and resonance.total < SCOUT_MIN_RESONANCE:
                continue
            entry_price = decision.get('entry_price')
            if not entry_price:
                continue
        except:
            continue
        
        # 摆动点SL/TP
        swing_params = calc_swing_sltp(ohlcv, i, entry_price)
        sl_price = swing_params['sl']
        tp_price = swing_params['tp']
        
        exit_idx, exit_price, won = -1, None, False
        for j in range(i + 1, min(i + MAX_HOLD + 1, n)):
            bar = ohlcv[j]
            if bar['h'] >= tp_price: exit_idx, exit_price, won = j, tp_price, True; break
            if bar['l'] <= sl_price: exit_idx, exit_price, won = j, sl_price, False; break
        
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
            'seq_name': seq_name, 'hold_bars': exit_idx - i,
            'use_swing_sltp': swing_params['use_swing'],
            'sl_pct': swing_params['sl_pct'],
            'tp_pct': swing_params['tp_pct'],
        })
        entered_bar = i
    
    if len(trades) < 2:
        return {'symbol': symbol, 'trades': 0, 'n_signals': len(all_signals), 'phase': phase, 'elapsed': round(time.time()-t0, 1)}
    
    wins = sum(1 for t in trades if t['won'])
    wr = wins / len(trades) * 100
    win_pnl = sum(t['pnl_pct'] for t in trades if t['won'])
    loss_pnl = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
    pf = win_pnl / loss_pnl if loss_pnl > 0 else 99.9
    avg_pnl = sum(t['pnl_pct'] for t in trades) / len(trades)
    avg_rr = sum(t['rr'] for t in trades) / len(trades)
    swing_count = sum(1 for t in trades if t.get('use_swing_sltp', False))
    
    return {
        'symbol': symbol, 'trades': len(trades),
        'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
        'profit_factor': round(pf, 2) if pf < 999 else 999,
        'avg_pnl': round(avg_pnl, 2),
        'swing_pct': round(swing_count / len(trades) * 100, 1) if trades else 0,
        'swing_count': swing_count, 'n_signals': len(all_signals),
        'phase': phase, 'elapsed': round(time.time()-t0, 1),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--batch', type=int, default=500)
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--output', default='v116_full')
    args = parser.parse_args()
    
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    symbols = symbols[args.start:args.start + args.batch]
    
    print(f"{'='*80}")
    print(f"V11.6 全量扫描 (摆动点SL/TP) — {len(symbols)} stocks, {args.workers} workers")
    print(f"{'='*80}")
    
    t_start = time.time()
    results = []
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_stock, sym): sym for sym in symbols}
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            sym = futures[future]
            try:
                r = future.result()
                if r and r.get('trades', 0) > 0:
                    results.append(r)
                    sw = r.get('swing_pct', 0)
                    print(f"  [{i+1:3d}/{len(symbols)}] {r['symbol']:12s} "
                          f"trades={r['trades']:2d} WR={r['win_rate']:.0f}% "
                          f"RR={r['avg_rr']:.1f}x PF={r['profit_factor']:.1f} "
                          f"P&L={r['avg_pnl']:+.2f}% swing={sw:.0f}% | "
                          f"{r.get('elapsed',0):.1f}s")
                elif r:
                    print(f"  [{i+1:3d}/{len(symbols)}] {sym:12s} "
                          f"NO-TRADE sigs={r.get('n_signals',0)} phase={r.get('phase','?')}")
                else:
                    print(f"  [{i+1:3d}/{len(symbols)}] {sym:12s} CACHE MISS")
            except Exception as e:
                print(f"  [{i+1:3d}/{len(symbols)}] {sym:12s} ERROR: {e}")
    
    total_time = time.time() - t_start
    print(f"\n{'='*80}")
    print(f"V11.6 全量扫描完成: {len(results)}/{len(symbols)} tradable | {total_time:.1f}s")
    print(f"{'='*80}")
    
    if results:
        n = sum(r['trades'] for r in results)
        wr = sum(r['win_rate'] * r['trades'] for r in results) / n
        rr = sum(r['avg_rr'] * r['trades'] for r in results) / n
        wins_pnl = sum(r['avg_pnl'] for r in results if r['avg_pnl'] > 0)
        loss_pnl = abs(sum(r['avg_pnl'] for r in results if r['avg_pnl'] < 0))
        pf = wins_pnl / loss_pnl if loss_pnl > 0 else 99
        sw_total = sum(r.get('swing_count', 0) for r in results)
        
        print(f"\n  总交易: {n}")
        print(f"  平均WR: {wr:.1f}%")
        print(f"  平均RR: {rr:.2f}x")
        print(f"  PF: {pf:.1f}")
        print(f"  摆动交易: {sw_total}/{n} ({sw_total/n*100:.1f}%)")
        print(f"  WR>=80%: {sum(1 for r in results if r['win_rate']>=80)} stocks")
        print(f"  WR>=70%: {sum(1 for r in results if r['win_rate']>=70)} stocks")
        
        sl_dist = Counter(r.get('swing_pct', 0) for r in results)
        print(f"  摆动使用率分布: {dict(sl_dist.most_common(10))}")
        
        outpath = OUTPUT_DIR / f'{args.output}.json'
        out = {
            'timestamp': datetime.now().isoformat(),
            'config': {'version': 'V11.6_full', 'stocks': f'{args.start}-{args.start+len(symbols)-1}'},
            'summary': {
                'tradable': len(results), 'total_trades': n,
                'win_rate': round(wr, 1), 'avg_rr': round(rr, 2),
                'profit_factor': round(pf, 1),
                'swing_pct': round(sw_total/n*100, 1),
            },
            'stocks': results,
        }
        outpath.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        print(f"\n  保存: {outpath}")
    
    # 打印TOP 20
    if results:
        print(f"\n  TOP 20 (by WR, n>=5):")
        for r in sorted([r for r in results if r['trades'] >= 5], key=lambda x: x['win_rate'], reverse=True)[:20]:
            print(f"    {r['symbol']:12s} WR={r['win_rate']:.0f}% RR={r['avg_rr']:.1f}x "
                  f"PF={r['profit_factor']:.1f} n={r['trades']} swing={r.get('swing_pct',0):.0f}% "
                  f"phase={r.get('phase','?')}")


if __name__ == '__main__':
    main()
