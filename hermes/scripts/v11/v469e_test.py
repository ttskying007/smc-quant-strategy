#!/usr/bin/env python3
"""V469-E: 统一松trailing 1.5x 测试 (200只)"""
import sys, json, importlib
sys.path.insert(0, '/root/.hermes/scripts')

# Force fresh import
if 'v11.v469_final' in sys.modules:
    del sys.modules['v11.v469_final']
import v11.v469_final as eng
importlib.reload(eng)

symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                 for f in eng.CACHE_DIR.glob('*_60min_200.json')])[:220]

eng.MIN_PROJECTED_RR = 6.0
eng.SWING_SKIP = 3
eng.POI_RETRACE_WINDOW = 50

result = eng.run_backtest(symbols, 'V469E-200')
trades = result.get('all_trades', [])
n = len(trades)
wins = sum(1 for t in trades if t.get('won'))
rr = sum(t.get('rr',0) for t in trades)/n if n else 0
pnl = sum(t.get('pnl_pct',0) for t in trades)/n if n else 0
hold = sum(t.get('hold_bars',0) for t in trades)/n if n else 0

print()
print('=== V469-E: 统一松trailing 1.5x ===')
print(f'Stocks: {len(result["stock_results"])}/{len(symbols)}')
print(f'Trades: {n} | WR: {wins/n*100:.1f}% | RR: {rr:.2f}x | P&L: {pnl:+.2f}% | Hold: {hold:.1f}b')
print()
print(f'V468 200-stock: WR=68.6% RR=6.77x P&L=+2.54% n=35')
print(f'V469-E 200-stock: WR={wins/n*100:.1f}% RR={rr:.2f}x P&L={pnl:+.2f}% n={n}')

# Save results
out = {
    'version': 'V469-E',
    'n_stocks': len(result['stock_results']),
    'n_trades': n,
    'wr': round(wins/n*100, 1) if n else 0,
    'rr': round(rr, 2),
    'pnl': round(pnl, 2),
    'hold': round(hold, 1),
}
json.dump(out, open('/root/.hermes/smc_opt_v469/v469e_results.json', 'w'))
print(f'\nSaved to smc_opt_v469/v469e_results.json')
