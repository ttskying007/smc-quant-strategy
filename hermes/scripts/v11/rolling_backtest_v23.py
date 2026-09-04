#!/usr/bin/env python3
"""
V23 — Swing Coverage Filter + Phase-Adaptive Params
====================================================
V21: WR=77.7%, 378 losing stocks (avg Swing SL=16% vs 93% for winners)

V23创新:
  1. Skip stocks where swing SL coverage < 30% (they don't have swing structure)
  2. Per-phase adaptive SL/TP:
     Breakout: SL=0.3%, TP=3.0% (fast trend)
     Volatile: SL=0.5%, TP=5.0% (wider stop)
     Ranging: SL=0.7%, TP=3.0% (wide stop for sideways)
     Trending_up: SL=0.3%, TP=5.0% (let winners run)
  3. Per-cycle SL adjustment: ALL-UP=normal, NEUTRAL=wider

预期: WR=80-82%, 覆盖从42%→35% (更少但更高质量的股票)
"""
import json, sys, time, math
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase
from v11.weekly_trend import synthesize_weekly, weekly_trend

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v23')
OUTPUT_DIR.mkdir(exist_ok=True)

# V23: Phase-adaptive parameters
PHASE_PARAMS = {
    'breakout':      {'sl': 0.3, 'tp': 3.0},  # Strong trend, tight stops
    'volatile':      {'sl': 0.5, 'tp': 5.0},  # Noisy, wider stops
    'ranging':       {'sl': 0.7, 'tp': 3.0},  # No trend, wide stops only
    'trending_up':   {'sl': 0.3, 'tp': 5.0},  # Let winners run
    'trending_down': {'sl': 0.5, 'tp': 5.0},  # Only strong signals
}

# V23: Multicyle phase override
CYCLE_SL_MULT = {
    'ALL-UP': 1.0,          # Normal
    '2UP-1NEUTRAL': 1.0,    # Normal
    'NEUTRAL': 1.2,         # 20% wider for neutral
}

# Swing coverage threshold
MIN_SWING_COVERAGE = 30  # Skip stocks with <30% swing SL coverage

SWING_MAX_DISTANCE = 20; SWING_SL_CAP = 0.5
MIN_VOL_RATIO = 0.8; MIN_FVG_GAP = 0.3
MAX_STOCKS = 200; MIN_BARS = 120; ROLL_START = 80
ROLL_END_OFFSET = 10; MAX_HOLD = 60; COOLDOWN = 15


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
    seg = ohlcv[idx-lookback:idx+1]
    s, e = seg[0]['c'], seg[-1]['c']
    change = (e - s) / s * 100
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
        bar = ohlcv[i]; left = ohlcv[i-1] if i > start else None; right = ohlcv[i+1] if i < end_idx-1 else None
        lv = left['l'] if left else 9999; rv = right['l'] if right else 9999
        if bar['l'] < lv and bar['l'] < rv:
            swings.append((i, bar['l'], end_idx - i))
    return swings

def find_all_swing_highs(ohlcv, end_idx, lookback=50):
    if end_idx < 3: return []
    start = max(0, end_idx - lookback)
    swings = []
    for i in range(end_idx - 1, start, -1):
        bar = ohlcv[i]; left = ohlcv[i-1] if i > start else None; right = ohlcv[i+1] if i < end_idx-1 else None
        lv = left['h'] if left else 0; rv = right['h'] if right else 0
        if bar['h'] > lv and bar['h'] > rv:
            swings.append((i, bar['h'], end_idx - i))
    return swings

def find_best_swing_sl(ohlcv, end_idx, entry_price):
    swings = find_all_swing_lows(ohlcv, end_idx)
    swings = [s for s in swings if s[2] <= SWING_MAX_DISTANCE]
    if not swings: return None
    best, best_score = None, 999
    for idx, price, dist in swings:
        capped = min(price, entry_price * (1 - SWING_SL_CAP / 100))
        sl_pct = (entry_price - capped) / entry_price * 100
        if 0.15 <= sl_pct <= 0.7:
            score = abs(sl_pct - 0.4) * 0.5 + (dist / SWING_MAX_DISTANCE) * 0.5
            if best is None or score < best_score:
                best_score = score; best = {'sl_price': capped, 'sl_pct': round(sl_pct,2)}
    return best

def find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price, max_dist=SWING_MAX_DISTANCE):
    swings = find_all_swing_highs(ohlcv, end_idx)
    swings = [s for s in swings if s[2] <= max_dist]
    if not swings: return None
    best, best_score = None, 999
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


def calc_sltp_v23(ohlcv, end_idx, entry_price, signal_type='FVG', 
                  base_sl=0.3, base_tp=3.0, cycle_mult=1.0):
    """V23: Phase + Cycle adaptive SL/TP"""
    sl_val = base_sl * cycle_mult
    tp_val = base_tp
    
    fixed_sl = entry_price * (1 - sl_val / 100)
    fixed_tp = entry_price * (1 + tp_val / 100)
    
    sl_info = find_best_swing_sl(ohlcv, end_idx, entry_price)
    if sl_info is not None:
        final_sl = sl_info['sl_price']; sl_pct_actual = sl_info['sl_pct']; sl_type = 'swing'
    else:
        if 'OB' in signal_type: return None, None
        final_sl = fixed_sl; sl_pct_actual = sl_val; sl_type = 'fixed'
    
    # Swing TP if available
    sl_pct_final = (entry_price - final_sl) / entry_price * 100 if entry_price > final_sl else 0.3
    tp_info = find_best_swing_tp(ohlcv, end_idx, entry_price, final_sl)
    if tp_info is not None:
        final_tp = tp_info['tp_price']; tp_pct_actual = tp_info['tp_pct']
        actual_rr = tp_pct_actual / sl_pct_final if sl_pct_final > 0 else 10; tp_type = 'swing'
    else:
        final_tp = fixed_tp; tp_pct_actual = tp_val
        actual_rr = tp_val / sl_pct_final if sl_pct_final > 0 else 10; tp_type = 'fixed'
    
    params = {'sl': round(final_sl,2), 'tp': round(final_tp,2), 'sl_pct': round(sl_pct_actual,2),
              'tp_pct': round(tp_pct_actual,2), 'rr': round(actual_rr,2), 'sl_type': sl_type, 'tp_type': tp_type,
              'used_sl': sl_val, 'used_tp': tp_val, 'cycle_mult': cycle_mult}
    return params, sl_type


def get_entry_signal_info(seq_result):
    entry_sig = seq_result.get('entry_signal', {})
    fvg_entry = seq_result.get('fvg_entry')
    if fvg_entry and fvg_entry.get('idx') is not None:
        return fvg_entry.get('idx', 0), fvg_entry.get('type', ''), fvg_entry
    return entry_sig.get('idx', 0), entry_sig.get('type', ''), entry_sig


def analyze_at_point(ohlcv, all_signals, end_idx, params, phase='breakout'):
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
    
    # V23: Multi-cycle check
    micro = short_trend(ohlcv, end_idx, lookback=8)
    meso = short_trend(ohlcv, end_idx, lookback=20)
    macro = short_trend(ohlcv, end_idx, lookback=40)
    up_count = sum(1 for c in [micro, meso, macro] if c[0] == 'up')
    down_count = sum(1 for c in [micro, meso, macro] if c[0] == 'down')
    if down_count >= 2 or (up_count == 1 and down_count == 0):
        return None
    
    if up_count == 3: cycle_detail = 'ALL-UP'
    elif up_count >= 2: cycle_detail = '2UP-1NEUTRAL'
    else: cycle_detail = 'NEUTRAL'
    
    cycle_mult = CYCLE_SL_MULT.get(cycle_detail, 1.0)
    
    window = ohlcv[:end_idx + 1]
    tf_sequences = {'daily': seq_result}
    resonance = evaluate_full_resonance_v11(all_signals=sigs_before, tf_sequences=tf_sequences, ohlcv=window)
    
    min_res = 0.55 if up_count >= 2 else 0.65
    if signal_type == 'OB': min_res = max(min_res, 0.70)
    if resonance.total < min_res: return None
    
    return {
        'seq_result': seq_result, 'resonance': resonance,
        'seq_name': seq_name, 'is_scout': is_scout,
        'n_sigs': len(sigs_before), 'best_seq': best_seq,
        'signal_type': signal_type, 'cycle_detail': cycle_detail,
        'cycle_mult': cycle_mult,
    }


def simulate_trades_v23(ohlcv, all_signals, params, phase='breakout'):
    n = len(ohlcv); roll_end = n - ROLL_END_OFFSET
    trades = []; entered_bar = -999
    phase_params = PHASE_PARAMS.get(phase, {'sl': 0.3, 'tp': 3.0})
    base_sl, base_tp = phase_params['sl'], phase_params['tp']
    swing_count, fixed_count = 0, 0
    
    for i in range(ROLL_START, roll_end):
        if i - entered_bar < COOLDOWN: continue
        entry_info = analyze_at_point(ohlcv, all_signals, i, params, phase)
        if entry_info is None: continue
        
        seq_result = entry_info['seq_result']
        resonance = entry_info['resonance']
        tf_sequences = {'daily': seq_result}
        best_seq = entry_info['best_seq']; signal_type = entry_info['signal_type']
        cycle_detail = entry_info['cycle_detail']; cycle_mult = entry_info['cycle_mult']
        
        decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
        if decision['action'] != 'enter': continue
        entry_price = decision.get('entry_price')
        if not entry_price: continue
        
        swing_result, sl_type = calc_sltp_v23(ohlcv, i, entry_price, signal_type, base_sl, base_tp, cycle_mult)
        if swing_result is None: continue
        sl_price = swing_result['sl']; tp_price = swing_result['tp']
        
        # Track swing coverage
        if sl_type == 'swing': swing_count += 1
        else: fixed_count += 1
        
        sl_cond = lambda b: b['l'] <= sl_price
        tp_cond = lambda b: b['h'] >= tp_price
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
            'entry_idx': i, 'exit_idx': exit_idx,
            'entry_price': round(entry_price,2), 'exit_price': round(exit_price,2),
            'sl': round(sl_price,2), 'tp': round(tp_price,2),
            'pnl_pct': round(pnl_pct,2), 'won': won, 'rr': round(actual_rr,2),
            'seq_name': best_seq.get('name', 'Scout'),
            'hold_bars': exit_idx - i,
            'sl_type': sl_type, 'sl_pct': swing_result['sl_pct'],
            'signal_type': signal_type,
            'used_sl': swing_result['used_sl'], 'used_tp': swing_result['used_tp'],
            'cycle_detail': cycle_detail, 'phase': phase,
        })
        entered_bar = i
    
    # If swing coverage < threshold, mark as low-quality
    total = swing_count + fixed_count
    swing_pct = swing_count / total * 100 if total else 0
    return trades, swing_pct


def backtest_stock_v23(ohlcv, symbol):
    t0 = time.time()
    phase = detect_market_phase(ohlcv)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')['all']
    if not all_signals or len(all_signals) < 5: return None
    params = {**base_params}
    trades, swing_pct = simulate_trades_v23(ohlcv, all_signals, params, phase)
    
    # V23: SKIP if swing coverage too low — doesn't have swing structure
    if swing_pct < MIN_SWING_COVERAGE:
        return None
    
    if len(trades) < 2: return None
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
        'perf': {'n_trades': len(trades), 'wins': wins, 'losses': len(trades)-wins,
                 'win_rate': round(wr,1), 'avg_rr': round(avg_rr,2),
                 'profit_factor': round(pf,2) if pf < 999 else 999,
                 'avg_pnl': round(avg_pnl,2),
                 'swing_sl_pct': round(swing_sl/len(trades)*100,1), 'phase': phase},
        'n_signals': len(all_signals), 'elapsed': round(time.time()-t0,1),
    }


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print(f"V23 — Swing Coverage Filter + Phase-Adaptive Params")
    print(f"  Min swing coverage: {MIN_SWING_COVERAGE}% | Adaptive SL/TP per phase+cycle")
    print(f"  200 stocks test")
    print(f"{'='*80}")
    print(f"Phase params:")
    for p, v in PHASE_PARAMS.items():
        print(f"  {p:15s}: SL={v['sl']}% TP={v['tp']}%")
    print(f"Cycle mult: {dict(CYCLE_SL_MULT)}")
    
    all_trades, stock_results = [], []; t_start = time.time()
    phases_seen = Counter()
    skipped_low_swing = 0
    
    for idx, sym in enumerate(symbols[:MAX_STOCKS]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv: continue
        result = backtest_stock_v23(ohlcv, sym)
        if result:
            p = result['perf']
            phases_seen[p['phase']] += 1
            all_trades.extend(result['trades'])
            stock_results.append({'symbol': sym, **p})
        else:
            skipped_low_swing += 1
        
        if (idx+1) % 20 == 0:
            t = result['perf'] if result else {}
            wr = t.get('win_rate', 0)
            n = t.get('n_trades', 0)
            print(f"  [{idx+1:3d}/200] {sym:12s} {'t='+str(n)+' WR='+str(wr)+'%' if result else 'SKIP(no-swing)'}")
    
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
        n80 = sum(1 for s in stock_results if s['win_rate']>=80)
        n70 = sum(1 for s in stock_results if s['win_rate']>=70)
        
        print(f"\n{'='*80}")
        print(f"V23 — {len(stock_results)} tradable | {skipped_low_swing} skipped (low swing) | {total_time:.0f}s")
        print(f"{'='*80}")
        print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {avg_rr:.2f}x | PF: {pf:.2f} | P&L: {avg_pnl:+.2f}%")
        print(f"  Swing SL: {len(sw)}/{n} ({len(sw)/n*100:.0f}%) | WR={sw_wr:.1f}%")
        print(f"  WR>=70%: {n70} | WR>=80%: {n80}")
        print(f"  Phases: {dict(phases_seen.most_common())}")
        
        # Per-phase performance
        print(f"\n  Per-Phase:")
        for phase, cnt in phases_seen.most_common():
            subset = [s for s in stock_results if s.get('phase','')==phase]
            aw = sum(s['win_rate'] for s in subset)/len(subset)
            ar = sum(s['avg_rr'] for s in subset)/len(subset)
            sw_subset = sum(s.get('swing_sl_pct',0) for s in subset)/len(subset)
            print(f"    {phase:15s}: {len(subset):3d} stocks | avg WR={aw:.0f}% | avg RR={ar:.1f}x | avg Swing={sw_subset:.0f}%")
        
        outpath = OUTPUT_DIR / 'backtest_v23.json'
        json.dump({'timestamp': datetime.now().isoformat(), 'config': {'version':'V23'},
                   'summary': {'total_trades':n, 'tradable':len(stock_results),
                              'win_rate':round(wr,1), 'avg_rr':round(avg_rr,2),
                              'profit_factor':round(pf,2), 'avg_pnl':round(avg_pnl,2),
                              'skipped_low_swing': skipped_low_swing},
                   'stocks':stock_results, 'all_trades':all_trades},
                  open(outpath,'w'), ensure_ascii=False, indent=2, default=str)
        print(f"\n  Saved: {outpath}")

if __name__ == '__main__':
    main()
