#!/usr/bin/env python3
"""
V22 — Signal Sequence Enhanced Entry Decision
==============================================
V21基线: WR=77.7%, PF=63.5, 摆动SL WR=95.3%

V22创新 — 信号序列模式嵌入入场决策:
  之前: 信号序列只做分析, 不参与入场判断
  V22: 信号序列评分直接修改共振门槛

信号序列评分规则(基于V18分析):
  OB→FVG = 90% WR → 降低共振门槛0.10
  Sweep→FVG = 85% WR → 降低共振门槛0.08
  FVG→OB = 100% WR → 降低共振门槛0.15
  OOOOO = 17% WR → 跳过
  SOOSO = 0% WR → 跳过
  seq≥0.7 = 92% WR → 降低门槛0.15
  默认 = 不变

预期: WR=78-80%, 更好信号质量
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
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v22')
OUTPUT_DIR.mkdir(exist_ok=True)

SWING_MAX_DISTANCE = 20; SWING_SL_CAP = 0.5; FIXED_SL = 0.3; FIXED_TP = 3.0
MIN_VOL_RATIO = 0.8; MIN_FVG_GAP = 0.3
MAX_STOCKS = 99999; MIN_BARS = 120; ROLL_START = 80
ROLL_END_OFFSET = 10; MAX_HOLD = 60; COOLDOWN = 15
BATCH_SIZE = 500


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
        bar, left, right = ohlcv[i], ohlcv[i-1] if i > start else None, ohlcv[i+1] if i < end_idx - 1 else None
        lv = left['l'] if left else 9999; rv = right['l'] if right else 9999
        if bar['l'] < lv and bar['l'] < rv:
            swings.append((i, bar['l'], end_idx - i))
    return swings

def find_all_swing_highs(ohlcv, end_idx, lookback=50):
    if end_idx < 3: return []
    start = max(0, end_idx - lookback)
    swings = []
    for i in range(end_idx - 1, start, -1):
        bar, left, right = ohlcv[i], ohlcv[i-1] if i > start else None, ohlcv[i+1] if i < end_idx - 1 else None
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
    best, best_score = None, 999
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


def get_entry_signal_info(seq_result):
    entry_sig = seq_result.get('entry_signal', {})
    fvg_entry = seq_result.get('fvg_entry')
    if fvg_entry and fvg_entry.get('idx') is not None:
        return fvg_entry.get('idx', 0), fvg_entry.get('type', ''), fvg_entry
    return entry_sig.get('idx', 0), entry_sig.get('type', ''), entry_sig


def score_signal_sequence(sigs_before, entry_signal_type):
    """
    V22: 信号序列模式评分 (基于V18发现的真实WR数据)
    返回: (seq_score, seq_detail, res_modifier)
      - seq_score: 0.0-1.0 模式质量
      - seq_detail: 模式描述
      - res_modifier: 共振门槛修正值 (-0.15 to +0.15)
    """
    if len(sigs_before) < 3:
        return 0.5, 'insufficient', 0.0
    
    recent = [s for s in sigs_before[-8:]][-5:]
    pattern = []
    for s in recent:
        st = s.get('type', '?')
        if 'FVG' in st: pattern.append('F')
        elif 'OB' in st: pattern.append('O')
        elif 'Sweep' in st: pattern.append('S')
        elif 'CHOCH' in st: pattern.append('C')
        elif 'BPR' in st: pattern.append('B')
        else: pattern.append('?')
    
    if not pattern: return 0.5, 'empty', 0.0
    
    seq = ''.join(pattern)
    
    # === SEQUENCE RULES (from V18 discovered WR data) ===
    
    # TERRIBLE PATTERNS — SKIP
    if seq == 'OOOOO': return 0.0, 'OOOOO:17%', -99  # skip
    if 'SOOSO' in seq: return 0.0, 'SOOSO:0%', -99   # skip
    if pattern.count('O') >= 4: return 0.1, f'OBx{pattern.count("O")}:17%', -0.20
    
    score = 0.5
    res_mod = 0.0  # Negative = lower threshold (easier entry), positive = raise threshold
    
    # BEST PATTERNS — lower threshold
    if len(pattern) >= 2:
        if pattern[-1] == 'F' and 'S' in pattern[:-1]:
            # Sweep→FVG: 85% WR
            score += 0.20; res_mod -= 0.08
        if pattern[-1] == 'F' and pattern[-2] == 'O':
            # OB→FVG: 90% WR
            score += 0.25; res_mod -= 0.10
        if pattern[-1] == 'O' and pattern[-2] == 'F':
            # FVG→OB: 100% WR
            score += 0.20; res_mod -= 0.15
    
    # GOOD patterns — slight bonus
    if pattern[-1] == 'F':
        score += 0.10; res_mod -= 0.03
    
    # NOISE patterns — raise threshold
    ob_count = pattern.count('O')
    if ob_count >= 3: score -= 0.10; res_mod += 0.10
    if len(set(pattern)) <= 1: score -= 0.15; res_mod += 0.08
    
    # DIVERSITY bonus
    if len(set(pattern)) >= 3 and len(pattern) >= 3:
        score += 0.05; res_mod -= 0.05
    
    score = max(0.0, min(1.0, score))
    res_mod = max(-0.20, min(0.20, res_mod))
    
    return round(score, 2), seq, round(res_mod, 2)


def analyze_at_point_v22(ohlcv, all_signals, end_idx, params):
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
    
    # V22: Signal sequence scoring
    seq_score, seq_pattern, res_mod = score_signal_sequence(sigs_before, signal_type)
    
    # Skip terrible patterns
    if seq_score <= 0.0:
        return None
    
    # Adjust resonance threshold based on signal sequence
    base_res = 0.65
    if signal_type == 'OB': base_res = 0.70
    adjusted_res = base_res + res_mod  # res_mod is negative = easier, positive = harder
    adjusted_res = max(0.40, min(0.85, adjusted_res))
    
    window = ohlcv[:end_idx + 1]
    tf_sequences = {'daily': seq_result}
    resonance = evaluate_full_resonance_v11(all_signals=sigs_before, tf_sequences=tf_sequences, ohlcv=window)
    if resonance.total < adjusted_res: return None
    
    return {
        'seq_result': seq_result, 'resonance': resonance,
        'seq_name': seq_name, 'is_scout': is_scout,
        'n_sigs': len(sigs_before), 'best_seq': best_seq,
        'signal_type': signal_type,
        'seq_score': seq_score, 'seq_pattern': seq_pattern,
        'res_mod': res_mod, 'adj_res': round(adjusted_res, 2),
    }


def simulate_trades(ohlcv, all_signals, params):
    n = len(ohlcv); roll_end = n - ROLL_END_OFFSET
    trades = []; entered_bar = -999
    
    for i in range(ROLL_START, roll_end):
        if i - entered_bar < COOLDOWN: continue
        entry_info = analyze_at_point_v22(ohlcv, all_signals, i, params)
        if entry_info is None: continue
        
        seq_result = entry_info['seq_result']
        resonance = entry_info['resonance']
        tf_sequences = {'daily': seq_result}
        best_seq = entry_info['best_seq']; signal_type = entry_info['signal_type']
        seq_score = entry_info['seq_score']; seq_pattern = entry_info['seq_pattern']
        res_mod = entry_info['res_mod']; adj_res = entry_info['adj_res']
        
        decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
        if decision['action'] != 'enter': continue
        entry_price = decision.get('entry_price')
        if not entry_price: continue
        
        swing_params = calc_sltp(ohlcv, i, entry_price, signal_type)
        if swing_params is None: continue
        sl_price = swing_params['sl']; tp_price = swing_params['tp']
        
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
            'sl_type': swing_params['sl_type'], 'sl_pct': swing_params['sl_pct'],
            'signal_type': signal_type,
            'seq_score': seq_score, 'seq_pattern': seq_pattern,
            'adj_res': adj_res,
        })
        entered_bar = i
    return trades


def backtest_stock(ohlcv, symbol):
    t0 = time.time()
    phase = detect_market_phase(ohlcv)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')['all']
    if not all_signals or len(all_signals) < 5: return None
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
        'perf': {'n_trades': len(trades), 'wins': wins, 'losses': len(trades)-wins,
                 'win_rate': round(wr,1), 'avg_rr': round(avg_rr,2),
                 'profit_factor': round(pf,2) if pf < 999 else 999,
                 'avg_pnl': round(avg_pnl,2),
                 'swing_sl_pct': round(swing_sl/len(trades)*100,1)},
        'n_signals': len(all_signals), 'phase': phase, 'elapsed': round(time.time()-t0,1),
    }


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print(f"V22 — Signal Sequence Enhanced (200 stocks test)")
    print(f"  OB→FVG:-0.10res | Sweep→FVG:-0.08res | OOOOO:SKIP")
    print(f"{'='*80}")
    
    all_trades, stock_results = [], []; t_start = time.time()
    
    for idx, sym in enumerate(symbols[:200]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv: continue
        result = backtest_stock(ohlcv, sym)
        if result:
            p = result['perf']
            all_trades.extend(result['trades'])
            stock_results.append({'symbol': sym, **p})
            if (idx+1) % 20 == 0:
                print(f"  [{idx+1:3d}/200] {sym:12s} t={p['n_trades']:2d} WR={p['win_rate']:.0f}% RR={p['avg_rr']:.1f}x")
        elif (idx+1) % 20 == 0:
            print(f"  [{idx+1:3d}/200] {sym:12s} NO-TRADE")
    
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
        print(f"V22 — {len(stock_results)} tradable | {total_time:.0f}s")
        print(f"{'='*80}")
        print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {avg_rr:.2f}x | PF: {pf:.2f} | P&L: {avg_pnl:+.2f}%")
        print(f"  Swing SL: {len(sw)}/{n} ({len(sw)/n*100:.0f}%) | WR={sw_wr:.1f}%")
        print(f"  WR>=70%: {sum(1 for s in stock_results if s['win_rate']>=70)} | WR>=80%: {sum(1 for s in stock_results if s['win_rate']>=80)}")
        
        # Sequence pattern analysis
        seq_cnt = Counter(t.get('seq_pattern', '?') for t in all_trades)
        print(f"\n  Signal Sequence Patterns:")
        for seq, cnt in seq_cnt.most_common(10):
            subset = [t for t in all_trades if t.get('seq_pattern','')==seq]
            swr = sum(1 for t in subset if t['won'])/len(subset)*100
            print(f"    {seq:15s}: {cnt:3d} trades | WR={swr:.0f}%")
        
        # Adj_res analysis
        print(f"\n  Adjusted Resonance Threshold vs WR:")
        for thresh in [0.45, 0.50, 0.55, 0.60, 0.65, 0.70]:
            subset = [t for t in all_trades if t.get('adj_res',0) <= thresh]
            if subset:
                swr = sum(1 for t in subset if t['won'])/len(subset)*100
                print(f"    res<={thresh:.2f}: {len(subset):3d} trades | WR={swr:.0f}%")
        
        outpath = OUTPUT_DIR / 'backtest_v22.json'
        json.dump({'timestamp': datetime.now().isoformat(),
                   'config': {'version':'V22'},
                   'summary': {'total_trades':n, 'tradable':len(stock_results),
                              'win_rate':round(wr,1), 'avg_rr':round(avg_rr,2)},
                   'stocks':stock_results, 'all_trades':all_trades},
                  open(outpath,'w'), ensure_ascii=False, indent=2, default=str)
        print(f"\n  Saved: {outpath}")

if __name__ == '__main__':
    main()
