#!/usr/bin/env python3
"""
V16 Full Market Scanner — All 4800 stocks + ETFs + Indices
==========================================================
Run V16 strategy on FULL market using parallel workers.
"""
import json, sys, time, math, logging, concurrent.futures
from pathlib import Path

sys.path.insert(0, '/root/.hermes/scripts')
logging.basicConfig(level=logging.WARNING)
from v11.rolling_backtest_v15 import *

# Override for full scan
MAX_STOCKS = 99999  # no limit
BATCH_SIZE = 500
NUM_WORKERS = 4

OUTPUT_DIR = Path('/root/.hermes/smc_opt_v16')
OUTPUT_DIR.mkdir(exist_ok=True)

def scan_batch(symbols, batch_id):
    """Scan a batch of symbols"""
    batch_trades = []
    batch_stocks = []
    for idx, sym in enumerate(symbols):
        ohlcv = load_ohlcv(sym)
        if not ohlcv: continue
        result = backtest_stock(ohlcv, sym)
        trades = result.get('trades', [])
        perf = result.get('perf', {})
        
        if trades:
            stock_result = {
                'symbol': sym, **perf,
                'n_signals': result.get('n_signals', 0),
                'phase': result.get('phase', '?'),
            }
            batch_stocks.append(stock_result)
            batch_trades.extend(trades)
            
            print(f"  [B{batch_id}-{idx:3d}] {sym:12s} "
                  f"t={perf['n_trades']:2d} WR={perf['win_rate']:.0f}% "
                  f"RR={perf['avg_rr']:.1f}x swing={perf.get('swing_sl_pct',0):.0f}%")
        
        if (idx + 1) % 50 == 0:
            time.sleep(0.5)  # rate limit
    
    return batch_stocks, batch_trades


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print(f"V16 FULL MARKET SCAN — {len(symbols)} symbols")
    print(f"  Parallel: {NUM_WORKERS} workers | Batch: {BATCH_SIZE}")
    print(f"  Swing dist <= {SWING_MAX_DISTANCE} | SL capped {SL_CAP}% | OB skip no-swing")
    print(f"{'='*80}")
    
    all_stocks = []
    all_trades = []
    t_start = time.time()
    
    # Split into batches
    batches = []
    for i in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[i:i+BATCH_SIZE]
        batches.append((batch, i // BATCH_SIZE))
    
    print(f"Total batches: {len(batches)}")
    
    # Process sequentially to avoid API rate limit issues (using cache)
    for batch_syms, batch_id in batches:
        t0 = time.time()
        stocks, trades = scan_batch(batch_syms, batch_id)
        
        all_stocks.extend(stocks)
        all_trades.extend(trades)
        
        elapsed = time.time() - t0
        print(f"\n  === Batch {batch_id} done: {len(stocks)} tradable, "
              f"{len(trades)} trades in {elapsed:.1f}s ===\n")
        
        # Save intermediate
        if len(trades) > 0:
            n = len(trades)
            wins = sum(1 for t in trades if t['won'])
            wr = wins / n * 100
            outpath = OUTPUT_DIR / f'batch_{batch_id*BATCH_SIZE}_{(batch_id+1)*BATCH_SIZE}.json'
            outpath.write_text(json.dumps({
                'timestamp': time.time(),
                'batch_id': batch_id,
                'stocks': stocks, 'all_trades': trades,
                'summary': {'n_trades': n, 'win_rate': round(wr, 1)},
            }, ensure_ascii=False, default=str))
    
    # Final summary
    total_time = time.time() - t_start
    print(f"\n{'='*80}")
    print(f"V16 FULL MARKET DONE — {len(all_stocks)}/{len(symbols)} | {total_time:.0f}s")
    print(f"{'='*80}")
    
    if all_trades:
        n = len(all_trades)
        wins = sum(1 for t in all_trades if t['won'])
        wr = wins / n * 100
        win_pnl = sum(t['pnl_pct'] for t in all_trades if t['won'])
        loss_pnl = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
        pf = win_pnl / loss_pnl if loss_pnl > 0 else 999
        avg_rr = sum(t['rr'] for t in all_trades) / n
        avg_pnl = sum(t['pnl_pct'] for t in all_trades) / n
        sw = [t for t in all_trades if t.get('sl_type') == 'swing']
        sw_wr = sum(1 for t in sw if t['won'])/len(sw)*100 if sw else 0
        fx = [t for t in all_trades if t.get('sl_type') != 'swing']
        fx_wr = sum(1 for t in fx if t['won'])/len(fx)*100 if fx else 0
        
        n80 = sum(1 for s in all_stocks if s['win_rate'] >= 80)
        n70 = sum(1 for s in all_stocks if s['win_rate'] >= 70)
        n60 = sum(1 for s in all_stocks if s['win_rate'] >= 60)
        
        print(f"\n  Trades: {n} | WR: {wr:.1f}% | Avg RR: {avg_rr:.2f}x | "
              f"PF: {pf:.2f} | Avg P&L: {avg_pnl:+.2f}%")
        print(f"  Swing SL: {len(sw)}/{n} ({len(sw)/n*100:.0f}%) | "
              f"Swing WR: {sw_wr:.1f}% | Fixed WR: {fx_wr:.1f}%")
        print(f"  WR>=60%: {n60} stocks | WR>=70%: {n70} | WR>=80%: {n80}")
        print(f"  Avg hold: {sum(t['hold_bars'] for t in all_trades)/n:.1f} bars")
    
    # Save final merged
    if all_trades:
        outpath = OUTPUT_DIR / 'v16_full_merged.json'
        outpath.write_text(json.dumps({
            'timestamp': time.time(),
            'config': {
                'version': 'V16', 'swing_max_distance': SWING_MAX_DISTANCE,
                'sl_cap': SL_CAP, 'sl_fixed': SL_FIXED, 'tp_fixed': TP_FIXED,
            },
            'summary': {
                'total_symbols': len(symbols), 'tradable': len(all_stocks),
                'total_trades': len(all_trades),
                'win_rate': round(wr, 1) if all_trades else 0,
                'avg_rr': round(avg_rr, 2) if all_trades else 0,
                'profit_factor': round(pf, 2) if all_trades else 0,
                'avg_pnl': round(avg_pnl, 2) if all_trades else 0,
            },
            'stocks': all_stocks, 'all_trades': all_trades,
        }, ensure_ascii=False, indent=2, default=str))
        print(f"\n  Saved: {outpath}")

if __name__ == '__main__':
    main()
