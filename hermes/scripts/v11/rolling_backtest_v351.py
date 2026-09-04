#!/usr/bin/env python3
"""
V35.1 — 紧SL(0.3%) + 延迟trailing + 多周期共振 + 4层信号评分

核心改进自V28:
  1. SL=0.3%(紧)维持高WR — 不变
  2. 删除0.2% breakeven — 这是1-bar退出的元凶
  3. 删除0.5% profit trail — 太激进
  4. 新增: +2.0%才启动trailing, trail=30%回撤
  5. 4层信号评分同V35 (POI+上下文+链+多周期)
"""
import json, sys, time
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Optional

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v35')
OUTPUT_DIR.mkdir(exist_ok=True)

# === V35.1 PARAMS ===
SL_FIXED = 0.3                      # same as V28 — tight, proven optimal
TRAIL_TRIGGER = 2.0                 # was never triggered before (BE at 0.2%)
TRAIL_RETRACE = 0.33                # trail at 33% retracement from peak
                                    # e.g. peak=+5%, trail at +3.35%
RENEWAL_HIGH_BARS = 120             # how long to track highest price

SWING_SL_CAP = 0.5
SWING_MAX_DIST = 20
MIN_VOL_RATIO = 0.7
MIN_FVG_GAP = 0.2
MIN_TRADES = 2
MIN_BARS = 120
ROLL_START = 60
ROLL_END_OFFSET = 10
MAX_HOLD = 120
COOLDOWN = 5

def load_ohlcv(symbol):
    fname = f"{symbol.replace('.','_')}_daily_300.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists(): return None
    data = json.loads(fpath.read_text())
    if not data or len(data) < MIN_BARS: return None
    for bar in data:
        if 'date' not in bar and 't' in bar: bar['date'] = str(bar['t'])
    return data

def synthesize_weekly(ohlcv):
    weekly = []
    for i in range(0, len(ohlcv), 5):
        chunk = ohlcv[i:i+5]
        if not chunk: continue
        weekly.append({
            'o': chunk[0]['o'], 'h': max(b['h'] for b in chunk),
            'l': min(b['l'] for b in chunk), 'c': chunk[-1]['c'],
        })
    return weekly

def weekly_trend(weekly, lookback=8):
    if len(weekly) < lookback: return 'neutral'
    seg = weekly[-lookback:]
    start, end = seg[0]['c'], seg[-1]['c']
    pct = (end - start) / start * 100
    green = sum(1 for b in seg if b['c'] > b['o'])
    if pct > 3 and green >= lookback * 0.6: return 'bull'
    if pct < -3 and green <= lookback * 0.4: return 'bear'
    return 'neutral'

def short_trend(ohlcv, idx, lookback=10):
    if idx < lookback: return 'neutral', 0.0, 0.0
    seg = ohlcv[idx-lookback:idx+1]
    start, end = seg[0]['c'], seg[-1]['c']
    pct = (end - start) / start * 100
    ema = sum(ohlcv[i]['c'] for i in range(max(0, idx-8), idx+1)) / min(9, idx+1)
    ed = (ohlcv[idx]['c'] - ema) / ema * 100
    return pct, ed

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

# ============================================================
# V35.1 TRAILING (延迟trailing, 不立刻breakeven)
# ============================================================
def calc_trailing_v35(ohlcv, entry_idx, entry_price, initial_sl, n, max_hold=120):
    """
    V35.1 trailing:
    - SL = 0.3% (tight, proven optimal)
    - NO breakeven at +0.2% (was causing 1-bar exits)
    - Trailing starts ONLY after +2.0% gain
    - After trigger: trail at 33% retracement from peak
    """
    sl = initial_sl
    highest = entry_price
    trailing_active = False
    exit_idx, exit_price, won = -1, None, False
    
    for j in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        bar = ohlcv[j]
        
        # Track highest price
        if bar['h'] > highest:
            highest = bar['h']
        
        gain_from_entry = (highest - entry_price) / entry_price * 100
        
        # Check if trailing trigger is hit
        if not trailing_active and gain_from_entry >= TRAIL_TRIGGER:
            trailing_active = True
        
        # If trailing is active, adjust SL
        if trailing_active:
            # Trail at TRAIL_RETRACE retracement from peak
            # e.g., peak=+5%, retrace=33% → trail at entry + 3.35%
            peak_value = highest
            trail_price = peak_value - (peak_value - entry_price) * TRAIL_RETRACE
            # Don't let SL go below entry (lock in profit)
            trail_price = max(trail_price, entry_price)
            sl = max(sl, trail_price)
        
        # Check for exit
        if bar['l'] <= sl:
            exit_idx = j
            exit_price = max(sl, bar['l'])
            won = exit_price >= entry_price
            break
        
        # Also check close
        if bar['c'] <= sl:
            exit_idx = j
            exit_price = bar['c']
            won = exit_price >= entry_price
            break
    
    if exit_idx == -1:
        exit_idx = min(entry_idx + max_hold, n - 1)
        exit_price = ohlcv[exit_idx]['c']
        won = exit_price >= entry_price
    
    return exit_idx, exit_price, won

# ============================================================
# V35.1 信号时序评分 (复用V35 4层架构)
# ============================================================
CORE_SIGNAL_TYPES = {'FVG', 'OB', 'Sweep', 'CHOCH'}
SIGNAL_CODES = {
    'FVG_Bull': 'F', 'FVG_Bear': 'f',
    'OB_Bull': 'O', 'OB_Bear': 'o',
    'SweepDown': 'S', 'SweepUp': 's',
    'CHOCH_Bull': 'C', 'CHOCH_Bear': 'c',
}

PATTERN_DB = {
    'CF': {'desc': 'CHOCH→FVG', 'bonus': 0.35},
    'FO': {'desc': 'FVG→OB', 'bonus': 0.30},
    'SF': {'desc': 'Sweep→FVG', 'bonus': 0.30},
    'FF': {'desc': 'FVG→FVG', 'bonus': 0.20},
    'SO': {'desc': 'Sweep→OB', 'bonus': 0.18},
    'OF': {'desc': 'OB→FVG', 'bonus': 0.18},
    'OFC': {'desc': 'OB→FVG→CHOCH', 'bonus': 0.45},
    'COF': {'desc': 'CHOCH→OB→FVG', 'bonus': 0.40},
    'SFF': {'desc': 'Sweep→FVG→FVG', 'bonus': 0.40},
    'CSF': {'desc': 'CHOCH→Sweep→FVG', 'bonus': 0.50},
    'OO': {'desc': 'OB→OB', 'bonus': 0.05},
    'SS': {'desc': 'Sweep→Sweep', 'bonus': -0.10},
}

def classify_signal_code(signal):
    stype = signal.get('type', '')
    for pattern, code in SIGNAL_CODES.items():
        if pattern in stype: return code
    if stype: return stype[0].upper()
    return '?'

def _is_core_signal(signal):
    stype = signal.get('type', '')
    return any(core in stype for core in CORE_SIGNAL_TYPES)

def score_signal_v35(all_signals, target_signal, ohlcv, weekly_trend_val, phase, entry_bar_idx):
    """
    V35.1 4层评分 — 在entry_bar_idx处评估
    
    Layer 1: POI — FVG lower是否被测试
    Layer 2: 价格上下文 — 趋势延续/回调/新鲜
    Layer 3: 链模式匹配
    Layer 4: 多周期共振
    """
    target_idx = target_signal.get('idx', 0)
    fvg_lower = target_signal.get('lower', 0)
    fvg_upper = target_signal.get('upper', 0)
    
    # Layer 1: POI分析(在entry_bar_idx之前)
    poi_tested = False
    test_bars = 0
    for i in range(target_idx + 1, entry_bar_idx):
        if i >= len(ohlcv): break
        bar = ohlcv[i]
        if fvg_lower > 0 and bar['l'] <= fvg_upper and bar['l'] >= fvg_lower * 0.998:
            poi_tested = True
            test_bars = i - target_idx
    
    # Layer 2: 价格上下文
    trend_10, ema_dist = short_trend(ohlcv, entry_bar_idx, 10)
    
    if poi_tested:
        context = 'poi_pullback'
        base_score = 0.65
        context_desc = 'POI回调'
    elif trend_10 > 0.5 and ema_dist > 0:
        context = 'trend_continuation'
        base_score = 0.55
        context_desc = '趋势延续'
    else:
        context = 'fresh'
        base_score = 0.50
        context_desc = '新鲜信号'
    
    # Layer 3: 链模式
    preceding = [s for s in all_signals 
                 if s.get('idx', 0) < entry_bar_idx
                 and s.get('idx', 0) >= entry_bar_idx - 30
                 and s.get('direction') == 'bull'
                 and _is_core_signal(s)]
    preceding.sort(key=lambda s: s.get('idx', 0))
    recent = preceding[-5:] if preceding else []
    chain_code = ''.join(classify_signal_code(s) for s in recent)
    
    pattern_bonus = 0.0
    matched_desc = ''
    for length in range(min(5, len(chain_code)), 1, -1):
        for start in range(len(chain_code) - length + 1):
            sub = chain_code[start:start+length]
            if sub in PATTERN_DB:
                pattern_bonus = PATTERN_DB[sub]['bonus']
                matched_desc = PATTERN_DB[sub]['desc']
                break
        if pattern_bonus != 0: break
    
    if not matched_desc:
        matched_desc = '孤立' if len(preceding) == 0 else f'链({chain_code[-3:]})'
    
    # Layer 4: 多周期共振
    resonance_bonus = 0.0
    if weekly_trend_val == 'bull' and context in ('trend_continuation', 'poi_pullback'):
        resonance_bonus = 0.15
    elif weekly_trend_val == 'bull':
        resonance_bonus = 0.05
    elif weekly_trend_val == 'bear':
        resonance_bonus = -0.10
    
    phase_bonus = 0.10 if phase == 'breakout' else (0.05 if phase == 'volatile' else 0.0)
    
    score = base_score + pattern_bonus + resonance_bonus + phase_bonus
    score = max(0.0, min(1.0, score))
    
    if score >= 0.75:
        grade = 'A'; entry_mult = 1.3
    elif score >= 0.60:
        grade = 'B'; entry_mult = 1.0
    elif score >= 0.50:
        grade = 'C'; entry_mult = 0.6
    else:
        grade = 'D'; entry_mult = 0.0
    
    return {
        'score': round(score, 3), 'grade': grade, 'entry_mult': entry_mult,
        'chain': chain_code[-6:], 'desc': context_desc, 'pattern': matched_desc,
        'context': context, 'poi_tested': poi_tested,
        'resonance': weekly_trend_val, 'phase': phase,
    }


def run_stock_v35(symbol):
    ohlcv = load_ohlcv(symbol)
    if not ohlcv: return None
    
    try:
        n = len(ohlcv)
        roll_end = n - ROLL_END_OFFSET
        phase = detect_market_phase(ohlcv)
        base = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
        all_signals = detect_all_signals_v11(ohlcv, params=base, tf='daily')['all']
        if not all_signals or len(all_signals) < 3: return None
        
        weekly = synthesize_weekly(ohlcv)
        wt = weekly_trend(weekly)
        
        trades = []
        entered_bar = -999
        swing_count, fixed_count = 0, 0
        context_stats = defaultdict(lambda: {'n': 0, 'wins': 0, 'pnl': 0.0, 'hold': 0.0})
        
        for i in range(ROLL_START, roll_end):
            if i - entered_bar < COOLDOWN: continue
            
            sigs_before = [s for s in all_signals if s.get('idx', 0) <= i]
            fvg_bull = [s for s in sigs_before if 'FVG_Bull' in s.get('type', '')]
            if not fvg_bull: continue
            
            sig = None
            for s in reversed(fvg_bull):
                s_conf = s.get('confirmed_at', s.get('idx', 0) + 1)
                if i >= s_conf: sig = s; break
            if sig is None: continue
            
            # V35.1 信号评分
            timing = score_signal_v35(all_signals, sig, ohlcv, wt, phase, i)
            if timing['grade'] in ('D',): continue
            if timing['grade'] == 'C' and timing['entry_mult'] < 0.5: continue
            
            # 成交量
            bar_vol = ohlcv[i].get('v', ohlcv[i].get('vol', 0))
            avg_vol = sum(ohlcv[j].get('v', ohlcv[j].get('vol', 0)) for j in range(max(0,i-30),i)) / 30
            if avg_vol > 0 and bar_vol < avg_vol * MIN_VOL_RATIO: continue
            
            # 阳线
            if ohlcv[i]['c'] <= ohlcv[i]['o']: continue
            
            # FVG gap
            upper = sig.get('upper', 0); lower = sig.get('lower', 0)
            if upper > 0 and lower > 0:
                if (upper - lower) / lower * 100 < MIN_FVG_GAP: continue
            
            entry_price = ohlcv[i]['c']
            
            # SL
            sl_info = find_best_swing_sl(ohlcv, i, entry_price)
            if sl_info is not None:
                init_sl = sl_info['sl_price']
                sl_type = 'swing'
            else:
                init_sl = entry_price * (1 - SL_FIXED / 100)
                sl_type = 'fixed'
            
            # V35.1 trailing (延迟trailing, 无breakeven)
            exit_idx, exit_price, won = calc_trailing_v35(
                ohlcv, i, entry_price, init_sl, n, MAX_HOLD)
            
            pnl = (exit_price - entry_price) / entry_price * 100
            risk = abs(entry_price - init_sl)
            actual_rr = abs(exit_price - entry_price) / risk if risk > 0 else 10
            
            trade = {
                'entry_idx': i, 'exit_idx': exit_idx,
                'entry_price': round(entry_price, 2),
                'exit_price': round(exit_price, 2),
                'sl': round(init_sl, 2),
                'pnl_pct': round(pnl, 2),
                'won': won, 'rr': round(actual_rr, 2),
                'hold_bars': exit_idx - i,
                'sl_type': sl_type,
                'v35_score': timing['score'],
                'v35_grade': timing['grade'],
                'v35_chain': timing['chain'],
                'v35_desc': timing['desc'],
                'v35_context': timing['context'],
                'pattern': timing['pattern'],
                'poi_tested': timing['poi_tested'],
                'resonance': timing['resonance'],
                'phase': phase,
            }
            trades.append(trade)
            
            ctx = timing['context']
            context_stats[ctx]['n'] += 1
            context_stats[ctx]['wins'] += 1 if won else 0
            context_stats[ctx]['pnl'] += pnl
            context_stats[ctx]['hold'] += exit_idx - i
            
            entered_bar = i
            if sl_type == 'swing': swing_count += 1
            else: fixed_count += 1
        
        if len(trades) < MIN_TRADES: return None
        
        wins = sum(1 for t in trades if t['won'])
        wr = wins / len(trades) * 100
        win_pnl = sum(t['pnl_pct'] for t in trades if t['won'])
        loss_pnl = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
        pf = win_pnl / loss_pnl if loss_pnl > 0 else 999
        avg_rr = sum(t['rr'] for t in trades) / len(trades)
        avg_pnl = sum(t['pnl_pct'] for t in trades) / len(trades)
        avg_hold = sum(t['hold_bars'] for t in trades) / len(trades)
        
        return {
            'trades': trades,
            'perf': {
                'symbol': symbol,
                'n_trades': len(trades), 'wins': wins, 'losses': len(trades)-wins,
                'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
                'profit_factor': round(pf, 1) if pf < 999 else 999,
                'avg_pnl': round(avg_pnl, 2),
                'avg_hold': round(avg_hold, 1),
                'swing_sl_pct': round(swing_count/len(trades)*100, 1),
                'phase': phase,
                'avg_v35_score': round(sum(t['v35_score'] for t in trades)/len(trades), 2),
            },
            'context_stats': dict(context_stats),
        }
    except Exception as e:
        return None


def main():
    symbols = sorted([f.stem.replace('_daily_300','').replace('_','.') 
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print(f"V35.1 — 紧SL(0.3%) + 延迟trailing(+2%触发) + 4层评分 + 多周期共振")
    print(f"  关键改进: 删除0.2% breakeven, +2%后才启动trailing(33%回撤)")
    print(f"{'='*80}")
    
    all_trades, stock_results = [], []
    all_context = defaultdict(lambda: {'n': 0, 'wins': 0, 'pnl': 0.0, 'hold': 0.0})
    t_start = time.time()
    
    for idx, sym in enumerate(symbols[:200]):
        result = run_stock_v35(sym)
        if result:
            p = result['perf']
            all_trades.extend(result['trades'])
            stock_results.append(p)
            for ctx, data in result.get('context_stats', {}).items():
                all_context[ctx]['n'] += data['n']
                all_context[ctx]['wins'] += data['wins']
                all_context[ctx]['pnl'] += data['pnl']
                all_context[ctx]['hold'] += data['hold']
            print(f"  [{idx+1:3d}/200] {sym:12s} n={p['n_trades']:2d} "
                  f"WR={p['win_rate']:.0f}% hold={p['avg_hold']:.1f} "
                  f"RR={p['avg_rr']:.1f}x PF={p['profit_factor']:.0f}", flush=True)
        else:
            print(f"  [{idx+1:3d}/200] {sym:12s} SKIP", flush=True)
    
    total_time = time.time() - t_start
    
    if not all_trades:
        print("No trades!")
        return
    
    n = len(all_trades)
    wins = sum(1 for t in all_trades if t['won'])
    wr = wins / n * 100
    win_pnl = sum(t['pnl_pct'] for t in all_trades if t['won'])
    loss_pnl = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
    pf = win_pnl / loss_pnl if loss_pnl > 0 else 999
    avg_rr = sum(t['rr'] for t in all_trades) / n
    avg_pnl = sum(t['pnl_pct'] for t in all_trades) / n
    avg_hold = sum(t['hold_bars'] for t in all_trades) / n
    swing_trades = [t for t in all_trades if t.get('sl_type') == 'swing']
    sw_wr = sum(1 for t in swing_trades if t['won']) / len(swing_trades) * 100 if swing_trades else 0
    
    print(f"\n{'='*80}")
    print(f"V35.1 — {len(stock_results)}/{200} tradable | {total_time:.0f}s")
    print(f"{'='*80}")
    print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {avg_rr:.2f}x | PF: {pf:.0f} | P&L: {avg_pnl:+.2f}%")
    print(f"  Avg hold: {avg_hold:.1f} bars | Swing SL: {len(swing_trades)}/{n} ({len(swing_trades)/n*100:.0f}%)")
    print(f"  WR>=80%: {sum(1 for s in stock_results if s['win_rate']>=80)}/{len(stock_results)}")
    
    # Hold distribution
    hold_dist = {}
    for t in all_trades:
        h = t['hold_bars']
        hold_dist[h] = hold_dist.get(h, 0) + 1
    print(f"\n  Hold bars:")
    for h in sorted(hold_dist.keys()):
        print(f"    {h:3d} bars: {hold_dist[h]:4d} ({hold_dist[h]/n*100:.1f}%)")
    
    print(f"\n  Context breakdown:")
    for ctx, data in sorted(all_context.items(), key=lambda x: x[1]['n'], reverse=True):
        cwr = data['wins'] / data['n'] * 100
        apnl = data['pnl'] / data['n']
        ahold = data['hold'] / data['n']
        print(f"    {ctx:25s}: {data['n']:4d} trades | WR={cwr:.1f}% | P&L={apnl:+.2f}% | hold={ahold:.1f}")
    
    print(f"\n  P&L:")
    for b in [(-5,0),(0,0.5),(0.5,1),(1,2),(2,5),(5,10),(10,50)]:
        subset = [t for t in all_trades if b[0] <= t['pnl_pct'] < b[1]]
        if subset:
            print(f"    {b[0]:+}% to {b[1]:+}%: {len(subset):3d} | "
                  f"RR>=2: {sum(1 for t in subset if t['rr']>=2):3d}")
    
    good = [t for t in all_trades if t['rr'] >= 2.0]
    gw = sum(1 for t in good if t['won'])/len(good)*100 if good else 0
    print(f"\n  RR>=2.0: {len(good)}/{n} trades | WR={gw:.1f}% | "
          f"P&L={sum(t['pnl_pct'] for t in good)/len(good):+.2f}%")
    
    print(f"\n{'='*80}")
    print(f"                    VERSION COMPARISON")
    print(f"{'='*80}")
    print(f"  V28: WR=76.6% RR=5.94x PF=27 P&L=+1.59% (1-bar holds, tight trail)")
    print(f"  V34: WR=71.9% RR=5.10x PF=26 P&L=+1.54% (POI+context, tight trail)")
    print(f"  V35: WR=36.1% RR=2.12x PF=2  P&L=+0.50% (fixed SL/TP, multi-bar)")
    print(f"V35.1: WR={wr:.1f}% RR={avg_rr:.2f}x PF={pf:.0f} P&L={avg_pnl:+.2f}% "
          f"(delayed trail, 4-layer)")
    
    # Save
    outpath = OUTPUT_DIR / 'backtest_v351.json'
    json.dump({
        'timestamp': datetime.now().isoformat(),
        'config': {'version': 'V35.1', 'sl': '0.3', 'trail_trigger': '2.0%', 'trail_retrace': '33%'},
        'summary': {
            'total_trades': n, 'tradable': len(stock_results),
            'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
            'profit_factor': round(pf, 2), 'avg_pnl': round(avg_pnl, 2),
            'avg_hold': round(avg_hold, 1),
        },
        'stocks': stock_results, 'all_trades': all_trades,
    }, open(outpath, 'w'), ensure_ascii=False, indent=2, default=str)
    print(f"\n  Saved: {outpath}")

if __name__ == '__main__':
    main()
