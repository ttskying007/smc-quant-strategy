#!/usr/bin/env python3
"""Debug: check daily signal dict structure."""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11, calc_adaptive_thresholds
from v11.adaptive_params import calc_stock_params, detect_market_phase

symbol = '000001.SZ'
ohlcv = json.loads(open(f'/root/.hermes/kline_cache/000001_SZ_daily_300.json').read())
# Ensure date field
for bar in ohlcv:
    if 'date' not in bar and 't' in bar:
        bar['date'] = str(bar['t'])

phase = detect_market_phase(ohlcv)
params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
result = detect_all_signals_v11(ohlcv, params=params, tf='daily')
signals = result['all']
print(f"Daily signals: {len(signals)}")

# Find FVG_Bull signals
fvg_bull = [s for s in signals if 'FVG_Bull' in s.get('type', '')]
print(f"FVG_Bull signals: {len(fvg_bull)}")

if fvg_bull:
    s = fvg_bull[0]
    print(f"\nFirst FVG_Bull signal:")
    for k, v in s.items():
        print(f"  {k}: {v}")
    
    print(f"\nKeys available: {list(s.keys())}")
    
    # Does it have the daily bar's 't'?
    sig_idx = s.get('idx', 0)
    print(f"\nDaily bar at idx {sig_idx}:")
    if sig_idx < len(ohlcv):
        print(f"  {ohlcv[sig_idx]}")
    
    # How to get the date?
    print(f"\nTrying to get date from signal:")
    print(f"  signal.get('date', signal.get('t', 'N/A')): {s.get('date', s.get('t', 'N/A'))}")
    print(f"  ohlcv[sig_idx].get('t', 'N/A'): {ohlcv[sig_idx].get('t', 'N/A')}")
    print(f"  ohlcv[sig_idx].get('date', 'N/A'): {ohlcv[sig_idx].get('date', 'N/A')}")
