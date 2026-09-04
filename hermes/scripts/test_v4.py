#!/usr/bin/env python3
"""Quick V4 test"""
import sys, os
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
from smc_engine_v4 import get_klines, backtest_v4, evaluate

stocks = ['600519.SH','000001.SZ','000858.SZ']
all_s = {'strict':[], 'total':[], 'loose':[]}
for code in stocks:
    try:
        bars = get_klines(code, 'daily', 600)
        if len(bars) < 100: continue
        for mode in ['strict', 'total', 'loose']:
            trades = backtest_v4(bars, mode)
            all_s[mode].extend(trades)
    except Exception as e:
        print(f'{code}: {e}')
print()
for mode in ['loose', 'total', 'strict']:
    evaluate(all_s[mode], f'V4.{mode}(3stk)')
print('Done!')