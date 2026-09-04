#!/usr/bin/env python3
"""V20 Multi-TF Backtest: Weekly trend → Daily signal → 60min entry"""
import json, sys, time
sys.path.insert(0, '/root/.hermes/scripts')
from pathlib import Path
from v11.signals_v19 import detect_all_signals_v19
from v11.v19_backtest_engine import backtest_v19
from v11.multitf_filter import get_weekly_trend, refine_entry_60min

CACHE_W = Path('/root/.hermes/kline_cache_weekly')
CACHE_60M = Path('/root/.hermes/kline_cache_60min')
CACHE_D = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v20')
OUT.mkdir(exist_ok=True)

# Get stocks that have both daily + weekly + 60min data
daily_files = sorted(CACHE_D.glob('*_daily_300.json'))
symbols = []
for f in daily_files:
    sym = f.stem.replace('_daily_300','').replace('_','.')
    wf = CACHE_W / f'{sym.replace(".","_")}_weekly_100.json'
    mf = CACHE_60M / f'{sym.replace(".","_")}_60min_200.json'
    if wf.exists() and mf.exists():
        symbols.append(sym)

print(f"Stocks with full multi-TF data: {len(symbols)}")

all_trades = []
stock_results = []
t0 = time.time()

for i, sym in enumerate(symbols):
    # Load daily
    dpath = CACHE_D / f'{sym.replace(".","_")}_daily_300.json'
    ohlcv = json.loads(dpath.read_bytes())
    
    # V19 signals
    signals, stats, swings, swings_dict = detect_all_signals_v19(ohlcv)
    
    # Weekly trend filter
    trend = get_weekly_trend(sym)
    if trend == 'bearish':
        continue  # Skip bearish weekly trend for long-only
    
    # Filter entries
    entries = [s for s in signals if s.type in ('FVG_Bull','OB_Bull')]
    entries.sort(key=lambda s: s.idx)
    
    # Backtest with 60min entry refinement
    trades = backtest_v19(sym, ohlcv, signals, swings_dict)
    
    # Apply 60min entry refinement
    for t in trades:
        refined = refine_entry_60min(sym, t.entry_idx, t.entry_price, ohlcv)
        if refined < t.entry_price:
            t.entry_price = refined
            t.pnl_pct = (t.exit_price - refined) / refined * 100
    
    if trades:
        wins = sum(1 for t in trades if t.pnl_pct > 0)
        wr = wins/len(trades)*100
        avg_pnl = sum(t.pnl_pct for t in trades)/len(trades)
        stock_results.append({'symbol':sym,'n_trades':len(trades),'wr':round(wr,1),'avg_pnl':round(avg_pnl,4),'weekly_trend':trend})
        all_trades.extend(trades)
    
    if (i+1) % 20 == 0:
        print(f"  {i+1}/{len(symbols)} ({time.time()-t0:.0f}s)")

total = len(all_trades)
if total:
    wins = sum(1 for t in all_trades if t.pnl_pct > 0)
    wr = wins/total*100
    avg_pnl = sum(t.pnl_pct for t in all_trades)/total
    avg_hold = sum(t.hold_bars for t in all_trades)/total
    em = {}; [em.update({t.exit_method:em.get(t.exit_method,0)+1}) for t in all_trades]
    
    print(f"\n=== V20 Multi-TF ({time.time()-t0:.0f}s) ===")
    print(f"Stocks with full data: {len(symbols)}")
    print(f"Active (weekly bullish): {len(stock_results)}")
    print(f"Trades: {total} | WR: {wr:.1f}% | P&L: {avg_pnl:+.2f}% | Hold: {avg_hold:.1f}")
    print(f"Exit: {em}")
    
    json.dump({
        'summary':{'engine':'V20','stocks_full_data':len(symbols),'stocks_active':len(stock_results),'total_trades':total,'wr':round(wr,1),'avg_pnl':round(avg_pnl,4),'avg_hold_bars':round(avg_hold,1),'exit_methods':{str(k):v for k,v in em.items()}},
        'stock_results':stock_results
    }, open(OUT/'v20_multitf.json','w'), indent=2, ensure_ascii=False)
    print(f"Saved to {OUT/'v20_multitf.json'}")
else:
    print("No trades — check data")
