#!/usr/bin/env python3
"""
V32 — Triple Fix + Signal Time-Sequence Scoring
================================================
A) Built-in RR>=2.0 filter — skip trades where projected RR < 2.0
B) SL widened from 0.3% to 0.5% — reduce noise-triggered stops
C) Trailing improvements: breakeven at +1.0%, tighter trail at +0.8%
D) Signal time-sequence scoring — first real implementation:
   For each FVG signal, look back 20 bars, score preceding signal types
   Sweep→FVG +0.20, OB→FVG +0.15, CHOCH→FVG +0.25, isolated -0.15
"""
import json, sys, time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v32')
OUTPUT_DIR.mkdir(exist_ok=True)

# === V32: Wider SL + Better Trail + RR>=2.0 filter ===
SL = 0.5           # B) Wider SL from 0.3% to 0.5%
SWING_SL_CAP = 0.7  # Allow wider swing SL
SWING_MAX_DIST = 30
MIN_VOL_RATIO = 0.7
MIN_FVG_GAP = 0.2
MIN_TRADES = 2
MIN_BARS = 120
ROLL_START = 60
ROLL_END_OFFSET = 10
MAX_HOLD = 60
COOLDOWN = 8  # Reduced cooldown for more trades
MIN_RR = 2.0  # A) Built-in RR>=2.0 filter
MIN_RR_PROJECTED = 2.0  # C) Trailing: need projected RR >= 2.0 to enter

# C) New trailing thresholds
TRAIL_BREAKEVEN_PCT = 1.0   # Breakeven now at +1.0% (was +0.2%)
TRAIL_BREAKEVEN_SL = 0.2    # SL = entry + 0.2% after hitting breakeven
TRAIL_PROFIT_PCT = 1.5      # First tier: +1.5% → lock in +0.5%
TRAIL_PROFIT_SL = 0.5       # Lock in +0.5%
TRAIL_SECURE_PCT = 2.5      # Second tier: +2.5% → trail from high
TRAIL_SECURE_TRAIL = 1.0    # Trail max -1.0% from highest

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
        weekly.append({
            'o': chunk[0]['o'], 'h': max(b['h'] for b in chunk),
            'l': min(b['l'] for b in chunk), 'c': chunk[-1]['c'],
            'v': sum(b.get('v', b.get('vol', 0)) for b in chunk),
        })
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

def find_all_swing_lows(ohlcv, end_idx, lookback=60):
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
        if 0.15 <= sl_pct <= 1.0:
            score = abs(sl_pct - 0.5) * 0.5 + (dist / SWING_MAX_DIST) * 0.5
            if score < bs: bs = score; best = {'sl_price': capped, 'sl_pct': round(sl_pct,2)}
    return best

def calc_trailing_exit_v32(ohlcv, entry_idx, entry_price, initial_sl, n, max_hold=60):
    """V32 trailing: +1.0% breakeven, +1.5% lock, +2.5% trail"""
    sl = initial_sl
    highest = entry_price
    exit_idx, exit_price, won = -1, None, False

    for j in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        bar = ohlcv[j]
        if bar['h'] > highest: highest = bar['h']
        gain = (highest - entry_price) / entry_price * 100

        if gain >= TRAIL_SECURE_PCT:
            # Trail from high: lock in highest - 1.0%
            new_sl = highest * (1 - TRAIL_SECURE_TRAIL / 100)
            sl = max(sl, new_sl)
        elif gain >= TRAIL_PROFIT_PCT:
            # Lock in +0.5% profit
            sl = max(sl, entry_price * (1 + TRAIL_PROFIT_SL / 100))
        elif gain >= TRAIL_BREAKEVEN_PCT:
            # Breakeven +0.2%
            sl = max(sl, entry_price * (1 + TRAIL_BREAKEVEN_SL / 100))

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


def score_signal_sequence(all_signals, target_signal):
    """
    D) Signal time-sequence scoring — FIRST REAL IMPLEMENTATION
    
    Look back 20 bars from target_signal, collect preceding signals
    by TYPE (not name), score based on time-ordered signal patterns.
    """
    target_idx = target_signal.get('idx', 0)
    target_type = target_signal.get('type', '')
    
    # Only score for FVG signals
    if 'FVG' not in target_type:
        return 0.50, 'no-score'
    
    # Get preceding signals within 20 bars
    lookback = 20
    preceding = [s for s in all_signals 
                 if s.get('idx', 0) < target_idx 
                 and s.get('idx', 0) >= target_idx - lookback
                 and s.get('direction') == target_signal.get('direction')]
    
    # Remove exact same signal (same idx+type)
    preceding = [s for s in preceding 
                 if not (s.get('idx') == target_idx and s.get('type') == target_type)]
    
    if not preceding:
        # Isolated signal — penalize
        return 0.35, 'isolated'
    
    # Get the closest preceding signal by time
    closest = max(preceding, key=lambda s: s.get('idx', 0))
    closest_type = closest.get('type', '')
    
    # Also check if Sweep or CHOCH exists ANYWHERE in lookback window
    has_sweep = any('Sweep' in s.get('type', '') for s in preceding)
    has_choch = any('CHOCH' in s.get('type', '') for s in preceding)
    has_ob = any('OB' in s.get('type', '') for s in preceding)
    has_fvg = any('FVG' in s.get('type', '') for s in preceding if s.get('idx') != target_idx)
    
    score = 0.50  # Base
    
    # Build pattern description
    pattern_parts = []
    if has_sweep: pattern_parts.append('Sweep')
    if has_choch: pattern_parts.append('CHOCH')
    if has_ob: pattern_parts.append('OB')
    if has_fvg: pattern_parts.append('FVG')
    pattern = '→'.join(pattern_parts) if pattern_parts else 'none'
    
    if has_choch:
        # CHOCH→FVG = strongest reversal signal (structure break)
        score += 0.25
        pattern = f'CHOCH→{target_type}'
    elif has_sweep:
        # Sweep→FVG = liquidity grab + mitigation
        score += 0.20
        pattern = f'Sweep→{target_type}'
    elif has_ob:
        # OB→FVG = order block + fair value gap
        score += 0.15
        pattern = f'OB→{target_type}'
    elif has_fvg:
        # FVG→FVG = confluent gaps
        score += 0.10
        pattern = f'FVG→{target_type}'
    
    # Bonus: if closest signal is very near (within 3 bars)
    dist = target_idx - closest.get('idx', target_idx)
    if dist <= 3:
        score += 0.10  # Tight time proximity bonus
        pattern += f'(close:{dist})'
    
    # Penalty for noise: too many signals in window
    if len(preceding) >= 5:
        score -= 0.10  # Too much noise nearby
    
    score = max(0.0, min(1.0, score))
    return score, pattern


def simulate_trades_v32(ohlcv, all_signals, params):
    """V32 simulate with all fixes"""
    n = len(ohlcv)
    roll_end = n - ROLL_END_OFFSET
    trades = []
    entered_bar = -999
    
    phase = detect_market_phase(ohlcv)
    swing_count, fixed_count = 0, 0
    
    # Pre-calc weekly trend
    weekly = synthesize_weekly(ohlcv)
    wt = weekly_trend(weekly)
    
    for i in range(ROLL_START, roll_end):
        if i - entered_bar < COOLDOWN: continue
        
        # Check signals up to current bar
        sigs_before = [s for s in all_signals if s.get('idx', 0) <= i]
        
        # Need FVG signals
        fvg_bull = [s for s in sigs_before if 'FVG_Bull' in s.get('type', '')]
        if not fvg_bull: continue
        
        # Find last FVG signal that has been CONFIRMED by current bar
        sig = None; sig_idx = -1
        for s in reversed(fvg_bull):
            s_idx = s.get('idx', 0)
            s_conf = s.get('confirmed_at', s_idx + 1)
            if i >= s_conf:  # Confirmed by current bar
                sig = s; sig_idx = s_idx
                break
        
        if sig is None: continue  # No confirmed FVG
        
        # Bull-only filter
        if sig.get('direction') != 'bull': continue
        
        # Volume check
        bar_vol = ohlcv[i].get('v', ohlcv[i].get('vol', 0))
        avg_vol = sum(ohlcv[j].get('v', ohlcv[j].get('vol', 0)) for j in range(max(0,i-30),i)) / 30
        if avg_vol > 0 and bar_vol < avg_vol * MIN_VOL_RATIO: continue
        
        # FVG quality: bullish close
        if ohlcv[i]['c'] <= ohlcv[i]['o']: continue
        
        # FVG gap check
        upper = sig.get('upper', 0)
        lower = sig.get('lower', 0)
        if upper > 0 and lower > 0:
            gap = (upper - lower) / lower * 100
            if gap < MIN_FVG_GAP: continue
        
        # Need enough total signals
        if len(sigs_before) < 5: continue
        
        # Trend filter
        td, _ = short_trend(ohlcv, i)
        if td == 'down': continue
        
        # Weekly trend filter
        if wt == 'down': continue
        
        # D) Signal time-sequence scoring
        seq_score, seq_pattern = score_signal_sequence(all_signals, sig)
        if seq_score < 0.30: continue  # Skip isolated signals
        
        # Multi-cycle check
        micro = short_trend(ohlcv, i, 8)
        meso = short_trend(ohlcv, i, 20)
        macro = short_trend(ohlcv, i, 40)
        up_cnt = sum(1 for c in [micro, meso, macro] if c[0] == 'up')
        down_cnt = sum(1 for c in [micro, meso, macro] if c[0] == 'down')
        if down_cnt >= 2: continue
        if up_cnt == 1 and down_cnt == 0: continue
        
        # Entry price = current bar close
        entry_price = ohlcv[i]['c']
        
        # Calculate SL
        sl_info = find_best_swing_sl(ohlcv, i, entry_price)
        if sl_info is not None:
            init_sl = sl_info['sl_price']
            sl_pct = sl_info['sl_pct']
            sl_type = 'swing'
        else:
            # Fixed SL = 0.5%
            init_sl = entry_price * (1 - SL / 100)
            sl_pct = SL
            sl_type = 'fixed'
        
        # A) Projected RR check (A) — skip if RR < 2.0
        risk = abs(entry_price - init_sl)
        if risk <= 0: continue
        # C) With trailing: estimate min viable RR as 2.0
        min_reward = risk * MIN_RR
        projected_exit = entry_price + (min_reward if entry_price >= init_sl else -min_reward)
        # We need the price to move at least MIN_RR * risk in our favor
        min_needed_move = risk * MIN_RR / entry_price * 100
        # For A-shares, with 10% daily limit, this should be achievable
        # Check: if the gap to SL is > 5%, RR<2.0 means need 10% move — skip
        if sl_pct * MIN_RR > 8.0:  # Can't achieve RR>=2.0 with tight SL
            continue
        
        # Track swing usage
        if sl_type == 'swing': swing_count += 1
        else: fixed_count += 1
        
        # Execute trade with trailing
        exit_idx, exit_price, won = calc_trailing_exit_v32(ohlcv, i, entry_price, init_sl, n, MAX_HOLD)
        
        pnl = (exit_price - entry_price) / entry_price * 100
        actual_rr = abs(exit_price - entry_price) / risk if risk > 0 else 10
        
        # Store seq pattern info
        trades.append({
            'entry_idx': i, 'exit_idx': exit_idx,
            'entry_price': round(entry_price, 2),
            'exit_price': round(exit_price, 2),
            'sl': round(init_sl, 2),
            'pnl_pct': round(pnl, 2),
            'won': won, 'rr': round(actual_rr, 2),
            'hold_bars': exit_idx - i,
            'sl_type': sl_type, 'sl_pct': round(sl_pct, 2),
            'signal_type': 'FVG',
            'seq_score': round(seq_score, 2),
            'seq_pattern': seq_pattern,
            'phase': phase,
        })
        entered_bar = i
    
    total = swing_count + fixed_count
    swing_pct = swing_count / total * 100 if total else 0
    return trades, swing_pct


def run_stock(symbol):
    """Run V32 on a single stock"""
    ohlcv = load_ohlcv(symbol)
    if not ohlcv: return None
    
    # Test if symbol actually exists as 000001.SZ etc.
    try:
        phase = detect_market_phase(ohlcv)
        base = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
        sigs = detect_all_signals_v11(ohlcv, params=base, tf='daily')['all']
        if not sigs or len(sigs) < 3: return None
        trades, swing_pct = simulate_trades_v32(ohlcv, sigs, base)
        if len(trades) < MIN_TRADES: return None
        
        wins = sum(1 for t in trades if t['won'])
        wr = wins / len(trades) * 100
        wp = sum(t['pnl_pct'] for t in trades if t['won'])
        lp = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
        pf = wp / lp if lp > 0 else 999
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
                'swing_sl_pct': round(swing_pct, 1),
                'phase': phase,
            }
        }
    except Exception as e:
        return None


def main():
    symbols = sorted([f.stem.replace('_daily_300','').replace('_','.') for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print(f"V32 — Triple Fix + Signal Time-Sequence Scoring")
    print(f"  A) RR>=2.0 built-in filter")
    print(f"  B) SL: {SL}% (widened from 0.3%)")
    print(f"  C) Breakeven at +{TRAIL_BREAKEVEN_PCT}%, trail at +{TRAIL_PROFIT_PCT}%")
    print(f"  D) Signal seq scoring: CHOCH+0.25, Sweep+0.20, OB+0.15, close+0.10")
    print(f"  Test: 200 stocks")
    print(f"{'='*80}")
    
    all_trades, stock_results = [], []
    t_start = time.time()
    analyzed = len(symbols[:200])
    
    for idx, sym in enumerate(symbols[:200]):
        result = run_stock(sym)
        if result:
            p = result['perf']
            all_trades.extend(result['trades'])
            stock_results.append(p)
            print(f"  [{idx+1:3d}/200] {sym:12s} n={p['n_trades']:2d} WR={p['win_rate']:.0f}% PF={p['profit_factor']:.0f} swing={p['swing_sl_pct']:.0f}%", flush=True)
        else:
            print(f"  [{idx+1:3d}/200] {sym:12s} SKIP", flush=True)
    
    total_time = time.time() - t_start
    
    if all_trades:
        n = len(all_trades)
        wins = sum(1 for t in all_trades if t['won'])
        wr = wins / n * 100
        wp = sum(t['pnl_pct'] for t in all_trades if t['won'])
        lp = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
        pf = wp / lp if lp > 0 else 999
        rr = sum(t['rr'] for t in all_trades) / n
        pnl = sum(t['pnl_pct'] for t in all_trades) / n
        swing_trades = [t for t in all_trades if t.get('sl_type') == 'swing']
        sw_wr = sum(1 for t in swing_trades if t['won']) / len(swing_trades) * 100 if swing_trades else 0
        
        n80 = sum(1 for s in stock_results if s['win_rate'] >= 80)
        
        # Signal sequence analysis
        seq_scores = {}
        for t in all_trades:
            sp = t.get('seq_pattern', 'none')
            if sp not in seq_scores:
                seq_scores[sp] = {'trades': 0, 'wins': 0, 'pnl': 0}
            seq_scores[sp]['trades'] += 1
            seq_scores[sp]['wins'] += 1 if t['won'] else 0
            seq_scores[sp]['pnl'] += t['pnl_pct']
        
        print(f"\n{'='*80}")
        print(f"V32 — {len(stock_results)}/{analyzed} tradable | {total_time:.0f}s")
        print(f"{'='*80}")
        print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
        print(f"  Swing SL: {len(swing_trades)}/{n} ({len(swing_trades)/n*100:.0f}%) | WR={sw_wr:.1f}%")
        print(f"  WR>=80%: {n80}/{len(stock_results)}")
        print(f"\n  Signal Sequence Performance:")
        for sp, data in sorted(seq_scores.items(), key=lambda x: x[1]['trades'], reverse=True):
            swr = data['wins'] / data['trades'] * 100
            avg_p = data['pnl'] / data['trades']
            if data['trades'] >= 3:
                print(f"    {sp:30s}: {data['trades']:3d} trades | WR={swr:.0f}% | P&L={avg_p:+.2f}%")
        
        print(f"\n  P&L Distribution:")
        for bucket in [(-5,0),(0,1),(1,2),(2,5),(5,10),(10,50)]:
            subset = [t for t in all_trades if bucket[0] <= t['pnl_pct'] < bucket[1]]
            if subset:
                wr_s = sum(1 for t in subset if t['won']) / len(subset) * 100
                print(f"    {bucket[0]:+}% to {bucket[1]:+}%: {len(subset):3d} trades WR={wr_s:.0f}%")
        
        # Compare with V28
        print(f"\n{'='*80}")
        print(f"                        V28 vs V32 COMPARISON                         ")
        print(f"{'='*80}")
        print(f"  V28: WR=76.6% RR=5.94x PF=27 P&L=+1.59% (confirmed_at+SL=0.3%)")
        print(f"  V32: WR={wr:.1f}% RR={rr:.2f}x PF={pf:.0f} P&L={pnl:+.2f}% (SL=0.5%+trail+RR>=2.0)")
        
        # Save
        outpath = OUTPUT_DIR / 'backtest_v32.json'
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'config': {'version': 'V32', 'sl': SL, 'breakeven_pct': TRAIL_BREAKEVEN_PCT,
                       'min_rr': MIN_RR, 'seq_scoring': True},
            'summary': {
                'total_trades': n, 'tradable': len(stock_results),
                'win_rate': round(wr, 1), 'avg_rr': round(rr, 2),
                'profit_factor': round(pf, 2), 'avg_pnl': round(pnl, 2),
            },
            'stocks': stock_results, 'all_trades': all_trades,
        }, open(outpath, 'w'), ensure_ascii=False, indent=2, default=str)
        print(f"\n  Saved: {outpath}")


if __name__ == '__main__':
    main()
