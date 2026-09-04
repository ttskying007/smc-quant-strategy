#!/usr/bin/env python3
"""
V25.5 Market State Detection + Adaptive Parameters
Classifies each stock at entry time and applies state-adaptive SL/TP/hold/trail.

State detection uses:
  ADX(14) — trend strength
  ATR(14)/price% — volatility
  MA20 position & slope — trend direction
  Recent swing structure — range detection

Adaptive params per state:
  TREND_UP/DOWN: tighter SL, wider TP, longer hold, early trail
  RANGE:         wider SL, closer TP, shorter hold, late trail
  HIGH_VOL:      widest SL, closest TP, shortest hold
  LOW_VOL:       tightest SL, moderate TP, longest hold
"""
import json, sys
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Tuple

sys.path.insert(0, '/root/.hermes/scripts')

# ── State-Adaptive Parameters ──

STATE_PARAMS = {
    'TREND_UP': {
        'sl_atr_mult': 0.4,      # Tighter SL (trend is friend)
        'tp_atr_mult': 2.0,      # Wider TP (let winners run)
        'max_hold': 60,           # Longer hold
        'trail_activate_r': 0.8, # Early trail activation
        'trail_buffer_atr': 0.3,
        'min_rr': 0.7,
    },
    'TREND_DOWN': {
        'sl_atr_mult': 0.4,
        'tp_atr_mult': 2.0,
        'max_hold': 60,
        'trail_activate_r': 0.8,
        'trail_buffer_atr': 0.3,
        'min_rr': 0.7,
    },
    'RANGE': {
        'sl_atr_mult': 0.7,      # Wider SL (avoid whipsaws)
        'tp_atr_mult': 1.3,      # Closer TP (mean reversion)
        'max_hold': 30,           # Shorter hold
        'trail_activate_r': 1.5, # Late trail activation
        'trail_buffer_atr': 0.5,
        'min_rr': 0.6,
    },
    'HIGH_VOL': {
        'sl_atr_mult': 0.8,      # Widest SL
        'tp_atr_mult': 1.5,
        'max_hold': 20,           # Shortest hold
        'trail_activate_r': 1.2,
        'trail_buffer_atr': 0.6,
        'min_rr': 0.5,
    },
    'LOW_VOL': {
        'sl_atr_mult': 0.3,      # Tightest SL
        'tp_atr_mult': 1.5,
        'max_hold': 90,           # Longest hold
        'trail_activate_r': 0.7,
        'trail_buffer_atr': 0.2,
        'min_rr': 0.8,
    },
}


def compute_adx(klines, period=14, idx=None):
    """Compute ADX at given index."""
    if idx is None: idx = len(klines) - 1
    if idx < period * 2: return 0
    
    trs = []; plus_dms = []; minus_dms = []
    
    for i in range(idx - period * 2 + 1, idx + 1):
        b, pb = klines[i], klines[i-1]
        h, l = float(b.get('h',0)), float(b.get('l',0))
        ph, pl = float(pb.get('h',0)), float(pb.get('l',0))
        pc = float(pb.get('c',0))
        
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
        
        up_move = h - ph if h > ph else 0
        down_move = pl - l if l < pl else 0
        
        if up_move > down_move and up_move > 0:
            plus_dm = up_move
        else:
            plus_dm = 0
            
        if down_move > up_move and down_move > 0:
            minus_dm = down_move
        else:
            minus_dm = 0
        
        plus_dms.append(plus_dm)
        minus_dms.append(minus_dm)
    
    # Smooth with Wilder's method
    atr = sum(trs[:period]) / period
    smoothed_plus = sum(plus_dms[:period]) / period
    smoothed_minus = sum(minus_dms[:period]) / period
    
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
        smoothed_plus = (smoothed_plus * (period - 1) + plus_dms[i]) / period
        smoothed_minus = (smoothed_minus * (period - 1) + minus_dms[i]) / period
    
    if atr == 0: return 0
    
    plus_di = smoothed_plus / atr * 100
    minus_di = smoothed_minus / atr * 100
    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0
    
    return dx


def detect_market_state(klines, entry_idx):
    """
    Detect market state at entry time.
    
    Returns: {
        'state': 'TREND_UP'|'TREND_DOWN'|'RANGE'|'HIGH_VOL'|'LOW_VOL',
        'adx': float, 'atr_pct': float, 'ma20_pct': float, 'ma_slope': float,
        'params': {...adaptive params...}
    }
    """
    if entry_idx < 40:
        return {'state': 'RANGE', 'params': STATE_PARAMS['RANGE']}
    
    # Compute indicators
    closes = [float(b.get('c', 0)) for b in klines[max(0, entry_idx-20):entry_idx+1]]
    if not closes or closes[-1] == 0:
        return {'state': 'RANGE', 'params': STATE_PARAMS['RANGE']}
    
    current = closes[-1]
    ma20 = sum(closes) / len(closes)
    pct_from_ma = (current - ma20) / ma20 * 100 if ma20 > 0 else 0
    
    # MA slope (5-period)
    if len(closes) >= 5:
        ma_slope = (closes[-1] - closes[-5]) / max(abs(closes[-5]), 0.01) * 100
    else:
        ma_slope = 0
    
    # ATR%
    atr = 0
    trs = []
    for i in range(max(14, entry_idx-14), entry_idx+1):
        if i < 1 or i >= len(klines): continue
        b, pb = klines[i], klines[i-1]
        h = float(b.get('h',0)); l = float(b.get('l',0))
        pc = float(pb.get('c',0))
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    atr = sum(trs)/len(trs) if trs else 0
    atr_pct = (atr / current * 100) if current > 0 and atr > 0 else 0
    
    # ADX
    adx = compute_adx(klines, 14, entry_idx)
    
    # ── Classification ──
    details = {'adx': round(adx, 1), 'atr_pct': round(atr_pct, 2),
               'ma20_pct': round(pct_from_ma, 1), 'ma_slope': round(ma_slope, 1)}
    
    # Priority: volatility first
    if atr_pct > 5:
        return {'state': 'HIGH_VOL', **details, 'params': STATE_PARAMS['HIGH_VOL']}
    if atr_pct < 1.5 and adx < 20:
        return {'state': 'LOW_VOL', **details, 'params': STATE_PARAMS['LOW_VOL']}
    
    # Range detection
    if adx < 20:
        return {'state': 'RANGE', **details, 'params': STATE_PARAMS['RANGE']}
    
    # Trending
    if pct_from_ma > 1 and ma_slope > 0.5:
        return {'state': 'TREND_UP', **details, 'params': STATE_PARAMS['TREND_UP']}
    elif pct_from_ma < -1 and ma_slope < -0.5:
        return {'state': 'TREND_DOWN', **details, 'params': STATE_PARAMS['TREND_DOWN']}
    
    # Default: weak trend or range
    if adx >= 20:
        return {'state': 'TREND_UP' if pct_from_ma > 0 else 'TREND_DOWN', 
                **details, 'params': STATE_PARAMS['TREND_UP' if pct_from_ma > 0 else 'TREND_DOWN']}
    
    return {'state': 'RANGE', **details, 'params': STATE_PARAMS['RANGE']}


def apply_state_params(pick, klines, state_info):
    """Apply state-adaptive SL/TP/hold to a pick."""
    params = state_info['params']
    entry_date = str(pick.get('entry_date', ''))
    
    # Find entry
    entry_idx = None
    for i, b in enumerate(klines):
        if str(b.get('t', b.get('date', ''))) == entry_date:
            entry_idx = i
            break
    if entry_idx is None:
        entry_idx = pick.get('entry_idx', len(klines)-1)
    
    entry_price = pick.get('price', pick.get('entry_price', float(klines[entry_idx].get('c',0))))
    
    # ATR
    atr = 0
    trs = []
    for i in range(max(14, entry_idx-14), entry_idx+1):
        if i < 1 or i >= len(klines): continue
        b, pb = klines[i], klines[i-1]
        h, l = float(b.get('h',0)), float(b.get('l',0))
        pc = float(pb.get('c',0))
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    atr = sum(trs)/len(trs) if trs else entry_price * 0.02
    
    # Zone
    dz_low = pick.get('v25_zone_bottom', pick.get('dz_low', entry_price*0.95))
    
    # ── Adaptive SL/TP ──
    sl_price = dz_low - atr * params['sl_atr_mult']
    sl_pct = abs(entry_price - sl_price) / entry_price * 100
    
    # TP: structural + ATR adjustment
    highs = sorted(set(round(float(klines[j].get('h', 0)), 2)
                       for j in range(max(0, entry_idx-60), min(entry_idx+5, len(klines)))
                       if float(klines[j].get('h', 0)) > entry_price * 1.03))
    
    if len(highs) >= 2:
        tp1_price = highs[1]
    elif len(highs) == 1:
        tp1_price = highs[0]
    else:
        tp1_price = entry_price * (1 + atr/entry_price * params['tp_atr_mult'])
    
    tp1_pct = (tp1_price - entry_price) / entry_price * 100
    
    return {
        'sl_price': round(sl_price, 2),
        'sl_pct': round(sl_pct, 2),
        'tp1_price': round(tp1_price, 2),
        'tp1_pct': round(tp1_pct, 1),
        'rr': round(tp1_pct / sl_pct, 2) if sl_pct > 0 else 0,
        'max_hold': params['max_hold'],
        'trail_activate_r': params['trail_activate_r'],
        'trail_buffer_atr': params['trail_buffer_atr'],
        'atr': round(atr, 2),
        'state': state_info['state'],
    }


def simulate_state_adaptive(pick, params, klines):
    """Simulate exit with state-adaptive parameters."""
    entry_date = str(pick.get('entry_date', ''))
    entry_idx = None
    for i, b in enumerate(klines):
        if str(b.get('t', b.get('date', ''))) == entry_date:
            entry_idx = i
            break
    if entry_idx is None:
        entry_idx = pick.get('entry_idx', len(klines)-1)
    
    entry_price = pick.get('price', pick.get('entry_price', float(klines[entry_idx].get('c',0))))
    sl_price = params['sl_price']
    tp_price = params['tp1_price']
    max_hold = params['max_hold']
    trail_r = params['trail_activate_r']
    trail_buf = params['trail_buffer_atr'] * params['atr']
    
    trail_active = False
    trail_level = None
    highest = entry_price
    
    exit_idx = entry_idx
    exit_price = entry_price
    exit_reason = 'timeout'
    
    for i in range(entry_idx + 1, min(entry_idx + max_hold + 1, len(klines))):
        bar = klines[i]
        lo = float(bar.get('l', 0))
        hi = float(bar.get('h', 0))
        cl = float(bar.get('c', 0))
        if lo <= 0: continue
        
        if hi > highest: highest = hi
        
        # Trail activation
        r_multiple = (highest - entry_price) / (entry_price - sl_price) if entry_price > sl_price else 0
        if not trail_active and r_multiple >= trail_r:
            trail_active = True
            trail_level = highest - trail_buf
        
        if trail_active:
            trail_level = max(trail_level or 0, highest - trail_buf)
        
        effective_sl = trail_level if trail_active else sl_price
        
        if hi >= tp_price:
            exit_idx = i; exit_price = tp_price
            exit_reason = 'TP_hit'; break
        if lo <= effective_sl:
            exit_idx = i; exit_price = effective_sl
            exit_reason = 'trailing' if trail_active else 'SL_hit'; break
    
    pnl_pct = (exit_price - entry_price) / entry_price * 100
    
    return {
        'symbol': pick['symbol'],
        'entry_bar': int(entry_idx), 'exit_bar': int(exit_idx),
        'entry_price': round(entry_price, 2), 'exit_price': round(exit_price, 2),
        'exit_reason': exit_reason,
        'pnl_pct': round(pnl_pct, 2), 'hold_bars': int(exit_idx - entry_idx),
        'won': pnl_pct > 0,
        'sl_price': params['sl_price'], 'tp_price': params['tp1_price'],
        'sl_pct': params['sl_pct'], 'tp_pct': params['tp1_pct'],
        'rr': params['rr'],
        'trail_activated': trail_active,
        'market_state': params['state'],
        'zone_type': pick.get('zone_type', ''),
        'conf_type': pick.get('conf_type', ''),
        'ctx_seq': pick.get('ctx_seq', ''),
    }


def run_state_backtest():
    """Run backtest with state-adaptive parameters."""
    import os
    from collections import Counter
    
    kline_dir = Path('/root/.hermes/kline_cache')
    picks_path = Path('/root/.hermes/smc_opt_v25/v25_picks.json')
    
    picks = json.loads(picks_path.read_text())
    print(f"State-adaptive backtest: {len(picks)} picks")
    
    trades = []
    state_counts = Counter()
    skipped = 0
    
    for i, p in enumerate(picks):
        sym = p['symbol']
        parts = sym.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ')
        kpath = kline_dir / f'{parts}_daily_300.json'
        if not kpath.exists():
            skipped += 1; continue
        
        klines = json.loads(kpath.read_text())
        for b in klines:
            for k in ('o','h','l','c'):
                if k in b: b[k] = float(b[k])
        
        entry_date = str(p.get('entry_date', ''))
        entry_idx = None
        for j, b in enumerate(klines):
            if str(b.get('t', b.get('date', ''))) == entry_date:
                entry_idx = j; break
        if entry_idx is None:
            entry_idx = p.get('entry_idx', len(klines)-1)
        
        # Detect state
        state = detect_market_state(klines, entry_idx)
        state_counts[state['state']] += 1
        
        # Skip RANGE state entirely — kills performance (44% WR in backtest)
        if state['state'] == 'RANGE':
            continue
        
        # Apply adaptive params
        params = apply_state_params(p, klines, state)
        if params['rr'] < 0.5:
            continue
        
        # Simulate
        result = simulate_state_adaptive(p, params, klines)
        if result:
            trades.append(result)
        
        if (i+1) % 100 == 0:
            print(f"  {i+1}/{len(picks)}...")
    
    # ── Stats ──
    n = len(trades)
    won = sum(1 for t in trades if t['won'])
    wr = won/n*100 if n > 0 else 0
    avg_pnl = sum(t['pnl_pct'] for t in trades)/n if n > 0 else 0
    exits = Counter(t['exit_reason'] for t in trades)
    
    print(f"\n═══ V25.5 State-Adaptive Backtest ═══")
    print(f"  Trades: {n}  WR: {wr:.1f}%  Avg PnL: {avg_pnl:+.2f}%")
    print(f"  Total PnL: {sum(t['pnl_pct'] for t in trades):+.2f}%")
    print(f"  Avg Win: {sum(t['pnl_pct'] for t in trades if t['won'])/max(won,1):+.2f}%")
    print(f"  Avg Loss: {sum(t['pnl_pct'] for t in trades if not t['won'])/max(n-won,1):+.2f}%")
    
    print(f"\n  Exit: TP={exits.get('TP_hit',0)}({exits.get('TP_hit',0)/n*100:.0f}%) "
          f"SL={exits.get('SL_hit',0)}({exits.get('SL_hit',0)/n*100:.0f}%) "
          f"Trail={exits.get('trailing',0)}({exits.get('trailing',0)/n*100:.0f}%)")
    
    print(f"\n  Market states used:")
    for state in ['TREND_UP','TREND_DOWN','RANGE','HIGH_VOL','LOW_VOL']:
        ts = [t for t in trades if t['market_state'] == state]
        if not ts: continue
        twr = sum(1 for t in ts if t['won'])/len(ts)*100
        tpnl = sum(t['pnl_pct'] for t in ts)/len(ts)
        print(f"    {state:12s}: {len(ts):4d} WR={twr:.1f}% avgP={tpnl:+.2f}%")
    
    # Save
    out = Path('/root/.hermes/smc_opt_v25/v255_trades.json')
    out.write_text(json.dumps(trades, ensure_ascii=False, indent=2))
    print(f"\nSaved: {out}")
    
    return trades


if __name__ == '__main__':
    run_state_backtest()
