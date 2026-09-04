#!/usr/bin/env python3
"""V45 smoke test: 10 stocks, validate ENABLE_BEAR=False + ENTRY_AT_ZONE=True"""
import sys
sys.path.insert(0, '/root/.hermes/scripts')
from v45_engine import load_ohlcv, backtest_stock_v45, ENABLE_BEAR

print(f"ENABLE_BEAR={ENABLE_BEAR}, ENTRY_AT_ZONE=True")
print("="*60)

symbols = ['000001.SZ','000002.SZ','000004.SZ','600519.SH','300750.SZ',
           '000858.SZ','002415.SZ','601318.SH','000333.SZ','600036.SH']

for sym in symbols:
    ohlcv = load_ohlcv(sym)
    if not ohlcv:
        print(f"{sym}: NO-DATA")
        continue
    result = backtest_stock_v45(ohlcv, sym)
    if not result:
        print(f"{sym}: SKIP")
        continue
    p = result['perf']
    bears = sum(1 for t in result['trades'] if t['direction'] == 'bear')
    entries = []
    for t in result['trades'][:3]:
        entries.append(f"${t['entry_price']}({t['signal_type']})SL={t['sl_type']}@{t.get('sl_pct',0)}%")
    print(f"{sym}: n={p['n_trades']} WR={p['win_rate']:.0f}% RR={p['avg_rr']:.2f}x bear={bears}")
    for e in entries:
        print(f"   {e}")

print("="*60)
print("DONE")
