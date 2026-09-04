#!/usr/bin/env python3
"""V32 Full Market Scan"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts')
from v11.rolling_backtest_v32 import *

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v32')
OUTPUT_DIR.mkdir(exist_ok=True)

symbols = sorted([f.stem.replace('_daily_300','').replace('_','.') for f in CACHE_DIR.glob('*_daily_300.json')])
print(f"V32 Full Market — {len(symbols)} stocks")

all_stocks=[]; all_trades=[]; t_start=time.time()

for idx,sym in enumerate(symbols):
    result = run_stock(sym)
    if result:
        p = result['perf']
        all_trades.extend(result['trades'])
        all_stocks.append(p)
    if (idx+1)%500==0:
        print(f"  [{idx+1}/{len(symbols)}] {len(all_stocks)} tradable | {(time.time()-t_start):.0f}s")

total_time=time.time()-t_start
n=len(all_trades); wins=sum(1 for t in all_trades if t['won'])
wr=wins/n*100 if n else 0
wp=sum(t['pnl_pct'] for t in all_trades if t['won'])
lp=abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
pf=wp/lp if lp>0 else 999
rr=sum(t['rr'] for t in all_trades)/n if n else 0
pnl=sum(t['pnl_pct'] for t in all_trades)/n if n else 0
n80=sum(1 for s in all_stocks if s['win_rate']>=80)

print(f"\n{'='*70}")
print(f"V32 FULL MARKET — {len(all_stocks)}/{len(symbols)} | {total_time:.0f}s")
print(f"{'='*70}")
print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
print(f"  WR>=80%: {n80}")
print(f"  Swing SL: {sum(1 for t in all_trades if t.get('sl_type')=='swing')}/{n}")

# Save
json.dump({'timestamp':time.time(),'config':{'version':'V32','sl':SL,'breakeven':TRAIL_BREAKEVEN_PCT,'min_rr':MIN_RR},
           'summary':{'total_symbols':len(symbols),'tradable':len(all_stocks),
                      'total_trades':n,'win_rate':round(wr,1),'avg_rr':round(rr,2),
                      'profit_factor':round(pf,2),'avg_pnl':round(pnl,2)},
           'stocks':all_stocks,'all_trades':all_trades},
          open(OUTPUT_DIR/'v32_full_merged.json','w'),ensure_ascii=False,indent=2,default=str)
print(f"\nSaved: {OUTPUT_DIR/'v32_full_merged.json'}")
