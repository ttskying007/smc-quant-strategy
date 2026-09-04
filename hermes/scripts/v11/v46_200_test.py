#!/usr/bin/env python3
"""V46 200只验证"""
import json, sys, time
sys.path.insert(0, '/root/.hermes/scripts')
from v11.v46_engine import run_backtest, load_ohlcv, OUTPUT_DIR, CACHE_DIR

# 加载股票列表
symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_daily_300.json')])[:200]
print(f"Testing {len(symbols)} stocks...")

results, all_trades, t = run_backtest(symbols, label="V46-200")

# Save
output = {
    'n_stocks': len(results),
    'n_trades': len(all_trades),
    'label': 'V46-200',
    'time_sec': round(t, 1),
    'stock_results': results,
}

if all_trades:
    n = len(all_trades)
    wins = sum(1 for t in all_trades if t['won'])
    output['win_rate'] = round(wins/n*100, 1)
    output['avg_rr'] = round(sum(t['rr'] for t in all_trades)/n, 2)
    wp = sum(t['pnl_pct'] for t in all_trades if t['won'])
    lp = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
    output['profit_factor'] = round(wp/lp, 2) if lp > 0 else 999
    output['avg_pnl'] = round(sum(t['pnl_pct'] for t in all_trades)/n, 2)

with open(OUTPUT_DIR / 'v46_200_results.json', 'w') as f:
    json.dump(output, f, indent=2, default=str)

print(f"\nSaved to {OUTPUT_DIR}/v46_200_results.json")
