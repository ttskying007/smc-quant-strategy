#!/usr/bin/env python3
"""V469_final 全量4552 stock scan — V468 entry + graded trailing"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts')
import v11.v469_final as eng

# ── Params ──
eng.MIN_PROJECTED_RR = 6.0
eng.SWING_SKIP = 3
eng.POI_RETRACE_WINDOW = 50
eng.SL_MIN = 0.30

# ── Load all 4552 symbols ──
all_files = sorted(eng.CACHE_DIR.glob('*_60min_200.json'))
symbols = [f.stem.replace('_60min_200', '').replace('_', '.') for f in all_files]
print(f"Total symbols loaded: {len(symbols)}")

# ── Run ──
t0 = time.time()
result = eng.run_backtest(symbols, "V469-full-4552")
elapsed = time.time() - t0
print(f"\nElapsed: {elapsed:.0f}s ({elapsed/60:.1f}min)")

# ── Results ──
if result and result.get('all_trades'):
    trades = result['all_trades']
    stocks = result.get('stock_results', [])
    n = len(trades)
    wins = sum(1 for t in trades if t.get('won'))
    wr = wins / n * 100 if n else 0
    avg_rr = sum(t.get('rr', 0) for t in trades) / n if n else 0
    avg_pnl = sum(t.get('pnl_pct', 0) for t in trades) / n if n else 0
    avg_hold = sum(t.get('hold_bars', 0) for t in trades) / n if n else 0
    total_pnl = sum(t.get('pnl_pct', 0) for t in trades)
    
    print(f"\n{'='*70}")
    print(f"V469 FINAL FULL 4552-STOCK")
    print(f"{'='*70}")
    print(f"Stocks traded: {len(stocks)}/{len(symbols)} ({len(stocks)/len(symbols)*100:.1f}%)")
    print(f"Total trades: {n}")
    print(f"WR: {wr:.1f}% ({wins}/{n})")
    print(f"Avg RR: {avg_rr:.2f}x")
    print(f"Avg P&L: {avg_pnl:+.2f}%")
    print(f"Total P&L: {total_pnl:+.2f}%")
    print(f"Avg Hold: {avg_hold:.1f}bars")
    print(f"Elapsed: {elapsed:.0f}s")
    
    # ── Grade breakdown ──
    grades = {'A': [], 'B': [], 'C': []}
    for t in trades:
        g = t.get('signal_grade', 'C')
        grades.setdefault(g, []).append(t)
    print(f"\n{'─'*50}")
    print("Grade Breakdown:")
    for g in ['A', 'B', 'C']:
        gt = grades[g]
        if gt:
            gw = sum(1 for t in gt if t.get('won'))
            gr = sum(t.get('rr', 0) for t in gt) / len(gt)
            gp = sum(t.get('pnl_pct', 0) for t in gt) / len(gt)
            print(f"  Grade {g}: {len(gt)} trades | WR={gw/len(gt)*100:.1f}% | RR={gr:.2f}x | P&L={gp:+.2f}%")
    
    # ── RR distribution ──
    rr_buckets = {'<=1.5x': 0, '1.5-3x': 0, '3-5x': 0, '5-10x': 0, '>10x': 0}
    for t in trades:
        r = t.get('rr', 0)
        if r <= 1.5: rr_buckets['<=1.5x'] += 1
        elif r <= 3: rr_buckets['1.5-3x'] += 1
        elif r <= 5: rr_buckets['3-5x'] += 1
        elif r <= 10: rr_buckets['5-10x'] += 1
        else: rr_buckets['>10x'] += 1
    print(f"\nRR Distribution:")
    for k, v in rr_buckets.items():
        print(f"  {k}: {v} ({v/n*100:.1f}%)")
    
    # ── Save results for frontend ──
    outdir = eng.OUTPUT_DIR if hasattr(eng, 'OUTPUT_DIR') else Path('/root/.hermes/smc_opt_v469')
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    
    # Build trade_map (symbol -> trades)
    trade_map = {}
    offset = 0
    stock_summaries = []
    for sr in stocks:
        st = sr.get('symbol', sr.get('name', ''))
        n_t = sr.get('n_trades', 0)
        trade_map[st] = trades[offset:offset+n_t]
        offset += n_t
        stock_summaries.append({
            'symbol': st,
            'n_trades': n_t,
            'signal_grade': sr.get('signal_grade', 'C'),
        })
    
    # Save
    with open(outdir / 'v469_full_stocks.json', 'w') as f:
        json.dump(stock_summaries, f, indent=2)
    with open(outdir / 'v469_full_trade_map.json', 'w') as f:
        json.dump(trade_map, f, indent=2, default=str)
    with open(outdir / 'v469_full_trades.json', 'w') as f:
        json.dump(trades, f, indent=2, default=str)
    
    print(f"\n✅ Results saved to {outdir}/")
    print(f"  - v469_full_stocks.json ({len(stock_summaries)} stocks)")
    print(f"  - v469_full_trades.json ({len(trades)} trades)")
    print(f"  - v469_full_trade_map.json")
else:
    print("❌ No trades found or result is empty")
