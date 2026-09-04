#!/usr/bin/env python3
"""测试V5.5优化结果"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')

# Load best params
with open('/root/.hermes/smc_opt_v55/final.json') as f:
    data = json.load(f)

bp = data['best_params']

# Relax for more coverage
bp['min_sources'] = 1
bp['min_score'] = 1.5
bp['max_trades'] = 6

from smc_v55 import backtest_all, score_trades, load_bars, get_vol

stocks = ['300231.SZ','002415.SZ','300750.SZ','688981.SH','300059.SZ',
          '002230.SZ','002594.SZ','300124.SZ','600030.SH','601318.SH']

all_tr = []
stocks_ok = 0
stocks_sig = 0

for sym in stocks:
    bars = load_bars(sym)
    if not bars or len(bars) < 60:
        continue
    vol = get_vol(bars)
    if vol['atr_pct'] < 1.5:
        continue
    stocks_ok += 1
    tr = backtest_all(bars, bp)
    if tr:
        stocks_sig += 1
        all_tr.extend(tr)

s = score_trades(all_tr)
print(f"=== V5.5 Relaxed Evaluation ({len(stocks)} stocks) ===")
for k in ['score','wr','pf','n','ret','n_wins','n_losses','stocks_sig','stocks_ok']:
    print(f"  {k}: {s.get(k,0)}")

# Show per-stock breakdown
print("\nPer-stock:")
for sym in stocks:
    bars = load_bars(sym)
    if not bars or len(bars) < 60:
        continue
    vol = get_vol(bars)
    if vol['atr_pct'] < 1.5:
        print(f"  {sym}: skipped (ATR={vol['atr_pct']}%)")
        continue
    tr = backtest_all(bars, bp)
    if tr:
        ss = score_trades(tr)
        print(f"  {sym}: Trades={ss['n']} WR={ss['wr']}% PF={ss['pf']} Ret={ss['ret']}%")
    else:
        print(f"  {sym}: No trades")