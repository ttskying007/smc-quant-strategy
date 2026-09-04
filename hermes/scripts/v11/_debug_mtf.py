#!/usr/bin/env python3
"""Debug: test 60min data loading and signal detection for one stock."""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
from v11.klines_60min import get_60min_kline
from v11.signals_v11 import detect_all_signals_v11, calc_adaptive_thresholds
from v11.adaptive_params import calc_stock_params, detect_market_phase

# Test with a stock that has daily data
symbol = '000001.SZ'

# Load 60min
bars_60 = get_60min_kline(symbol, force_refresh=False)
if bars_60:
    print(f"60min bars: {len(bars_60)}")
    print(f"First: {bars_60[0]}")
    print(f"Last: {bars_60[-1]}")
    print()
    
    # Detect signals
    params_60 = calc_stock_params(bars_60, symbol, tf='60min')
    result = detect_all_signals_v11(bars_60, params=params_60, tf='60min')
    signals = result['all']
    print(f"60min signals: {len(signals)}")
    
    bull_sigs = [s for s in signals if s.get('direction') == 'bull']
    print(f"  Bull signals: {len(bull_sigs)}")
    for s in bull_sigs[:10]:
        print(f"    {s.get('type'):20s} idx={s.get('idx'):4d} price={s.get('price'):.2f}")
    
    # Check datemap
    daily_t = '20260430'  # latest daily bar date
    from backtest_multitf_v37 import find_60min_index_for_daily
    idx_60 = find_60min_index_for_daily(daily_t, bars_60)
    print(f"\nDaily date {daily_t} -> 60min index: {idx_60}")
    if idx_60 >= 0:
        print(f"  60min bar at idx {idx_60}: {bars_60[idx_60]}")
    
    # Look back 50 bars for signals
    start = max(0, idx_60 - 50)
    near_signals = [s for s in bull_sigs if start <= s.get('idx', -1) <= idx_60]
    print(f"\nSignals in last 50 bars before idx {idx_60}: {len(near_signals)}")
    for s in near_signals[:10]:
        print(f"    {s.get('type'):20s} idx={s.get('idx'):4d}")
else:
    print("FAILED to load 60min data")
