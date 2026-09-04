#!/usr/bin/env python3
"""Deep diagnostic: why V468 skips all 000xxx stocks"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
from v11.v468_engine import CACHE_DIR, load_ohlcv, backtest_stock_v45, calc_stock_params_v45
from v11.signals_v11 import detect_all_signals_v11

# Test a few stocks
for sym in ['000001.SZ', '000002.SZ', '000008.SZ']:
    ohlcv = load_ohlcv(sym)
    if not ohlcv:
        print(f'{sym}: no data')
        continue
    
    base_params = {'fvg_min_width': None, 'sweep_lookback': 12}
    sigs = detect_all_signals_v11(ohlcv, params=base_params, tf='60min')
    all_sigs = sigs.get('all', [])
    
    # Count signal types
    fvg = sum(1 for s in all_sigs if 'FVG' in s.get('type','') and 'Mitigated' not in s.get('type',''))
    ob = sum(1 for s in all_sigs if 'OB' in s.get('type','') and 'BreakerBlock' not in s.get('type',''))
    sweep = sum(1 for s in all_sigs if 'Sweep' in s.get('type',''))
    choch = sum(1 for s in all_sigs if 'CHOCH' in s.get('type',''))
    bull_ob = sum(1 for s in all_sigs if 'OB_Bull' in s.get('type',''))
    bear_ob = sum(1 for s in all_sigs if 'OB_Bear' in s.get('type',''))
    
    print(f'{sym}:')
    print(f'  Total signals: {len(all_sigs)}')
    print(f'  FVG={fvg} OB={ob}(Bull={bull_ob} Bear={bear_ob}) Sweep={sweep} CHOCH={choch}')
    print(f'  Quality distribution:')
    for s in all_sigs:
        if 'OB_Bull' in s.get('type',''):
            q = s.get('quality', s.get('confidence', 0))
            idx = s.get('idx',0)
            rev, reason = None, None
            # Check reversal
            if idx >= 20:
                t20 = (ohlcv[idx]['c'] - ohlcv[idx-20]['c']) / ohlcv[idx-20]['c'] * 100
                has_sweep = any('SweepDown' in ss.get('type','') and abs(ss.get('idx',0)-idx)<=10 for ss in all_sigs)
                has_choch = any('CHOCH_Bull' in ss.get('type','') and ss.get('idx',0)<=idx and idx-ss.get('idx',0)<=15 for ss in all_sigs)
                rev = not (t20 > 1.0 and not (has_sweep and has_choch))
                reason = f't20={t20:.1f}% sweep={has_sweep} choch={has_choch}'
            print(f'    idx={idx:3d} q={q:.2f} rev={rev} {reason}')
    
    print()
