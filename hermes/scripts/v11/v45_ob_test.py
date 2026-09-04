#!/usr/bin/env python3
"""V45 OB-only 200-stock validation & full 4800 scan"""
import sys, json, time
sys.path.insert(0, '/root/.hermes/scripts')
from pathlib import Path

OUTPUT_DIR = Path('/root/.hermes/smc_opt_v45')
CACHE_DIR = Path('/root/.hermes/kline_cache')

symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_daily_300.json')])

# Patch engine for OB-only
if 'v11.v45_engine' in sys.modules:
    del sys.modules['v11.v45_engine']
import v11.v45_engine as eng
eng.TRADE_SIGNAL_TYPES = {'OB_Bull'}
eng.ENTRY_SIGNAL_TYPES = {'OB_Bull'}
eng.QUALITY_THRESHOLDS = {'OB_Bull': 0.50}
eng.ENABLE_BEAR = False
eng.ENTRY_AT_ZONE = True
eng.STOCK_PARAMS_CACHE = {}

# 200-stock validation
t0 = time.time()
result = eng.run_backtest(symbols[:200], "OB-only-200")
elapsed = time.time() - t0

if result:
    s = result['summary']
    print(f"\n=== OB-only 200-stock ===")
    print(f"Stocks: {len(result['stock_results'])} | Trades: {s['n_trades']}")
    print(f"WR: {s['win_rate']:.1f}% | RR: {s['avg_rr']:.2f}x | PF: {s['profit_factor']:.0f} | P&L: {s['avg_pnl']:+.2f}%")
    print(f"Time: {elapsed:.0f}s")
    
    out = OUTPUT_DIR / 'v45_ob200.json'
    json.dump(result['summary'], open(str(out), 'w'))
    print(f"Saved: {out}")
