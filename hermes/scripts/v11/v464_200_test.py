#!/usr/bin/env python3
"""V464 200只验证 — 三管齐下RR优化"""
import sys, json, time
sys.path.insert(0, '/root/.hermes/scripts')
import v464_engine as e
from pathlib import Path

# 取前200只
all_syms = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                 for f in Path('/root/.hermes/kline_cache').glob('*_daily_300.json')])
syms = all_syms[:200]

result = e.run_backtest(syms, "V464-RR-OPT")

if result and result.get('all_trades'):
    out = Path('/root/.hermes/smc_opt_v464/v464_200.json')
    out.parent.mkdir(exist_ok=True)
    result['stock_results'].sort(key=lambda r: -r['n_trades'])
    json.dump(result['all_trades'], open(str(out), 'w'))
    print(f"\n  Saved: {out}")
