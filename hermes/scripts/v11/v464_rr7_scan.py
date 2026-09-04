#!/usr/bin/env python3
"""V464 RR7 全量4800扫描 — MIN_PROJECTED_RR=7.0"""
import json, sys, time
sys.path.insert(0, '/root/.hermes/scripts')

for mod in list(sys.modules.keys()):
    if 'v464_engine' in mod:
        del sys.modules[mod]
from v11.v464_engine_b import run_backtest, CACHE_DIR, OUTPUT_DIR

symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_daily_300.json')])
print(f"Full scan: {len(symbols)} stocks")

t0 = time.time()
result = run_backtest(symbols, label="V464-RR7")
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
    out_path = OUTPUT_DIR / 'v464_rr7_full.json'
    json.dump(summary, open(str(out_path), 'w'))
    print(f"\nFull scan saved: {out_path}")
    print(f"V464-RR7: {json.dumps(summary)}")
