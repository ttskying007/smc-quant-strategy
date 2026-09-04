#!/usr/bin/env python3
"""V27 Full Market Scan — Signal-Driven Immediate Entry (Corrected)"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts')
from v11.rolling_backtest_v27 import *

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v27')
OUTPUT_DIR.mkdir(exist_ok=True)

symbols = sorted([f.stem.replace('_daily_300','').replace('_','.') for f in CACHE_DIR.glob('*_daily_300.json')])
print(f"V27 Full Market — {len(symbols)} stocks")

all_stocks=[]; all_trades=[]; t_start=time.time()

for idx,sym in enumerate(symbols):
    ohlcv=load_ohlcv(sym)
    if not ohlcv: continue
    result = backtest_stock_v27(ohlcv, sym)
    if result:
        p = result['perf']
        all_trades.extend(result['trades'])
        all_stocks.append({'symbol':sym,'n_trades':p['n_trades'],'win_rate':round(p['win_rate'],1),
                          'avg_rr':round(p['avg_rr'],2),'profit_factor':round(p['profit_factor'],1),
                          'swing_sl_pct':round(p['swing_sl_pct'],1),'avg_pnl':round(p['avg_pnl'],2),
                          'phase':p['phase']})
    
    if (idx+1)%500==0:
        print(f"  [{idx+1}/{len(symbols)}] {len(all_stocks)} tradable | {(time.time()-t_start):.0f}s")
        json.dump({'stocks':all_stocks,'trades':all_trades[:5000],'processed':idx+1},
                  open(OUTPUT_DIR/'checkpoint.json','w'),default=str)

total_time=time.time()-t_start
n=len(all_trades); wins=sum(1 for t in all_trades if t['won'])
wr=wins/n*100
wp=sum(t['pnl_pct'] for t in all_trades if t['won'])
lp=abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
pf=wp/lp if lp>0 else 999
rr=sum(t['rr'] for t in all_trades)/n
pnl=sum(t['pnl_pct'] for t in all_trades)/n

print(f"\n{'='*70}")
print(f"V27 FULL MARKET — {len(all_stocks)}/{len(symbols)} | {total_time:.0f}s")
print(f"{'='*70}")
print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
print(f"  WR>=80%: {sum(1 for s in all_stocks if s['win_rate']>=80)}")
print(f"  Swing SL: {sum(1 for t in all_trades if t.get('sl_type')=='swing')}/{n}")

outpath=OUTPUT_DIR/'v27_full_merged.json'
json.dump({'timestamp':time.time(),'config':{'version':'V27','signal_driven':True},
           'summary':{'total_symbols':len(symbols),'tradable':len(all_stocks),
                      'total_trades':n,'win_rate':round(wr,1),'avg_rr':round(rr,2),
                      'profit_factor':round(pf,2),'avg_pnl':round(pnl,2)},
           'stocks':all_stocks,'all_trades':all_trades},
          open(outpath,'w'),ensure_ascii=False,indent=2,default=str)
print(f"\nSaved: {outpath}")
