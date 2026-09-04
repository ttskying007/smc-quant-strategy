#!/usr/bin/env python3
"""V12 OB: trace why swing backward scan fails on each swing point."""

import sys, json
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts')

CACHE_DIR = Path('/root/.hermes/kline_cache_60min')
from v11.signals_v12 import detect_ob_v12, detect_swings_v12, calc_adaptive_thresholds

def load_ohlcv(symbol):
    fname = symbol.replace('.', '_') + '_60min_200.json'
    fpath = CACHE_DIR / fname
    if not fpath.exists():
        return None
    data = json.load(open(fpath))
    if isinstance(data, list): return data
    if isinstance(data, dict) and 'data' in data: return data['data']
    return None

def trace_ob_scan(symbol):
    """For each swing high/low, trace why OB scan fails/succeeds."""
    ohlcv = load_ohlcv(symbol)
    if not ohlcv:
        return
    
    n = len(ohlcv)
    adaptive = calc_adaptive_thresholds(ohlcv)
    vol_median = adaptive['vol_median']
    displacement_mult = 1.3
    
    sh, sl = detect_swings_v12(ohlcv, left=8, right=3)
    
    print(f"\n{'='*80}")
    print(f"TRACE OB SCAN: {symbol} ({n} bars, vol_median={vol_median:.0f})")
    print(f"Swing points: {len(sh)} highs, {len(sl)} lows")
    
    # OB by direct call
    ob_result = detect_ob_v12(ohlcv, adaptive=adaptive, tf='60min')
    ob_idxs = set(s.get('idx', -1) for s in ob_result)
    print(f"OB found: {len(ob_result)} at idxs {sorted(ob_idxs)}")
    
    ## TRACE SWING HIGHS (Bullish OB backward scan)
    print(f"\n--- Bullish OB: scan backward from each swing high ---")
    bull_ob_count = 0
    
    for sh_idx, sh_price in sh:
        if sh_idx < 5:
            print(f"  [SKIP swing high idx={sh_idx:3d}] price={sh_price:.2f} - too early")
            continue
        
        # Manual trace of the backward scan
        phase = 'skip'
        impulse_len = 0
        ob_idx = None
        trace_steps = []
        
        for bi in range(sh_idx - 1, max(sh_idx - 25, 4), -1):
            bar = ohlcv[bi]
            is_bear = bar['c'] < bar['o']
            is_bull = bar['c'] > bar['o']
            
            if phase == 'skip':
                if is_bear:
                    trace_steps.append(f"    bi={bi:3d} BEAR skip (pullback)")
                    continue
                elif is_bull:
                    phase = 'impulse'
                    impulse_len = 1
                    trace_steps.append(f"    bi={bi:3d} BULL -> impulse start (len=1)")
                else:
                    trace_steps.append(f"    bi={bi:3d} DOJI skip")
                    continue
                    
            elif phase == 'impulse':
                if is_bull:
                    impulse_len += 1
                    trace_steps.append(f"    bi={bi:3d} BULL impulse_len={impulse_len}")
                    continue
                elif is_bear:
                    ob_idx = bi
                    trace_steps.append(f"    bi={bi:3d} BEAR -> OB FOUND at idx={bi}")
                    break
                else:
                    impulse_len += 1
                    trace_steps.append(f"    bi={bi:3d} DOJI impulse_len={impulse_len}")
                    continue
        
        # Check validation
        if ob_idx is None or impulse_len < 1:
            print(f"  [FAIL sh_idx={sh_idx:3d} price={sh_price:.2f}] impulse_len={impulse_len} ob_idx={ob_idx}")
            for step in trace_steps[-5:]: print(step)
            continue
        
        ob_bar = ohlcv[ob_idx]
        body_pct = abs(ob_bar['c'] - ob_bar['o']) / max(ob_bar['o'], 0.01) * 100
        if body_pct < 0.15:
            print(f"  [FAIL sh_idx={sh_idx:3d}] body_pct={body_pct:.3f}% < 0.15")
            continue
        
        bar_range = ob_bar['h'] - ob_bar['l']
        if bar_range <= 0:
            print(f"  [FAIL sh_idx={sh_idx:3d}] zero range")
            continue
        
        displacement = sh_price - ob_bar['l']
        dis_ratio = displacement / bar_range
        
        if dis_ratio < displacement_mult:
            print(f"  [FAIL sh_idx={sh_idx:3d}] dis_ratio={dis_ratio:.2f}x < {displacement_mult}x body={body_pct:.2f}%")
            continue
        
        # Volume check
        impulse_end = ob_idx + impulse_len + 1
        impulse_vols = [ohlcv[j]['v'] for j in range(ob_idx + 1, min(impulse_end + 1, n))]
        avg_imp_v = sum(impulse_vols) / max(len(impulse_vols), 1)
        vol_ok = avg_imp_v > vol_median * 1.2 or ob_bar['v'] > vol_median * 1.2
        
        if not vol_ok:
            print(f"  [VOLFAIL sh_idx={sh_idx:3d}] avg_imp_v={avg_imp_v:.0f} vol_median*1.2={vol_median*1.2:.0f} ob_v={ob_bar['v']:.0f}")
            continue
        
        bull_ob_count += 1
        print(f"  [OK    sh_idx={sh_idx:3d}] ob_idx={ob_idx:3d} imp={impulse_len} dis_ratio={dis_ratio:.2f}x body={body_pct:.2f}%")
        # Show last 3 trace steps
        for step in trace_steps[-3:]: print(step)
    
    ## TRACE SWING LOWS (Bearish OB backward scan)
    print(f"\n--- Bearish OB: scan backward from each swing low ---")
    bear_ob_count = 0
    
    for sl_idx, sl_price in sl:
        if sl_idx < 5:
            print(f"  [SKIP swing low  idx={sl_idx:3d}] price={sl_price:.2f} - too early")
            continue
        
        phase = 'skip'
        impulse_len = 0
        ob_idx = None
        trace_steps = []
        
        for bi in range(sl_idx - 1, max(sl_idx - 25, 4), -1):
            bar = ohlcv[bi]
            is_bull = bar['c'] > bar['o']
            is_bear = bar['c'] < bar['o']
            
            if phase == 'skip':
                if is_bull:
                    trace_steps.append(f"    bi={bi:3d} BULL skip (bounce)")
                    continue
                elif is_bear:
                    phase = 'impulse'
                    impulse_len = 1
                    trace_steps.append(f"    bi={bi:3d} BEAR -> impulse start")
                else:
                    trace_steps.append(f"    bi={bi:3d} DOJI skip")
                    continue
                    
            elif phase == 'impulse':
                if is_bear:
                    impulse_len += 1
                    trace_steps.append(f"    bi={bi:3d} BEAR impulse_len={impulse_len}")
                    continue
                elif is_bull:
                    ob_idx = bi
                    trace_steps.append(f"    bi={bi:3d} BULL -> OB FOUND")
                    break
                else:
                    ob_idx = bi
                    trace_steps.append(f"    bi={bi:3d} DOJI -> set as OB")
                    break
        
        if ob_idx is None or impulse_len < 2:
            print(f"  [FAIL sl_idx={sl_idx:3d} price={sl_price:.2f}] impulse_len={impulse_len} ob_idx={ob_idx}")
            for step in trace_steps[-5:]: print(step)
            continue
        
        ob_bar = ohlcv[ob_idx]
        body_pct = abs(ob_bar['c'] - ob_bar['o']) / max(ob_bar['o'], 0.01) * 100
        if body_pct < 0.15:
            print(f"  [FAIL sl_idx={sl_idx:3d}] body_pct={body_pct:.3f}% < 0.15")
            continue
        
        bar_range = ob_bar['h'] - ob_bar['l']
        displacement = ob_bar['h'] - sl_price
        dis_ratio = displacement / bar_range
        
        if dis_ratio < displacement_mult:
            print(f"  [FAIL sl_idx={sl_idx:3d}] dis_ratio={dis_ratio:.2f}x < {displacement_mult}x body={body_pct:.2f}%")
            continue
        
        impulse_end = ob_idx + impulse_len + 1
        impulse_vols = [ohlcv[j]['v'] for j in range(ob_idx + 1, min(impulse_end + 1, n))]
        avg_imp_v = sum(impulse_vols) / max(len(impulse_vols), 1)
        vol_ok = avg_imp_v > vol_median * 1.2 or ob_bar['v'] > vol_median * 1.2
        
        if not vol_ok:
            print(f"  [VOLFAIL sl_idx={sl_idx:3d}] avg_imp_v={avg_imp_v:.0f} vs {vol_median*1.2:.0f}")
            continue
        
        bear_ob_count += 1
        print(f"  [OK    sl_idx={sl_idx:3d}] ob_idx={ob_idx:3d} imp={impulse_len} dis_ratio={dis_ratio:.2f}x body={body_pct:.2f}%")
        for step in trace_steps[-3:]: print(step)
    
    print(f"\n  Total: {bull_ob_count} bull OB + {bear_ob_count} bear OB = {bull_ob_count + bear_ob_count}")


if __name__ == '__main__':
    symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                     for f in CACHE_DIR.glob('*_60min_200.json')])
    
    for sym in ['000001.SZ', '000858.SZ', '002415.SZ', '600519.SH']:
        if sym in symbols:
            trace_ob_scan(sym)
