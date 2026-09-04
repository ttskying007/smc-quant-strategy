#!/usr/bin/env python3
"""V469-B 反向分级Trailing — 200只验证"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
import v11.v469_final as eng

symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                 for f in eng.CACHE_DIR.glob('*_60min_200.json')])
# Take first 220, skip first 20 (banks)
symbols = symbols[:220]

eng.MIN_PROJECTED_RR = 6.0
eng.SWING_SKIP = 3
eng.POI_RETRACE_WINDOW = 50

result = eng.run_backtest(symbols, 'V469B-200')
trades = result.get('all_trades', [])
n = len(trades)
wins = sum(1 for t in trades if t.get('won'))
rr = sum(t.get('rr',0) for t in trades)/n if n else 0
pnl = sum(t.get('pnl_pct',0) for t in trades)/n if n else 0
hold = sum(t.get('hold_bars',0) for t in trades)/n if n else 0

print()
print('=== V469-B: 反向分级Trailing (A紧/C松) ===')
print(f'Stocks: {len(result["stock_results"])}/{len(symbols)}')
print(f'Trades: {n} | WR: {wins/n*100:.1f}% | RR: {rr:.2f}x | P&L: {pnl:+.2f}% | Hold: {hold:.1f}b')

# Grade breakdown
gs = {'A':[],'B':[],'C':[]}
for t in trades:
    g = t.get('signal_grade','C') or 'C'
    if g in gs: gs[g].append(t)
for g in ['A','B','C']:
    gt = gs[g]
    if gt:
        gw = sum(1 for t in gt if t.get('won'))
        gr = sum(t.get('rr',0) for t in gt)/len(gt)
        gp = sum(t.get('pnl_pct',0) for t in gt)/len(gt)
        print(f'  Grade {g}: {len(gt)} trades | WR={gw/len(gt)*100:.1f}% | RR={gr:.2f}x | P&L={gp:+.2f}%')

print()
print('V468 200-stock (ref): WR=68.6% RR=6.77x P&L=+2.54% n=35')
print(f'V469-B 200-stock:     WR={wins/n*100:.1f}% RR={rr:.2f}x P&L={pnl:+.2f}% n={n}')

# Save trade level data for frontend
json.dump(result.get('stock_results', []), open('/root/.hermes/smc_opt_v469/v469b_stocks.json','w'))
json.dump(trades, open('/root/.hermes/smc_opt_v469/v469b_trades.json','w'))
print('Results saved to smc_opt_v469/v469b_*.json')
