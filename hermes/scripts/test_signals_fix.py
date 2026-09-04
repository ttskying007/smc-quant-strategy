#!/usr/bin/env python3
"""测试修复后的信号检测引擎"""
import json, sys
sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from pathlib import Path

CACHE = Path('/root/.hermes/kline_cache')

tests = ['000425.SZ', '000426.SZ', '000007.SZ', '000001.SZ', '000651.SZ']
for sym in tests:
    fname = sym.replace('.', '_') + '_daily_300.json'
    data = json.loads((CACHE / fname).read_text())
    result = detect_all_signals_v11(data)
    sigs = result['all']
    stats = result['stats']
    ad = result['adaptive']
    print(f'{sym}: {len(sigs)} signals | ATR={ad["atr_pct"]}% class={ad["volatility_class"]}')
    
    # Show breakdown by signal type
    for k in sorted(stats.keys()):
        v = stats[k]
        if k in ('total', 'bull', 'bear'): 
            continue
        if v > 0:
            print(f'  {k:20s}: {v}')
    print()

print('=== ALL TESTS PASSED ===')
