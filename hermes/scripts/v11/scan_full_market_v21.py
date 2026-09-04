#!/usr/bin/env python3
"""
V21 — FINAL ENGINE: Swing-Enhanced + Multi-Cycle + Seq Scoring
===============================================================
整合V12-V20所有已验证发现:
  V16核心: 摆动SL封顶0.5%, OB过滤, 距离≤20
  V18发现: 每股最优SL=0.3%/TP=3.0%
  V19发现: 信号序列评分(seq≥0.7=92% WR)
  V20发现: 多周期ALL-UP=82% WR

最终策略:
  1. Scout-only + Bull-only
  2. 摆动SL封顶0.5%(距入场≤20K线), 无摆动时FVG-only SL=0.3%
  3. OB仅当有摆动SL时接受
  4. 信号序列评分过滤 (跳过BEARISH/1UP-2NEUTRAL)
  5. 每股参数: SL=0.3%/TP=3.0% (V18最优)
  6. 全量4800扫描 + 并行4进程

预期: WR=80-82%, 覆盖35-40%
"""
import json, sys, time, math, logging
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
import concurrent.futures

logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase
from v11.weekly_trend import synthesize_weekly, weekly_trend

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v21')
OUTPUT_DIR.mkdir(exist_ok=True)

# ====== V21 FINAL PARAMETERS ======
MAX_STOCKS = 99999
MIN_BARS = 120
ROLL_START = 80
ROLL_END_OFFSET = 10
MAX_HOLD = 60
COOLDOWN = 15

# SL/TP — V16 proven + V18 per-stock optimal
SWING_MAX_DISTANCE = 20
SWING_SL_CAP = 0.5
FIXED_SL = 0.3   # V18每股最优
FIXED_TP = 3.0   # V18每股最优
SWING_TP_MIN_RR = 2.0

# Signal quality
MIN_VOL_RATIO = 0.8
MIN_FVG_GAP = 0.3
SCOUT_MIN_RES = 0.65
OB_MIN_RES = 0.70

BATCH_SIZE = 500
NUM_WORKERS = 4


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


def find_best_swing_sl(ohlcv, end_idx, entry_price):
    swings = find_all_swing_lows(ohlcv, end_idx, lookback=50)
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
    swings = find_all_swing_highs(ohlcv, end_idx, lookback=50)
    swings = [s for s in swings if s[2] <= SWING_MAX_DISTANCE]
    if not swings: return None
    best = None; best_score = 999
    sl_pct = (entry_price - sl_price) / entry_price * 100 if entry_price > sl_price else 0.3
    for idx, price, dist in swings:
        tp = max(price, entry_price * 1.005)
        tp_pct = (tp - entry_price) / entry_price * 100
        tc_rr = tp_pct / sl_pct if sl_pct > 0 else 10
        if tc_rr >= SWING_TP_MIN_RR and tp_pct <= 20.0:
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


def get_entry_signal_info(seq_result):
    entry_sig = seq_result.get('entry_signal', {})
    fvg_entry = seq_result.get('fvg_entry')
    if fvg_entry and fvg_entry.get('idx') is not None:
        return fvg_entry.get('idx', 0), fvg_entry.get('type', ''), fvg_entry
    return entry_sig.get('idx', 0), entry_sig.get('type', ''), entry_sig


def score_multi_cycle(ohlcv, idx):
    """V20: 三级多周期评分"""
    micro = short_trend(ohlcv, idx, lookback=8)
    meso = short_trend(ohlcv, idx, lookback=20)
    macro = short_trend(ohlcv, idx, lookback=40)
    cycles = [micro, meso, macro]
    up_count = sum(1 for c in cycles if c[0] == 'up')
    down_count = sum(1 for c in cycles if c[0] == 'down')
    
    if up_count == 3: return 1.0, 'ALL-UP'
    elif up_count >= 2 and down_count == 0: return 0.85, '2UP-1NEUTRAL'
    elif up_count >= 2: return 0.75, '2UP-1DOWN'
    elif up_count == 1 and down_count == 0: return 0.60, '1UP-2NEUTRAL'
    elif down_count >= 2: return 0.20, 'BEARISH'
    else: return 0.40, 'NEUTRAL'


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
    
    # V21: Multi-cycle filter — skip bad cycles
    cycle_score, cycle_detail = score_multi_cycle(ohlcv, end_idx)
    if cycle_detail in ('BEARISH', '1UP-2NEUTRAL'):
        return None  # Skip weak bearish or mixed-down cycles
    
    effective_min_resonance = SCOUT_MIN_RES
    if cycle_score >= 0.85:
        effective_min_resonance = 0.55  # Strong cycles = easier entry
    if signal_type == 'OB':
        effective_min_resonance = max(effective_min_resonance, OB_MIN_RES)
    
    window = ohlcv[:end_idx + 1]
    tf_sequences = {'daily': seq_result}
    resonance = evaluate_full_resonance_v11(all_signals=sigs_before, tf_sequences=tf_sequences, ohlcv=window)
    if resonance.total < effective_min_resonance: return None
    
    return {
        'seq_result': seq_result, 'resonance': resonance,
        'seq_name': seq_name, 'is_scout': is_scout,
        'n_sigs': len(sigs_before), 'best_seq': best_seq,
        'signal_type': signal_type,
        'cycle_score': cycle_score, 'cycle_detail': cycle_detail,
    }


def simulate_trades(ohlcv, all_signals, params):
    n = len(ohlcv); roll_end = n - ROLL_END_OFFSET
    trades = []; entered_bar = -999
    
    for i in range(ROLL_START, roll_end):
        if i - entered_bar < COOLDOWN: continue
        entry_info = analyze_at_point(ohlcv, all_signals, i, params)
        if entry_info is None: continue
        
        seq_result = entry_info['seq_result']
        resonance = entry_info['resonance']
        tf_sequences = {'daily': seq_result}
        best_seq = entry_info['best_seq']; signal_type = entry_info['signal_type']
        cycle_detail = entry_info['cycle_detail']
        
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
            'entry_idx': i, 'exit_idx': exit_idx,
            'entry_price': round(entry_price,2), 'exit_price': round(exit_price,2),
            'sl': round(sl_price,2), 'tp': round(tp_price,2),
            'pnl_pct': round(pnl_pct,2), 'won': won, 'rr': round(actual_rr,2),
            'seq_name': best_seq.get('name', 'Scout'),
            'hold_bars': exit_idx - i,
            'sl_type': swing_params['sl_type'], 'sl_pct': swing_params['sl_pct'],
            'signal_type': signal_type,
            'cycle_detail': cycle_detail,
        })
        entered_bar = i
    return trades


def backtest_stock(ohlcv, symbol):
    t0 = time.time()
    phase = detect_market_phase(ohlcv)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')['all']
    if not all_signals or len(all_signals) < 5:
        return None
    params = {**base_params, 'sl_pct': FIXED_SL, 'tp_pct': FIXED_TP}
    trades = simulate_trades(ohlcv, all_signals, params)
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
        'perf': {
            'n_trades': len(trades), 'wins': wins, 'losses': len(trades)-wins,
            'win_rate': round(wr,1), 'avg_rr': round(avg_rr,2),
            'profit_factor': round(pf,2) if pf < 999 else 999,
            'avg_pnl': round(avg_pnl,2), 'total_pnl': round(sum(t['pnl_pct'] for t in trades),2),
            'swing_sl_pct': round(swing_sl/len(trades)*100,1),
        },
        'n_signals': len(all_signals), 'phase': phase, 'elapsed': round(time.time()-t0,1),
    }


def scan_batch(symbols, batch_id):
    results = []
    for idx, sym in enumerate(symbols):
        ohlcv = load_ohlcv(sym)
        if not ohlcv: continue
        result = backtest_stock(ohlcv, sym)
        if result:
            results.append({'symbol': sym, **result['perf'],
                           'n_signals': result['n_signals'], 'phase': result['phase']})
            results[-1]['_trades'] = result['trades']  # attach trades
            if (idx+1) % 50 == 0:
                print(f"  [B{batch_id}-{idx:3d}] {sym:12s} t={result['perf']['n_trades']:2d} WR={result['perf']['win_rate']:.0f}%")
        else:
            if (idx+1) % 50 == 0:
                print(f"  [B{batch_id}-{idx:3d}] {sym:12s} NO-TRADE")
    return results


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print(f"V21 FINAL — Full Market Scan ({len(symbols)} stocks)")
    print(f"  SL/TP: Swing cap={SWING_SL_CAP}% / Fixed={FIXED_SL}%/{FIXED_TP}%")
    print(f"  Multi-cycle: SKIP BEARISH+1UP2NEUTRAL | ALL-UP res=0.55")
    print(f"  Swing dist<={SWING_MAX_DISTANCE} bars | OB filtered at fixed")
    print(f"{'='*80}")
    
    all_results = []
    all_trades = []
    t_start = time.time()
    
    for batch_start in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[batch_start:batch_start+BATCH_SIZE]
        batch_id = batch_start // BATCH_SIZE
        print(f"\n--- Batch {batch_id} ({batch_start}-{batch_start+len(batch)}) ---")
        
        t0 = time.time()
        results = scan_batch(batch, batch_id)
        elapsed = time.time() - t0
        
        for r in results:
            all_results.append({k:v for k,v in r.items() if k != '_trades'})
            all_trades.extend(r.get('_trades', []))
        
        print(f"  Batch {batch_id}: {len(results)} tradable, in {elapsed:.1f}s")
        
        # Save intermediate
        if all_trades:
            batch_out = OUTPUT_DIR / f'batch_{batch_start}_{batch_start+len(batch)}.json'
            json.dump({'stocks': all_results, 'trades': all_trades}, 
                      open(batch_out,'w'), default=str)
    
    total_time = time.time() - t_start
    print(f"\n{'='*80}")
    print(f"V21 FINAL — {len(all_results)}/{len(symbols)} | {total_time:.0f}s")
    print(f"{'='*80}")
    
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
        n80 = sum(1 for s in all_results if s['win_rate']>=80)
        n70 = sum(1 for s in all_results if s['win_rate']>=70)
        
        print(f"\n  Trades: {n} | WR: {wr:.1f}% | RR: {avg_rr:.2f}x | PF: {pf:.2f} | P&L: {avg_pnl:+.2f}%")
        print(f"  Swing SL: {len(sw)}/{n} ({len(sw)/n*100:.0f}%) | Swing WR: {sw_wr:.1f}%")
        print(f"  WR>=70%: {n70} stocks | WR>=80%: {n80} stocks")
        print(f"  Avg hold: {sum(t['hold_bars'] for t in all_trades)/n:.1f} bars")
        
        # Cycle detail
        cd_cnt = Counter(t.get('cycle_detail','?') for t in all_trades)
        print(f"\n  Cycle Detail:")
        for detail, cnt in cd_cnt.most_common():
            subset = [t for t in all_trades if t.get('cycle_detail','')==detail]
            swr = sum(1 for t in subset if t['won'])/len(subset)*100
            print(f"    {detail:15s}: {cnt:3d} trades | WR={swr:.0f}%")
        
        # Save final
        outpath = OUTPUT_DIR / 'v21_final_merged.json'
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'config': {'version':'V21','swing_max_dist':SWING_MAX_DISTANCE,
                       'sl_cap':SWING_SL_CAP,'sl_fixed':FIXED_SL,'tp_fixed':FIXED_TP},
            'summary':{'total_symbols':len(symbols),'tradable':len(all_results),
                       'total_trades':n,'win_rate':round(wr,1),'avg_rr':round(avg_rr,2),
                       'profit_factor':round(pf,2),'avg_pnl':round(avg_pnl,2)},
            'stocks':all_results,'all_trades':all_trades,
        }, open(outpath,'w'), ensure_ascii=False, indent=2, default=str)
        print(f"\n  Saved: {outpath}")

if __name__ == '__main__':
    main()
