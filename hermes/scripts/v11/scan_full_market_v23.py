#!/usr/bin/env python3
"""V23 Full Market Scan — Swing Coverage Filter + Phase-Adaptive"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts')
from v11.rolling_backtest_v23 import *

MAX_STOCKS = 99999
BATCH_SIZE = 500
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v23')
OUTPUT_DIR.mkdir(exist_ok=True)

def scan_batch(symbols, batch_id):
    results = []
    for idx, sym in enumerate(symbols):
        ohlcv = load_ohlcv(sym)
        if not ohlcv: continue
        result = backtest_stock_v23(ohlcv, sym)
        if result:
            results.append({'symbol': sym, **result['perf'],
                           'n_signals': result['n_signals']})
            results[-1]['_trades'] = result['trades']
        if (idx+1) % 100 == 0:
            print(f"  [B{batch_id}-{idx:3d}] {sym:12s} {'t='+str(result['perf']['n_trades'])+' WR='+str(result['perf']['win_rate'])+'%' if result else 'SKIP'}")
    return results


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print(f"V23 FULL MARKET — {len(symbols)} stocks")
    print(f"  Swing coverage filter >=30% | Phase-adaptive SL/TP")
    print(f"  Expected: WR~87%, coverage~30%")
    print(f"{'='*80}")
    
    all_stocks, all_trades = [], []; t_start = time.time()
    
    for batch_start in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[batch_start:batch_start+BATCH_SIZE]
        bid = batch_start // BATCH_SIZE
        print(f"\n--- Batch {bid} ({batch_start}-{batch_start+len(batch)}) ---")
        t0 = time.time()
        results = scan_batch(batch, bid)
        elapsed = time.time() - t0
        
        for r in results:
            all_stocks.append({k:v for k,v in r.items() if k != '_trades'})
            all_trades.extend(r.get('_trades', []))
        
        print(f"  Batch {bid}: {len(results)} tradable in {elapsed:.1f}s")
    
    total_time = time.time() - t_start
    print(f"\n{'='*80}")
    print(f"V23 FULL MARKET — {len(all_stocks)}/{len(symbols)} | {total_time:.0f}s")
    print(f"{'='*80}")
    
    if all_trades:
        n = len(all_trades); wins = sum(1 for t in all_trades if t['won'])
        wr = wins/n*100
        win_pnl = sum(t['pnl_pct'] for t in all_trades if t['won'])
        loss_pnl = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
        pf = win_pnl/loss_pnl if loss_pnl > 0 else 999
        avg_rr = sum(t['rr'] for t in all_trades)/n
        avg_pnl = sum(t['pnl_pct'] for t in all_trades)/n
        sw = [t for t in all_trades if t.get('sl_type')=='swing']
        sw_wr = sum(1 for t in sw if t['won'])/len(sw)*100 if sw else 0
        n80 = sum(1 for s in all_stocks if s['win_rate']>=80)
        n70 = sum(1 for s in all_stocks if s['win_rate']>=70)
        
        print(f"\n  Trades: {n} | WR: {wr:.1f}% | RR: {avg_rr:.2f}x | PF: {pf:.2f} | P&L: {avg_pnl:+.2f}%")
        print(f"  Swing SL: {len(sw)}/{n} ({len(sw)/n*100:.0f}%) | WR={sw_wr:.1f}%")
        print(f"  WR>=70%: {n70} | WR>=80%: {n80}")
        
        from collections import Counter
        pc = Counter(s.get('phase','?') for s in all_stocks)
        print(f"  Phases: {dict(pc.most_common())}")
        
        outpath = OUTPUT_DIR / 'v23_full_merged.json'
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'config': {'version':'V23','min_swing_coverage':MIN_SWING_COVERAGE,
                       'phase_params':PHASE_PARAMS,'cycle_mult':dict(CYCLE_SL_MULT)},
            'summary':{'total_symbols':len(symbols),'tradable':len(all_stocks),
                       'total_trades':n,'win_rate':round(wr,1),'avg_rr':round(avg_rr,2),
                       'profit_factor':round(pf,2),'avg_pnl':round(avg_pnl,2)},
            'stocks':all_stocks,'all_trades':all_trades,
        }, open(outpath,'w'), ensure_ascii=False, indent=2, default=str)
        print(f"\n  Saved: {outpath}")

if __name__ == '__main__':
    main()
