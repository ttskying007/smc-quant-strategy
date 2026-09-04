#!/usr/bin/env python3
"""V12 vs V11 comprehensive debug: trace the entire signal pipeline to find where V12 loses coverage."""

import sys, json, math
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts')

CACHE_DIR = Path('/root/.hermes/kline_cache_60min')

# Load V11 and V12 signal modules
from v11.signals_v11 import (
    detect_all_signals_v11, calc_adaptive_thresholds as calc_v11
)
from v11.signals_v12 import (
    detect_all_signals_v12, calc_adaptive_thresholds as calc_v12,
    detect_ob_v12, detect_swings_v12
)

def load_ohlcv(symbol):
    """Load OHLCV data from cached JSON files."""
    fname = symbol.replace('.', '_') + '_60min_200.json'
    fpath = CACHE_DIR / fname
    if not fpath.exists():
        return None
    data = json.load(open(fpath))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and 'data' in data:
        return data['data']
    return None

def compare_engines(symbols, max_stocks=50):
    """Compare V11 vs V12 signal detection on multiple stocks."""
    v11_stats = {'n_stocks': 0, 'total_signals': 0, 'fvg': 0, 'sweep': 0, 'ob': 0, 'choch': 0, 'others': 0}
    v12_stats = {'n_stocks': 0, 'total_signals': 0, 'fvg': 0, 'sweep': 0, 'ob': 0, 'choch': 0, 'others': 0}
    
    stock_details = []
    
    for idx, sym in enumerate(symbols[:max_stocks]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv or len(ohlcv) < 60:
            continue
        
        v11_res = detect_all_signals_v11(ohlcv, params={}, tf='60min')
        v12_res = detect_all_signals_v12(ohlcv, params={}, tf='60min')
        
        v11_all = v11_res.get('all', [])
        v12_all = v12_res.get('all', [])
        
        # V11 signal counts by type
        v11_ob = len(v11_res.get('ob', []))
        v11_fvg = len(v11_res.get('fvg', []))
        v11_sweep = len(v11_res.get('sweep', []))
        v11_choch = len(v11_res.get('choch', []))
        v11_other = len(v11_all) - v11_ob - v11_fvg - v11_sweep - v11_choch
        
        # V12 can't easily filter by type from return dict...
        v12_fvg = len(v12_res.get('FVG_Bull', [])) + len(v12_res.get('FVG_Bear', []))
        v12_ob = len(v12_res.get('OB_Bull', [])) + len(v12_res.get('OB_Bear', []))
        v12_sweep = len(v12_res.get('Sweep', []))
        v12_choch = len(v12_res.get('CHOCH_Bull', [])) + len(v12_res.get('CHOCH_Bear', []))
        v12_other = len(v12_all) - v12_fvg - v12_ob - v12_sweep - v12_choch
        
        v11_stats['n_stocks'] += 1
        v11_stats['total_signals'] += len(v11_all)
        v11_stats['fvg'] += v11_fvg
        v11_stats['sweep'] += v11_sweep
        v11_stats['ob'] += v11_ob
        v11_stats['choch'] += v11_choch
        v11_stats['others'] += v11_other
        
        v12_stats['n_stocks'] += 1
        v12_stats['total_signals'] += len(v12_all)
        v12_stats['fvg'] += v12_fvg
        v12_stats['sweep'] += v12_sweep
        v12_stats['ob'] += v12_ob
        v12_stats['choch'] += v12_choch
        v12_stats['others'] += v12_other
        
        stock_details.append({
            'symbol': sym,
            'v11_total': len(v11_all), 'v12_total': len(v12_all),
            'v11_ob': v11_ob, 'v12_ob': v12_ob,
            'v11_fvg': v11_fvg, 'v12_fvg': v12_fvg,
            'v11_sweep': v11_sweep, 'v12_sweep': v12_sweep,
            'v11_choch': v11_choch, 'v12_choch': v12_choch,
        })
        
        print(f"{sym:12s} V11: total={len(v11_all):3d} OB={v11_ob:2d} FVG={v11_fvg:2d} Sweep={v11_sweep:2d} CHOCH={v11_choch:2d}  |  V12: total={len(v12_all):3d} OB={v12_ob:2d} FVG={v12_fvg:2d} Sweep={v12_sweep:2d} CHOCH={v12_choch:2d}")
    
    print(f"\n{'='*80}")
    print(f"V11 totals ({v11_stats['n_stocks']} stocks):")
    print(f"  Total signals: {v11_stats['total_signals']} ({v11_stats['total_signals']/max(v11_stats['n_stocks'],1):.1f}/stock)")
    print(f"  OB: {v11_stats['ob']} ({v11_stats['ob']/max(v11_stats['n_stocks'],1):.1f}/stock)")
    print(f"  FVG: {v11_stats['fvg']} ({v11_stats['fvg']/max(v11_stats['n_stocks'],1):.1f}/stock)")
    print(f"  Sweep: {v11_stats['sweep']} ({v11_stats['sweep']/max(v11_stats['n_stocks'],1):.1f}/stock)")
    print(f"  CHOCH: {v11_stats['choch']} ({v11_stats['choch']/max(v11_stats['n_stocks'],1):.1f}/stock)")
    
    print(f"\nV12 totals ({v12_stats['n_stocks']} stocks):")
    print(f"  Total signals: {v12_stats['total_signals']} ({v12_stats['total_signals']/max(v12_stats['n_stocks'],1):.1f}/stock)")
    print(f"  OB: {v12_stats['ob']} ({v12_stats['ob']/max(v12_stats['n_stocks'],1):.1f}/stock)  -> {v12_stats['ob']/max(v11_stats['ob'],1)*100:.0f}% of V11")
    print(f"  FVG: {v12_stats['fvg']} ({v12_stats['fvg']/max(v12_stats['n_stocks'],1):.1f}/stock)")
    print(f"  Sweep: {v12_stats['sweep']} ({v12_stats['sweep']/max(v12_stats['n_stocks'],1):.1f}/stock)  -> {v12_stats['sweep']/max(v11_stats['sweep'],1)*100:.0f}% of V11")
    print(f"  CHOCH: {v12_stats['choch']} ({v12_stats['choch']/max(v12_stats['n_stocks'],1):.1f}/stock)")
    
    # Find biggest drop stocks
    print(f"\n{'='*80}")
    print(f"Top 10 stocks with biggest OB drop (V11 > V12):")
    drops = sorted(stock_details, key=lambda s: -(s['v11_ob'] - s['v12_ob']))[:10]
    for s in drops:
        print(f"  {s['symbol']:12s} V11_OB={s['v11_ob']:2d} V12_OB={s['v12_ob']:2d} drop={s['v11_ob']-s['v12_ob']:2d}")


def deep_dive_stock(symbol):
    """Deep dive into one stock to trace OB detection differences."""
    ohlcv = load_ohlcv(symbol)
    if not ohlcv:
        print(f"Cannot load {symbol}")
        return
    
    print(f"\n{'='*80}")
    print(f"DEEP DIVE: {symbol} ({len(ohlcv)} bars)")
    
    # V11 signals
    v11_res = detect_all_signals_v11(ohlcv, params={}, tf='60min')
    v11_obs = v11_res.get('ob', [])
    v11_swingh = v11_res.get('swing_highs', [])
    v11_swingl = v11_res.get('swing_lows', [])
    print(f"\nV11 OB count: {len(v11_obs)}")
    
    # V12 signals
    v12_res = detect_all_signals_v12(ohlcv, params={}, tf='60min')
    v12_obs = v12_res.get('OB_Bull', []) + v12_res.get('OB_Bear', [])
    v12_swingh = v12_res.get('swing_highs', [])
    v12_swingl = v12_res.get('swing_lows', [])
    print(f"V12 OB count: {len(v12_obs)}")
    
    print(f"\nV11 swing points: {len(v11_swingh)} highs, {len(v11_swingl)} lows")
    print(f"V12 swing points: {len(v12_swingh)} highs, {len(v12_swingl)} lows")
    
    # Compare swing point detection
    v11_sh_set = {(s['idx'], round(s['price'], 2)) for s in v11_swingh}
    v12_sh_set = {(s['idx'], round(s['price'], 2)) for s in v12_swingh}
    v11_sl_set = {(s['idx'], round(s['price'], 2)) for s in v11_swingl}
    v12_sl_set = {(s['idx'], round(s['price'], 2)) for s in v12_swingl}
    
    common_sh = v11_sh_set & v12_sh_set
    v11_only_sh = v11_sh_set - v12_sh_set
    v12_only_sh = v12_sh_set - v11_sh_set
    print(f"\nSwing high overlap: {len(common_sh)}/{max(len(v11_sh_set),1)} V11, {len(common_sh)}/{max(len(v12_sh_set),1)} V12")
    print(f"  V11-only swing highs: {len(v11_only_sh)}")
    print(f"  V12-only swing highs: {len(v12_only_sh)}")
    if v11_only_sh:
        print(f"  Examples V11-only: {sorted(list(v11_only_sh))[:5]}")
    if v12_only_sh:
        print(f"  Examples V12-only: {sorted(list(v12_only_sh))[:5]}")
    
    # Check V12 OB reasons for low count
    print(f"\n--- V12 OB detection analysis ---")
    adaptive = calc_v12(ohlcv)
    vol_median = adaptive['vol_median']
    print(f"Vol median: {vol_median:.0f}")
    
    # Direct swing detection
    swings_v12 = detect_swings_v12(ohlcv)
    print(f"Swing detection gave: {len(swings_v12[0])} highs, {len(swings_v12[1])} lows")
    
    # Try OB detection with no volume requirement
    ob_no_vol = detect_ob_v12(ohlcv, adaptive=adaptive, require_volume=False, swings=swings_v12, tf='60min')
    print(f"\nV12 OB with require_volume=False: {len(ob_no_vol)} (vs {len(v12_obs)} with volume)")
    
    # Try with lower displacement
    ob_low_disp = detect_ob_v12(ohlcv, adaptive=adaptive, require_volume=False, 
                                 displacement_mult=0.8, swings=swings_v12, tf='60min')
    print(f"V12 OB disp_mult=0.8, no_vol: {len(ob_low_disp)}")
    
    ob_low_disp2 = detect_ob_v12(ohlcv, adaptive=adaptive, require_volume=False,
                                  displacement_mult=0.5, swings=swings_v12, tf='60min')
    print(f"V12 OB disp_mult=0.5, no_vol: {len(ob_low_disp2)}")
    
    # List V12 OB details
    print(f"\nV12 OB details (volume-allowed):")
    for ob in v12_obs:
        md = ob.get('metadata', {})
        print(f"  idx={ob['idx']:3d} dir={ob['direction']:4s} disp={md.get('displacement_ratio',0):.2f}x "
              f"imp={md.get('impulse_bars',0)} body={md.get('body_pct',0):.2f}% "
              f"conf={ob.get('confidence',0):.2f} strength={ob.get('strength',0):.1f} "
              f"vol_ratio={ob.get('volume_ratio',0):.2f} swing_h={md.get('swing_high_idx', md.get('swing_low_idx','?'))}")
    
    # V11 OB details for comparison
    print(f"\nV11 OB details:")
    for ob in v11_obs[:15]:
        md = ob.get('metadata', {})
        print(f"  idx={ob['idx']:3d} dir={ob['direction']:4s} imp={md.get('impulse_bars',0)} "
              f"body={md.get('body_pct',0):.2f}% conf={ob.get('confidence',0):.2f} "
              f"at_struct={md.get('at_structure', False)} vol_ratio={ob.get('volume_ratio',0):.2f}")
    if len(v11_obs) > 15:
        print(f"  ... and {len(v11_obs)-15} more V11 OBs")


if __name__ == '__main__':
    # Load symbol list
    symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                     for f in CACHE_DIR.glob('*_60min_200.json')])
    print(f"Total symbols available: {len(symbols)}")
    
    # 1) Broad comparison
    print(f"\n{'='*80}")
    print(f"BROAD COMPARISON - scanning up to 100 stocks")
    compare_engines(symbols, max_stocks=100)
    
    # 2) Deep dive on stocks where V12 OB count is very low
    # Pick a few stocks that have data
    test_stocks = ['000001.SZ', '000002.SZ', '000858.SZ', '600519.SH', '600036.SH', '002415.SZ']
    for sym in test_stocks:
        if sym in symbols:
            deep_dive_stock(sym)
