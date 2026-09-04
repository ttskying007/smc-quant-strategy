#!/usr/bin/env python3
"""V470 200-stock quick test"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts')
sys.path.insert(0, '/root/.hermes/scripts/v11')

from v470_engine import load_ohlcv, backtest_stock_v45, run_backtest

CACHE_DIR = Path('/root/.hermes/kline_cache_60min')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v470')
OUTPUT_DIR.mkdir(exist_ok=True)

# Load symbols
fpath = '/root/.hermes/kline_cache_60min/symbols_4552.json'
if Path(fpath).exists():
    all_symbols = json.loads(Path(fpath).read_text())
else:
    all_symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                     for f in CACHE_DIR.glob('*_60min_200.json')])

test_syms = all_symbols[:200]
print(f"Testing V470 on {len(test_syms)} stocks")

trades = []
results = []
t0 = time.time()

for idx, sym in enumerate(test_syms):
    ohlcv = load_ohlcv(sym)
    if not ohlcv:
        print(f"  [{idx+1:3d}/{len(test_syms)}] {sym:12s} NO-DATA")
        continue

    try:
        result = backtest_stock_v45(ohlcv, sym)
    except Exception as e:
        print(f"  [{idx+1:3d}/{len(test_syms)}] {sym:12s} ERR: {e}")
        continue

    if result:
        p = result['perf']
        trades.extend(result['trades'])
        results.append({'symbol': sym, **p})
        print(f"  [{idx+1:3d}/{len(test_syms)}] {sym:12s} n={p['n_trades']:2d} WR={p['win_rate']:.0f}% RR={p['avg_rr']:.2f}x")
    else:
        print(f"  [{idx+1:3d}/{len(test_syms)}] {sym:12s} SKIP")

    if (idx + 1) % 50 == 0:
        time.sleep(0.1)

tt = time.time() - t0
print(f"\n{'='*60}")
print(f"V470 200-stock RESULTS ({tt:.0f}s)")
print(f"{'='*60}")

if trades:
    n = len(trades)
    wins = sum(1 for t in trades if t['won'])
    wr = wins / n * 100
    wp = sum(t['pnl_pct'] for t in trades if t['won'])
    lp = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
    pf = wp / lp if lp > 0 else 999
    rr = sum(t['rr'] for t in trades) / n
    pnl = sum(t['pnl_pct'] for t in trades) / n
    holds = [t['hold_bars'] for t in trades]
    
    print(f"  Stocks: {len(results)}/{len(test_syms)}")
    print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
    print(f"  Avg hold: {sum(holds)/len(holds):.1f} bars")
    print(f"  POI activated: {sum(1 for t in trades if t.get('poi_activated', False))}")
    
    # Direction breakdown
    bull = [t for t in trades if t.get('direction') == 'bull']
    if bull:
        wr_b = sum(1 for t in bull if t['won'])/len(bull)*100
        rr_b = sum(t['rr'] for t in bull)/len(bull)
        pnl_b = sum(t['pnl_pct'] for t in bull)/len(bull)
        print(f"  Bull: n={len(bull)} WR={wr_b:.1f}% RR={rr_b:.2f}x P&L={pnl_b:+.2f}%")
    
    # Entry type breakdown
    from collections import Counter
    et = Counter(t.get('entry_type', '?') for t in trades)
    print(f"  Entry types: {dict(et.most_common())}")
    
    # Save results
    trades.sort(key=lambda t: t['entry_idx'])
    Path(f'{OUTPUT_DIR}/v470_200_trades.json').write_text(json.dumps(trades, indent=2))
    Path(f'{OUTPUT_DIR}/v470_200_results.json').write_text(json.dumps(results, indent=2))
    print(f"\n  Results saved to smc_opt_v470/")
else:
    print("  NO TRADES FOUND")
