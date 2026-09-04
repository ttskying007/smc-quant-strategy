#!/usr/bin/env python3
"""Test OB detection on multiple stocks with varying volatility."""
import json, sys
sys.path.insert(0, '/root/.hermes/scripts/v25')
from pathlib import Path
from collections import Counter
from smc_core_pine_like import detect_all_signals_pine_like

test_symbols = [
    '000001.SZ', '002415.SZ', '300750.SZ', '688981.SH',
    '000858.SZ', '002594.SZ', '601012.SH', '600519.SH'
]

cache = Path('/root/.hermes/kline_cache')
for sym in test_symbols:
    fname = sym.replace('.', '_') + '_daily_300.json'
    fp = cache / fname
    if not fp.exists():
        print(f'{sym}: NO DATA')
        continue
    data = json.loads(fp.read_bytes())
    if len(data) < 80:
        print(f'{sym}: {len(data)} bars (too short)')
        continue
    
    # Test with 1.3x displacement mult
    res = detect_all_signals_pine_like(data)
    obs = res['signals']['obs']
    sweeps = res['signals']['sweeps']
    struct = res['signals']['structure']
    sm = res['summary']
    
    # Get displacement ratios
    if obs:
        disps = [ob.get('displacement_ratio', 0) for ob in obs]
        min_d = min(disps)
        max_d = max(disps)
        avg_d = sum(disps) / len(disps)
    else:
        min_d = max_d = avg_d = 0
    
    print(f'{sym}: {len(data)}b F={sm["n_fvg"]} S={sm["n_sweep"]} '
          f'OB={len(obs)} St={sm["n_swing_structure"]}+{sm["n_internal_structure"]} '
          f'OB_disp: min={min_d:.1f}x avg={avg_d:.1f}x max={max_d:.1f}x '
          f'n_swings={sm["n_swing_highs"]}/{sm["n_swing_lows"]}')
