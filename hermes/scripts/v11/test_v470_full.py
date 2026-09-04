#!/usr/bin/env python3
"""V470 full 4552 stock scan"""
import sys, json, time
from pathlib import Path
from collections import Counter
sys.path.insert(0, '/root/.hermes/scripts')

from v470_engine import load_ohlcv, backtest_stock_v45, CACHE_DIR, OUTPUT_DIR

OUTPUT_DIR.mkdir(exist_ok=True)

all_symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_60min_200.json')])
print(f"V470 full scan: {len(all_symbols)} stocks")

trades = []
results = []
t0 = time.time()

for idx, sym in enumerate(all_symbols):
    ohlcv = load_ohlcv(sym)
    if not ohlcv:
        continue

    try:
        result = backtest_stock_v45(ohlcv, sym)
    except Exception as e:
        print(f"  [{idx+1:4d}/{len(all_symbols)}] {sym:12s} ERR")
        continue

    if result:
        p = result['perf']
        trades.extend(result['trades'])
        results.append({'symbol': sym, **p})
        print(f"  [{idx+1:4d}/{len(all_symbols)}] {sym:12s} n={p['n_trades']:2d} WR={p['win_rate']:.0f}% RR={p['avg_rr']:.2f}x")
    else:
        if (idx + 1) % 100 == 0:
            print(f"  [{idx+1:4d}/{len(all_symbols)}] ... {time.time()-t0:.0f}s")

    if (idx + 1) % 200 == 0:
        time.sleep(0.1)

tt = time.time() - t0
print(f"\n{'='*60}")
print(f"V470 FULL 4552 RESULTS ({tt:.0f}s)")
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

    sl_types = Counter(t.get('sl_type', 'unknown') for t in trades)
    tp_types = Counter(t.get('tp_type', 'none') for t in trades)
    exit_methods = Counter(t.get('exit_method', 'unknown') for t in trades)
    directions = Counter(t.get('direction', 'unknown') for t in trades)
    entry_types = Counter(t.get('entry_type', 'unknown') for t in trades)

    print(f"  Time: {tt:.0f}s | Stocks: {len(results)}/{len(all_symbols)}")
    print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
    print(f"  Avg hold: {sum(holds)/len(holds):.1f} bars")
    print(f"  POI activated: {sum(1 for t in trades if t.get('poi_activated', False))}")

    print(f"\n  Direction:")
    for d, cnt in directions.most_common():
        dt = [t for t in trades if t.get('direction') == d]
        wr_d = sum(1 for t in dt if t['won'])/cnt*100
        rr_d = sum(t['rr'] for t in dt)/cnt
        pnl_d = sum(t['pnl_pct'] for t in dt)/cnt
        print(f"    {d}: n={cnt:5d} WR={wr_d:.1f}% RR={rr_d:.2f}x P&L={pnl_d:+.2f}%")

    print(f"\n  Entry types: {dict(entry_types.most_common())}")
    print(f"\n  SL types: {dict(sl_types.most_common(5))}")
    print(f"\n  TP types: {dict(tp_types.most_common(5))}")
    print(f"\n  Exit methods: {dict(exit_methods.most_common())}")

    # Save
    trades.sort(key=lambda t: t['entry_idx'])
    Path(f'{OUTPUT_DIR}/v470_full_trades.json').write_text(json.dumps(trades, indent=2))
    Path(f'{OUTPUT_DIR}/v470_full_stocks.json').write_text(json.dumps(results, indent=2))
    print(f"\n  Saved to smc_opt_v470/")
else:
    print("  NO TRADES")

# Perf summary
summary = {
    'n_stocks': len(results),
    'n_trades': len(trades),
    'win_rate': round(wr, 1) if trades else 0,
    'avg_rr': round(rr, 2) if trades else 0,
    'profit_factor': round(pf, 2) if trades else 0,
    'avg_pnl': round(pnl, 2) if trades else 0,
}
Path(f'{OUTPUT_DIR}/v470_summary.json').write_text(json.dumps(summary, indent=2))
print(f"\n  Summary: {json.dumps(summary, indent=2)}")
