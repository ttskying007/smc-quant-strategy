#!/usr/bin/env python3
"""Compare V11 vs vPine signal counts on sample stocks"""
import json, sys
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.signals_vPine import detect_all_signals_vPine

CACHE = Path('/root/.hermes/kline_cache')
CACHE_60M = Path('/root/.hermes/kline_cache_60min')

samples = ['600519.SH', '000858.SZ', '002415.SZ', '000001.SZ', '300750.SZ',
           '601318.SH', '000333.SZ', '002594.SZ', '688800.SH', '600036.SH']

for sym in samples:
    # Load daily
    fname_d = sym.replace('.','_') + '.json'
    dpath = CACHE / fname_d
    if dpath.exists():
        ohlcv = json.loads(dpath.read_bytes())
        rv11 = detect_all_signals_v11(ohlcv, tf='daily')
        rvp = detect_all_signals_vPine(ohlcv, tf='daily')
        s11 = rv11.get('stats', {})
        svp = rvp.get('stats', {})
        
        # Compare core signals: FVG, OB, Sweep, CHOCH, MSS, EQL
        print(f"{sym} (daily):")
        for key in ['fvg','ob','sweep','choch','mss','eql','bpr','rejection_block','liquidity_void','ote','po3','breaker_block','ifvg']:
            c11 = s11.get(key, 0)
            cvp = svp.get(key, 0)
            if c11 > 0 or cvp > 0:
                diff = "+" if cvp > c11 else "-" if cvp < c11 else "="
                print(f"  {key:20s}: V11={c11:4d}  vPine={cvp:4d}  {diff}")
        print(f"  {'TOTAL':20s}: V11={s11.get('total',0):4d}  vPine={svp.get('total',0):4d}")
        print()
    else:
        print(f"{sym}: no daily data")
