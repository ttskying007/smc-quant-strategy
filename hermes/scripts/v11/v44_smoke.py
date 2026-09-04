#!/usr/bin/env python3
"""V44引擎快速冒烟测试 (10只股票)"""
import sys, json, time, traceback
sys.path.insert(0, '/root/.hermes/scripts')

from pathlib import Path

CACHE_DIR = Path('/root/.hermes/kline_cache')

# 只选10只
symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_daily_300.json')])[:10]

print(f"V44 Smoke Test: {len(symbols)} stocks")

from v44_engine import backtest_stock_v44, load_ohlcv

for idx, sym in enumerate(symbols):
    try:
        ohlcv = load_ohlcv(sym)
        if not ohlcv or len(ohlcv) < 150:
            print(f"  [{idx+1}] {sym}: NO DATA")
            continue
        result = backtest_stock_v44(ohlcv, sym)
        if result:
            p = result['perf']
            print(f"  [{idx+1}] {sym}: n={p['n_trades']:2d} WR={p['win_rate']:.1f}% "
                  f"RR={p['avg_rr']:.2f}x PF={p['profit_factor']:.0f} retest={p['retest_entries']}")
        else:
            print(f"  [{idx+1}] {sym}: NO TRADES")
    except Exception as e:
        print(f"  [{idx+1}] {sym}: ERROR: {e}")
        traceback.print_exc()

print("\nSmoke test done!")