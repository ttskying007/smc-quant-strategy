#!/usr/bin/env python3
"""V46 全量4800扫描"""
import json, sys, time
sys.path.insert(0, '/root/.hermes/scripts')
from v11.v46_engine import run_backtest, OUTPUT_DIR, CACHE_DIR
from pathlib import Path

symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_daily_300.json')])
print(f"Full scan: {len(symbols)} stocks")

t0 = time.time()
results, all_trades, total_time = run_backtest(symbols, "V46-FULL")
elapsed = time.time() - t0

# Build summary
summary = {
    'n_stocks': len(results),
    'n_trades': len(all_trades),
    'total_time_sec': round(total_time, 1),
    'elapsed_sec': round(elapsed, 1),
}

if all_trades:
    n = len(all_trades)
    wins = sum(1 for t in all_trades if t['won'])
    summary['win_rate'] = round(wins/n*100, 1)
    summary['avg_rr'] = round(sum(t['rr'] for t in all_trades)/n, 2)
    wp = sum(t['pnl_pct'] for t in all_trades if t['won'])
    lp = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
    summary['profit_factor'] = round(wp/lp, 2) if lp > 0 else 999
    summary['avg_pnl'] = round(sum(t['pnl_pct'] for t in all_trades)/n, 2)
    summary['retest_pct'] = round(sum(1 for t in all_trades if t.get('retest_bars',0)>0)/n*100, 1)

# Save full results
output = {
    'summary': summary,
    'stock_results': results,
}
out_path = OUTPUT_DIR / 'v46_full.json'
with open(out_path, 'w') as f:
    json.dump(output, f, indent=2, default=str)

print(f"\n{'='*60}")
print(f"V46 FULL 4800 COMPLETE")
print(f"{'='*60}")
for k, v in summary.items():
    print(f"  {k}: {v}")
print(f"Saved: {out_path}")
