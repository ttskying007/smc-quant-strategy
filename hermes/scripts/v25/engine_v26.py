#!/usr/bin/env python3
"""
V25.6 Engine — RR Floor + Multi-Tier TP + Delayed Trail
Fixes 3 core issues found in V25.5 backtest analysis:
  1. 74/300 trades RR<1.0 (negative EV) → min RR ≥ 1.2
  2. avgP only +1.68% (TP too close, trail too early) → 3rd high TP + delayed trail
  3. 37 winners in 0-1% range → multi-tier: 50% TP1 close + 50% trail
"""
import json, sys
from pathlib import Path
from collections import Counter, defaultdict
sys.path.insert(0, '/root/.hermes/scripts')

KLINE_DIR = Path('/root/.hermes/kline_cache')
PICKS_PATH = Path('/root/.hermes/smc_opt_v25/v25_picks.json')
OUT_DIR = Path('/root/.hermes/smc_opt_v25')

# ── V25.6 State-Adaptive Parameters ──
STATE_PARAMS = {
    'TREND_UP': {
        'sl_atr_mult': 0.4,        # Tighter SL (trend is friend)
        'tp_atr_mult': 2.5,        # Wider TP (let winners run)
        'max_hold': 60,
        'trail_activate_r': 1.5,   # DELAYED: was 0.8R → 1.5R
        'trail_buffer_atr': 0.3,
        'min_rr': 1.2,             # RR floor
    },
    'TREND_DOWN': {
        'sl_atr_mult': 0.4,
        'tp_atr_mult': 2.5,
        'max_hold': 60,
        'trail_activate_r': 1.5,
        'trail_buffer_atr': 0.3,
        'min_rr': 1.2,
    },
    'HIGH_VOL': {
        'sl_atr_mult': 0.7,        # Slightly tighter than V25.5 (was 0.8)
        'tp_atr_mult': 2.0,
        'max_hold': 25,
        'trail_activate_r': 1.2,
        'trail_buffer_atr': 0.5,
        'min_rr': 1.0,             # Lower floor for high vol
    },
    'LOW_VOL': {
        'sl_atr_mult': 0.3,
        'tp_atr_mult': 1.8,
        'max_hold': 90,
        'trail_activate_r': 1.0,
        'trail_buffer_atr': 0.2,
        'min_rr': 1.2,
    },
}

def load_kline(symbol):
    parts = symbol.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ')
    path = KLINE_DIR / f'{parts}_daily_300.json'
    if path.exists():
        data = json.loads(path.read_text())
        for b in data:
            for k in ('o', 'h', 'l', 'c'):
                if k in b: b[k] = float(b[k])
        return data
    return []

def compute_atr(klines, period, idx):
    if idx < period: return 0
    trs = []
    for i in range(idx-period+1, idx+1):
        b, pb = klines[i], klines[i-1]
        h, l = float(b.get('h',0)), float(b.get('l',0))
        pc = float(pb.get('c',0))
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs)/len(trs) if trs else 0

def compute_adx(klines, period=14, idx=None):
    if idx is None: idx = len(klines) - 1
    if idx < period * 2: return 0
    trs = []; plus_dms = []; minus_dms = []
    for i in range(idx - period * 2 + 1, idx + 1):
        b, pb = klines[i], klines[i-1]
        h, l = float(b.get('h',0)), float(b.get('l',0))
        ph, pl = float(pb.get('h',0)), float(pb.get('l',0))
        pc = float(pb.get('c',0))
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
        up_move = h - ph if h > ph else 0
        down_move = pl - l if l < pl else 0
        plus_dms.append(up_move if up_move > down_move and up_move > 0 else 0)
        minus_dms.append(down_move if down_move > up_move and down_move > 0 else 0)
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
    if entry_idx < 40:
        return {'state': 'RANGE', 'params': STATE_PARAMS['TREND_UP']}
    closes = [float(b.get('c', 0)) for b in klines[max(0, entry_idx-20):entry_idx+1]]
    if not closes or closes[-1] == 0:
        return {'state': 'RANGE', 'params': STATE_PARAMS['TREND_UP']}
    current = closes[-1]
    ma20 = sum(closes) / len(closes)
    pct_from_ma = (current - ma20) / ma20 * 100 if ma20 > 0 else 0
    if len(closes) >= 5:
        ma_slope = (closes[-1] - closes[-5]) / max(abs(closes[-5]), 0.01) * 100
    else:
        ma_slope = 0
    atr = compute_atr(klines, 14, entry_idx)
    atr_pct = (atr / current * 100) if current > 0 and atr > 0 else 0
    adx = compute_adx(klines, 14, entry_idx)
    details = {'adx': round(adx, 1), 'atr_pct': round(atr_pct, 2),
               'ma20_pct': round(pct_from_ma, 1), 'ma_slope': round(ma_slope, 1)}
    if atr_pct > 5:
        return {'state': 'HIGH_VOL', **details, 'params': STATE_PARAMS['HIGH_VOL']}
    if atr_pct < 1.5 and adx < 20:
        return {'state': 'LOW_VOL', **details, 'params': STATE_PARAMS['LOW_VOL']}
    if adx < 20:
        return {'state': 'RANGE', **details, 'params': STATE_PARAMS['TREND_UP']}
    if pct_from_ma > 1 and ma_slope > 0.5:
        return {'state': 'TREND_UP', **details, 'params': STATE_PARAMS['TREND_UP']}
    elif pct_from_ma < -1 and ma_slope < -0.5:
        return {'state': 'TREND_DOWN', **details, 'params': STATE_PARAMS['TREND_DOWN']}
    if adx >= 20:
        return {'state': 'TREND_UP' if pct_from_ma > 0 else 'TREND_DOWN',
                **details, 'params': STATE_PARAMS['TREND_UP' if pct_from_ma > 0 else 'TREND_DOWN']}
    return {'state': 'RANGE', **details, 'params': STATE_PARAMS['TREND_UP']}

def compute_sltp(pick, klines, entry_idx, entry_price, atr, zone_lo):
    """Compute multi-tier SL/TP with state-adaptive params + RR floor."""
    state = detect_market_state(klines, entry_idx)
    params = state['params']
    
    # ── SL: zone_bottom - ATR × sl_mult ──
    sl_price = zone_lo - atr * params['sl_atr_mult']
    
    # Phase 0 Fix: Hard floor SL must be below zone_low by at least 0.5%
    hard_floor_sl = zone_lo * 0.995
    sl_price = max(sl_price, hard_floor_sl)
    
    # Final check: ensure SL is below zone_low
    if sl_price >= zone_lo:
        sl_price = zone_lo * 0.995
    
    sl_pct = abs(entry_price - sl_price) / entry_price * 100
    
    # ── TP: 3rd structural high for wider target ──
    highs = sorted(set(round(float(klines[j].get('h', 0)), 2)
                       for j in range(max(0, entry_idx-60), min(entry_idx+5, len(klines)))
                       if float(klines[j].get('h', 0)) > entry_price * 1.03))
    
    if len(highs) >= 3:
        tp2_price = highs[2]   # 3rd high for trail portion
        tp1_price = highs[1]   # 2nd high for close portion
    elif len(highs) == 2:
        tp1_price = highs[1]
        tp2_price = highs[1] * 1.05  # Extend
    elif len(highs) == 1:
        tp1_price = highs[0]
        tp2_price = highs[0] * 1.05
    else:
        tp1_price = entry_price * (1 + atr/entry_price * params['tp_atr_mult'])
        tp2_price = tp1_price * 1.05
    
    tp1_pct = (tp1_price - entry_price) / entry_price * 100
    tp2_pct = (tp2_price - entry_price) / entry_price * 100
    rr = tp1_pct / sl_pct if sl_pct > 0 else 0
    
    return {
        'sl_price': round(sl_price, 2),
        'sl_pct': round(sl_pct, 2),
        'tp1_price': round(tp1_price, 2),
        'tp1_pct': round(tp1_pct, 1),
        'tp2_price': round(tp2_price, 2),
        'tp2_pct': round(tp2_pct, 1),
        'rr': round(rr, 2),
        'atr': round(atr, 2),
        'state': state['state'],
        'params': params,
    }

def simulate_exit(pick, sltp, klines):
    """Simulate exit with multi-tier TP (50% close + 50% trail)."""
    entry_date = str(pick.get('entry_date', ''))
    entry_idx = None
    for i, b in enumerate(klines):
        if str(b.get('t', b.get('date', ''))) == entry_date:
            entry_idx = i; break
    if entry_idx is None:
        entry_idx = pick.get('entry_idx', len(klines)-1)
    
    entry_price = pick.get('price', pick.get('entry_price', float(klines[entry_idx].get('c', 0))))
    sl_price = sltp['sl_price']
    tp1_price = sltp['tp1_price']
    tp2_price = sltp['tp2_price']
    params = sltp['params']
    
    max_hold = params['max_hold']
    trail_r = params['trail_activate_r']
    trail_buf = params['trail_buffer_atr'] * sltp['atr']
    
    trail_active = False
    trail_level = None
    highest = entry_price
    tp1_hit = False
    tp1_exit_price = None
    
    exit_idx = entry_idx
    exit_price = entry_price
    exit_reason = 'timeout'
    
    for i in range(entry_idx + 1, min(entry_idx + max_hold + 1, len(klines))):
        bar = klines[i]
        lo = float(bar.get('l', 0))
        hi = float(bar.get('h', 0))
        cl = float(bar.get('c', 0))
        if lo <= 0: continue
        
        if hi > highest:
            highest = hi
        
        # ── TP1 hit: close 50%, rest trails ──
        if not tp1_hit and hi >= tp1_price:
            tp1_hit = True
            tp1_exit_price = tp1_price
            # Activate trail for remaining 50%
            trail_active = True
            trail_level = tp1_price - trail_buf
            # Continue (don't break — let remaining portion trail)
            continue
        
        # ── TP2 hit (trail portion) ──
        if tp1_hit and hi >= tp2_price:
            exit_idx = i
            exit_price = 0.5 * tp1_exit_price + 0.5 * tp2_price  # Blended
            exit_reason = 'TP2_hit'
            break
        
        # ── Trail activation (if not already from TP1) ──
        r_multiple = (highest - entry_price) / (entry_price - sl_price) if entry_price > sl_price else 0
        if not trail_active and r_multiple >= trail_r:
            trail_active = True
            trail_level = highest - trail_buf
        
        if trail_active:
            trail_level = max(trail_level or 0, highest - trail_buf)
        
        effective_sl = trail_level if trail_active else sl_price
        
        if lo <= effective_sl:
            exit_idx = i
            if tp1_hit:
                # TP1 portion was closed at TP1, trail portion at trail level
                exit_price = 0.5 * tp1_exit_price + 0.5 * effective_sl
                exit_reason = 'multi_exit'
            else:
                exit_price = effective_sl
                exit_reason = 'trailing' if trail_active else 'SL_hit'
            break
    
    # If timed out with TP1 hit but no exit
    if exit_reason == 'timeout' and tp1_hit:
        exit_price = 0.5 * tp1_exit_price + 0.5 * float(klines[-1]['c'])
        exit_reason = 'timeout_partial'
    
    pnl_pct = (exit_price - entry_price) / entry_price * 100
    
    return {
        'symbol': pick['symbol'],
        'entry_bar': int(entry_idx), 'exit_bar': int(exit_idx),
        'entry_price': round(entry_price, 2), 'exit_price': round(exit_price, 2),
        'exit_reason': exit_reason,
        'pnl_pct': round(pnl_pct, 2), 'hold_bars': int(exit_idx - entry_idx),
        'won': pnl_pct > 0,
        'sl_price': sltp['sl_price'], 'tp_price': tp1_price,
        'sl_pct': sltp['sl_pct'], 'tp_pct': sltp['tp1_pct'],
        'rr': sltp['rr'],
        'trail_activated': trail_active,
        'market_state': sltp['state'],
        'zone_type': pick.get('zone_type', ''),
        'conf_type': pick.get('conf_type', ''),
        'ctx_seq': pick.get('ctx_seq', ''),
    }

def run_v26_backtest():
    picks = json.loads(PICKS_PATH.read_text())
    print(f"V25.6 backtest: {len(picks)} picks")
    
    trades = []
    skipped_rr = 0
    skipped_range = 0
    skipped_no_kline = 0
    
    for i, p in enumerate(picks):
        sym = p['symbol']
        klines = load_kline(sym)
        if not klines:
            skipped_no_kline += 1; continue
        
        entry_date = str(p.get('entry_date', ''))
        entry_idx = None
        for j, b in enumerate(klines):
            if str(b.get('t', b.get('date', ''))) == entry_date:
                entry_idx = j; break
        if entry_idx is None:
            entry_idx = p.get('entry_idx', len(klines)-1)
        
        entry_price = p.get('price', p.get('entry_price', float(klines[entry_idx].get('c', 0))))
        atr = compute_atr(klines, 14, entry_idx)
        if atr == 0: atr = entry_price * 0.02
        
        zone_lo = p.get('v25_zone_bottom', p.get('dz_low', entry_price * 0.95))
        
        # Compute state-adaptive SLTP
        sltp = compute_sltp(p, klines, entry_idx, entry_price, atr, zone_lo)
        
        # ── Skip RANGE ──
        if sltp['state'] == 'RANGE':
            skipped_range += 1; continue
        
        # ── RR floor ──
        min_rr = sltp['params']['min_rr']
        if sltp['rr'] < min_rr:
            skipped_rr += 1; continue
        
        result = simulate_exit(p, sltp, klines)
        if result:
            trades.append(result)
        
        if (i+1) % 100 == 0:
            print(f"  {i+1}/{len(picks)}...")
    
    # ── Stats ──
    n = len(trades)
    won = sum(1 for t in trades if t['won'])
    wr = won / n * 100 if n else 0
    avg_pnl = sum(t['pnl_pct'] for t in trades) / n if n else 0
    total_pnl = sum(t['pnl_pct'] for t in trades)
    avg_win = sum(t['pnl_pct'] for t in trades if t['won']) / max(won, 1)
    avg_loss = sum(t['pnl_pct'] for t in trades if not t['won']) / max(n-won, 1)
    exits = Counter(t['exit_reason'] for t in trades)
    
    print(f"\n═══ V25.6 Backtest ═══")
    print(f"  Skipped: {skipped_range} RANGE, {skipped_rr} low RR, {skipped_no_kline} no kline")
    print(f"  Trades: {n}  WR: {wr:.1f}%  avgP: {avg_pnl:+.2f}%  total: {total_pnl:+.2f}%")
    print(f"  avgWin: {avg_win:+.2f}%  avgLoss: {avg_loss:+.2f}%")
    
    print(f"\n  Exit reasons:")
    for reason, count in exits.most_common():
        print(f"    {reason:20s}: {count:4d} ({count/n*100:5.1f}%)")
    
    # By state
    states = Counter(t['market_state'] for t in trades)
    print(f"\n  By market state:")
    for state in ['TREND_UP', 'TREND_DOWN', 'HIGH_VOL', 'LOW_VOL']:
        ts = [t for t in trades if t['market_state'] == state]
        if not ts: continue
        twr = sum(1 for t in ts if t['won']) / len(ts) * 100
        tpnl = sum(t['pnl_pct'] for t in ts) / len(ts)
        print(f"    {state:12s}: {len(ts):4d} WR={twr:.1f}% avgP={tpnl:+.2f}%")
    
    # By zone
    zones = Counter(t['zone_type'] for t in trades)
    print(f"\n  By zone:")
    for zone, count in zones.most_common(5):
        zt = [t for t in trades if t['zone_type'] == zone]
        zwr = sum(1 for t in zt if t['won']) / len(zt) * 100
        zpnl = sum(t['pnl_pct'] for t in zt) / len(zt)
        print(f"    {zone:25s}: {count:3d} WR={zwr:.1f}% avgP={zpnl:+.2f}%")
    
    # By conf
    confs = Counter(t['conf_type'] for t in trades)
    print(f"\n  By confirmation:")
    for conf, count in confs.most_common(6):
        ct = [t for t in trades if t['conf_type'] == conf]
        cwr = sum(1 for t in ct if t['won']) / len(ct) * 100
        cpnl = sum(t['pnl_pct'] for t in ct) / len(ct)
        print(f"    {conf:20s}: {count:3d} WR={cwr:.1f}% avgP={cpnl:+.2f}%")
    
    # RR distribution
    rrs = [t.get('rr', 0) for t in trades]
    rr_bins = Counter()
    for rr in rrs:
        if rr < 1.0: rr_bins['<1.0'] += 1
        elif rr < 1.5: rr_bins['1.0-1.5'] += 1
        elif rr < 2.0: rr_bins['1.5-2.0'] += 1
        elif rr < 3.0: rr_bins['2.0-3.0'] += 1
        else: rr_bins['>3.0'] += 1
    print(f"\n  RR distribution: {dict(rr_bins)}")
    
    avg_rr = sum(rrs) / n if n else 0
    print(f"  Avg RR: {avg_rr:.2f}")
    
    # Save
    out = OUT_DIR / 'v26_trades.json'
    out.write_text(json.dumps(trades, ensure_ascii=False, indent=2))
    print(f"\nSaved: {out}")
    return trades

if __name__ == '__main__':
    run_v26_backtest()
