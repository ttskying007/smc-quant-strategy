#!/usr/bin/env python3
"""V46.3 策略C 全量4800扫描 — OB-only + 反转过滤 + V45入口"""
import json, sys, time
sys.path.insert(0, '/root/.hermes/scripts')

if 'v11.v463_engine' in sys.modules:
    del sys.modules['v11.v463_engine']
from v11.v463_engine import run_backtest, CACHE_DIR, OUTPUT_DIR

symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_daily_300.json')])
print(f"Full scan: {len(symbols)} stocks")

t0 = time.time()
result = run_backtest(symbols, label="V463-OB-Rev-FULL")
elapsed = time.time() - t0

if result:
    summary = {
        'n_stocks': result['summary']['n_stocks'],
        'n_trades': result['summary']['n_trades'],
        'win_rate': result['summary']['win_rate'],
        'avg_rr': result['summary']['avg_rr'],
        'profit_factor': result['summary']['profit_factor'],
        'avg_pnl': result['summary']['avg_pnl'],
        'total_time_sec': round(elapsed, 1),
    }
    out_path = OUTPUT_DIR / 'v463_full.json'
    json.dump(summary, open(str(out_path), 'w'))
    print(f"\nFull scan saved: {out_path}")
    print(f"V463-OB-Rev-FULL: {json.dumps(summary)}")
