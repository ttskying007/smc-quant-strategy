#!/usr/bin/env python3
"""V23 Full Market Scan V2 — Fixed with checkpoints"""
import json, sys, time, os
from pathlib import Path

sys.path.insert(0, '/root/.hermes/scripts')

# Import step by step to catch errors
print("Loading V23 engine...")
import v11.signals_v11 as sig
import v11.sequencer_v11 as seq
import v11.resonance_v11 as res
import v11.adaptive_params as adp
import v11.weekly_trend as wt
from v11.rolling_backtest_v23 import *

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v23')
OUTPUT_DIR.mkdir(exist_ok=True)

symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                  for f in CACHE_DIR.glob('*_daily_300.json')])

print(f"V23 Full Market — {len(symbols)} stocks")
print(f"Phase params: {PHASE_PARAMS}")

all_stocks = []
all_trades = []
t_start = time.time()
checkpoint = OUTPUT_DIR / 'checkpoint.json'

# Load checkpoint if exists
if checkpoint.exists():
    cp = json.loads(checkpoint.read_text())
    all_stocks = cp.get('stocks', [])
    all_trades = cp.get('trades', [])
    processed = cp.get('processed', 0)
    print(f"Resumed from checkpoint: {processed} done, {len(all_stocks)} tradable")
else:
    processed = 0

try:
    for idx in range(processed, len(symbols)):
        sym = symbols[idx]
        ohlcv = load_ohlcv(sym)
        if ohlcv:
            result = backtest_stock_v23(ohlcv, sym)
            if result:
                all_stocks.append({'symbol': sym, **result['perf'],
                                  'n_signals': result['n_signals']})
                all_trades.extend(result['trades'])
        
        if (idx + 1) % 100 == 0:
            elapsed = time.time() - t_start
            tradable = len(all_stocks)
            # Save checkpoint
            json.dump({'stocks': all_stocks[:500], 'trades': all_trades[:10000], 
                       'processed': idx + 1}, open(checkpoint, 'w'), default=str)
            print(f"  [{idx+1}/{len(symbols)}] {tradable} tradable | {elapsed:.0f}s")
        
        if (idx + 1) % 500 == 0:
            # Save batch
            batch_out = OUTPUT_DIR / f'batch_{(idx+1)-500}_{idx+1}.json'
            json.dump({'stocks': all_stocks[-500:], 'trades': all_trades[-(min(5000, len(all_trades))):]},
                       open(batch_out, 'w'), indent=2, default=str)

except KeyboardInterrupt:
    print("\nInterrupted, saving checkpoint...")
    json.dump({'stocks': all_stocks[:500], 'trades': all_trades[:10000],
               'processed': idx}, open(checkpoint, 'w'), default=str)
    raise

total_time = time.time() - t_start
n = len(all_trades)
wins = sum(1 for t in all_trades if t['won'])
wr = wins/n*100 if n else 0
win_pnl = sum(t['pnl_pct'] for t in all_trades if t['won'])
loss_pnl = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
pf = win_pnl/loss_pnl if loss_pnl > 0 else 999
avg_rr = sum(t['rr'] for t in all_trades)/n if n else 0

print(f"\n{'='*70}")
print(f"V23 FULL MARKET — {len(all_stocks)}/{len(symbols)} | {total_time:.0f}s")
print(f"{'='*70}")
print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {avg_rr:.2f}x | PF: {pf:.2f}")
print(f"  WR>=80%: {sum(1 for s in all_stocks if s['win_rate']>=80)}")

outpath = OUTPUT_DIR / 'v23_full_merged.json'
json.dump({
    'timestamp': time.time(),
    'config': {'version':'V23','min_swing_coverage':MIN_SWING_COVERAGE},
    'summary':{'total_symbols':len(symbols),'tradable':len(all_stocks),
               'total_trades':n,'win_rate':round(wr,1),'avg_rr':round(avg_rr,2),
               'profit_factor':round(pf,2)},
    'stocks':all_stocks[:1000], 'all_trades':all_trades[:5000],
}, open(outpath,'w'), ensure_ascii=False, indent=2, default=str)
print(f"\nSaved: {outpath}")
