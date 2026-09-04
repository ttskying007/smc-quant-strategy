#!/usr/bin/env python3
"""
V37 — Multi-TF Integration: Daily + 60min SMC Signal Confirmation
=================================================================
Architecture:
  V36 core (FVG_Bull-only, confirmed_at entry, structural SL/TP)
  + 60min intraday context check:
    When daily FVG_Bull signal fires, check if 60min timeframe shows
    same-direction signals (FVG_Bull, SweepDown, OB_Bull, etc.) in the
    recent 50-bar window. If yes → boost confidence / confirm entry.

This script compares:
  (a) Daily-only baseline (V36 logic)
  (b) Daily + 60min confirmation

Usage: python3 backtest_multitf_v37.py
"""

import json, sys, math, time
from pathlib import Path
from collections import Counter
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11, calc_adaptive_thresholds
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase
from v11.weekly_trend import synthesize_weekly, weekly_trend
from v11.klines_60min import get_60min_kline

CACHE_DIR = Path('/root/.hermes/kline_cache')
CACHE_DIR_60MIN = Path('/root/.hermes/kline_cache_60min')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v37')
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Global params ──
SWING_MAX_DISTANCE = 30
SWING_SL_CAP = 0.5
MIN_VOL_RATIO = 0.7
MIN_FVG_GAP = 0.2
MAX_STOCKS = 50          # 50 stocks as requested
MIN_BARS = 120
MAX_HOLD = 60

PHASE_PARAMS = {
    'breakout':     {'sl': 0.3},
    'volatile':     {'sl': 0.5},
    'ranging':      {'sl': 0.8},
    'trending_up':  {'sl': 0.3},
    'trending_down':{'sl': 0.5},
}
CYCLE_SL_MULT = {'ALL-UP': 0.8, '2UP-1NEUTRAL': 1.0, 'NEUTRAL': 1.2}

# ═══════════════════════════════════════════════════════════════════════
# Data Loading
# ═══════════════════════════════════════════════════════════════════════

def load_ohlcv(symbol: str) -> Optional[List[Dict]]:
    fname = f"{symbol.replace('.','_')}_daily_300.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists():
        return None
    data = json.loads(fpath.read_text())
    if not data or len(data) < MIN_BARS:
        return None
    # Ensure 'date' field exists
    for bar in data:
        if 'date' not in bar and 't' in bar:
            bar['date'] = str(bar['t'])
    return data


def load_60min_ohlcv(symbol: str, force_refresh: bool = False) -> Optional[List[Dict]]:
    """Load 60min data for a symbol, using cache or fetching from Tencent API."""
    bars = get_60min_kline(symbol, force_refresh=force_refresh)
    if bars is None or len(bars) < 20:
        return None
    return bars


# ═══════════════════════════════════════════════════════════════════════
# Utility Functions (same as V36)
# ═══════════════════════════════════════════════════════════════════════

def short_trend(ohlcv, idx, lookback=10):
    if idx < lookback:
        return 'neutral', 0
    seg = ohlcv[idx-lookback:idx+1]
    s, e = seg[0]['c'], seg[-1]['c']
    change = (e - s) / s * 100
    ema = sum(ohlcv[i]['c'] for i in range(idx-min(5,idx), idx+1)) / min(6, idx+1)
    ema_d = (ohlcv[idx]['c'] - ema) / ema * 100
    if change > 0.6 and ema_d > 0:
        return 'up', change
    if change < -0.6 and ema_d < 0:
        return 'down', abs(change)
    return 'neutral', 0


def calc_atr(ohlcv, idx, period=14):
    if idx < period + 1:
        return (ohlcv[idx]['h'] - ohlcv[idx]['l']) / ohlcv[idx]['l'] * 100
    trs = []
    for i in range(max(1, idx - period), idx + 1):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    avg_tr = sum(trs) / len(trs)
    return avg_tr / ohlcv[idx]['l'] * 100


def find_all_swing_lows(ohlcv, end_idx, lookback=60):
    if end_idx < 3:
        return []
    start = max(0, end_idx - lookback)
    swings = []
    for i in range(end_idx-1, start, -1):
        b = ohlcv[i]
        l = ohlcv[i-1] if i > start else None
        r = ohlcv[i+1] if i < end_idx - 1 else None
        lv = l['l'] if l else 9999
        rv = r['l'] if r else 9999
        if b['l'] < lv and b['l'] < rv:
            swings.append((i, b['l'], end_idx - i))
    return swings


def find_best_swing_sl(ohlcv, end_idx, entry_price):
    swings = find_all_swing_lows(ohlcv, end_idx)
    swings = [s for s in swings if s[2] <= SWING_MAX_DISTANCE]
    if not swings:
        return None
    best, bs = None, 999
    for idx, price, dist in swings:
        capped = min(price, entry_price * (1 - SWING_SL_CAP / 100))
        sp = (entry_price - capped) / entry_price * 100
        if 0.10 <= sp <= 0.70:
            sc = abs(sp - 0.35) * 0.4 + (dist / SWING_MAX_DISTANCE) * 0.6
            if sc < bs:
                bs = sc
                best = {'sl_price': round(capped, 4), 'sl_pct': round(sp, 2)}
    return best


def find_swing_high_forward(ohlcv, start_idx, lookahead=30):
    end = min(start_idx + lookahead, len(ohlcv) - 1)
    for i in range(start_idx + 1, end - 1):
        b = ohlcv[i]
        l = ohlcv[i-1] if i > start_idx else None
        r = ohlcv[i+1] if i < end - 1 else None
        hv = l['h'] if l else 0
        rv = r['h'] if r else 0
        if b['h'] > hv and b['h'] > rv:
            return {'idx': i, 'price': b['h']}
    return None


def calc_structural_sl(ohlcv, entry_idx, entry_price, signal, all_signals):
    sig_type = signal.get('type', '')

    # FVG_Bull: SL at FVG lower boundary
    if 'FVG_Bull' in sig_type:
        fvg_lower = signal.get('lower', 0)
        if fvg_lower > 0:
            sl_pct = (entry_price - fvg_lower) / entry_price * 100
            atr = calc_atr(ohlcv, entry_idx)
            max_sl = min(0.80, atr * 0.8)
            if 0.08 <= sl_pct <= max_sl:
                sl_price = max(fvg_lower, entry_price * (1 - max_sl/100))
                return round(sl_price, 4), 'structure_fvg', round(sl_pct, 2)

    # OB_Bull: SL at OB lower boundary
    if 'OB_Bull' in sig_type:
        ob_lower = signal.get('lower', 0)
        if ob_lower > 0:
            sl_pct = (entry_price - ob_lower) / entry_price * 100
            if 0.08 <= sl_pct <= 1.0:
                return round(ob_lower, 4), 'structure_ob', round(sl_pct, 2)

    # Swing low fallback
    swing = find_best_swing_sl(ohlcv, entry_idx, entry_price)
    if swing:
        return swing['sl_price'], 'swing', swing['sl_pct']

    # ATR-adaptive dynamic SL (fallback)
    atr = calc_atr(ohlcv, entry_idx)
    dyn_sl_pct = max(0.15, min(0.80, atr * 0.3))
    return round(entry_price * (1 - dyn_sl_pct/100), 4), 'adaptive', round(dyn_sl_pct, 2)


def calc_structural_tp(ohlcv, entry_idx, entry_price, signal, all_signals):
    forward_choch = [s for s in all_signals
                     if 'CHOCH_Bull' in s.get('type', '')
                     and s.get('idx', 0) > entry_idx
                     and s.get('idx', 0) <= entry_idx + 60]
    if forward_choch:
        nearest = min(forward_choch, key=lambda s: s.get('idx', 0))
        tp_price = nearest.get('break_level', nearest.get('upper', 0))
        if tp_price > entry_price:
            tp_pct = (tp_price - entry_price) / entry_price * 100
            if tp_pct >= 0.5:
                return round(tp_price, 4), 'choch', round(tp_pct, 2), nearest['idx']

    swing_high = find_swing_high_forward(ohlcv, entry_idx)
    if swing_high and swing_high['price'] > entry_price:
        tp_pct = (swing_high['price'] - entry_price) / entry_price * 100
        if tp_pct >= 0.5:
            return round(swing_high['price'], 4), 'swing_high', round(tp_pct, 2), swing_high['idx']

    return None, None, None, None


def calc_trailing_v36(ohlcv, entry_idx, entry_price, initial_sl,
                      structural_tp, n, max_hold=60):
    sl = initial_sl
    highest = entry_price
    tp_price = structural_tp[0] if structural_tp and structural_tp[0] else None
    tp_pct = structural_tp[2] if structural_tp and structural_tp[2] else None

    for j in range(entry_idx+1, min(entry_idx+max_hold+1, n)):
        bar = ohlcv[j]
        if bar['h'] > highest:
            highest = bar['h']
        gain_pct = (highest - entry_price) / entry_price * 100

        if tp_price and highest >= tp_price * 0.95:
            sl = max(sl, entry_price * (1 + max(0.5, (tp_pct or 0) * 0.3) / 100))
            if highest >= tp_price:
                return j, tp_price, True
        else:
            if gain_pct >= 4.0:
                sl = max(sl, highest * (1 - 2.0/100))
            elif gain_pct >= 2.0:
                sl = max(sl, highest * (1 - 1.0/100))
            elif gain_pct >= 1.0:
                sl = max(sl, entry_price * 1.005)
            elif gain_pct >= 0.5:
                sl = max(sl, entry_price * 1.002)
            elif gain_pct >= 0.2:
                sl = max(sl, entry_price * 0.999)

        if bar['l'] <= sl:
            exit_price = max(sl, bar['l'])
            return j, round(exit_price, 2), exit_price > entry_price

    exit_idx = min(entry_idx + max_hold, n - 1)
    return exit_idx, round(ohlcv[exit_idx]['c'], 2), ohlcv[exit_idx]['c'] > entry_price


# ═══════════════════════════════════════════════════════════════════════
# 60min Context Check
# ═══════════════════════════════════════════════════════════════════════

def find_60min_index_for_daily(daily_t: str, ohlcv_60min: List[Dict]) -> int:
    """
    Find the index in 60min data corresponding to the daily bar date.
    daily_t is 'YYYYMMDD' format.
    Returns the index of the LAST 60min bar of that trading day.
    """
    if not ohlcv_60min:
        return -1
    # 60min dates are like '2026-04-30 14:00:00'
    # Extract YYYYMMDD from daily_t
    daily_date = str(daily_t)[:8]  # YYYYMMDD
    
    # Find the latest 60min bar that matches this date
    best_idx = -1
    for i, bar in enumerate(ohlcv_60min):
        dt = bar.get('date', '')
        # dt could be '2026-04-30 14:00:00' or '20260430'
        if '-' in dt:
            # Format: YYYY-MM-DD HH:MM:SS
            bar_date = dt[:10].replace('-', '')  # YYYYMMDD
        else:
            bar_date = str(bar.get('t', dt))[:8]
        
        if bar_date == daily_date:
            best_idx = i
        elif best_idx != -1 and bar_date > daily_date:
            break
    
    return best_idx


def check_60min_support(daily_signal: Dict, daily_ohlcv: List[Dict],
                        ohlcv_60min: List[Dict], signals_60min: List[Dict],
                        lookback_60: int = 50) -> Dict:
    """
    Check if the 60min timeframe supports a daily bull signal.
    Returns supported=True if no 60min data covers this date (neutral).
    
    Args:
        daily_signal: The daily FVG_Bull signal dict
        daily_ohlcv: Daily OHLCV data (to look up date from signal idx)
        ohlcv_60min: 60min OHLCV data
        signals_60min: All signals detected on 60min data
        lookback_60: Number of 60min bars to look back for context
    
    Returns:
        Dict with:
            - 'supported': bool (True if no 60min data available → neutral)
            - 'supporting_signals': list of supporting signal types found
            - 'score': confidence score (0-1)
            - 'no_60min_data': bool (True if no overlapping 60min data)
    """
    result = {
        'supported': True,  # Default: neutral (allow trade)
        'supporting_signals': [],
        'score': 0.0,
        'no_60min_data': False,
    }
    
    # Get the daily timestamp from the OHLCV bar at the signal's idx
    sig_idx = daily_signal.get('idx', -1)
    if sig_idx < 0 or sig_idx >= len(daily_ohlcv):
        return result
    daily_t = str(daily_ohlcv[sig_idx].get('t', daily_ohlcv[sig_idx].get('date', '')))
    if not daily_t:
        return result
    
    # Find the corresponding 60min index
    idx_60 = find_60min_index_for_daily(daily_t, ohlcv_60min)
    if idx_60 < 0:
        # No 60min data covers this date → neutral, don't reject
        result['no_60min_data'] = True
        return result
    
    # Define the window: [idx_60 - lookback_60, idx_60]
    window_start = max(0, idx_60 - lookback_60)
    
    # Find 60min signals in this window
    same_dir_signals = []
    for sig in signals_60min:
        sig_idx = sig.get('idx', -1)
        if window_start <= sig_idx <= idx_60:
            direction = sig.get('direction', '')
            sig_type = sig.get('type', '')
            if direction == 'bull':
                same_dir_signals.append(sig_type)
    
    if not same_dir_signals:
        return result
    
    # Count unique signal types
    sig_counts = Counter(same_dir_signals)
    
    # Score based on type and count
    score = 0.0
    supporting = []
    
    # FVG_Bull in 60min = strongest confirmation
    fvg_count = sig_counts.get('FVG_Bull', 0)
    if fvg_count > 0:
        score += min(0.5, fvg_count * 0.15)
        supporting.append(f'FVG_Bull({fvg_count})')
    
    # SweepDown (bullish sweep) = strong
    sweep_count = sig_counts.get('SweepDown', 0)
    if sweep_count > 0:
        score += min(0.3, sweep_count * 0.1)
        supporting.append(f'SweepDown({sweep_count})')
    
    # OB_Bull = good
    ob_count = sig_counts.get('OB_Bull', 0)
    if ob_count > 0:
        score += min(0.2, ob_count * 0.08)
        supporting.append(f'OB_Bull({ob_count})')
    
    # CHOCH_Bull = structural confirmation
    choch_count = sig_counts.get('CHOCH_Bull', 0)
    if choch_count > 0:
        score += min(0.3, choch_count * 0.12)
        supporting.append(f'CHOCH_Bull({choch_count})')
    
    # BPR = FVG retest, good confirmation
    bpr_count = sig_counts.get('BPR', 0)
    if bpr_count > 0:
        score += min(0.2, bpr_count * 0.1)
        supporting.append(f'BPR({bpr_count})')
    
    # Other signals add smaller bonus
    other_bull = sum(c for t, c in sig_counts.items()
                     if t not in ('FVG_Bull', 'SweepDown', 'OB_Bull', 'CHOCH_Bull', 'BPR')
                     and 'Bull' in t)
    if other_bull > 0:
        score += min(0.15, other_bull * 0.05)
        supporting.append(f'other({other_bull})')
    
    # Threshold: at least moderate support
    supported = score >= 0.15
    
    return {
        'supported': supported,
        'supporting_signals': supporting,
        'score': round(min(1.0, score), 3),
    }


def find_overlap_start(daily_ohlcv: List[Dict], ohlcv_60min: List[Dict]) -> int:
    """Find first daily index that overlaps with 60min data range."""
    if not daily_ohlcv or not ohlcv_60min:
        return 0
    first_60min_t = str(ohlcv_60min[0].get('date', ''))
    if '-' in first_60min_t:
        first_60min_date = first_60min_t[:10].replace('-', '')
    else:
        first_60min_date = first_60min_t[:8]
    
    for i, bar in enumerate(daily_ohlcv):
        daily_t = str(bar.get('t', bar.get('date', '')))
        if daily_t[:8] >= first_60min_date:
            # Ensure we have at least 40 bars before this point for signal detection
            return max(40, i - 5)  # a few bars before for safety
    return max(40, len(daily_ohlcv) - 100)


# ═══════════════════════════════════════════════════════════════════════
# Signal Entry Evaluation (V36-based)
# ═══════════════════════════════════════════════════════════════════════

def evaluate_signal_entry(ohlcv, sig_idx, sig, all_sigs_up_to_idx, all_signals,
                          params, phase, ohlcv_60min=None, signals_60min=None,
                          min_idx: int = 40):
    """
    V36 entry evaluation, augmented with optional 60min confirmation.
    """
    n = len(ohlcv)
    sig_type = sig.get('type', '')
    
    # Only FVG_Bull entries (same as V36)
    if 'FVG' not in sig_type and 'OB' not in sig_type:
        return None, False  # (result, used_multi_tf)
    if 'Bull' not in sig_type:
        return None, False
    
    signal_type = 'FVG' if 'FVG' in sig_type else 'OB'
    
    confirmed_at = sig.get('confirmed_at', sig_idx)
    entry_bar = max(sig_idx, confirmed_at)
    if entry_bar >= n - 2:
        return None, False
    
    # Use min_idx instead of hardcoded 40
    if sig_idx < min_idx or sig_idx >= n - 10:
        return None, False
    
    # Volume check
    if sig_idx > 30 and sig_idx < n:
        bv = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
        av = sum(ohlcv[j].get('v', ohlcv[j].get('vol', 0))
                 for j in range(max(0, sig_idx-30), sig_idx)) / 30
        if bv < av * 0.7:
            return None, False
    
    # FVG quality
    if 'FVG' in sig_type and sig_idx > 0 and sig_idx < n:
        bar = ohlcv[sig_idx]
        if bar['c'] <= bar['o']:
            return None, False
        upper = sig.get('upper', 0)
        lower = sig.get('lower', 0)
        if upper > 0 and lower > 0:
            gap_pct = (upper - lower) / lower * 100
            if gap_pct < 0.2:
                return None, False
    
    # Trend filters
    td, _ = short_trend(ohlcv, entry_bar)
    if td == 'down':
        return None, False
    
    weekly = synthesize_weekly(ohlcv[:entry_bar+1])
    if len(weekly) >= 3:
        wt = weekly_trend(weekly, lookback=min(5, len(weekly)))
        if wt == 'down':
            return None, False
    
    micro = short_trend(ohlcv, entry_bar, 8)
    meso = short_trend(ohlcv, entry_bar, 20)
    macro = short_trend(ohlcv, entry_bar, 40)
    uc = sum(1 for c in [micro, meso, macro] if c[0] == 'up')
    dc = sum(1 for c in [micro, meso, macro] if c[0] == 'down')
    if dc >= 2 or (uc == 1 and dc == 0):
        return None, False
    
    cd = 'ALL-UP' if uc == 3 else ('2UP-1NEUTRAL' if uc >= 2 else 'NEUTRAL')
    
    # Sequence + Resonance
    seq_r = analyze_sequence_v11(all_sigs_up_to_idx, params=params)
    best_seq = seq_r.get('best_sequence')
    if not best_seq:
        return None, False
    seq_name = best_seq.get('name', '')
    if 'SCOUT' not in seq_name:
        return None, False
    
    window = ohlcv[:entry_bar+1]
    tf_seq = {'daily': seq_r}
    res = evaluate_full_resonance_v11(
        all_signals=all_sigs_up_to_idx,
        tf_sequences=tf_seq,
        ohlcv=window
    )
    mr = 0.55 if uc >= 2 else 0.65
    if signal_type == 'OB':
        mr = max(mr, 0.70)
    if res.total < mr:
        return None, False
    
    dec = make_entry_decision_v11(res, seq_r, params, tf_sequences=tf_seq)
    if dec['action'] != 'enter':
        if uc >= 2 and res.total >= 0.50:
            pass
        else:
            return None, False
    
    # ── Multi-TF: 60min context check ──
    used_multi_tf = False
    rejected_mtf_no_data = False
    if ohlcv_60min is not None and signals_60min is not None:
        mtf_check = check_60min_support(sig, ohlcv, ohlcv_60min, signals_60min)
        if mtf_check.get('no_60min_data', False):
            # No 60min data for this date → don't filter, just pass through
            used_multi_tf = True
        elif not mtf_check['supported']:
            return None, True  # Rejected by 60min filter (had data, no support)
        else:
            used_multi_tf = True
    
    entry_price = ohlcv[entry_bar]['c']
    
    # Structural SL
    init_sl, sl_type_name, sl_pct_val = calc_structural_sl(
        ohlcv, entry_bar, entry_price, sig, all_signals)
    if init_sl is None:
        return None, used_multi_tf
    
    # Structural TP
    tp_price, tp_type, tp_pct, tp_idx = calc_structural_tp(
        ohlcv, entry_bar, entry_price, sig, all_signals)
    
    # Trailing
    exit_idx, exit_price, won = calc_trailing_v36(
        ohlcv, entry_bar, entry_price, init_sl,
        (tp_price, tp_type, tp_pct, tp_idx), n, MAX_HOLD)
    
    pnl = (exit_price - entry_price) / entry_price * 100
    actual_rr = abs(exit_price - entry_price) / abs(entry_price - init_sl) if entry_price != init_sl else 10
    
    return {
        'entry_idx': entry_bar,
        'sig_idx': sig_idx,
        'confirmed_at': confirmed_at,
        'exit_idx': exit_idx,
        'entry_price': round(entry_price, 2),
        'exit_price': round(exit_price, 2),
        'sl': round(init_sl, 2),
        'pnl_pct': round(pnl, 2),
        'won': won,
        'rr': round(actual_rr, 2),
        'hold_bars': exit_idx - entry_bar,
        'sl_type': sl_type_name,
        'sl_pct': round(sl_pct_val, 2),
        'tp_type': tp_type,
        'tp_pct': round(tp_pct, 2) if tp_pct else None,
        'signal_type': signal_type,
        'exit_method': 'tp_hit' if tp_type and tp_price and exit_price >= tp_price else 'trailing',
        'used_sl': round(sl_pct_val, 2),
        'phase': phase,
        'cycle_detail': cd,
        'used_multi_tf': used_multi_tf,
    }, used_multi_tf


# ═══════════════════════════════════════════════════════════════════════
# Backtest: Single Stock (Daily Only)
# ═══════════════════════════════════════════════════════════════════════

def backtest_stock_daily_only(ohlcv, symbol):
    """V36 baseline: daily-only backtest."""
    n = len(ohlcv)
    phase = detect_market_phase(ohlcv)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')['all']
    
    if not all_signals or len(all_signals) < 3:
        return None
    
    trades = []
    used_bars = set()
    
    for sig in all_signals:
        sig_idx = sig.get('idx', 0)
        if sig_idx < 40 or sig_idx >= n - 10:
            continue
        
        sigs_up_to = [s for s in all_signals if s.get('idx', 0) <= sig_idx]
        
        result, _ = evaluate_signal_entry(
            ohlcv, sig_idx, sig, sigs_up_to, all_signals,
            {**base_params}, phase, ohlcv_60min=None, signals_60min=None)
        if result:
            if result['entry_idx'] in used_bars:
                continue
            used_bars.add(result['entry_idx'])
            trades.append(result)
    
    if len(trades) < 2:
        return None
    
    wins = sum(1 for t in trades if t['won'])
    wr = wins / len(trades) * 100
    wp = sum(t['pnl_pct'] for t in trades if t['won'])
    lp = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
    pf = wp / lp if lp > 0 else 999
    avg_pnl = sum(t['pnl_pct'] for t in trades) / len(trades)
    avg_rr = sum(t['rr'] for t in trades) / len(trades)
    
    sl_types = Counter(t.get('sl_type', 'unknown') for t in trades)
    tp_types = Counter(t.get('tp_type', 'none') for t in trades)
    
    return {
        'trades': trades,
        'perf': {
            'n_trades': len(trades), 'wins': wins, 'losses': len(trades) - wins,
            'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
            'profit_factor': round(pf, 2) if pf < 999 else 999,
            'avg_pnl': round(avg_pnl, 2),
            'sl_types': dict(sl_types),
            'tp_types': dict(tp_types),
            'phase': phase,
        }
    }


# ═══════════════════════════════════════════════════════════════════════
# Backtest: Single Stock (Daily + 60min)
# ═══════════════════════════════════════════════════════════════════════

def backtest_stock_multitf(ohlcv, ohlcv_60min, symbol):
    """Multi-TF backtest: daily data with 60min confirmation."""
    n = len(ohlcv)
    phase = detect_market_phase(ohlcv)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    
    # Detect signals on daily
    daily_result = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')
    all_signals_daily = daily_result['all']
    
    # Detect signals on 60min
    params_60 = calc_stock_params(ohlcv_60min, symbol, phase=phase, tf='60min')
    signals_60min = detect_all_signals_v11(ohlcv_60min, params=params_60, tf='60min')['all']
    
    if not all_signals_daily or len(all_signals_daily) < 3:
        return None, 0
    
    trades = []
    used_bars = set()
    rejected_by_mtf = 0
    
    for sig in all_signals_daily:
        sig_idx = sig.get('idx', 0)
        if sig_idx < 40 or sig_idx >= n - 10:
            continue
        
        sigs_up_to = [s for s in all_signals_daily if s.get('idx', 0) <= sig_idx]
        
        result, was_mtf = evaluate_signal_entry(
            ohlcv, sig_idx, sig, sigs_up_to, all_signals_daily,
            {**base_params}, phase,
            ohlcv_60min=ohlcv_60min, signals_60min=signals_60min)
        
        if result is None:
            if was_mtf:
                rejected_by_mtf += 1
            continue
        
        if result['entry_idx'] in used_bars:
            continue
        used_bars.add(result['entry_idx'])
        trades.append(result)
    
    if len(trades) < 2:
        return None, rejected_by_mtf
    
    wins = sum(1 for t in trades if t['won'])
    wr = wins / len(trades) * 100
    wp = sum(t['pnl_pct'] for t in trades if t['won'])
    lp = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
    pf = wp / lp if lp > 0 else 999
    avg_pnl = sum(t['pnl_pct'] for t in trades) / len(trades)
    avg_rr = sum(t['rr'] for t in trades) / len(trades)
    
    sl_types = Counter(t.get('sl_type', 'unknown') for t in trades)
    tp_types = Counter(t.get('tp_type', 'none') for t in trades)
    
    return {
        'trades': trades,
        'perf': {
            'n_trades': len(trades), 'wins': wins, 'losses': len(trades) - wins,
            'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
            'profit_factor': round(pf, 2) if pf < 999 else 999,
            'avg_pnl': round(avg_pnl, 2),
            'sl_types': dict(sl_types),
            'tp_types': dict(tp_types),
            'phase': phase,
            'rejected_by_mtf': rejected_by_mtf,
        }
    }, rejected_by_mtf


# ═══════════════════════════════════════════════════════════════════════
# Weekly trend utility
# ═══════════════════════════════════════════════════════════════════════

def weekly_trend(weekly_data, lookback=5):
    """Simple weekly trend detection for filter."""
    if len(weekly_data) < lookback:
        return 'neutral'
    
    segment = weekly_data[-lookback:]
    start_price = segment[0]['c']
    end_price = segment[-1]['c']
    change = (end_price - start_price) / start_price * 100
    
    if change > 1.0:
        return 'up'
    elif change < -1.0:
        return 'down'
    return 'neutral'


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    # Get symbols from daily cache
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    n_stocks = min(MAX_STOCKS, len(symbols))
    test_symbols = symbols[:n_stocks]
    
    print(f"{'='*90}")
    print("V37 — Multi-TF Integration: Daily + 60min SMC Confirmation")
    print(f"  {n_stocks} stocks | SL: FVG下边界/swing | TP: CHOCH/摆动高点")
    print(f"  60min: {lookback=} bars context | Confirmation threshold: score >= 0.15")
    print(f"{'='*90}")
    
    results_daily = []     # Daily-only results
    results_multitf = []   # Daily+60min results
    all_trades_daily = []
    all_trades_multitf = []
    
    t_start = time.time()
    
    for idx, sym in enumerate(test_symbols):
        # Load daily data
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            print(f"  [{idx+1:3d}/{n_stocks}] {sym:12s} NO-DATA(day)")
            continue
        
        # Load 60min data
        ohlcv_60min = load_60min_ohlcv(sym)
        if not ohlcv_60min:
            print(f"  [{idx+1:3d}/{n_stocks}] {sym:12s} NO-DATA(60min)")
            continue
        
        # ── Daily-only baseline ──
        p = {'n_trades': 0, 'win_rate': 0}
        result_d = backtest_stock_daily_only(ohlcv, sym)
        if result_d:
            p = result_d['perf']
            all_trades_daily.extend(result_d['trades'])
            results_daily.append({'symbol': sym, **p})
        
        # ── Daily + 60min ──
        p2 = {'n_trades': 0, 'win_rate': 0}
        rej_str = ""
        result_m = backtest_stock_multitf(ohlcv, ohlcv_60min, sym)
        if result_m and isinstance(result_m, tuple) and result_m[0]:
            result_data, rej = result_m
            p2 = result_data['perf']
            all_trades_multitf.extend(result_data['trades'])
            results_multitf.append({'symbol': sym, **p2})
            rej_str = f"rejected={rej}"
        else:
            rej_str = "SKIP"
        
        # Daily trades count for display
        dt = p.get('n_trades', 0)
        dw = p.get('win_rate', 0)
        mt = p2.get('n_trades', 0)
        mw = p2.get('win_rate', 0)
        
        print(f"  [{idx+1:3d}/{n_stocks}] {sym:12s} daily: {dt:2d}t WR={dw:.0f}% | "
              f"mtf: {mt:2d}t WR={mw:.0f}% | {rej_str if not result_m else ''}")
        
        if (idx + 1) % 10 == 0:
            elapsed = time.time() - t_start
            print(f"  ── Progress: {idx+1}/{n_stocks} | {elapsed:.0f}s elapsed")
    
    total_time = time.time() - t_start
    
    # ═══════════════════════════════════════════════════════════════════
    # Print Comparison
    # ═══════════════════════════════════════════════════════════════════
    
    print(f"\n{'='*90}")
    print(f"RESULTS COMPARISON — {total_time:.0f}s total")
    print(f"{'='*90}")
    
    def calc_aggregate(trades, stock_results):
        if not trades:
            return {'n_trades': 0, 'win_rate': 0, 'avg_rr': 0, 'pf': 0, 'avg_pnl': 0,
                    'avg_hold': 0, 'max_hold': 0, 'high_wr': 0, 'tradable': len(stock_results)}
        n = len(trades)
        wins = sum(1 for t in trades if t['won'])
        wr = wins / n * 100
        wp = sum(t['pnl_pct'] for t in trades if t['won'])
        lp = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
        pf = wp / lp if lp > 0 else 999
        rr = sum(t['rr'] for t in trades) / n
        pnl = sum(t['pnl_pct'] for t in trades) / n
        holds = [t['hold_bars'] for t in trades]
        high_wr = sum(1 for s in stock_results if s.get('win_rate', 0) >= 80)
        return {
            'n_trades': n,
            'win_rate': round(wr, 1),
            'avg_rr': round(rr, 2),
            'pf': round(pf, 2) if pf < 999 else 999,
            'avg_pnl': round(pnl, 2),
            'avg_hold': round(sum(holds) / len(holds), 1) if holds else 0,
            'max_hold': max(holds) if holds else 0,
            'high_wr': high_wr,
            'tradable': len(stock_results),
        }
    
    agg_d = calc_aggregate(all_trades_daily, results_daily)
    agg_m = calc_aggregate(all_trades_multitf, results_multitf)
    
    print(f"\n  {'Metric':<20s} {'Daily-Only':<18s} {'Daily+60min':<18s} {'Change':<12s}")
    print(f"  {'─'*20} {'─'*18} {'─'*18} {'─'*12}")
    
    metrics = [
        ('Tradable Stocks', f"{agg_d['tradable']}", f"{agg_m['tradable']}", ''),
        ('Total Trades', f"{agg_d['n_trades']}", f"{agg_m['n_trades']}",
         f"{agg_m['n_trades'] - agg_d['n_trades']:+d}"),
        ('Win Rate', f"{agg_d['win_rate']:.1f}%", f"{agg_m['win_rate']:.1f}%",
         f"{agg_m['win_rate'] - agg_d['win_rate']:+.1f}%"),
        ('Avg RR', f"{agg_d['avg_rr']:.2f}x", f"{agg_m['avg_rr']:.2f}x",
         f"{agg_m['avg_rr'] - agg_d['avg_rr']:+.2f}"),
        ('Profit Factor', f"{agg_d['pf']:.2f}", f"{agg_m['pf']:.2f}",
         f"{agg_m['pf'] - agg_d['pf']:+.2f}"),
        ('Avg P&L', f"{agg_d['avg_pnl']:+.2f}%", f"{agg_m['avg_pnl']:+.2f}%",
         f"{agg_m['avg_pnl'] - agg_d['avg_pnl']:+.2f}%"),
        ('Avg Hold (bars)', f"{agg_d['avg_hold']:.1f}", f"{agg_m['avg_hold']:.1f}",
         f"{agg_m['avg_hold'] - agg_d['avg_hold']:+.1f}"),
        ('Stocks WR>=80%', f"{agg_d['high_wr']}", f"{agg_m['high_wr']}",
         f"{agg_m['high_wr'] - agg_d['high_wr']:+d}"),
    ]
    
    for name, v1, v2, v3 in metrics:
        print(f"  {name:<20s} {v1:<18s} {v2:<18s} {v3:<12s}")
    
    # Per-stock comparison
    print(f"\n{'─'*90}")
    print(f"PER-STOCK COMPARISON (stocks with trades in both modes)")
    print(f"{'─'*90}")
    print(f"  {'Symbol':<12s} {'Daily WR':<10s} {'Daily n':<8s} {'MTF WR':<10s} {'MTF n':<8s} {'WR Δ':<8s} {'N Δ':<6s}")
    print(f"  {'─'*12} {'─'*10} {'─'*8} {'─'*10} {'─'*8} {'─'*8} {'─'*6}")
    
    d_map = {s['symbol']: s for s in results_daily}
    m_map = {s['symbol']: s for s in results_multitf}
    
    comparisons = []
    for sym in sorted(set(list(d_map.keys()) + list(m_map.keys()))):
        d = d_map.get(sym)
        m = m_map.get(sym)
        dwr = d['win_rate'] if d else 0
        mwr = m['win_rate'] if m else 0
        dn = d['n_trades'] if d else 0
        mn = m['n_trades'] if m else 0
        wr_delta = mwr - dwr
        n_delta = mn - dn
        comparisons.append({
            'symbol': sym,
            'daily_wr': dwr, 'daily_n': dn,
            'mtf_wr': mwr, 'mtf_n': mn,
            'wr_delta': wr_delta, 'n_delta': n_delta,
        })
        print(f"  {sym:<12s} {dwr:<8.1f}% {dn:<8d} {mwr:<8.1f}% {mn:<8d} {wr_delta:<+7.1f}% {n_delta:<+5d}")
    
    # Summary improvements
    wr_improved = sum(1 for c in comparisons if c['wr_delta'] > 0 and c['daily_n'] > 0 and c['mtf_n'] > 0)
    wr_worsened = sum(1 for c in comparisons if c['wr_delta'] < 0 and c['daily_n'] > 0 and c['mtf_n'] > 0)
    
    print(f"\n  WR Improvement: {wr_improved} stocks | WR Worsened: {wr_worsened} stocks")
    
    # Save results
    outpath = OUTPUT_DIR / 'backtest_multitf_v37_comparison.json'
    json.dump({
        'timestamp': __import__('datetime').datetime.now().isoformat(),
        'config': {
            'version': 'V37 Multi-TF',
            'n_stocks': n_stocks,
            'lookback_60min': lookback,
            'min_mtf_score': 0.15,
        },
        'summary_daily_only': agg_d,
        'summary_multitf': agg_m,
        'improvement': {
            'wr_delta': round(agg_m['win_rate'] - agg_d['win_rate'], 1),
            'pf_delta': round(agg_m['pf'] - agg_d['pf'], 2),
            'pnl_delta': round(agg_m['avg_pnl'] - agg_d['avg_pnl'], 2),
            'n_delta': agg_m['n_trades'] - agg_d['n_trades'],
        },
        'stocks_daily': results_daily,
        'stocks_multitf': results_multitf,
        'comparisons': comparisons,
    }, open(outpath, 'w'), ensure_ascii=False, indent=2, default=str)
    print(f"\n  Saved: {outpath}")

    # Also save comparison table as text
    txt_path = OUTPUT_DIR / 'backtest_multitf_v37_comparison.txt'
    with open(txt_path, 'w') as f:
        f.write(f"V37 Multi-TF Comparison — {total_time:.0f}s\n")
        f.write(f"{'='*70}\n\n")
        f.write(f"{'Metric':<20s} {'Daily-Only':<18s} {'Daily+60min':<18s} {'Change':<12s}\n")
        f.write(f"{'─'*20} {'─'*18} {'─'*18} {'─'*12}\n")
        for name, v1, v2, v3 in metrics:
            f.write(f"{name:<20s} {v1:<18s} {v2:<18s} {v3:<12s}\n")
    print(f"  Saved: {txt_path}")
    
    # Print summary
    print(f"\n{'='*90}")
    print("SUMMARY")
    print(f"{'='*90}")
    print(f"  Daily-Only:  {agg_d['n_trades']} trades, WR={agg_d['win_rate']:.1f}%, "
          f"RR={agg_d['avg_rr']:.2f}x, PF={agg_d['pf']:.2f}, P&L={agg_d['avg_pnl']:+.2f}%")
    print(f"  Daily+60min: {agg_m['n_trades']} trades, WR={agg_m['win_rate']:.1f}%, "
          f"RR={agg_m['avg_rr']:.2f}x, PF={agg_m['pf']:.2f}, P&L={agg_m['avg_pnl']:+.2f}%")
    print(f"  Delta:       {agg_m['n_trades'] - agg_d['n_trades']:+d} trades, "
          f"WR={agg_m['win_rate'] - agg_d['win_rate']:+.1f}%, "
          f"PF={agg_m['pf'] - agg_d['pf']:+.2f}, "
          f"P&L={agg_m['avg_pnl'] - agg_d['avg_pnl']:+.2f}%")
    print(f"  Script: /root/.hermes/scripts/v11/backtest_multitf_v37.py")
    
    return agg_d, agg_m, comparisons


if __name__ == '__main__':
    lookback = 50  # 60min lookback window
    main()
