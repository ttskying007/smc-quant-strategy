#!/usr/bin/env python3
"""V45 v2 smoke test - verify ENABLE_BEAR and ENTRY_AT_ZONE"""
import sys
sys.path.insert(0, '/root/.hermes/scripts')
from v45_engine import backtest_stock_v45, load_ohlcv

# Test 3 stocks
for sym in ['000001.SZ', '300750.SZ', '600519.SH']:
    ohlcv = load_ohlcv(sym)
    if not ohlcv:
        print(f'{sym}: NO-DATA')
        continue
    result = backtest_stock_v45(ohlcv, sym)
    if not result:
        print(f'{sym}: SKIP')
        continue
    p = result['perf']
    bear_trades = [t for t in result['trades'] if t.get('direction') == 'bear']
    entries = [(t['entry_price'], t['entry_idx'], t['signal_type'], t['sl_type'], t['sl_pct']) 
               for t in result['trades'][:2]]
    print(f'{sym}: n={p["n_trades"]} WR={p["win_rate"]:.0f}% RR={p["avg_rr"]:.2f}x bear={len(bear_trades)} entries={entries}')
    if bear_trades:
        print(f'  WARN: Bear trades found! ENABLE_BEAR=False not working')
