#!/usr/bin/env python3
"""
V33 — V28 Core + Comprehensive Signal Time-Sequence Scoring
===========================================================
保留V28已验证的紧架构(SL=0.3%, confirmed_at入口, 追踪止盈)
加上V33三层信号时序评分系统

时序评分决定:
  - 是否入场 (grade A/B/C=enter, D=wait, F=skip)
  - 共振门槛调整 (entry_mult)
  - 入场信心水平
"""
import json, sys, time
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase
from v11.signal_timing_sequencer_v11 import score_signal_timing

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v33')
OUTPUT_DIR.mkdir(exist_ok=True)

# === V28 proven params ===
SL_FIXED = 0.3
SWING_SL_CAP = 0.5
SWING_MAX_DIST = 20
MIN_VOL_RATIO = 0.7
MIN_FVG_GAP = 0.2
MIN_TRADES = 2
MIN_BARS = 120
ROLL_START = 60
ROLL_END_OFFSET = 10
MAX_HOLD = 60
COOLDOWN = 8

# === V28 Trailing (tight) ===
TRAIL_BE_PCT = 0.2
TRAIL_BE_SL = 0.0  # SL = entry
TRAIL_PROFIT_PCT = 0.5
TRAIL_PROFIT_SL = 0.2
TRAIL_SECURE_PCT = 1.5
TRAIL_SECURE_TRAIL = 0.8

def load_ohlcv(symbol):
    fname = f"{symbol.replace('.','_')}_daily_300.json"
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
    pct = (e - s) / s * 100
    ema = sum(ohlcv[i]['c'] for i in range(idx-min(5,idx), idx+1)) / min(6, idx+1)
    ed = (ohlcv[idx]['c'] - ema) / ema * 100
    if pct > 0.5 and ed > 0: return 'up', pct
    if pct < -0.5 and ed < 0: return 'down', abs(pct)
    return 'neutral', 0

def synthesize_weekly(ohlcv):
    weekly = []
    for i in range(0, len(ohlcv), 5):
        chunk = ohlcv[i:i+5]
        if not chunk: continue
        weekly.append({'o': chunk[0]['o'], 'h': max(b['h'] for b in chunk),
                       'l': min(b['l'] for b in chunk), 'c': chunk[-1]['c'],
                       'v': sum(b.get('v', b.get('vol', 0)) for b in chunk)})
    return weekly

def weekly_trend(weekly, lookback=5):
    if len(weekly) < lookback: return 'neutral'
    seg = weekly[-lookback:]
    s, e = seg[0]['c'], seg[-1]['c']
    pct = (e - s) / s * 100
    green = sum(1 for b in seg if b['c'] > b['o'])
    if pct > 2 and green >= lookback * 0.6: return 'up'
    if pct < -2 and green <= lookback * 0.4: return 'down'
    return 'neutral'

def find_all_swing_lows(ohlcv, end_idx, lookback=50):
    if end_idx < 3: return []
    start = max(0, end_idx - lookback)
    swings = []
    for i in range(end_idx - 1, start, -1):
        left = ohlcv[i-1] if i > start else None
        right = ohlcv[i+1] if i < end_idx-1 else None
        lv = left['l'] if left else 9999
        rv = right['l'] if right else 9999
        if ohlcv[i]['l'] < lv and ohlcv[i]['l'] < rv:
            swings.append((i, ohlcv[i]['l'], end_idx - i))
    return swings

def find_best_swing_sl(ohlcv, end_idx, entry_price):
    swings = find_all_swing_lows(ohlcv, end_idx)
    swings = [s for s in swings if s[2] <= SWING_MAX_DIST]
    if not swings: return None
    best, bs = None, 999
    for idx, price, dist in swings:
        capped = min(price, entry_price * (1 - SWING_SL_CAP / 100))
        sl_pct = (entry_price - capped) / entry_price * 100
        if 0.15 <= sl_pct <= 0.7:
            score = abs(sl_pct - 0.4) * 0.5 + (dist / SWING_MAX_DIST) * 0.5
            if score < bs: bs = score; best = {'sl_price': capped, 'sl_pct': round(sl_pct,2)}
    return best

def calc_trailing_v33(ohlcv, entry_idx, entry_price, initial_sl, n, max_hold=60):
    """V28 tight trailing"""
    sl = initial_sl
    highest = entry_price
    exit_idx, exit_price, won = -1, None, False
    for j in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        bar = ohlcv[j]
        if bar['h'] > highest: highest = bar['h']
        gain = (highest - entry_price) / entry_price * 100
        if gain >= TRAIL_SECURE_PCT:
            new_sl = highest * (1 - TRAIL_SECURE_TRAIL / 100)
            sl = max(sl, new_sl)
        elif gain >= TRAIL_PROFIT_PCT:
            sl = max(sl, entry_price * (1 + TRAIL_PROFIT_SL / 100))
        elif gain >= TRAIL_BE_PCT:
            sl = max(sl, entry_price * (1 + TRAIL_BE_SL / 100))
        if bar['l'] <= sl:
            exit_idx = j
            exit_price = max(sl, bar['l'])
            won = exit_price > entry_price
            break
    if exit_idx == -1:
        exit_idx = min(entry_idx + max_hold, n - 1)
        exit_price = ohlcv[exit_idx]['c']
        won = exit_price > entry_price
    return exit_idx, exit_price, won


def run_stock_v33(symbol):
    """V33: V28 core + signal timing scoring"""
    ohlcv = load_ohlcv(symbol)
    if not ohlcv: return None
    
    try:
        n = len(ohlcv)
        roll_end = n - ROLL_END_OFFSET
        phase = detect_market_phase(ohlcv)
        base = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
        all_signals = detect_all_signals_v11(ohlcv, params=base, tf='daily')['all']
        if not all_signals or len(all_signals) < 3: return None
        
        # Pre-calc weekly
        weekly = synthesize_weekly(ohlcv)
        wt = weekly_trend(weekly)
        
        trades = []
        entered_bar = -999
        swing_count, fixed_count = 0, 0
        seq_perf = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0.0})
        
        for i in range(ROLL_START, roll_end):
            if i - entered_bar < COOLDOWN: continue
            
            # Get signals up to current bar
            sigs_before = [s for s in all_signals if s.get('idx', 0) <= i]
            
            # Find last confirmed FVG Bull
            fvg_bull = [s for s in sigs_before if 'FVG_Bull' in s.get('type', '')]
            if not fvg_bull: continue
            
            sig = None
            for s in reversed(fvg_bull):
                s_conf = s.get('confirmed_at', s.get('idx', 0) + 1)
                if i >= s_conf:
                    sig = s
                    break
            if sig is None: continue
            
            # === V33: Signal Time-Sequence Scoring ===
            timing = score_signal_timing(all_signals, sig)
            
            # Grade A/B: enter confidently | Grade C: enter with caution | D/F: skip
            if timing['grade'] in ('D', 'F'): continue
            # Grade C: reduce conviction slightly
            if timing['grade'] == 'C':
                # Only accept C-grade if entry_mult >= 0.5
                if timing['entry_mult'] < 0.5: continue
            
            # === Standard filters (V28) ===
            # Volume
            bar_vol = ohlcv[i].get('v', ohlcv[i].get('vol', 0))
            avg_vol = sum(ohlcv[j].get('v', ohlcv[j].get('vol', 0)) for j in range(max(0,i-30),i)) / 30
            if avg_vol > 0 and bar_vol < avg_vol * MIN_VOL_RATIO: continue
            
            # Bullish close
            if ohlcv[i]['c'] <= ohlcv[i]['o']: continue
            
            # FVG gap
            upper = sig.get('upper', 0); lower = sig.get('lower', 0)
            if upper > 0 and lower > 0:
                if (upper - lower) / lower * 100 < MIN_FVG_GAP: continue
            
            # Minimum signals
            if len(sigs_before) < 5: continue
            
            # Trend
            td, _ = short_trend(ohlcv, i)
            if td == 'down': continue
            
            # Weekly
            if wt == 'down': continue
            
            # Multi-cycle
            micro = short_trend(ohlcv, i, 8)
            meso = short_trend(ohlcv, i, 20)
            macro = short_trend(ohlcv, i, 40)
            up_cnt = sum(1 for c in [micro, meso, macro] if c[0] == 'up')
            down_cnt = sum(1 for c in [micro, meso, macro] if c[0] == 'down')
            if down_cnt >= 2: continue
            if up_cnt == 1 and down_cnt == 0: continue
            
            # Entry price
            entry_price = ohlcv[i]['c']
            
            # SL: swing if available, then fixed
            sl_info = find_best_swing_sl(ohlcv, i, entry_price)
            if sl_info is not None:
                init_sl = sl_info['sl_price']; sl_pct = sl_info['sl_pct']; sl_type = 'swing'
            else:
                init_sl = entry_price * (1 - SL_FIXED / 100); sl_pct = SL_FIXED; sl_type = 'fixed'
            
            if sl_type == 'swing': swing_count += 1
            else: fixed_count += 1
            
            # Trailing exit
            exit_idx, exit_price, won = calc_trailing_v33(ohlcv, i, entry_price, init_sl, n, MAX_HOLD)
            
            pnl = (exit_price - entry_price) / entry_price * 100
            risk = abs(entry_price - init_sl)
            actual_rr = abs(exit_price - entry_price) / risk if risk > 0 else 10
            
            # Record trade with timing metadata
            trade = {
                'entry_idx': i, 'exit_idx': exit_idx,
                'entry_price': round(entry_price, 2),
                'exit_price': round(exit_price, 2),
                'sl': round(init_sl, 2),
                'pnl_pct': round(pnl, 2),
                'won': won, 'rr': round(actual_rr, 2),
                'hold_bars': exit_idx - i,
                'sl_type': sl_type, 'sl_pct': round(sl_pct, 2),
                'signal_type': 'FVG',
                'seq_score': timing['score'],
                'seq_grade': timing['grade'],
                'seq_chain': timing['chain'],
                'seq_desc': timing['desc'],
                'entry_mult': timing['entry_mult'],
                'phase': phase,
            }
            trades.append(trade)
            
            # Track seq performance
            desc = timing['desc'][:35]
            seq_perf[desc]['trades'] += 1
            seq_perf[desc]['wins'] += 1 if won else 0
            seq_perf[desc]['pnl'] += pnl
            
            entered_bar = i
        
        if len(trades) < MIN_TRADES: return None
        
        wins = sum(1 for t in trades if t['won'])
        wr = wins / len(trades) * 100
        win_pnl = sum(t['pnl_pct'] for t in trades if t['won'])
        loss_pnl = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
        pf = win_pnl / loss_pnl if loss_pnl > 0 else 999
        avg_rr = sum(t['rr'] for t in trades) / len(trades)
        avg_pnl = sum(t['pnl_pct'] for t in trades) / len(trades)
        
        return {
            'trades': trades,
            'perf': {
                'symbol': symbol,
                'n_trades': len(trades), 'wins': wins, 'losses': len(trades)-wins,
                'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
                'profit_factor': round(pf, 1) if pf < 999 else 999,
                'avg_pnl': round(avg_pnl, 2),
                'swing_sl_pct': round(swing_count/len(trades)*100, 1),
                'phase': phase,
                'avg_seq_score': round(sum(t['seq_score'] for t in trades)/len(trades), 2),
            },
            'seq_perf': dict(seq_perf),
        }
    except Exception as e:
        return None


def main():
    symbols = sorted([f.stem.replace('_daily_300','').replace('_','.') for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print(f"V33 — V28 Core + Comprehensive Signal Time-Sequence Scoring")
    print(f"  3-layer timing: pairs, chains, patterns")
    print(f"  Score grades: A/enter, B/enter, C/enter, D/wait, F/skip")
    print(f"  Test: 200 stocks")
    print(f"{'='*80}")
    
    all_trades, stock_results = [], []
    all_seq_perf = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0.0})
    t_start = time.time()
    analyzed = len(symbols[:200])
    
    for idx, sym in enumerate(symbols[:200]):
        result = run_stock_v33(sym)
        if result:
            p = result['perf']
            all_trades.extend(result['trades'])
            stock_results.append(p)
            for desc, data in result.get('seq_perf', {}).items():
                all_seq_perf[desc]['trades'] += data['trades']
                all_seq_perf[desc]['wins'] += data['wins']
                all_seq_perf[desc]['pnl'] += data['pnl']
            print(f"  [{idx+1:3d}/200] {sym:12s} n={p['n_trades']:2d} WR={p['win_rate']:.0f}% seq={p['avg_seq_score']:.2f} PF={p['profit_factor']:.0f}", flush=True)
        else:
            print(f"  [{idx+1:3d}/200] {sym:12s} SKIP", flush=True)
    
    total_time = time.time() - t_start
    
    if all_trades:
        n = len(all_trades)
        wins = sum(1 for t in all_trades if t['won'])
        wr = wins / n * 100
        win_pnl = sum(t['pnl_pct'] for t in all_trades if t['won'])
        loss_pnl = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
        pf = win_pnl / loss_pnl if loss_pnl > 0 else 999
        avg_rr = sum(t['rr'] for t in all_trades) / n
        avg_pnl = sum(t['pnl_pct'] for t in all_trades) / n
        swing_trades = [t for t in all_trades if t.get('sl_type') == 'swing']
        sw_wr = sum(1 for t in swing_trades if t['won']) / len(swing_trades) * 100 if swing_trades else 0
        n80 = sum(1 for s in stock_results if s['win_rate'] >= 80)
        
        print(f"\n{'='*80}")
        print(f"V33 — {len(stock_results)}/{analyzed} tradable | {total_time:.0f}s")
        print(f"{'='*80}")
        print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {avg_rr:.2f}x | PF: {pf:.0f} | P&L: {avg_pnl:+.2f}%")
        print(f"  Swing SL: {len(swing_trades)}/{n} ({len(swing_trades)/n*100:.0f}%) | WR={sw_wr:.1f}%")
        print(f"  WR>=80%: {n80}/{len(stock_results)}")
        
        print(f"\n  Signal Sequence Performance (V33):")
        for desc, data in sorted(all_seq_perf.items(), key=lambda x: x[1]['trades'], reverse=True):
            swr = data['wins'] / data['trades'] * 100
            apnl = data['pnl'] / data['trades']
            if data['trades'] >= 3:
                print(f"    {desc:35s}: {data['trades']:3d} trades | WR={swr:.0f}% | P&L={apnl:+.2f}%")
        
        print(f"\n  P&L Distribution:")
        for bucket in [(-5,0),(0,0.5),(0.5,1),(1,2),(2,5),(5,10),(10,50)]:
            subset = [t for t in all_trades if bucket[0] <= t['pnl_pct'] < bucket[1]]
            if subset:
                wr_s = sum(1 for t in subset if t['won']) / len(subset) * 100
                print(f"    {bucket[0]:+}% to {bucket[1]:+}%: {len(subset):3d} trades | RR>=2: {sum(1 for t in subset if t['rr']>=2):3d}")
        
        # RR>=2.0 subset
        good = [t for t in all_trades if t['rr'] >= 2.0]
        gw = sum(1 for t in good if t['won'])/len(good)*100 if good else 0
        print(f"\n  RR>=2.0 subset: {len(good)}/{n} trades | WR={gw:.1f}% | P&L={sum(t['pnl_pct'] for t in good)/len(good):+.2f}%")
        
        print(f"\n{'='*80}")
        print(f"                        V28 vs V33 COMPARISON                         ")
        print(f"{'='*80}")
        print(f"  V28: WR=76.6% RR=5.94x PF=27 P&L=+1.59% (no seq scoring)")
        print(f"  V33: WR={wr:.1f}% RR={avg_rr:.2f}x PF={pf:.0f} P&L={avg_pnl:+.2f}% (3-layer timing)")
        
        # Save
        outpath = OUTPUT_DIR / 'backtest_v33.json'
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'config': {'version': 'V33', 'sl': SL_FIXED, 'seq_scoring': '3-layer'},
            'summary': {
                'total_trades': n, 'tradable': len(stock_results),
                'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
                'profit_factor': round(pf, 2), 'avg_pnl': round(avg_pnl, 2),
                'avg_seq_score': round(sum(t['seq_score'] for t in all_trades)/n, 2),
            },
            'stocks': stock_results, 'all_trades': all_trades,
        }, open(outpath, 'w'), ensure_ascii=False, indent=2, default=str)
        print(f"\n  Saved: {outpath}")

if __name__ == '__main__':
    main()
